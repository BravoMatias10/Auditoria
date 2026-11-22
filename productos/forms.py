from urllib.parse import urlsplit, urlunsplit

from django import forms
from django.core.exceptions import ValidationError

from .models import Auditoria, Producto, Resultado


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['nombre', 'precio']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'precio': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class AuditoriaForm(forms.ModelForm):
    class Meta:
        model = Auditoria
        fields = ['url', 'alcance']
        widgets = {
            'url': forms.URLInput(attrs={'placeholder': 'https://ejemplo.cl'}),
            'alcance': forms.Textarea(attrs={'rows': 4}),
        }
        help_texts = {
            'url': 'Usa una dirección HTTP o HTTPS pública. Se omiten parámetros y fragmentos. '
                   'Evita rutas con identificadores personales.',
            'alcance': 'Indica qué páginas o procesos revisarás y qué partes quedan fuera de la evaluación.',
        }

    def clean_url(self):
        url = urlsplit(self.cleaned_data['url'])
        if url.scheme.lower() not in ('http', 'https'):
            raise ValidationError('La dirección debe usar HTTP o HTTPS.')
        if url.username is not None or url.password is not None:
            raise ValidationError('Ingresa una dirección sin credenciales.')
        return urlunsplit((url.scheme, url.netloc, url.path, '', ''))


class AlcanceForm(AuditoriaForm):
    class Meta(AuditoriaForm.Meta):
        fields = ['alcance']


class ResultadoForm(forms.ModelForm):
    class Meta:
        model = Resultado
        fields = ['estado', 'fuente', 'evidencia', 'observacion', 'pendiente']
        widgets = {
            'evidencia': forms.Textarea(attrs={'rows': 5}),
            'observacion': forms.Textarea(attrs={'rows': 3}),
            'pendiente': forms.Textarea(attrs={'rows': 2}),
        }
        help_texts = {
            'evidencia': 'Indica la fecha, página pública o referencia interna y el hecho observado. '
                         'Omite contraseñas, identificadores y datos personales de terceros.',
            'observacion': 'Explica cómo la evidencia respalda el estado o justifica la inaplicabilidad.',
            'pendiente': 'Indica qué falta verificar o qué acción se recomienda.',
        }

    def clean(self):
        datos = super().clean()
        estado = datos.get('estado')
        fuente = datos.get('fuente')
        evidencia = datos.get('evidencia')

        if evidencia and not fuente:
            self.add_error('fuente', 'Identifica el tipo de evidencia registrada.')

        if estado in (Resultado.Estado.CUMPLE, Resultado.Estado.NO_CUMPLE, Resultado.Estado.NO_APLICA):
            if not evidencia and 'evidencia' not in self.errors:
                self.add_error('evidencia', 'Registra la evidencia que respalda este estado.')
            if not fuente and 'fuente' not in self.errors:
                self.add_error('fuente', 'Identifica el tipo de evidencia que respalda el estado.')

        if estado == Resultado.Estado.NO_APLICA and not datos.get('observacion'):
            self.add_error('observacion', 'Justifica por qué la obligación no se activa en este caso.')

        if estado == Resultado.Estado.CUMPLE and fuente:
            requerida = self.instance.fuente_requerida
            if fuente != requerida and fuente != Resultado.Fuente.AMBAS:
                self.add_error('fuente', 'Registra el tipo de evidencia indicado para verificar este criterio.')

        if (
            estado in (Resultado.Estado.NO_CUMPLE, Resultado.Estado.NO_APLICA)
            and fuente == Resultado.Fuente.PUBLICA
            and self.instance.fuente_requerida == Resultado.Fuente.INTERNA
        ):
            self.add_error('fuente', 'Este criterio requiere evidencia interna. Usa No verificable si falta.')
        return datos
