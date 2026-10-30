"""
pos_app/models.py
Modelos ORM de Django para el Sistema Web POS — Parque Safari.
Mapea la base de datos relacional PostgreSQL (Neon) y añade el soporte de:
- Gestión de Usuarios y Roles con control de acceso y contraseñas PBKDF2-SHA256 (Fase 01)
- Mantenedores de Mesas, Productos, Categorías y Menús con integridad en servidor y BD (Fase 02)
- Historial de Auditoría
- Inicio/Cierre de jornada, Apertura/Cierre de caja y Cuadratura
- Ventas en Barra vs Ventas en Mesa con comandas de Cocina y Bar
"""

from decimal import Decimal

from django.contrib.auth.hashers import (
    check_password as django_check_password,
    identify_hasher,
    make_password,
)
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def is_password_hashed(value: str) -> bool:
    """
    Comprueba de forma estricta e idempotente si una cadena es un hash válido
    generado por los hashers de Django (ej. pbkdf2_sha256$iteraciones$salt$hash).
    Rechaza texto plano aunque comience con el nombre de un algoritmo.
    """
    if not value or not isinstance(value, str):
        return False
    if value.count('$') < 3 or len(value) < 40:
        return False
    try:
        hasher = identify_hasher(value)
        summary = hasher.safe_summary(value)
        return bool(summary)
    except (ValueError, IndexError, TypeError):
        return False


# =============================================================================
# 1. CARGOS Y ROLES DE ACCESO
# =============================================================================
class Cargo(models.Model):
    id = models.CharField(max_length=20, primary_key=True)
    nombre = models.CharField(max_length=50)
    descripcion = models.TextField(blank=True, null=True)
    nivel = models.CharField(max_length=50, help_text="Nivel jerárquico o categoría de permiso")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'cargos'
        verbose_name = 'Cargo / Rol'
        verbose_name_plural = 'Cargos y Roles'

    def __str__(self):
        return self.nombre


# =============================================================================
# 2. USUARIOS / COLABORADORES
# =============================================================================
class Usuario(models.Model):
    ESTADOS = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
        ('Suspendido', 'Suspendido'),
    ]

    nombre = models.CharField(max_length=100)
    usuario = models.CharField(max_length=50, unique=True)
    email = models.EmailField(max_length=120, unique=True)
    password = models.CharField(max_length=255)
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='usuarios')
    caja_asignada = models.CharField(max_length=100, default='Sin asignar')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    ultimo_acceso = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario del Sistema'
        verbose_name_plural = 'Usuarios del Sistema'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=['Activo', 'Inactivo', 'Suspendido']),
                name='chk_usuario_estado_valido',
            ),
        ]

    def set_password(self, raw_password: str) -> None:
        """Almacena la contraseña aplicando el algoritmo PBKDF2-SHA256 de Django."""
        if not isinstance(raw_password, str) or not raw_password:
            raise ValueError("La contraseña no puede estar vacía.")
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        """Verifica la contraseña contra el hash almacenado usando comparación en tiempo constante."""
        if not isinstance(raw_password, str) or not raw_password:
            return False
        if not is_password_hashed(self.password):
            return False
        return django_check_password(raw_password, self.password)

    def save(self, *args, **kwargs):
        if self.usuario:
            self.usuario = self.usuario.strip().lower()
        if not self.password or not isinstance(self.password, str):
            raise ValueError("El usuario debe tener una contraseña válida antes de guardarse.")
        if not is_password_hashed(self.password):
            self.password = make_password(self.password)
            if kwargs.get('update_fields') is not None:
                update_fields = set(kwargs['update_fields'])
                update_fields.add('password')
                kwargs['update_fields'] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre} (@{self.usuario}) - {self.cargo.nombre}"


# =============================================================================
# 3. CATEGORÍAS DE PRODUCTOS
# =============================================================================
class Categoria(models.Model):
    id = models.CharField(max_length=30, primary_key=True)
    nombre = models.CharField(max_length=100)
    icono = models.CharField(max_length=50, default='bi-grid-fill')
    color = models.CharField(max_length=30, default='primary')
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = 'categorias'
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre


# =============================================================================
# 4. PRODUCTOS
# =============================================================================
class Producto(models.Model):
    DESTINOS = [
        ('Cocina', 'Cocina (KDS)'),
        ('Bar', 'Bar (BDS)'),
        ('Directo', 'Directo / Entrega Inmediata'),
    ]
    TIPOS = [
        ('Requiere preparación', 'Requiere preparación'),
        ('Producto listo', 'Producto listo'),
    ]
    ESTADOS = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
        ('Agotado', 'Agotado'),
    ]

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='productos')
    precio = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Precio en pesos chilenos (CLP), estrictamente mayor a 0",
    )
    tipo = models.CharField(max_length=50, choices=TIPOS, default='Producto listo')
    destino = models.CharField(max_length=30, choices=DESTINOS, default='Directo')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    badge_tipo = models.CharField(max_length=30, default='badge-listo')
    descripcion = models.TextField(blank=True, null=True)
    icono = models.CharField(max_length=50, default='bi-box2-heart')
    imagen_placeholder = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'productos'
        verbose_name = 'Producto'
        verbose_name_plural = 'Productos'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio__gt=0),
                name='chk_producto_precio_positivo',
            ),
            models.CheckConstraint(
                condition=models.Q(tipo__in=['Requiere preparación', 'Producto listo']),
                name='chk_producto_tipo_valido',
            ),
            models.CheckConstraint(
                condition=models.Q(destino__in=['Cocina', 'Bar', 'Directo']),
                name='chk_producto_destino_valido',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Activo', 'Inactivo', 'Agotado']),
                name='chk_producto_estado_valido',
            ),
        ]

    def __str__(self):
        return f"{self.nombre} (${self.precio:,}) [{self.destino}]"

    @property
    def precio_formateado(self):
        return f"${self.precio:,}".replace(',', '.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 5. MENÚS Y COMBOS
# =============================================================================
class MenuCombo(models.Model):
    ESTADOS = [
        ('Activo', 'Activo'),
        ('Inactivo', 'Inactivo'),
    ]

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    productos_incluidos = models.TextField(help_text="Descripción o listado de productos que incluye el combo")
    precio = models.IntegerField(
        validators=[MinValueValidator(1)],
        help_text="Precio de venta del menú/combo en CLP (> 0)",
    )
    ahorro_estimado = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Ahorro estimado en CLP respecto a la compra individual (>= 0)",
    )
    categoria = models.CharField(max_length=50, default='Combos')
    disponibilidad = models.CharField(max_length=100, default='Todo el día')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'menus_combos'
        verbose_name = 'Menú / Combo'
        verbose_name_plural = 'Menús y Combos'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(precio__gt=0),
                name='chk_menu_precio_positivo',
            ),
            models.CheckConstraint(
                condition=models.Q(ahorro_estimado__gte=0),
                name='chk_menu_ahorro_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Activo', 'Inactivo']),
                name='chk_menu_estado_valido',
            ),
        ]

    def __str__(self):
        return f"{self.nombre} (${self.precio:,})"

    @property
    def precio_formateado(self):
        return f"${self.precio:,}".replace(',', '.')

    @property
    def ahorro_formateado(self):
        return f"Ahorro ${self.ahorro_estimado:,}".replace(',', '.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 6. MESAS Y SALÓN
# =============================================================================
class Mesa(models.Model):
    ZONAS = [
        ('Salón Principal', 'Salón Principal'),
        ('Terraza Jirafas', 'Terraza Jirafas'),
        ('Sector Familiar', 'Sector Familiar'),
        ('Sector Mirador', 'Sector Mirador'),
    ]
    ESTADOS = [
        ('Disponible', 'Disponible'),
        ('Ocupada', 'Ocupada'),
        ('Reservada', 'Reservada'),
        ('Mantenimiento', 'Mantenimiento'),
    ]

    numero = models.CharField(max_length=20, unique=True)
    zona = models.CharField(max_length=50, choices=ZONAS)
    capacidad = models.IntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Disponible')
    consumo_actual = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    mozo_asignado = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mesas_atendidas',
    )
    comensales_actuales = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    hora_inicio_ocupacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mesas'
        verbose_name = 'Mesa'
        verbose_name_plural = 'Mesas'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacidad__gt=0),
                name='chk_mesa_capacidad_positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(consumo_actual__gte=0),
                name='chk_mesa_consumo_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(comensales_actuales__gte=0),
                name='chk_mesa_comensales_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    zona__in=[
                        'Salón Principal',
                        'Terraza Jirafas',
                        'Sector Familiar',
                        'Sector Mirador',
                    ]
                ),
                name='chk_mesa_zona_valida',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estado__in=['Disponible', 'Ocupada', 'Reservada', 'Mantenimiento']
                ),
                name='chk_mesa_estado_valido',
            ),
        ]

    def __str__(self):
        return f"Mesa {self.numero} ({self.zona}) - {self.estado}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 7. SESIONES DE CAJA Y CUADRATURA (Requisito Semana 12)
# =============================================================================
class SesionCaja(models.Model):
    ESTADOS = [
        ('Abierta', 'Abierta'),
        ('Cerrada', 'Cerrada'),
    ]

    cajero = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='sesiones_caja')
    terminal_nombre = models.CharField(max_length=50, default='Terminal 01 - Caja Principal')
    fecha_apertura = models.DateTimeField(default=timezone.now)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_apertura = models.IntegerField(
        help_text="Monto de efectivo disponible para vueltos/sencillo (>= 0)",
        default=50000,
        validators=[MinValueValidator(0)],
    )
    monto_cierre_sistema = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total esperado según ventas del sistema (>= 0)",
    )
    monto_cierre_real = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Total contado físicamente en cuadratura (>= 0)",
    )
    # Nota: `diferencia` admite valores negativos (faltante de caja), cero (exacta) o positivos (sobrante)
    diferencia = models.IntegerField(
        default=0,
        help_text="Diferencia de arqueo (negativa = faltante, 0 = exacta, positiva = sobrante)",
    )
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Abierta')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sesiones_caja'
        verbose_name = 'Sesión de Caja'
        verbose_name_plural = 'Sesiones de Caja'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto_apertura__gte=0),
                name='chk_sesioncaja_apertura_no_negativa',
            ),
            models.CheckConstraint(
                condition=models.Q(monto_cierre_sistema__gte=0),
                name='chk_sesioncaja_sistema_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(monto_cierre_real__gte=0),
                name='chk_sesioncaja_real_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Abierta', 'Cerrada']),
                name='chk_sesioncaja_estado_valido',
            ),
        ]

    def __str__(self):
        return f"Caja {self.terminal_nombre} - {self.cajero.nombre} ({self.estado})"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CuadraturaCaja(models.Model):
    """
    Desglose obligatorio exigido en Semana 12:
    - Billetes: $20.000, $10.000, $5.000, $1.000
    - Monedas: $500, $100, $50, $5, $1
    """
    sesion = models.OneToOneField(SesionCaja, on_delete=models.CASCADE, related_name='cuadratura')

    # Billetes
    billetes_20000 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    billetes_10000 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    billetes_5000 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    billetes_1000 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    # Monedas
    monedas_500 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    monedas_100 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    monedas_50 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    monedas_5 = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    monedas_1 = models.IntegerField(default=0, validators=[MinValueValidator(0)])

    total_efectivo_contado = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'cuadraturas_caja'
        verbose_name = 'Cuadratura de Caja'
        verbose_name_plural = 'Cuadraturas de Caja'
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(billetes_20000__gte=0)
                    & models.Q(billetes_10000__gte=0)
                    & models.Q(billetes_5000__gte=0)
                    & models.Q(billetes_1000__gte=0)
                    & models.Q(monedas_500__gte=0)
                    & models.Q(monedas_100__gte=0)
                    & models.Q(monedas_50__gte=0)
                    & models.Q(monedas_5__gte=0)
                    & models.Q(monedas_1__gte=0)
                    & models.Q(total_efectivo_contado__gte=0)
                ),
                name='chk_cuadratura_denominaciones_no_negativas',
            ),
        ]

    def calcular_total(self):
        return (
            (self.billetes_20000 or 0) * 20000
            + (self.billetes_10000 or 0) * 10000
            + (self.billetes_5000 or 0) * 5000
            + (self.billetes_1000 or 0) * 1000
            + (self.monedas_500 or 0) * 500
            + (self.monedas_100 or 0) * 100
            + (self.monedas_50 or 0) * 50
            + (self.monedas_5 or 0) * 5
            + (self.monedas_1 or 0) * 1
        )

    def save(self, *args, **kwargs):
        self.total_efectivo_contado = self.calcular_total()
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 8. VENTAS Y DETALLE
# =============================================================================
class Venta(models.Model):
    MODALIDADES = [
        ('BAR', 'Venta en Barra (Boleta Inmediata)'),
        ('MESA', 'Toma Pedido Mesa (Boleta diferida al pagar)'),
        ('PARA LLEVAR', 'Para Llevar'),
    ]
    METODOS_PAGO = [
        ('Efectivo', 'Efectivo'),
        ('Tarjeta Débito', 'Tarjeta Débito'),
        ('Tarjeta Crédito', 'Tarjeta Crédito'),
        ('Vale Fiado', 'Vale Fiado'),
        ('Transferencia', 'Transferencia'),
    ]
    ESTADOS = [
        ('Pendiente', 'Pendiente (Mesa activa)'),
        ('Pagado', 'Pagado / Boleta Emitida'),
        ('Anulado', 'Anulado'),
    ]

    venta_num = models.CharField(max_length=20, unique=True)
    fecha_hora = models.DateTimeField(default=timezone.now)
    modalidad = models.CharField(max_length=30, choices=MODALIDADES, default='BAR')
    mesa = models.ForeignKey(Mesa, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas')
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name='ventas_realizadas')
    sesion_caja = models.ForeignKey(SesionCaja, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas')
    subtotal = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    iva = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    metodo_pago = models.CharField(max_length=50, choices=METODOS_PAGO, default='Efectivo')
    estado = models.CharField(max_length=30, choices=ESTADOS, default='Pagado')
    boleta_emitida = models.BooleanField(default=True)
    notas = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ventas'
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0),
                name='chk_venta_subtotal_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(iva__gte=0),
                name='chk_venta_iva_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=0),
                name='chk_venta_total_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(modalidad__in=['BAR', 'MESA', 'PARA LLEVAR']),
                name='chk_venta_modalidad_valida',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    metodo_pago__in=[
                        'Efectivo',
                        'Tarjeta Débito',
                        'Tarjeta Crédito',
                        'Vale Fiado',
                        'Transferencia',
                    ]
                ),
                name='chk_venta_metodo_pago_valido',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Pendiente', 'Pagado', 'Anulado']),
                name='chk_venta_estado_valido',
            ),
        ]

    def __str__(self):
        return f"Venta #{self.venta_num} - {self.modalidad} (${self.total:,})"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DetalleVenta(models.Model):
    DESTINOS = [
        ('COCINA', 'COCINA'),
        ('BAR', 'BAR'),
        ('ENTREGA INMEDIATA', 'ENTREGA INMEDIATA'),
    ]
    ESTADOS_PRODUCCION = [
        ('Pendiente', 'Pendiente'),
        ('En preparación', 'En preparación'),
        ('Preparado', 'Preparado'),
        ('Listo', 'Listo'),
        ('Entregado', 'Entregado'),
    ]

    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, null=True, blank=True)
    menu = models.ForeignKey(MenuCombo, on_delete=models.PROTECT, null=True, blank=True)
    nombre_item = models.CharField(max_length=150)
    cantidad = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    precio_unitario = models.IntegerField(validators=[MinValueValidator(1)])
    subtotal = models.IntegerField(validators=[MinValueValidator(1)])
    destino = models.CharField(max_length=30, choices=DESTINOS, default='ENTREGA INMEDIATA')
    estado_produccion = models.CharField(max_length=30, choices=ESTADOS_PRODUCCION, default='Pendiente')
    notas_preparacion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'detalle_ventas'
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalles de Venta'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='chk_detalleventa_cantidad_positiva',
            ),
            models.CheckConstraint(
                condition=models.Q(precio_unitario__gt=0),
                name='chk_detalleventa_precio_positivo',
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gt=0),
                name='chk_detalleventa_subtotal_positivo',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(producto__isnull=False, menu__isnull=True)
                    | models.Q(producto__isnull=True, menu__isnull=False)
                ),
                name='chk_detalleventa_producto_xor_menu',
            ),
            models.CheckConstraint(
                condition=models.Q(destino__in=['COCINA', 'BAR', 'ENTREGA INMEDIATA']),
                name='chk_detalleventa_destino_valido',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estado_produccion__in=[
                        'Pendiente',
                        'En preparación',
                        'Preparado',
                        'Listo',
                        'Entregado',
                    ]
                ),
                name='chk_detalleventa_estado_prod_valido',
            ),
        ]

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_item} (${self.subtotal:,})"

    def clean(self):
        super().clean()
        has_producto = self.producto_id is not None
        has_menu = self.menu_id is not None
        if not has_producto and not has_menu:
            raise ValidationError("El detalle de venta debe estar asociado a un Producto o a un Menú/Combo.")
        if has_producto and has_menu:
            raise ValidationError("El detalle de venta no puede asociarse simultáneamente a un Producto y a un Menú.")
        if (
            self.cantidad is not None
            and self.precio_unitario is not None
            and self.subtotal is not None
            and self.cantidad > 0
            and self.precio_unitario > 0
        ):
            esperado = self.cantidad * self.precio_unitario
            if self.subtotal != esperado:
                raise ValidationError(
                    {"subtotal": f"El subtotal ({self.subtotal}) no coincide con cantidad * precio_unitario ({esperado})."}
                )

    def save(self, *args, **kwargs):
        if (
            self.subtotal is None
            and self.cantidad is not None
            and self.precio_unitario is not None
        ):
            self.subtotal = self.cantidad * self.precio_unitario
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 9. COMANDAS DE PRODUCCIÓN (KDS COCINA & BDS BAR)
# =============================================================================
class ComandaProduccion(models.Model):
    AREAS = [
        ('COCINA', 'Cocina KDS'),
        ('BAR', 'Bar BDS'),
    ]
    ESTADOS = [
        ('Pendiente', 'Pendiente'),
        ('En preparación', 'En preparación'),
        ('Preparado', 'Preparado / Listo'),
        ('Listo', 'Listo en Barra'),
        ('Entregado', 'Entregado'),
    ]
    URGENCIAS = [
        ('normal', 'Normal'),
        ('advertencia', 'Advertencia (+10 min)'),
        ('urgente', 'Urgente (+20 min)'),
        ('listo', 'Listo para despacho'),
    ]

    codigo_comanda = models.CharField(max_length=20, unique=True)
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='comandas')
    area_destino = models.CharField(max_length=20, choices=AREAS)
    urgencia = models.CharField(max_length=20, choices=URGENCIAS, default='normal')
    estado = models.CharField(max_length=30, choices=ESTADOS, default='Pendiente')
    comentarios = models.TextField(blank=True, null=True)
    fecha_hora_ingreso = models.DateTimeField(default=timezone.now)
    fecha_hora_despacho = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'comandas_produccion'
        verbose_name = 'Comanda de Producción'
        verbose_name_plural = 'Comandas de Producción'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(area_destino__in=['COCINA', 'BAR']),
                name='chk_comanda_area_valida',
            ),
            models.CheckConstraint(
                condition=models.Q(urgencia__in=['normal', 'advertencia', 'urgente', 'listo']),
                name='chk_comanda_urgencia_valida',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    estado__in=['Pendiente', 'En preparación', 'Preparado', 'Listo', 'Entregado']
                ),
                name='chk_comanda_estado_valido',
            ),
        ]

    def __str__(self):
        return f"Comanda {self.codigo_comanda} [{self.area_destino}] - {self.estado}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 10. FIADOS PERSONAL
# =============================================================================
class FiadoPersonal(models.Model):
    ESTADOS = [
        ('Al día', 'Al día'),
        ('Por descontar', 'Por descontar'),
        ('Excedido', 'Excedido'),
        ('Bloqueado', 'Bloqueado'),
    ]

    rut = models.CharField(max_length=15, unique=True)
    trabajador = models.CharField(max_length=150)
    cargo_grupo = models.CharField(max_length=100)
    limite_credito = models.IntegerField(default=50000, validators=[MinValueValidator(0)])
    total_acumulado = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    consumos_mes = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    estado = models.CharField(max_length=30, choices=ESTADOS, default='Al día')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'fiados_personal'
        verbose_name = 'Fiado de Colaborador'
        verbose_name_plural = 'Fiados de Colaboradores'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(limite_credito__gte=0),
                name='chk_fiado_limite_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(total_acumulado__gte=0),
                name='chk_fiado_acumulado_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(consumos_mes__gte=0),
                name='chk_fiado_consumos_no_negativo',
            ),
            models.CheckConstraint(
                condition=models.Q(estado__in=['Al día', 'Por descontar', 'Excedido', 'Bloqueado']),
                name='chk_fiado_estado_valido',
            ),
        ]

    def __str__(self):
        return f"{self.trabajador} ({self.rut}) - ${self.total_acumulado:,}"

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class FiadoMovimiento(models.Model):
    fiado = models.ForeignKey(FiadoPersonal, on_delete=models.CASCADE, related_name='movimientos')
    venta = models.ForeignKey(Venta, on_delete=models.SET_NULL, null=True, blank=True)
    detalle = models.CharField(max_length=255)
    cantidad = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    # Nota: `monto` es positivo para cargos/vales de consumo y puede ser negativo para abonos/descuentos de nómina, pero nunca 0
    monto = models.IntegerField(
        help_text="Importe en CLP (> 0 para cargo de consumo, < 0 para abono/descuento, distinto de 0)"
    )
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'fiados_movimientos'
        verbose_name = 'Movimiento de Fiado'
        verbose_name_plural = 'Movimientos de Fiados'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad__gt=0),
                name='chk_fiadomov_cantidad_positiva',
            ),
            models.CheckConstraint(
                condition=~models.Q(monto=0),
                name='chk_fiadomov_monto_no_cero',
            ),
        ]

    def __str__(self):
        return f"{self.fiado.trabajador}: {self.detalle} (${self.monto:,})"

    def clean(self):
        super().clean()
        if self.monto == 0:
            raise ValidationError({"monto": "El monto del movimiento de fiado no puede ser 0."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# =============================================================================
# 11. HISTORIAL DE AUDITORÍA / ACCIONES (Requisito Semana 11)
# =============================================================================
class LogAuditoria(models.Model):
    ACCIONES = [
        ('LOGIN', 'Inicio de Sesión'),
        ('LOGIN_FALLIDO', 'Intento de Inicio de Sesión Fallido'),
        ('LOGOUT', 'Cierre de Sesión'),
        ('ACCESO_DENEGADO', 'Acceso Denegado por Rol (RBAC)'),
        ('APERTURA_CAJA', 'Apertura de Caja'),
        ('CIERRE_CAJA', 'Cierre de Caja y Cuadratura'),
        ('VENTA_CREADA', 'Emisión de Venta'),
        ('COMANDA_ENVIADA', 'Envío de Comanda a Cocina/Bar'),
        ('COMANDA_ESTADO', 'Cambio de Estado en Comanda'),
        ('MESA_REASIGNADA', 'Reasignación de Mesa'),
        ('PRODUCTO_MODIFICADO', 'Modificación de Producto'),
    ]

    usuario = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True)
    accion = models.CharField(max_length=50, choices=ACCIONES)
    modulo = models.CharField(max_length=50)
    descripcion = models.TextField()
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    fecha_hora = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'log_auditoria'
        verbose_name = 'Log de Auditoría'
        verbose_name_plural = 'Historial de Auditoría'
        ordering = ['-fecha_hora']

    def __str__(self):
        return f"[{self.fecha_hora.strftime('%d/%m/%Y %H:%M')}] {self.accion} por {self.usuario or 'Sistema'}"


# =============================================================================
# 12. CONFIGURACIÓN DEL SISTEMA POS
# =============================================================================
class ConfiguracionPOS(models.Model):
    nombre_parque = models.CharField(max_length=100, default='Parque Safari Rancagua')
    razon_social = models.CharField(max_length=150, default='Parque Safari Chile S.A.')
    rut = models.CharField(max_length=20, default='76.123.456-7')
    direccion = models.CharField(max_length=200, default='Ruta Travesía Km 82, Rancagua, Región de O\'Higgins')
    telefono = models.CharField(max_length=50, default='+56 72 258 3100')
    terminal_caja = models.CharField(max_length=100, default='Terminal POS 01 - Casona Central')
    impresora_tickets = models.CharField(max_length=100, default='Epson TM-T20III (Térmica 80mm - USB)')
    impresora_cocina = models.CharField(max_length=100, default='Epson TM-U220B (Matricial Impacto - Red)')
    impresora_bar = models.CharField(max_length=100, default='Bixolon SRP-330II (Térmica 80mm - WiFi)')
    iva_incluido = models.BooleanField(default=True)
    iva_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=19.00,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
    )
    modo_offline = models.BooleanField(default=True)
    sonido_comandas = models.BooleanField(default=True)
    resolucion_optimizada = models.CharField(max_length=100, default='1920x1080 Full HD & Pantallas Táctiles 10"')

    class Meta:
        db_table = 'configuracion_pos'
        verbose_name = 'Configuración POS'
        verbose_name_plural = 'Configuración POS'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(iva_porcentaje__gte=0) & models.Q(iva_porcentaje__lte=100),
                name='chk_config_iva_rango',
            ),
        ]

    def __str__(self):
        return self.nombre_parque

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
