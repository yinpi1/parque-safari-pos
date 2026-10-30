"""
pos_app/services.py
Capa de servicios transaccionales y de dominio para el flujo comercial de Parque Safari POS (Fase 03).

Responsabilidades:
- Cálculo exacto en pesos chilenos (CLP) de Subtotal Neto, IVA (19%) y Total Bruto.
- Descomposición determinista de Menús/Combos en componentes de Cocina (KDS), Bar (BDS) y Entrega Inmediata
  respetando el catálogo real sin duplicar precios ni cantidades.
- Procesamiento atómico de ventas con bloqueo de filas (`select_for_update`) e idempotencia en servidor.
- Máquina de estados coherente para Comandas de Cocina (`Pendiente -> En preparación -> Preparado -> Entregado`)
  y de Bar (`Pendiente -> En preparación -> Listo -> Entregado`) sincronizada con `DetalleVenta`.
- Operaciones transaccionales de salón (ocupación, reasignación y cobro/liberación de mesas).
"""

from datetime import datetime, time, timedelta
import json
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, F, ProtectedError, Q, Sum
from django.utils import timezone

from .models import (
    Cargo,
    Categoria,
    ComandaProduccion,
    ConfiguracionPOS,
    CuadraturaCaja,
    DetalleVenta,
    FiadoMovimiento,
    FiadoPersonal,
    LogAuditoria,
    MenuCombo,
    Mesa,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
    is_password_hashed,
)


class PosDomainError(Exception):
    """Excepción controlada de regla de negocio o validación del POS."""

    def __init__(self, message: str, status_code: int = 400, code: str = "pos_error"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


# Mapa canónico de componentes de los menús del catálogo hacia códigos de Producto y cantidades base.
# Si un menú personalizado no está en este mapa, se analiza dinámicamente su campo `productos_incluidos`
# contra el catálogo activo en PostgreSQL.
CANONICAL_MENU_COMPONENTS = {
    "MENU-SAF-01": [
        {"codigo": "COM-001", "nombre_fallback": "Hamburguesa Safari Especial", "cantidad": 1, "destino_fallback": "COCINA"},
        {"codigo": "COM-004", "nombre_fallback": "Papas Fritas Rústicas Safari", "cantidad": 1, "destino_fallback": "COCINA"},
        {"codigo": "BEB-003", "nombre_fallback": "Bebida Coca-Cola Original 500ml", "cantidad": 1, "destino_fallback": "ENTREGA INMEDIATA"},
    ],
    "MENU-SAF-02": [
        {"codigo": "COM-002", "nombre_fallback": "Churrasco León Italiano", "cantidad": 1, "destino_fallback": "COCINA"},
        {"codigo": "BEB-001", "nombre_fallback": "Jugo Natural Guayaba-Mango 500ml", "cantidad": 1, "destino_fallback": "BAR"},
        {"codigo": "HEL-002", "nombre_fallback": "Copa Sundae León Chocolate Aventura", "cantidad": 1, "destino_fallback": "BAR"},
    ],
    "MENU-SAF-03": [
        {"codigo": "COM-003", "nombre_fallback": "Completo Safari Gigante", "cantidad": 1, "destino_fallback": "COCINA"},
        {"codigo": "HEL-001", "nombre_fallback": "Helado Paleta Selva Artesanal", "cantidad": 1, "destino_fallback": "ENTREGA INMEDIATA"},
    ],
    "MENU-SAF-04": [
        {"codigo": "SNA-001", "nombre_fallback": "Nachos con Queso Cheddar & Guacamole", "cantidad": 1, "destino_fallback": "COCINA"},
        {"codigo": "BEB-002", "nombre_fallback": "Cerveza Artesanal Safari Golden Schop 500cc", "cantidad": 2, "destino_fallback": "BAR"},
    ],
}


def format_clp(amount: int) -> str:
    """Formatea un entero en pesos chilenos con separador de miles '.' (ej. $14.690)."""
    val = int(amount or 0)
    sign = "-" if val < 0 else ""
    return f"{sign}${abs(val):,}".replace(",", ".")


def map_producto_destino_to_produccion(destino_producto: str) -> str:
    """Convierte el destino de catálogo ('Cocina', 'Bar', 'Directo') al destino de producción."""
    d = (destino_producto or "").strip().lower()
    if d == "cocina":
        return "COCINA"
    if d == "bar":
        return "BAR"
    return "ENTREGA INMEDIATA"


def calcular_totales_clp(total_bruto_o_base: int, iva_incluido: bool = True, iva_porcentaje: Decimal = Decimal("19.00")) -> dict:
    """
    Calcula en pesos chilenos enteros (CLP) el Subtotal Neto, el IVA y el Total.
    Garantiza la invariante contable exacta: subtotal + iva == total.
    """
    monto = int(total_bruto_o_base or 0)
    if monto <= 0:
        return {"subtotal": 0, "iva": 0, "total": 0}

    tasa = float(iva_porcentaje) / 100.0
    if tasa <= 0:
        return {"subtotal": monto, "iva": 0, "total": monto}

    if iva_incluido:
        total = monto
        subtotal = int(round(total / (1.0 + tasa)))
        iva = total - subtotal
    else:
        subtotal = monto
        iva = int(round(subtotal * tasa))
        total = subtotal + iva

    return {
        "subtotal": subtotal,
        "iva": iva,
        "total": total,
    }


def descomponer_menu_combo(menu_obj: MenuCombo, cantidad_combo: int = 1) -> list:
    """
    Descompone un `MenuCombo` en sus componentes operativos para Cocina (KDS),
    Bar (BDS) y Entrega Inmediata, consultando el catálogo real en PostgreSQL
    sin duplicar cantidades ni precios.
    """
    qty_combo = max(1, int(cantidad_combo or 1))
    componentes_resultado = []

    if menu_obj.codigo in CANONICAL_MENU_COMPONENTS:
        spec_list = CANONICAL_MENU_COMPONENTS[menu_obj.codigo]
        codigos = [s["codigo"] for s in spec_list]
        productos_db = {
            p.codigo: p for p in Producto.objects.filter(codigo__in=codigos)
        }
        for spec in spec_list:
            prod = productos_db.get(spec["codigo"])
            if prod is not None:
                destino_prod = map_producto_destino_to_produccion(prod.destino)
                nombre_comp = prod.nombre
            else:
                destino_prod = spec["destino_fallback"]
                nombre_comp = spec["nombre_fallback"]

            componentes_resultado.append(
                {
                    "nombre": nombre_comp,
                    "cantidad": spec["cantidad"] * qty_combo,
                    "destino": destino_prod,
                    "combo_codigo": menu_obj.codigo,
                    "combo_nombre": menu_obj.nombre,
                }
            )
        return componentes_resultado

    # Descomposición dinámica para menús personalizados creados en base de datos
    partes = [p.strip() for p in re.split(r"\+|,", menu_obj.productos_incluidos or "") if p.strip()]
    catalogo = list(Producto.objects.all())

    for parte in partes:
        factor = 1
        texto_item = parte
        m_qty = re.match(r"^(\d+)\s*[xX]?\s+(.+)$", parte)
        if m_qty:
            factor = max(1, int(m_qty.group(1)))
            texto_item = m_qty.group(2).strip()

        matched_prod = None
        texto_lower = texto_item.lower()
        for prod in catalogo:
            prod_lower = prod.nombre.lower()
            if texto_lower in prod_lower or prod_lower in texto_lower:
                matched_prod = prod
                break
            # Coincidencia por palabras significativas (>= 4 letras)
            palabras = [w for w in re.split(r"\s+", texto_lower) if len(w) >= 4]
            if palabras and all(w in prod_lower for w in palabras[:2]):
                matched_prod = prod
                break

        if matched_prod is not None:
            destino_prod = map_producto_destino_to_produccion(matched_prod.destino)
            nombre_comp = matched_prod.nombre
        else:
            # Inferencia segura por palabras clave de estación
            if any(k in texto_lower for k in ("jugo", "cerveza", "schop", "café", "cafe", "sundae", "copa", "bar")):
                destino_prod = "BAR"
            elif any(k in texto_lower for k in ("bebida", "lata", "botella", "paleta", "juguete", "agua")):
                destino_prod = "ENTREGA INMEDIATA"
            else:
                destino_prod = "COCINA"
            nombre_comp = texto_item

        componentes_resultado.append(
            {
                "nombre": nombre_comp,
                "cantidad": factor * qty_combo,
                "destino": destino_prod,
                "combo_codigo": menu_obj.codigo,
                "combo_nombre": menu_obj.nombre,
            }
        )

    if not componentes_resultado:
        componentes_resultado.append(
            {
                "nombre": menu_obj.nombre,
                "cantidad": qty_combo,
                "destino": "COCINA",
                "combo_codigo": menu_obj.codigo,
                "combo_nombre": menu_obj.nombre,
            }
        )

    return componentes_resultado


def obtener_destinos_resumen_menu(menu_obj: MenuCombo) -> dict:
    """
    Determina qué estaciones intervienen en un MenuCombo para mostrarlo en la tarjeta del POS.
    """
    comps = descomponer_menu_combo(menu_obj, cantidad_combo=1)
    tiene_cocina = any(c["destino"] == "COCINA" for c in comps)
    tiene_bar = any(c["destino"] == "BAR" for c in comps)
    if tiene_cocina and tiene_bar:
        return {"destino": "Cocina + Bar", "badge_tipo": "badge-cocina", "tipo": "Combo Mixto (Cocina y Bar)"}
    if tiene_cocina:
        return {"destino": "Cocina", "badge_tipo": "badge-cocina", "tipo": "Combo Cocina"}
    if tiene_bar:
        return {"destino": "Bar", "badge_tipo": "badge-bar", "tipo": "Combo Bar"}
    return {"destino": "Directo", "badge_tipo": "badge-listo", "tipo": "Combo Directo"}


def _generar_siguiente_venta_num() -> str:
    """Genera un número de folio correlativo de 5 dígitos (ej. '00144') único en Venta."""
    numeros_existentes = []
    for raw_num in Venta.objects.values_list("venta_num", flat=True):
        digits = re.sub(r"[^\d]", "", str(raw_num or ""))
        if digits.isdigit():
            numeros_existentes.append(int(digits))

    base_num = max(numeros_existentes, default=143) + 1
    while True:
        candidato = f"{base_num:05d}"
        if not Venta.objects.filter(venta_num__in=[candidato, f"#{candidato}"]).exists():
            return candidato
        base_num += 1


def serializar_venta_completa(venta: Venta, config: ConfiguracionPOS = None) -> dict:
    """
    Construye la representación estructurada y verificada de una Venta persistida,
    incluyendo sus líneas de ticket y las comandas de Cocina y Bar asociadas.
    """
    if config is None:
        config = ConfiguracionPOS.objects.first()

    fecha_local = timezone.localtime(venta.fecha_hora) if timezone.is_aware(venta.fecha_hora) else venta.fecha_hora
    fecha_str = fecha_local.strftime("%d/%m/%Y")
    hora_str = fecha_local.strftime("%H:%M")
    hora_completa_str = fecha_local.strftime("%H:%M:%S")

    detalles = list(venta.detalles.select_related("producto", "menu").all())
    comandas_map = {c.area_destino: c for c in venta.comandas.all()}

    items_ticket = []
    items_distribucion = []
    cocina_items = []
    bar_items = []

    nota_general = (venta.notas or "").strip()

    for det in detalles:
        items_ticket.append(
            {
                "id": det.id,
                "tipo": "menu" if det.menu_id else "producto",
                "nombre": det.nombre_item,
                "cant": det.cantidad,
                "precio_unitario": det.precio_unitario,
                "precio_unitario_fmt": format_clp(det.precio_unitario),
                "subtotal": det.subtotal,
                "subtotal_fmt": format_clp(det.subtotal),
                "destino": det.destino,
                "estado": det.estado_produccion,
            }
        )

        if det.menu_id and det.menu is not None:
            componentes = descomponer_menu_combo(det.menu, cantidad_combo=det.cantidad)
            for comp in componentes:
                dest_comp = comp["destino"]
                comanda_area = comandas_map.get(dest_comp)
                estado_comp = (
                    comanda_area.estado
                    if comanda_area is not None
                    else ("Entregado" if dest_comp == "ENTREGA INMEDIATA" else det.estado_produccion)
                )
                label_comp = f"{comp['nombre']} ({det.menu.nombre})"
                items_distribucion.append(
                    {
                        "nombre": label_comp,
                        "cant": comp["cantidad"],
                        "destino": dest_comp,
                        "estado": estado_comp,
                    }
                )
                if dest_comp == "COCINA":
                    cocina_items.append(
                        {"cant": comp["cantidad"], "nombre": label_comp, "nota": nota_general}
                    )
                elif dest_comp == "BAR":
                    bar_items.append(
                        {"cant": comp["cantidad"], "nombre": label_comp, "nota": nota_general}
                    )
        else:
            comanda_area = comandas_map.get(det.destino)
            estado_item = comanda_area.estado if comanda_area is not None else det.estado_produccion
            items_distribucion.append(
                {
                    "nombre": det.nombre_item,
                    "cant": det.cantidad,
                    "destino": det.destino,
                    "estado": estado_item,
                }
            )
            if det.destino == "COCINA":
                cocina_items.append(
                    {"cant": det.cantidad, "nombre": det.nombre_item, "nota": nota_general}
                )
            elif det.destino == "BAR":
                bar_items.append(
                    {"cant": det.cantidad, "nombre": det.nombre_item, "nota": nota_general}
                )

    ubicacion_label = venta.mesa.numero if venta.mesa else ("BAR / Barra Rápida" if venta.modalidad == "BAR" else venta.modalidad)
    cajero_nombre = venta.usuario.nombre if venta.usuario else "Operador POS"

    comanda_cocina_obj = comandas_map.get("COCINA")
    comanda_bar_obj = comandas_map.get("BAR")

    return {
        "id": venta.id,
        "venta_num": venta.venta_num,
        "fecha": fecha_str,
        "hora": hora_str,
        "hora_completa": hora_completa_str,
        "modalidad": venta.modalidad,
        "ubicacion": ubicacion_label,
        "mesa_numero": venta.mesa.numero if venta.mesa else None,
        "garzon": cajero_nombre,
        "cajero": cajero_nombre,
        "subtotal": venta.subtotal,
        "subtotal_fmt": format_clp(venta.subtotal),
        "iva": venta.iva,
        "iva_fmt": format_clp(venta.iva),
        "total": venta.total,
        "total_fmt": format_clp(venta.total),
        "metodo_pago": venta.metodo_pago,
        "estado": venta.estado,
        "boleta_emitida": venta.boleta_emitida,
        "tipo_documento": (
            "COMANDA PEDIDO MESA (BOLETA DIFERIDA)"
            if venta.modalidad == "MESA" and not venta.boleta_emitida
            else "BOLETA ELECTRÓNICA DE VENTA"
        ),
        "notas": nota_general,
        "items": items_ticket,
        "items_distribucion": items_distribucion,
        "comanda_cocina": (
            {
                "codigo": comanda_cocina_obj.codigo_comanda,
                "estado": comanda_cocina_obj.estado,
                "hora": hora_str,
                "ubicacion": ubicacion_label,
                "garzon": cajero_nombre,
                "notas": comanda_cocina_obj.comentarios or nota_general or "Sin notas especiales",
                "items": cocina_items,
            }
            if comanda_cocina_obj
            else None
        ),
        "comanda_bar": (
            {
                "codigo": comanda_bar_obj.codigo_comanda,
                "estado": comanda_bar_obj.estado,
                "hora": hora_str,
                "ubicacion": ubicacion_label,
                "garzon": cajero_nombre,
                "notas": comanda_bar_obj.comentarios or nota_general or "Sin notas especiales",
                "items": bar_items,
            }
            if comanda_bar_obj
            else None
        ),
    }


def procesar_venta_transaccional(
    *,
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> tuple[dict, bool]:
    """
    Ejecuta la creación atómica de una Venta o Pedido de Mesa desde el POS.
    Retorna `(venta_serializada, fue_replay_idempotente)`.
    """
    if not isinstance(payload, dict):
        raise PosDomainError("El formato de los datos de la operación no es válido.")

    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if idempotency_key and (len(idempotency_key) > 80 or "\x00" in idempotency_key):
        raise PosDomainError("La clave de idempotencia proporcionada no es válida.")

    modalidad = str(payload.get("modalidad") or "BAR").strip().upper()
    if modalidad not in ("BAR", "MESA", "PARA LLEVAR"):
        raise PosDomainError(f"Modalidad de venta no permitida: '{modalidad}'.")

    metodo_pago = str(payload.get("metodo_pago") or "Efectivo").strip()
    metodos_validos = {"Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Vale Fiado", "Transferencia"}
    if metodo_pago not in metodos_validos:
        raise PosDomainError(f"Método de pago no válido: '{metodo_pago}'.")

    notas = str(payload.get("notas") or "").strip()[:500]
    mesa_numero = str(payload.get("mesa_numero") or "").strip()
    modo_mesa = str(payload.get("modo_mesa") or "nueva").strip().lower()

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or len(raw_items) == 0:
        raise PosDomainError("El carrito está vacío. Agregue al menos un producto o menú activo.")
    if len(raw_items) > 50:
        raise PosDomainError("El pedido excede el número máximo de líneas permitidas por transacción (50).")

    with transaction.atomic():
        # 1. Bloquear fila del usuario operador para serializar envíos concurrentes (doble clic)
        usuario_locked = Usuario.objects.select_for_update().get(pk=usuario.pk)

        # 2. Verificar idempotencia respaldada en base de datos
        if idempotency_key:
            idem_tag = f"[idem:{idempotency_key}]"
            existing_log = (
                LogAuditoria.objects.filter(
                    usuario=usuario_locked,
                    accion="VENTA_CREADA",
                    descripcion__startswith=idem_tag,
                )
                .order_by("-fecha_hora")
                .first()
            )
            if existing_log is not None:
                m_venta = re.search(r"\[venta:([^\]]+)\]", existing_log.descripcion)
                if m_venta:
                    existing_venta = Venta.objects.filter(venta_num=m_venta.group(1)).first()
                    if existing_venta is not None:
                        return serializar_venta_completa(existing_venta), True

        # 3. Consolidar y validar cada ítem del carrito contra PostgreSQL (ignorando precios del cliente)
        consolidated_lines = {}
        for idx, raw_line in enumerate(raw_items, start=1):
            if not isinstance(raw_line, dict):
                raise PosDomainError(f"Formato inválido en la línea #{idx} del pedido.")

            item_type = str(raw_line.get("tipo") or "producto").strip().lower()
            if item_type not in ("producto", "menu"):
                raise PosDomainError(f"Tipo de ítem desconocido en la línea #{idx}: '{item_type}'.")

            raw_id = raw_line.get("id")
            if isinstance(raw_id, bool) or raw_id is None or not str(raw_id).strip().lstrip("-").isdigit():
                raise PosDomainError(f"Identificador de ítem inválido en la línea #{idx}.")
            item_id = int(raw_id)

            raw_qty = raw_line.get("cantidad")
            if isinstance(raw_qty, bool) or raw_qty is None:
                raise PosDomainError(f"Cantidad inválida en la línea #{idx}.")
            try:
                cantidad = int(raw_qty)
            except (TypeError, ValueError):
                raise PosDomainError(f"La cantidad en la línea #{idx} debe ser un número entero.")

            if cantidad <= 0:
                raise PosDomainError(
                    f"La cantidad debe ser estrictamente positiva (línea #{idx}, recibido: {cantidad})."
                )
            if cantidad > 100:
                raise PosDomainError(f"La cantidad máxima por línea es de 100 unidades (línea #{idx}).")

            key = (item_type, item_id)
            consolidated_lines[key] = consolidated_lines.get(key, 0) + cantidad

        lineas_validadas = []
        tiene_items_cocina = False
        tiene_items_bar = False
        total_bruto = 0

        for (item_type, item_id), cantidad in consolidated_lines.items():
            if item_type == "producto":
                prod = Producto.objects.filter(pk=item_id).first()
                if prod is None:
                    raise PosDomainError(f"El producto solicitado (ID {item_id}) no existe en el catálogo.")
                if prod.estado != "Activo":
                    raise PosDomainError(
                        f"El producto '{prod.nombre}' no está disponible para la venta (estado: {prod.estado})."
                    )
                precio_oficial = int(prod.precio)
                subtotal_linea = precio_oficial * cantidad
                destino_linea = map_producto_destino_to_produccion(prod.destino)
                if destino_linea == "COCINA":
                    tiene_items_cocina = True
                elif destino_linea == "BAR":
                    tiene_items_bar = True

                lineas_validadas.append(
                    {
                        "tipo": "producto",
                        "producto": prod,
                        "menu": None,
                        "nombre_item": prod.nombre,
                        "cantidad": cantidad,
                        "precio_unitario": precio_oficial,
                        "subtotal": subtotal_linea,
                        "destino": destino_linea,
                        "estado_produccion": "Entregado" if destino_linea == "ENTREGA INMEDIATA" else "Pendiente",
                    }
                )
                total_bruto += subtotal_linea
            else:
                menu = MenuCombo.objects.filter(pk=item_id).first()
                if menu is None:
                    raise PosDomainError(f"El menú o combo solicitado (ID {item_id}) no existe en el catálogo.")
                if menu.estado != "Activo":
                    raise PosDomainError(
                        f"El menú '{menu.nombre}' no se encuentra activo para la venta."
                    )
                precio_oficial = int(menu.precio)
                subtotal_linea = precio_oficial * cantidad
                componentes = descomponer_menu_combo(menu, cantidad_combo=cantidad)
                comp_cocina = any(c["destino"] == "COCINA" for c in componentes)
                comp_bar = any(c["destino"] == "BAR" for c in componentes)

                if comp_cocina:
                    tiene_items_cocina = True
                if comp_bar:
                    tiene_items_bar = True

                if comp_cocina:
                    destino_menu = "COCINA"
                elif comp_bar:
                    destino_menu = "BAR"
                else:
                    destino_menu = "ENTREGA INMEDIATA"

                lineas_validadas.append(
                    {
                        "tipo": "menu",
                        "producto": None,
                        "menu": menu,
                        "nombre_item": menu.nombre,
                        "cantidad": cantidad,
                        "precio_unitario": precio_oficial,
                        "subtotal": subtotal_linea,
                        "destino": destino_menu,
                        "estado_produccion": "Entregado" if destino_menu == "ENTREGA INMEDIATA" else "Pendiente",
                    }
                )
                total_bruto += subtotal_linea

        # 4. Validar y bloquear Mesa cuando la modalidad es MESA
        mesa_obj = None
        if modalidad == "MESA":
            if not mesa_numero:
                raise PosDomainError("Debe seleccionar una mesa válida para registrar un pedido en modalidad MESA.")
            mesa_obj = Mesa.objects.select_for_update().filter(numero__iexact=mesa_numero).first()
            if mesa_obj is None:
                raise PosDomainError(f"La mesa '{mesa_numero}' no existe en el salón.", status_code=404)

            if modo_mesa == "agregar":
                if mesa_obj.estado not in ("Ocupada", "Disponible"):
                    raise PosDomainError(
                        f"No se pueden agregar pedidos a la {mesa_obj.numero} en estado '{mesa_obj.estado}'.",
                        status_code=409,
                    )
            else:
                if mesa_obj.estado != "Disponible":
                    raise PosDomainError(
                        f"La {mesa_obj.numero} ya se encuentra {mesa_obj.estado}. "
                        f"Seleccione una mesa disponible para abrir un nuevo pedido.",
                        status_code=409,
                    )

        # 5. Calcular Subtotal Neto, IVA (19%) y Total en CLP con la configuración vigente
        config_pos = ConfiguracionPOS.objects.first()
        iva_incluido = config_pos.iva_incluido if config_pos else True
        iva_porcentaje = config_pos.iva_porcentaje if config_pos else Decimal("19.00")
        totales = calcular_totales_clp(
            total_bruto,
            iva_incluido=iva_incluido,
            iva_porcentaje=iva_porcentaje,
        )

        # 6. Crear cabecera de Venta
        venta_num = _generar_siguiente_venta_num()
        sesion_activa = SesionCaja.objects.filter(estado="Abierta").order_by("-fecha_apertura").first()

        es_mesa_diferida = modalidad == "MESA"
        venta = Venta.objects.create(
            venta_num=venta_num,
            fecha_hora=timezone.now(),
            modalidad=modalidad,
            mesa=mesa_obj,
            usuario=usuario_locked,
            sesion_caja=sesion_activa,
            subtotal=totales["subtotal"],
            iva=totales["iva"],
            total=totales["total"],
            metodo_pago=metodo_pago,
            estado="Pendiente" if es_mesa_diferida else "Pagado",
            boleta_emitida=not es_mesa_diferida,
            notas=notas or None,
        )

        # 7. Crear registros de DetalleVenta
        for linea in lineas_validadas:
            DetalleVenta.objects.create(
                venta=venta,
                producto=linea["producto"],
                menu=linea["menu"],
                nombre_item=linea["nombre_item"],
                cantidad=linea["cantidad"],
                precio_unitario=linea["precio_unitario"],
                subtotal=linea["subtotal"],
                destino=linea["destino"],
                estado_produccion=linea["estado_produccion"],
                notas_preparacion=notas or None,
            )

        # 8. Generar Comandas de Producción para Cocina (KDS) y Bar (BDS)
        if tiene_items_cocina:
            ComandaProduccion.objects.create(
                codigo_comanda=f"C-{venta_num}",
                venta=venta,
                area_destino="COCINA",
                urgencia="normal",
                estado="Pendiente",
                comentarios=notas or None,
            )

        if tiene_items_bar:
            ComandaProduccion.objects.create(
                codigo_comanda=f"B-{venta_num}",
                venta=venta,
                area_destino="BAR",
                urgencia="normal",
                estado="Pendiente",
                comentarios=notas or None,
            )

        # 9. Actualizar estado y consumo de la Mesa atómicamente
        if mesa_obj is not None:
            raw_comensales = payload.get("comensales")
            try:
                comensales_int = int(raw_comensales) if raw_comensales else 0
            except (TypeError, ValueError):
                comensales_int = 0

            if comensales_int <= 0:
                comensales_int = mesa_obj.comensales_actuales or min(2, mesa_obj.capacidad)
            comensales_int = min(comensales_int, mesa_obj.capacidad)

            mesa_obj.estado = "Ocupada"
            mesa_obj.consumo_actual = (mesa_obj.consumo_actual or 0) + totales["total"]
            mesa_obj.mozo_asignado = usuario_locked
            mesa_obj.comensales_actuales = comensales_int
            if not mesa_obj.hora_inicio_ocupacion:
                mesa_obj.hora_inicio_ocupacion = timezone.now()
            mesa_obj.save()

        # 10. Si es Vale Fiado y se especificó rut_fiado o fiado_id, registrar cargo en FiadoPersonal
        rut_fiado = str(payload.get("rut_fiado") or "").strip()
        fiado_id_raw = payload.get("fiado_id")
        if metodo_pago == "Vale Fiado" and (rut_fiado or fiado_id_raw) and not es_mesa_diferida:
            fiado_qs = FiadoPersonal.objects.select_for_update()
            if fiado_id_raw not in (None, "") and str(fiado_id_raw).isdigit():
                fiado_obj = fiado_qs.filter(pk=int(fiado_id_raw)).first()
            else:
                fiado_obj = fiado_qs.filter(rut__iexact=rut_fiado).first()
            if fiado_obj is None:
                raise PosDomainError("No existe cuenta de colaborador para el fiado indicado.")
            if fiado_obj.estado in ("Bloqueado", "Excedido"):
                raise PosDomainError(
                    f"La cuenta de fiado de {fiado_obj.trabajador} se encuentra en estado '{fiado_obj.estado}'."
                )
            nuevo_acumulado = int(fiado_obj.total_acumulado) + int(totales["total"])
            if nuevo_acumulado > int(fiado_obj.limite_credito):
                disponible = max(0, int(fiado_obj.limite_credito) - int(fiado_obj.total_acumulado))
                raise PosDomainError(
                    f"El monto de {format_clp(totales['total'])} excede el cupo disponible de {fiado_obj.trabajador} "
                    f"(Disponible: {format_clp(disponible)} / Límite: {format_clp(fiado_obj.limite_credito)}).",
                    code="fiado_cupo_excedido",
                )
            fiado_obj.total_acumulado = nuevo_acumulado
            fiado_obj.consumos_mes = (fiado_obj.consumos_mes or 0) + 1
            fiado_obj.estado = "Por descontar"
            fiado_obj.save()

            FiadoMovimiento.objects.create(
                fiado=fiado_obj,
                venta=venta,
                detalle=f"Venta POS #{venta_num}",
                cantidad=sum(l["cantidad"] for l in lineas_validadas),
                monto=totales["total"],
            )

        # 11. Registrar Auditoría con clave de idempotencia
        idem_prefix = f"[idem:{idempotency_key}]" if idempotency_key else ""
        LogAuditoria.objects.create(
            usuario=usuario_locked,
            accion="VENTA_CREADA",
            modulo="POS",
            descripcion=(
                f"{idem_prefix}[venta:{venta_num}] Venta registrada en modalidad {modalidad} "
                f"por {format_clp(totales['total'])} ({metodo_pago})."
            ),
            ip_origen=ip_origen,
        )
        if tiene_items_cocina or tiene_items_bar:
            areas_str = ", ".join(
                a for a, flag in (("COCINA", tiene_items_cocina), ("BAR", tiene_items_bar)) if flag
            )
            LogAuditoria.objects.create(
                usuario=usuario_locked,
                accion="COMANDA_ENVIADA",
                modulo="Producción",
                descripcion=f"Comandas derivadas a [{areas_str}] para Venta #{venta_num}.",
                ip_origen=ip_origen,
            )

        return serializar_venta_completa(venta, config=config_pos), False


def obtener_contadores_estacion(area_destino: str) -> dict:
    """
    Calcula en tiempo real desde PostgreSQL los contadores de una estación ('COCINA' o 'BAR').
    """
    area = area_destino.upper()
    estado_listo = "Preparado" if area == "COCINA" else "Listo"
    umbral_atraso = 15 if area == "COCINA" else 10
    ahora = timezone.now()

    comandas = list(
        ComandaProduccion.objects.filter(area_destino=area).exclude(estado="Entregado")
    )

    pendientes = 0
    en_prep = 0
    listos = 0
    atrasados = 0

    for c in comandas:
        minutos = max(0, int((ahora - c.fecha_hora_ingreso).total_seconds() // 60))
        if c.estado == "Pendiente":
            pendientes += 1
        elif c.estado == "En preparación":
            en_prep += 1
        elif c.estado in ("Preparado", "Listo"):
            listos += 1

        if c.estado not in ("Preparado", "Listo", "Entregado"):
            if minutos >= umbral_atraso or c.urgencia in ("urgente", "advertencia"):
                atrasados += 1

    return {
        "todos": len(comandas),
        "atrasados": atrasados,
        "pendientes": pendientes,
        "en_preparacion": en_prep,
        "listos": listos,
        "estado_listo_nombre": estado_listo,
    }


def avanzar_estado_comanda_transaccional(
    *,
    usuario: Usuario,
    user_role: str,
    codigo_comanda: str,
    accion: str = None,
    nuevo_estado: str = None,
    ip_origen: str = None,
) -> dict:
    """
    Avanza el estado de una `ComandaProduccion` en PostgreSQL validando permisos de estación
    y sincronizando simultáneamente `DetalleVenta.estado_produccion`.

    Secuencia oficial por estación:
    - COCINA: Pendiente -> En preparación -> Preparado -> Entregado
    - BAR:    Pendiente -> En preparación -> Listo -> Entregado
    """
    codigo = (codigo_comanda or "").strip()
    if not codigo:
        raise PosDomainError("Debe indicar el código de la comanda.")

    with transaction.atomic():
        comanda = (
            ComandaProduccion.objects.select_for_update()
            .select_related("venta")
            .filter(codigo_comanda__iexact=codigo)
            .first()
        )
        if comanda is None:
            raise PosDomainError(f"La comanda '{codigo}' no existe en la base de datos.", status_code=404)

        area = comanda.area_destino.upper()
        estado_listo_estacion = "Preparado" if area == "COCINA" else "Listo"

        # Verificar autorización por rol y estación
        if user_role == "cocina" and area != "COCINA":
            raise PosDomainError(
                "El rol de Cocina solo está autorizado para actualizar comandas del área COCINA.",
                status_code=403,
            )
        if user_role == "bar" and area != "BAR":
            raise PosDomainError(
                "El rol de Bar solo está autorizado para actualizar comandas del área BAR.",
                status_code=403,
            )

        accion_norm = (accion or "").strip().lower()
        target_estado = (nuevo_estado or "").strip()

        if not target_estado:
            if accion_norm in ("preparar", "iniciar"):
                target_estado = "En preparación"
            elif accion_norm in ("completar", "listo", "preparado"):
                target_estado = estado_listo_estacion
            elif accion_norm in ("entregar", "despachar", "entregado"):
                target_estado = "Entregado"
            else:
                raise PosDomainError(
                    f"Acción de comanda no reconocida: '{accion}'. Use 'preparar', 'completar' o 'entregar'."
                )

        # Normalizar equivalencia Preparado/Listo según la estación de la comanda
        if target_estado in ("Preparado", "Listo"):
            target_estado = estado_listo_estacion

        transiciones_validas = {
            "Pendiente": {"En preparación", estado_listo_estacion},
            "En preparación": {estado_listo_estacion, "Entregado"},
            "Preparado": {"Entregado"},
            "Listo": {"Entregado"},
            "Entregado": set(),
        }

        if comanda.estado == target_estado:
            contadores = obtener_contadores_estacion(area)
            return {
                "codigo_comanda": comanda.codigo_comanda,
                "area_destino": area,
                "estado_anterior": comanda.estado,
                "estado_actual": comanda.estado,
                "contadores": contadores,
            }

        permitidos = transiciones_validas.get(comanda.estado, set())
        if target_estado not in permitidos:
            raise PosDomainError(
                f"Transición de estado inválida para la comanda {comanda.codigo_comanda}: "
                f"no se puede pasar de '{comanda.estado}' a '{target_estado}'."
            )

        estado_anterior = comanda.estado
        comanda.estado = target_estado
        if target_estado in ("Preparado", "Listo", "Entregado"):
            comanda.urgencia = "listo"
            comanda.fecha_hora_despacho = timezone.now()
        comanda.save()

        # Sincronizar el estado de producción en las líneas de DetalleVenta asociadas
        detalles_venta = list(comanda.venta.detalles.select_related("menu").all())
        for det in detalles_venta:
            if det.destino == area:
                det.estado_produccion = target_estado
                det.save(update_fields=["estado_produccion"])
            elif det.menu_id and det.menu is not None:
                comps = descomponer_menu_combo(det.menu, cantidad_combo=1)
                if any(c["destino"] == area for c in comps):
                    # Si el combo tiene componentes en esta área, reflejar el avance
                    det.estado_produccion = target_estado
                    det.save(update_fields=["estado_produccion"])

        LogAuditoria.objects.create(
            usuario=usuario,
            accion="COMANDA_ESTADO",
            modulo=f"KDS {area}",
            descripcion=(
                f"Comanda {comanda.codigo_comanda} (Venta #{comanda.venta.venta_num}) "
                f"cambió de '{estado_anterior}' a '{target_estado}'."
            ),
            ip_origen=ip_origen,
        )

        contadores = obtener_contadores_estacion(area)
        return {
            "codigo_comanda": comanda.codigo_comanda,
            "venta_num": comanda.venta.venta_num,
            "area_destino": area,
            "estado_anterior": estado_anterior,
            "estado_actual": comanda.estado,
            "urgencia": comanda.urgencia,
            "contadores": contadores,
        }


def operar_mesa_transaccional(
    *,
    usuario: Usuario,
    accion: str,
    mesa_origen_num: str,
    mesa_destino_num: str = None,
    metodo_pago: str = "Efectivo",
    ip_origen: str = None,
) -> dict:
    """
    Ejecuta operaciones reales sobre mesas en PostgreSQL:
    - 'reasignar': traslada la ocupación y ventas pendientes de `mesa_origen` a `mesa_destino` libre.
    - 'liberar' / 'cobrar': cierra las ventas pendientes de `mesa_origen` (emitiendo su boleta) y libera la mesa.
    """
    accion_norm = (accion or "").strip().lower()
    origen_str = (mesa_origen_num or "").strip()
    if not origen_str:
        raise PosDomainError("Debe especificar la mesa de origen.")

    with transaction.atomic():
        if accion_norm == "reasignar":
            destino_str = (mesa_destino_num or "").strip()
            if not destino_str:
                raise PosDomainError("Debe seleccionar una mesa de destino disponible.")
            if origen_str.lower() == destino_str.lower():
                raise PosDomainError("La mesa de destino debe ser distinta a la mesa de origen.")

            # Bloquear ambas mesas en orden determinista por ID para evitar deadlocks
            mesas_locked = list(
                Mesa.objects.select_for_update()
                .filter(numero__in=[origen_str, destino_str])
                .order_by("id")
            )
            mapa_mesas = {m.numero.lower(): m for m in mesas_locked}
            m_origen = mapa_mesas.get(origen_str.lower())
            m_destino = mapa_mesas.get(destino_str.lower())

            if m_origen is None:
                raise PosDomainError(f"No existe la mesa de origen '{origen_str}'.", status_code=404)
            if m_destino is None:
                raise PosDomainError(f"No existe la mesa de destino '{destino_str}'.", status_code=404)
            if m_origen.estado != "Ocupada":
                raise PosDomainError(f"La {m_origen.numero} no se encuentra ocupada.", status_code=409)
            if m_destino.estado != "Disponible":
                raise PosDomainError(
                    f"La {m_destino.numero} no está disponible (estado: {m_destino.estado}).",
                    status_code=409,
                )

            # Trasladar estado operativo y ventas pendientes a la mesa de destino
            m_destino.estado = "Ocupada"
            m_destino.consumo_actual = m_origen.consumo_actual
            m_destino.mozo_asignado = m_origen.mozo_asignado or usuario
            m_destino.comensales_actuales = min(
                max(1, m_origen.comensales_actuales or 2),
                m_destino.capacidad,
            )
            m_destino.hora_inicio_ocupacion = m_origen.hora_inicio_ocupacion or timezone.now()
            m_destino.save()

            Venta.objects.filter(mesa=m_origen, estado="Pendiente").update(mesa=m_destino)

            m_origen.estado = "Disponible"
            m_origen.consumo_actual = 0
            m_origen.mozo_asignado = None
            m_origen.comensales_actuales = 0
            m_origen.hora_inicio_ocupacion = None
            m_origen.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="MESA_REASIGNADA",
                modulo="Mesas",
                descripcion=f"Reasignación de {m_origen.numero} hacia {m_destino.numero}.",
                ip_origen=ip_origen,
            )
            return {
                "accion": "reasignar",
                "mesa_origen": m_origen.numero,
                "mesa_destino": m_destino.numero,
                "consumo_trasladado": format_clp(m_destino.consumo_actual),
                "mensaje": f"Pedido trasladado exitosamente de {m_origen.numero} a {m_destino.numero}.",
            }

        elif accion_norm in ("liberar", "cobrar"):
            m_origen = Mesa.objects.select_for_update().filter(numero__iexact=origen_str).first()
            if m_origen is None:
                raise PosDomainError(f"No existe la mesa '{origen_str}'.", status_code=404)

            consumo_previo = m_origen.consumo_actual
            sesion_abierta = (
                SesionCaja.objects.select_for_update()
                .filter(estado="Abierta")
                .order_by("-fecha_apertura", "-id")
                .first()
            )
            ventas_pendientes = list(
                Venta.objects.select_for_update().filter(mesa=m_origen, estado="Pendiente")
            )
            for v in ventas_pendientes:
                v.estado = "Pagado"
                v.boleta_emitida = True
                if metodo_pago in {"Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Vale Fiado", "Transferencia"}:
                    v.metodo_pago = metodo_pago
                if v.sesion_caja_id is None and sesion_abierta is not None:
                    v.sesion_caja = sesion_abierta
                v.save()

            m_origen.estado = "Disponible"
            m_origen.consumo_actual = 0
            m_origen.mozo_asignado = None
            m_origen.comensales_actuales = 0
            m_origen.hora_inicio_ocupacion = None
            m_origen.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="MESA_REASIGNADA",
                modulo="Mesas",
                descripcion=(
                    f"Liberación y cierre de cuenta de {m_origen.numero} "
                    f"(consumo cerrado: {format_clp(consumo_previo)})."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "liberar",
                "mesa": m_origen.numero,
                "ventas_cerradas": len(ventas_pendientes),
                "consumo_cerrado": format_clp(consumo_previo),
                "mensaje": f"{m_origen.numero} liberada y disponible para nuevos clientes.",
            }

        else:
            raise PosDomainError(f"Acción de mesa no válida: '{accion}'.")


# =============================================================================
# CONSULTA Y SERIALIZACIÓN DE MÓDULOS DESDE POSTGRESQL
# =============================================================================
def obtener_configuracion_dict() -> dict:
    """Retorna la configuración vigente desde ConfiguracionPOS (o defaults del modelo)."""
    cfg = ConfiguracionPOS.objects.first()
    if cfg is None:
        cfg = ConfiguracionPOS()
    return {
        "id": cfg.id,
        "nombre_parque": cfg.nombre_parque,
        "razon_social": cfg.razon_social,
        "rut": cfg.rut,
        "direccion": cfg.direccion,
        "telefono": cfg.telefono,
        "terminal_caja": cfg.terminal_caja,
        "impresora_tickets": cfg.impresora_tickets,
        "impresora_cocina": cfg.impresora_cocina,
        "impresora_bar": cfg.impresora_bar,
        "iva_incluido": bool(cfg.iva_incluido),
        "iva_porcentaje": float(cfg.iva_porcentaje),
        "modo_offline_bool": bool(cfg.modo_offline),
        "modo_offline": "Habilitado (Cache local)" if cfg.modo_offline else "Deshabilitado",
        "sonido_comandas": bool(cfg.sonido_comandas),
        "resolucion_optimizada": cfg.resolucion_optimizada,
    }


def obtener_catalogo_pos() -> dict:
    """
    Obtiene desde PostgreSQL las categorías, productos activos, menús/combos activos
    y cuentas de fiado disponibles listos para renderizar en `pos.html`.
    """
    cats_db = list(Categoria.objects.filter(activo=True).order_by("id"))
    orden_preferido = ["todas", "comidas", "bebidas", "snacks", "helados", "combos"]
    cats_map = {c.id: {"id": c.id, "nombre": c.nombre, "icono": c.icono, "color": c.color} for c in cats_db}

    categorias_list = []
    if "todas" not in cats_map:
        categorias_list.append(
            {"id": "todas", "nombre": "Todas las Categorías", "icono": "bi-grid-fill", "color": "primary"}
        )
    for cid in orden_preferido:
        if cid in cats_map:
            categorias_list.append(cats_map.pop(cid))
    for cid, cdata in cats_map.items():
        categorias_list.append(cdata)
    if not any(c["id"] == "combos" for c in categorias_list):
        categorias_list.append(
            {"id": "combos", "nombre": "Menús & Combos", "icono": "bi-stars", "color": "success"}
        )

    productos_list = []
    for p in Producto.objects.select_related("categoria").filter(estado="Activo").order_by("id"):
        productos_list.append(
            {
                "id": p.id,
                "codigo": p.codigo,
                "nombre": p.nombre,
                "categoria_id": p.categoria_id,
                "categoria_nombre": p.categoria.nombre if p.categoria else "",
                "precio": p.precio,
                "precio_formateado": p.precio_formateado,
                "tipo": p.tipo,
                "destino": p.destino,
                "estado": p.estado,
                "badge_tipo": p.badge_tipo,
                "descripcion": p.descripcion or "",
                "icono": p.icono or "bi-box2-heart",
            }
        )

    menus_list = []
    for m in MenuCombo.objects.filter(estado="Activo").order_by("id"):
        info_dest = obtener_destinos_resumen_menu(m)
        menus_list.append(
            {
                "id": m.id,
                "codigo": m.codigo,
                "nombre": m.nombre,
                "productos_incluidos": m.productos_incluidos,
                "precio": m.precio,
                "precio_formateado": m.precio_formateado,
                "ahorro_estimado": m.ahorro_estimado,
                "ahorro": m.ahorro_formateado,
                "categoria": m.categoria,
                "disponibilidad": m.disponibilidad,
                "estado": m.estado,
                "destino": info_dest["destino"],
                "badge_tipo": info_dest["badge_tipo"],
                "tipo": info_dest["tipo"],
            }
        )

    fiados_list = []
    for f in FiadoPersonal.objects.exclude(estado="Bloqueado").order_by("trabajador"):
        fiados_list.append(
            {
                "id": f.id,
                "rut": f.rut,
                "trabajador": f.trabajador,
                "cargo_grupo": f.cargo_grupo,
                "disponible": max(0, f.limite_credito - f.total_acumulado),
                "disponible_fmt": format_clp(max(0, f.limite_credito - f.total_acumulado)),
            }
        )

    return {
        "categorias": categorias_list,
        "productos": productos_list,
        "menus": menus_list,
        "fiados": fiados_list,
    }


def obtener_mesas_salon() -> list:
    """
    Obtiene el listado de mesas desde PostgreSQL con tiempos transcurridos,
    consumo formateado y garzón asignado en tiempo real.
    """
    ahora = timezone.now()
    mesas_out = []
    for m in Mesa.objects.select_related("mozo_asignado").order_by("id"):
        es_ocupada = m.estado == "Ocupada"
        if es_ocupada and m.hora_inicio_ocupacion:
            hora_local = (
                timezone.localtime(m.hora_inicio_ocupacion)
                if timezone.is_aware(m.hora_inicio_ocupacion)
                else m.hora_inicio_ocupacion
            )
            inicio_str = hora_local.strftime("%H:%M")
            mins = max(1, int((ahora - m.hora_inicio_ocupacion).total_seconds() // 60))
            tiempo_str = f"{mins} min"
        elif es_ocupada:
            inicio_str = timezone.localtime(ahora).strftime("%H:%M")
            tiempo_str = "Reciente"
        else:
            inicio_str = "-"
            tiempo_str = "-"

        mozo_nombre = m.mozo_asignado.nombre if (es_ocupada and m.mozo_asignado) else "-"
        mesas_out.append(
            {
                "id": m.id,
                "numero": m.numero,
                "zona": m.zona,
                "capacidad": m.capacidad,
                "estado": m.estado,
                "inicio": inicio_str,
                "tiempo_transcurrido": tiempo_str,
                "consumo_actual_int": m.consumo_actual if es_ocupada else 0,
                "consumo_actual": format_clp(m.consumo_actual if es_ocupada else 0),
                "mozo": mozo_nombre,
                "comensales": m.comensales_actuales if es_ocupada else 0,
            }
        )
    return mesas_out


def obtener_pedidos_estacion(area_destino: str) -> list:
    """
    Obtiene las comandas activas de Cocina ('COCINA') o Bar ('BAR') desde PostgreSQL.
    """
    area = area_destino.upper()
    ahora = timezone.now()
    umbral_urgente = 25 if area == "COCINA" else 15
    umbral_advertencia = 15 if area == "COCINA" else 8

    comandas_qs = (
        ComandaProduccion.objects.select_related("venta", "venta__mesa", "venta__usuario")
        .prefetch_related("venta__detalles", "venta__detalles__menu")
        .filter(area_destino=area)
        .exclude(estado="Entregado")
        .order_by("fecha_hora_ingreso", "id")
    )

    pedidos_out = []
    for cmd in comandas_qs:
        venta = cmd.venta
        ingreso_local = (
            timezone.localtime(cmd.fecha_hora_ingreso)
            if timezone.is_aware(cmd.fecha_hora_ingreso)
            else cmd.fecha_hora_ingreso
        )
        hora_str = ingreso_local.strftime("%H:%M")
        minutos = max(0, int((ahora - cmd.fecha_hora_ingreso).total_seconds() // 60))

        if cmd.estado in ("Preparado", "Listo"):
            urgencia = "listo"
            estado_badge = "bg-success text-white"
        elif cmd.estado == "En preparación":
            urgencia = "urgente" if minutos >= umbral_urgente else ("advertencia" if minutos >= umbral_advertencia else "normal")
            estado_badge = "bg-warning text-dark"
        else:
            urgencia = "urgente" if minutos >= umbral_urgente else ("advertencia" if minutos >= umbral_advertencia else "normal")
            estado_badge = "bg-danger text-white" if area == "COCINA" else "bg-info text-dark"

        productos_cmd = []
        nota_venta = (venta.notas or cmd.comentarios or "").strip()
        for det in venta.detalles.all():
            if det.menu_id and det.menu is not None:
                comps = descomponer_menu_combo(det.menu, cantidad_combo=det.cantidad)
                for comp in comps:
                    if comp["destino"] == area:
                        productos_cmd.append(
                            {
                                "cant": comp["cantidad"],
                                "nombre": f"{comp['nombre']} ({det.menu.nombre})",
                                "nota": det.notas_preparacion or "",
                            }
                        )
            elif det.destino == area:
                productos_cmd.append(
                    {
                        "cant": det.cantidad,
                        "nombre": det.nombre_item,
                        "nota": det.notas_preparacion or "",
                    }
                )

        ubicacion = venta.mesa.numero if venta.mesa else ("Barra Principal" if area == "BAR" else "Barra Rápida")
        mozo_nombre = venta.usuario.nombre if venta.usuario else "Operador POS"
        modalidad_filtro = "MESA" if venta.modalidad == "MESA" else "BAR"

        pedidos_out.append(
            {
                "id": cmd.codigo_comanda,
                "venta_num": venta.venta_num,
                "hora": hora_str,
                "minutos_espera": minutos,
                "urgencia": urgencia,
                "modalidad": modalidad_filtro,
                "ubicacion": ubicacion,
                "mozo": mozo_nombre,
                "estado": cmd.estado,
                "estado_badge": estado_badge,
                "comentarios": cmd.comentarios or nota_venta,
                "productos": productos_cmd,
            }
        )

    return pedidos_out


def obtener_ventas_distribucion(limit: int = 30) -> list:
    """
    Construye el listado de ventas distribuidas desde PostgreSQL para el módulo Distribución.
    """
    ventas_qs = (
        Venta.objects.select_related("mesa", "usuario")
        .prefetch_related("detalles", "detalles__menu", "comandas")
        .order_by("-fecha_hora", "-id")[:limit]
    )

    distrib_out = []
    for v in ventas_qs:
        serial = serializar_venta_completa(v)
        distrib_out.append(
            {
                "id": v.id,
                "venta_num": serial["venta_num"],
                "modalidad": serial["ubicacion"],
                "modalidad_tipo": serial["modalidad"],
                "estado_venta": serial["estado"],
                "metodo_pago": serial["metodo_pago"],
                "hora": serial["hora"],
                "fecha": serial["fecha"],
                "garzon": serial["garzon"],
                "subtotal": serial["subtotal_fmt"],
                "iva": serial["iva_fmt"],
                "total": serial["total_fmt"],
                "items": serial["items_distribucion"],
            }
        )
    return distrib_out


# =============================================================================
# FASE 04 — CAJA, CUADRATURA Y FIADOS
# =============================================================================
def _parse_non_negative_int(raw_val, field_label: str, default: int = 0) -> int:
    """Convierte y valida un número entero no negativo (>= 0) rechazando decimales o negativos."""
    if raw_val in (None, ""):
        return default
    if isinstance(raw_val, bool):
        raise PosDomainError(f"Valor inválido para {field_label}.")
    if isinstance(raw_val, float):
        if not raw_val.is_integer():
            raise PosDomainError(f"El campo '{field_label}' debe ser un número entero.")
        val = int(raw_val)
    elif isinstance(raw_val, str):
        cleaned = raw_val.strip().replace(".", "").replace("$", "")
        if not re.fullmatch(r"-?\d+", cleaned):
            raise PosDomainError(f"El campo '{field_label}' debe ser un número entero válido.")
        val = int(cleaned)
    elif isinstance(raw_val, int):
        val = raw_val
    else:
        raise PosDomainError(f"Tipo de dato no válido para '{field_label}'.")

    if val < 0:
        raise PosDomainError(f"El campo '{field_label}' no puede ser negativo.")
    return val


def _parse_positive_int(raw_val, field_label: str) -> int:
    """Convierte y valida un número entero estrictamente positivo (>= 1)."""
    val = _parse_non_negative_int(raw_val, field_label, default=0)
    if val <= 0:
        raise PosDomainError(f"El campo '{field_label}' debe ser mayor a cero.")
    return val


def obtener_estado_caja_actual() -> dict:
    """
    Consulta desde PostgreSQL el estado real de la caja (`SesionCaja`), calculando:
    - Fondo inicial (`monto_apertura`)
    - Ventas pagadas en Efectivo de la sesión activa (`ventas_efectivo`)
    - Ventas pagadas con Tarjeta Débito / Crédito (`ventas_tarjetas`)
    - Ventas pagadas por Transferencia (`ventas_transferencia`)
    - Ventas registradas con Vale Fiado (`ventas_fiado`)
    - Efectivo esperado en gaveta (`monto_apertura + ventas_efectivo`)
    - Historial de las últimas sesiones cerradas con su cuadratura.
    """
    sesion = (
        SesionCaja.objects.select_related("cajero", "cajero__cargo")
        .filter(estado="Abierta")
        .order_by("-fecha_apertura", "-id")
        .first()
    )

    ultimos_cierres_qs = (
        SesionCaja.objects.select_related("cajero", "cuadratura")
        .filter(estado="Cerrada")
        .order_by("-fecha_cierre", "-id")[:5]
    )
    ultimos_cierres = []
    for s in ultimos_cierres_qs:
        fc_local = (
            timezone.localtime(s.fecha_cierre)
            if (s.fecha_cierre and timezone.is_aware(s.fecha_cierre))
            else (s.fecha_cierre or s.fecha_apertura)
        )
        ultimos_cierres.append(
            {
                "id": s.id,
                "cajero": s.cajero.nombre if s.cajero else "Operador",
                "terminal": s.terminal_nombre,
                "fecha_cierre": fc_local.strftime("%d/%m/%Y %H:%M") if fc_local else "-",
                "monto_apertura": s.monto_apertura,
                "monto_apertura_fmt": format_clp(s.monto_apertura),
                "esperado": s.monto_cierre_sistema,
                "esperado_fmt": format_clp(s.monto_cierre_sistema),
                "contado": s.monto_cierre_real,
                "contado_fmt": format_clp(s.monto_cierre_real),
                "diferencia": s.diferencia,
                "diferencia_fmt": (
                    "$0 (Exacta)"
                    if s.diferencia == 0
                    else (
                        f"+{format_clp(s.diferencia)} (Sobrante)"
                        if s.diferencia > 0
                        else f"-{format_clp(abs(s.diferencia))} (Faltante)"
                    )
                ),
            }
        )

    if sesion is None:
        return {
            "abierta": False,
            "sesion_id": None,
            "estado": "Cerrada",
            "terminal_nombre": "Terminal 01 - Caja Principal",
            "cajero_nombre": "-",
            "fecha_apertura": "-",
            "monto_apertura": 0,
            "monto_apertura_fmt": "$0",
            "ventas_efectivo": 0,
            "ventas_efectivo_fmt": "$0",
            "ventas_tarjetas": 0,
            "ventas_tarjetas_fmt": "$0",
            "ventas_transferencia": 0,
            "ventas_transferencia_fmt": "$0",
            "ventas_fiado": 0,
            "ventas_fiado_fmt": "$0",
            "efectivo_esperado": 0,
            "efectivo_esperado_fmt": "$0",
            "total_transacciones": 0,
            "ultimos_cierres": ultimos_cierres,
        }

    ventas_sesion_qs = Venta.objects.filter(
        Q(sesion_caja=sesion) | Q(sesion_caja__isnull=True, fecha_hora__gte=sesion.fecha_apertura),
        estado="Pagado",
    )

    ventas_efectivo = (
        ventas_sesion_qs.filter(metodo_pago="Efectivo").aggregate(t=Sum("total"))["t"] or 0
    )
    ventas_tarjetas = (
        ventas_sesion_qs.filter(metodo_pago__in=["Tarjeta Débito", "Tarjeta Crédito"]).aggregate(t=Sum("total"))["t"]
        or 0
    )
    ventas_transferencia = (
        ventas_sesion_qs.filter(metodo_pago="Transferencia").aggregate(t=Sum("total"))["t"] or 0
    )
    ventas_fiado = (
        ventas_sesion_qs.filter(metodo_pago="Vale Fiado").aggregate(t=Sum("total"))["t"] or 0
    )
    total_tx = ventas_sesion_qs.count()

    efectivo_esperado = int(sesion.monto_apertura) + int(ventas_efectivo)
    fa_local = (
        timezone.localtime(sesion.fecha_apertura)
        if timezone.is_aware(sesion.fecha_apertura)
        else sesion.fecha_apertura
    )

    return {
        "abierta": True,
        "sesion_id": sesion.id,
        "estado": "Abierta",
        "terminal_nombre": sesion.terminal_nombre,
        "cajero_nombre": sesion.cajero.nombre if sesion.cajero else "Operador",
        "fecha_apertura": fa_local.strftime("%d/%m/%Y %H:%M"),
        "monto_apertura": sesion.monto_apertura,
        "monto_apertura_fmt": format_clp(sesion.monto_apertura),
        "ventas_efectivo": ventas_efectivo,
        "ventas_efectivo_fmt": format_clp(ventas_efectivo),
        "ventas_tarjetas": ventas_tarjetas,
        "ventas_tarjetas_fmt": format_clp(ventas_tarjetas),
        "ventas_transferencia": ventas_transferencia,
        "ventas_transferencia_fmt": format_clp(ventas_transferencia),
        "ventas_fiado": ventas_fiado,
        "ventas_fiado_fmt": format_clp(ventas_fiado),
        "efectivo_esperado": efectivo_esperado,
        "efectivo_esperado_fmt": format_clp(efectivo_esperado),
        "total_transacciones": total_tx,
        "ultimos_cierres": ultimos_cierres,
    }


def ejecutar_operacion_caja_transaccional(
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    Procesa de forma transaccional y con bloqueo pesimista (`select_for_update`):
    - `apertura`: Abre una nueva `SesionCaja` con fondo inicial (`monto_apertura >= 0`),
      impidiendo sesiones abiertas duplicadas.
    - `cierre`: Calcula desde PostgreSQL el efectivo esperado (`monto_apertura + ventas en Efectivo`),
      registra las denominaciones en `CuadraturaCaja`, calcula el efectivo físico contado y la diferencia
      (`monto_cierre_real - monto_cierre_sistema`), cierra la sesión y audita la operación.
    """
    if usuario is None or usuario.estado != "Activo":
        raise PosDomainError("Sesión de usuario inválida o inactiva.", status_code=401)

    accion = str(payload.get("accion") or "").strip().lower()
    if accion not in ("apertura", "cierre", "estado"):
        raise PosDomainError("Acción de caja no válida. Use 'apertura', 'cierre' o 'estado'.")

    if accion == "estado":
        return {"accion": "estado", "caja": obtener_estado_caja_actual()}

    with transaction.atomic():
        # Bloquear fila del operador para serializar intentos concurrentes de apertura/cierre
        Usuario.objects.select_for_update().filter(pk=usuario.pk).first()
        sesion_abierta = (
            SesionCaja.objects.select_for_update()
            .filter(estado="Abierta")
            .order_by("-fecha_apertura", "-id")
            .first()
        )

        if accion == "apertura":
            if sesion_abierta is not None:
                raise PosDomainError(
                    f"Ya existe una sesión de caja abierta (#{sesion_abierta.id} en {sesion_abierta.terminal_nombre}). "
                    "Debe realizar el cierre y cuadratura antes de abrir un nuevo turno.",
                    status_code=400,
                    code="caja_ya_abierta",
                )

            monto_apertura = _parse_non_negative_int(
                payload.get("monto_apertura"),
                "monto de fondo inicial",
                default=50000,
            )
            observaciones = str(payload.get("observaciones") or "").strip()[:500]
            cfg = ConfiguracionPOS.objects.first()
            terminal_default = (
                usuario.caja_asignada
                if (usuario.caja_asignada and usuario.caja_asignada != "Sin asignar")
                else (cfg.terminal_caja if cfg else "Terminal 01 - Caja Principal")
            )
            terminal_nombre = str(payload.get("terminal_nombre") or terminal_default).strip()[:50]

            nueva_sesion = SesionCaja(
                cajero=usuario,
                terminal_nombre=terminal_nombre,
                fecha_apertura=timezone.now(),
                monto_apertura=monto_apertura,
                monto_cierre_sistema=monto_apertura,
                monto_cierre_real=0,
                diferencia=0,
                estado="Abierta",
                observaciones=observaciones,
            )
            nueva_sesion.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="APERTURA_CAJA",
                modulo="Caja y Cuadratura",
                descripcion=(
                    f"Apertura de caja #{nueva_sesion.id} en {terminal_nombre} por "
                    f"{usuario.nombre} (@{usuario.usuario}) con fondo inicial {format_clp(monto_apertura)}."
                ),
                ip_origen=ip_origen,
            )

            estado_actual = obtener_estado_caja_actual()
            return {
                "accion": "apertura",
                "sesion_id": nueva_sesion.id,
                "cajero": usuario.nombre,
                "rol": usuario.cargo.nombre if usuario.cargo else "",
                "monto_apertura": monto_apertura,
                "monto_apertura_fmt": format_clp(monto_apertura),
                "caja": estado_actual,
                "mensaje": (
                    f"Apertura de caja #{nueva_sesion.id} registrada correctamente "
                    f"con fondo inicial de {format_clp(monto_apertura)}."
                ),
            }

        # accion == "cierre"
        if sesion_abierta is None:
            raise PosDomainError(
                "No existe una sesión de caja abierta para realizar el cierre y cuadratura.",
                status_code=400,
                code="caja_no_abierta",
            )

        b_20000 = _parse_non_negative_int(payload.get("billetes_20000"), "billetes de $20.000", default=0)
        b_10000 = _parse_non_negative_int(payload.get("billetes_10000"), "billetes de $10.000", default=0)
        b_5000 = _parse_non_negative_int(payload.get("billetes_5000"), "billetes de $5.000", default=0)
        b_1000 = _parse_non_negative_int(payload.get("billetes_1000"), "billetes de $1.000", default=0)
        m_500 = _parse_non_negative_int(payload.get("monedas_500"), "monedas de $500", default=0)
        m_100 = _parse_non_negative_int(payload.get("monedas_100"), "monedas de $100", default=0)
        m_50 = _parse_non_negative_int(payload.get("monedas_50"), "monedas de $50", default=0)
        m_5 = _parse_non_negative_int(payload.get("monedas_5"), "monedas de $5", default=0)
        m_1 = _parse_non_negative_int(payload.get("monedas_1"), "monedas de $1", default=0)

        # Vincular ventas huérfanas pagadas durante el turno a esta sesión
        ventas_turno_qs = Venta.objects.select_for_update().filter(
            Q(sesion_caja=sesion_abierta)
            | Q(sesion_caja__isnull=True, fecha_hora__gte=sesion_abierta.fecha_apertura),
            estado="Pagado",
        )
        for v_turno in ventas_turno_qs:
            if v_turno.sesion_caja_id is None:
                v_turno.sesion_caja = sesion_abierta
                v_turno.save()

        ventas_efectivo_total = (
            Venta.objects.filter(
                sesion_caja=sesion_abierta,
                estado="Pagado",
                metodo_pago="Efectivo",
            ).aggregate(t=Sum("total"))["t"]
            or 0
        )
        ventas_otros_total = (
            Venta.objects.filter(
                sesion_caja=sesion_abierta,
                estado="Pagado",
            )
            .exclude(metodo_pago="Efectivo")
            .aggregate(t=Sum("total"))["t"]
            or 0
        )

        # El servidor calcula autoritativamente el efectivo esperado y el contado desde las denominaciones
        monto_cierre_sistema = int(sesion_abierta.monto_apertura) + int(ventas_efectivo_total)

        cuadratura, _ = CuadraturaCaja.objects.update_or_create(
            sesion=sesion_abierta,
            defaults={
                "billetes_20000": b_20000,
                "billetes_10000": b_10000,
                "billetes_5000": b_5000,
                "billetes_1000": b_1000,
                "monedas_500": m_500,
                "monedas_100": m_100,
                "monedas_50": m_50,
                "monedas_5": m_5,
                "monedas_1": m_1,
            },
        )
        monto_cierre_real = int(cuadratura.total_efectivo_contado)
        diferencia = monto_cierre_real - monto_cierre_sistema

        obs_cierre = str(payload.get("observaciones") or "").strip()[:500]
        if obs_cierre:
            sesion_abierta.observaciones = (
                f"{sesion_abierta.observaciones} | Cierre: {obs_cierre}".strip(" |")
                if sesion_abierta.observaciones
                else obs_cierre
            )

        sesion_abierta.fecha_cierre = timezone.now()
        sesion_abierta.monto_cierre_sistema = monto_cierre_sistema
        sesion_abierta.monto_cierre_real = monto_cierre_real
        sesion_abierta.diferencia = diferencia
        sesion_abierta.estado = "Cerrada"
        sesion_abierta.save()

        estado_dif = (
            "Cuadratura Exacta ($0)"
            if diferencia == 0
            else (
                f"Sobrante (+{format_clp(diferencia)})"
                if diferencia > 0
                else f"Faltante (-{format_clp(abs(diferencia))})"
            )
        )

        LogAuditoria.objects.create(
            usuario=usuario,
            accion="CIERRE_CAJA",
            modulo="Caja y Cuadratura",
            descripcion=(
                f"Cierre y cuadratura de caja #{sesion_abierta.id} por {usuario.nombre} (@{usuario.usuario}). "
                f"Esperado efectivo: {format_clp(monto_cierre_sistema)}, "
                f"Contado físico: {format_clp(monto_cierre_real)}, "
                f"Resultado: {estado_dif}. Otros medios no efectivo: {format_clp(ventas_otros_total)}."
            ),
            ip_origen=ip_origen,
        )

        estado_actual = obtener_estado_caja_actual()
        return {
            "accion": "cierre",
            "sesion_id": sesion_abierta.id,
            "cajero": usuario.nombre,
            "rol": usuario.cargo.nombre if usuario.cargo else "",
            "monto_apertura": sesion_abierta.monto_apertura,
            "ventas_efectivo": ventas_efectivo_total,
            "ventas_otros_medios": ventas_otros_total,
            "monto_cierre_sistema": monto_cierre_sistema,
            "monto_cierre_sistema_fmt": format_clp(monto_cierre_sistema),
            "monto_cierre_real": monto_cierre_real,
            "monto_cierre_real_fmt": format_clp(monto_cierre_real),
            "diferencia": diferencia,
            "diferencia_fmt": estado_dif,
            "caja": estado_actual,
            "mensaje": (
                f"Cierre de caja #{sesion_abierta.id} completado. "
                f"Contado: {format_clp(monto_cierre_real)} | Esperado: {format_clp(monto_cierre_sistema)} | {estado_dif}."
            ),
        }


def obtener_fiados_panel() -> dict:
    """
    Obtiene desde PostgreSQL las cuentas de `FiadoPersonal` y sus movimientos históricos (`FiadoMovimiento`).
    """
    cuentas_qs = FiadoPersonal.objects.prefetch_related("movimientos").order_by("trabajador")
    fiados_list = []
    deuda_total = 0
    colaboradores_con_saldo = 0
    consumos_pendientes = 0

    for f in cuentas_qs:
        deuda_total += int(f.total_acumulado)
        if f.total_acumulado > 0:
            colaboradores_con_saldo += 1
        consumos_pendientes += int(f.consumos_mes)

        movs = list(f.movimientos.order_by("-fecha", "-id"))
        ultimo_mov = movs[0] if movs else None
        if ultimo_mov:
            fecha_loc = (
                timezone.localtime(ultimo_mov.fecha)
                if timezone.is_aware(ultimo_mov.fecha)
                else ultimo_mov.fecha
            )
            ultimo_prod = ultimo_mov.detalle
            ultima_cant = ultimo_mov.cantidad
            ultimo_val_int = ultimo_mov.monto
            ultimo_val_fmt = (
                format_clp(ultimo_mov.monto)
                if ultimo_mov.monto > 0
                else f"-{format_clp(abs(ultimo_mov.monto))} (Abono)"
            )
            fecha_str = fecha_loc.strftime("%d/%m/%Y %H:%M")
        else:
            ultimo_prod = "Sin movimientos registrados"
            ultima_cant = 0
            ultimo_val_int = 0
            ultimo_val_fmt = "$0"
            fecha_str = "-"

        historial = []
        for m in movs[:20]:
            f_m = timezone.localtime(m.fecha) if timezone.is_aware(m.fecha) else m.fecha
            historial.append(
                {
                    "id": m.id,
                    "detalle": m.detalle,
                    "cantidad": m.cantidad,
                    "monto": m.monto,
                    "monto_fmt": (
                        f"+{format_clp(m.monto)}"
                        if m.monto > 0
                        else f"-{format_clp(abs(m.monto))}"
                    ),
                    "tipo": "Cargo Consumo" if m.monto > 0 else "Abono / Descuento Nómina",
                    "fecha": f_m.strftime("%d/%m/%Y %H:%M"),
                }
            )

        cupo_disponible = max(0, int(f.limite_credito) - int(f.total_acumulado))
        fiados_list.append(
            {
                "id": f.id,
                "rut": f.rut,
                "trabajador": f.trabajador,
                "cargo_grupo": f.cargo_grupo,
                "limite_credito": f.limite_credito,
                "limite_formateado": format_clp(f.limite_credito),
                "cupo_disponible": cupo_disponible,
                "cupo_formateado": format_clp(cupo_disponible),
                "ultimo_producto": ultimo_prod,
                "cantidad": ultima_cant,
                "valor": ultimo_val_int,
                "valor_formateado": ultimo_val_fmt,
                "fecha": fecha_str,
                "total_acumulado": f.total_acumulado,
                "total_formateado": format_clp(f.total_acumulado),
                "consumos_mes": f.consumos_mes,
                "estado": f.estado,
                "movimientos": historial,
            }
        )

    return {
        "fiados": fiados_list,
        "deuda_total_int": deuda_total,
        "deuda_total": format_clp(deuda_total),
        "total_colaboradores": colaboradores_con_saldo,
        "total_cuentas": len(fiados_list),
        "consumos_pendientes": consumos_pendientes,
    }


def ejecutar_operacion_fiado_transaccional(
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    Gestiona de forma transaccional y segura las operaciones de `FiadoPersonal` y `FiadoMovimiento`:
    - `crear_cuenta`: Crea cuenta de crédito para un colaborador validando RUT único y límite >= 0.
    - `cargo`: Registra un vale de consumo validando estado, límite de crédito, idempotencia y precios reales si se indica producto/menú.
    - `abono`: Registra un pago o descuento de nómina (`monto < 0` en `FiadoMovimiento`) rebajando `total_acumulado` sin permitir saldos negativos ni borrar historial.
    - `estado`: Actualiza límite de crédito o estado de cuenta (`Al día`, `Por descontar`, `Bloqueado`).
    - Rechaza cualquier intento de modificar o eliminar registros históricos de `FiadoMovimiento`.
    """
    if usuario is None or usuario.estado != "Activo":
        raise PosDomainError("Sesión de usuario inválida.", status_code=401)

    accion = str(payload.get("accion") or "").strip().lower()
    if accion in ("editar_movimiento", "eliminar_movimiento", "borrar_movimiento"):
        raise PosDomainError(
            "Los movimientos históricos de fiado son inmutables y no pueden ser modificados ni eliminados.",
            status_code=400,
            code="fiado_historial_inmutable",
        )

    if accion not in ("crear_cuenta", "cargo", "abono", "estado"):
        raise PosDomainError("Acción de fiado no válida. Use 'crear_cuenta', 'cargo', 'abono' o 'estado'.")

    idem_key = str(payload.get("idempotency_key") or "").strip()[:80]
    if idem_key and not re.fullmatch(r"[A-Za-z0-9_\-\.:]+", idem_key):
        raise PosDomainError("Formato de idempotency_key no válido.")

    with transaction.atomic():
        Usuario.objects.select_for_update().filter(pk=usuario.pk).first()

        if idem_key:
            marker = f"[idem_fiado:{idem_key}]"
            existing_log = (
                LogAuditoria.objects.filter(modulo="Fiados", descripcion__startswith=marker)
                .order_by("-id")
                .first()
            )
            if existing_log:
                return {
                    "accion": accion,
                    "idempotent_replay": True,
                    "mensaje": "El movimiento de fiado ya se encontraba registrado (idempotencia activa).",
                    "panel": obtener_fiados_panel(),
                }

        if accion == "crear_cuenta":
            rut = str(payload.get("rut") or "").strip()
            trabajador = str(payload.get("trabajador") or "").strip()
            cargo_grupo = str(payload.get("cargo_grupo") or "Operaciones").strip()
            limite_credito = _parse_non_negative_int(
                payload.get("limite_credito"), "límite de crédito", default=50000
            )
            if not rut or len(rut) < 7:
                raise PosDomainError("Debe ingresar un RUT válido para el colaborador.")
            if not trabajador:
                raise PosDomainError("Debe ingresar el nombre completo del colaborador.")
            if FiadoPersonal.objects.filter(rut__iexact=rut).exists():
                raise PosDomainError(f"Ya existe una cuenta de fiado registrada con el RUT {rut}.")

            nueva_cuenta = FiadoPersonal(
                rut=rut,
                trabajador=trabajador,
                cargo_grupo=cargo_grupo,
                limite_credito=limite_credito,
                total_acumulado=0,
                consumos_mes=0,
                estado="Al día",
            )
            nueva_cuenta.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="VENTA_CREADA",
                modulo="Fiados",
                descripcion=(
                    f"{f'[idem_fiado:{idem_key}] ' if idem_key else ''}"
                    f"Alta de cuenta de fiado para {trabajador} ({rut}) con límite {format_clp(limite_credito)}."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "crear_cuenta",
                "fiado_id": nueva_cuenta.id,
                "mensaje": f"Cuenta de crédito creada para {trabajador} ({rut}).",
                "panel": obtener_fiados_panel(),
            }

        fiado_id = payload.get("fiado_id")
        rut_lookup = str(payload.get("rut") or "").strip()
        fiado_qs = FiadoPersonal.objects.select_for_update()
        fiado_obj = None
        if fiado_id not in (None, "") and str(fiado_id).isdigit():
            fiado_obj = fiado_qs.filter(pk=int(fiado_id)).first()
        elif rut_lookup:
            fiado_obj = fiado_qs.filter(rut__iexact=rut_lookup).first()

        if fiado_obj is None:
            raise PosDomainError("No se encontró la cuenta del colaborador seleccionado.", status_code=404)

        if accion == "cargo":
            if fiado_obj.estado in ("Bloqueado", "Excedido"):
                raise PosDomainError(
                    f"La cuenta de {fiado_obj.trabajador} se encuentra en estado '{fiado_obj.estado}' y no admite nuevos cargos."
                )

            cantidad = _parse_positive_int(payload.get("cantidad", 1), "cantidad")
            producto_id = payload.get("producto_id")
            menu_id = payload.get("menu_id")

            if producto_id not in (None, "") and str(producto_id).isdigit():
                prod_obj = Producto.objects.filter(pk=int(producto_id), estado="Activo").first()
                if prod_obj is None:
                    raise PosDomainError("El producto seleccionado no existe o está inactivo.")
                detalle = prod_obj.nombre
                monto = cantidad * int(prod_obj.precio)
            elif menu_id not in (None, "") and str(menu_id).isdigit():
                menu_obj = MenuCombo.objects.filter(pk=int(menu_id), estado="Activo").first()
                if menu_obj is None:
                    raise PosDomainError("El menú seleccionado no existe o está inactivo.")
                detalle = menu_obj.nombre
                monto = cantidad * int(menu_obj.precio)
            else:
                detalle = str(payload.get("detalle") or payload.get("producto") or "").strip()
                if not detalle:
                    raise PosDomainError("Debe indicar el producto o concepto del consumo fiado.")
                monto = _parse_positive_int(payload.get("monto"), "monto del consumo")

            nuevo_acumulado = int(fiado_obj.total_acumulado) + monto
            if nuevo_acumulado > int(fiado_obj.limite_credito):
                disponible = max(0, int(fiado_obj.limite_credito) - int(fiado_obj.total_acumulado))
                raise PosDomainError(
                    f"El cargo por {format_clp(monto)} excede el cupo disponible de {fiado_obj.trabajador} "
                    f"(Disponible: {format_clp(disponible)} / Límite: {format_clp(fiado_obj.limite_credito)}).",
                    status_code=400,
                    code="fiado_cupo_excedido",
                )

            mov = FiadoMovimiento(
                fiado=fiado_obj,
                detalle=detalle[:255],
                cantidad=cantidad,
                monto=monto,
                fecha=timezone.now(),
            )
            mov.save()

            fiado_obj.total_acumulado = nuevo_acumulado
            fiado_obj.consumos_mes = int(fiado_obj.consumos_mes) + 1
            fiado_obj.estado = "Por descontar" if nuevo_acumulado > 0 else "Al día"
            fiado_obj.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="VENTA_CREADA",
                modulo="Fiados",
                descripcion=(
                    f"{f'[idem_fiado:{idem_key}] ' if idem_key else ''}"
                    f"Cargo de vale fiado a {fiado_obj.trabajador} ({fiado_obj.rut}): "
                    f"{cantidad}x {detalle} por {format_clp(monto)}. Saldo acumulado: {format_clp(nuevo_acumulado)}."
                ),
                ip_origen=ip_origen,
            )

            return {
                "accion": "cargo",
                "fiado_id": fiado_obj.id,
                "movimiento_id": mov.id,
                "monto": monto,
                "nuevo_saldo": nuevo_acumulado,
                "nuevo_saldo_fmt": format_clp(nuevo_acumulado),
                "mensaje": (
                    f"Vale fiado registrado a {fiado_obj.trabajador}: {format_clp(monto)}. "
                    f"Nuevo saldo: {format_clp(nuevo_acumulado)}."
                ),
                "panel": obtener_fiados_panel(),
            }

        elif accion == "abono":
            if fiado_obj.total_acumulado <= 0:
                raise PosDomainError(
                    f"{fiado_obj.trabajador} no registra deuda pendiente para abonar ($0)."
                )

            monto_abono = _parse_positive_int(
                payload.get("monto") or payload.get("total_acumulado") or fiado_obj.total_acumulado,
                "monto de abono",
            )
            if monto_abono > int(fiado_obj.total_acumulado):
                raise PosDomainError(
                    f"El abono ({format_clp(monto_abono)}) no puede superar la deuda acumulada actual "
                    f"({format_clp(fiado_obj.total_acumulado)})."
                )

            motivo = str(payload.get("detalle") or "Abono / Descuento por nómina").strip()[:255]
            mov = FiadoMovimiento(
                fiado=fiado_obj,
                detalle=motivo,
                cantidad=1,
                monto=-monto_abono,
                fecha=timezone.now(),
            )
            mov.save()

            nuevo_saldo = int(fiado_obj.total_acumulado) - monto_abono
            fiado_obj.total_acumulado = nuevo_saldo
            if nuevo_saldo == 0 and fiado_obj.estado != "Bloqueado":
                fiado_obj.estado = "Al día"
                fiado_obj.consumos_mes = 0
            elif nuevo_saldo > 0 and fiado_obj.estado != "Bloqueado":
                fiado_obj.estado = "Por descontar"
            fiado_obj.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="VENTA_CREADA",
                modulo="Fiados",
                descripcion=(
                    f"{f'[idem_fiado:{idem_key}] ' if idem_key else ''}"
                    f"Abono/pago registrado para {fiado_obj.trabajador} ({fiado_obj.rut}) "
                    f"por {format_clp(monto_abono)}. Saldo restante: {format_clp(nuevo_saldo)}."
                ),
                ip_origen=ip_origen,
            )

            return {
                "accion": "abono",
                "fiado_id": fiado_obj.id,
                "movimiento_id": mov.id,
                "monto_abonado": monto_abono,
                "nuevo_saldo": nuevo_saldo,
                "nuevo_saldo_fmt": format_clp(nuevo_saldo),
                "mensaje": (
                    f"Abono de {format_clp(monto_abono)} registrado para {fiado_obj.trabajador}. "
                    f"Saldo pendiente: {format_clp(nuevo_saldo)}."
                ),
                "panel": obtener_fiados_panel(),
            }

        else:  # accion == "estado"
            nuevo_estado = str(payload.get("estado") or "").strip()
            if nuevo_estado:
                if nuevo_estado not in ("Al día", "Por descontar", "Excedido", "Bloqueado"):
                    raise PosDomainError(f"Estado de cuenta de fiado no válido: '{nuevo_estado}'.")
                if nuevo_estado == "Al día" and fiado_obj.total_acumulado > 0:
                    raise PosDomainError(
                        "No se puede marcar como 'Al día' una cuenta con saldo pendiente sin registrar el abono correspondiente."
                    )
                fiado_obj.estado = nuevo_estado

            if payload.get("limite_credito") not in (None, ""):
                fiado_obj.limite_credito = _parse_non_negative_int(
                    payload.get("limite_credito"), "límite de crédito"
                )
            fiado_obj.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Fiados",
                descripcion=(
                    f"Actualización de cuenta de fiado de {fiado_obj.trabajador}: "
                    f"estado={fiado_obj.estado}, límite={format_clp(fiado_obj.limite_credito)}."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "estado",
                "fiado_id": fiado_obj.id,
                "estado": fiado_obj.estado,
                "limite_credito": fiado_obj.limite_credito,
                "mensaje": f"Cuenta de {fiado_obj.trabajador} actualizada correctamente.",
                "panel": obtener_fiados_panel(),
            }


# =============================================================================
# FASE 05 — MANTENEDORES ADMINISTRATIVOS (PRODUCTOS, MENÚS, USUARIOS, CONFIG)
# =============================================================================
def obtener_productos_panel() -> dict:
    """Obtiene el catálogo completo de productos y categorías desde PostgreSQL para el mantenedor."""
    categorias_qs = Categoria.objects.exclude(id="todas").order_by("id")
    categorias_list = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "icono": c.icono,
            "color": c.color,
            "activo": c.activo,
        }
        for c in categorias_qs
    ]

    productos_qs = Producto.objects.select_related("categoria").order_by("codigo", "id")
    productos_list = []
    for p in productos_qs:
        productos_list.append(
            {
                "id": p.id,
                "codigo": p.codigo,
                "nombre": p.nombre,
                "categoria_id": p.categoria_id,
                "categoria_nombre": p.categoria.nombre if p.categoria else "",
                "precio": p.precio,
                "precio_formateado": p.precio_formateado,
                "tipo": p.tipo,
                "destino": p.destino,
                "estado": p.estado,
                "badge_tipo": p.badge_tipo,
                "descripcion": p.descripcion or "",
                "icono": p.icono or "bi-box2-heart",
            }
        )

    return {
        "productos": productos_list,
        "categorias": categorias_list,
        "total_productos": len(productos_list),
        "total_activos": len([p for p in productos_list if p["estado"] == "Activo"]),
        "total_cocina": len([p for p in productos_list if p["destino"] == "Cocina"]),
        "total_bar": len([p for p in productos_list if p["destino"] == "Bar"]),
        "total_listos": len([p for p in productos_list if p["destino"] == "Directo"]),
    }


def ejecutar_operacion_producto_transaccional(
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    CRUD transaccional de `Producto` y `Categoria`:
    - `crear` / `editar`: Valida código, nombre, categoría real, precio > 0, tipo, destino y estado.
    - `cambiar_estado` / `desactivar`: Cambia estado (`Activo`, `Inactivo`, `Agotado`) sin romper referencias históricas.
    - `eliminar`: Si el producto posee historial en `DetalleVenta`, impide el borrado físico y sugiere/aplica desactivación.
    - `crear_categoria` / `editar_categoria`: Crea o edita una categoría en PostgreSQL.
    """
    if usuario is None or usuario.estado != "Activo":
        raise PosDomainError("Sesión de usuario inválida.", status_code=401)

    accion = str(payload.get("accion") or "").strip().lower()
    if accion not in (
        "crear",
        "editar",
        "cambiar_estado",
        "desactivar",
        "eliminar",
        "crear_categoria",
        "editar_categoria",
    ):
        raise PosDomainError(f"Acción de mantenedor de productos no válida: '{accion}'.")

    with transaction.atomic():
        if accion in ("crear_categoria", "editar_categoria"):
            cat_id = str(payload.get("id") or "").strip().lower()
            nombre_cat = str(payload.get("nombre") or "").strip()
            icono_cat = str(payload.get("icono") or "bi-grid-fill").strip()
            color_cat = str(payload.get("color") or "primary").strip()
            activo_cat = str(payload.get("activo", "true")).lower() not in ("false", "0", "no")

            if not cat_id or not re.fullmatch(r"[a-z0-9_\-]+", cat_id):
                raise PosDomainError("El identificador de categoría debe ser alfanumérico (ej. 'postres').")
            if not nombre_cat:
                raise PosDomainError("El nombre de la categoría es obligatorio.")

            cat_obj, created = Categoria.objects.update_or_create(
                id=cat_id,
                defaults={
                    "nombre": nombre_cat[:100],
                    "icono": icono_cat[:50],
                    "color": color_cat[:30],
                    "activo": activo_cat,
                },
            )
            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Productos",
                descripcion=f"{'Creación' if created else 'Edición'} de categoría '{cat_obj.nombre}' ({cat_obj.id}).",
                ip_origen=ip_origen,
            )
            return {
                "accion": accion,
                "categoria_id": cat_obj.id,
                "mensaje": f"Categoría '{cat_obj.nombre}' guardada exitosamente.",
            }

        if accion in ("cambiar_estado", "desactivar", "eliminar"):
            prod_id = payload.get("id") or payload.get("producto_id")
            codigo_lookup = str(payload.get("codigo") or "").strip()
            prod_obj = None
            if prod_id not in (None, "") and str(prod_id).isdigit():
                prod_obj = Producto.objects.select_for_update().filter(pk=int(prod_id)).first()
            elif codigo_lookup:
                prod_obj = Producto.objects.select_for_update().filter(codigo__iexact=codigo_lookup).first()

            if prod_obj is None:
                raise PosDomainError("El producto especificado no existe.", status_code=404)

            if accion == "eliminar":
                if DetalleVenta.objects.filter(producto=prod_obj).exists():
                    raise PosDomainError(
                        f"No se puede eliminar físicamente '{prod_obj.nombre}' porque posee ventas históricas asociadas. "
                        "Utilice la opción de desactivar para conservar la integridad referencial.",
                        status_code=400,
                        code="producto_con_historial",
                    )
                try:
                    nombre_eliminado = prod_obj.nombre
                    prod_obj.delete()
                    LogAuditoria.objects.create(
                        usuario=usuario,
                        accion="PRODUCTO_MODIFICADO",
                        modulo="Productos",
                        descripcion=f"Eliminación de producto sin historial: {nombre_eliminado}.",
                        ip_origen=ip_origen,
                    )
                    return {
                        "accion": "eliminar",
                        "mensaje": f"Producto '{nombre_eliminado}' eliminado.",
                    }
                except ProtectedError:
                    raise PosDomainError(
                        "El producto está protegido por referencias históricas y no puede eliminarse.",
                        status_code=400,
                    )

            nuevo_estado = str(payload.get("estado") or "").strip()
            if not nuevo_estado:
                nuevo_estado = "Inactivo" if prod_obj.estado == "Activo" else "Activo"
            if nuevo_estado not in ("Activo", "Inactivo", "Agotado"):
                raise PosDomainError(f"Estado de producto no válido: '{nuevo_estado}'.")

            prod_obj.estado = nuevo_estado
            prod_obj.save()
            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Productos",
                descripcion=f"Cambio de estado de producto '{prod_obj.nombre}' ({prod_obj.codigo}) a '{nuevo_estado}'.",
                ip_origen=ip_origen,
            )
            return {
                "accion": accion,
                "producto_id": prod_obj.id,
                "estado": prod_obj.estado,
                "mensaje": f"Estado de '{prod_obj.nombre}' actualizado a {prod_obj.estado}.",
            }

        # accion in ("crear", "editar")
        prod_id = payload.get("id") or payload.get("producto_id")
        codigo = str(payload.get("codigo") or "").strip().upper()
        nombre = str(payload.get("nombre") or "").strip()
        categoria_id = str(payload.get("categoria_id") or payload.get("categoria") or "").strip().lower()
        precio = _parse_positive_int(payload.get("precio"), "precio del producto")
        tipo_raw = str(payload.get("tipo") or "Requiere preparación").strip()
        destino = str(payload.get("destino") or "Directo").strip()
        estado = str(payload.get("estado") or "Activo").strip()
        descripcion = str(payload.get("descripcion") or "").strip()
        icono = str(payload.get("icono") or "").strip()

        if not codigo:
            raise PosDomainError("El código del producto es obligatorio.")
        if not nombre:
            raise PosDomainError("El nombre del producto es obligatorio.")

        tipo_map = {
            "preparacion": "Requiere preparación",
            "requiere preparación": "Requiere preparación",
            "requiere preparacion": "Requiere preparación",
            "listo": "Producto listo",
            "producto listo": "Producto listo",
        }
        tipo = tipo_map.get(tipo_raw.lower(), tipo_raw)
        if tipo not in ("Requiere preparación", "Producto listo"):
            raise PosDomainError("El tipo de producto debe ser 'Requiere preparación' o 'Producto listo'.")

        if destino not in ("Cocina", "Bar", "Directo"):
            raise PosDomainError("El destino del producto debe ser 'Cocina', 'Bar' o 'Directo'.")

        if estado not in ("Activo", "Inactivo", "Agotado"):
            raise PosDomainError("El estado del producto debe ser 'Activo', 'Inactivo' o 'Agotado'.")

        cat_obj = Categoria.objects.filter(id=categoria_id).first()
        if cat_obj is None:
            raise PosDomainError(f"La categoría '{categoria_id}' no existe.")

        badge_map = {
            "Cocina": "badge-cocina",
            "Bar": "badge-bar",
            "Directo": "badge-listo",
        }
        icono_default = {
            "Cocina": "bi-fire",
            "Bar": "bi-cup-straw",
            "Directo": "bi-box2-heart",
        }

        if accion == "editar" or (prod_id not in (None, "") and str(prod_id).isdigit()):
            if prod_id not in (None, "") and str(prod_id).isdigit():
                prod_obj = Producto.objects.select_for_update().filter(pk=int(prod_id)).first()
            else:
                prod_obj = Producto.objects.select_for_update().filter(codigo__iexact=codigo).first()

            if prod_obj is None:
                raise PosDomainError("El producto que intenta editar no existe.", status_code=404)

            if Producto.objects.exclude(pk=prod_obj.pk).filter(codigo__iexact=codigo).exists():
                raise PosDomainError(f"Ya existe otro producto con el código '{codigo}'.")

            prod_obj.codigo = codigo
            prod_obj.nombre = nombre
            prod_obj.categoria = cat_obj
            prod_obj.precio = precio
            prod_obj.tipo = tipo
            prod_obj.destino = destino
            prod_obj.estado = estado
            prod_obj.badge_tipo = badge_map[destino]
            prod_obj.descripcion = descripcion
            if icono:
                prod_obj.icono = icono
            prod_obj.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Productos",
                descripcion=(
                    f"Edición de producto '{prod_obj.nombre}' ({prod_obj.codigo}): "
                    f"precio={format_clp(precio)}, destino={destino}, estado={estado}."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "editar",
                "producto_id": prod_obj.id,
                "codigo": prod_obj.codigo,
                "mensaje": f"Producto '{prod_obj.nombre}' actualizado exitosamente.",
            }

        if Producto.objects.filter(codigo__iexact=codigo).exists():
            raise PosDomainError(f"Ya existe un producto registrado con el código '{codigo}'.")

        nuevo_prod = Producto(
            codigo=codigo,
            nombre=nombre,
            categoria=cat_obj,
            precio=precio,
            tipo=tipo,
            destino=destino,
            estado=estado,
            badge_tipo=badge_map[destino],
            descripcion=descripcion,
            icono=icono or icono_default[destino],
        )
        nuevo_prod.save()

        LogAuditoria.objects.create(
            usuario=usuario,
            accion="PRODUCTO_MODIFICADO",
            modulo="Productos",
            descripcion=(
                f"Creación de producto '{nuevo_prod.nombre}' ({nuevo_prod.codigo}): "
                f"precio={format_clp(precio)}, destino={destino}, estado={estado}."
            ),
            ip_origen=ip_origen,
        )
        return {
            "accion": "crear",
            "producto_id": nuevo_prod.id,
            "codigo": nuevo_prod.codigo,
            "mensaje": f"Producto '{nuevo_prod.nombre}' creado exitosamente.",
        }


def obtener_menus_panel() -> dict:
    """Obtiene desde PostgreSQL todos los `MenuCombo` con su desglose de componentes para Cocina y Bar."""
    menus_qs = MenuCombo.objects.order_by("codigo", "id")
    productos_activos = {
        p.nombre.strip().lower(): p for p in Producto.objects.filter(estado="Activo")
    }
    menus_list = []
    for m in menus_qs:
        info_dest = obtener_destinos_resumen_menu(m, productos_activos)
        componentes = descomponer_menu_combo(m, 1, productos_activos)
        menus_list.append(
            {
                "id": m.id,
                "codigo": m.codigo,
                "nombre": m.nombre,
                "productos_incluidos": m.productos_incluidos,
                "precio": m.precio,
                "precio_formateado": m.precio_formateado,
                "ahorro_estimado": m.ahorro_estimado,
                "ahorro": m.ahorro_formateado,
                "categoria": m.categoria,
                "disponibilidad": m.disponibilidad,
                "estado": m.estado,
                "destino": info_dest["destino"],
                "badge_tipo": info_dest["badge_tipo"],
                "componentes": componentes,
            }
        )

    catalogo_productos = [
        {"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "destino": p.destino, "precio": p.precio}
        for p in Producto.objects.filter(estado="Activo").order_by("nombre")
    ]

    return {
        "menus": menus_list,
        "productos_catalogo": catalogo_productos,
        "total_menus": len(menus_list),
        "total_activos": len([m for m in menus_list if m["estado"] == "Activo"]),
    }


def ejecutar_operacion_menu_transaccional(
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    CRUD transaccional de `MenuCombo`:
    - `crear` / `editar`: Valida código, nombre, productos_incluidos, precio > 0, ahorro >= 0, disponibilidad y estado,
      y verifica su desglose para Cocina y Bar.
    - `cambiar_estado` / `desactivar`: Activa o desactiva el menú sin romper ventas históricas.
    """
    if usuario is None or usuario.estado != "Activo":
        raise PosDomainError("Sesión de usuario inválida.", status_code=401)

    accion = str(payload.get("accion") or "").strip().lower()
    if accion not in ("crear", "editar", "cambiar_estado", "desactivar", "eliminar"):
        raise PosDomainError(f"Acción de menú no válida: '{accion}'.")

    with transaction.atomic():
        if accion in ("cambiar_estado", "desactivar", "eliminar"):
            menu_id = payload.get("id") or payload.get("menu_id")
            codigo_lookup = str(payload.get("codigo") or "").strip()
            menu_obj = None
            if menu_id not in (None, "") and str(menu_id).isdigit():
                menu_obj = MenuCombo.objects.select_for_update().filter(pk=int(menu_id)).first()
            elif codigo_lookup:
                menu_obj = MenuCombo.objects.select_for_update().filter(codigo__iexact=codigo_lookup).first()

            if menu_obj is None:
                raise PosDomainError("El menú o combo especificado no existe.", status_code=404)

            if accion == "eliminar" and DetalleVenta.objects.filter(menu=menu_obj).exists():
                raise PosDomainError(
                    f"No se puede eliminar físicamente '{menu_obj.nombre}' porque tiene ventas históricas asociadas. "
                    "Desactívelo para preservar el historial.",
                    status_code=400,
                )
            elif accion == "eliminar":
                nombre_del = menu_obj.nombre
                menu_obj.delete()
                LogAuditoria.objects.create(
                    usuario=usuario,
                    accion="PRODUCTO_MODIFICADO",
                    modulo="Menús y Combos",
                    descripcion=f"Eliminación de menú sin historial: {nombre_del}.",
                    ip_origen=ip_origen,
                )
                return {"accion": "eliminar", "mensaje": f"Menú '{nombre_del}' eliminado."}

            nuevo_estado = str(payload.get("estado") or "").strip()
            if not nuevo_estado:
                nuevo_estado = "Inactivo" if menu_obj.estado == "Activo" else "Activo"
            if nuevo_estado not in ("Activo", "Inactivo"):
                raise PosDomainError("El estado del menú debe ser 'Activo' o 'Inactivo'.")

            menu_obj.estado = nuevo_estado
            menu_obj.save()

            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Menús y Combos",
                descripcion=f"Cambio de estado de menú '{menu_obj.nombre}' ({menu_obj.codigo}) a '{nuevo_estado}'.",
                ip_origen=ip_origen,
            )
            return {
                "accion": accion,
                "menu_id": menu_obj.id,
                "estado": menu_obj.estado,
                "mensaje": f"Estado de '{menu_obj.nombre}' actualizado a {menu_obj.estado}.",
            }

        menu_id = payload.get("id") or payload.get("menu_id")
        codigo = str(payload.get("codigo") or "").strip().upper()
        nombre = str(payload.get("nombre") or "").strip()
        productos_incluidos = str(payload.get("productos_incluidos") or "").strip()
        precio = _parse_positive_int(payload.get("precio"), "precio del combo")
        ahorro_estimado = _parse_non_negative_int(
            payload.get("ahorro_estimado"), "ahorro estimado", default=0
        )
        disponibilidad = str(payload.get("disponibilidad") or "Todo el día").strip()[:100]
        estado = str(payload.get("estado") or "Activo").strip()

        if not codigo:
            raise PosDomainError("El código del menú/combo es obligatorio.")
        if not nombre:
            raise PosDomainError("El nombre del menú/combo es obligatorio.")
        if not productos_incluidos:
            raise PosDomainError("Debe especificar los productos que componen el menú/combo.")
        if estado not in ("Activo", "Inactivo"):
            raise PosDomainError("El estado del menú debe ser 'Activo' o 'Inactivo'.")

        if accion == "editar" or (menu_id not in (None, "") and str(menu_id).isdigit()):
            if menu_id not in (None, "") and str(menu_id).isdigit():
                menu_obj = MenuCombo.objects.select_for_update().filter(pk=int(menu_id)).first()
            else:
                menu_obj = MenuCombo.objects.select_for_update().filter(codigo__iexact=codigo).first()

            if menu_obj is None:
                raise PosDomainError("El menú o combo que intenta editar no existe.", status_code=404)

            if MenuCombo.objects.exclude(pk=menu_obj.pk).filter(codigo__iexact=codigo).exists():
                raise PosDomainError(f"Ya existe otro menú con el código '{codigo}'.")

            menu_obj.codigo = codigo
            menu_obj.nombre = nombre
            menu_obj.productos_incluidos = productos_incluidos
            menu_obj.precio = precio
            menu_obj.ahorro_estimado = ahorro_estimado
            menu_obj.disponibilidad = disponibilidad
            menu_obj.estado = estado
            menu_obj.save()

            componentes = descomponer_menu_combo(menu_obj, 1)
            LogAuditoria.objects.create(
                usuario=usuario,
                accion="PRODUCTO_MODIFICADO",
                modulo="Menús y Combos",
                descripcion=(
                    f"Edición de menú '{menu_obj.nombre}' ({menu_obj.codigo}): "
                    f"precio={format_clp(precio)}, componentes={len(componentes)}."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "editar",
                "menu_id": menu_obj.id,
                "codigo": menu_obj.codigo,
                "componentes": componentes,
                "mensaje": f"Menú '{menu_obj.nombre}' actualizado exitosamente.",
            }

        if MenuCombo.objects.filter(codigo__iexact=codigo).exists():
            raise PosDomainError(f"Ya existe un menú registrado con el código '{codigo}'.")

        nuevo_menu = MenuCombo(
            codigo=codigo,
            nombre=nombre,
            productos_incluidos=productos_incluidos,
            precio=precio,
            ahorro_estimado=ahorro_estimado,
            categoria="Combos",
            disponibilidad=disponibilidad,
            estado=estado,
        )
        nuevo_menu.save()
        componentes = descomponer_menu_combo(nuevo_menu, 1)

        LogAuditoria.objects.create(
            usuario=usuario,
            accion="PRODUCTO_MODIFICADO",
            modulo="Menús y Combos",
            descripcion=(
                f"Creación de menú '{nuevo_menu.nombre}' ({nuevo_menu.codigo}): "
                f"precio={format_clp(precio)}, componentes={len(componentes)}."
            ),
            ip_origen=ip_origen,
        )
        return {
            "accion": "crear",
            "menu_id": nuevo_menu.id,
            "codigo": nuevo_menu.codigo,
            "componentes": componentes,
            "mensaje": f"Menú '{nuevo_menu.nombre}' creado exitosamente.",
        }


def obtener_usuarios_panel() -> dict:
    """Obtiene desde PostgreSQL el listado real de `Usuario` y `Cargo` para el mantenedor administrativo."""
    usuarios_qs = Usuario.objects.select_related("cargo").order_by("id")
    usuarios_list = []
    for u in usuarios_qs:
        ua_str = (
            timezone.localtime(u.ultimo_acceso).strftime("%d/%m/%Y %H:%M")
            if (u.ultimo_acceso and timezone.is_aware(u.ultimo_acceso))
            else (u.ultimo_acceso.strftime("%d/%m/%Y %H:%M") if u.ultimo_acceso else "Sin accesos registrados")
        )
        usuarios_list.append(
            {
                "id": u.id,
                "nombre": u.nombre,
                "usuario": u.usuario,
                "email": u.email,
                "cargo_id": u.cargo_id,
                "cargo": u.cargo.nombre if u.cargo else u.cargo_id,
                "caja_asignada": u.caja_asignada,
                "estado": u.estado,
                "ultimo_acceso": ua_str,
            }
        )

    cargos_qs = Cargo.objects.annotate(
        activos_count=Count("usuarios", filter=Q(usuarios__estado="Activo"))
    ).order_by("id")
    cargos_list = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "descripcion": c.descripcion or "",
            "nivel": c.nivel,
            "usuarios_asociados": c.activos_count,
        }
        for c in cargos_qs
    ]

    return {
        "usuarios": usuarios_list,
        "cargos": cargos_list,
        "total_usuarios": len(usuarios_list),
        "usuarios_activos": len([u for u in usuarios_list if u["estado"] == "Activo"]),
        "total_cargos": len(cargos_list),
    }


def ejecutar_operacion_usuario_transaccional(
    usuario_admin: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    CRUD transaccional de `Usuario` y `Cargo` (exclusivo Administrador):
    - Impide escalamiento de privilegios por usuarios no administradores.
    - Almacena contraseñas exclusivamente con el hasher PBKDF2-SHA256 de Django (`Usuario.set_password()`).
    - Impide que el administrador en sesión se desactive o degrade su propio rol accidentalmente.
    """
    if usuario_admin is None or usuario_admin.estado != "Activo":
        raise PosDomainError("Sesión de administrador inválida.", status_code=401)
    if str(usuario_admin.cargo_id).lower() not in ("admin", "administrador"):
        raise PosDomainError(
            "Acceso denegado: solo un Administrador autorizado puede gestionar cuentas y privilegios.",
            status_code=403,
        )

    accion = str(payload.get("accion") or "").strip().lower()
    if accion not in ("crear", "editar", "cambiar_estado", "desactivar", "editar_cargo"):
        raise PosDomainError(f"Acción de gestión de usuarios no válida: '{accion}'.")

    with transaction.atomic():
        if accion == "editar_cargo":
            cargo_id = str(payload.get("id") or payload.get("cargo_id") or "").strip().lower()
            nombre_c = str(payload.get("nombre") or "").strip()
            descripcion_c = str(payload.get("descripcion") or "").strip()
            nivel_c = str(payload.get("nivel") or "Operativo").strip()
            if not cargo_id or not nombre_c:
                raise PosDomainError("Debe indicar identificador y nombre del cargo.")
            cargo_obj, _ = Cargo.objects.update_or_create(
                id=cargo_id,
                defaults={
                    "nombre": nombre_c[:50],
                    "descripcion": descripcion_c,
                    "nivel": nivel_c[:50],
                },
            )
            LogAuditoria.objects.create(
                usuario=usuario_admin,
                accion="PRODUCTO_MODIFICADO",
                modulo="Usuarios",
                descripcion=f"Actualización de cargo '{cargo_obj.nombre}' ({cargo_obj.id}).",
                ip_origen=ip_origen,
            )
            return {
                "accion": "editar_cargo",
                "cargo_id": cargo_obj.id,
                "mensaje": f"Cargo '{cargo_obj.nombre}' actualizado exitosamente.",
            }

        if accion in ("cambiar_estado", "desactivar"):
            target_id = payload.get("id") or payload.get("usuario_id")
            username_lookup = str(payload.get("usuario") or "").strip().lower()
            target_user = None
            if target_id not in (None, "") and str(target_id).isdigit():
                target_user = Usuario.objects.select_for_update().filter(pk=int(target_id)).first()
            elif username_lookup:
                target_user = Usuario.objects.select_for_update().filter(usuario=username_lookup).first()

            if target_user is None:
                raise PosDomainError("El usuario especificado no existe.", status_code=404)

            if target_user.pk == usuario_admin.pk:
                raise PosDomainError(
                    "Por seguridad operativa, no puede desactivar su propia cuenta de administrador en sesión.",
                    status_code=400,
                )

            nuevo_estado = str(payload.get("estado") or "").strip()
            if not nuevo_estado:
                nuevo_estado = "Inactivo" if target_user.estado == "Activo" else "Activo"
            if nuevo_estado not in ("Activo", "Inactivo", "Suspendido"):
                raise PosDomainError(f"Estado de usuario no válido: '{nuevo_estado}'.")

            target_user.estado = nuevo_estado
            target_user.save()

            LogAuditoria.objects.create(
                usuario=usuario_admin,
                accion="PRODUCTO_MODIFICADO",
                modulo="Usuarios",
                descripcion=f"Cambio de estado de usuario @{target_user.usuario} a '{nuevo_estado}'.",
                ip_origen=ip_origen,
            )
            return {
                "accion": accion,
                "usuario_id": target_user.id,
                "estado": target_user.estado,
                "mensaje": f"Estado de @{target_user.usuario} actualizado a {target_user.estado}.",
            }

        # accion in ("crear", "editar")
        target_id = payload.get("id") or payload.get("usuario_id")
        nombre = str(payload.get("nombre") or "").strip()
        username = str(payload.get("usuario") or "").strip().lower()
        email = str(payload.get("email") or "").strip().lower()
        cargo_input = str(payload.get("cargo_id") or payload.get("cargo") or "").strip().lower()
        caja_asignada = str(payload.get("caja_asignada") or "Caja 01 - Principal").strip()[:100]
        estado = str(payload.get("estado") or "Activo").strip()
        raw_password = payload.get("password")
        if raw_password is not None:
            raw_password = str(raw_password)

        if not nombre:
            raise PosDomainError("El nombre completo del usuario es obligatorio.")
        if not username or not re.fullmatch(r"[a-z0-9_.\-]+", username):
            raise PosDomainError("El nombre de usuario debe contener solo letras, números, puntos o guiones.")
        if not email or "@" not in email:
            raise PosDomainError("Debe ingresar un correo electrónico válido.")
        if estado not in ("Activo", "Inactivo", "Suspendido"):
            raise PosDomainError("El estado del usuario debe ser 'Activo', 'Inactivo' o 'Suspendido'.")

        cargo_aliases = {
            "administrador": "admin",
            "admin": "admin",
            "cajero": "cajero",
            "vendedor": "garzon",
            "garzon": "garzon",
            "garzón": "garzon",
            "cocina": "cocina",
            "bar": "bar",
        }
        cargo_id_resolved = cargo_aliases.get(cargo_input, cargo_input)
        cargo_obj = Cargo.objects.filter(id=cargo_id_resolved).first()
        if cargo_obj is None:
            cargo_obj = Cargo.objects.filter(nombre__iexact=cargo_input).first()
        if cargo_obj is None:
            raise PosDomainError(f"El cargo '{cargo_input}' no existe en el sistema.")

        if accion == "editar" or (target_id not in (None, "") and str(target_id).isdigit()):
            if target_id not in (None, "") and str(target_id).isdigit():
                target_user = Usuario.objects.select_for_update().filter(pk=int(target_id)).first()
            else:
                target_user = Usuario.objects.select_for_update().filter(usuario=username).first()

            if target_user is None:
                raise PosDomainError("El usuario que intenta editar no existe.", status_code=404)

            if target_user.pk == usuario_admin.pk:
                if estado != "Activo":
                    raise PosDomainError("No puede desactivar su propia cuenta activa.")
                if cargo_obj.id != usuario_admin.cargo_id:
                    raise PosDomainError("No puede quitarse el rol de Administrador a sí mismo.")

            if Usuario.objects.exclude(pk=target_user.pk).filter(usuario__iexact=username).exists():
                raise PosDomainError(f"El nombre de usuario '@{username}' ya está en uso.")
            if Usuario.objects.exclude(pk=target_user.pk).filter(email__iexact=email).exists():
                raise PosDomainError(f"El correo '{email}' ya está registrado por otro usuario.")

            target_user.nombre = nombre[:100]
            target_user.usuario = username[:50]
            target_user.email = email[:120]
            target_user.cargo = cargo_obj
            target_user.caja_asignada = caja_asignada
            target_user.estado = estado

            if raw_password and raw_password.strip():
                if len(raw_password) < 6:
                    raise PosDomainError("La nueva contraseña debe tener al menos 6 caracteres.")
                target_user.set_password(raw_password)

            target_user.full_clean()
            target_user.save()

            LogAuditoria.objects.create(
                usuario=usuario_admin,
                accion="PRODUCTO_MODIFICADO",
                modulo="Usuarios",
                descripcion=(
                    f"Edición de usuario @{target_user.usuario} ({target_user.nombre}): "
                    f"cargo={cargo_obj.nombre}, estado={estado}."
                ),
                ip_origen=ip_origen,
            )
            return {
                "accion": "editar",
                "usuario_id": target_user.id,
                "usuario": target_user.usuario,
                "mensaje": f"Usuario @{target_user.usuario} actualizado exitosamente.",
            }

        if Usuario.objects.filter(usuario__iexact=username).exists():
            raise PosDomainError(f"El nombre de usuario '@{username}' ya existe.")
        if Usuario.objects.filter(email__iexact=email).exists():
            raise PosDomainError(f"El correo '{email}' ya está registrado.")
        if not raw_password or len(raw_password) < 6:
            raise PosDomainError("Debe asignar una contraseña segura de al menos 6 caracteres.")

        nuevo_usuario = Usuario(
            nombre=nombre[:100],
            usuario=username[:50],
            email=email[:120],
            cargo=cargo_obj,
            caja_asignada=caja_asignada,
            estado=estado,
        )
        nuevo_usuario.set_password(raw_password)
        nuevo_usuario.full_clean()
        nuevo_usuario.save()

        LogAuditoria.objects.create(
            usuario=usuario_admin,
            accion="PRODUCTO_MODIFICADO",
            modulo="Usuarios",
            descripcion=(
                f"Creación de usuario @{nuevo_usuario.usuario} ({nuevo_usuario.nombre}) "
                f"con cargo '{cargo_obj.nombre}'."
            ),
            ip_origen=ip_origen,
        )
        return {
            "accion": "crear",
            "usuario_id": nuevo_usuario.id,
            "usuario": nuevo_usuario.usuario,
            "mensaje": f"Usuario @{nuevo_usuario.usuario} creado exitosamente con contraseña cifrada.",
        }


def guardar_configuracion_transaccional(
    usuario: Usuario,
    payload: dict,
    ip_origen: str = None,
) -> dict:
    """
    Valida y persiste en PostgreSQL los parámetros generales de `ConfiguracionPOS`.
    """
    if usuario is None or usuario.estado != "Activo":
        raise PosDomainError("Sesión de usuario inválida.", status_code=401)

    with transaction.atomic():
        cfg = ConfiguracionPOS.objects.select_for_update().first()
        if cfg is None:
            cfg = ConfiguracionPOS()

        nombre_parque = str(payload.get("nombre_parque") or cfg.nombre_parque).strip()
        razon_social = str(payload.get("razon_social") or cfg.razon_social).strip()
        rut = str(payload.get("rut") or cfg.rut).strip()
        direccion = str(payload.get("direccion") or cfg.direccion).strip()
        telefono = str(payload.get("telefono") or cfg.telefono).strip()
        terminal_caja = str(payload.get("terminal_caja") or cfg.terminal_caja).strip()
        impresora_tickets = str(payload.get("impresora_tickets") or cfg.impresora_tickets).strip()
        impresora_cocina = str(payload.get("impresora_cocina") or cfg.impresora_cocina).strip()
        impresora_bar = str(payload.get("impresora_bar") or cfg.impresora_bar).strip()
        resolucion_optimizada = str(
            payload.get("resolucion_optimizada") or cfg.resolucion_optimizada
        ).strip()

        if not nombre_parque:
            raise PosDomainError("El nombre de fantasía del parque no puede estar vacío.")
        if not razon_social:
            raise PosDomainError("La razón social no puede estar vacía.")
        if not rut or len(rut) < 7:
            raise PosDomainError("Debe ingresar un RUT de empresa válido.")

        if "iva_porcentaje" in payload and payload.get("iva_porcentaje") not in (None, ""):
            try:
                iva_dec = Decimal(str(payload.get("iva_porcentaje")).strip())
            except (InvalidOperation, ValueError):
                raise PosDomainError("El porcentaje de IVA debe ser un valor numérico válido.")
            if iva_dec < Decimal("0.00") or iva_dec > Decimal("100.00"):
                raise PosDomainError("El porcentaje de IVA debe estar entre 0% y 100%.")
            cfg.iva_porcentaje = iva_dec

        def _parse_bool(key: str, current_val: bool) -> bool:
            if key not in payload:
                return current_val
            val = payload.get(key)
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in ("true", "1", "yes", "on", "si", "sí")

        cfg.nombre_parque = nombre_parque[:100]
        cfg.razon_social = razon_social[:150]
        cfg.rut = rut[:20]
        cfg.direccion = direccion[:200]
        cfg.telefono = telefono[:50]
        cfg.terminal_caja = terminal_caja[:100]
        cfg.impresora_tickets = impresora_tickets[:100]
        cfg.impresora_cocina = impresora_cocina[:100]
        cfg.impresora_bar = impresora_bar[:100]
        cfg.resolucion_optimizada = resolucion_optimizada[:100]
        cfg.iva_incluido = _parse_bool("iva_incluido", cfg.iva_incluido)
        cfg.modo_offline = _parse_bool("modo_offline", cfg.modo_offline)
        cfg.sonido_comandas = _parse_bool("sonido_comandas", cfg.sonido_comandas)
        cfg.save()

        LogAuditoria.objects.create(
            usuario=usuario,
            accion="PRODUCTO_MODIFICADO",
            modulo="Configuración",
            descripcion=(
                f"Actualización de ConfiguracionPOS por @{usuario.usuario}: "
                f"parque='{cfg.nombre_parque}', terminal='{cfg.terminal_caja}', IVA={cfg.iva_porcentaje}%."
            ),
            ip_origen=ip_origen,
        )

        return {
            "config": obtener_configuracion_dict(),
            "mensaje": "Configuración del sistema guardada exitosamente en PostgreSQL.",
        }


# =============================================================================
# FASE 06 — DASHBOARD, ESTADÍSTICAS Y REPORTES DESDE POSTGRESQL
# =============================================================================
def _calcular_tiempo_promedio_estacion(area_destino: str) -> str:
    """
    Calcula el tiempo promedio real en minutos de las comandas de `area_destino` ('COCINA' o 'BAR')
    a partir de los timestamps de PostgreSQL (`fecha_hora_despacho - fecha_hora_ingreso` para despachadas,
    o tiempo transcurrido en curso si aún no hay despachadas).
    """
    despachadas = list(
        ComandaProduccion.objects.filter(
            area_destino=area_destino,
            fecha_hora_despacho__isnull=False,
        )
        .order_by("-fecha_hora_despacho")[:50]
    )
    if despachadas:
        duraciones = [
            max(1, int((c.fecha_hora_despacho - c.fecha_hora_ingreso).total_seconds() // 60))
            for c in despachadas
            if c.fecha_hora_despacho and c.fecha_hora_ingreso
        ]
        if duraciones:
            prom = round(sum(duraciones) / len(duraciones))
            return f"{prom} min"

    activas = list(
        ComandaProduccion.objects.filter(area_destino=area_destino).exclude(estado="Entregado")
    )
    if activas:
        ahora = timezone.now()
        duraciones = [
            max(1, int((ahora - c.fecha_hora_ingreso).total_seconds() // 60))
            for c in activas
            if c.fecha_hora_ingreso
        ]
        if duraciones:
            prom = round(sum(duraciones) / len(duraciones))
            return f"{prom} min"

    return "0 min"


def obtener_estadisticas_operativas() -> dict:
    """
    Calcula en tiempo real todos los indicadores de Dashboard y Estadísticas desde PostgreSQL
    sin utilizar `mock_data.py`.
    """
    ventas_pagadas_qs = Venta.objects.filter(estado="Pagado")
    agg_pagadas = ventas_pagadas_qs.aggregate(
        total_facturado=Sum("total"),
        subtotal_neto=Sum("subtotal"),
        iva_total=Sum("iva"),
        cantidad_tx=Count("id"),
    )
    total_facturado = int(agg_pagadas["total_facturado"] or 0)
    cantidad_tx = int(agg_pagadas["cantidad_tx"] or 0)
    ticket_promedio_int = round(total_facturado / cantidad_tx) if cantidad_tx > 0 else 0

    ventas_pendientes_qs = Venta.objects.filter(estado="Pendiente")
    agg_pendientes = ventas_pendientes_qs.aggregate(
        total_pendiente=Sum("total"),
        cantidad_pendiente=Count("id"),
    )
    total_pendiente = int(agg_pendientes["total_pendiente"] or 0)
    cantidad_pendiente = int(agg_pendientes["cantidad_pendiente"] or 0)

    total_mesas = Mesa.objects.count()
    mesas_ocupadas = Mesa.objects.filter(estado="Ocupada").count()
    porcentaje_ocupacion = round((mesas_ocupadas / total_mesas) * 100) if total_mesas > 0 else 0

    pedidos_cocina_activos = (
        ComandaProduccion.objects.filter(area_destino="COCINA")
        .exclude(estado__in=["Preparado", "Entregado"])
        .count()
    )
    pedidos_bar_activos = (
        ComandaProduccion.objects.filter(area_destino="BAR")
        .exclude(estado__in=["Listo", "Entregado"])
        .count()
    )
    pedidos_despachados = ComandaProduccion.objects.filter(
        estado__in=["Preparado", "Listo", "Entregado"]
    ).count()

    tiempo_prom_cocina = _calcular_tiempo_promedio_estacion("COCINA")
    tiempo_prom_bar = _calcular_tiempo_promedio_estacion("BAR")

    # Curva horaria real (franjas 10:00 a 18:00 + agrupación de ventas reales)
    franjas = [f"{h:02d}:00" for h in range(10, 19)]
    montos_por_hora = {f: 0 for f in franjas}
    for v in ventas_pagadas_qs.only("fecha_hora", "total"):
        fh_loc = timezone.localtime(v.fecha_hora) if timezone.is_aware(v.fecha_hora) else v.fecha_hora
        clave_h = f"{fh_loc.hour:02d}:00"
        if clave_h not in montos_por_hora:
            montos_por_hora[clave_h] = 0
        montos_por_hora[clave_h] += int(v.total)

    max_hora = max(montos_por_hora.values()) if montos_por_hora else 0
    ventas_por_hora = []
    for hora_k, monto_h in sorted(montos_por_hora.items()):
        pct = max(5, round((monto_h / max_hora) * 100)) if (max_hora > 0 and monto_h > 0) else 0
        ventas_por_hora.append(
            {
                "hora": hora_k,
                "monto": monto_h,
                "monto_formateado": format_clp(monto_h),
                "porcentaje": pct,
            }
        )

    # Ventas por categoría desde DetalleVenta (ventas pagadas y activas)
    detalles_qs = DetalleVenta.objects.select_related(
        "producto", "producto__categoria", "menu", "venta"
    ).exclude(venta__estado="Anulado")

    totales_cat = {}
    ranking_items = {}
    suma_detalles = 0

    for d in detalles_qs:
        sub = int(d.subtotal)
        suma_detalles += sub
        if d.menu_id and d.menu is not None:
            cat_nombre = "Menús y Combos"
            item_key = f"MENU:{d.menu.nombre}"
            item_nombre = d.menu.nombre
        elif d.producto_id and d.producto is not None:
            cat_nombre = d.producto.categoria.nombre if d.producto.categoria else "General"
            item_key = f"PROD:{d.producto.nombre}"
            item_nombre = d.producto.nombre
        else:
            cat_nombre = "General"
            item_key = f"OTRO:{d.nombre_item}"
            item_nombre = d.nombre_item

        totales_cat[cat_nombre] = totales_cat.get(cat_nombre, 0) + sub
        if item_key not in ranking_items:
            ranking_items[item_key] = {"nombre": item_nombre, "cantidad": 0, "ingresos_int": 0}
        ranking_items[item_key]["cantidad"] += int(d.cantidad)
        ranking_items[item_key]["ingresos_int"] += sub

    ventas_por_categoria = []
    for cat_nom, monto_cat in sorted(totales_cat.items(), key=lambda x: x[1], reverse=True):
        pct_cat = round((monto_cat / suma_detalles) * 100) if suma_detalles > 0 else 0
        ventas_por_categoria.append(
            {
                "categoria": cat_nom,
                "total_int": monto_cat,
                "total": format_clp(monto_cat),
                "porcentaje": pct_cat,
            }
        )

    top_sorted = sorted(
        ranking_items.values(),
        key=lambda x: (x["cantidad"], x["ingresos_int"]),
        reverse=True,
    )[:8]
    max_cant = top_sorted[0]["cantidad"] if top_sorted else 0
    top_productos = []
    for item in top_sorted:
        pct_prod = round((item["cantidad"] / max_cant) * 100) if max_cant > 0 else 0
        top_productos.append(
            {
                "nombre": item["nombre"],
                "cantidad": item["cantidad"],
                "ingresos_int": item["ingresos_int"],
                "ingresos": format_clp(item["ingresos_int"]),
                "porcentaje": pct_prod,
            }
        )

    caja_actual = obtener_estado_caja_actual()

    return {
        "total_ventas_dia_int": total_facturado,
        "total_ventas_dia": format_clp(total_facturado),
        "subtotal_neto_dia": format_clp(int(agg_pagadas["subtotal_neto"] or 0)),
        "iva_dia": format_clp(int(agg_pagadas["iva_total"] or 0)),
        "ventas_realizadas": cantidad_tx,
        "ventas_pendientes": cantidad_pendiente,
        "monto_pendiente_mesas": format_clp(total_pendiente),
        "ticket_promedio_int": ticket_promedio_int,
        "ticket_promedio": format_clp(ticket_promedio_int),
        "pedidos_cocina_activos": pedidos_cocina_activos,
        "pedidos_bar_activos": pedidos_bar_activos,
        "pedidos_preparados": pedidos_despachados,
        "tiempo_prom_cocina": tiempo_prom_cocina,
        "tiempo_prom_bar": tiempo_prom_bar,
        "total_mesas_ocupadas": mesas_ocupadas,
        "total_mesas": total_mesas,
        "mesas_ocupadas_ratio": f"{mesas_ocupadas} / {total_mesas}",
        "porcentaje_ocupacion": porcentaje_ocupacion,
        "ventas_por_hora": ventas_por_hora,
        "ventas_por_categoria": ventas_por_categoria,
        "top_productos": top_productos,
        "caja_actual": caja_actual,
    }


def obtener_reporte_operativo(
    tipo_reporte: str = "ventas",
    fecha_desde: str = None,
    fecha_hasta: str = None,
) -> dict:
    """
    Consulta y construye reportes gerenciales dinámicos desde PostgreSQL según período y tipo:
    - `ventas`: Ventas detalladas con subtotal neto, IVA (19%), total cobrado, método de pago y estado.
    - `productos`: Rotación de productos y menús vendidos en el período.
    - `tiempos`: Comandas de Cocina y Bar con tiempos de preparación y estado.
    - `fiados`: Estado de cuentas de colaboradores y movimientos del período.
    - `caja`: Historial de sesiones de caja y arqueos/cuadraturas.
    """
    tipo = (tipo_reporte or "ventas").strip().lower()
    if tipo not in ("ventas", "productos", "tiempos", "fiados", "caja"):
        tipo = "ventas"

    hoy_local = timezone.localdate()
    desde_date = None
    hasta_date = None

    if fecha_desde:
        try:
            desde_date = datetime.strptime(str(fecha_desde).strip(), "%Y-%m-%d").date()
        except ValueError:
            desde_date = None
    if fecha_hasta:
        try:
            hasta_date = datetime.strptime(str(fecha_hasta).strip(), "%Y-%m-%d").date()
        except ValueError:
            hasta_date = None

    ventas_qs = Venta.objects.select_related("mesa", "usuario").order_by("-fecha_hora", "-id")
    if desde_date:
        dt_inicio = timezone.make_aware(datetime.combine(desde_date, time.min))
        ventas_qs = ventas_qs.filter(fecha_hora__gte=dt_inicio)
    if hasta_date:
        dt_fin = timezone.make_aware(datetime.combine(hasta_date, time.max))
        ventas_qs = ventas_qs.filter(fecha_hora__lte=dt_fin)

    ventas_rows = []
    suma_subtotal = 0
    suma_iva = 0
    suma_total_pagado = 0
    suma_total_pendiente = 0

    for v in ventas_qs:
        fh_loc = timezone.localtime(v.fecha_hora) if timezone.is_aware(v.fecha_hora) else v.fecha_hora
        if v.estado == "Pagado":
            suma_subtotal += int(v.subtotal)
            suma_iva += int(v.iva)
            suma_total_pagado += int(v.total)
        elif v.estado == "Pendiente":
            suma_total_pendiente += int(v.total)

        ventas_rows.append(
            {
                "id": v.id,
                "venta_num": v.venta_num,
                "fecha_hora": fh_loc.strftime("%d/%m/%Y %H:%M"),
                "cajero": v.usuario.nombre if v.usuario else "Operador",
                "atencion": v.mesa.numero if (v.modalidad == "MESA" and v.mesa) else v.modalidad,
                "metodo_pago": v.metodo_pago,
                "subtotal_int": v.subtotal,
                "subtotal": format_clp(v.subtotal),
                "iva_int": v.iva,
                "iva": format_clp(v.iva),
                "total_int": v.total,
                "total": format_clp(v.total),
                "estado": v.estado,
                "boleta_emitida": v.boleta_emitida,
            }
        )

    # Rotación de productos en el período filtrado
    detalles_qs = DetalleVenta.objects.select_related("producto", "producto__categoria", "menu", "venta").filter(
        venta__in=ventas_qs.exclude(estado="Anulado")
    )
    rotacion_map = {}
    for d in detalles_qs:
        key = d.nombre_item
        if key not in rotacion_map:
            rotacion_map[key] = {
                "nombre": d.nombre_item,
                "destino": d.destino,
                "cantidad": 0,
                "subtotal_int": 0,
            }
        rotacion_map[key]["cantidad"] += int(d.cantidad)
        rotacion_map[key]["subtotal_int"] += int(d.subtotal)

    productos_rows = [
        {
            **item,
            "subtotal": format_clp(item["subtotal_int"]),
        }
        for item in sorted(rotacion_map.values(), key=lambda x: x["subtotal_int"], reverse=True)
    ]

    # Tiempos de comandas en el período
    comandas_qs = ComandaProduccion.objects.select_related("venta", "venta__mesa", "venta__usuario").filter(
        venta__in=ventas_qs
    ).order_by("-fecha_hora_ingreso", "-id")
    tiempos_rows = []
    ahora = timezone.now()
    for c in comandas_qs:
        fi_loc = (
            timezone.localtime(c.fecha_hora_ingreso)
            if timezone.is_aware(c.fecha_hora_ingreso)
            else c.fecha_hora_ingreso
        )
        fin_ref = c.fecha_hora_despacho or ahora
        mins = max(1, int((fin_ref - c.fecha_hora_ingreso).total_seconds() // 60))
        tiempos_rows.append(
            {
                "codigo_comanda": c.codigo_comanda,
                "venta_num": c.venta.venta_num if c.venta else "-",
                "area": c.area_destino,
                "ubicacion": c.venta.mesa.numero if (c.venta and c.venta.mesa) else (c.venta.modalidad if c.venta else "BAR"),
                "ingreso": fi_loc.strftime("%d/%m/%Y %H:%M"),
                "duracion": f"{mins} min",
                "estado": c.estado,
            }
        )

    fiados_panel = obtener_fiados_panel()
    caja_panel = obtener_estado_caja_actual()

    titulos_map = {
        "ventas": "Reporte de Ventas Diarias y Facturación",
        "productos": "Reporte de Rotación de Productos y Combos",
        "tiempos": "Reporte de Tiempos de Servicio (Cocina KDS y Bar BDS)",
        "fiados": "Reporte de Consumos Fiados por Colaborador",
        "caja": "Reporte de Sesiones de Caja y Cuadraturas",
    }

    return {
        "tipo_reporte": tipo,
        "titulo_reporte": titulos_map[tipo],
        "fecha_desde": desde_date.strftime("%Y-%m-%d") if desde_date else "",
        "fecha_hasta": hasta_date.strftime("%Y-%m-%d") if hasta_date else hoy_local.strftime("%Y-%m-%d"),
        "periodo_label": (
            f"{desde_date.strftime('%d/%m/%Y') if desde_date else 'Inicio histórico'} al "
            f"{hasta_date.strftime('%d/%m/%Y') if hasta_date else hoy_local.strftime('%d/%m/%Y')}"
        ),
        "ventas_rows": ventas_rows,
        "productos_rows": productos_rows,
        "tiempos_rows": tiempos_rows,
        "fiados_rows": fiados_panel["fiados"],
        "cierres_caja_rows": caja_panel["ultimos_cierres"],
        "total_registros": (
            len(ventas_rows)
            if tipo == "ventas"
            else (
                len(productos_rows)
                if tipo == "productos"
                else (
                    len(tiempos_rows)
                    if tipo == "tiempos"
                    else (
                        len(fiados_panel["fiados"])
                        if tipo == "fiados"
                        else len(caja_panel["ultimos_cierres"])
                    )
                )
            )
        ),
        "suma_subtotal": format_clp(suma_subtotal),
        "suma_iva": format_clp(suma_iva),
        "suma_total_pagado_int": suma_total_pagado,
        "suma_total_pagado": format_clp(suma_total_pagado),
        "suma_total_pendiente": format_clp(suma_total_pendiente),
        "deuda_fiados_total": fiados_panel["deuda_total"],
    }

