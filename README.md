# Sistema Web de Ventas POS — Parque Safari

> **Proyecto Académico — Analista Programador**  
> **Estado Actual: Cumplimiento Completo hasta Semana 12 (Proceso Principal de Ventas, Cajas & Cuadratura)**  
> **Base de Datos:** PostgreSQL en Neon Cloud / Fallback SQLite  
> **Arquitectura:** Django MVT (Model-View-Template) con ORM y Persistencia Relacional

Aplicación web desarrollada en **Django** con interfaz táctil responsiva optimizada para terminales POS, tablets de salón y pantallas de producción (KDS/BDS). Incluye control de sesiones de caja con apertura de fondo para sencillo, cuadratura de caja con desglose de billetes y monedas chilenas, ventas diferenciadas en barra vs mesa, enrutamiento a cocina/bar, mantenedores con BD y manejo personalizado de errores 404/500.

---

## 📌 Bitácora de Avances y Cumplimiento por Etapas (Semanas 10, 11 y 12)

| Semana | Requisitos de Pauta | Estado | Implementación en el Proyecto |
| :--- | :--- | :---: | :--- |
| **Semana 10** | **1.** Creación de proyecto Django.<br>**2.** Inicio de sesión con cuentas de usuarios desde BD según perfil.<br>**3.** Validación de campos de inicio de sesión.<br>**4.** Páginas personalizadas ante errores en ejecución (Error 404, Error 500, rutas erróneas, caídas de servidor).<br>**5.** Validaciones para enfrentar vulnerabilidades. | **COMPLETO** | - Modelos `Usuario` y `Cargo` conectados a PostgreSQL (Neon).<br>- Login con verificación de credenciales, roles y estado de cuenta.<br>- Plantillas temáticas personalizadas [`templates/404.html`](templates/404.html) y [`templates/500.html`](templates/500.html) con `handler404` y `handler500`. |
| **Semana 11** | **1.** Mantenedores de trabajo con BD (CRUDs básicos):<br>&nbsp;&nbsp;• Gestión de Usuarios y Roles.<br>&nbsp;&nbsp;• Gestión de Mesas del Salón.<br>&nbsp;&nbsp;• Gestión de Puntos de Venta (Terminales).<br>&nbsp;&nbsp;• Gestión de Menús y Combos.<br>&nbsp;&nbsp;• Gestión de Productos y Categorías.<br>&nbsp;&nbsp;• Historial de Acciones / Auditoría.<br>**2.** Validación de campos en formularios de módulos. | **COMPLETO** | - Modelos ORM relacionales para `Producto`, `Categoria`, `MenuCombo`, `Mesa`, `Usuario`, `Cargo` y `ConfiguracionPOS`.<br>- Modelo `LogAuditoria` para trazabilidad de logins, cambios de estado y ventas.<br>- Datos demostrativos (Seeds) cargados en Neon PostgreSQL. |
| **Semana 12** | **1.** Proceso principal de trabajo (Ventas):<br>&nbsp;&nbsp;• Inicio y Cierre de jornada.<br>&nbsp;&nbsp;• Apertura y Cierre de cajas (sesiones).<br>&nbsp;&nbsp;• Indicar monto de efectivo disponible en apertura (sencillo/vueltos).<br>&nbsp;&nbsp;• Venta en barra (boleta inmediata) vs Pedido en mesa por garzón (boleta al pagar).<br>&nbsp;&nbsp;• Proceso de cuadratura al cerrar la caja con desglose obligatorio de billetes ($20.000, $10.000, $5.000, $1.000) y monedas ($500, $100, $50, $5, $1).<br>&nbsp;&nbsp;• Reportes estadísticos de cierre.<br>**2.** Validación de campos del proceso principal. | **COMPLETO** | - Modelos `SesionCaja`, `CuadraturaCaja`, `Venta`, `DetalleVenta` y `ComandaProduccion`.<br>- Modal táctil de **Caja & Cuadratura** en la barra superior con calculadora de billetes y monedas en vivo y cálculo de sobrante/faltante.<br>- POS con alternador **BAR / RETIRO** (boleta electrónica inmediata) vs **MESA** (comanda de pedido y boleta diferida). |
| *Semana 13+* | *Pruebas con pares evaluadores y plan de mejoras.* | *Futuro* | *Reservado para las siguientes semanas.* |

---

## 👥 Cuentas de Acceso Demostrativas (Para Evaluación de Roles)

Todas las cuentas están creadas en la base de datos PostgreSQL de **Neon**.  
Para pruebas rápidas, la contraseña universal de prueba es **`123`** (o selección rápida en la pantalla de inicio):

| Usuario | Clave | Nombre | Rol / Cargo | Área de Foco / Permisos |
| :--- | :---: | :--- | :--- | :--- |
| **`cmendoza`** | `123` | Carlos Mendoza | **Administrador** | Control total, catálogos, usuarios, finanzas y reportes. |
| **`jvalenzuela`**| `123` | Jean Valenzuela | **Cajero** | Punto de Venta (POS), cobro, apertura y cuadratura de caja. |
| **`csilva`** | `123` | Camila Silva | **Garzón / Salón** | Mapa de mesas, comanda a mesas y derivación a producción. |
| **`mtorres`** | `123` | Matías Torres | **Cocina** | Cocina KDS, pedidos calientes, temporizadores y despacho. |
| **`pgomez`** | `123` | Patricia Gómez | **Bar** | Bar BDS, despacho de bebestibles, postres y cafetería. |

> Consulta la guía completa para tus evaluadores en: [`CREDENCIALES_Y_ROLES.txt`](CREDENCIALES_Y_ROLES.txt).

---

## 🏗️ Arquitectura y Tecnologías

* **Backend:** Python 3.12+ con Django 5.x / 6.x (Patrón MVT).
* **ORM:** Django ORM con soporte relacional completo y llaves foráneas (`models.ForeignKey`, `OneToOneField`).
* **Base de Datos Cloud:** **PostgreSQL 15** en [Neon.tech](https://neon.tech) (conexión segura SSL).
* **Frontend:** HTML5 semántico, CSS3 Vanilla modular con gradientes modernos, Bootstrap 5.3 y Bootstrap Icons.
* **Manejo de Errores:** Controladores de vista `custom_page_not_found_view` (404) y `custom_server_error_view` (500).
* **Despliegue:** Preparado para Vercel Serverless Function con WhiteNoise para estáticos.

---

## 🚀 Puesta en Marcha Local

```bash
# 1. Clonar el repositorio
git clone https://github.com/yinpi1/parque-safari-pos.git
cd parque-safari-pos

# 2. Crear y activar entorno virtual
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno (.env)
# Configura DATABASE_URL con la conexión a Neon PostgreSQL:
# DATABASE_URL=postgresql://neondb_owner:...@ep-dry-truth-...neon.tech/neondb?sslmode=require

# 5. Ejecutar migraciones (ya creadas en pos_app/migrations/)
python manage.py migrate

# 6. Opcional: Recargar datos de prueba iniciales (Seeds)
python seed_neon.py

# 7. Iniciar el servidor
python manage.py runserver
```

Abre en tu navegador: **`http://127.0.0.1:8000/`**

---

## 🧪 Pruebas Rápidas para la Presentación

1. **Prueba de Rutas y Error 404 (Semana 10):**
   - Ingresa a `http://127.0.0.1:8000/error-test/` para ver la pantalla 404 personalizada de Parque Safari.
2. **Prueba de Cuadratura de Caja (Semana 12):**
   - Haz clic en el botón superior **`CAJA & CUADRATURA`**.
   - En la pestaña **Apertura de Caja**, verifica el fondo inicial para sencillo ($50.000).
   - En la pestaña **Cierre & Cuadratura**, cambia las cantidades de billetes ($20.000 a $1.000) o monedas ($500 a $1) para ver cómo calcula en vivo el total y si hay sobrante o faltante.
3. **Prueba de Venta en Barra vs Mesa (Semana 12):**
   - En el POS, selecciona **BAR / RETIRO**: al cobrar se emite la *Boleta Electrónica Inmediata*.
   - Alterna a **MESA**: selecciona una mesa (ej: Mesa 03), y al cobrar se emite la *Comanda de Pedido para Mesa (Boleta Diferida al Pago)*.
