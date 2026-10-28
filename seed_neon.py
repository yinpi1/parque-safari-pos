"""
Script de Carga de Semillas (Seeds) para Parque Safari POS en Neon PostgreSQL.
Puebla:
- Cargos y Roles de acceso
- Usuarios demostrativos con distintos perfiles y permisos
- Categorías y Productos
- Menús y Combos
- Mesas del Salón
- Configuración General
- Fiados y Saldos de colaboradores
- Sesión de Caja activa inicial
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parque_safari.settings')
django.setup()

from pos_app.models import (
    Cargo, Usuario, Categoria, Producto, MenuCombo,
    Mesa, SesionCaja, ConfiguracionPOS, FiadoPersonal, FiadoMovimiento, LogAuditoria
)
from pos_app import mock_data

def poblar_base_de_datos():
    print("[INFO] Iniciando carga de semillas (Seeds) en Neon PostgreSQL...")

    # 1. CARGOS
    print("-> Cargando Cargos...")
    cargos_data = [
        {"id": "cajero", "nombre": "Cajero", "descripcion": "Atención rápida en caja, cobros, boletas y cuadratura", "nivel": "Operativo"},
        {"id": "garzon", "nombre": "Garzón / Mesero", "descripcion": "Toma de pedidos en mesas del salón y derivación", "nivel": "Operativo"},
        {"id": "cocina", "nombre": "Cocina", "descripcion": "Preparación de platos calientes y control KDS", "nivel": "Producción"},
        {"id": "bar", "nombre": "Bar", "descripcion": "Despacho de bebestibles, postres y cafetería BDS", "nivel": "Producción"},
        {"id": "admin", "nombre": "Administrador", "descripcion": "Control total, catálogos, aperturas/cierres y reportes", "nivel": "Gerencial"},
    ]
    for c in cargos_data:
        Cargo.objects.update_or_create(id=c["id"], defaults=c)

    # 2. USUARIOS
    print("-> Cargando Usuarios demostrativos...")
    cargo_map = {
        "Cajero": "cajero",
        "Administrador": "admin",
        "Vendedor": "garzon",
        "Cocina": "cocina",
        "Bar": "bar"
    }
    for u in mock_data.USUARIOS:
        cargo_id = cargo_map.get(u.get("cargo"), "cajero")
        cargo_obj = Cargo.objects.get(id=cargo_id)
        Usuario.objects.update_or_create(
            usuario=u["usuario"],
            defaults={
                "nombre": u["nombre"],
                "email": u["email"],
                "password": "123",  # Clave demostrativa simple para pruebas
                "cargo": cargo_obj,
                "caja_asignada": u.get("caja_asignada", "Sin asignar"),
                "estado": u.get("estado", "Activo"),
            }
        )

    # 3. CATEGORÍAS
    print("-> Cargando Categorías...")
    for cat in mock_data.CATEGORIAS:
        Categoria.objects.update_or_create(
            id=cat["id"],
            defaults={
                "nombre": cat["nombre"],
                "icono": cat.get("icono", "bi-grid-fill"),
                "color": cat.get("color", "primary"),
                "activo": True
            }
        )

    # 4. PRODUCTOS
    print("-> Cargando Productos...")
    for p in mock_data.PRODUCTOS:
        cat_obj = Categoria.objects.get(id=p["categoria_id"])
        Producto.objects.update_or_create(
            codigo=p["codigo"],
            defaults={
                "nombre": p["nombre"],
                "categoria": cat_obj,
                "precio": p["precio"],
                "tipo": p.get("tipo", "Producto listo"),
                "destino": p.get("destino", "Directo"),
                "estado": p.get("estado", "Activo"),
                "badge_tipo": p.get("badge_tipo", "badge-listo"),
                "descripcion": p.get("descripcion", ""),
                "icono": p.get("icono", "bi-box2-heart"),
            }
        )

    # 5. MENÚS / COMBOS
    print("-> Cargando Menús y Combos...")
    for m in mock_data.MENUS:
        MenuCombo.objects.update_or_create(
            codigo=m["codigo"],
            defaults={
                "nombre": m["nombre"],
                "productos_incluidos": m.get("productos_incluidos", ""),
                "precio": m["precio"],
                "ahorro_estimado": m.get("ahorro_estimado", 0),
                "categoria": m.get("categoria", "Combos"),
                "disponibilidad": m.get("disponibilidad", "Todo el día"),
                "estado": m.get("estado", "Activo"),
            }
        )

    # 6. MESAS
    print("-> Cargando Mesas...")
    cajero_u = Usuario.objects.filter(cargo__id='cajero').first()
    for mesa in mock_data.MESAS:
        raw_consumo = str(mesa.get("consumo_actual", "0")).replace('$', '').replace('.', '').strip()
        consumo_int = int(raw_consumo) if raw_consumo.isdigit() else 0

        Mesa.objects.update_or_create(
            numero=mesa["numero"],
            defaults={
                "zona": mesa.get("zona", "Salón Principal"),
                "capacidad": mesa.get("capacidad", 4),
                "estado": mesa.get("estado", "Disponible"),
                "consumo_actual": consumo_int,
                "mozo_asignado": cajero_u if mesa.get("estado") == "Ocupada" else None,
                "comensales_actuales": mesa.get("comensales", 0) if mesa.get("estado") == "Ocupada" else 0,
            }
        )

    # 7. FIADOS PERSONAL
    print("-> Cargando Fiados...")
    for f in mock_data.FIADOS:
        raw_limite = str(f.get("limite", "50000")).replace('$', '').replace('.', '').strip()
        limite_int = int(raw_limite) if raw_limite.isdigit() else 50000

        raw_acumulado = str(f.get("total_acumulado", "0")).replace('$', '').replace('.', '').strip()
        acumulado_int = int(raw_acumulado) if raw_acumulado.isdigit() else 0

        FiadoPersonal.objects.update_or_create(
            rut=f["rut"],
            defaults={
                "trabajador": f["trabajador"],
                "cargo_grupo": f.get("cargo", "Personal Parque"),
                "limite_credito": limite_int,
                "total_acumulado": acumulado_int,
                "consumos_mes": f.get("consumos_mes", 0),
                "estado": f.get("estado", "Al día"),
            }
        )

    # 8. CONFIGURACIÓN POS
    print("-> Cargando Configuración del Sistema...")
    ConfiguracionPOS.objects.get_or_create(
        id=1,
        defaults={
            "nombre_parque": mock_data.CONFIGURACION.get("nombre_parque", "Parque Safari Rancagua"),
            "razon_social": mock_data.CONFIGURACION.get("razon_social", "Parque Safari Chile S.A."),
            "rut": mock_data.CONFIGURACION.get("rut", "76.123.456-7"),
            "direccion": mock_data.CONFIGURACION.get("direccion", "Ruta Travesía Km 82, Rancagua"),
            "telefono": mock_data.CONFIGURACION.get("telefono", "+56 72 258 3100"),
            "terminal_caja": mock_data.CONFIGURACION.get("terminal_caja", "Terminal POS 01"),
        }
    )

    # 9. SESIÓN DE CAJA INICIAL ABIERTA
    if not SesionCaja.objects.filter(estado='Abierta').exists():
        SesionCaja.objects.create(
            cajero=cajero_u,
            terminal_nombre="Terminal POS 01 - Casona Central",
            monto_apertura=50000,
            estado='Abierta',
            observaciones="Apertura inicial demostrativa con fondo para sencillo de $50.000."
        )

    # 10. AUDITORÍA INICIAL
    LogAuditoria.objects.create(
        usuario=Usuario.objects.filter(cargo__id='admin').first(),
        accion='LOGIN',
        modulo='Sistema',
        descripcion='Carga inicial de semillas y configuración en base de datos Neon PostgreSQL exitosa.'
    )

    print("[EXITO] Carga de semillas completada exitosamente en Neon PostgreSQL!")

if __name__ == '__main__':
    poblar_base_de_datos()
