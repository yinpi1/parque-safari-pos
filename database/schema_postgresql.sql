-- =============================================================================
-- PROYECTO: Sistema Web POS - Parque Safari Chile
-- ARCHIVO: database/schema_postgresql.sql (Referencia DDL Sincronizada)
-- MOTOR: PostgreSQL 14+ / 15+ (Neon Serverless PostgreSQL)
--
-- FUENTE DE VERDAD DEL ESQUEMA:
-- Las migraciones de Django (`pos_app/migrations/`) constituyen la ÚNICA fuente
-- de verdad ejecutable para crear y evolucionar el esquema en desarrollo,
-- pruebas y producción:
--   * 0001_initial.py
--   * 0002_hash_plain_passwords.py
--   * 0003_integridad_restricciones_pos.py
--
-- Este archivo SQL se mantiene como documentación técnica de referencia,
-- 100% alineado con `pos_app/models.py`. Para inspeccionar el SQL exacto
-- generado por Django para PostgreSQL sin tocar la base de datos:
--   python manage.py sqlmigrate pos_app 0001
--   python manage.py sqlmigrate pos_app 0003
-- =============================================================================

-- =============================================================================
-- 1. TABLA: cargos (Roles y Niveles de Acceso RBAC)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cargos (
    id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    descripcion TEXT,
    nivel VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE cargos IS 'Roles de usuarios del sistema POS (cajero, garzon, cocina, bar, admin)';

-- =============================================================================
-- 2. TABLA: usuarios (Colaboradores que acceden al sistema)
-- =============================================================================
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    cargo_id VARCHAR(20) NOT NULL REFERENCES cargos(id) ON DELETE RESTRICT,
    caja_asignada VARCHAR(100) NOT NULL DEFAULT 'Sin asignar',
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo',
    ultimo_acceso TIMESTAMP WITH TIME ZONE NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_usuario_estado_valido CHECK (estado IN ('Activo', 'Inactivo', 'Suspendido'))
);

CREATE INDEX IF NOT EXISTS idx_usuarios_cargo ON usuarios(cargo_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_estado ON usuarios(estado);

-- =============================================================================
-- 3. TABLA: categorias (Categorías de Productos del Parque)
-- =============================================================================
CREATE TABLE IF NOT EXISTS categorias (
    id VARCHAR(30) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    icono VARCHAR(50) NOT NULL DEFAULT 'bi-grid-fill',
    color VARCHAR(30) NOT NULL DEFAULT 'primary',
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- =============================================================================
-- 4. TABLA: productos (Catálogo de Productos)
-- =============================================================================
CREATE TABLE IF NOT EXISTS productos (
    id BIGSERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    categoria_id VARCHAR(30) NOT NULL REFERENCES categorias(id) ON DELETE RESTRICT,
    precio INTEGER NOT NULL,
    tipo VARCHAR(50) NOT NULL DEFAULT 'Producto listo',
    destino VARCHAR(30) NOT NULL DEFAULT 'Directo',
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo',
    badge_tipo VARCHAR(30) NOT NULL DEFAULT 'badge-listo',
    descripcion TEXT NULL,
    icono VARCHAR(50) NOT NULL DEFAULT 'bi-box2-heart',
    imagen_placeholder VARCHAR(50) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_producto_precio_positivo CHECK (precio > 0),
    CONSTRAINT chk_producto_tipo_valido CHECK (tipo IN ('Requiere preparación', 'Producto listo')),
    CONSTRAINT chk_producto_destino_valido CHECK (destino IN ('Cocina', 'Bar', 'Directo')),
    CONSTRAINT chk_producto_estado_valido CHECK (estado IN ('Activo', 'Inactivo', 'Agotado'))
);

CREATE INDEX IF NOT EXISTS idx_productos_categoria ON productos(categoria_id);
CREATE INDEX IF NOT EXISTS idx_productos_destino ON productos(destino);
CREATE INDEX IF NOT EXISTS idx_productos_estado ON productos(estado);

-- =============================================================================
-- 5. TABLA: menus_combos (Packs Promocionales y Combos)
-- =============================================================================
CREATE TABLE IF NOT EXISTS menus_combos (
    id BIGSERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    productos_incluidos TEXT NOT NULL,
    precio INTEGER NOT NULL,
    ahorro_estimado INTEGER NOT NULL DEFAULT 0,
    categoria VARCHAR(50) NOT NULL DEFAULT 'Combos',
    disponibilidad VARCHAR(100) NOT NULL DEFAULT 'Todo el día',
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_menu_precio_positivo CHECK (precio > 0),
    CONSTRAINT chk_menu_ahorro_no_negativo CHECK (ahorro_estimado >= 0),
    CONSTRAINT chk_menu_estado_valido CHECK (estado IN ('Activo', 'Inactivo'))
);

-- =============================================================================
-- 6. TABLA: mesas (Zonas y Mesas de Atención)
-- =============================================================================
CREATE TABLE IF NOT EXISTS mesas (
    id BIGSERIAL PRIMARY KEY,
    numero VARCHAR(20) UNIQUE NOT NULL,
    zona VARCHAR(50) NOT NULL,
    capacidad INTEGER NOT NULL DEFAULT 4,
    estado VARCHAR(20) NOT NULL DEFAULT 'Disponible',
    consumo_actual INTEGER NOT NULL DEFAULT 0,
    mozo_asignado_id BIGINT NULL REFERENCES usuarios(id) ON DELETE SET NULL,
    comensales_actuales INTEGER NOT NULL DEFAULT 0,
    hora_inicio_ocupacion TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT chk_mesa_capacidad_positiva CHECK (capacidad > 0),
    CONSTRAINT chk_mesa_consumo_no_negativo CHECK (consumo_actual >= 0),
    CONSTRAINT chk_mesa_comensales_no_negativo CHECK (comensales_actuales >= 0),
    CONSTRAINT chk_mesa_zona_valida CHECK (zona IN ('Salón Principal', 'Terraza Jirafas', 'Sector Familiar', 'Sector Mirador')),
    CONSTRAINT chk_mesa_estado_valido CHECK (estado IN ('Disponible', 'Ocupada', 'Reservada', 'Mantenimiento'))
);

CREATE INDEX IF NOT EXISTS idx_mesas_zona ON mesas(zona);
CREATE INDEX IF NOT EXISTS idx_mesas_estado ON mesas(estado);

-- =============================================================================
-- 7. TABLA: sesiones_caja (Apertura, Arqueo y Cierre de Turnos de Caja)
-- =============================================================================
CREATE TABLE IF NOT EXISTS sesiones_caja (
    id BIGSERIAL PRIMARY KEY,
    cajero_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    terminal_nombre VARCHAR(100) NOT NULL DEFAULT 'Terminal POS 01 - Casona Central',
    fecha_apertura TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre TIMESTAMP WITH TIME ZONE NULL,
    monto_apertura INTEGER NOT NULL DEFAULT 50000,
    monto_cierre_sistema INTEGER NOT NULL DEFAULT 0,
    monto_cierre_real INTEGER NOT NULL DEFAULT 0,
    diferencia INTEGER NOT NULL DEFAULT 0, -- Admite negativos (faltantes de caja) y positivos (sobrantes)
    estado VARCHAR(20) NOT NULL DEFAULT 'Abierta',
    observaciones TEXT NULL,
    CONSTRAINT chk_sesioncaja_apertura_no_negativa CHECK (monto_apertura >= 0),
    CONSTRAINT chk_sesioncaja_sistema_no_negativo CHECK (monto_cierre_sistema >= 0),
    CONSTRAINT chk_sesioncaja_real_no_negativo CHECK (monto_cierre_real >= 0),
    CONSTRAINT chk_sesioncaja_estado_valido CHECK (estado IN ('Abierta', 'Cerrada'))
);

-- =============================================================================
-- 8. TABLA: cuadraturas_caja (Desglose Físico de Billetes y Monedas)
-- =============================================================================
CREATE TABLE IF NOT EXISTS cuadraturas_caja (
    id BIGSERIAL PRIMARY KEY,
    sesion_id BIGINT UNIQUE NOT NULL REFERENCES sesiones_caja(id) ON DELETE CASCADE,
    billetes_20000 INTEGER NOT NULL DEFAULT 0,
    billetes_10000 INTEGER NOT NULL DEFAULT 0,
    billetes_5000 INTEGER NOT NULL DEFAULT 0,
    billetes_1000 INTEGER NOT NULL DEFAULT 0,
    monedas_500 INTEGER NOT NULL DEFAULT 0,
    monedas_100 INTEGER NOT NULL DEFAULT 0,
    monedas_50 INTEGER NOT NULL DEFAULT 0,
    monedas_5 INTEGER NOT NULL DEFAULT 0,
    monedas_1 INTEGER NOT NULL DEFAULT 0,
    total_efectivo_contado INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_cuadratura_denominaciones_no_negativas CHECK (
        billetes_20000 >= 0 AND billetes_10000 >= 0 AND billetes_5000 >= 0 AND
        billetes_1000 >= 0 AND monedas_500 >= 0 AND monedas_100 >= 0 AND
        monedas_50 >= 0 AND monedas_5 >= 0 AND monedas_1 >= 0 AND
        total_efectivo_contado >= 0
    )
);

-- =============================================================================
-- 9. TABLA: ventas (Cabecera de Tickets / Boletas de Venta)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ventas (
    id BIGSERIAL PRIMARY KEY,
    venta_num VARCHAR(20) UNIQUE NOT NULL,
    fecha_hora TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modalidad VARCHAR(30) NOT NULL,
    mesa_id BIGINT NULL REFERENCES mesas(id) ON DELETE SET NULL,
    usuario_id BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT,
    sesion_caja_id BIGINT NULL REFERENCES sesiones_caja(id) ON DELETE SET NULL,
    subtotal INTEGER NOT NULL DEFAULT 0,
    iva INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    metodo_pago VARCHAR(50) NOT NULL DEFAULT 'Efectivo',
    estado VARCHAR(30) NOT NULL DEFAULT 'Pagado',
    boleta_emitida BOOLEAN NOT NULL DEFAULT TRUE,
    notas TEXT NULL,
    CONSTRAINT chk_venta_subtotal_no_negativo CHECK (subtotal >= 0),
    CONSTRAINT chk_venta_iva_no_negativo CHECK (iva >= 0),
    CONSTRAINT chk_venta_total_no_negativo CHECK (total >= 0),
    CONSTRAINT chk_venta_modalidad_valida CHECK (modalidad IN ('MESA', 'BAR', 'DELIVERY', 'PARA LLEVAR')),
    CONSTRAINT chk_venta_metodo_pago_valido CHECK (metodo_pago IN ('Efectivo', 'Tarjeta Débito', 'Tarjeta Crédito', 'Vale Fiado', 'Transferencia')),
    CONSTRAINT chk_venta_estado_valido CHECK (estado IN ('Pendiente', 'Pagado', 'Anulado', 'Cortesía'))
);

CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha_hora);
CREATE INDEX IF NOT EXISTS idx_ventas_usuario ON ventas(usuario_id);
CREATE INDEX IF NOT EXISTS idx_ventas_modalidad ON ventas(modalidad);

-- =============================================================================
-- 10. TABLA: detalle_ventas (Líneas de Producto o Menú por Venta)
-- =============================================================================
CREATE TABLE IF NOT EXISTS detalle_ventas (
    id BIGSERIAL PRIMARY KEY,
    venta_id BIGINT NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id BIGINT NULL REFERENCES productos(id) ON DELETE RESTRICT,
    menu_id BIGINT NULL REFERENCES menus_combos(id) ON DELETE RESTRICT,
    nombre_item VARCHAR(150) NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1,
    precio_unitario INTEGER NOT NULL,
    subtotal INTEGER NOT NULL,
    destino VARCHAR(30) NOT NULL DEFAULT 'ENTREGA INMEDIATA',
    estado_produccion VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    notas_preparacion TEXT NULL,
    CONSTRAINT chk_detalle_cantidad_positiva CHECK (cantidad > 0),
    CONSTRAINT chk_detalle_precio_unitario_no_negativo CHECK (precio_unitario >= 0),
    CONSTRAINT chk_detalle_subtotal_no_negativo CHECK (subtotal >= 0),
    CONSTRAINT chk_detalle_producto_xor_menu CHECK (
        (producto_id IS NOT NULL AND menu_id IS NULL) OR
        (producto_id IS NULL AND menu_id IS NOT NULL)
    ),
    CONSTRAINT chk_detalle_destino_valido CHECK (destino IN ('COCINA', 'BAR', 'ENTREGA INMEDIATA')),
    CONSTRAINT chk_detalle_estado_produccion_valido CHECK (
        estado_produccion IN ('Pendiente', 'En preparación', 'Preparado', 'Listo', 'Entregado')
    )
);

CREATE INDEX IF NOT EXISTS idx_detalle_ventas_venta ON detalle_ventas(venta_id);
CREATE INDEX IF NOT EXISTS idx_detalle_ventas_destino ON detalle_ventas(destino);

-- =============================================================================
-- 11. TABLA: comandas_produccion (KDS Cocina y BDS Bar)
-- =============================================================================
CREATE TABLE IF NOT EXISTS comandas_produccion (
    id BIGSERIAL PRIMARY KEY,
    codigo_comanda VARCHAR(20) UNIQUE NOT NULL,
    venta_id BIGINT NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    area_destino VARCHAR(20) NOT NULL,
    urgencia VARCHAR(20) NOT NULL DEFAULT 'normal',
    estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
    comentarios TEXT NULL,
    fecha_hora_ingreso TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_hora_despacho TIMESTAMP WITH TIME ZONE NULL,
    CONSTRAINT chk_comanda_area_valida CHECK (area_destino IN ('COCINA', 'BAR')),
    CONSTRAINT chk_comanda_urgencia_valida CHECK (urgencia IN ('normal', 'advertencia', 'urgente', 'listo')),
    CONSTRAINT chk_comanda_estado_valido CHECK (
        estado IN ('Pendiente', 'En preparación', 'Preparado', 'Listo', 'Entregado')
    )
);

CREATE INDEX IF NOT EXISTS idx_comandas_area ON comandas_produccion(area_destino);
CREATE INDEX IF NOT EXISTS idx_comandas_estado ON comandas_produccion(estado);

-- =============================================================================
-- 12. TABLA: fiados_personal (Cuentas Corrientes Colaboradores)
-- =============================================================================
CREATE TABLE IF NOT EXISTS fiados_personal (
    id BIGSERIAL PRIMARY KEY,
    rut VARCHAR(15) UNIQUE NOT NULL,
    trabajador VARCHAR(150) NOT NULL,
    cargo_grupo VARCHAR(100) NOT NULL,
    limite_credito INTEGER NOT NULL DEFAULT 50000,
    total_acumulado INTEGER NOT NULL DEFAULT 0,
    consumos_mes INTEGER NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'Al día',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fiado_limite_no_negativo CHECK (limite_credito >= 0),
    CONSTRAINT chk_fiado_acumulado_no_negativo CHECK (total_acumulado >= 0),
    CONSTRAINT chk_fiado_consumos_mes_no_negativo CHECK (consumos_mes >= 0),
    CONSTRAINT chk_fiado_estado_valido CHECK (estado IN ('Al día', 'Por descontar', 'Excedido', 'Bloqueado'))
);

CREATE INDEX IF NOT EXISTS idx_fiados_rut ON fiados_personal(rut);
CREATE INDEX IF NOT EXISTS idx_fiados_estado ON fiados_personal(estado);

-- =============================================================================
-- 13. TABLA: fiados_movimientos (Historial de Vales, Cargos y Abonos)
-- =============================================================================
CREATE TABLE IF NOT EXISTS fiados_movimientos (
    id BIGSERIAL PRIMARY KEY,
    fiado_id BIGINT NOT NULL REFERENCES fiados_personal(id) ON DELETE CASCADE,
    venta_id BIGINT NULL REFERENCES ventas(id) ON DELETE SET NULL,
    detalle VARCHAR(255) NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1,
    monto INTEGER NOT NULL, -- Positivo para cargos de consumo; negativo permitido para abonos/descuentos por planilla
    fecha TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fiado_mov_cantidad_positiva CHECK (cantidad > 0),
    CONSTRAINT chk_fiado_mov_monto_no_cero CHECK (monto <> 0)
);

CREATE INDEX IF NOT EXISTS idx_fiados_movimientos_fiado ON fiados_movimientos(fiado_id);

-- =============================================================================
-- 14. TABLA: log_auditoria (Trazabilidad Operativa y de Seguridad)
-- =============================================================================
CREATE TABLE IF NOT EXISTS log_auditoria (
    id BIGSERIAL PRIMARY KEY,
    usuario_id BIGINT NULL REFERENCES usuarios(id) ON DELETE SET NULL,
    accion VARCHAR(50) NOT NULL,
    modulo VARCHAR(50) NOT NULL,
    descripcion TEXT NOT NULL,
    ip_origen INET NULL,
    fecha_hora TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 15. TABLA: configuracion_pos (Parámetros Generales de Empresa y Terminal)
-- =============================================================================
CREATE TABLE IF NOT EXISTS configuracion_pos (
    id BIGSERIAL PRIMARY KEY,
    nombre_parque VARCHAR(100) NOT NULL DEFAULT 'Parque Safari Rancagua',
    razon_social VARCHAR(150) NOT NULL DEFAULT 'Parque Safari Chile S.A.',
    rut VARCHAR(20) NOT NULL DEFAULT '76.123.456-7',
    direccion VARCHAR(200) NOT NULL DEFAULT 'Ruta Travesía Km 82, Rancagua',
    telefono VARCHAR(50) NOT NULL DEFAULT '+56 72 258 3100',
    terminal_caja VARCHAR(100) NOT NULL DEFAULT 'Terminal POS 01',
    impresora_tickets VARCHAR(100) NOT NULL DEFAULT 'Epson TM-T20II (USB)',
    impresora_cocina VARCHAR(100) NOT NULL DEFAULT 'Bixolon SRP-330II (Red Local)',
    impresora_bar VARCHAR(100) NOT NULL DEFAULT 'Epson TM-T20II (Red Local)',
    iva_incluido BOOLEAN NOT NULL DEFAULT TRUE,
    iva_porcentaje NUMERIC(5, 2) NOT NULL DEFAULT 19.00,
    modo_offline BOOLEAN NOT NULL DEFAULT TRUE,
    sonido_comandas BOOLEAN NOT NULL DEFAULT TRUE,
    resolucion_optimizada VARCHAR(100) NOT NULL DEFAULT 'Touchscreen 15" (1366x768) / 1080p',
    CONSTRAINT chk_config_iva_rango CHECK (iva_porcentaje >= 0 AND iva_porcentaje <= 100)
);
