"""Consulta acotada de páginas públicas para evaluar indicios de privacidad."""

from dataclasses import dataclass
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException
from ipaddress import IPv4Address
import re
import socket
import ssl
from unicodedata import normalize
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from .models import Resultado


LIMITE_BYTES = 384 * 1024
LIMITE_PAGINAS_PRIVACIDAD = 2
LIMITE_REDIRECCIONES = 2
TIEMPO_CONEXION = 3
SENALES_PRIVACIDAD = ('privacidad', 'privacy', 'proteccion de datos', 'datos personales')
REDIRECCIONES = (301, 302, 303, 307, 308)


@dataclass
class Pagina:
    url: str
    html: str
    hsts: bool
    estado_http: int = 200
    aviso: str = ""


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
        self.texto = []
        self._enlace = None
        self._texto_enlace = []
        self._omitir = None
        try:
            self.feed(html)
            self.close()
        except AssertionError:
            self.enlaces.clear()
            self.texto.clear()

    def handle_starttag(self, tag, attrs):
        if self._omitir:
            return
        if tag in ('script', 'style', 'template'):
            self._omitir = tag
        elif tag == 'a':
            self._enlace = dict(attrs).get('href')
            self._texto_enlace = []

    def handle_endtag(self, tag):
        if self._omitir:
            if tag == self._omitir:
                self._omitir = None
            return
        if tag == 'a' and self._enlace:
            self.enlaces.append((self._enlace, texto_simple(' '.join(self._texto_enlace))))
            self._enlace = None

    def handle_data(self, data):
        if not self._omitir:
            self.texto.append(data)
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


def conexion_http(host, puerto, contexto_tls):
    # Conecta directamente a la IP ya validada. La comprobación TLS usa el nombre original.
    ip = direccion_publica(host, puerto)
    cliente = HTTPConnection(host, puerto, timeout=TIEMPO_CONEXION)
    conexion = socket.create_connection((ip, puerto), timeout=TIEMPO_CONEXION)
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
                    'Connection': 'close',
                })
                with cliente.getresponse() as respuesta:
                    pagina = Pagina(
                        url, '', bool(respuesta.getheader('Strict-Transport-Security')), respuesta.status,
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
                        contenido = respuesta.read(LIMITE_BYTES + 1)
                        charset = respuesta.headers.get_content_charset() or 'utf-8'
                        pagina.html = contenido[:LIMITE_BYTES].decode(charset, errors='replace')
                        if len(contenido) > LIMITE_BYTES:
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


def paginas_privacidad(pagina, contenido, dominio):
    visitadas = {pagina.url}
    intentos = 0
    if not pagina.aviso and es_enlace_privacidad(pagina.url, '') and any(
        senal in contenido.contenido for senal in SENALES_PRIVACIDAD
    ):
        yield pagina, contenido
        return
    for href, etiqueta in contenido.enlaces:
        try:
            enlace, host, _ = direccion_normalizada(urljoin(pagina.url, href))
            if host.removeprefix('www.') != dominio or enlace in visitadas:
                continue
            if not es_enlace_privacidad(enlace, etiqueta):
                continue
            if intentos == LIMITE_PAGINAS_PRIVACIDAD:
                break
            intentos += 1
            visitadas.add(enlace)
            politica = leer_pagina(enlace, dominio)
        except (PaginaInaccesible, ValueError):
            continue
        contenido_politica = ContenidoPublico(politica.html)
        if not politica.aviso and any(senal in contenido_politica.contenido for senal in SENALES_PRIVACIDAD):
            yield politica, contenido_politica


def hallazgo(url, evidencia, observacion, estado=Resultado.Estado.NO_VERIFICABLE, pendiente=''):
    return {
        'estado': estado,
        'fuente': Resultado.Fuente.PUBLICA,
        'evidencia': f'{evidencia} Página: {url}'[:2200],
        'observacion': observacion,
        'pendiente': pendiente,
    }


def evaluar_politica(pagina, contenido):
    texto = contenido.contenido
    version = re.search(r'\b(?:version|version de la politica)\s*[:v.]?\s*\d', texto)
    fecha = re.search(
        r'\b(?:ultima actualizacion|fecha de actualizacion|fecha de vigencia)\s*:?\s*\d', texto,
    )
    verificada = bool(version and fecha)
    resultados = {
        'Publicación y versión de la política': hallazgo(
            pagina.url, 'Se encontró una página pública de privacidad.',
            'La página indica su fecha de actualización o vigencia y su versión.' if verificada else
            'La política está publicada. La revisión no pudo confirmar su fecha y versión.',
            Resultado.Estado.CUMPLE if verificada else Resultado.Estado.NO_VERIFICABLE,
            '' if verificada else 'Confirmar la fecha y la versión de la política.',
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
        ('Información sobre los derechos', ('rectificacion', 'supresion', 'portabilidad', 'oposicion'),
         'La política contiene menciones a derechos de las personas.',
         'Confirmar qué derechos se explican y cómo se ejercen.'),
        ('Información sobre el período de conservación', ('conservacion de los datos', 'plazo de conservacion', 'periodo de conservacion'),
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
    for politica, contenido in paginas_privacidad(pagina, ContenidoPublico(pagina.html), dominio):
        politica_encontrada = True
        for criterio, resultado in evaluar_politica(politica, contenido).items():
            if criterio not in resultados or resultado['estado'] == Resultado.Estado.CUMPLE:
                resultados[criterio] = resultado

    if politica_encontrada:
        resumen = 'Se revisó la página indicada y se encontró una política de privacidad pública.'
    elif pagina.html:
        resumen = 'No encontramos una política de privacidad en los enlaces que pudimos leer.'
    else:
        resumen = 'Se pudo comprobar la respuesta del sitio. La información de privacidad quedó pendiente.'
    if pagina.aviso:
        resumen = f'{pagina.aviso} {resumen}'
    return Revision(resumen, resultados)
