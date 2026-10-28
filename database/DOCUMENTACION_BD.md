# Documentación Técnica del Modelo de Base de Datos
## Sistema Web de Ventas POS — Parque Safari Chile

> **Carrera:** Analista Programador  
> **Proyecto:** Sistema Integrado POS & Comandas (Cocina KDS / Bar BDS)  
> **Motor de Base de Datos:** PostgreSQL (v14 o superior)  
> **Fecha:** Octubre 2026  

---

## 1. Resumen y Contexto de la Base de Datos

En la fase inicial (**MVP 2.1**), el sistema operó con un repositorio desacoplado en memoria (`pos_app/mock_data.py`) y SQLite local. Este diseño permitió validar la experiencia de usuario táctil, el flujo de ventas, las pantallas KDS/BDS y el despliegue en Vercel sin dependencias de red externas.

Para la etapa de producción, persistencia y entrega formal del proyecto, se ha diseñado el **Modelo Relacional Normalizado en PostgreSQL**, estructurado en 12 entidades que cubren la totalidad del flujo operativo de Parque Safari.

Los scripts correspondientes se encuentran disponibles en:
* **Script DDL (Estructura y Tablas):** [`database/schema_postgresql.sql`](schema_postgresql.sql)
* **Script DML (Datos Maestros y Semilla):** [`database/seed_data_postgresql.sql`](seed_data_postgresql.sql)

---

## 2. Diagrama Entidad-Relación (DER)

A continuación se presenta la arquitectura relacional del sistema:

```mermaid
erDiagram
    CARGOS ||--o{ USUARIOS : "posee"
    CATEGORIAS ||--o{ PRODUCTOS : "clasifica"
    USUARIOS ||--o{ MESAS : "atiende"
    USUARIOS ||--o{ VENTAS : "emite"
    MESAS ||--o{ VENTAS : "aloja"
    VENTAS ||--o{ DETALLE_VENTAS : "contiene"
    PRODUCTOS ||--o{ DETALLE_VENTAS : "se_vende_en"
    MENUS_COMBOS ||--o{ DETALLE_VENTAS : "se_incluye_en"
    VENTAS ||--o{ COMANDAS_PRODUCCION : "genera"
    FIADOS_PERSONAL ||--o{ FIADOS_MOVIMIENTOS : "registra"
    VENTAS ||--o{ FIADOS_MOVIMIENTOS : "origina"

    CARGOS {
        varchar id PK
        varchar nombre
        text descripcion
        varchar nivel
    }

    USUARIOS {
        serial id PK
        varchar nombre
        varchar usuario UK
        varchar email UK
        varchar password_hash
        varchar cargo_id FK
        varchar caja_asignada
        varchar estado
        timestamptz ultimo_acceso
    }

    CATEGORIAS {
        varchar id PK
        varchar nombre
        varchar icono
        varchar color
        boolean activo
    }

    PRODUCTOS {
        serial id PK
        varchar codigo UK
        varchar nombre
        varchar categoria_id FK
        integer precio
        varchar tipo
        varchar destino
        varchar estado
        text descripcion
    }

    MENUS_COMBOS {
        serial id PK
        varchar codigo UK
        varchar nombre
        text productos_incluidos
        integer precio
        integer ahorro_estimado
        varchar categoria
        varchar estado
    }

    MESAS {
        serial id PK
        varchar numero UK
        varchar zona
        integer capacidad
        varchar estado
        integer consumo_actual
        integer mozo_asignado_id FK
        integer comensales_actuales
    }

    VENTAS {
        serial id PK
        varchar venta_num UK
        timestamptz fecha_hora
        varchar modalidad
        integer mesa_id FK
        integer usuario_id FK
        integer total
        varchar metodo_pago
        varchar estado
    }

    DETALLE_VENTAS {
        serial id PK
        integer venta_id FK
        integer producto_id FK
        integer menu_id FK
        integer cantidad
        integer precio_unitario
        integer subtotal
        varchar destino
        varchar estado_produccion
        text notas_preparacion
    }

    COMANDAS_PRODUCCION {
        varchar id PK
        integer venta_id FK
        varchar area_destino
        varchar urgencia
        varchar estado
        text comentarios
        timestamptz fecha_hora_ingreso
    }

    FIADOS_PERSONAL {
        serial id PK
        varchar rut UK
        varchar trabajador
        varchar cargo_grupo
        integer limite_credito
        integer total_acumulado
        integer consumos_mes
        varchar estado
    }

    FIADOS_MOVIMIENTOS {
        serial id PK
        integer fiado_id FK
        integer venta_id FK
        varchar detalle
        integer cantidad
        integer monto
        timestamptz fecha
    }

    CONFIGURACION_POS {
        serial id PK
        varchar nombre_parque
        varchar razon_social
        varchar rut
        varchar terminal_caja
        boolean iva_incluido
        numeric iva_porcentaje
    }
```

---

## 3. Diccionario de Datos

### 3.1. Tabla `cargos`
Almacena los roles del personal para el control de acceso y permisos en la aplicación.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | VARCHAR(20) | **PK** | No | — | Identificador alfanumérico (`cajero`, `cocina`, etc.) |
| `nombre` | VARCHAR(50) | — | No | — | Nombre legible del cargo |
| `descripcion` | TEXT | — | Sí | — | Responsabilidades y accesos permitidos |
| `nivel` | VARCHAR(50) | — | No | — | Categoría funcional (`Operativo POS`, `Producción`, etc.) |
| `created_at` | TIMESTAMPTZ | — | No | `CURRENT_TIMESTAMP` | Fecha de creación del registro |

---

### 3.2. Tabla `usuarios`
Colaboradores autorizados a operar los terminales POS, KDS y BDS.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `nombre` | VARCHAR(100) | — | No | — | Nombre y apellido del trabajador |
| `usuario` | VARCHAR(50) | — | No | `UNIQUE` | Username para inicio de sesión |
| `email` | VARCHAR(120) | — | No | `UNIQUE` | Correo corporativo institucional |
| `password_hash` | VARCHAR(255) | — | No | Hash Django | Contraseña cifrada |
| `cargo_id` | VARCHAR(20) | **FK** | No | `REFERENCES cargos(id)` | Relación con el cargo asignado |
| `caja_asignada` | VARCHAR(100) | — | Sí | `'Sin asignar'` | Terminal o caja fija/móvil asignada |
| `estado` | VARCHAR(20) | — | No | `CHECK (estado IN ('Activo', 'Inactivo', 'Suspendido'))` | Estado operativo del usuario |
| `ultimo_acceso` | TIMESTAMPTZ | — | Sí | NULL | Registro de último login |
| `created_at` | TIMESTAMPTZ | — | No | `CURRENT_TIMESTAMP` | Fecha de alta en el sistema |

---

### 3.3. Tabla `categorias`
Clasificación de productos gastronómicos del Parque Safari.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | VARCHAR(30) | **PK** | No | — | Identificador (`comidas`, `bebidas`, etc.) |
| `nombre` | VARCHAR(100) | — | No | — | Nombre para pestañas de catálogo POS |
| `icono` | VARCHAR(50) | — | No | `'bi-grid-fill'` | Nombre de clase Bootstrap Icons |
| `color` | VARCHAR(30) | — | No | `'primary'` | Variante de color para interfaz gráfica |
| `activo` | BOOLEAN | — | No | `TRUE` | Permite habilitar/deshabilitar la categoría |

---

### 3.4. Tabla `productos`
Catálogo de ítems a la venta con direccionamiento a centros de producción.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `codigo` | VARCHAR(30) | — | No | `UNIQUE` | Código SKU (`COM-001`, `BEB-001`, etc.) |
| `nombre` | VARCHAR(150) | — | No | — | Nombre comercial del plato/producto |
| `categoria_id` | VARCHAR(30) | **FK** | No | `REFERENCES categorias(id)` | Categoría a la que pertenece |
| `precio` | INTEGER | — | No | `CHECK (precio >= 0)` | Precio venta público en CLP |
| `tipo` | VARCHAR(50) | — | No | `'Producto listo'` / `'Requiere preparación'` | Clasificación de esfuerzo operativo |
| `destino` | VARCHAR(30) | — | No | `CHECK (destino IN ('Cocina', 'Bar', 'Directo'))` | Centro de despacho o preparación |
| `estado` | VARCHAR(20) | — | No | `CHECK (estado IN ('Activo', 'Inactivo', 'Agotado'))` | Disponibilidad en el POS |
| `badge_tipo` | VARCHAR(30) | — | No | `'badge-listo'` | Clase CSS para etiquetas en pantalla |
| `descripcion` | TEXT | — | Sí | — | Receta breve, ingredientes y detalles |
| `icono` | VARCHAR(50) | — | Sí | `'bi-box2-heart'` | Ícono representativo |
| `imagen_placeholder` | VARCHAR(50) | — | Sí | — | Clave de imagen demostrativa |

---

### 3.5. Tabla `menus_combos`
Paquetes promocionales compuestos por múltiples productos con precio reducido.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `codigo` | VARCHAR(30) | — | No | `UNIQUE` | Código del combo (`MENU-SAF-01`) |
| `nombre` | VARCHAR(150) | — | No | — | Nombre comercial de la promoción |
| `productos_incluidos` | TEXT | — | No | — | Desglose legible de los productos |
| `precio` | INTEGER | — | No | `CHECK (precio >= 0)` | Precio final en CLP |
| `ahorro_estimado` | INTEGER | — | Sí | `0` | Descuento total frente a compra individual |
| `categoria` | VARCHAR(50) | — | No | `'Combos'` | Agrupación comercial |
| `disponibilidad` | VARCHAR(100) | — | Sí | `'Todo el día'` | Franja horaria de vigencia |
| `estado` | VARCHAR(20) | — | No | `'Activo'` | Estado de oferta |

---

### 3.6. Tabla `mesas`
Zonas de atención y capacidad física del restaurante y terrazas del parque.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `numero` | VARCHAR(20) | — | No | `UNIQUE` | Código o número visible (`Mesa 01`) |
| `zona` | VARCHAR(50) | — | No | `CHECK (zona IN (...))` | Sector del parque (Salón, Terrazas, etc.) |
| `capacidad` | INTEGER | — | No | `CHECK (capacidad > 0)` | Cantidad de sillas disponibles |
| `estado` | VARCHAR(20) | — | No | `CHECK (estado IN ('Disponible', 'Ocupada', ...))` | Estado en tiempo real del mapa de salón |
| `consumo_actual` | INTEGER | — | No | `DEFAULT 0` | Total acumulado de la comanda abierta |
| `mozo_asignado_id` | INTEGER | **FK** | Sí | `REFERENCES usuarios(id)` | Garzón a cargo de la mesa |
| `comensales_actuales` | INTEGER | — | No | `DEFAULT 0` | Cantidad de clientes sentados |
| `hora_inicio_ocupacion`| TIMESTAMPTZ | — | Sí | NULL | Timestamp de apertura de mesa |

---

### 3.7. Tabla `ventas`
Encabezado de cada transacción comercial (Boleta / Factura / Ticket).

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `venta_num` | VARCHAR(20) | — | No | `UNIQUE` | Folio del ticket (`00142`) |
| `fecha_hora` | TIMESTAMPTZ | — | No | `CURRENT_TIMESTAMP` | Fecha y hora exacta de emisión |
| `modalidad` | VARCHAR(30) | — | No | `CHECK (modalidad IN ('MESA', 'BAR', 'DELIVERY', 'PARA LLEVAR'))` | Canal de venta |
| `mesa_id` | INTEGER | **FK** | Sí | `REFERENCES mesas(id)` | Mesa asignada (opcional si es Barra) |
| `usuario_id` | INTEGER | **FK** | No | `REFERENCES usuarios(id)` | Cajero o garzón que registró la venta |
| `subtotal` | INTEGER | — | No | `CHECK (subtotal >= 0)` | Monto neto |
| `iva` | INTEGER | — | No | `DEFAULT 0` | Impuesto al valor agregado (19%) |
| `total` | INTEGER | — | No | `CHECK (total >= 0)` | Total final a pagar en CLP |
| `metodo_pago` | VARCHAR(50) | — | No | `CHECK (metodo_pago IN (...))` | Medio de pago utilizado |
| `estado` | VARCHAR(30) | — | No | `'Pagado'` / `'Pendiente'` / `'Anulado'` | Estado de recaudación |
| `notas` | TEXT | — | Sí | — | Observaciones generales del pedido |

---

### 3.8. Tabla `detalle_ventas`
Renglones o líneas de producto asociados a una venta.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `venta_id` | INTEGER | **FK** | No | `REFERENCES ventas(id) ON DELETE CASCADE` | Venta asociada |
| `producto_id` | INTEGER | **FK** | Sí | `REFERENCES productos(id)` | Producto individual |
| `menu_id` | INTEGER | **FK** | Sí | `REFERENCES menus_combos(id)` | Combo promocional |
| `cantidad` | INTEGER | — | No | `CHECK (cantidad > 0)` | Cantidad ordenada |
| `precio_unitario` | INTEGER | — | No | `CHECK (precio_unitario >= 0)` | Precio unitario aplicado |
| `subtotal` | INTEGER | — | No | `CHECK (subtotal >= 0)` | `cantidad * precio_unitario` |
| `destino` | VARCHAR(30) | — | No | `CHECK (destino IN ('COCINA', 'BAR', 'ENTREGA INMEDIATA'))` | Ruteo automático de producción |
| `estado_produccion` | VARCHAR(30) | — | No | `'Pendiente'` / `'En preparación'` / `'Listo'` | Estado en pantallas KDS/BDS |
| `notas_preparacion` | TEXT | — | Sí | — | Instrucciones de cocina (ej. "sin cebolla") |

---

### 3.9. Tabla `comandas_produccion`
Agrupación de órdenes derivadas a los monitores de producción en cocina (KDS) o barra (BDS).

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | VARCHAR(20) | **PK** | No | — | Código de comanda (`C-142`, `B-142`) |
| `venta_id` | INTEGER | **FK** | No | `REFERENCES ventas(id) ON DELETE CASCADE` | Ticket de origen |
| `area_destino` | VARCHAR(20) | — | No | `CHECK (area_destino IN ('COCINA', 'BAR'))` | Área de trabajo destinataria |
| `urgencia` | VARCHAR(20) | — | No | `'normal'` / `'advertencia'` / `'urgente'` | Nivel de prioridad según tiempo de espera |
| `estado` | VARCHAR(30) | — | No | `'Pendiente'` / `'En preparación'` / `'Preparado'` | Estado actual en la pantalla |
| `comentarios` | TEXT | — | Sí | — | Observaciones de servicio |
| `fecha_hora_ingreso` | TIMESTAMPTZ | — | No | `CURRENT_TIMESTAMP` | Hora en que ingresó al KDS/BDS |
| `fecha_hora_despacho` | TIMESTAMPTZ | — | Sí | NULL | Hora en que el cocinero/barman despachó |

---

### 3.10. Tabla `fiados_personal`
Control de créditos y vales de consumo para colaboradores del Parque Safari con descuento por nómina.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `rut` | VARCHAR(15) | — | No | `UNIQUE` | RUT chileno del colaborador |
| `trabajador` | VARCHAR(150) | — | No | — | Nombre completo del colaborador |
| `cargo_grupo` | VARCHAR(100) | — | No | — | Área (Guía Safari, Veterinario, etc.) |
| `limite_credito` | INTEGER | — | No | `DEFAULT 50000` | Monto máximo permitido al mes en CLP |
| `total_acumulado` | INTEGER | — | No | `DEFAULT 0` | Deuda pendiente actual |
| `consumos_mes` | INTEGER | — | No | `DEFAULT 0` | Número de compras en el ciclo |
| `estado` | VARCHAR(30) | — | No | `'Al día'` / `'Por descontar'` / `'Bloqueado'` | Estado financiero del colaborador |

---

### 3.11. Tabla `fiados_movimientos`
Historial de compras efectuadas al crédito por cada trabajador.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `fiado_id` | INTEGER | **FK** | No | `REFERENCES fiados_personal(id)` | Trabajador titular |
| `venta_id` | INTEGER | **FK** | Sí | `REFERENCES ventas(id)` | Boleta originaria |
| `detalle` | VARCHAR(255) | — | No | — | Descripción resumida de los artículos |
| `cantidad` | INTEGER | — | No | `DEFAULT 1` | Total de unidades |
| `monto` | INTEGER | — | No | `CHECK (monto >= 0)` | Monto imputado |
| `fecha` | TIMESTAMPTZ | — | No | `CURRENT_TIMESTAMP` | Fecha y hora del vale |

---

### 3.12. Tabla `configuracion_pos`
Parámetros globales del parque, hardware de impresión térmica y tributación.

| Atributo | Tipo de Dato (PostgreSQL) | PK / FK | Nulo | Restricciones / Default | Descripción |
| :--- | :--- | :---: | :---: | :--- | :--- |
| `id` | SERIAL | **PK** | No | Autoincremental | Clave primaria |
| `nombre_parque` | VARCHAR(100) | — | No | — | Nombre de fantasía |
| `razon_social` | VARCHAR(150) | — | No | — | Razón social legal de la empresa |
| `rut` | VARCHAR(20) | — | No | — | RUT de la empresa |
| `direccion` | VARCHAR(200) | — | No | — | Dirección física del parque |
| `telefono` | VARCHAR(50) | — | No | — | Fono de contacto |
| `terminal_caja` | VARCHAR(100) | — | No | — | Identificador de la caja física |
| `impresora_tickets` | VARCHAR(100) | — | Sí | — | Modelo de impresora térmica de boletas |
| `impresora_cocina` | VARCHAR(100) | — | Sí | — | Impresora de red para comandas de cocina |
| `impresora_bar` | VARCHAR(100) | — | Sí | — | Impresora de barra de bebidas |
| `iva_incluido` | BOOLEAN | — | No | `TRUE` | Bandera de IVA incluido en precios |
| `iva_porcentaje` | NUMERIC(5,2) | — | No | `19.00` | Tasa de impuesto en Chile |
| `modo_offline` | BOOLEAN | — | No | `TRUE` | Soporte para cache local |

---

## 4. Instrucciones de Ejecución en PostgreSQL

### Opción A: Mediante Consola (`psql`)
1. Iniciar sesión en el servidor PostgreSQL:
   ```bash
   psql -U postgres -h localhost
   ```
2. Crear la base de datos:
   ```sql
   CREATE DATABASE parque_safari_pos WITH ENCODING 'UTF8';
   \c parque_safari_pos
   ```
3. Ejecutar los scripts en orden:
   ```bash
   \i database/schema_postgresql.sql
   \i database/seed_data_postgresql.sql
   ```

### Opción B: Mediante pgAdmin o DBeaver
1. Crear una nueva base de datos llamada `parque_safari_pos`.
2. Abrir la herramienta **Query Tool**.
3. Copiar y ejecutar el contenido de `database/schema_postgresql.sql`.
4. Copiar y ejecutar el contenido de `database/seed_data_postgresql.sql`.

---

## 5. Integración con Django (`settings.py`)

Para conectar Django directamente a PostgreSQL en lugar de SQLite, se deben realizar los siguientes ajustes:

1. **Instalar el driver PostgreSQL:**
   ```bash
   pip install psycopg2-binary
   ```
2. **Actualizar `parque_safari/settings.py`:**
   ```python
   DATABASES = {
       'default': {
           'ENGINE': 'django.db.backends.postgresql',
           'NAME': 'parque_safari_pos',
           'USER': 'postgres',
           'PASSWORD': 'tu_password',
           'HOST': 'localhost',
           'PORT': '5432',
       }
   }
   ```
3. *(Opcional con Neon / Supabase Cloud):*
   Utilizar la librería `dj-database-url` para configurar la cadena de conexión mediante variable de entorno:
   ```python
   import dj_database_url
   DATABASES = {
       'default': dj_database_url.config(
           default='postgresql://usuario:password@host/parque_safari_pos',
           conn_max_age=600
       )
   }
   ```
