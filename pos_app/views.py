"""
pos_app/views.py
Vistas del Sistema POS de Parque Safari.

Implementa:
- Autenticación real contra PostgreSQL con contraseñas con hash PBKDF2-SHA256 (AUD-003).
- Validación estricta de entradas en backend sin alterar contraseñas (AUD-004).
- Prevención de enumeración de usuarios y limitación de intentos respaldada en BD (AUD-005).
- Protección centralizada de vistas privadas sin fallbacks a usuarios por defecto (AUD-002).
- Control de acceso basado en roles (RBAC) en servidor (AUD-008).
- Cierre de sesión real con invalidación de sesión en servidor y cabeceras no-store (AUD-006).
- Sincronización de identidad del usuario autenticado en todas las vistas (AUD-010).
"""

import csv
from datetime import datetime, timedelta
from functools import wraps
import ipaddress
import json
import logging

from django.contrib.auth.hashers import (
    check_password as django_check_password,
    make_password,
)
from django.core.exceptions import ValidationError
from django.db import DatabaseError, OperationalError
from django.db.models import Q
from django.http import HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers

from .context_processors import (
    get_authenticated_user,
    get_user_role,
    normalize_role,
)
from .models import (
    Cargo,
    Categoria,
    ComandaProduccion,
    ConfiguracionPOS,
    CuadraturaCaja,
    DetalleVenta,
    FiadoPersonal,
    LogAuditoria,
    MenuCombo,
    Mesa,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
)
from .services import (
    PosDomainError,
    avanzar_estado_comanda_transaccional,
    ejecutar_operacion_caja_transaccional,
    ejecutar_operacion_fiado_transaccional,
    ejecutar_operacion_menu_transaccional,
    ejecutar_operacion_producto_transaccional,
    ejecutar_operacion_usuario_transaccional,
    format_clp,
    guardar_configuracion_transaccional,
    obtener_catalogo_pos,
    obtener_configuracion_dict,
    obtener_contadores_estacion,
    obtener_estadisticas_operativas,
    obtener_estado_caja_actual,
    obtener_fiados_panel,
    obtener_menus_panel,
    obtener_mesas_salon,
    obtener_pedidos_estacion,
    obtener_productos_panel,
    obtener_reporte_operativo,
    obtener_usuarios_panel,
    obtener_ventas_distribucion,
    operar_mesa_transaccional,
    procesar_venta_transaccional,
    serializar_venta_completa,
)

logger = logging.getLogger(__name__)

# Constantes de seguridad para autenticación (AUD-004, AUD-005)
MAX_USERNAME_LENGTH = 50
MAX_PASSWORD_LENGTH = 128
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_WINDOW = timedelta(minutes=5)
GENERIC_AUTH_ERROR = (
    "Credenciales inválidas o cuenta no autorizada. "
    "Verifique su usuario y contraseña."
)
# Hash señuelo precomputado para mitigar ataques de temporización cuando el usuario no existe
DUMMY_PASSWORD_HASH = make_password(" dummy_timing_mitigation_safari_pos ")


def _get_client_ip(request):
    """
    Obtiene y valida sintácticamente la IP del cliente considerando proxies inversos.
    Retorna `None` si el valor no es una dirección IPv4/IPv6 válida para evitar
    errores `DataError` en columnas `inet` (`GenericIPAddressField`) de PostgreSQL.
    """
    candidates = []
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff and isinstance(xff, str):
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            candidates.append(first_ip)

    remote_addr = request.META.get("REMOTE_ADDR")
    if remote_addr and isinstance(remote_addr, str):
        candidates.append(remote_addr.strip())

    for candidate in candidates:
        try:
            ip_obj = ipaddress.ip_address(candidate)
            return str(ip_obj)
        except ValueError:
            continue
    return None


def _expects_json(request) -> bool:
    """Determina si la petición espera una respuesta JSON (fetch / AJAX)."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = request.headers.get("Accept", "")
    content_type = request.headers.get("Content-Type", "")
    return "application/json" in accept or "application/json" in content_type


def _registrar_auditoria(usuario, accion: str, modulo: str, descripcion: str, ip_origen: str = None):
    """Registra un evento en LogAuditoria sin exponer secretos ni interrumpir el flujo si falla."""
    try:
        LogAuditoria.objects.create(
            usuario=usuario,
            accion=accion,
            modulo=modulo,
            descripcion=descripcion,
            ip_origen=ip_origen,
        )
    except Exception:
        logger.warning("No fue posible registrar evento de auditoría: %s (%s)", accion, modulo)


def _is_login_rate_limited(username_norm: str, client_ip: str) -> bool:
    """
    Verifica en PostgreSQL (LogAuditoria) si el usuario o IP ha superado el límite
    de intentos fallidos dentro de la ventana de bloqueo, compatible con despliegues
    serverless multi-instancia (Vercel).
    Si el usuario tuvo un LOGIN exitoso dentro de la ventana, solo cuenta los fallos
    posteriores a ese último inicio de sesión exitoso.
    """
    window_start = timezone.now() - LOGIN_LOCKOUT_WINDOW
    user_tag = f"[user:{username_norm}]"

    last_success = (
        LogAuditoria.objects.filter(
            accion="LOGIN",
            fecha_hora__gte=window_start,
            descripcion__startswith=user_tag,
        )
        .order_by("-fecha_hora")
        .values_list("fecha_hora", flat=True)
        .first()
    )
    user_since = max(window_start, last_success) if last_success else window_start

    # Contar intentos fallidos recientes para el identificador de usuario
    user_failures = LogAuditoria.objects.filter(
        accion="LOGIN_FALLIDO",
        fecha_hora__gte=user_since,
        descripcion__startswith=user_tag,
    ).count()
    if user_failures >= MAX_LOGIN_ATTEMPTS:
        return True

    # Contar intentos fallidos consecutivos recientes desde la misma dirección IP válida
    if client_ip:
        last_ip_success = (
            LogAuditoria.objects.filter(
                accion="LOGIN",
                fecha_hora__gte=window_start,
                ip_origen=client_ip,
            )
            .order_by("-fecha_hora")
            .values_list("fecha_hora", flat=True)
            .first()
        )
        ip_since = max(window_start, last_ip_success) if last_ip_success else window_start
        ip_failures = LogAuditoria.objects.filter(
            accion="LOGIN_FALLIDO",
            fecha_hora__gte=ip_since,
            ip_origen=client_ip,
        ).count()
        if ip_failures >= MAX_LOGIN_ATTEMPTS * 2:
            return True

    return False


def get_usuario_actual(request):
    """
    Obtiene exclusivamente el usuario autenticado en la sesión activa.
    Retorna `None` si no existe sesión válida o si el usuario no está Activo.
    No utiliza fallbacks a `Usuario.objects.first()` ni a `mock_data.USUARIOS` (AUD-002).
    """
    return get_authenticated_user(request)


def pos_login_required(view_func):
    """
    Decorador centralizado que exige una sesión válida y un usuario activo en BD.
    Redirige a `login` en peticiones de navegador o responde HTTP 401 en peticiones JSON.
    Añade cabeceras `Cache-Control: no-store` para impedir exposición tras logout (AUD-002, AUD-006).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        usuario = get_usuario_actual(request)
        if not usuario:
            if hasattr(request, "session"):
                request.session.flush()
            if _expects_json(request):
                response = JsonResponse(
                    {"ok": False, "error": "Autenticación requerida."},
                    status=401,
                )
            else:
                response = redirect("login")
            add_never_cache_headers(response)
            return response

        response = view_func(request, *args, **kwargs)
        add_never_cache_headers(response)
        return response

    return _wrapped_view


def role_required(*allowed_roles):
    """
    Decorador de autorización basada en roles (RBAC) en el servidor (AUD-008).
    Comprueba que el rol del usuario autenticado esté dentro de `allowed_roles`.
    Si no tiene permiso, registra `ACCESO_DENEGADO` y responde HTTP 403.
    """
    normalized_allowed = {normalize_role(r) for r in allowed_roles if r}

    def decorator(view_func):
        @wraps(view_func)
        @pos_login_required
        def _wrapped_view(request, *args, **kwargs):
            usuario = get_usuario_actual(request)
            user_role = get_user_role(usuario)

            if user_role not in normalized_allowed:
                client_ip = _get_client_ip(request)
                _registrar_auditoria(
                    usuario=usuario,
                    accion="ACCESO_DENEGADO",
                    modulo=request.path,
                    descripcion=(
                        f"Acceso denegado a {request.path} para rol '{user_role}'. "
                        f"Roles permitidos: {sorted(normalized_allowed)}."
                    ),
                    ip_origen=client_ip,
                )
                if _expects_json(request):
                    response = JsonResponse(
                        {
                            "ok": False,
                            "error": "No tiene permisos para acceder a este módulo o realizar esta operación.",
                        },
                        status=403,
                    )
                else:
                    context = {
                        "titulo": "Acceso Restringido | Parque Safari POS",
                        "ruta": request.path,
                        "rol_actual_nombre": usuario.cargo.nombre if getattr(usuario, "cargo", None) else user_role,
                    }
                    response = render(request, "403.html", context, status=403)
                add_never_cache_headers(response)
                return response

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def login_view(request):
    """
    Pantalla de inicio de sesión de Parque Safari POS (AUD-003, AUD-004, AUD-005).
    - Valida tipos, presencia y longitud máxima de `username` y `password`.
    - Normaliza únicamente `username` (`strip().lower()`); conserva `password` intacta.
    - Verifica contraseñas exclusivamente con `check_password()` (sin claves maestras).
    - Falla de forma cerrada (HTTP 503) si PostgreSQL no está disponible.
    - Aplica mensajes genéricos externos y limitación de intentos en base de datos.
    """
    error = None
    status_code = 200

    if request.method == "POST":
        raw_username = request.POST.get("username")
        raw_password = request.POST.get("password")

        if not isinstance(raw_username, str) or not isinstance(raw_password, str):
            error = "Por favor ingrese usuario y contraseña válidos."
            status_code = 400
        else:
            # Normalizar únicamente el identificador de usuario; NUNCA aplicar .strip() a la contraseña
            username_input = raw_username.strip().lower()
            password_input = raw_password

            if not username_input or not password_input:
                error = "Por favor ingrese usuario y contraseña."
                status_code = 400
            elif (
                len(username_input) > MAX_USERNAME_LENGTH
                or len(password_input) > MAX_PASSWORD_LENGTH
                or "\x00" in username_input
                or "\x00" in password_input
            ):
                error = (
                    f"Las credenciales exceden la longitud máxima permitida "
                    f"(usuario máx. {MAX_USERNAME_LENGTH}, contraseña máx. {MAX_PASSWORD_LENGTH} caracteres)."
                )
                status_code = 400
            else:
                client_ip = _get_client_ip(request)
                try:
                    if _is_login_rate_limited(username_input, client_ip):
                        error = (
                            "Demasiados intentos fallidos de inicio de sesión. "
                            "Por seguridad, espere 5 minutos antes de volver a intentar."
                        )
                        status_code = 429
                    else:
                        try:
                            usuario_db = Usuario.objects.select_related("cargo").get(
                                usuario__iexact=username_input
                            )
                        except Usuario.DoesNotExist:
                            usuario_db = None

                        if usuario_db is None:
                            # Mitigación de enumeración por tiempo de respuesta
                            django_check_password(password_input, DUMMY_PASSWORD_HASH)
                            _registrar_auditoria(
                                usuario=None,
                                accion="LOGIN_FALLIDO",
                                modulo="Autenticación",
                                descripcion=f"[user:{username_input}] Intento de login con usuario inexistente.",
                                ip_origen=client_ip,
                            )
                            error = GENERIC_AUTH_ERROR
                        elif not usuario_db.check_password(password_input):
                            _registrar_auditoria(
                                usuario=usuario_db,
                                accion="LOGIN_FALLIDO",
                                modulo="Autenticación",
                                descripcion=f"[user:{username_input}] Contraseña inválida.",
                                ip_origen=client_ip,
                            )
                            error = GENERIC_AUTH_ERROR
                        elif usuario_db.estado != "Activo":
                            _registrar_auditoria(
                                usuario=usuario_db,
                                accion="LOGIN_FALLIDO",
                                modulo="Autenticación",
                                descripcion=(
                                    f"[user:{username_input}] Intento de acceso a cuenta en estado {usuario_db.estado}."
                                ),
                                ip_origen=client_ip,
                            )
                            error = GENERIC_AUTH_ERROR
                        else:
                            # Rotar identificador de sesión para prevenir fijación de sesión
                            request.session.cycle_key()
                            request.session["usuario_id"] = usuario_db.id
                            request.session["usuario_nombre"] = usuario_db.nombre
                            request.session["usuario_username"] = usuario_db.usuario
                            request.session["cargo_id"] = usuario_db.cargo.id
                            request.session["cargo_nombre"] = usuario_db.cargo.nombre

                            usuario_db.ultimo_acceso = timezone.now()
                            usuario_db.save(update_fields=["ultimo_acceso"])

                            _registrar_auditoria(
                                usuario=usuario_db,
                                accion="LOGIN",
                                modulo="Autenticación",
                                descripcion=(
                                    f"[user:{usuario_db.usuario}] Inicio de sesión exitoso "
                                    f"con rol {usuario_db.cargo.nombre}."
                                ),
                                ip_origen=client_ip,
                            )
                            return redirect("dashboard")

                except (OperationalError, DatabaseError):
                    # Fallo cerrado (Fail-Closed): nunca autenticar con mock_data si PostgreSQL cae
                    logger.error("Error de conexión a PostgreSQL durante el inicio de sesión.")
                    error = (
                        "El servicio de autenticación no está disponible temporalmente. "
                        "Por seguridad no se permite el acceso sin verificación en base de datos."
                    )
                    status_code = 503

    if error and request.method == "POST" and hasattr(request, "session"):
        # Asegurar que un intento fallido de login en un terminal compartido no conserve
        # una sesión previa activa en el mismo navegador
        request.session.flush()
        request._cached_pos_user = None

    nombre_parque = "Parque Safari Chile"
    try:
        config_db = ConfiguracionPOS.objects.first()
        if config_db and config_db.nombre_parque:
            nombre_parque = config_db.nombre_parque
    except (OperationalError, DatabaseError):
        pass

    context = {
        "titulo": "Iniciar Sesión | Parque Safari POS",
        "parque": nombre_parque,
        "error": error,
    }
    response = render(request, "login.html", context, status=status_code)
    add_never_cache_headers(response)
    return response


def logout_view(request):
    """
    Endpoint real de cierre de sesión (AUD-006).
    Acepta únicamente peticiones POST protegidas por CSRF, registra el evento
    `LOGOUT` en `LogAuditoria`, invalida completamente la sesión en el servidor
    y redirige al formulario de inicio de sesión.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    if usuario:
        _registrar_auditoria(
            usuario=usuario,
            accion="LOGOUT",
            modulo="Autenticación",
            descripcion=f"[user:{usuario.usuario}] Cierre de sesión ejecutado por el usuario.",
            ip_origen=_get_client_ip(request),
        )

    request.session.flush()
    request._cached_pos_user = None

    response = redirect("login")
    add_never_cache_headers(response)
    return response


@role_required("admin", "cajero")
def caja_operacion_view(request):
    """
    Endpoint protegido en servidor para consulta (`GET`) y ejecución transaccional (`POST`)
    de Apertura y Cierre/Cuadratura de Caja en PostgreSQL (Fase 04).
    Exige rol `admin` o `cajero`.
    """
    if request.method == "GET":
        try:
            return JsonResponse({"ok": True, "caja": obtener_estado_caja_actual()})
        except (OperationalError, DatabaseError):
            return JsonResponse(
                {"ok": False, "error": "Base de datos temporalmente no disponible."},
                status=503,
            )

    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    usuario = get_usuario_actual(request)
    try:
        if request.content_type and "application/json" in request.content_type:
            payload = json.loads(request.body.decode("utf-8") if request.body else "{}")
        else:
            payload = request.POST.dict()
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo de la solicitud no contiene un JSON válido."},
            status=400,
        )

    try:
        resultado = ejecutar_operacion_caja_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse(
            {"ok": False, "error": exc.message, "code": exc.code},
            status=exc.status_code,
        )
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos durante operación de caja.")
        return JsonResponse(
            {
                "ok": False,
                "error": "No fue posible registrar la operación de caja en la base de datos. Ningún cambio fue aplicado.",
            },
            status=503,
        )


@role_required("admin", "cajero", "garzon", "cocina", "bar")
def dashboard_view(request):
    """Panel principal con indicadores clave calculados en tiempo real desde PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    mesas_salon = obtener_mesas_salon()
    config_dict = obtener_configuracion_dict()
    stats = obtener_estadisticas_operativas()

    context = {
        "titulo": "Panel Principal | Parque Safari",
        "usuario_actual": usuario_sesion,
        "estadisticas": stats,
        "mesas": mesas_salon,
        "config": config_dict,
        "fecha_actual": datetime.now().strftime("%d/%m/%Y"),
        "pedidos_cocina_activos": stats["pedidos_cocina_activos"],
        "pedidos_bar_activos": stats["pedidos_bar_activos"],
        "total_mesas_ocupadas": stats["total_mesas_ocupadas"],
        "total_mesas": stats["total_mesas"],
        "porcentaje_ocupacion": stats["porcentaje_ocupacion"],
    }
    return render(request, "dashboard.html", context)


@role_required("admin", "cajero", "garzon")
def pos_view(request):
    """Interfaz principal del Punto de Venta (POS) táctil conectada al catálogo y mesas de PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    catalogo = obtener_catalogo_pos()
    mesas_salon = obtener_mesas_salon()
    config_dict = obtener_configuracion_dict()

    mesa_preseleccionada = (request.GET.get("mesa") or "").strip()
    modo_mesa_inicial = (request.GET.get("modo") or "nueva").strip().lower()
    if modo_mesa_inicial not in ("nueva", "agregar"):
        modo_mesa_inicial = "nueva"

    context = {
        "titulo": "Punto de Venta | Parque Safari",
        "usuario_actual": usuario_sesion,
        "categorias": catalogo["categorias"],
        "productos": catalogo["productos"],
        "menus": catalogo["menus"],
        "fiados": catalogo.get("fiados", []),
        "mesas": mesas_salon,
        "config": config_dict,
        "mesa_preseleccionada": mesa_preseleccionada,
        "modo_mesa_inicial": modo_mesa_inicial,
    }
    return render(request, "pos.html", context)


@role_required("admin", "cajero", "garzon")
def procesar_venta_view(request):
    """
    Endpoint transaccional de servidor para procesar el carrito del POS (`POST /pos/procesar-venta/`).
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        if request.content_type and "application/json" in request.content_type:
            raw_body = request.body.decode("utf-8") if request.body else "{}"
            payload = json.loads(raw_body)
        else:
            payload = json.loads(request.POST.get("payload") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo de la solicitud no contiene un JSON válido."},
            status=400,
        )

    try:
        venta_data, is_replay = procesar_venta_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        venta_data["ticket_url"] = f"{reverse('ticket')}?venta_num={venta_data['venta_num']}"
        return JsonResponse(
            {
                "ok": True,
                "idempotent_replay": is_replay,
                "venta": venta_data,
                "mensaje": (
                    f"Operación #{venta_data['venta_num']} ya se encontraba registrada."
                    if is_replay
                    else f"Venta #{venta_data['venta_num']} procesada y persistida exitosamente."
                ),
            },
            status=200 if is_replay else 201,
        )
    except PosDomainError as exc:
        return JsonResponse(
            {"ok": False, "error": exc.message, "code": exc.code},
            status=exc.status_code,
        )
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse(
            {"ok": False, "error": f"Error de validación de datos: {msg}"},
            status=400,
        )
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos al procesar venta en POS.")
        return JsonResponse(
            {
                "ok": False,
                "error": "No fue posible registrar la operación en la base de datos. Ningún cargo fue aplicado.",
            },
            status=503,
        )


@role_required("admin", "cajero", "garzon")
def ticket_view(request):
    """
    Módulo de Tickets y Comandas Térmicas (`GET /ticket/`).
    Muestra la venta real persistida en PostgreSQL.
    """
    usuario_sesion = get_usuario_actual(request)
    config_dict = obtener_configuracion_dict()

    venta_id_param = (request.GET.get("venta_id") or "").strip()
    venta_num_param = (request.GET.get("venta_num") or "").strip()

    venta_obj = None
    qs = Venta.objects.select_related("mesa", "usuario").prefetch_related("detalles", "detalles__menu", "comandas")
    if venta_id_param.isdigit():
        venta_obj = qs.filter(pk=int(venta_id_param)).first()
    elif venta_num_param:
        venta_obj = qs.filter(venta_num__iexact=venta_num_param).first()

    if venta_obj is None:
        venta_obj = qs.order_by("-fecha_hora", "-id").first()

    ventas_recientes = list(qs.order_by("-fecha_hora", "-id")[:12])

    if venta_obj is not None:
        venta_serial = serializar_venta_completa(venta_obj)
    else:
        venta_serial = None

    context = {
        "titulo": "Ticket y Comandas | Parque Safari",
        "usuario_actual": usuario_sesion,
        "venta": venta_serial,
        "ventas_recientes": ventas_recientes,
        "config": config_dict,
        "fecha_actual": datetime.now().strftime("%d/%m/%Y"),
        "hora_actual": datetime.now().strftime("%H:%M:%S"),
    }
    return render(request, "ticket.html", context)


def _parse_request_payload(request) -> dict:
    """Extrae y valida payload JSON o form-urlencoded de una petición POST."""
    if request.content_type and "application/json" in request.content_type:
        raw_body = request.body.decode("utf-8") if request.body else "{}"
        return json.loads(raw_body)
    return request.POST.dict()


@role_required("admin")
def productos_view(request):
    """Módulo de gestión y catálogo de productos conectado a PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    panel = obtener_productos_panel()
    context = {
        "titulo": "Catálogo de Productos | Parque Safari",
        "usuario_actual": usuario_sesion,
        **panel,
    }
    return render(request, "productos.html", context)


@role_required("admin")
def producto_operacion_view(request):
    """Endpoint CRUD de Productos y Categorías en PostgreSQL (`POST /productos/operacion/`)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = ejecutar_operacion_producto_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message, "code": exc.code}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos en mantenedor de productos.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible. Ningún cambio fue aplicado."},
            status=503,
        )


@role_required("admin")
def menus_view(request):
    """Módulo de Menús y Combos promocionales conectado a PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    panel = obtener_menus_panel()
    context = {
        "titulo": "Gestión de Menús y Combos | Parque Safari",
        "usuario_actual": usuario_sesion,
        **panel,
    }
    return render(request, "menus.html", context)


@role_required("admin")
def menu_operacion_view(request):
    """Endpoint CRUD de Menús y Combos en PostgreSQL (`POST /menus/operacion/`)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = ejecutar_operacion_menu_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message, "code": exc.code}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos en mantenedor de menús.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible. Ningún cambio fue aplicado."},
            status=503,
        )


@role_required("admin", "cajero", "garzon")
def mesas_view(request):
    """Módulo visual de mapa y gestión de mesas sincronizado con PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    mesas_list = obtener_mesas_salon()
    ocupadas = [m for m in mesas_list if m["estado"] == "Ocupada"]
    disponibles = [m for m in mesas_list if m["estado"] == "Disponible"]
    context = {
        "titulo": "Mapa de Mesas | Parque Safari",
        "usuario_actual": usuario_sesion,
        "mesas": mesas_list,
        "mesas_libres": disponibles,
        "total_mesas": len(mesas_list),
        "mesas_ocupadas": len(ocupadas),
        "mesas_disponibles": len(disponibles),
        "total_comensales": sum([m.get("comensales", 0) for m in ocupadas]),
    }
    return render(request, "mesas.html", context)


@role_required("admin", "cajero", "garzon")
def mesa_operacion_view(request):
    """
    Endpoint transaccional (`POST /mesas/operacion/`) para reasignar una mesa ocupada
    a una mesa libre o liberar/cerrar la cuenta de una mesa en PostgreSQL.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = operar_mesa_transaccional(
            usuario=usuario,
            accion=payload.get("accion"),
            mesa_origen_num=payload.get("mesa_origen"),
            mesa_destino_num=payload.get("mesa_destino"),
            metodo_pago=payload.get("metodo_pago") or "Efectivo",
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos en operación de mesa.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible."},
            status=503,
        )


@role_required("admin")
def usuarios_view(request):
    """Módulo de gestión de usuarios y cargos conectado a PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    panel = obtener_usuarios_panel()
    context = {
        "titulo": "Usuarios y Cargos | Parque Safari",
        "usuario_actual": usuario_sesion,
        **panel,
    }
    return render(request, "usuarios.html", context)


@role_required("admin")
def usuario_operacion_view(request):
    """Endpoint CRUD de Usuarios y Cargos en PostgreSQL (`POST /usuarios/operacion/`)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = ejecutar_operacion_usuario_transaccional(
            usuario_admin=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message, "code": exc.code}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos en mantenedor de usuarios.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible. Ningún cambio fue aplicado."},
            status=503,
        )


@role_required("admin")
def fiados_view(request):
    """Módulo de fiados y consumos internos de colaboradores conectado a PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    panel = obtener_fiados_panel()
    catalogo = obtener_catalogo_pos()
    context = {
        "titulo": "Consumos Fiados de Colaboradores | Parque Safari",
        "usuario_actual": usuario_sesion,
        "productos_activos": catalogo["productos"],
        "menus_activos": catalogo["menus"],
        **panel,
    }
    return render(request, "fiados.html", context)


@role_required("admin")
def fiado_operacion_view(request):
    """Endpoint transaccional de gestión de cuentas y movimientos de Fiado (`POST /fiados/operacion/`)."""
    if request.method == "GET":
        try:
            return JsonResponse({"ok": True, "panel": obtener_fiados_panel()})
        except (OperationalError, DatabaseError):
            return JsonResponse({"ok": False, "error": "Base de datos no disponible."}, status=503)

    if request.method != "POST":
        return HttpResponseNotAllowed(["GET", "POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = ejecutar_operacion_fiado_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message, "code": exc.code}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos en operación de fiado.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible. Ningún cambio fue aplicado."},
            status=503,
        )


@role_required("admin", "cajero", "garzon", "cocina", "bar")
def distribucion_view(request):
    """Módulo de visualización de enrutamiento y distribución de ventas a Cocina y Bar desde PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    distribucion_list = obtener_ventas_distribucion()
    cocina_list = obtener_pedidos_estacion("COCINA")
    bar_list = obtener_pedidos_estacion("BAR")
    context = {
        "titulo": "Distribución de Ventas | Parque Safari",
        "usuario_actual": usuario_sesion,
        "distribucion": distribucion_list,
        "cocina_pedidos": cocina_list,
        "bar_pedidos": bar_list,
    }
    return render(request, "distribucion.html", context)


@role_required("admin", "cocina")
def cocina_view(request):
    """Módulo KDS de Cocina: comandas y estados de preparación persistidos en PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    pedidos_cocina = obtener_pedidos_estacion("COCINA")
    contadores = obtener_contadores_estacion("COCINA")
    stats = obtener_estadisticas_operativas()
    context = {
        "titulo": "Cocina KDS | Parque Safari",
        "usuario_actual": usuario_sesion,
        "pedidos": pedidos_cocina,
        "total_pendientes": contadores["pendientes"],
        "total_en_prep": contadores["en_preparacion"],
        "total_preparados": contadores["listos"],
        "total_atrasados": contadores["atrasados"],
        "tiempo_promedio": stats["tiempo_prom_cocina"],
    }
    return render(request, "cocina.html", context)


@role_required("admin", "bar")
def bar_view(request):
    """Módulo BDS de Bar: comandas de líquidos y barra persistidas en PostgreSQL."""
    usuario_sesion = get_usuario_actual(request)
    pedidos_bar = obtener_pedidos_estacion("BAR")
    contadores = obtener_contadores_estacion("BAR")
    stats = obtener_estadisticas_operativas()
    context = {
        "titulo": "Bar BDS | Parque Safari",
        "usuario_actual": usuario_sesion,
        "pedidos": pedidos_bar,
        "total_pendientes": contadores["pendientes"],
        "total_en_prep": contadores["en_preparacion"],
        "total_listos": contadores["listos"],
        "total_atrasados": contadores["atrasados"],
        "tiempo_promedio": stats["tiempo_prom_bar"],
    }
    return render(request, "bar.html", context)


@role_required("admin", "cocina", "bar", "garzon", "cajero")
def actualizar_estado_comanda_view(request):
    """
    Endpoint transaccional (`POST /comandas/estado/`) para avanzar el estado de una comanda
    en Cocina KDS o Bar BDS y sincronizar DetalleVenta en PostgreSQL.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    user_role = get_user_role(usuario)

    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Formato JSON inválido."}, status=400)

    try:
        resultado = avanzar_estado_comanda_transaccional(
            usuario=usuario,
            user_role=user_role,
            codigo_comanda=payload.get("codigo_comanda"),
            accion=payload.get("accion"),
            nuevo_estado=payload.get("nuevo_estado"),
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos al actualizar estado de comanda.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible."},
            status=503,
        )


@role_required("admin")
def estadisticas_view(request):
    """Módulo de Estadísticas y gráficos visuales calculados desde PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    stats = obtener_estadisticas_operativas()
    context = {
        "titulo": "Estadísticas de Operación | Parque Safari",
        "usuario_actual": usuario_sesion,
        "stats": stats,
    }
    return render(request, "estadisticas.html", context)


@role_required("admin")
def reportes_view(request):
    """Módulo de Reportes con filtros de fecha/tipo y exportación CSV desde PostgreSQL (exclusivo Administrador)."""
    usuario_sesion = get_usuario_actual(request)
    tipo = (request.GET.get("tipo") or "ventas").strip().lower()
    fecha_desde = (request.GET.get("desde") or "").strip()
    fecha_hasta = (request.GET.get("hasta") or "").strip()
    formato = (request.GET.get("formato") or "").strip().lower()

    reporte = obtener_reporte_operativo(
        tipo_reporte=tipo,
        fecha_desde=fecha_desde or None,
        fecha_hasta=fecha_hasta or None,
    )

    if formato == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="reporte_{reporte["tipo_reporte"]}_safari.csv"'
        response.write("\ufeff")
        writer = csv.writer(response, delimiter=";")

        if reporte["tipo_reporte"] == "ventas":
            writer.writerow(["Fecha y Hora", "N Venta", "Operador", "Atencion", "Metodo Pago", "Subtotal Neto", "IVA 19%", "Total", "Estado"])
            for r in reporte["ventas_rows"]:
                writer.writerow([r["fecha_hora"], f"#{r['venta_num']}", r["cajero"], r["atencion"], r["metodo_pago"], r["subtotal_int"], r["iva_int"], r["total_int"], r["estado"]])
        elif reporte["tipo_reporte"] == "productos":
            writer.writerow(["Producto / Menu", "Estacion Destino", "Unidades Vendidas", "Total Facturado CLP"])
            for r in reporte["productos_rows"]:
                writer.writerow([r["nombre"], r["destino"], r["cantidad"], r["subtotal_int"]])
        elif reporte["tipo_reporte"] == "tiempos":
            writer.writerow(["Comanda", "Venta", "Estacion", "Ubicacion", "Hora Ingreso", "Duracion", "Estado"])
            for r in reporte["tiempos_rows"]:
                writer.writerow([r["codigo_comanda"], f"#{r['venta_num']}", r["area"], r["ubicacion"], r["ingreso"], r["duracion"], r["estado"]])
        elif reporte["tipo_reporte"] == "fiados":
            writer.writerow(["Colaborador", "RUT", "Area", "Limite Credito", "Total Acumulado", "Consumos Mes", "Estado"])
            for r in reporte["fiados_rows"]:
                writer.writerow([r["trabajador"], r["rut"], r["cargo_grupo"], r["limite_credito"], r["total_acumulado"], r["consumos_mes"], r["estado"]])
        else:
            writer.writerow(["Sesion ID", "Cajero", "Terminal", "Fecha Cierre", "Fondo Inicial", "Esperado", "Contado", "Diferencia"])
            for r in reporte["cierres_caja_rows"]:
                writer.writerow([r["id"], r["cajero"], r["terminal"], r["fecha_cierre"], r["monto_apertura"], r["esperado"], r["contado"], r["diferencia"]])
        return response

    stats = obtener_estadisticas_operativas()
    context = {
        "titulo": "Centro de Reportes | Parque Safari",
        "usuario_actual": usuario_sesion,
        "stats": stats,
        "reporte": reporte,
    }
    return render(request, "reportes.html", context)


@role_required("admin")
def configuracion_view(request):
    """Módulo de Configuración general del sistema POS conectado a `ConfiguracionPOS` en PostgreSQL."""
    from django.db import connection

    usuario_sesion = get_usuario_actual(request)
    db_engine = connection.vendor

    estado_bd = "Conectado"
    detalles_bd = (
        "PostgreSQL Cloud (Conexión TLS verificada)"
        if db_engine == "postgresql"
        else f"Motor local ({db_engine.upper()})"
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
    except Exception:
        estado_bd = "Error de conexión"
        detalles_bd = "No fue posible verificar la conexión con el motor de base de datos."

    context = {
        "titulo": "Configuración del Sistema | Parque Safari",
        "usuario_actual": usuario_sesion,
        "config": obtener_configuracion_dict(),
        "db_estado": estado_bd,
        "db_engine": db_engine,
        "db_detalles": detalles_bd,
    }
    return render(request, "configuracion.html", context)


@role_required("admin")
def configuracion_operacion_view(request):
    """Endpoint para persistir cambios reales en `ConfiguracionPOS` (`POST /configuracion/operacion/`)."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    usuario = get_usuario_actual(request)
    try:
        payload = _parse_request_payload(request)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Solicitud JSON inválida."}, status=400)

    try:
        resultado = guardar_configuracion_transaccional(
            usuario=usuario,
            payload=payload,
            ip_origen=_get_client_ip(request),
        )
        return JsonResponse({"ok": True, **resultado})
    except PosDomainError as exc:
        return JsonResponse({"ok": False, "error": exc.message, "code": exc.code}, status=exc.status_code)
    except ValidationError as exc:
        msg = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return JsonResponse({"ok": False, "error": msg}, status=400)
    except (OperationalError, DatabaseError):
        logger.exception("Error de base de datos al guardar configuración.")
        return JsonResponse(
            {"ok": False, "error": "Servicio de base de datos no disponible. Ningún cambio fue aplicado."},
            status=503,
        )


def custom_page_not_found_view(request, exception=None, ruta=None, **kwargs):
    """Vista personalizada institucional para manejar rutas inexistentes con código HTTP 404."""
    from django.conf import settings
    from django.urls import Resolver404, resolve

    # Conservar redirección APPEND_SLASH cuando existe una ruta válida terminada en '/'
    if getattr(settings, "APPEND_SLASH", True) and not request.path.endswith("/"):
        candidate_path = f"{request.path}/"
        try:
            match = resolve(candidate_path)
            if match.func is not custom_page_not_found_view:
                query = request.META.get("QUERY_STRING", "")
                target = f"{candidate_path}?{query}" if query else candidate_path
                return redirect(target)
        except Resolver404:
            pass

    ruta_limpia = (request.path or "").lstrip("/")[:120]
    context = {
        "titulo": "Página no encontrada | Parque Safari POS",
        "ruta": ruta_limpia,
    }
    response = render(request, "404.html", context, status=404)
    add_never_cache_headers(response)
    return response


def custom_server_error_view(request):
    """Vista personalizada institucional para errores internos con código HTTP 500 sin exponer trazas."""
    context = {
        "titulo": "Error del Servidor | Parque Safari POS",
    }
    response = render(request, "500.html", context, status=500)
    add_never_cache_headers(response)
    return response

