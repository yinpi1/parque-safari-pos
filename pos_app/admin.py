from django.contrib import admin
from .models import (
    Cargo,
    Usuario,
    Categoria,
    Producto,
    MenuCombo,
    Mesa,
    SesionCaja,
    CuadraturaCaja,
    Venta,
    DetalleVenta,
    ComandaProduccion,
    FiadoPersonal,
    FiadoMovimiento,
    LogAuditoria,
    ConfiguracionPOS,
)


@admin.register(Cargo)
class CargoAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'nivel', 'created_at')
    list_filter = ('nivel',)
    search_fields = ('id', 'nombre', 'descripcion')


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'nombre', 'email', 'cargo', 'caja_asignada', 'estado', 'ultimo_acceso')
    list_filter = ('estado', 'cargo')
    search_fields = ('usuario', 'nombre', 'email')
    readonly_fields = ('ultimo_acceso', 'created_at')


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre', 'icono', 'color', 'activo')
    list_filter = ('activo',)
    search_fields = ('id', 'nombre')


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'categoria', 'precio', 'tipo', 'destino', 'estado')
    list_filter = ('categoria', 'tipo', 'destino', 'estado')
    search_fields = ('codigo', 'nombre', 'descripcion')


@admin.register(MenuCombo)
class MenuComboAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nombre', 'precio', 'ahorro_estimado', 'categoria', 'disponibilidad', 'estado')
    list_filter = ('estado', 'categoria')
    search_fields = ('codigo', 'nombre', 'productos_incluidos')


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'zona', 'capacidad', 'estado', 'consumo_actual', 'mozo_asignado', 'comensales_actuales')
    list_filter = ('zona', 'estado')
    search_fields = ('numero', 'zona')


@admin.register(SesionCaja)
class SesionCajaAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'cajero', 'terminal_nombre', 'fecha_apertura', 'fecha_cierre',
        'monto_apertura', 'monto_cierre_sistema', 'monto_cierre_real', 'diferencia', 'estado',
    )
    list_filter = ('estado', 'terminal_nombre')
    search_fields = ('terminal_nombre', 'cajero__nombre', 'cajero__usuario')


@admin.register(CuadraturaCaja)
class CuadraturaCajaAdmin(admin.ModelAdmin):
    list_display = ('id', 'sesion', 'total_efectivo_contado', 'created_at')


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('venta_num', 'fecha_hora', 'modalidad', 'mesa', 'usuario', 'total', 'metodo_pago', 'estado', 'boleta_emitida')
    list_filter = ('modalidad', 'metodo_pago', 'estado', 'boleta_emitida')
    search_fields = ('venta_num', 'notas')


@admin.register(DetalleVenta)
class DetalleVentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'venta', 'nombre_item', 'cantidad', 'precio_unitario', 'subtotal', 'destino', 'estado_produccion')
    list_filter = ('destino', 'estado_produccion')
    search_fields = ('nombre_item', 'venta__venta_num')


@admin.register(ComandaProduccion)
class ComandaProduccionAdmin(admin.ModelAdmin):
    list_display = ('codigo_comanda', 'venta', 'area_destino', 'urgencia', 'estado', 'fecha_hora_ingreso', 'fecha_hora_despacho')
    list_filter = ('area_destino', 'urgencia', 'estado')
    search_fields = ('codigo_comanda', 'venta__venta_num')


@admin.register(FiadoPersonal)
class FiadoPersonalAdmin(admin.ModelAdmin):
    list_display = ('rut', 'trabajador', 'cargo_grupo', 'limite_credito', 'total_acumulado', 'consumos_mes', 'estado')
    list_filter = ('estado', 'cargo_grupo')
    search_fields = ('rut', 'trabajador', 'cargo_grupo')


@admin.register(FiadoMovimiento)
class FiadoMovimientoAdmin(admin.ModelAdmin):
    list_display = ('id', 'fiado', 'venta', 'detalle', 'cantidad', 'monto', 'fecha')
    search_fields = ('fiado__rut', 'fiado__trabajador', 'detalle')


@admin.register(LogAuditoria)
class LogAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_hora', 'usuario', 'accion', 'modulo', 'ip_origen')
    list_filter = ('accion', 'modulo')
    search_fields = ('descripcion', 'usuario__usuario', 'usuario__nombre')
    readonly_fields = ('fecha_hora',)


@admin.register(ConfiguracionPOS)
class ConfiguracionPOSAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre_parque', 'rut', 'terminal_caja', 'iva_incluido', 'iva_porcentaje', 'modo_offline')
