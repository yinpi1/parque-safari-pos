-- =============================================================================
-- PROYECTO: Sistema Web POS - Parque Safari Chile
-- ETAPA: Script DDL de Base de Datos Relacional para PostgreSQL
-- MOTOR RECOMENDADO: PostgreSQL 14+ / Neon / Supabase
-- FECHA: Octubre 2026
-- =============================================================================

-- 0. Limpieza previa (opcional, para entornos de desarrollo)
DROP TABLE IF EXISTS fiados_movimientos CASCADE;
DROP TABLE IF EXISTS fiados_personal CASCADE;
DROP TABLE IF EXISTS comandas_produccion CASCADE;
DROP TABLE IF EXISTS detalle_ventas CASCADE;
DROP TABLE IF EXISTS ventas CASCADE;
DROP TABLE IF EXISTS mesas CASCADE;
DROP TABLE IF EXISTS menus_combos CASCADE;
DROP TABLE IF EXISTS productos CASCADE;
DROP TABLE IF EXISTS categorias CASCADE;
DROP TABLE IF EXISTS usuarios CASCADE;
DROP TABLE IF EXISTS cargos CASCADE;
DROP TABLE IF EXISTS configuracion_pos CASCADE;

-- =============================================================================
-- 1. TABLA: cargos (Roles y Niveles de Acceso)
-- =============================================================================
CREATE TABLE cargos (
    id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL,
    descripcion TEXT,
    nivel VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE cargos IS 'Roles de usuarios del sistema POS (Cajero, Garzón, Cocina, Bar, Administrador)';

-- =============================================================================
-- 2. TABLA: usuarios (Colaboradores que acceden al sistema)
-- =============================================================================
CREATE TABLE usuarios (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    usuario VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL DEFAULT 'pbkdf2_sha256$600000$default_insecure_hash',
    cargo_id VARCHAR(20) NOT NULL REFERENCES cargos(id) ON UPDATE CASCADE,
    caja_asignada VARCHAR(100) DEFAULT 'Sin asignar',
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Inactivo', 'Suspendido')),
    ultimo_acceso TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_usuarios_cargo ON usuarios(cargo_id);
CREATE INDEX idx_usuarios_estado ON usuarios(estado);

-- =============================================================================
-- 3. TABLA: categorias (Categorías de Productos del Parque)
-- =============================================================================
CREATE TABLE categorias (
    id VARCHAR(30) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    icono VARCHAR(50) NOT NULL DEFAULT 'bi-grid-fill',
    color VARCHAR(30) NOT NULL DEFAULT 'primary',
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- =============================================================================
-- 4. TABLA: productos (Catálogo de Productos)
-- =============================================================================
CREATE TABLE productos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    categoria_id VARCHAR(30) NOT NULL REFERENCES categorias(id) ON UPDATE CASCADE,
    precio INTEGER NOT NULL CHECK (precio >= 0),
    tipo VARCHAR(50) NOT NULL DEFAULT 'Producto listo' CHECK (tipo IN ('Requiere preparación', 'Producto listo')),
    destino VARCHAR(30) NOT NULL DEFAULT 'Directo' CHECK (destino IN ('Cocina', 'Bar', 'Directo')),
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Inactivo', 'Agotado')),
    badge_tipo VARCHAR(30) NOT NULL DEFAULT 'badge-listo',
    descripcion TEXT,
    icono VARCHAR(50) DEFAULT 'bi-box2-heart',
    imagen_placeholder VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_productos_categoria ON productos(categoria_id);
CREATE INDEX idx_productos_destino ON productos(destino);
CREATE INDEX idx_productos_estado ON productos(estado);

-- =============================================================================
-- 5. TABLA: menus_combos (Packs Promocionales y Combos)
-- =============================================================================
CREATE TABLE menus_combos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    productos_incluidos TEXT NOT NULL,
    precio INTEGER NOT NULL CHECK (precio >= 0),
    ahorro_estimado INTEGER DEFAULT 0,
    categoria VARCHAR(50) DEFAULT 'Combos',
    disponibilidad VARCHAR(100) DEFAULT 'Todo el día',
    estado VARCHAR(20) NOT NULL DEFAULT 'Activo' CHECK (estado IN ('Activo', 'Inactivo')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- 6. TABLA: mesas (Zonas y Mesas de Atención)
-- =============================================================================
CREATE TABLE mesas (
    id SERIAL PRIMARY KEY,
    numero VARCHAR(20) UNIQUE NOT NULL,
    zona VARCHAR(50) NOT NULL CHECK (zona IN ('Salón Principal', 'Terraza Jirafas', 'Sector Familiar', 'Sector Mirador')),
    capacidad INTEGER NOT NULL CHECK (capacidad > 0),
    estado VARCHAR(20) NOT NULL DEFAULT 'Disponible' CHECK (estado IN ('Disponible', 'Ocupada', 'Reservada', 'Mantenimiento')),
    consumo_actual INTEGER DEFAULT 0,
    mozo_asignado_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    comensales_actuales INTEGER DEFAULT 0,
    hora_inicio_ocupacion TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_mesas_zona ON mesas(zona);
CREATE INDEX idx_mesas_estado ON mesas(estado);

-- =============================================================================
-- 7. TABLA: ventas (Cabecera de Tickets / Boletas de Venta)
-- =============================================================================
CREATE TABLE ventas (
    id SERIAL PRIMARY KEY,
    venta_num VARCHAR(20) UNIQUE NOT NULL,
    fecha_hora TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    modalidad VARCHAR(30) NOT NULL CHECK (modalidad IN ('MESA', 'BAR', 'DELIVERY', 'PARA LLEVAR')),
    mesa_id INTEGER REFERENCES mesas(id) ON DELETE SET NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
    iva INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL CHECK (total >= 0),
    metodo_pago VARCHAR(50) NOT NULL DEFAULT 'Efectivo' CHECK (metodo_pago IN ('Efectivo', 'Tarjeta Débito', 'Tarjeta Crédito', 'Vale Fiado', 'Transferencia')),
    estado VARCHAR(30) NOT NULL DEFAULT 'Pagado' CHECK (estado IN ('Pendiente', 'Pagado', 'Anulado', 'Cortesía')),
    notas TEXT
);

CREATE INDEX idx_ventas_fecha ON ventas(fecha_hora);
CREATE INDEX idx_ventas_usuario ON ventas(usuario_id);
CREATE INDEX idx_ventas_modalidad ON ventas(modalidad);

-- =============================================================================
-- 8. TABLA: detalle_ventas (Líneas de Producto por Venta)
-- =============================================================================
CREATE TABLE detalle_ventas (
    id SERIAL PRIMARY KEY,
    venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id INTEGER REFERENCES productos(id) ON DELETE RESTRICT,
    menu_id INTEGER REFERENCES menus_combos(id) ON DELETE RESTRICT,
    cantidad INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario INTEGER NOT NULL CHECK (precio_unitario >= 0),
    subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
    destino VARCHAR(30) NOT NULL CHECK (destino IN ('COCINA', 'BAR', 'ENTREGA INMEDIATA')),
    estado_produccion VARCHAR(30) NOT NULL DEFAULT 'Pendiente' CHECK (estado_produccion IN ('Pendiente', 'En preparación', 'Preparado', 'Listo', 'Entregado')),
    notas_preparacion TEXT,
    CONSTRAINT chk_producto_o_menu CHECK (producto_id IS NOT NULL OR menu_id IS NOT NULL)
);

CREATE INDEX idx_detalle_ventas_venta ON detalle_ventas(venta_id);
CREATE INDEX idx_detalle_ventas_destino ON detalle_ventas(destino);

-- =============================================================================
-- 9. TABLA: comandas_produccion (KDS Cocina y BDS Bar)
-- =============================================================================
CREATE TABLE comandas_produccion (
    id VARCHAR(20) PRIMARY KEY, -- ej: 'C-142', 'B-142'
    venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    area_destino VARCHAR(20) NOT NULL CHECK (area_destino IN ('COCINA', 'BAR')),
    urgencia VARCHAR(20) NOT NULL DEFAULT 'normal' CHECK (urgencia IN ('normal', 'advertencia', 'urgente', 'listo')),
    estado VARCHAR(30) NOT NULL DEFAULT 'Pendiente' CHECK (estado IN ('Pendiente', 'En preparación', 'Preparado', 'Listo', 'Entregado')),
    comentarios TEXT,
    fecha_hora_ingreso TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    fecha_hora_despacho TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_comandas_area ON comandas_produccion(area_destino);
CREATE INDEX idx_comandas_estado ON comandas_produccion(estado);

-- =============================================================================
-- 10. TABLA: fiados_personal (Cuentas Corrientes Colaboradores)
-- =============================================================================
CREATE TABLE fiados_personal (
    id SERIAL PRIMARY KEY,
    rut VARCHAR(15) UNIQUE NOT NULL,
    trabajador VARCHAR(150) NOT NULL,
    cargo_grupo VARCHAR(100) NOT NULL,
    limite_credito INTEGER NOT NULL DEFAULT 50000 CHECK (limite_credito >= 0),
    total_acumulado INTEGER NOT NULL DEFAULT 0 CHECK (total_acumulado >= 0),
    consumos_mes INTEGER NOT NULL DEFAULT 0,
    estado VARCHAR(30) NOT NULL DEFAULT 'Al día' CHECK (estado IN ('Al día', 'Por descontar', 'Excedido', 'Bloqueado')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fiados_rut ON fiados_personal(rut);
CREATE INDEX idx_fiados_estado ON fiados_personal(estado);

-- =============================================================================
-- 11. TABLA: fiados_movimientos (Historial de Vales y Consumos)
-- =============================================================================
CREATE TABLE fiados_movimientos (
    id SERIAL PRIMARY KEY,
    fiado_id INTEGER NOT NULL REFERENCES fiados_personal(id) ON DELETE CASCADE,
    venta_id INTEGER REFERENCES ventas(id) ON DELETE SET NULL,
    detalle VARCHAR(255) NOT NULL,
    cantidad INTEGER NOT NULL DEFAULT 1 CHECK (cantidad > 0),
    monto INTEGER NOT NULL CHECK (monto >= 0),
    fecha TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fiados_movimientos_fiado ON fiados_movimientos(fiado_id);

-- =============================================================================
-- 12. TABLA: configuracion_pos (Parámetros Generales de Empresa y Terminal)
-- =============================================================================
CREATE TABLE configuracion_pos (
    id SERIAL PRIMARY KEY,
    nombre_parque VARCHAR(100) NOT NULL,
    razon_social VARCHAR(150) NOT NULL,
    rut VARCHAR(20) NOT NULL,
    direccion VARCHAR(200) NOT NULL,
    telefono VARCHAR(50) NOT NULL,
    terminal_caja VARCHAR(100) NOT NULL,
    impresora_tickets VARCHAR(100),
    impresora_cocina VARCHAR(100),
    impresora_bar VARCHAR(100),
    iva_incluido BOOLEAN NOT NULL DEFAULT TRUE,
    iva_porcentaje NUMERIC(5, 2) NOT NULL DEFAULT 19.00,
    modo_offline BOOLEAN NOT NULL DEFAULT TRUE,
    sonido_comandas BOOLEAN NOT NULL DEFAULT TRUE,
    resolucion_optimizada VARCHAR(100)
);
