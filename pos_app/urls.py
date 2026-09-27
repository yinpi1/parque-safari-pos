"""
pos_app/urls.py
Rutas URL para la maqueta navegable del Sistema POS de Parque Safari.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Login & Dashboard
    path('', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Flujo de Ventas
    path('pos/', views.pos_view, name='pos'),
    path('ticket/', views.ticket_view, name='ticket'),
    
    # Módulos de Operación & Catálogo
    path('productos/', views.productos_view, name='productos'),
    path('menus/', views.menus_view, name='menus'),
    path('mesas/', views.mesas_view, name='mesas'),
    
    # Gestión Interna & Colaboradores
    path('usuarios/', views.usuarios_view, name='usuarios'),
    path('fiados/', views.fiados_view, name='fiados'),
    
    # Producción & Despacho
    path('distribucion/', views.distribucion_view, name='distribucion'),
    path('cocina/', views.cocina_view, name='cocina'),
    path('bar/', views.bar_view, name='bar'),
    
    # Métricas y Reportes
    path('estadisticas/', views.estadisticas_view, name='estadisticas'),
    path('reportes/', views.reportes_view, name='reportes'),
    
    # Configuración
    path('configuracion/', views.configuracion_view, name='configuracion'),
]
