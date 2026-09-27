"""
pos_app/views.py
Vistas del Sistema POS de Parque Safari.

Todas las vistas suministran los datos a las plantillas a través del contexto de Django,
manteniendo los datos desacoplados de los archivos HTML (Regla de diseño #25).
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse
from datetime import datetime
from . import mock_data

def login_view(request):
    """Pantalla de inicio de sesión de Parque Safari."""
    if request.method == "POST":
        return redirect("dashboard")
    context = {
        "titulo": "Iniciar Sesión | Parque Safari POS",
        "parque": mock_data.CONFIGURACION["nombre_parque"],
    }
    return render(request, "login.html", context)

def dashboard_view(request):
    """Panel principal / Dashboard demostrativo con indicadores clave."""
    context = {
        "titulo": "Panel Principal | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],  # Jean Valenzuela
        "estadisticas": mock_data.ESTADISTICAS,
        "mesas": mock_data.MESAS,
        "config": mock_data.CONFIGURACION,
        "fecha_actual": datetime.now().strftime("%d de %B de %Y"),
        "pedidos_cocina_activos": len([p for p in mock_data.COCINA_PEDIDOS if p["estado"] != "Preparado"]),
        "pedidos_bar_activos": len([p for p in mock_data.BAR_PEDIDOS if p["estado"] != "Entregado"]),
        "total_mesas_ocupadas": len([m for m in mock_data.MESAS if m["estado"] == "Ocupada"]),
        "total_mesas": len(mock_data.MESAS),
    }
    return render(request, "dashboard.html", context)

def pos_view(request):
    """Interfaz principal del Punto de Venta (POS) táctil."""
    context = {
        "titulo": "Punto de Venta | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "categorias": mock_data.CATEGORIAS,
        "productos": mock_data.PRODUCTOS,
        "menus": mock_data.MENUS,
        "mesas": mock_data.MESAS,
        "config": mock_data.CONFIGURACION,
    }
    return render(request, "pos.html", context)

def ticket_view(request):
    """Maqueta visual de tickets y comandas (Venta, Cocina, Bar)."""
    # Venta simulada por defecto para demostración
    venta_ejemplo = mock_data.DISTRIBUCION_VENTAS[0]
    context = {
        "titulo": "Ticket y Comandas | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "venta": venta_ejemplo,
        "config": mock_data.CONFIGURACION,
        "fecha_actual": datetime.now().strftime("%d/%m/%Y"),
        "hora_actual": datetime.now().strftime("%H:%M:%S"),
    }
    return render(request, "ticket.html", context)

def productos_view(request):
    """Módulo de gestión y catálogo de productos."""
    context = {
        "titulo": "Catálogo de Productos | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "productos": mock_data.PRODUCTOS,
        "categorias": mock_data.CATEGORIAS,
        "total_productos": len(mock_data.PRODUCTOS),
        "total_activos": len([p for p in mock_data.PRODUCTOS if p["estado"] == "Activo"]),
        "total_cocina": len([p for p in mock_data.PRODUCTOS if p["destino"] == "Cocina"]),
        "total_bar": len([p for p in mock_data.PRODUCTOS if p["destino"] == "Bar"]),
        "total_listos": len([p for p in mock_data.PRODUCTOS if p["destino"] == "Directo"]),
    }
    return render(request, "productos.html", context)

def menus_view(request):
    """Módulo de Menús y Combos promocionales."""
    context = {
        "titulo": "Gestión de Menús y Combos | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "menus": mock_data.MENUS,
        "total_menus": len(mock_data.MENUS),
        "total_activos": len([m for m in mock_data.MENUS if m["estado"] == "Activo"]),
    }
    return render(request, "menus.html", context)

def mesas_view(request):
    """Módulo visual de mapa y gestión de mesas."""
    ocupadas = [m for m in mock_data.MESAS if m["estado"] == "Ocupada"]
    disponibles = [m for m in mock_data.MESAS if m["estado"] == "Disponible"]
    context = {
        "titulo": "Mapa de Mesas | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "mesas": mock_data.MESAS,
        "total_mesas": len(mock_data.MESAS),
        "mesas_ocupadas": len(ocupadas),
        "mesas_disponibles": len(disponibles),
        "total_comensales": sum([m["comensales"] for m in ocupadas]),
    }
    return render(request, "mesas.html", context)

def usuarios_view(request):
    """Módulo de gestión de usuarios y cargos."""
    context = {
        "titulo": "Usuarios y Cargos | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "usuarios": mock_data.USUARIOS,
        "cargos": mock_data.CARGOS,
        "total_usuarios": len(mock_data.USUARIOS),
        "usuarios_activos": len([u for u in mock_data.USUARIOS if u["estado"] == "Activo"]),
        "total_cargos": len(mock_data.CARGOS),
    }
    return render(request, "usuarios.html", context)

def fiados_view(request):
    """Módulo de fiados / consumos internos de colaboradores."""
    deuda_total = sum([f["total_acumulado"] for f in mock_data.FIADOS])
    context = {
        "titulo": "Consumos Fiados de Colaboradores | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "fiados": mock_data.FIADOS,
        "deuda_total": f"${deuda_total:,.0f}".replace(",", "."),
        "total_colaboradores": len(mock_data.FIADOS),
        "consumos_pendientes": sum([f["consumos_mes"] for f in mock_data.FIADOS]),
    }
    return render(request, "fiados.html", context)

def distribucion_view(request):
    """Módulo de visualización de enrutamiento y distribución de ventas a Cocina y Bar."""
    context = {
        "titulo": "Distribución de Ventas | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "distribucion": mock_data.DISTRIBUCION_VENTAS,
        "cocina_pedidos": mock_data.COCINA_PEDIDOS,
        "bar_pedidos": mock_data.BAR_PEDIDOS,
    }
    return render(request, "distribucion.html", context)

def cocina_view(request):
    """Módulo KDS de Cocina: comandas y preparación."""
    pendientes = [p for p in mock_data.COCINA_PEDIDOS if p["estado"] == "Pendiente"]
    en_prep = [p for p in mock_data.COCINA_PEDIDOS if p["estado"] == "En preparación"]
    listos = [p for p in mock_data.COCINA_PEDIDOS if p["estado"] == "Preparado"]
    context = {
        "titulo": "Cocina KDS | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[4],  # Matías Torres (Cocina)
        "pedidos": mock_data.COCINA_PEDIDOS,
        "total_pendientes": len(pendientes),
        "total_en_prep": len(en_prep),
        "total_preparados": len(listos),
        "tiempo_promedio": mock_data.ESTADISTICAS["tiempo_prom_cocina"],
    }
    return render(request, "cocina.html", context)

def bar_view(request):
    """Módulo BDS de Bar: comandas de líquidos y barra."""
    pendientes = [p for p in mock_data.BAR_PEDIDOS if p["estado"] == "Pendiente"]
    en_prep = [p for p in mock_data.BAR_PEDIDOS if p["estado"] == "En preparación"]
    listos = [p for p in mock_data.BAR_PEDIDOS if p["estado"] == "Listo"]
    context = {
        "titulo": "Bar BDS | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[5],  # Patricia Gómez (Bar)
        "pedidos": mock_data.BAR_PEDIDOS,
        "total_pendientes": len(pendientes),
        "total_en_prep": len(en_prep),
        "total_listos": len(listos),
        "tiempo_promedio": mock_data.ESTADISTICAS["tiempo_prom_bar"],
    }
    return render(request, "bar.html", context)

def estadisticas_view(request):
    """Módulo de Estadísticas y gráficos visuales."""
    context = {
        "titulo": "Estadísticas de Operación | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "stats": mock_data.ESTADISTICAS,
    }
    return render(request, "estadisticas.html", context)

def reportes_view(request):
    """Módulo de Reportes con filtros de fecha y exportaciones simuladas."""
    context = {
        "titulo": "Centro de Reportes | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[0],
        "stats": mock_data.ESTADISTICAS,
        "ventas_recientes": mock_data.DISTRIBUCION_VENTAS,
        "fiados": mock_data.FIADOS,
    }
    return render(request, "reportes.html", context)

def configuracion_view(request):
    """Módulo de Configuración general del sistema POS."""
    context = {
        "titulo": "Configuración del Sistema | Parque Safari",
        "usuario_actual": mock_data.USUARIOS[1],  # Carlos Mendoza (Admin)
        "config": mock_data.CONFIGURACION,
    }
    return render(request, "configuracion.html", context)
