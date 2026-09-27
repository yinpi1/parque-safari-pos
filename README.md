# 🦁 Sistema Web de Ventas POS — Parque Safari

> **Proyecto Académico — Analista Programador**  
> **Etapa 1: MVP Visual / Maqueta Completa y Navegable**

Aplicación web desarrollada en **Django (MVT)** con diseño táctil optimizado para terminales POS y pantallas Full HD (1920x1080).

---

## 🚀 Despliegue en Vercel

Este proyecto está configurado para desplegarse automáticamente en **Vercel**:
* **`vercel.json`**: Configuración de Serverless Function con `@vercel/python`.
* **`build_files.sh`**: Instalación automática de dependencias y recopilación de archivos estáticos (`collectstatic`).
* **`requirements.txt`**: Django 5+, Whitenoise, sqlparse, asgiref.

Para desplegar:
1. Entra a [vercel.com](https://vercel.com) e inicia sesión con tu cuenta de GitHub.
2. Haz click en **Add New...** -> **Project**.
3. Importa el repositorio `parque-safari-pos`.
4. Deja la configuración por defecto y haz click en **Deploy**.

---

## 🖥️ Módulos Incluidos

1. **Login**: Acceso táctil con selector rápido de roles demostrativos (Cajero, Administrador, Cocina, Bar).
2. **Dashboard**: Panel principal con métricas clave (ventas del día, ticket promedio, ocupación de mesas, pedidos activos) y accesos directos.
3. **Punto de Venta (POS)**: Catálogo clasificado por categorías, buscador en vivo, carrito interactivo con ajuste de cantidades, selector BAR vs MESA y campo de notas.
4. **Confirmación y Ticket Térmico**:
   - Boleta electrónica de venta para el cliente.
   - Comanda de Cocina (solo platos calientes y notas de preparación).
   - Comanda de Bar (solo líquidos y postres para barra).
5. **Catálogo de Productos**: Tabla administrativa clasificada por destino de producción (Cocina / Bar / Listo) con modal de nuevo producto.
6. **Menús y Combos**: Promociones y paquetes con cálculo de ahorro y productos incluidos.
7. **Mapa de Mesas**: Salón con 12 mesas codificadas por estado (Disponible / Ocupada), tiempos de atención y modal de reasignación.
8. **Usuarios y Cargos**: Gestión de colaboradores con cajas asignadas y roles del sistema.
9. **Fiados Personal**: Control de consumos internos de colaboradores con modal de vales y resumen para descuento por nómina.
10. **Distribución**: Diagrama de enrutamiento que muestra cómo una venta se separa y deriva automáticamente a Cocina y Bar.
11. **Cocina KDS**: Pantalla de producción para cocineros con temporizadores de espera y cambio de estado de comandas.
12. **Bar BDS**: Pantalla de despacho de bebestibles y postres para barman.
13. **Estadísticas**: Curvas visuales de ventas por hora, desglose por categoría y ranking de productos más vendidos.
14. **Centro de Reportes**: Filtros por rango de fechas y botones de exportación a PDF y Excel.
15. **Configuración**: Parámetros de la empresa, impresoras térmicas de 80mm e impuestos.

---

## 🛠️ Ejecución Local

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

# 4. Iniciar servidor de desarrollo
python manage.py runserver
```

Abre en tu navegador: **`http://127.0.0.1:8000/`**

---

## 🎨 Estructura de Estilos
* **`static/css/estilos.css`**: Hoja de estilos principal del sistema POS.
* **`static/js/pos.js`**: Lógica de interacción táctil, carrito de compras y reloj digital en vivo.
