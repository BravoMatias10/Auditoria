from django.conf import settings
from django.db import models

class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    precio = models.PositiveIntegerField()

    def __str__(self):
        return self.nombre
# Create your models here.


class Auditoria(models.Model):
    propietario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='auditorias'
    )
    url = models.URLField('URL pública', max_length=500)
    alcance = models.CharField('alcance de la revisión', max_length=1200)
    creada = models.DateTimeField(auto_now_add=True)
    marco = models.CharField(max_length=280)

    class Meta:
        ordering = ('-creada', '-pk')

    def __str__(self):
        return self.url


class Resultado(models.Model):
    class Estado(models.TextChoices):
        CUMPLE = 'cumple', 'Cumple'
        NO_CUMPLE = 'no_cumple', 'No cumple'
        NO_VERIFICABLE = 'no_verificable', 'No verificable'
        NO_APLICA = 'no_aplica', 'No aplica'

    class Fuente(models.TextChoices):
        PUBLICA = 'publica', 'Navegación pública'
        INTERNA = 'interna', 'Documento, respuesta o revisión interna'
        AMBAS = 'ambas', 'Evidencia pública e interna'

    auditoria = models.ForeignKey(Auditoria, on_delete=models.CASCADE, related_name='resultados')
    orden = models.PositiveSmallIntegerField()
    articulo = models.CharField('artículo', max_length=100)
    criterio = models.CharField(max_length=160)
    fuente_requerida = models.CharField(max_length=10, choices=Fuente.choices)
    guia = models.CharField(max_length=650)
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.NO_VERIFICABLE)
    fuente = models.CharField('tipo de evidencia', max_length=10, choices=Fuente.choices, blank=True)
    evidencia = models.CharField(max_length=2200, blank=True)
    observacion = models.CharField('observación', max_length=1200, blank=True)
    pendiente = models.CharField('acción pendiente', max_length=650, blank=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('orden',)
        unique_together = ('auditoria', 'orden')
