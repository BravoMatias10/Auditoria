"""Consulta acotada de páginas públicas para evaluar indicios de privacidad."""

from dataclasses import dataclass, replace
from gzip import BadGzipFile, GzipFile
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException
from io import BytesIO
from ipaddress import IPv4Address
import re
import socket
import ssl
from unicodedata import normalize
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from zlib import error as ErrorCompresion

from .models import Resultado
from .navegador import renderizar_html


LIMITE_BYTES = 2 * 1024 * 1024
LIMITE_PAGINAS_PRIVACIDAD = 2
LIMITE_REDIRECCIONES = 2
TIEMPO_CONEXION = 3
SENALES_PRIVACIDAD = ('privacidad', 'privacy', 'proteccion de datos', 'datos personales')
TITULOS_POLITICA = (
    'politica de privacidad', 'aviso de privacidad', 'politica de proteccion de datos',
    'privacy policy', 'privacy notice', 'data protection policy',
)
REDIRECCIONES = (301, 302, 303, 307, 308)
POLITICAS_OFICIALES = {
    'youtube.com': (
        'https://policies.google.com/privacy',
        'https://help.youtube.com/intl/es-419/policies/privacy/',
    ),
}


@dataclass
class Pagina:
    url: str
    html: str
    hsts: bool
    estado_http: int = 200
    aviso: str = ""
    csp: str = ""


@dataclass
class Revision:
    resumen: str
    hallazgos: dict


class PaginaInaccesible(Exception):
    """La URL no se pudo consultar dentro del alcance de la revisión."""


def texto_simple(texto):
    texto = normalize('NFKD', texto.casefold()).encode('ascii', 'ignore').decode('ascii')
    return ' '.join(texto.split())


class ContenidoPublico(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.enlaces = []
        self.politicas_declaradas = []
        self.encabezados = []
        self.texto = []
        self._enlace = None
        self._texto_enlace = []
        self._omitir = None
        self._encabezado = None
        try:
            self.feed(html)
            self.close()
        except AssertionError:
            self.enlaces.clear()
            self.politicas_declaradas.clear()
            self.encabezados.clear()
            self.texto.clear()

    def handle_starttag(self, tag, attrs):
        if self._omitir:
            return
        if tag in ('script', 'style', 'template'):
            self._omitir = tag
        elif tag in ('title', 'h1', 'h2'):
            self._encabezado = tag
        elif tag in ('link', 'a'):
            atributos = dict(attrs)
            href = atributos.get('href')
            if href and 'privacy-policy' in (atributos.get('rel') or '').lower().split():
                self.politicas_declaradas.append(href)
            if tag == 'a':
                self._enlace = href
                self._texto_enlace = []

    def handle_endtag(self, tag):
        if self._omitir:
            if tag == self._omitir:
                self._omitir = None
            return
        if tag == self._encabezado:
            self._encabezado = None
        if tag == 'a' and self._enlace:
            self.enlaces.append((self._enlace, texto_simple(' '.join(self._texto_enlace))))
            self._enlace = None

    def handle_data(self, data):
        if not self._omitir:
            self.texto.append(data)
            if self._encabezado:
                self.encabezados.append(data)
            if self._enlace:
                self._texto_enlace.append(data)

    @property
    def contenido(self):
        return texto_simple(' '.join(self.texto))


def direccion_normalizada(url):
    try:
        partes = urlsplit(url)
        puerto = {'http': 80, 'https': 443}.get(partes.scheme)
        if (
            not puerto or not partes.hostname or partes.username is not None
            or partes.password is not None or partes.port not in (None, puerto)
            or partes.path.startswith('//') or len(url) > 500
        ):
            raise PaginaInaccesible
        host = partes.hostname.rstrip('.').encode('idna').decode('ascii')
        if not re.fullmatch(r'[a-z0-9.-]+', host) or '.' not in host:
            raise PaginaInaccesible
        ruta = quote(partes.path or '/', safe="/%:@!$&'()*+,;=-._~")
    except (UnicodeError, ValueError) as error:
        raise PaginaInaccesible from error
    return urlunsplit((partes.scheme, host, ruta, '', '')), host, puerto


def direccion_publica(host, puerto):
    direcciones = socket.getaddrinfo(host, puerto, socket.AF_INET, socket.SOCK_STREAM)
    for direccion in direcciones:
        ip = IPv4Address(direccion[4][0])
        if ip.is_global and not ip.is_multicast and not ip.is_reserved:
            return str(ip)
    raise PaginaInaccesible("La dirección apunta a una red local o no tiene un destino público IPv4.")


def conexion_http(host, puerto, contexto_tls, timeout=TIEMPO_CONEXION):
    # Conecta directamente a la IP ya validada. La comprobación TLS usa el nombre original.
    ip = direccion_publica(host, puerto)
    cliente = HTTPConnection(host, puerto, timeout=timeout)
    conexion = socket.create_connection((ip, puerto), timeout=timeout)
    try:
        if contexto_tls:
            conexion = contexto_tls.wrap_socket(conexion, server_hostname=host)
    except (OSError, ValueError):
        conexion.close()
        raise
    cliente.sock = conexion
    return cliente


def motivo_fallo(error):
    if isinstance(error, PaginaInaccesible):
        return str(error)
    if isinstance(error, socket.gaierror):
        return 'No se encontró el dominio. Revisa cómo escribiste la dirección.'
    if isinstance(error, ssl.SSLError):
        return 'No se pudo verificar la conexión segura (HTTPS).'
    if isinstance(error, TimeoutError):
        return 'El sitio tardó demasiado en responder.'
    if isinstance(error, OSError):
        return 'La aplicación no pudo conectarse al sitio desde esta red.'
    return 'La respuesta del sitio no se pudo leer.'


def leer_cuerpo(respuesta, limite):
    contenido = respuesta.read(limite + 1)
    codificacion = respuesta.getheader('Content-Encoding') or 'identity'
    if codificacion.lower() == 'gzip':
        if len(contenido) > limite:
            raise PaginaInaccesible('La página comprimida supera el tamaño que podemos revisar.')
        try:
            with GzipFile(fileobj=BytesIO(contenido)) as archivo:
                contenido = archivo.read(limite + 1)
        except (BadGzipFile, EOFError, ErrorCompresion) as error:
            raise PaginaInaccesible('No se pudo leer la página comprimida.') from error
    elif codificacion.lower() != 'identity':
        raise PaginaInaccesible('El sitio usa un formato de compresión que no se puede leer.')

    return contenido[:limite], len(contenido) > limite


def leer_recurso(url, dominio, recurso, tiempo):
    if tiempo <= 0:
        return None
    try:
        url, host, puerto = direccion_normalizada(url)
        if host.removeprefix('www.') != dominio:
            return None
        partes = urlsplit(url)
        contexto = ssl.create_default_context() if partes.scheme == 'https' else None
        cliente = conexion_http(host, puerto, contexto, timeout=min(tiempo, TIEMPO_CONEXION))
        try:
            cliente.request('GET', partes.path, headers={
                'User-Agent': 'AuditoriaAcademica/1.0', 'Accept-Encoding': 'gzip',
                'Connection': 'close',
            })
            with cliente.getresponse() as respuesta:
                if respuesta.status != 200:
                    return None
                tipo = respuesta.headers.get_content_type()
                if recurso == 'script' and tipo not in (
                    'application/javascript', 'text/javascript', 'application/ecmascript', 'text/ecmascript',
                ):
                    return None
                if recurso == 'stylesheet' and tipo != 'text/css':
                    return None
                if recurso in ('xhr', 'fetch') and tipo not in (
                    'application/json', 'text/html', 'text/plain',
                ) and not tipo.endswith('+json'):
                    return None
                contenido, parcial = leer_cuerpo(respuesta, 512 * 1024)
                if not parcial:
                    return respuesta.headers.get('Content-Type', tipo), contenido
        finally:
            cliente.close()
    except (PaginaInaccesible, OSError, HTTPException, ValueError, LookupError):
        return None
    return None


def leer_pagina(url, dominio):
    ultima_respuesta = None
    try:
        for _ in range(LIMITE_REDIRECCIONES + 1):
            url, host, puerto = direccion_normalizada(url)
            if host.removeprefix('www.') != dominio:
                raise PaginaInaccesible('El sitio redirigió a otro dominio. Esa página quedó fuera de esta revisión.')
            es_https = urlsplit(url).scheme == 'https'
            contexto = ssl.create_default_context() if es_https else None
            cliente = conexion_http(host, puerto, contexto)
            try:
                cliente.request('GET', urlsplit(url).path, headers={
                    'User-Agent': 'AuditoriaAcademica/1.0',
                    'Accept': 'text/html, application/xhtml+xml',
                    'Accept-Language': 'es-CL,es;q=0.9,en;q=0.5',
                    'Accept-Encoding': 'gzip',
                    'Connection': 'close',
                })
                with cliente.getresponse() as respuesta:
                    pagina = Pagina(
                        url, '', bool(respuesta.getheader('Strict-Transport-Security')), respuesta.status,
                        csp=respuesta.getheader('Content-Security-Policy') or '',
                    )
                    ultima_respuesta = pagina
                    destino = respuesta.getheader('Location')
                    if respuesta.status in REDIRECCIONES and destino:
                        url = urljoin(url, destino)
                        continue
                    if respuesta.status != 200:
                        pagina.aviso = (
                            f'El sitio respondió con el código {respuesta.status}. '
                            'No se pudo leer una página pública en esa respuesta.'
                        )
                    elif respuesta.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
                        pagina.aviso = 'La dirección devolvió un archivo u otro contenido distinto de una página web.'
                    else:
                        contenido, parcial = leer_cuerpo(respuesta, LIMITE_BYTES)
                        charset = respuesta.headers.get_content_charset() or 'utf-8'
                        pagina.html = contenido.decode(charset, errors='replace')
                        if parcial:
                            pagina.aviso = 'La página es extensa. Solo se revisó la parte inicial.'
                    return pagina
            finally:
                cliente.close()
        raise PaginaInaccesible('La página hizo demasiadas redirecciones.')
    except (PaginaInaccesible, OSError, HTTPException, ValueError, LookupError) as error:
        motivo = motivo_fallo(error)
        if ultima_respuesta is not None:
            ultima_respuesta.aviso = motivo
            return ultima_respuesta
        raise PaginaInaccesible(motivo) from error


def es_enlace_privacidad(href, etiqueta):
    ruta = texto_simple(urlsplit(href).path.replace('-', ' ').replace('_', ' '))
    return any(senal in etiqueta or senal in ruta for senal in SENALES_PRIVACIDAD)


def paginas_privacidad(pagina, contenido, dominio, cargadas, renderizar=None):
    visitadas = {pagina.url}
    intentos = 0
    if es_enlace_privacidad(pagina.url, '') and es_politica_legible(pagina, contenido):
        yield pagina, contenido, ''
        return
    candidatos = [(href, '', True) for href in contenido.politicas_declaradas]
    candidatos += [(href, etiqueta, False) for href, etiqueta in contenido.enlaces]
    for href, etiqueta, declarada in candidatos:
        try:
            enlace, host, _ = direccion_normalizada(urljoin(pagina.url, href))
            dominio_enlace = host.removeprefix('www.')
            externa = dominio_enlace != dominio
            if enlace in visitadas or (externa and not (declarada and enlace.startswith('https://'))):
                continue
            if not declarada and not es_enlace_privacidad(enlace, etiqueta):
                continue
            if intentos == LIMITE_PAGINAS_PRIVACIDAD:
                break
            intentos += 1
            visitadas.add(enlace)
            if enlace not in cargadas:
                cargadas[enlace] = None
                cargadas[enlace] = leer_pagina(enlace, dominio_enlace)
        except (PaginaInaccesible, ValueError):
            continue
        politica = cargadas[enlace]
        if politica is None:
            continue
        contenido_politica = ContenidoPublico(politica.html)
        if renderizar and not es_politica_legible(politica, contenido_politica):
            politica = renderizar(politica)
            contenido_politica = ContenidoPublico(politica.html)
        if es_politica_legible(politica, contenido_politica):
            yield politica, contenido_politica, pagina.url if externa else ''


def es_politica_legible(pagina, contenido):
    encabezados = texto_simple(' '.join(contenido.encabezados))
    tiene_texto = len(contenido.contenido) > len(encabezados)
    return not pagina.aviso and tiene_texto and any(senal in encabezados for senal in TITULOS_POLITICA)


def leer_politica_oficial(url):
    _, dominio, _ = direccion_normalizada(url)
    try:
        pagina = leer_pagina(url, dominio)
    except PaginaInaccesible:
        return None
    contenido = ContenidoPublico(pagina.html)
    if es_politica_legible(pagina, contenido):
        return pagina, contenido
    return None


def hallazgo(url, evidencia, observacion, estado=Resultado.Estado.NO_VERIFICABLE, pendiente=''):
    return {
        'estado': estado,
        'fuente': Resultado.Fuente.PUBLICA,
        'evidencia': f'{evidencia} Página: {url}'[:2200],
        'observacion': observacion,
        'pendiente': pendiente,
    }


def evaluar_politica(pagina, contenido, referencia=''):
    texto = contenido.contenido
    version = re.search(r'\b(?:version|version de la politica)\s*[:v.]?\s*\d', texto)
    fecha = re.search(
        r'\b(?:ultima actualizacion|fecha de actualizacion|fecha de vigencia|vigente desde|'
        r'entrada en vigor|effective date|effective|last updated)\s*:?\s*'
        r'(?:\d{1,4}\b|[a-z]{3,9}\s+\d{1,2}\b)',
        texto,
    )
    verificada = bool(version and fecha)
    evidencia = 'Se abrió una política de privacidad pública.'
    if referencia:
        evidencia += f' Referencia a la política: {referencia}.'
    resultados = {
        'Política de privacidad disponible': hallazgo(
            pagina.url, evidencia,
            'Este punto verifica que la política está disponible. Su contenido se evalúa por separado.',
            Resultado.Estado.CUMPLE,
        ),
        'Fecha y versión de la política': hallazgo(
            pagina.url, 'Se encontró una página pública de privacidad.',
            'La página indica su fecha de actualización o vigencia y su versión.' if verificada else
            'Se encontró la fecha, pero no una versión clara.' if fecha else
            'Se encontró la versión, pero no una fecha clara.' if version else
            'La revisión no pudo identificar una fecha ni una versión claras.',
            Resultado.Estado.CUMPLE if verificada else Resultado.Estado.NO_VERIFICABLE,
            '' if verificada else 'Confirmar la fecha o la versión que falta identificar.',
        )
    }

    if any(
        re.match(r'mailto:[^?\s@]+@[^?\s@]+\.[^?\s@]+(?:\?|$)', href, re.IGNORECASE)
        and any(senal in texto_simple(href.split('?')[0]) or senal in etiqueta
                for senal in SENALES_PRIVACIDAD)
        for href, etiqueta in contenido.enlaces
    ):
        resultados['Publicación del canal de privacidad'] = hallazgo(
            pagina.url, 'La política publica un enlace de correo identificado como canal de privacidad.',
            'Se comprobó que el canal está publicado. Su funcionamiento se evalúa por separado.',
            Resultado.Estado.CUMPLE,
        )

    indicios = (
        ('Identificación del responsable', ('responsable del tratamiento', 'responsable de datos'),
         'La política menciona al responsable.',
         'Confirmar que la política identifica a la entidad y a las personas que corresponda.'),
        ('Información sobre los derechos',
         ('rectificacion', 'supresion', 'portabilidad', 'oposicion', 'privacy rights', 'right to access'),
         'La política contiene menciones a derechos de las personas.',
         'Confirmar qué derechos se explican y cómo se ejercen.'),
        ('Información sobre el período de conservación',
         ('conservacion de los datos', 'plazo de conservacion', 'periodo de conservacion',
          'conservar su informacion', 'retaining your information', 'retention period'),
         'La política menciona la conservación de los datos.',
         'Confirmar que se informa un plazo o período para los datos tratados.'),
        ('Información sobre el recurso ante la Agencia', ('agencia de proteccion de datos personales',),
         'La política menciona a la Agencia de Protección de Datos Personales.',
         'Confirmar si se explica cuándo acudir a la Agencia.'),
        ('Cookies, rastreo y marketing', ('cookies',),
         'La política contiene información sobre cookies.',
         'Confirmar para qué se usan y cuáles se activan en la práctica.'),
    )
    for criterio, claves, evidencia, pendiente in indicios:
        if any(clave in texto for clave in claves):
            resultados[criterio] = hallazgo(
                pagina.url, evidencia, 'Se encontró una mención que requiere confirmación.', pendiente=pendiente,
            )

    plazo = re.search(
        r'\bplazo de conservacion(?: de (?:los|tus|sus) datos)?\s*'
        r'(?:es de|sera de|:)\s*(\d{1,4})\s+(dias?|mes(?:es)?|anos?)\b',
        texto,
    )
    if plazo:
        duracion = f"{plazo[1]} {plazo[2].replace('ano', 'año').replace('dia', 'día')}"
        resultados['Información sobre el período de conservación'] = hallazgo(
            pagina.url, f'La política publica un plazo de conservación de {duracion}.',
            'Comprobamos que el plazo está publicado. Para saber si se respeta hacen falta registros internos.',
            Resultado.Estado.CUMPLE,
        )
    return resultados


def buscar_con_navegador(pagina, dominio, cargadas):
    intentos = 0
    aviso = ''

    def renderizar(documento):
        nonlocal intentos, aviso
        if intentos >= 2 or aviso or documento.aviso or not re.search(r'<script[\s>]', documento.html, re.I):
            return documento
        intentos += 1
        _, host, _ = direccion_normalizada(documento.url)
        dominio_recurso = host.removeprefix('www.')
        html, aviso = renderizar_html(
            documento, lambda url, recurso, tiempo: leer_recurso(url, dominio_recurso, recurso, tiempo),
        )
        return replace(documento, html=html) if html else documento

    portada = renderizar(pagina)
    hallazgos = {}
    for politica in paginas_privacidad(
        portada, ContenidoPublico(portada.html), dominio, cargadas, renderizar=renderizar,
    ):
        hallazgos.update(evaluar_politica(*politica))
    if hallazgos:
        return hallazgos, 'El navegador permitió encontrar y leer una política de privacidad pública.'
    if intentos and not aviso:
        aviso = 'También se revisó el contenido mostrado con JavaScript.'
    return {}, aviso


def revisar_sitio(url):
    try:
        url, host, _ = direccion_normalizada(url)
        dominio = host.removeprefix('www.')
        pagina = leer_pagina(url, dominio)
    except PaginaInaccesible as error:
        causa = str(error) or 'Comprueba que abre públicamente y que la URL es correcta.'
        return Revision(f'No pudimos leer la página indicada. {causa}', {})

    es_https = urlsplit(pagina.url).scheme == 'https'
    if es_https:
        estado = Resultado.Estado.CUMPLE
        conexion = 'La dirección respondió con HTTPS.' if pagina.aviso else 'La página revisada cargó con HTTPS.'
        pendiente = ''
    elif pagina.estado_http == 200:
        estado = Resultado.Estado.NO_CUMPLE
        conexion = 'La página revisada cargó con HTTP.'
        pendiente = 'Comprobar que la página redirija a HTTPS.'
    else:
        estado = Resultado.Estado.NO_VERIFICABLE
        conexion = 'Se observó una respuesta HTTP, pero no se pudo confirmar la conexión de la página de destino.'
        pendiente = 'Comprobar si la página de destino usa HTTPS.'
    resultados = {
        'Protección observable de la conexión': hallazgo(
            pagina.url,
            conexion + (' La respuesta anuncia HSTS.' if es_https and pagina.hsts else ''),
            'Este resultado se refiere a la respuesta observada en la dirección indicada.',
            estado,
            pendiente,
        )
    }

    politica_encontrada = False
    cargadas = {}
    for politica, contenido, referencia in paginas_privacidad(
        pagina, ContenidoPublico(pagina.html), dominio, cargadas,
    ):
        politica_encontrada = True
        for criterio, resultado in evaluar_politica(politica, contenido, referencia).items():
            if criterio not in resultados or resultado['estado'] == Resultado.Estado.CUMPLE:
                resultados[criterio] = resultado

    if politica_encontrada:
        resumen = 'Se revisó la página indicada y se encontró una política de privacidad pública.'
    elif dominio in POLITICAS_OFICIALES:
        url_politica, referencia = POLITICAS_OFICIALES[dominio]
        politica = leer_politica_oficial(url_politica)
        if politica:
            resultados.update(evaluar_politica(*politica, referencia=referencia))
            resumen = 'Encontramos y revisamos la política pública enlazada desde la ayuda oficial del servicio.'
        else:
            resumen = 'La ayuda oficial enlaza una política de privacidad, pero no pudimos leerla.'
    elif pagina.html:
        resumen = 'No encontramos una política de privacidad en los enlaces que pudimos leer.'
    else:
        resumen = 'Se pudo comprobar la respuesta del sitio. La información de privacidad quedó pendiente.'
    if 'Política de privacidad disponible' not in resultados and pagina.html:
        hallazgos, nota_navegador = buscar_con_navegador(pagina, dominio, cargadas)
        if hallazgos:
            resultados.update(hallazgos)
            resumen = nota_navegador
        elif nota_navegador:
            resumen = f'{resumen} {nota_navegador}'
    if pagina.aviso:
        resumen = f'{pagina.aviso} {resumen}'
    return Revision(resumen[:350], resultados)
