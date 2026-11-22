from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .criterios import (
    CRITERIOS, DIARIO_OFICIAL, FECHA_CORTE, LEY_CONSOLIDADA, MARCO, VIGENCIA_DE_REFERENCIA,
)
from .forms import AlcanceForm, AuditoriaForm, ResultadoForm
from .models import Auditoria, Resultado


def rol_de(user):
    if user.is_superuser:
        return 'Administrador'
    if user.groups.filter(name='Usuario').exists():
        return 'Usuario'
    raise PermissionDenied


def auditoria_visible(user, pk):
    auditorias = Auditoria.objects.all()
    if rol_de(user) == 'Usuario':
        auditorias = auditorias.filter(propietario=user)
    return get_object_or_404(auditorias, pk=pk)


def auditoria_propia(user, pk):
    rol_de(user)
    return get_object_or_404(Auditoria, pk=pk, propietario=user)


@never_cache
@login_required
def listar(request):
    rol = rol_de(request.user)
    auditorias = Auditoria.objects.all()
    if rol == 'Usuario':
        auditorias = auditorias.filter(propietario=request.user)
    return render(request, 'productos/listar.html', {'auditorias': auditorias, 'rol': rol})


@never_cache
@login_required
def crear(request):
    rol_de(request.user)
    form = AuditoriaForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        auditoria = form.save(commit=False)
        auditoria.propietario = request.user
        auditoria.marco = MARCO
        with transaction.atomic():
            auditoria.save()
            Resultado.objects.bulk_create([
                Resultado(
                    auditoria=auditoria, orden=orden, articulo=articulo,
                    criterio=criterio, fuente_requerida=fuente, guia=guia,
                )
                for orden, (articulo, criterio, fuente, guia) in enumerate(CRITERIOS, start=1)
            ])
        return redirect('detalle', pk=auditoria.pk)

    return render(request, 'productos/formulario.html', {
        'form': form, 'titulo': 'Nueva auditoría',
    })


@never_cache
@login_required
def detalle(request, pk):
    auditoria = auditoria_visible(request.user, pk)
    resultados = list(auditoria.resultados.all())
    totales = [
        (estado.label, sum(resultado.estado == estado for resultado in resultados))
        for estado in Resultado.Estado
    ]
    return render(request, 'productos/detalle.html', {
        'auditoria': auditoria, 'resultados': resultados, 'totales': totales,
        'editable': auditoria.propietario_id == request.user.pk,
    })


@never_cache
@login_required
def editar(request, pk):
    auditoria = auditoria_propia(request.user, pk)
    form = AlcanceForm(request.POST if request.method == 'POST' else None, instance=auditoria)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('detalle', pk=auditoria.pk)

    return render(request, 'productos/formulario.html', {
        'form': form, 'titulo': 'Editar alcance', 'auditoria': auditoria,
    })


@never_cache
@login_required
def editar_resultado(request, pk, resultado_pk):
    auditoria = auditoria_propia(request.user, pk)
    resultado = get_object_or_404(auditoria.resultados, pk=resultado_pk)
    form = ResultadoForm(request.POST if request.method == 'POST' else None, instance=resultado)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('detalle', pk=auditoria.pk)

    return render(request, 'productos/formulario.html', {
        'form': form, 'titulo': resultado.criterio, 'auditoria': auditoria, 'resultado': resultado,
    })


@never_cache
@login_required
def eliminar(request, pk):
    auditoria = auditoria_propia(request.user, pk)
    if request.method == 'POST':
        auditoria.delete()
        return redirect('listar')

    return render(request, 'productos/eliminar.html', {'auditoria': auditoria})


@never_cache
@login_required
def reporte(request, pk):
    auditoria = auditoria_visible(request.user, pk)
    return render(request, 'productos/reporte.html', {
        'auditoria': auditoria, 'resultados': auditoria.resultados.all(),
        'ley_consolidada': LEY_CONSOLIDADA, 'diario_oficial': DIARIO_OFICIAL,
        'preparacion': timezone.localdate(auditoria.creada) < VIGENCIA_DE_REFERENCIA,
    })


def privacidad(request):
    return render(request, 'productos/privacidad.html', {
        'responsable': settings.PRIVACIDAD_RESPONSABLE,
        'contacto': settings.PRIVACIDAD_CONTACTO,
        'fecha_corte': FECHA_CORTE,
    })
