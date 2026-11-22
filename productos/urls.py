from django.urls import path

from . import views

urlpatterns = [
    path('', views.listar, name='listar'),
    path('registro/', views.registrarse, name='registro'),
    path('crear/', views.crear, name='crear'),
    path('auditoria/<int:pk>/', views.detalle, name='detalle'),
    path('editar/<int:pk>/', views.editar, name='editar'),
    path('eliminar/<int:pk>/', views.eliminar, name='eliminar'),
    path('auditoria/<int:pk>/criterio/<int:resultado_pk>/', views.editar_resultado, name='editar_resultado'),
    path('auditoria/<int:pk>/reporte/', views.reporte, name='reporte'),
    path('privacidad/', views.privacidad, name='privacidad'),
]
