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
    raise PaginaInaccesible


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


def leer_pagina(url, dominio):
    try:
        for _ in range(LIMITE_REDIRECCIONES + 1):
            url, host, puerto = direccion_normalizada(url)
            if host.removeprefix('www.') != dominio:
                raise PaginaInaccesible
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
                    if respuesta.status in REDIRECCIONES and respuesta.getheader('Location'):
                        url = urljoin(url, respuesta.getheader('Location'))
                        continue
                    tipo = respuesta.headers.get_content_type()
                    if respuesta.status != 200 or tipo not in ('text/html', 'application/xhtml+xml'):
                        raise PaginaInaccesible
                    contenido = respuesta.read(LIMITE_BYTES + 1)
                    if len(contenido) > LIMITE_BYTES:
                        raise PaginaInaccesible
                    charset = respuesta.headers.get_content_charset() or 'utf-8'
                    html = contenido.decode(charset, errors='replace')
                    return Pagina(url, html, bool(respuesta.getheader('Strict-Transport-Security')))
            finally:
                cliente.close()
    except (OSError, HTTPException, UnicodeError, ValueError, LookupError) as error:
        raise PaginaInaccesible from error
    raise PaginaInaccesible


def es_enlace_privacidad(href, etiqueta):
    ruta = texto_simple(urlsplit(href).path.replace('-', ' ').replace('_', ' '))
    return any(senal in etiqueta or senal in ruta for senal in SENALES_PRIVACIDAD)


def paginas_privacidad(pagina, contenido, dominio):
    visitadas = {pagina.url}
    intentos = 0
    if es_enlace_privacidad(pagina.url, '') and any(
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
        if any(senal in contenido_politica.contenido for senal in SENALES_PRIVACIDAD):
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
    except PaginaInaccesible:
        return Revision(
            'No pudimos leer la página indicada. Comprueba que abre públicamente y que la URL es correcta.',
            {},
        )

    es_https = urlsplit(pagina.url).scheme == 'https'
    conexion = 'La página revisada cargó con HTTPS.' if es_https else 'La página revisada cargó con HTTP.'
    resultados = {
        'Protección observable de la conexión': hallazgo(
            pagina.url,
            conexion + (' La respuesta anuncia HSTS.' if es_https and pagina.hsts else ''),
            'Este resultado se refiere a la conexión de la página consultada.',
            Resultado.Estado.CUMPLE if es_https else Resultado.Estado.NO_CUMPLE,
            '' if es_https else 'Comprobar que la página redirija a HTTPS.',
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
    else:
        resumen = (
            'Se revisó la página indicada. No encontramos una política de privacidad en los enlaces que pudimos leer.'
        )
    return Revision(resumen, resultados)
