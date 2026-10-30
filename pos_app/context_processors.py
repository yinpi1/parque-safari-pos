"""
pos_app/context_processors.py
Procesador de contexto centralizado para sincronizar la identidad y permisos
del usuario autenticado en sesión en todas las plantillas del sistema (AUD-008, AUD-010).
"""

from .models import Usuario

ROLE_ALIASES = {
    'admin': 'admin',
    'administrador': 'admin',
    'cajero': 'cajero',
    'garzon': 'garzon',
    'garzón': 'garzon',
    'vendedor': 'garzon',
    'garzon / mesero': 'garzon',
    'garzón / mesero': 'garzon',
    'vendedor / garzon': 'garzon',
    'vendedor / garzón': 'garzon',
    'cocina': 'cocina',
    'cocina (kds)': 'cocina',
    'bar': 'bar',
    'bar (bds)': 'bar',
}

ROLE_PERMISSIONS = {
    'admin': {
        'dashboard', 'pos', 'ticket', 'productos', 'menus', 'mesas',
        'usuarios', 'fiados', 'distribucion', 'cocina', 'bar',
        'estadisticas', 'reportes', 'configuracion', 'caja_operacion',
    },
    'cajero': {
        'dashboard', 'pos', 'ticket', 'mesas', 'distribucion', 'caja_operacion',
    },
    'garzon': {
        'dashboard', 'pos', 'ticket', 'mesas', 'distribucion',
    },
    'cocina': {
        'dashboard', 'cocina', 'distribucion',
    },
    'bar': {
        'dashboard', 'bar', 'distribucion',
    },
}

ROLE_UI_META = {
    'admin': {
        'role_key': 'admin',
        'focus_role': 'admin',
        'focus_desc': 'GESTIÓN TOTAL & REPORTES',
        'avatar_bg': '#8b5cf6',
        'dot_color': '#c084fc',
        'badge_bg': 'rgba(168, 85, 247, 0.2)',
        'badge_color': '#c084fc',
    },
    'cajero': {
        'role_key': 'cajero',
        'focus_role': 'cajero',
        'focus_desc': 'VENTAS POS & CAJA',
        'avatar_bg': '#10b981',
        'dot_color': '#10b981',
        'badge_bg': 'rgba(16, 185, 129, 0.2)',
        'badge_color': '#34d399',
    },
    'garzon': {
        'role_key': 'garzon',
        'focus_role': 'cajero',
        'focus_desc': 'TOMA DE PEDIDOS & MESAS',
        'avatar_bg': '#3b82f6',
        'dot_color': '#60a5fa',
        'badge_bg': 'rgba(59, 130, 246, 0.2)',
        'badge_color': '#60a5fa',
    },
    'cocina': {
        'role_key': 'cocina',
        'focus_role': 'cocina',
        'focus_desc': 'COMANDAS DE PRODUCCIÓN KDS',
        'avatar_bg': '#f97316',
        'dot_color': '#fb923c',
        'badge_bg': 'rgba(249, 115, 22, 0.2)',
        'badge_color': '#fb923c',
    },
    'bar': {
        'role_key': 'bar',
        'focus_role': 'bar',
        'focus_desc': 'DESPACHO DE BARRA BDS',
        'avatar_bg': '#06b6d4',
        'dot_color': '#22d3ee',
        'badge_bg': 'rgba(6, 182, 212, 0.2)',
        'badge_color': '#22d3ee',
    },
}


def normalize_role(value: str) -> str:
    """Normaliza el identificador o nombre de cargo al código canónico de rol."""
    if not value:
        return ''
    cleaned = str(value).strip().lower()
    return ROLE_ALIASES.get(cleaned, cleaned)


def get_user_role(usuario: Usuario) -> str:
    """Obtiene el código de rol canónico de una instancia de Usuario."""
    if not usuario or not getattr(usuario, 'cargo_id', None):
        return ''
    role = normalize_role(usuario.cargo_id)
    if role not in ROLE_PERMISSIONS and getattr(usuario, 'cargo', None):
        role = normalize_role(usuario.cargo.nombre)
    return role


def get_avatar_initials(nombre: str) -> str:
    """Genera las iniciales (2 letras) a partir del nombre completo del usuario."""
    if not nombre or not isinstance(nombre, str):
        return 'US'
    parts = [p for p in nombre.strip().split() if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if len(parts) == 1:
        return parts[0][:2].upper()
    return 'US'


def get_authenticated_user(request):
    """
    Recupera y cachea en `request` el usuario autenticado en sesión activa.
    Retorna `None` si no hay sesión válida o si el usuario no está Activo.
    Nunca asigna `Usuario.objects.first()` ni `mock_data.USUARIOS[0]`.
    """
    if hasattr(request, '_cached_pos_user'):
        return request._cached_pos_user

    user_obj = None
    if hasattr(request, 'session'):
        user_id = request.session.get('usuario_id')
        if user_id:
            try:
                candidate = Usuario.objects.select_related('cargo').get(id=user_id)
                if candidate.estado == 'Activo':
                    user_obj = candidate
            except Exception:
                user_obj = None

    request._cached_pos_user = user_obj
    return user_obj


def pos_auth_context(request):
    """Inyecta en todas las plantillas la identidad real del usuario autenticado, permisos y estado vivo."""
    usuario = get_authenticated_user(request)
    if not usuario:
        return {
            'usuario_actual': None,
            'rol_actual': '',
            'permisos_usuario': set(),
            'avatar_iniciales': '',
            'rol_ui': {},
            'caja_estado': {},
            'nav_mesas_total': 0,
            'nav_cocina_activos': 0,
            'nav_bar_activos': 0,
        }

    rol = get_user_role(usuario)
    permisos = ROLE_PERMISSIONS.get(rol, set())
    ui_meta = ROLE_UI_META.get(rol, ROLE_UI_META['cajero'])

    caja_estado = {}
    nav_mesas_total = 0
    nav_cocina_activos = 0
    nav_bar_activos = 0
    try:
        from .models import ComandaProduccion, Mesa
        from .services import obtener_estado_caja_actual

        if 'caja_operacion' in permisos:
            caja_estado = obtener_estado_caja_actual()
        nav_mesas_total = Mesa.objects.count()
        nav_cocina_activos = (
            ComandaProduccion.objects.filter(area_destino='COCINA')
            .exclude(estado__in=['Preparado', 'Entregado'])
            .count()
        )
        nav_bar_activos = (
            ComandaProduccion.objects.filter(area_destino='BAR')
            .exclude(estado__in=['Listo', 'Entregado'])
            .count()
        )
    except Exception:
        pass

    return {
        'usuario_actual': usuario,
        'rol_actual': rol,
        'permisos_usuario': permisos,
        'avatar_iniciales': get_avatar_initials(usuario.nombre),
        'rol_ui': ui_meta,
        'caja_estado': caja_estado,
        'nav_mesas_total': nav_mesas_total,
        'nav_cocina_activos': nav_cocina_activos,
        'nav_bar_activos': nav_bar_activos,
    }

