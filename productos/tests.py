from datetime import datetime, timezone
from email.message import Message
from gzip import compress
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .criterios import CRITERIOS
from .models import Auditoria, Resultado
from .revision_publica import LIMITE_BYTES, Pagina, PaginaInaccesible, Revision, leer_recurso, revisar_sitio


class AuditoriasTests(TestCase):
    clave = 'Evaluacion-local-2026!'

    @classmethod
    def setUpTestData(cls):
        grupo = Group.objects.create(name='Usuario')
        cls.usuaria = User.objects.create_user('cuenta-propietaria', password=cls.clave)
        cls.otro = User.objects.create_user('cuenta-invitada', password=cls.clave)
        cls.admin = User.objects.create_superuser('cuenta-admin', '', cls.clave)
        cls.sin_rol = User.objects.create_user('cuenta-sin-rol', password=cls.clave, is_staff=True)
        cls.usuaria.groups.add(grupo)
        cls.otro.groups.add(grupo)

    def entrar(self, cuenta, cliente=None):
        cliente = cliente or self.client
        respuesta = cliente.post(reverse('login'), {
            'username': cuenta.username, 'password': self.clave,
        })
        self.assertRedirects(respuesta, reverse('listar'), fetch_redirect_response=False)

    def crear_auditoria(self, cuenta=None, sitio='https://sitio-ejemplo.cl/privacidad'):
        if cuenta:
            self.entrar(cuenta)
        with patch('productos.views.revisar_sitio', return_value=Revision('Consulta de prueba.', {})):
            respuesta = self.client.post(reverse('crear'), {
                'url': sitio, 'alcance': 'Portada pública y aviso de privacidad.',
            })
        auditoria = Auditoria.objects.latest('pk')
        self.assertRedirects(respuesta, reverse('detalle', args=[auditoria.pk]))
        return auditoria

    def obtener_criterio(self, auditoria, articulo):
        resultado = auditoria.resultados.get(articulo=articulo)
        url = reverse('editar_resultado', args=[auditoria.pk, resultado.pk])
        return resultado, url

    def test_usuaria_crea_evalua_y_abre_reporte(self):
        auditoria = self.crear_auditoria(
            self.usuaria, 'https://sitio-ejemplo.cl/privacidad?token=ficticio#identificador',
        )
        self.assertEqual(auditoria.propietario, self.usuaria)
        self.assertEqual(auditoria.url, 'https://sitio-ejemplo.cl/privacidad')
        self.assertEqual(auditoria.resultados.count(), len(CRITERIOS))
        self.assertFalse(auditoria.resultados.exclude(estado=Resultado.Estado.NO_VERIFICABLE).exists())

        resultado, url = self.obtener_criterio(auditoria, '3 g) y 14 ter a)')
        respuesta = self.client.post(url, {
            'estado': Resultado.Estado.CUMPLE, 'fuente': Resultado.Fuente.PUBLICA,
            'evidencia': 'Política versión 2, consultada el 22/11/2026.',
            'observacion': 'Visible desde el pie de la portada.',
        })
        self.assertRedirects(respuesta, reverse('detalle', args=[auditoria.pk]))
        resultado.refresh_from_db()
        self.assertEqual(resultado.estado, Resultado.Estado.CUMPLE)

        Auditoria.objects.filter(pk=auditoria.pk).update(
            creada=datetime(2026, 11, 22, 12, tzinfo=timezone.utc),
        )
        reporte = self.client.get(reverse('reporte', args=[auditoria.pk]))
        for texto in [
            'Reporte de auditoría', auditoria.url, auditoria.alcance, '14 ter a)',
            'Política versión 2', 'Visible desde el pie', 'Guardar como PDF',
            'No verificable', 'Acción pendiente', 'Evaluación de preparación para la reforma',
        ]:
            self.assertContains(reporte, texto)
        self.assertNotContains(reporte, self.usuaria.username)
        self.assertNotContains(reporte, 'token=ficticio')
        self.assertIn('no-store', reporte.headers['Cache-Control'])

    def test_otro_usuario_no_puede_leer_ni_modificar_registros_por_url(self):
        auditoria = self.crear_auditoria(self.usuaria)
        resultado, editar_criterio = self.obtener_criterio(auditoria, '15 bis')
        self.entrar(self.otro)
        self.assertNotContains(self.client.get(reverse('listar')), auditoria.url)

        for nombre in ['detalle', 'editar', 'eliminar', 'reporte']:
            with self.subTest(nombre=nombre):
                self.assertEqual(self.client.get(reverse(nombre, args=[auditoria.pk])).status_code, 404)
        self.assertEqual(self.client.get(editar_criterio).status_code, 404)
        self.assertEqual(self.client.post(editar_criterio, {'estado': 'cumple'}).status_code, 404)
        self.assertEqual(self.client.post(reverse('editar', args=[auditoria.pk]), {}).status_code, 404)
        self.assertEqual(self.client.post(reverse('eliminar', args=[auditoria.pk]), {}).status_code, 404)
        self.assertTrue(Resultado.objects.filter(pk=resultado.pk).exists())
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 302)

    def test_no_se_mezclan_criterios_de_distintas_auditorias(self):
        primera = self.crear_auditoria(self.usuaria)
        segunda = self.crear_auditoria(sitio='https://segundo-sitio.cl/')
        resultado, _ = self.obtener_criterio(segunda, '15 bis')
        enlace_cruzado = reverse('editar_resultado', args=[primera.pk, resultado.pk])
        self.assertEqual(self.client.get(enlace_cruzado).status_code, 404)
        self.assertEqual(self.client.post(enlace_cruzado, {}).status_code, 404)

    def test_admin_gestiona_usuarios_consulta_y_realiza_sus_auditorias(self):
        ajena = self.crear_auditoria(self.usuaria)
        propia = self.crear_auditoria(self.admin, 'https://administracion-ejemplo.cl/')
        panel = self.client.get(reverse('admin:auth_user_changelist'))
        self.assertContains(panel, self.usuaria.username)
        creada = self.client.post(reverse('admin:auth_user_add'), {
            'username': 'cuenta-creada-en-panel', 'password1': self.clave, 'password2': self.clave,
        })
        self.assertEqual(creada.status_code, 302)
        cuenta = User.objects.get(username='cuenta-creada-en-panel')
        grupo = Group.objects.get(name='Usuario')
        cambio = self.client.post(reverse('admin:auth_user_change', args=[cuenta.pk]), {
            'username': cuenta.username, 'is_active': 'on', 'groups': [grupo.pk],
            'date_joined_0': '2026-11-22', 'date_joined_1': '12:00:00', '_save': 'Guardar',
        })
        self.assertEqual(cambio.status_code, 302)
        self.assertTrue(cuenta.groups.filter(pk=grupo.pk).exists())
        listado = self.client.get(reverse('listar'))
        self.assertContains(listado, ajena.url)
        self.assertContains(listado, propia.url)
        self.assertContains(self.client.get(reverse('reporte', args=[ajena.pk])), ajena.url)
        self.assertEqual(self.client.get(reverse('editar', args=[ajena.pk])).status_code, 404)

        resultado, url = self.obtener_criterio(propia, '15 bis')
        guardado = self.client.post(url, {
            'estado': Resultado.Estado.NO_APLICA, 'fuente': Resultado.Fuente.INTERNA,
            'evidencia': 'Inventario sintético de proveedores, versión 1.',
            'observacion': 'El inventario acredita que no se encargan tratamientos a terceros.',
        })
        self.assertRedirects(guardado, reverse('detalle', args=[propia.pk]))
        resultado.refresh_from_db()
        self.assertEqual(resultado.estado, Resultado.Estado.NO_APLICA)
        self.assertContains(
            self.client.get(reverse('reporte', args=[propia.pk])), 'Inventario sintético',
        )

    def test_estados_determinados_necesitan_evidencia_y_no_aplica_justificacion(self):
        auditoria = self.crear_auditoria(self.usuaria)
        resultado, url = self.obtener_criterio(auditoria, '15 bis')
        for estado in [Resultado.Estado.CUMPLE, Resultado.Estado.NO_CUMPLE, Resultado.Estado.NO_APLICA]:
            with self.subTest(estado=estado):
                respuesta = self.client.post(url, {'estado': estado})
                self.assertTrue(respuesta.context['form'].has_error('evidencia'))
        no_aplica = self.client.post(url, {
            'estado': Resultado.Estado.NO_APLICA, 'fuente': Resultado.Fuente.INTERNA,
            'evidencia': 'Inventario de ejemplo.',
        })
        self.assertTrue(no_aplica.context['form'].has_error('observacion'))

        publica = self.client.post(url, {
            'estado': Resultado.Estado.CUMPLE, 'fuente': Resultado.Fuente.PUBLICA,
            'evidencia': 'Se observa un proveedor en la portada.',
        })
        self.assertTrue(publica.context['form'].has_error('fuente'))
        resultado.refresh_from_db()
        self.assertEqual(resultado.estado, Resultado.Estado.NO_VERIFICABLE)

    def test_reporte_escapa_evidencia_y_conserva_accion_pendiente(self):
        auditoria = self.crear_auditoria(self.usuaria)
        _, url = self.obtener_criterio(auditoria, '15 bis')
        respuesta = self.client.post(url, {
            'estado': Resultado.Estado.NO_VERIFICABLE, 'fuente': Resultado.Fuente.PUBLICA,
            'evidencia': '<script>alert(1)</script>', 'pendiente': 'Solicitar un contrato depurado.',
        })
        self.assertRedirects(respuesta, reverse('detalle', args=[auditoria.pk]))
        reporte = self.client.get(reverse('reporte', args=[auditoria.pk]))
        self.assertContains(reporte, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(reporte, '<script>alert(1)</script>')
        self.assertContains(reporte, 'Solicitar un contrato depurado.')

    def test_login_es_obligatorio_y_pertenecer_a_staff_no_otorga_rol(self):
        auditoria = self.crear_auditoria(self.usuaria)
        url = reverse('reporte', args=[auditoria.pk])
        anonimo = Client()
        self.assertRedirects(anonimo.get(url), reverse('login') + '?next=' + url)
        self.assertEqual(anonimo.get(reverse('privacidad')).status_code, 200)
        self.entrar(self.sin_rol)
        self.assertEqual(self.client.get(reverse('listar')).status_code, 403)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_acciones_de_escritura_requieren_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        navegador.force_login(self.usuaria)
        self.assertEqual(navegador.post(reverse('crear'), {}).status_code, 403)
        self.assertEqual(navegador.get(reverse('logout')).status_code, 405)
        self.assertEqual(navegador.post(reverse('logout')).status_code, 403)
        navegador.get(reverse('listar'))
        token = navegador.cookies['csrftoken'].value
        self.assertRedirects(
            navegador.post(reverse('logout'), {'csrfmiddlewaretoken': token}), reverse('login'),
        )

    def test_url_con_otro_esquema_o_credenciales_se_rechaza(self):
        self.entrar(self.usuaria)
        for url in ['ftp://ejemplo.cl/', 'https://cuenta:secreto@ejemplo.cl/']:
            respuesta = self.client.post(reverse('crear'), {'url': url, 'alcance': 'Portada.'})
            self.assertTrue(respuesta.context['form'].has_error('url'))
        self.assertFalse(Auditoria.objects.exists())

    def test_propietario_edita_y_elimina_con_confirmacion(self):
        auditoria = self.crear_auditoria(self.usuaria)
        editar = reverse('editar', args=[auditoria.pk])
        self.assertRedirects(self.client.post(editar, {'alcance': 'Solo portada.'}),
                             reverse('detalle', args=[auditoria.pk]))
        auditoria.refresh_from_db()
        self.assertEqual(auditoria.alcance, 'Solo portada.')
        eliminar = reverse('eliminar', args=[auditoria.pk])
        self.assertContains(self.client.get(eliminar), 'Eliminar auditoría')
        self.assertTrue(Auditoria.objects.filter(pk=auditoria.pk).exists())
        self.assertRedirects(self.client.post(eliminar), reverse('listar'))
        self.assertFalse(Resultado.objects.filter(auditoria_id=auditoria.pk).exists())

    @patch('productos.revision_publica.leer_pagina')
    def test_crear_audita_con_solo_la_url_y_presenta_un_resumen(self, consultar):
        portada = 'https://ejemplo.cl/'
        politica = 'https://ejemplo.cl/privacidad/'
        consultar.side_effect = [
            Pagina(portada, '<a href="/privacidad/">Política de privacidad</a>', False),
            Pagina(politica, (
                '<h1>Política de privacidad</h1>'
                '<p>Versión 2. Última actualización: 12 de octubre de 2026.</p>'
                '<p>El plazo de conservación de los datos es de 30 días.</p>'
                '<a href="mailto:privacidad@ejemplo.cl">Contacto de privacidad</a>'
            ), False),
        ]

        self.entrar(self.usuaria)
        self.assertContains(self.client.get(reverse('crear')), 'Auditar sitio')
        respuesta = self.client.post(reverse('crear'), {'url': portada})
        auditoria = Auditoria.objects.get(propietario=self.usuaria)
        self.assertRedirects(respuesta, reverse('detalle', args=[auditoria.pk]))

        def resultado(articulo):
            return auditoria.resultados.get(articulo=articulo)

        self.assertEqual(resultado('14 quinquies').estado, Resultado.Estado.CUMPLE)
        self.assertEqual(resultado('3 g) y 14 ter a)').estado, Resultado.Estado.CUMPLE)
        self.assertEqual(resultado('14 ter c)').estado, Resultado.Estado.CUMPLE)
        self.assertEqual(resultado('14 ter i)').estado, Resultado.Estado.CUMPLE)
        self.assertIn('30 días', resultado('14 ter i)').evidencia)
        self.assertEqual(resultado('3 c), 14 d) y 14 quáter').estado, Resultado.Estado.NO_VERIFICABLE)
        self.assertIn('https://ejemplo.cl/privacidad/', resultado('14 ter c)').evidencia)
        self.assertNotIn('privacidad@ejemplo.cl', resultado('14 ter c)').evidencia)
        reporte = self.client.get(reverse('reporte', args=[auditoria.pk]))
        self.assertContains(reporte, 'Hay puntos pendientes.')
        self.assertContains(reporte, 'se encontró una política de privacidad pública')
        self.assertContains(reporte, 'Cumple: 5')

    @patch('productos.revision_publica.leer_pagina', side_effect=PaginaInaccesible)
    def test_pagina_inaccesible_genera_informe_sin_inventar_resultados(self, consultar):
        self.entrar(self.usuaria)
        respuesta = self.client.post(reverse('crear'), {'url': 'https://ejemplo.cl/'})
        auditoria = Auditoria.objects.get(propietario=self.usuaria)
        self.assertRedirects(respuesta, reverse('detalle', args=[auditoria.pk]))
        self.assertTrue(auditoria.resumen_revision.startswith('No pudimos leer'))
        self.assertFalse(auditoria.resultados.exclude(estado=Resultado.Estado.NO_VERIFICABLE).exists())

    def test_aviso_explica_las_cookies_tecnicas(self):
        aviso = self.client.get(reverse('privacidad'))
        self.assertContains(aviso, 'sessionid')
        self.assertContains(aviso, 'csrftoken')
        self.assertContains(aviso, '14 días')
        self.assertContains(aviso, '364 días')


class RevisionPublicaTests(SimpleTestCase):
    @patch('productos.revision_publica.leer_pagina')
    def test_http_publico_y_enlace_externo_no_consultado(self, consultar):
        consultar.return_value = Pagina('http://ejemplo.cl/', (
            '<a href="https://otro.cl/privacidad">Política de privacidad</a>'
            '<script>Política de privacidad. Versión 3.</script>'
        ), False)
        with patch('productos.revision_publica.renderizar_html', return_value=('', '')):
            resultado = revisar_sitio('http://ejemplo.cl/')
        consultar.assert_called_once_with('http://ejemplo.cl/', 'ejemplo.cl')
        self.assertEqual(
            resultado.hallazgos['Protección observable de la conexión']['estado'],
            Resultado.Estado.NO_CUMPLE,
        )
        self.assertNotIn('Política de privacidad disponible', resultado.hallazgos)

    @patch('productos.revision_publica.socket.create_connection')
    @patch('productos.revision_publica.socket.getaddrinfo')
    def test_destino_local_no_abre_una_conexion(self, resolver, conectar):
        resolver.return_value = [(None, None, None, '', ('127.0.0.1', 80))]
        resultado = revisar_sitio('http://ejemplo.cl/')
        conectar.assert_not_called()
        self.assertEqual(resultado.hallazgos, {})

    def respuesta_http(self, conexion, estado, contenido=b'', **cabeceras):
        respuesta = MagicMock()
        respuesta.status = estado
        respuesta.headers = Message()
        respuesta.headers['Content-Type'] = 'text/html; charset=utf-8'
        for nombre, valor in cabeceras.items():
            respuesta.headers[nombre.replace('_', '-')] = valor
        respuesta.getheader.side_effect = respuesta.headers.get
        respuesta.read.return_value = contenido
        conexion.return_value.getresponse.return_value.__enter__.return_value = respuesta
        return respuesta

    @patch('productos.revision_publica.conexion_http')
    def test_pagina_extensa_conserva_el_hallazgo_https(self, conexion):
        respuesta = self.respuesta_http(conexion, 200, b'a' * (LIMITE_BYTES + 1))
        revision = revisar_sitio('https://ejemplo.cl/')
        respuesta.read.assert_called_once_with(LIMITE_BYTES + 1)
        self.assertIn('Solo se revisó la parte inicial', revision.resumen)
        conexion_observada = revision.hallazgos['Protección observable de la conexión']
        self.assertEqual(conexion_observada['estado'], Resultado.Estado.CUMPLE)
        self.assertIn('respondió con HTTPS', conexion_observada['evidencia'])
        self.assertNotIn('Política de privacidad disponible', revision.hallazgos)

    @patch('productos.revision_publica.conexion_http')
    def test_redireccion_a_otro_dominio_conserva_respuesta_inicial(self, conexion):
        self.respuesta_http(conexion, 302, Location='https://otro.cl/consentimiento')
        revision = revisar_sitio('https://ejemplo.cl/')
        self.assertIn('redirigió a otro dominio', revision.resumen)
        conexion.assert_called_once()
        self.assertEqual(
            revision.hallazgos['Protección observable de la conexión']['estado'],
            Resultado.Estado.CUMPLE,
        )

    @patch('productos.revision_publica.conexion_http')
    def test_respuesta_403_deja_una_explicacion_y_conexion_https(self, conexion):
        respuesta = self.respuesta_http(conexion, 403)
        revision = revisar_sitio('https://ejemplo.cl/')
        respuesta.read.assert_not_called()
        self.assertIn('código 403', revision.resumen)
        self.assertEqual(len(revision.hallazgos), 1)
        self.assertEqual(
            revision.hallazgos['Protección observable de la conexión']['estado'],
            Resultado.Estado.CUMPLE,
        )

    @patch('productos.revision_publica.conexion_http', side_effect=ConnectionRefusedError)
    def test_conexion_rechazada_informa_fallo_de_red_sin_hallazgos(self, conexion):
        revision = revisar_sitio('https://ejemplo.cl/')
        self.assertIn('no pudo conectarse al sitio desde esta red', revision.resumen)
        self.assertEqual(revision.hallazgos, {})

    @patch('productos.revision_publica.conexion_http')
    def test_pagina_comprimida_y_mayor_que_limite_anterior(self, conexion):
        contenido = (
            '<title>Política de privacidad</title><p>Ejercicio de derechos.</p>'
            + 'a' * (384 * 1024)
        ).encode()
        self.respuesta_http(conexion, 200, compress(contenido), Content_Encoding='gzip')
        revision = revisar_sitio('https://ejemplo.cl/privacidad')
        self.assertEqual(
            revision.hallazgos['Política de privacidad disponible']['estado'], Resultado.Estado.CUMPLE,
        )
        self.assertNotIn('Solo se revisó la parte inicial', revision.resumen)

    @patch('productos.revision_publica.conexion_http')
    def test_compresion_invalida_conserva_la_observacion_https(self, conexion):
        self.respuesta_http(conexion, 200, b'gzip no valido', Content_Encoding='gzip')
        revision = revisar_sitio('https://ejemplo.cl/')
        self.assertIn('No se pudo leer la página comprimida', revision.resumen)
        self.assertEqual(
            revision.hallazgos['Protección observable de la conexión']['estado'], Resultado.Estado.CUMPLE,
        )

    @patch('productos.revision_publica.leer_pagina')
    def test_youtube_consulta_politica_oficial_cuando_portada_no_la_muestra(self, consultar):
        portada = 'https://www.youtube.com/'
        politica = 'https://policies.google.com/privacy'
        consultar.side_effect = [
            Pagina(portada, '<title>YouTube</title>', True, aviso='Solo se revisó la parte inicial.'),
            Pagina(politica, '<title>Privacy Policy</title><p>Effective October 16, 2026</p><p>Cookies</p>', True),
        ]
        revision = revisar_sitio(portada)
        self.assertEqual(consultar.call_args_list[-1].args, (politica, 'policies.google.com'))
        disponible = revision.hallazgos['Política de privacidad disponible']
        self.assertEqual(disponible['estado'], Resultado.Estado.CUMPLE)
        self.assertIn(politica, disponible['evidencia'])
        self.assertIn('https://help.youtube.com/', disponible['evidencia'])
        self.assertEqual(revision.hallazgos['Fecha y versión de la política']['estado'], Resultado.Estado.NO_VERIFICABLE)
        self.assertIn('Se encontró la fecha', revision.hallazgos['Fecha y versión de la política']['observacion'])
        self.assertNotIn('Conservación, supresión y anonimización', revision.hallazgos)

    @patch('productos.revision_publica.leer_pagina')
    def test_acepta_politica_https_publicada_con_una_declaracion_explicita(self, consultar):
        portada = 'https://ejemplo.cl/'
        politica = 'https://portal-privacidad.cl/aviso'
        consultar.side_effect = [
            Pagina(portada, f'<link rel="privacy-policy" href="{politica}">', True),
            Pagina(politica, '<h1>Aviso de privacidad</h1><p>Información del servicio.</p>', True),
        ]
        revision = revisar_sitio(portada)
        self.assertEqual(consultar.call_args_list[-1].args, (politica, 'portal-privacidad.cl'))
        evidencia = revision.hallazgos['Política de privacidad disponible']['evidencia']
        self.assertIn(portada, evidencia)
        self.assertIn(politica, evidencia)

    @patch('productos.revision_publica.leer_pagina')
    def test_bloqueo_del_aviso_oficial_no_se_confunde_con_politica_verificada(self, consultar):
        consultar.side_effect = [
            Pagina('https://www.youtube.com/', '<title>YouTube</title>', True),
            Pagina('https://policies.google.com/privacy', '', True, 403, 'El sitio respondió con el código 403.'),
        ]
        revision = revisar_sitio('https://www.youtube.com/')
        self.assertNotIn('Política de privacidad disponible', revision.hallazgos)
        self.assertIn('no pudimos leerla', revision.resumen)


    @patch('productos.revision_publica.renderizar_html')
    @patch('productos.revision_publica.leer_pagina')
    def test_navegador_encuentra_un_enlace_agregado_con_javascript(self, consultar, renderizar):
        inicio = 'https://ejemplo.cl/'
        politica = 'https://ejemplo.cl/aviso'
        consultar.side_effect = [
            Pagina(inicio, '<main></main><script src="/inicio.js"></script>', True),
            Pagina(politica, '<h1>Aviso de privacidad</h1><p>Protegemos los datos de nuestros usuarios.</p>', True),
        ]
        renderizar.return_value = '<main><a href="/aviso">Aviso de privacidad</a></main>', ''
        revision = revisar_sitio(inicio)
        renderizar.assert_called_once()
        self.assertIn('El navegador permitió encontrar', revision.resumen)
        self.assertEqual(revision.hallazgos['Política de privacidad disponible']['estado'], Resultado.Estado.CUMPLE)

    @patch('productos.revision_publica.renderizar_html')
    @patch('productos.revision_publica.leer_pagina')
    def test_navegador_lee_una_politica_que_solo_tiene_titulo_en_html_inicial(self, consultar, renderizar):
        inicio = 'https://ejemplo.cl/'
        politica = 'https://ejemplo.cl/privacidad'
        consultar.side_effect = [
            Pagina(inicio, '<a href="/privacidad">Política de privacidad</a>', True),
            Pagina(politica, '<title>Política de privacidad</title><script src="/app.js"></script>', True),
        ]
        renderizar.return_value = '<h1>Política de privacidad</h1><p>Protegemos los datos de nuestros usuarios.</p>', ''
        revision = revisar_sitio(inicio)
        self.assertEqual(consultar.call_count, 2)
        self.assertEqual(renderizar.call_args.args[0].url, politica)
        self.assertEqual(revision.hallazgos['Política de privacidad disponible']['estado'], Resultado.Estado.CUMPLE)

    @patch('productos.revision_publica.conexion_http')
    def test_navegador_no_abre_recursos_de_otro_sitio(self, conectar):
        respuesta = leer_recurso('https://otro.cl/recurso.js', 'ejemplo.cl', 'script', 2)
        self.assertIsNone(respuesta)
        conectar.assert_not_called()


class RegistroTests(TestCase):
    def datos_registro(self, usuario='cuenta-piloto'):
        return {
            'username': usuario,
            'password1': 'Travesia-piloto-9142!',
            'password2': 'Travesia-piloto-9142!',
        }

    def test_desde_el_login_un_usuario_se_registra_e_inicia_sesion(self):
        login = reverse('login')
        registro = reverse('registro')
        self.assertContains(self.client.get(login), registro)
        formulario = self.client.get(registro)
        self.assertContains(formulario, 'Crear cuenta')
        self.assertContains(formulario, reverse('privacidad'))
        datos = self.datos_registro()
        datos.update(is_staff='on', is_superuser='on', email='prueba@ejemplo.cl')
        self.assertRedirects(self.client.post(registro, datos), login)
        cuenta = User.objects.get(username=datos['username'])
        self.assertEqual(list(cuenta.groups.values_list('name', flat=True)), ['Usuario'])
        self.assertFalse(cuenta.is_staff)
        self.assertFalse(cuenta.is_superuser)
        self.assertEqual(cuenta.email, '')
        self.assertTrue(cuenta.check_password(datos['password1']))
        self.assertRedirects(self.client.post(login, {
            'username': datos['username'], 'password': datos['password1'],
        }), reverse('listar'))
        self.assertRedirects(self.client.get(registro), reverse('listar'))
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 302)

    def test_registro_rechaza_nombre_repetido_y_contrasenas_distintas(self):
        registro = reverse('registro')
        datos = self.datos_registro()
        User.objects.create_user(datos['username'], password='OtroAcceso-2026!')
        self.assertTrue(self.client.post(registro, datos).context['form'].has_error('username'))
        distintos = self.datos_registro('cuenta-nueva')
        distintos['password2'] = 'OtraClave-2026!'
        self.assertTrue(self.client.post(registro, distintos).context['form'].has_error('password2'))
        self.assertFalse(User.objects.filter(username='cuenta-nueva').exists())

    def test_registro_requiere_csrf(self):
        navegador = Client(enforce_csrf_checks=True)
        self.assertEqual(navegador.post(reverse('registro'), self.datos_registro()).status_code, 403)
        self.assertEqual(User.objects.count(), 0)
