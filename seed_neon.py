"""
Script de Carga de Semillas (Seeds) para Parque Safari POS en PostgreSQL / Neon.

Modos de ejecución:
1. Modo Catálogo Base / Producción (por defecto, `incluir_datos_demo=False`):
   - Carga únicamente datos estructurales y de catálogo:
     * Cargos y Roles RBAC
     * Usuarios base (preservando hashes de contraseña existentes)
     * Categorías, Productos y Menús/Combos (con mapeo real de ahorro_estimado)
     * Mesas físicas del salón (en estado Disponible, sin consumos ficticios ni sobrescritura de mesas activas)
     * Configuración general del terminal POS
     * Registro único e idempotente de auditoría inicial
   - NO carga ventas ficticias, comandas ficticias, deudas de colaboradores ni sesiones/cierres de caja de prueba.

2. Modo Demostrativo (`python seed_neon.py --demo` o `incluir_datos_demo=True`):
   - Incluye además el estado operativo de demostración (mesas ocupadas con mozos reales asignados,
     cuentas de fiado con mapeo real de cargo_grupo y limite_credito, y sesión de caja inicial abierta).
"""

import os
import re
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parque_safari.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from django.db import transaction
from pos_app.models import (
    Cargo, Usuario, Categoria, Producto, MenuCombo,
    Mesa, SesionCaja, ConfiguracionPOS, FiadoPersonal, LogAuditoria,
    is_password_hashed,
)
from pos_app import mock_data


def _parse_clp_int(value, default=0):
    """
    Convierte un valor monetario chileno (ej. '$24.500', 'Ahorro $2.290', 50000)
    a un entero no negativo en CLP.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    digits = re.sub(r'[^\d]', '', str(value))
    return int(digits) if digits else default


def _parse_bool(value, default=True):
    """Normaliza valores booleanos provenientes de diccionarios de configuración."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    val_str = str(value).strip().lower()
    if val_str in ('false', '0', 'no', 'deshabilitado', 'inactivo', 'off'):
        return False
    return True


def poblar_base_de_datos(incluir_datos_demo=None):
    """
    Puebla la base de datos de forma transaccional e idempotente.

    :param incluir_datos_demo: Si es False (por defecto), solo carga catálogos y estructura base
                               sin inyectar deudas, sesiones de caja ni consumos ficticios.
                               Si es True, carga además los datos operativos de demostración.
    """
    if incluir_datos_demo is None:
        incluir_datos_demo = (
            '--demo' in sys.argv
            or os.environ.get('POS_SEED_DEMO', '').strip().lower() in ('1', 'true', 'yes')
        )

    modo_label = "DEMOSTRATIVO (catálogo + estado operativo demo)" if incluir_datos_demo else "PRODUCCIÓN / CATÁLOGO BASE"
    print(f"[INFO] Iniciando carga de semillas en modo: {modo_label}...")

    with transaction.atomic():
        # 1. CARGOS
        print("-> Sincronizando Cargos...")
        cargos_data = [
            {"id": "cajero", "nombre": "Cajero", "descripcion": "Atención rápida en caja, cobros, boletas y cuadratura", "nivel": "Operativo"},
            {"id": "garzon", "nombre": "Garzón / Mesero", "descripcion": "Toma de pedidos en mesas del salón y derivación", "nivel": "Operativo"},
            {"id": "cocina", "nombre": "Cocina", "descripcion": "Preparación de platos calientes y control KDS", "nivel": "Producción"},
            {"id": "bar", "nombre": "Bar", "descripcion": "Despacho de bebestibles, postres y cafetería BDS", "nivel": "Producción"},
            {"id": "admin", "nombre": "Administrador", "descripcion": "Control total, catálogos, aperturas/cierres y reportes", "nivel": "Gerencial"},
        ]
        for c in cargos_data:
            Cargo.objects.update_or_create(id=c["id"], defaults=c)

        # 2. USUARIOS (preservando contraseñas ya hasheadas en cuentas existentes)
        print("-> Sincronizando Usuarios...")
        cargo_map = {
            "Cajero": "cajero",
            "Administrador": "admin",
            "Vendedor": "garzon",
            "Garzón": "garzon",
            "Cocina": "cocina",
            "Bar": "bar",
        }
        seed_default_password = os.environ.get("POS_SEED_PASSWORD", "Safari2026!")
        for u in mock_data.USUARIOS:
            username = u["usuario"].strip().lower()
            cargo_id = cargo_map.get(u.get("cargo"), "cajero")
            cargo_obj = Cargo.objects.get(id=cargo_id)

            existing_user = Usuario.objects.filter(usuario=username).first()
            if existing_user is not None:
                existing_user.nombre = u["nombre"]
                existing_user.email = u["email"]
                existing_user.cargo = cargo_obj
                if not existing_user.caja_asignada:
                    existing_user.caja_asignada = u.get("caja_asignada", "Sin asignar")
                if not is_password_hashed(existing_user.password):
                    existing_user.password = make_password(seed_default_password)
                existing_user.save()
            else:
                Usuario.objects.create(
                    usuario=username,
                    nombre=u["nombre"],
                    email=u["email"],
                    password=make_password(seed_default_password),
                    cargo=cargo_obj,
                    caja_asignada=u.get("caja_asignada", "Sin asignar"),
                    estado=u.get("estado", "Activo"),
                )

        # 3. CATEGORÍAS
        print("-> Sincronizando Categorías...")
        for cat in mock_data.CATEGORIAS:
            Categoria.objects.update_or_create(
                id=cat["id"],
                defaults={
                    "nombre": cat["nombre"],
                    "icono": cat.get("icono", "bi-grid-fill"),
                    "color": cat.get("color", "primary"),
                    "activo": True,
                }
            )

        # 4. PRODUCTOS
        print("-> Sincronizando Productos...")
        for p in mock_data.PRODUCTOS:
            cat_obj = Categoria.objects.get(id=p["categoria_id"])
            Producto.objects.update_or_create(
                codigo=p["codigo"],
                defaults={
                    "nombre": p["nombre"],
                    "categoria": cat_obj,
                    "precio": int(p["precio"]),
                    "tipo": p.get("tipo", "Producto listo"),
                    "destino": p.get("destino", "Directo"),
                    "estado": p.get("estado", "Activo"),
                    "badge_tipo": p.get("badge_tipo", "badge-listo"),
                    "descripcion": p.get("descripcion", ""),
                    "icono": p.get("icono", "bi-box2-heart"),
                    "imagen_placeholder": p.get("imagen_placeholder"),
                }
            )

        # 5. MENÚS / COMBOS (con mapeo corregido de ahorro -> ahorro_estimado)
        print("-> Sincronizando Menús y Combos...")
        for m in mock_data.MENUS:
            raw_ahorro = m["ahorro_estimado"] if "ahorro_estimado" in m else m.get("ahorro", 0)
            ahorro_int = _parse_clp_int(raw_ahorro, default=0)

            MenuCombo.objects.update_or_create(
                codigo=m["codigo"],
                defaults={
                    "nombre": m["nombre"],
                    "productos_incluidos": m.get("productos_incluidos", ""),
                    "precio": int(m["precio"]),
                    "ahorro_estimado": ahorro_int,
                    "categoria": m.get("categoria", "Combos"),
                    "disponibilidad": m.get("disponibilidad", "Todo el día"),
                    "estado": m.get("estado", "Activo"),
                }
            )

        # 6. MESAS (con asignación real de mozos y separación catálogo vs demo)
        print("-> Sincronizando Mesas...")
        garzon_fallback = Usuario.objects.filter(cargo__id='garzon', estado='Activo').first()
        for mesa in mock_data.MESAS:
            numero_mesa = mesa["numero"]
            zona_mesa = mesa.get("zona", "Salón Principal")
            capacidad_mesa = int(mesa.get("capacidad", 4))

            if incluir_datos_demo:
                estado_mesa = mesa.get("estado", "Disponible")
                consumo_int = _parse_clp_int(mesa.get("consumo_actual", 0), default=0) if estado_mesa == "Ocupada" else 0
                comensales_int = int(mesa.get("comensales", 0)) if estado_mesa == "Ocupada" else 0

                mozo_obj = None
                if estado_mesa == "Ocupada":
                    mozo_nombre = (mesa.get("mozo") or "").strip()
                    if mozo_nombre and mozo_nombre != "-":
                        mozo_obj = (
                            Usuario.objects.filter(nombre__iexact=mozo_nombre, cargo__id='garzon').first()
                            or Usuario.objects.filter(nombre__iexact=mozo_nombre).first()
                        )
                    if mozo_obj is None:
                        mozo_obj = garzon_fallback

                Mesa.objects.update_or_create(
                    numero=numero_mesa,
                    defaults={
                        "zona": zona_mesa,
                        "capacidad": capacidad_mesa,
                        "estado": estado_mesa,
                        "consumo_actual": consumo_int,
                        "mozo_asignado": mozo_obj,
                        "comensales_actuales": comensales_int,
                    }
                )
            else:
                # Modo producción: no inyecta estados ocupados ni consumos ficticios,
                # ni sobrescribe el estado operativo de mesas ya existentes.
                existing_mesa = Mesa.objects.filter(numero=numero_mesa).first()
                if existing_mesa is not None:
                    existing_mesa.zona = zona_mesa
                    existing_mesa.capacidad = capacidad_mesa
                    existing_mesa.save()
                else:
                    Mesa.objects.create(
                        numero=numero_mesa,
                        zona=zona_mesa,
                        capacidad=capacidad_mesa,
                        estado="Disponible",
                        consumo_actual=0,
                        mozo_asignado=None,
                        comensales_actuales=0,
                    )

        # 7. FIADOS PERSONAL (solo en modo demo, con mapeo corregido de cargo_grupo y limite_credito)
        if incluir_datos_demo:
            print("-> Sincronizando Cuentas de Fiado (modo demostrativo)...")
            for f in mock_data.FIADOS:
                raw_limite = f["limite_credito"] if "limite_credito" in f else f.get("limite", 50000)
                limite_int = _parse_clp_int(raw_limite, default=50000)
                acumulado_int = _parse_clp_int(f.get("total_acumulado", 0), default=0)
                cargo_grupo_val = f.get("cargo_grupo") or f.get("cargo") or "Personal Parque"

                FiadoPersonal.objects.update_or_create(
                    rut=f["rut"],
                    defaults={
                        "trabajador": f["trabajador"],
                        "cargo_grupo": cargo_grupo_val,
                        "limite_credito": limite_int,
                        "total_acumulado": acumulado_int,
                        "consumos_mes": int(f.get("consumos_mes", 0)),
                        "estado": f.get("estado", "Al día"),
                    }
                )
        else:
            print("-> Omitiendo deudas demostrativas de FiadoPersonal (modo catálogo base).")

        # 8. CONFIGURACIÓN POS
        print("-> Sincronizando Configuración del Sistema...")
        ConfiguracionPOS.objects.update_or_create(
            id=1,
            defaults={
                "nombre_parque": mock_data.CONFIGURACION.get("nombre_parque", "Parque Safari Rancagua"),
                "razon_social": mock_data.CONFIGURACION.get("razon_social", "Parque Safari Chile S.A."),
                "rut": mock_data.CONFIGURACION.get("rut", "76.123.456-7"),
                "direccion": mock_data.CONFIGURACION.get("direccion", "Ruta Travesía Km 82, Rancagua"),
                "telefono": mock_data.CONFIGURACION.get("telefono", "+56 72 258 3100"),
                "terminal_caja": mock_data.CONFIGURACION.get("terminal_caja", "Terminal POS 01"),
                "impresora_tickets": mock_data.CONFIGURACION.get("impresora_tickets", "Epson TM-T20II (USB)"),
                "impresora_cocina": mock_data.CONFIGURACION.get("impresora_cocina", "Bixolon SRP-330II (Red Local)"),
                "impresora_bar": mock_data.CONFIGURACION.get("impresora_bar", "Epson TM-T20II (Red Local)"),
                "iva_incluido": _parse_bool(mock_data.CONFIGURACION.get("iva_incluido", True), default=True),
                "modo_offline": _parse_bool(mock_data.CONFIGURACION.get("modo_offline", True), default=True),
                "sonido_comandas": _parse_bool(mock_data.CONFIGURACION.get("sonido_comandas", True), default=True),
                "resolucion_optimizada": mock_data.CONFIGURACION.get("resolucion_optimizada", "Touchscreen 15\" (1366x768) / 1080p"),
            }
        )

        # 9. SESIÓN DE CAJA INICIAL ABIERTA (solo en modo demostrativo)
        if incluir_datos_demo:
            cajero_u = Usuario.objects.filter(cargo__id='cajero', estado='Activo').first()
            if cajero_u and not SesionCaja.objects.filter(estado='Abierta').exists():
                SesionCaja.objects.create(
                    cajero=cajero_u,
                    terminal_nombre="Terminal POS 01 - Casona Central",
                    monto_apertura=50000,
                    estado='Abierta',
                    observaciones="Apertura inicial demostrativa con fondo para sencillo de $50.000."
                )

        # 10. AUDITORÍA INICIAL (idempotente: no duplica registros en ejecuciones sucesivas)
        admin_u = Usuario.objects.filter(cargo__id='admin').first()
        if not LogAuditoria.objects.filter(
            modulo='Sistema',
            accion='LOGIN',
            descripcion__startswith='Carga inicial de semillas'
        ).exists():
            LogAuditoria.objects.create(
                usuario=admin_u,
                accion='LOGIN',
                modulo='Sistema',
                descripcion='Carga inicial de semillas y configuración en base de datos PostgreSQL exitosa.'
            )

    print("[EXITO] Carga de semillas completada exitosamente.")


if __name__ == '__main__':
    poblar_base_de_datos()
