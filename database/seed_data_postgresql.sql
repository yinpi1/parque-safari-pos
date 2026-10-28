-- =============================================================================
-- PROYECTO: Sistema Web POS - Parque Safari Chile
-- ETAPA: Script DML de Carga Inicial (Seed Data) para PostgreSQL
-- MOTOR RECOMENDADO: PostgreSQL 14+ / Neon / Supabase
-- FECHA: Octubre 2026
-- =============================================================================

-- =============================================================================
-- 1. CARGA DE CARGOS / ROLES
-- =============================================================================
INSERT INTO cargos (id, nombre, descripcion, nivel) VALUES
('cajero', 'Cajero', 'Acceso al Punto de Venta, cobro en efectivo/tarjetas, arqueo diario, consulta de tickets.', 'Operativo POS'),
('vendedor', 'Vendedor / Garzón', 'Toma de pedidos en mesas o bar, emisión de comandas a cocina y bar, reasignación de mesas.', 'Operativo Móvil'),
('cocina', 'Cocina (KDS)', 'Visualización de pedidos calientes y fríos que requieren preparación, cambio de estado de preparación.', 'Producción'),
('bar', 'Bar (BDS)', 'Visualización de comandas de líquidos, cafés, cervezas y postres, despacho expedito de barra.', 'Despacho Líquidos'),
('administrador', 'Administrador', 'Acceso global al sistema, gestión de precios, creación de usuarios, reportes, estadísticas y configuración.', 'Gestión Total')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, descripcion = EXCLUDED.descripcion, nivel = EXCLUDED.nivel;

-- =============================================================================
-- 2. CARGA DE USUARIOS
-- =============================================================================
INSERT INTO usuarios (id, nombre, usuario, email, password_hash, cargo_id, caja_asignada, estado, ultimo_acceso) VALUES
(1, 'Jean Valenzuela', 'jvalenzuela', 'j.valenzuela@parquesafari.cl', 'pbkdf2_sha256$600000$cajero123', 'cajero', 'Caja 01 - Principal', 'Activo', CURRENT_TIMESTAMP),
(2, 'Carlos Mendoza', 'cmendoza', 'c.mendoza@parquesafari.cl', 'pbkdf2_sha256$600000$admin123', 'administrador', 'Todas', 'Activo', CURRENT_TIMESTAMP),
(3, 'Camila Silva', 'csilva', 'c.silva@parquesafari.cl', 'pbkdf2_sha256$600000$vendedor123', 'vendedor', 'Caja Móvil 02', 'Activo', CURRENT_TIMESTAMP),
(4, 'Rodrigo Morales', 'rmorales', 'r.morales@parquesafari.cl', 'pbkdf2_sha256$600000$vendedor123', 'vendedor', 'Caja Móvil 03', 'Activo', CURRENT_TIMESTAMP),
(5, 'Matías Torres', 'mtorres', 'm.torres@parquesafari.cl', 'pbkdf2_sha256$600000$cocina123', 'cocina', 'Terminal KDS Cocina', 'Activo', CURRENT_TIMESTAMP),
(6, 'Patricia Gómez', 'pgomez', 'p.gomez@parquesafari.cl', 'pbkdf2_sha256$600000$bar123', 'bar', 'Terminal BDS Bar', 'Activo', CURRENT_TIMESTAMP),
(7, 'Esteban Soto', 'esoto', 'e.soto@parquesafari.cl', 'pbkdf2_sha256$600000$cajero123', 'cajero', 'Sin asignar', 'Inactivo', CURRENT_TIMESTAMP - INTERVAL '20 days')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, cargo_id = EXCLUDED.cargo_id;

SELECT setval('usuarios_id_seq', (SELECT MAX(id) FROM usuarios));

-- =============================================================================
-- 3. CARGA DE CATEGORÍAS
-- =============================================================================
INSERT INTO categorias (id, nombre, icono, color, activo) VALUES
('todas', 'Todas las Categorías', 'bi-grid-fill', 'primary', true),
('comidas', 'Comidas y Platos', 'bi-egg-fried', 'warning', true),
('bebidas', 'Bebidas y Líquidos', 'bi-cup-straw', 'info', true),
('snacks', 'Snacks y Picoteo', 'bi-cookie', 'secondary', true),
('helados', 'Helados y Postres', 'bi-snow', 'danger', true),
('combos', 'Menús & Combos', 'bi-stars', 'success', true)
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre;

-- =============================================================================
-- 4. CARGA DE PRODUCTOS DEL PARQUE
-- =============================================================================
INSERT INTO productos (id, codigo, nombre, categoria_id, precio, tipo, destino, estado, badge_tipo, descripcion, icono, imagen_placeholder) VALUES
(1, 'COM-001', 'Hamburguesa Safari Especial', 'comidas', 6990, 'Requiere preparación', 'Cocina', 'Activo', 'badge-cocina', 'Carne vacuna 200g, queso cheddar, tocino ahumado, cebolla caramelizada y salsa especial safari.', 'bi-fire', 'burger'),
(2, 'COM-002', 'Churrasco León Italiano', 'comidas', 7490, 'Requiere preparación', 'Cocina', 'Activo', 'badge-cocina', 'Finas láminas de vacuno, abundante palta hass molida, tomate fresco y mayonesa casera.', 'bi-fire', 'churrasco'),
(3, 'COM-003', 'Completo Safari Gigante', 'comidas', 3200, 'Requiere preparación', 'Cocina', 'Activo', 'badge-cocina', 'Salchicha premium 22cm, tomate picado, chucrut, palta y mayo artesanal en pan tostado.', 'bi-fire', 'hotdog'),
(4, 'COM-004', 'Papas Fritas Rústicas Safari', 'comidas', 3500, 'Requiere preparación', 'Cocina', 'Activo', 'badge-cocina', 'Papas con cáscara doble cocción condimentadas con hierbas de la sabana y sal de mar.', 'bi-fire', 'fries'),
(5, 'COM-005', 'Empanada de Pino al Horno', 'comidas', 2800, 'Producto listo', 'Directo', 'Activo', 'badge-listo', 'Tradicional pino de carne picada, cebolla tierna, huevo duro, aceituna y pasas.', 'bi-box2-heart', 'empanada'),
(6, 'BEB-001', 'Jugo Natural Guayaba-Mango 500ml', 'bebidas', 3200, 'Requiere preparación', 'Bar', 'Activo', 'badge-bar', 'Pulpa 100% natural frappé con hielo y un toque refrescante de menta.', 'bi-cup-straw', 'juice'),
(7, 'BEB-002', 'Cerveza Artesanal Safari Golden 330cc', 'bebidas', 4200, 'Requiere preparación', 'Bar', 'Activo', 'badge-bar', 'Schop tirado en vaso frío cervecero con notas a malta rubia y cítricos.', 'bi-cup-straw', 'beer'),
(8, 'BEB-003', 'Bebida Coca-Cola Original 500ml', 'bebidas', 1800, 'Producto listo', 'Directo', 'Activo', 'badge-listo', 'Botella individual sellada helada.', 'bi-box2-heart', 'coke'),
(9, 'BEB-004', 'Bebida Sprite Zero 500ml', 'bebidas', 1800, 'Producto listo', 'Directo', 'Activo', 'badge-listo', 'Botella individual sellada helada sin azúcar.', 'bi-box2-heart', 'sprite'),
(10, 'BEB-005', 'Café Espresso Doble / Cortado', 'bebidas', 2200, 'Requiere preparación', 'Bar', 'Activo', 'badge-bar', 'Granos arábica recién molidos servido en taza térmica o cerámica.', 'bi-cup-hot', 'coffee'),
(11, 'SNA-001', 'Nachos con Queso Cheddar & Guacamole', 'snacks', 3900, 'Requiere preparación', 'Cocina', 'Activo', 'badge-cocina', 'Totopos de maíz crujientes horneados con dip cheddar fundido y guacamole.', 'bi-fire', 'nachos'),
(12, 'SNA-002', 'Popcorn Safari Dulce Gigante', 'snacks', 2500, 'Producto listo', 'Directo', 'Activo', 'badge-listo', 'Balde conmemorativo Parque Safari con cabritas dulces recién acarameladas.', 'bi-box2-heart', 'popcorn'),
(13, 'HEL-001', 'Helado Paleta Selva Artesanal', 'helados', 2500, 'Producto listo', 'Directo', 'Activo', 'badge-listo', 'Paleta artesanal de frutos del bosque bañada en chocolate crujiente.', 'bi-box2-heart', 'popsicle'),
(14, 'HEL-002', 'Copa Sundae León Chocolate Aventura', 'helados', 3800, 'Requiere preparación', 'Bar', 'Activo', 'badge-bar', 'Bolas de helado crema americana, salsa fudge tibia, crema chantilly y barquillo.', 'bi-cup-straw', 'sundae')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, precio = EXCLUDED.precio;

SELECT setval('productos_id_seq', (SELECT MAX(id) FROM productos));

-- =============================================================================
-- 5. CARGA DE MENÚS Y COMBOS
-- =============================================================================
INSERT INTO menus_combos (id, codigo, nombre, productos_incluidos, precio, ahorro_estimado, categoria, disponibilidad, estado) VALUES
(1, 'MENU-SAF-01', 'Menú Safari Aventura', 'Hamburguesa Safari Especial + Papas Fritas Rústicas + Bebida 500ml', 9990, 2290, 'Combos', 'Todo el día', 'Activo'),
(2, 'MENU-SAF-02', 'Pack Explorador León', 'Churrasco Italiano + Jugo Natural Guayaba-Mango + Copa Sundae', 11500, 2990, 'Combos', 'Almuerzo y Tarde', 'Activo'),
(3, 'MENU-SAF-03', 'Combo Safari Kids', 'Completo Gigante + Jugo en caja + Helado Paleta Selva + Juguete Animalito', 6500, 1700, 'Infantil', 'Todo el día', 'Activo'),
(4, 'MENU-SAF-04', 'Dúo Picoteo Sabana', 'Nachos con Queso Cheddar & Guacamole + 2 Schop Cerveza Safari Golden', 10990, 1310, 'Bar & Snacks', 'Desde las 13:00 hrs', 'Activo')
ON CONFLICT (id) DO UPDATE SET nombre = EXCLUDED.nombre, precio = EXCLUDED.precio;

SELECT setval('menus_combos_id_seq', (SELECT MAX(id) FROM menus_combos));

-- =============================================================================
-- 6. CARGA DE MESAS Y ZONAS
-- =============================================================================
INSERT INTO mesas (id, numero, zona, capacidad, estado, consumo_actual, mozo_asignado_id, comensales_actuales) VALUES
(1, 'Mesa 01', 'Salón Principal', 4, 'Ocupada', 24500, 4, 4),
(2, 'Mesa 02', 'Salón Principal', 2, 'Disponible', 0, NULL, 0),
(3, 'Mesa 03', 'Salón Principal', 4, 'Ocupada', 14690, 3, 3),
(4, 'Mesa 04', 'Salón Principal', 6, 'Disponible', 0, NULL, 0),
(5, 'Mesa 05', 'Terraza Jirafas', 4, 'Disponible', 0, NULL, 0),
(6, 'Mesa 06', 'Terraza Jirafas', 6, 'Ocupada', 48200, 4, 5),
(7, 'Mesa 07', 'Terraza Jirafas', 4, 'Disponible', 0, NULL, 0),
(8, 'Mesa 08', 'Sector Familiar', 2, 'Disponible', 0, NULL, 0),
(9, 'Mesa 09', 'Sector Familiar', 4, 'Ocupada', 18900, 3, 4),
(10, 'Mesa 10', 'Sector Mirador', 8, 'Disponible', 0, NULL, 0),
(11, 'Mesa 11', 'Sector Mirador', 4, 'Disponible', 0, NULL, 0),
(12, 'Mesa 12', 'Sector Mirador', 4, 'Ocupada', 31400, 4, 4)
ON CONFLICT (id) DO UPDATE SET numero = EXCLUDED.numero, estado = EXCLUDED.estado;

SELECT setval('mesas_id_seq', (SELECT MAX(id) FROM mesas));

-- =============================================================================
-- 7. CARGA DE FIADOS / CONSUMO DE COLABORADORES
-- =============================================================================
INSERT INTO fiados_personal (id, rut, trabajador, cargo_grupo, limite_credito, total_acumulado, consumos_mes, estado) VALUES
(1, '15.421.890-3', 'Héctor Leal', 'Guía Safari Leones', 50000, 24500, 4, 'Al día'),
(2, '13.882.104-K', 'Dr. Fernando Bravo', 'Veterinario Fauna Mayor', 60000, 18900, 3, 'Al día'),
(3, '17.654.321-8', 'Marcela Rivas', 'Boletería y Acceso', 40000, 8400, 2, 'Al día'),
(4, '16.112.789-5', 'Juan Pablo Ríos', 'Mantenimiento y Parque', 45000, 31200, 6, 'Por descontar'),
(5, '18.334.901-2', 'Rosa Venegas', 'Educación Ambiental', 35000, 5400, 1, 'Al día')
ON CONFLICT (id) DO UPDATE SET trabajador = EXCLUDED.trabajador, total_acumulado = EXCLUDED.total_acumulado;

SELECT setval('fiados_personal_id_seq', (SELECT MAX(id) FROM fiados_personal));

-- =============================================================================
-- 8. CARGA DE HISTORIAL DE CONSUMOS / VALES DE FIADOS
-- =============================================================================
INSERT INTO fiados_movimientos (fiado_id, detalle, cantidad, monto, fecha) VALUES
(1, 'Churrasco León + Bebida 500ml', 2, 9290, CURRENT_TIMESTAMP - INTERVAL '2 hours'),
(2, 'Menú Safari Aventura', 1, 9990, CURRENT_TIMESTAMP - INTERVAL '1 day'),
(3, 'Café Cortado + Empanada Horno', 2, 5000, CURRENT_TIMESTAMP - INTERVAL '4 hours'),
(4, 'Hamburguesa Safari + Bebida', 2, 8790, CURRENT_TIMESTAMP - INTERVAL '3 hours'),
(5, 'Copa Sundae León Chocolate', 1, 3800, CURRENT_TIMESTAMP - INTERVAL '2 days');

-- =============================================================================
-- 9. CARGA DE VENTAS DEMOSTRATIVAS Y COMANDAS KDS / BDS
-- =============================================================================
INSERT INTO ventas (id, venta_num, fecha_hora, modalidad, mesa_id, usuario_id, subtotal, iva, total, metodo_pago, estado) VALUES
(140, '00140', CURRENT_TIMESTAMP - INTERVAL '35 minutes', 'MESA', 6, 4, 40504, 7696, 48200, 'Tarjeta Débito', 'Pagado'),
(141, '00141', CURRENT_TIMESTAMP - INTERVAL '25 minutes', 'BAR', NULL, 1, 12437, 2363, 14800, 'Efectivo', 'Pagado'),
(142, '00142', CURRENT_TIMESTAMP - INTERVAL '10 minutes', 'MESA', 3, 3, 12345, 2345, 14690, 'Tarjeta Débito', 'Pagado')
ON CONFLICT (id) DO NOTHING;

SELECT setval('ventas_id_seq', (SELECT MAX(id) FROM ventas));

-- Detalle de la Venta 142
INSERT INTO detalle_ventas (venta_id, producto_id, cantidad, precio_unitario, subtotal, destino, estado_produccion, notas_preparacion) VALUES
(142, 1, 1, 6990, 6990, 'COCINA', 'En preparación', 'Sin mayonesa'),
(142, 4, 1, 3500, 3500, 'COCINA', 'En preparación', 'Papas extra crocantes'),
(142, 6, 1, 3200, 3200, 'BAR', 'Listo', 'Poco hielo, azúcar normal'),
(142, 8, 1, 1800, 1800, 'ENTREGA INMEDIATA', 'Entregado', NULL);

-- Comandas KDS y BDS
INSERT INTO comandas_produccion (id, venta_id, area_destino, urgencia, estado, comentarios) VALUES
('C-142', 142, 'COCINA', 'normal', 'En preparación', 'Sin mayonesa en la hamburguesa; papas rústicas extra crocantes y con poca sal.'),
('B-142', 142, 'BAR', 'normal', 'Listo', 'Jugo bien helado con bombilla biodegradable.');

-- =============================================================================
-- 10. CARGA DE CONFIGURACIÓN DEL SISTEMA POS
-- =============================================================================
INSERT INTO configuracion_pos (
    id, nombre_parque, razon_social, rut, direccion, telefono,
    terminal_caja, impresora_tickets, impresora_cocina, impresora_bar,
    iva_incluido, iva_porcentaje, modo_offline, sonido_comandas, resolucion_optimizada
) VALUES (
    1,
    'Parque Safari Chile',
    'Inversiones Safari Park Ltda.',
    '76.432.890-5',
    'Ruta H-30 Km 5, Rancagua, Región de O''Higgins',
    '+56 72 258 4000',
    'POS-01 (Caja Principal Zona Safari)',
    'Epson TM-T20III (Térmica 80mm - USB)',
    'Bixolon SRP-350 (Red LAN 192.168.1.50)',
    'Bixolon SRP-350 (Red LAN 192.168.1.51)',
    true,
    19.00,
    true,
    true,
    '1920x1080 Full HD (Pantallas Táctiles)'
)
ON CONFLICT (id) DO UPDATE SET nombre_parque = EXCLUDED.nombre_parque;
