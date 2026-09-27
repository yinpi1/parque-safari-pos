"""
pos_app/mock_data.py
Fuente centralizada de datos simulados para el MVP Visual del Sistema POS - Parque Safari.

IMPORTANTE (Regla de diseño):
Los datos están desacoplados de los templates HTML y se inyectan a través del contexto
de las vistas de Django. Esto facilitará la transición posterior a Django ORM / PostgreSQL / Neon.
"""

# Categorías de productos del Parque Safari
CATEGORIAS = [
    {"id": "todas", "nombre": "Todas las Categorías", "icono": "bi-grid-fill", "color": "primary"},
    {"id": "comidas", "nombre": "Comidas y Platos", "icono": "bi-egg-fried", "color": "warning"},
    {"id": "bebidas", "nombre": "Bebidas y Líquidos", "icono": "bi-cup-straw", "color": "info"},
    {"id": "snacks", "nombre": "Snacks y Picoteo", "icono": "bi-cookie", "color": "secondary"},
    {"id": "helados", "nombre": "Helados y Postres", "icono": "bi-snow", "color": "danger"},
    {"id": "combos", "nombre": "Menús & Combos", "icono": "bi-stars", "color": "success"},
]

# Catálogo de Productos
PRODUCTOS = [
    {
        "id": 1,
        "codigo": "COM-001",
        "nombre": "Hamburguesa Safari Especial",
        "categoria_id": "comidas",
        "categoria_nombre": "Comidas",
        "precio": 6990,
        "precio_formateado": "$6.990",
        "tipo": "Requiere preparación",
        "destino": "Cocina",
        "estado": "Activo",
        "badge_tipo": "badge-cocina",
        "descripcion": "Carne vacuna 200g, queso cheddar, tocino ahumado, cebolla caramelizada y salsa especial safari.",
        "icono": "bi-fire",
        "imagen_placeholder": "burger"
    },
    {
        "id": 2,
        "codigo": "COM-002",
        "nombre": "Churrasco León Italiano",
        "categoria_id": "comidas",
        "categoria_nombre": "Comidas",
        "precio": 7490,
        "precio_formateado": "$7.490",
        "tipo": "Requiere preparación",
        "destino": "Cocina",
        "estado": "Activo",
        "badge_tipo": "badge-cocina",
        "descripcion": "Finas láminas de vacuno, abundante palta hass molida, tomate fresco y mayonesa casera.",
        "icono": "bi-fire",
        "imagen_placeholder": "churrasco"
    },
    {
        "id": 3,
        "codigo": "COM-003",
        "nombre": "Completo Safari Gigante",
        "categoria_id": "comidas",
        "categoria_nombre": "Comidas",
        "precio": 3200,
        "precio_formateado": "$3.200",
        "tipo": "Requiere preparación",
        "destino": "Cocina",
        "estado": "Activo",
        "badge_tipo": "badge-cocina",
        "descripcion": "Salchicha premium 22cm, tomate picado, chucrut, palta y mayo artesanal en pan tostado.",
        "icono": "bi-fire",
        "imagen_placeholder": "hotdog"
    },
    {
        "id": 4,
        "codigo": "COM-004",
        "nombre": "Papas Fritas Rústicas Safari",
        "categoria_id": "comidas",
        "categoria_nombre": "Comidas",
        "precio": 3500,
        "precio_formateado": "$3.500",
        "tipo": "Requiere preparación",
        "destino": "Cocina",
        "estado": "Activo",
        "badge_tipo": "badge-cocina",
        "descripcion": "Papas con cáscara doble cocción condimentadas con hierbas de la sabana y sal de mar.",
        "icono": "bi-fire",
        "imagen_placeholder": "fries"
    },
    {
        "id": 5,
        "codigo": "COM-005",
        "nombre": "Empanada de Pino al Horno",
        "categoria_id": "comidas",
        "categoria_nombre": "Comidas",
        "precio": 2800,
        "precio_formateado": "$2.800",
        "tipo": "Producto listo",
        "destino": "Directo",
        "estado": "Activo",
        "badge_tipo": "badge-listo",
        "descripcion": "Tradicional pino de carne picada, cebolla tierna, huevo duro, aceituna y pasas.",
        "icono": "bi-box2-heart",
        "imagen_placeholder": "empanada"
    },
    {
        "id": 6,
        "codigo": "BEB-001",
        "nombre": "Jugo Natural Guayaba-Mango 500ml",
        "categoria_id": "bebidas",
        "categoria_nombre": "Bebidas",
        "precio": 3200,
        "precio_formateado": "$3.200",
        "tipo": "Requiere preparación",
        "destino": "Bar",
        "badge_tipo": "badge-bar",
        "estado": "Activo",
        "descripcion": "Pulpa 100% natural frappé con hielo y un toque refrescante de menta.",
        "icono": "bi-cup-straw",
        "imagen_placeholder": "juice"
    },
    {
        "id": 7,
        "codigo": "BEB-002",
        "nombre": "Cerveza Artesanal Safari Golden 330cc",
        "categoria_id": "bebidas",
        "categoria_nombre": "Bebidas",
        "precio": 4200,
        "precio_formateado": "$4.200",
        "tipo": "Requiere preparación",
        "destino": "Bar",
        "badge_tipo": "badge-bar",
        "estado": "Activo",
        "descripcion": "Schop tirado en vaso frío cervecero con notas a malta rubia y cítricos.",
        "icono": "bi-cup-straw",
        "imagen_placeholder": "beer"
    },
    {
        "id": 8,
        "codigo": "BEB-003",
        "nombre": "Bebida Coca-Cola Original 500ml",
        "categoria_id": "bebidas",
        "categoria_nombre": "Bebidas",
        "precio": 1800,
        "precio_formateado": "$1.800",
        "tipo": "Producto listo",
        "destino": "Directo",
        "badge_tipo": "badge-listo",
        "estado": "Activo",
        "descripcion": "Botella individual sellada helada.",
        "icono": "bi-box2-heart",
        "imagen_placeholder": "coke"
    },
    {
        "id": 9,
        "codigo": "BEB-004",
        "nombre": "Bebida Sprite Zero 500ml",
        "categoria_id": "bebidas",
        "categoria_nombre": "Bebidas",
        "precio": 1800,
        "precio_formateado": "$1.800",
        "tipo": "Producto listo",
        "destino": "Directo",
        "badge_tipo": "badge-listo",
        "estado": "Activo",
        "descripcion": "Botella individual sellada helada sin azúcar.",
        "icono": "bi-box2-heart",
        "imagen_placeholder": "sprite"
    },
    {
        "id": 10,
        "codigo": "BEB-005",
        "nombre": "Café Espresso Doble / Cortado",
        "categoria_id": "bebidas",
        "categoria_nombre": "Bebidas",
        "precio": 2200,
        "precio_formateado": "$2.200",
        "tipo": "Requiere preparación",
        "destino": "Bar",
        "badge_tipo": "badge-bar",
        "estado": "Activo",
        "descripcion": "Granos arábica recién molidos servido en taza térmica o cerámica.",
        "icono": "bi-cup-hot",
        "imagen_placeholder": "coffee"
    },
    {
        "id": 11,
        "codigo": "SNA-001",
        "nombre": "Nachos con Queso Cheddar & Guacamole",
        "categoria_id": "snacks",
        "categoria_nombre": "Snacks",
        "precio": 3900,
        "precio_formateado": "$3.900",
        "tipo": "Requiere preparación",
        "destino": "Cocina",
        "badge_tipo": "badge-cocina",
        "estado": "Activo",
        "descripcion": "Totopos de maíz crujientes horneados con dip cheddar fundido y guacamole.",
        "icono": "bi-fire",
        "imagen_placeholder": "nachos"
    },
    {
        "id": 12,
        "codigo": "SNA-002",
        "nombre": "Popcorn Safari Dulce Gigante",
        "categoria_id": "snacks",
        "categoria_nombre": "Snacks",
        "precio": 2500,
        "precio_formateado": "$2.500",
        "tipo": "Producto listo",
        "destino": "Directo",
        "badge_tipo": "badge-listo",
        "estado": "Activo",
        "descripcion": "Balde conmemorativo Parque Safari con cabritas dulces recién acarameladas.",
        "icono": "bi-box2-heart",
        "imagen_placeholder": "popcorn"
    },
    {
        "id": 13,
        "codigo": "HEL-001",
        "nombre": "Helado Paleta Selva Artesanal",
        "categoria_id": "helados",
        "categoria_nombre": "Helados",
        "precio": 2500,
        "precio_formateado": "$2.500",
        "tipo": "Producto listo",
        "destino": "Directo",
        "badge_tipo": "badge-listo",
        "estado": "Activo",
        "descripcion": "Paleta artesanal de frutos del bosque bañada en chocolate crujiente.",
        "icono": "bi-box2-heart",
        "imagen_placeholder": "popsicle"
    },
    {
        "id": 14,
        "codigo": "HEL-002",
        "nombre": "Copa Sundae León Chocolate Aventura",
        "categoria_id": "helados",
        "categoria_nombre": "Helados",
        "precio": 3800,
        "precio_formateado": "$3.800",
        "tipo": "Requiere preparación",
        "destino": "Bar",
        "badge_tipo": "badge-bar",
        "estado": "Activo",
        "descripcion": "Bolas de helado crema americana, salsa fudge tibia, crema chantilly y barquillo.",
        "icono": "bi-cup-straw",
        "imagen_placeholder": "sundae"
    },
]

# Menús y Combos Promocionales
MENUS = [
    {
        "id": 1,
        "codigo": "MENU-SAF-01",
        "nombre": "Menú Safari Aventura",
        "productos_incluidos": "Hamburguesa Safari Especial + Papas Fritas Rústicas + Bebida 500ml",
        "precio": 9990,
        "precio_formateado": "$9.990",
        "ahorro": "Ahorro $2.290",
        "estado": "Activo",
        "categoria": "Combos",
        "disponibilidad": "Todo el día"
    },
    {
        "id": 2,
        "codigo": "MENU-SAF-02",
        "nombre": "Pack Explorador León",
        "productos_incluidos": "Churrasco Italiano + Jugo Natural Guayaba-Mango + Copa Sundae",
        "precio": 11500,
        "precio_formateado": "$11.500",
        "ahorro": "Ahorro $2.990",
        "estado": "Activo",
        "categoria": "Combos",
        "disponibilidad": "Almuerzo y Tarde"
    },
    {
        "id": 3,
        "codigo": "MENU-SAF-03",
        "nombre": "Combo Safari Kids",
        "productos_incluidos": "Completo Gigante + Jugo en caja + Helado Paleta Selva + Juguete Animalito",
        "precio": 6500,
        "precio_formateado": "$6.500",
        "ahorro": "Ahorro $1.700",
        "estado": "Activo",
        "categoria": "Infantil",
        "disponibilidad": "Todo el día"
    },
    {
        "id": 4,
        "codigo": "MENU-SAF-04",
        "nombre": "Dúo Picoteo Sabana",
        "productos_incluidos": "Nachos con Queso Cheddar & Guacamole + 2 Schop Cerveza Safari Golden",
        "precio": 10990,
        "precio_formateado": "$10.990",
        "ahorro": "Ahorro $1.310",
        "estado": "Activo",
        "categoria": "Bar & Snacks",
        "disponibilidad": "Desde las 13:00 hrs"
    },
]

# Mapa / Listado de Mesas del Parque
MESAS = [
    {"id": 1, "numero": "Mesa 01", "zona": "Salón Principal", "capacidad": 4, "estado": "Ocupada", "inicio": "12:15", "tiempo_transcurrido": "38 min", "consumo_actual": "$24.500", "mozo": "Rodrigo Morales", "comensales": 4},
    {"id": 2, "numero": "Mesa 02", "zona": "Salón Principal", "capacidad": 2, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 3, "numero": "Mesa 03", "zona": "Salón Principal", "capacidad": 4, "estado": "Ocupada", "inicio": "12:35", "tiempo_transcurrido": "18 min", "consumo_actual": "$14.690", "mozo": "Camila Silva", "comensales": 3},
    {"id": 4, "numero": "Mesa 04", "zona": "Salón Principal", "capacidad": 6, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 5, "numero": "Mesa 05", "zona": "Terraza Jirafas", "capacidad": 4, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 6, "numero": "Mesa 06", "zona": "Terraza Jirafas", "capacidad": 6, "estado": "Ocupada", "inicio": "12:02", "tiempo_transcurrido": "51 min", "consumo_actual": "$48.200", "mozo": "Rodrigo Morales", "comensales": 5},
    {"id": 7, "numero": "Mesa 07", "zona": "Terraza Jirafas", "capacidad": 4, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 8, "numero": "Mesa 08", "zona": "Sector Familiar", "capacidad": 2, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 9, "numero": "Mesa 09", "zona": "Sector Familiar", "capacidad": 4, "estado": "Ocupada", "inicio": "12:40", "tiempo_transcurrido": "13 min", "consumo_actual": "$18.900", "mozo": "Camila Silva", "comensales": 4},
    {"id": 10, "numero": "Mesa 10", "zona": "Sector Mirador", "capacidad": 8, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 11, "numero": "Mesa 11", "zona": "Sector Mirador", "capacidad": 4, "estado": "Disponible", "inicio": "-", "tiempo_transcurrido": "-", "consumo_actual": "$0", "mozo": "-", "comensales": 0},
    {"id": 12, "numero": "Mesa 12", "zona": "Sector Mirador", "capacidad": 4, "estado": "Ocupada", "inicio": "12:10", "tiempo_transcurrido": "43 min", "consumo_actual": "$31.400", "mozo": "Rodrigo Morales", "comensales": 4},
]

# Usuarios y Colaboradores del Sistema
USUARIOS = [
    {"id": 1, "nombre": "Jean Valenzuela", "usuario": "jvalenzuela", "cargo": "Cajero", "email": "j.valenzuela@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:30", "caja_asignada": "Caja 01 - Principal"},
    {"id": 2, "nombre": "Carlos Mendoza", "usuario": "cmendoza", "cargo": "Administrador", "email": "c.mendoza@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:00", "caja_asignada": "Todas"},
    {"id": 3, "nombre": "Camila Silva", "usuario": "csilva", "cargo": "Vendedor", "email": "c.silva@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:45", "caja_asignada": "Caja Móvil 02"},
    {"id": 4, "nombre": "Rodrigo Morales", "usuario": "rmorales", "cargo": "Vendedor", "email": "r.morales@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:50", "caja_asignada": "Caja Móvil 03"},
    {"id": 5, "nombre": "Matías Torres", "usuario": "mtorres", "cargo": "Cocina", "email": "m.torres@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:15", "caja_asignada": "Terminal KDS Cocina"},
    {"id": 6, "nombre": "Patricia Gómez", "usuario": "pgomez", "cargo": "Bar", "email": "p.gomez@parquesafari.cl", "estado": "Activo", "ultimo_acceso": "Hoy 08:20", "caja_asignada": "Terminal BDS Bar"},
    {"id": 7, "nombre": "Esteban Soto", "usuario": "esoto", "cargo": "Cajero", "email": "e.soto@parquesafari.cl", "estado": "Inactivo", "ultimo_acceso": "20-09-2026", "caja_asignada": "Sin asignar"},
]

# Cargos / Roles del Sistema
CARGOS = [
    {
        "id": "cajero",
        "nombre": "Cajero",
        "descripcion": "Acceso al Punto de Venta, cobro en efectivo/tarjetas, arqueo diario, consulta de tickets.",
        "usuarios_asociados": 2,
        "nivel": "Operativo POS"
    },
    {
        "id": "vendedor",
        "nombre": "Vendedor / Garzón",
        "descripcion": "Toma de pedidos en mesas o bar, emisión de comandas a cocina y bar, reasignación de mesas.",
        "usuarios_asociados": 2,
        "nivel": "Operativo Móvil"
    },
    {
        "id": "cocina",
        "nombre": "Cocina (KDS)",
        "descripcion": "Visualización de pedidos calientes y fríos que requieren preparación, cambio de estado de preparación.",
        "usuarios_asociados": 1,
        "nivel": "Producción"
    },
    {
        "id": "bar",
        "nombre": "Bar (BDS)",
        "descripcion": "Visualización de comandas de líquidos, cafés, cervezas y postres, despacho expedito de barra.",
        "usuarios_asociados": 1,
        "nivel": "Despacho Líquidos"
    },
    {
        "id": "administrador",
        "nombre": "Administrador",
        "descripcion": "Acceso global al sistema, gestión de precios, creación de usuarios, reportes, estadísticas y configuración.",
        "usuarios_asociados": 1,
        "nivel": "Gestión Total"
    },
]

# Módulo de Fiados / Consumo Colaboradores del Parque
FIADOS = [
    {
        "id": 1,
        "trabajador": "Héctor Leal",
        "rut": "15.421.890-3",
        "cargo_grupo": "Guía Safari Leones",
        "ultimo_producto": "Churrasco León + Bebida 500ml",
        "cantidad": 2,
        "valor": 9290,
        "valor_formateado": "$9.290",
        "fecha": "26-09-2026 13:10",
        "consumos_mes": 4,
        "total_acumulado": 24500,
        "total_formateado": "$24.500",
        "limite_credito": "$50.000",
        "estado": "Al día"
    },
    {
        "id": 2,
        "trabajador": "Dr. Fernando Bravo",
        "rut": "13.882.104-K",
        "cargo_grupo": "Veterinario Fauna Mayor",
        "ultimo_producto": "Menú Safari Aventura",
        "cantidad": 1,
        "valor": 9990,
        "valor_formateado": "$9.990",
        "fecha": "25-09-2026 14:05",
        "consumos_mes": 3,
        "total_acumulado": 18900,
        "total_formateado": "$18.900",
        "limite_credito": "$60.000",
        "estado": "Al día"
    },
    {
        "id": 3,
        "trabajador": "Marcela Rivas",
        "rut": "17.654.321-8",
        "cargo_grupo": "Boletería y Acceso",
        "ultimo_producto": "Café Cortado + Empanada Horno",
        "cantidad": 2,
        "valor": 5000,
        "valor_formateado": "$5.000",
        "fecha": "26-09-2026 10:20",
        "consumos_mes": 2,
        "total_acumulado": 8400,
        "total_formateado": "$8.400",
        "limite_credito": "$40.000",
        "estado": "Al día"
    },
    {
        "id": 4,
        "trabajador": "Juan Pablo Ríos",
        "rut": "16.112.789-5",
        "cargo_grupo": "Mantenimiento y Parque",
        "ultimo_producto": "Hamburguesa Safari + Bebida",
        "cantidad": 2,
        "valor": 8790,
        "valor_formateado": "$8.790",
        "fecha": "26-09-2026 12:55",
        "consumos_mes": 6,
        "total_acumulado": 31200,
        "total_formateado": "$31.200",
        "limite_credito": "$45.000",
        "estado": "Por descontar"
    },
    {
        "id": 5,
        "trabajador": "Rosa Venegas",
        "rut": "18.334.901-2",
        "cargo_grupo": "Educación Ambiental",
        "ultimo_producto": "Copa Sundae León Chocolate",
        "cantidad": 1,
        "valor": 3800,
        "valor_formateado": "$3.800",
        "fecha": "24-09-2026 16:30",
        "consumos_mes": 1,
        "total_acumulado": 5400,
        "total_formateado": "$5.400",
        "limite_credito": "$35.000",
        "estado": "Al día"
    },
]

# Módulo de Distribución de Ventas a Áreas
DISTRIBUCION_VENTAS = [
    {
        "venta_num": "00142",
        "modalidad": "Mesa 03",
        "hora": "12:44",
        "garzon": "Camila Silva",
        "total": "$14.690",
        "items": [
            {"nombre": "Hamburguesa Safari Especial", "cant": 1, "destino": "COCINA", "color": "warning", "estado": "En preparación"},
            {"nombre": "Papas Fritas Rústicas Safari", "cant": 1, "destino": "COCINA", "color": "warning", "estado": "En preparación"},
            {"nombre": "Jugo Natural Guayaba-Mango 500ml", "cant": 1, "destino": "BAR", "color": "info", "estado": "Listo"},
            {"nombre": "Bebida Coca-Cola 500ml", "cant": 1, "destino": "ENTREGA INMEDIATA", "color": "secondary", "estado": "Entregado"},
        ]
    },
    {
        "venta_num": "00141",
        "modalidad": "BAR / Barra Rápida",
        "hora": "12:40",
        "garzon": "Jean Valenzuela (Cajero)",
        "total": "$14.800",
        "items": [
            {"nombre": "Completo Safari Gigante", "cant": 2, "destino": "COCINA", "color": "warning", "estado": "Preparado"},
            {"nombre": "Cerveza Artesanal Safari Golden", "cant": 2, "destino": "BAR", "color": "info", "estado": "Entregado"},
        ]
    },
    {
        "venta_num": "00140",
        "modalidad": "Mesa 06",
        "hora": "12:35",
        "garzon": "Rodrigo Morales",
        "total": "$48.200",
        "items": [
            {"nombre": "Churrasco León Italiano", "cant": 2, "destino": "COCINA", "color": "warning", "estado": "En preparación"},
            {"nombre": "Nachos con Queso Cheddar & Guacamole", "cant": 1, "destino": "COCINA", "color": "warning", "estado": "En preparación"},
            {"nombre": "Café Espresso Doble", "cant": 2, "destino": "BAR", "color": "info", "estado": "Listo"},
            {"nombre": "Helado Paleta Selva", "cant": 2, "destino": "ENTREGA INMEDIATA", "color": "secondary", "estado": "Entregado"},
        ]
    }
]

# Módulo Cocina (KDS)
COCINA_PEDIDOS = [
    {
        "id": "C-142",
        "venta_num": "00142",
        "hora": "12:44",
        "minutos_espera": 9,
        "urgencia": "normal",  # normal, advertencia, urgente
        "modalidad": "MESA",
        "ubicacion": "Mesa 03",
        "mozo": "Camila Silva",
        "estado": "En preparación",
        "estado_badge": "bg-warning text-dark",
        "comentarios": "Sin mayonesa en la hamburguesa; papas rústicas extra crocantes y con poca sal.",
        "productos": [
            {"cant": 1, "nombre": "Hamburguesa Safari Especial", "nota": "Sin mayonesa"},
            {"cant": 1, "nombre": "Papas Fritas Rústicas Safari", "nota": "Extra crocantes"}
        ]
    },
    {
        "id": "C-140",
        "venta_num": "00140",
        "hora": "12:35",
        "minutos_espera": 18,
        "urgencia": "advertencia",
        "modalidad": "MESA",
        "ubicacion": "Mesa 06",
        "mozo": "Rodrigo Morales",
        "estado": "En preparación",
        "estado_badge": "bg-warning text-dark",
        "comentarios": "Carne churrasco término medio bien jugosa. Nachos con queso bien caliente.",
        "productos": [
            {"cant": 2, "nombre": "Churrasco León Italiano", "nota": "Término medio"},
            {"cant": 1, "nombre": "Nachos con Queso Cheddar & Guacamole", "nota": "Cheddar bien caliente"}
        ]
    },
    {
        "id": "C-139",
        "venta_num": "00139",
        "hora": "12:25",
        "minutos_espera": 28,
        "urgencia": "urgente",
        "modalidad": "MESA",
        "ubicacion": "Mesa 12",
        "mozo": "Rodrigo Morales",
        "estado": "Pendiente",
        "estado_badge": "bg-danger text-white",
        "comentarios": "Mesa con niños pequeños, despachar apenas esté listo.",
        "productos": [
            {"cant": 2, "nombre": "Completo Safari Gigante", "nota": "Sin chucrut"},
            {"cant": 1, "nombre": "Papas Fritas Rústicas", "nota": "Sin condimento"}
        ]
    },
    {
        "id": "C-138",
        "venta_num": "00138",
        "hora": "12:15",
        "minutos_espera": 38,
        "urgencia": "listo",
        "modalidad": "BAR",
        "ubicacion": "Barra Rápida",
        "mozo": "Jean Valenzuela",
        "estado": "Preparado",
        "estado_badge": "bg-success text-white",
        "comentarios": "Listo en pasaplatos para retiro.",
        "productos": [
            {"cant": 2, "nombre": "Empanada de Pino Horno", "nota": "Calentadas"}
        ]
    }
]

# Módulo Bar (BDS)
BAR_PEDIDOS = [
    {
        "id": "B-142",
        "venta_num": "00142",
        "hora": "12:44",
        "minutos_espera": 9,
        "modalidad": "MESA",
        "ubicacion": "Mesa 03",
        "mozo": "Camila Silva",
        "estado": "Listo",
        "estado_badge": "bg-success text-white",
        "comentarios": "Jugo bien helado con bombilla biodegradable.",
        "productos": [
            {"cant": 1, "nombre": "Jugo Natural Guayaba-Mango 500ml", "nota": "Poco hielo, azúcar normal"}
        ]
    },
    {
        "id": "B-140",
        "venta_num": "00140",
        "hora": "12:35",
        "minutos_espera": 18,
        "modalidad": "MESA",
        "ubicacion": "Mesa 06",
        "mozo": "Rodrigo Morales",
        "estado": "En preparación",
        "estado_badge": "bg-warning text-dark",
        "comentarios": "Cafés para servir junto al postre.",
        "productos": [
            {"cant": 2, "nombre": "Café Espresso Doble", "nota": "Con leche deslactosada"}
        ]
    },
    {
        "id": "B-143",
        "venta_num": "00143",
        "hora": "12:51",
        "minutos_espera": 2,
        "modalidad": "BAR",
        "ubicacion": "Barra Principal",
        "mozo": "Patricia Gómez",
        "estado": "Pendiente",
        "estado_badge": "bg-info text-dark",
        "comentarios": "Cliente esperando en barra.",
        "productos": [
            {"cant": 2, "nombre": "Cerveza Artesanal Safari Golden", "nota": "Vaso cervecero congelado"},
            {"cant": 1, "nombre": "Copa Sundae León Chocolate", "nota": "Extra salsa fudge"}
        ]
    }
]

# Estadísticas del Día
ESTADISTICAS = {
    "total_ventas_dia": "$846.500",
    "ventas_realizadas": 112,
    "ticket_promedio": "$7.558",
    "pedidos_pendientes": 5,
    "pedidos_preparados": 107,
    "mesas_ocupadas_ratio": "5 / 12 (42%)",
    "tiempo_prom_cocina": "11.4 min",
    "tiempo_prom_bar": "4.2 min",
    "top_productos": [
        {"nombre": "Hamburguesa Safari Especial", "cantidad": 46, "porcentaje": 88, "ingresos": "$321.540"},
        {"nombre": "Bebida Coca-Cola 500ml", "cantidad": 38, "porcentaje": 72, "ingresos": "$68.400"},
        {"nombre": "Papas Fritas Rústicas Safari", "cantidad": 34, "porcentaje": 65, "ingresos": "$119.000"},
        {"nombre": "Jugo Natural Guayaba-Mango", "cantidad": 29, "porcentaje": 55, "ingresos": "$92.800"},
        {"nombre": "Helado Paleta Selva", "cantidad": 25, "porcentaje": 48, "ingresos": "$62.500"},
        {"nombre": "Cerveza Artesanal Golden", "cantidad": 21, "porcentaje": 40, "ingresos": "$88.200"},
    ],
    "ventas_por_hora": [
        {"hora": "10:00", "monto": 35000, "monto_formateado": "$35.000", "porcentaje": 22},
        {"hora": "11:00", "monto": 68000, "monto_formateado": "$68.000", "porcentaje": 42},
        {"hora": "12:00", "monto": 142000, "monto_formateado": "$142.000", "porcentaje": 88},
        {"hora": "13:00", "monto": 160000, "monto_formateado": "$160.000", "porcentaje": 100},
        {"hora": "14:00", "monto": 135000, "monto_formateado": "$135.000", "porcentaje": 84},
        {"hora": "15:00", "monto": 98000, "monto_formateado": "$98.000", "porcentaje": 61},
        {"hora": "16:00", "monto": 84000, "monto_formateado": "$84.000", "porcentaje": 52},
        {"hora": "17:00", "monto": 72000, "monto_formateado": "$72.000", "porcentaje": 45},
        {"hora": "18:00", "monto": 52500, "monto_formateado": "$52.500", "porcentaje": 32},
    ],
    "ventas_por_categoria": [
        {"categoria": "Comidas y Platos", "total": "$482.000", "porcentaje": 57},
        {"categoria": "Bebidas y Líquidos", "total": "$198.500", "porcentaje": 23},
        {"categoria": "Helados y Postres", "total": "$88.000", "porcentaje": 10},
        {"categoria": "Snacks y Otros", "total": "$78.000", "porcentaje": 10},
    ]
}

# Configuración del Sistema POS
CONFIGURACION = {
    "nombre_parque": "Parque Safari Chile",
    "razon_social": "Inversiones Safari Park Ltda.",
    "rut": "76.432.890-5",
    "direccion": "Ruta H-30 Km 5, Rancagua, Región de O'Higgins",
    "telefono": "+56 72 258 4000",
    "terminal_caja": "POS-01 (Caja Principal Zona Safari)",
    "impresora_tickets": "Epson TM-T20III (Térmica 80mm - USB)",
    "impresora_cocina": "Bixolon SRP-350 (Red LAN 192.168.1.50)",
    "impresora_bar": "Bixolon SRP-350 (Red LAN 192.168.1.51)",
    "iva_incluido": True,
    "iva_porcentaje": 19,
    "modo_offline": "Habilitado (Cache local)",
    "sonido_comandas": True,
    "resolucion_optimizada": "1920x1080 Full HD (Pantallas Táctiles)"
}
