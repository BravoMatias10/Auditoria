from datetime import datetime, timezone

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from .criterios import CRITERIOS
from .models import Auditoria, Resultado


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
