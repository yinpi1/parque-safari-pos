"""
pos_app/urls.py
Rutas URL para la maqueta navegable del Sistema POS de Parque Safari.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Login, Logout & Dashboard
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Control de Caja & Cuadratura (Protegido por RBAC)
    path('caja/operacion/', views.caja_operacion_view, name='caja_operacion'),
    
    # Flujo de Ventas y Procesamiento Transaccional
    path('pos/', views.pos_view, name='pos'),
    path('pos/procesar-venta/', views.procesar_venta_view, name='procesar_venta'),
    path('ticket/', views.ticket_view, name='ticket'),

    # Módulos de Operación & Catálogo
    path('productos/', views.productos_view, name='productos'),
    path('productos/operacion/', views.producto_operacion_view, name='producto_operacion'),
    path('menus/', views.menus_view, name='menus'),
    path('menus/operacion/', views.menu_operacion_view, name='menu_operacion'),
    path('mesas/', views.mesas_view, name='mesas'),
    path('mesas/operacion/', views.mesa_operacion_view, name='mesa_operacion'),

    # Gestión Interna & Colaboradores
    path('usuarios/', views.usuarios_view, name='usuarios'),
    path('usuarios/operacion/', views.usuario_operacion_view, name='usuario_operacion'),
    path('fiados/', views.fiados_view, name='fiados'),
    path('fiados/operacion/', views.fiado_operacion_view, name='fiado_operacion'),

    # Producción & Despacho (KDS Cocina / BDS Bar)
    path('distribucion/', views.distribucion_view, name='distribucion'),
    path('cocina/', views.cocina_view, name='cocina'),
    path('bar/', views.bar_view, name='bar'),
    path('comandas/estado/', views.actualizar_estado_comanda_view, name='actualizar_estado_comanda'),
    
    # Métricas y Reportes
    path('estadisticas/', views.estadisticas_view, name='estadisticas'),
    path('reportes/', views.reportes_view, name='reportes'),
    
    # Configuración
    path('configuracion/', views.configuracion_view, name='configuracion'),
    path('configuracion/operacion/', views.configuracion_operacion_view, name='configuracion_operacion'),
]
