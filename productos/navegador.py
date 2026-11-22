"""Lee contenido público que el sitio muestra al ejecutar JavaScript."""

from contextlib import closing
from time import monotonic


LIMITE_RECURSOS = 12
LIMITE_DOM = 2 * 1024 * 1024
TIEMPO_NAVEGACION = 7
RECURSOS = ('script', 'stylesheet', 'xhr', 'fetch')


def renderizar_html(pagina, leer_recurso):
    try:
        from playwright.sync_api import Error, TimeoutError, sync_playwright
    except ImportError:
        return '', 'Instala Playwright y Chromium para revisar contenido que se carga con JavaScript.'

    try:
        with sync_playwright() as playwright:
            with closing(playwright.chromium.launch(
                chromium_sandbox=True,
                timeout=5000,
                args=[
                    '--proxy-server=http://auditoria-sin-red.invalid:1',
                    '--proxy-bypass-list=<-loopback>',
                    '--host-resolver-rules=MAP * ~NOTFOUND',
                    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                    '--disable-quic',
                    '--js-flags=--max-old-space-size=128',
                ],
            )) as navegador:
                contexto = navegador.new_context(service_workers='block', accept_downloads=False)
                contexto.route_web_socket('**/*', lambda websocket: websocket.close())
                pestana = contexto.new_page()
                recursos = 0
                fin = monotonic() + TIEMPO_NAVEGACION

                def atender(ruta):
                    nonlocal recursos
                    solicitud = ruta.request
                    if solicitud.method != 'GET' or monotonic() >= fin:
                        ruta.abort()
                        return
                    if solicitud.resource_type == 'document' and solicitud.url == pagina.url:
                        cabeceras = {'content-type': 'text/html; charset=utf-8'}
                        if pagina.csp:
                            cabeceras['content-security-policy'] = pagina.csp
                        ruta.fulfill(status=200, headers=cabeceras, body=pagina.html)
                        return
                    if solicitud.resource_type not in RECURSOS or recursos >= LIMITE_RECURSOS:
                        ruta.abort()
                        return

                    recursos += 1
                    respuesta = leer_recurso(solicitud.url, solicitud.resource_type, fin - monotonic())
                    if respuesta is None:
                        ruta.abort()
                        return
                    tipo, contenido = respuesta
                    ruta.fulfill(
                        status=200,
                        headers={'content-type': tipo, 'x-content-type-options': 'nosniff'},
                        body=contenido,
                    )

                contexto.route('**/*', atender)
                try:
                    pestana.goto(pagina.url, wait_until='domcontentloaded', timeout=4500)
                    pestana.wait_for_load_state('networkidle', timeout=1500)
                except TimeoutError:
                    # Puede haber contenido visible aun cuando algún recurso siga pendiente.
                    pass

                if pestana.url != pagina.url:
                    return '', 'La página cambió de dirección durante la revisión con navegador.'
                html = pestana.locator('html').evaluate(
                    '(nodo, limite) => nodo.outerHTML.slice(0, limite + 1)', LIMITE_DOM, timeout=1000,
                )
                if len(html) > LIMITE_DOM:
                    return '', 'El contenido mostrado en el navegador excedió el límite de lectura.'
                return html, ''
    except Error as error:
        if "Executable doesn't exist" in str(error):
            return '', 'Chromium aún no está instalado. Consulta los pasos de instalación del proyecto.'
        if 'No usable sandbox' in str(error):
            return '', 'El sistema no permitió iniciar Chromium en su entorno aislado.'
        return '', 'Chromium no pudo completar la lectura de la página.'
