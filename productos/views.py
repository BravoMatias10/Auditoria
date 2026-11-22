from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .criterios import (
    CRITERIOS, DIARIO_OFICIAL, FECHA_CORTE, LEY_CONSOLIDADA, MARCO, VIGENCIA_DE_REFERENCIA,
)
from .forms import AlcanceForm, AuditoriaForm, ResultadoForm
from .models import Auditoria, Resultado
from .revision_publica import revisar_sitio


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
def registrarse(request):
    if request.user.is_authenticated:
        return redirect('listar')

    form = UserCreationForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                cuenta = form.save()
                grupo, _ = Group.objects.get_or_create(name='Usuario')
                cuenta.groups.add(grupo)
        except IntegrityError:
            if not get_user_model().objects.filter(username=form.cleaned_data['username']).exists():
                raise
            form.add_error('username', 'Ese nombre de usuario ya está en uso.')
        else:
            return redirect('login')

    return render(request, 'productos/formulario.html', {
        'form': form, 'titulo': 'Crear cuenta', 'registro': True,
    })


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
        revision = revisar_sitio(auditoria.url)
        auditoria.resumen_revision = revision.resumen
        if not auditoria.alcance:
            auditoria.alcance = 'Consulta de la URL indicada y de sus enlaces públicos de privacidad.'
        with transaction.atomic():
            auditoria.save()
            Resultado.objects.bulk_create([
                Resultado(
                    auditoria=auditoria, orden=orden, articulo=articulo,
                    criterio=criterio, fuente_requerida=fuente, guia=guia,
                    **revision.hallazgos.get(criterio, {}),
                )
                for orden, (articulo, criterio, fuente, guia) in enumerate(CRITERIOS, start=1)
            ])
        return redirect('detalle', pk=auditoria.pk)

    return render(request, 'productos/formulario.html', {
        'form': form, 'titulo': 'Audita un sitio web', 'auditoria_nueva': True,
    })


def contexto_resultados(auditoria):
    resultados = sorted(auditoria.resultados.all(), key=lambda resultado: not resultado.evidencia)
    conteo = {
        estado: sum(resultado.estado == estado for resultado in resultados)
        for estado in Resultado.Estado
    }
    if conteo[Resultado.Estado.NO_CUMPLE]:
        conclusion = 'Se encontraron puntos que requieren corrección.'
    elif conteo[Resultado.Estado.NO_VERIFICABLE]:
        conclusion = 'Hay puntos pendientes. La revisión no permite confirmar el cumplimiento general.'
    else:
        conclusion = 'Los puntos aplicables fueron verificados dentro del alcance de la revisión.'
    return {
        'resultados': resultados,
        'totales': [(estado.label, total) for estado, total in conteo.items()],
        'conclusion': conclusion,
    }


@never_cache
@login_required
def detalle(request, pk):
    auditoria = auditoria_visible(request.user, pk)
    return render(request, 'productos/detalle.html', {
        'auditoria': auditoria, **contexto_resultados(auditoria),
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
        'auditoria': auditoria, **contexto_resultados(auditoria),
        'ley_consolidada': LEY_CONSOLIDADA, 'diario_oficial': DIARIO_OFICIAL,
        'preparacion': timezone.localdate(auditoria.creada) < VIGENCIA_DE_REFERENCIA,
    })


def privacidad(request):
    return render(request, 'productos/privacidad.html', {
        'responsable': settings.PRIVACIDAD_RESPONSABLE,
        'contacto': settings.PRIVACIDAD_CONTACTO,
        'fecha_corte': FECHA_CORTE,
        'cookie_sesion': settings.SESSION_COOKIE_NAME,
        'dias_sesion': settings.SESSION_COOKIE_AGE // 86400,
        'cookie_csrf': settings.CSRF_COOKIE_NAME,
        'dias_csrf': settings.CSRF_COOKIE_AGE // 86400,
    })
