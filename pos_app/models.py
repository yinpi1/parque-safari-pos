"""
pos_app/models.py
Modelos ORM de Django para el Sistema Web POS — Parque Safari.
Mapea la base de datos relacional PostgreSQL (Neon) y añade el soporte de:
- Gestión de Usuarios y Roles con control de acceso (Semana 10 y 11)
- Mantenedores de Mesas, Productos, Categorías y Menús (Semana 11)
- Historial de Auditoría (Semana 11)
- Inicio/Cierre de jornada, Apertura/Cierre de caja y Cuadratura (Semana 12)
- Ventas en Barra vs Ventas en Mesa con comandas de Cocina y Bar (Semana 12)
"""

from django.db import models
from django.utils import timezone

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
    password = models.CharField(max_length=255, default='123456')
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, related_name='usuarios')
    caja_asignada = models.CharField(max_length=100, default='Sin asignar')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    ultimo_acceso = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'usuarios'
        verbose_name = 'Usuario del Sistema'
        verbose_name_plural = 'Usuarios del Sistema'

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
    precio = models.IntegerField(help_text="Precio en pesos chilenos (CLP)")
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

    def __str__(self):
        return f"{self.nombre} (${self.precio:,}) [{self.destino}]"

    @property
    def precio_formateado(self):
        return f"${self.precio:,}".replace(',', '.')


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
    precio = models.IntegerField()
    ahorro_estimado = models.IntegerField(default=0)
    categoria = models.CharField(max_length=50, default='Combos')
    disponibilidad = models.CharField(max_length=100, default='Todo el día')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Activo')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'menus_combos'
        verbose_name = 'Menú / Combo'
        verbose_name_plural = 'Menús y Combos'

    def __str__(self):
        return f"{self.nombre} (${self.precio:,})"


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
    capacidad = models.IntegerField(default=4)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Disponible')
    consumo_actual = models.IntegerField(default=0)
    mozo_asignado = models.ForeignKey(Usuario, on_delete=models.SET_NULL, null=True, blank=True, related_name='mesas_atendidas')
    comensales_actuales = models.IntegerField(default=0)
    hora_inicio_ocupacion = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mesas'
        verbose_name = 'Mesa'
        verbose_name_plural = 'Mesas'

    def __str__(self):
        return f"Mesa {self.numero} ({self.zona}) - {self.estado}"


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
    monto_apertura = models.IntegerField(help_text="Monto de efectivo disponible para vueltos/sencillo", default=50000)
    monto_cierre_sistema = models.IntegerField(default=0, help_text="Total esperado según ventas del sistema")
    monto_cierre_real = models.IntegerField(default=0, help_text="Total contado físicamente en cuadratura")
    diferencia = models.IntegerField(default=0, help_text="Diferencia (Sobrante/Faltante)")
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Abierta')
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'sesiones_caja'
        verbose_name = 'Sesión de Caja'
        verbose_name_plural = 'Sesiones de Caja'

    def __str__(self):
        return f"Caja {self.terminal_nombre} - {self.cajero.nombre} ({self.estado})"


class CuadraturaCaja(models.Model):
    """
    Desglose obligatorio exigido en Semana 12:
    - Billetes: $20.000, $10.000, $5.000, $1.000
    - Monedas: $500, $100, $50, $5, $1
    """
    sesion = models.OneToOneField(SesionCaja, on_delete=models.CASCADE, related_name='cuadratura')
    
    # Billetes
    billetes_20000 = models.IntegerField(default=0)
    billetes_10000 = models.IntegerField(default=0)
    billetes_5000 = models.IntegerField(default=0)
    billetes_1000 = models.IntegerField(default=0)
    
    # Monedas
    monedas_500 = models.IntegerField(default=0)
    monedas_100 = models.IntegerField(default=0)
    monedas_50 = models.IntegerField(default=0)
    monedas_5 = models.IntegerField(default=0)
    monedas_1 = models.IntegerField(default=0)
    
    total_efectivo_contado = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'cuadraturas_caja'
        verbose_name = 'Cuadratura de Caja'
        verbose_name_plural = 'Cuadraturas de Caja'

    def calcular_total(self):
        return (
            self.billetes_20000 * 20000 +
            self.billetes_10000 * 10000 +
            self.billetes_5000 * 5000 +
            self.billetes_1000 * 1000 +
            self.monedas_500 * 500 +
            self.monedas_100 * 100 +
            self.monedas_50 * 50 +
            self.monedas_5 * 5 +
            self.monedas_1 * 1
        )

    def save(self, *args, **kwargs):
        self.total_efectivo_contado = self.calcular_total()
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
    subtotal = models.IntegerField(default=0)
    iva = models.IntegerField(default=0)
    total = models.IntegerField(default=0)
    metodo_pago = models.CharField(max_length=50, choices=METODOS_PAGO, default='Efectivo')
    estado = models.CharField(max_length=30, choices=ESTADOS, default='Pagado')
    boleta_emitida = models.BooleanField(default=True)
    notas = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'ventas'
        verbose_name = 'Venta'
        verbose_name_plural = 'Ventas'

    def __str__(self):
        return f"Venta #{self.venta_num} - {self.modalidad} (${self.total:,})"


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
    cantidad = models.IntegerField(default=1)
    precio_unitario = models.IntegerField()
    subtotal = models.IntegerField()
    destino = models.CharField(max_length=30, choices=DESTINOS, default='ENTREGA INMEDIATA')
    estado_produccion = models.CharField(max_length=30, choices=ESTADOS_PRODUCCION, default='Pendiente')
    notas_preparacion = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'detalle_ventas'
        verbose_name = 'Detalle de Venta'
        verbose_name_plural = 'Detalles de Venta'

    def __str__(self):
        return f"{self.cantidad}x {self.nombre_item} (${self.subtotal:,})"


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

    def __str__(self):
        return f"Comanda {self.codigo_comanda} [{self.area_destino}] - {self.estado}"


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
    limite_credito = models.IntegerField(default=50000)
    total_acumulado = models.IntegerField(default=0)
    consumos_mes = models.IntegerField(default=0)
    estado = models.CharField(max_length=30, choices=ESTADOS, default='Al día')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'fiados_personal'
        verbose_name = 'Fiado de Colaborador'
        verbose_name_plural = 'Fiados de Colaboradores'

    def __str__(self):
        return f"{self.trabajador} ({self.rut}) - ${self.total_acumulado:,}"


class FiadoMovimiento(models.Model):
    fiado = models.ForeignKey(FiadoPersonal, on_delete=models.CASCADE, related_name='movimientos')
    venta = models.ForeignKey(Venta, on_delete=models.SET_NULL, null=True, blank=True)
    detalle = models.CharField(max_length=255)
    cantidad = models.IntegerField(default=1)
    monto = models.IntegerField()
    fecha = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'fiados_movimientos'
        verbose_name = 'Movimiento de Fiado'
        verbose_name_plural = 'Movimientos de Fiados'

    def __str__(self):
        return f"{self.fiado.trabajador}: {self.detalle} (${self.monto:,})"


# =============================================================================
# 11. HISTORIAL DE AUDITORÍA / ACCIONES (Requisito Semana 11)
# =============================================================================
class LogAuditoria(models.Model):
    ACCIONES = [
        ('LOGIN', 'Inicio de Sesión'),
        ('LOGOUT', 'Cierre de Sesión'),
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
    iva_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=19.00)
    modo_offline = models.BooleanField(default=True)
    sonido_comandas = models.BooleanField(default=True)
    resolucion_optimizada = models.CharField(max_length=100, default='1920x1080 Full HD & Pantallas Táctiles 10"')

    class Meta:
        db_table = 'configuracion_pos'
        verbose_name = 'Configuración POS'
        verbose_name_plural = 'Configuración POS'

    def __str__(self):
        return self.nombre_parque
