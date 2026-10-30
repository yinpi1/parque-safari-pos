"""
pos_app/tests.py
Suite de pruebas automatizadas para la Fase 1: Seguridad y Autenticación
de Parque Safari POS (AUD-002, AUD-003, AUD-004, AUD-005, AUD-006, AUD-007, AUD-008, AUD-010).

Se ejecuta sobre una base de datos SQLite en memoria completamente aislada
(configurada en parque_safari/settings.py cuando 'test' está en sys.argv),
sin tocar ni modificar datos reales de Neon PostgreSQL.
"""

from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, OperationalError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

import seed_neon
from .models import (
    Cargo,
    Categoria,
    ComandaProduccion,
    ConfiguracionPOS,
    CuadraturaCaja,
    DetalleVenta,
    FiadoMovimiento,
    FiadoPersonal,
    LogAuditoria,
    MenuCombo,
    Mesa,
    Producto,
    SesionCaja,
    Usuario,
    Venta,
    is_password_hashed,
)
from .views import GENERIC_AUTH_ERROR, MAX_LOGIN_ATTEMPTS

migration_0002 = import_module("pos_app.migrations.0002_hash_plain_passwords")


class Fase1SeguridadAutenticacionTests(TestCase):
    """Verificación integral de los 12 escenarios obligatorios de la Fase 1."""

    @classmethod
    def setUpTestData(cls):
        # Crear cargos canónicos una sola vez por clase para acelerar PBKDF2
        cls.cargo_admin = Cargo.objects.create(
            id="admin", nombre="Administrador", nivel="Gerencial"
        )
        cls.cargo_cajero = Cargo.objects.create(
            id="cajero", nombre="Cajero", nivel="Operativo"
        )
        cls.cargo_garzon = Cargo.objects.create(
            id="garzon", nombre="Garzón / Mesero", nivel="Operativo"
        )
        cls.cargo_cocina = Cargo.objects.create(
            id="cocina", nombre="Cocina", nivel="Producción"
        )
        cls.cargo_bar = Cargo.objects.create(
            id="bar", nombre="Bar", nivel="Producción"
        )

        # Contraseñas exclusivas de prueba (distintas de '123' y '123456')
        cls.pass_admin = "AdminSafari#2026!"
        cls.pass_cajero = "CajeroSafari#2026!"
        cls.pass_garzon = "GarzonSafari#2026!"
        cls.pass_cocina = "CocinaSafari#2026!"
        cls.pass_bar = "BarSafari#2026!"
        cls.pass_inactivo = "InactivoSafari#2026!"

        cls.user_admin = Usuario.objects.create(
            nombre="Carlos Mendoza",
            usuario="cmendoza",
            email="cmendoza@parquesafari.cl",
            password=cls.pass_admin,
            cargo=cls.cargo_admin,
            caja_asignada="Todas las Cajas",
            estado="Activo",
        )
        cls.user_cajero = Usuario.objects.create(
            nombre="Jean Valenzuela",
            usuario="jvalenzuela",
            email="jvalenzuela@parquesafari.cl",
            password=cls.pass_cajero,
            cargo=cls.cargo_cajero,
            caja_asignada="Caja 01 - Principal",
            estado="Activo",
        )
        cls.user_garzon = Usuario.objects.create(
            nombre="Roberto Morales",
            usuario="rmorales",
            email="rmorales@parquesafari.cl",
            password=cls.pass_garzon,
            cargo=cls.cargo_garzon,
            caja_asignada="Salón Comedor",
            estado="Activo",
        )
        cls.user_cocina = Usuario.objects.create(
            nombre="Matías Torres",
            usuario="mtorres",
            email="mtorres@parquesafari.cl",
            password=cls.pass_cocina,
            cargo=cls.cargo_cocina,
            caja_asignada="Terminal KDS Cocina",
            estado="Activo",
        )
        cls.user_bar = Usuario.objects.create(
            nombre="Patricia Gómez",
            usuario="pgomez",
            email="pgomez@parquesafari.cl",
            password=cls.pass_bar,
            cargo=cls.cargo_bar,
            caja_asignada="Terminal BDS Barra",
            estado="Activo",
        )
        cls.user_inactivo = Usuario.objects.create(
            nombre="Esteban Soto",
            usuario="esoto",
            email="esoto@parquesafari.cl",
            password=cls.pass_inactivo,
            cargo=cls.cargo_garzon,
            caja_asignada="Sin asignar",
            estado="Inactivo",
        )

    def setUp(self):
        self.client = Client()

    def _login(self, username: str, password: str):
        return self.client.post(
            reverse("login"),
            {"username": username, "password": password},
        )

    # -------------------------------------------------------------------------
    # 1. Inicio de sesión exitoso con credenciales válidas
    # -------------------------------------------------------------------------
    def test_01_login_exitoso_credenciales_validas(self):
        response = self._login("  JVALENZUELA  ", self.pass_cajero)
        self.assertRedirects(response, reverse("dashboard"))

        session = self.client.session
        self.assertEqual(session.get("usuario_id"), self.user_cajero.id)
        self.assertEqual(session.get("usuario_username"), "jvalenzuela")
        self.assertEqual(session.get("cargo_id"), "cajero")

        self.user_cajero.refresh_from_db()
        self.assertIsNotNone(self.user_cajero.ultimo_acceso)
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.user_cajero, accion="LOGIN"
            ).exists()
        )

    # -------------------------------------------------------------------------
    # 2. Rechazo de contraseña incorrecta y preservación de espacios en clave
    # -------------------------------------------------------------------------
    def test_02_rechazo_contrasena_incorrecta_y_no_strip_password(self):
        response = self._login("jvalenzuela", "ClaveIncorrecta999")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, GENERIC_AUTH_ERROR)
        self.assertIsNone(self.client.session.get("usuario_id"))

        # Verificar que NO se aplica .strip() a la contraseña
        response_spaced = self._login("jvalenzuela", f"  {self.pass_cajero}  ")
        self.assertEqual(response_spaced.status_code, 200)
        self.assertContains(response_spaced, GENERIC_AUTH_ERROR)
        self.assertIsNone(self.client.session.get("usuario_id"))

    # -------------------------------------------------------------------------
    # 3. Rechazo de contraseñas maestras antiguas '123' y '123456'
    # -------------------------------------------------------------------------
    def test_03_rechazo_claves_maestras_123_y_123456(self):
        for master_key in ("123", "123456"):
            response = self._login("cmendoza", master_key)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, GENERIC_AUTH_ERROR)
            self.assertIsNone(
                self.client.session.get("usuario_id"),
                f"La clave maestra '{master_key}' no debe autenticar usuarios.",
            )

    # -------------------------------------------------------------------------
    # 4. Rechazo de usuario inactivo sin exponer información interna
    # -------------------------------------------------------------------------
    def test_04_rechazo_usuario_inactivo_sin_enumeracion(self):
        response = self._login("esoto", self.pass_inactivo)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn(GENERIC_AUTH_ERROR, html)
        self.assertNotIn("Inactivo", html)
        self.assertNotIn("@esoto", html)
        self.assertIsNone(self.client.session.get("usuario_id"))

    # -------------------------------------------------------------------------
    # 5. Respuesta genérica ante usuario inexistente y bloqueo por rate limit
    # -------------------------------------------------------------------------
    def test_05_respuesta_generica_usuario_inexistente_y_rate_limit(self):
        response = self._login("usuario_fantasma", "CualquierClave123")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn(GENERIC_AUTH_ERROR, html)
        self.assertNotIn("no existe", html.lower())
        self.assertNotIn("usuario_fantasma", html)

        # Alcanzar el umbral de intentos fallidos (MAX_LOGIN_ATTEMPTS = 5)
        for _ in range(MAX_LOGIN_ATTEMPTS - 1):
            self._login("usuario_fantasma", "CualquierClave123")

        # El intento siguiente debe ser bloqueado con HTTP 429
        locked_response = self._login("usuario_fantasma", "CualquierClave123")
        self.assertEqual(locked_response.status_code, 429)
        self.assertIn(
            "Demasiados intentos fallidos",
            locked_response.content.decode("utf-8"),
        )

    # -------------------------------------------------------------------------
    # 6. Rechazo de acceso (Fail-Closed) cuando falla la base de datos
    # -------------------------------------------------------------------------
    def test_06_fallo_cerrado_cuando_base_de_datos_falla(self):
        with patch(
            "pos_app.views.Usuario.objects.select_related",
            side_effect=OperationalError("Simulated Neon connection failure"),
        ):
            response = self._login("jvalenzuela", self.pass_cajero)
            self.assertEqual(response.status_code, 503)
            self.assertIsNone(self.client.session.get("usuario_id"))

    # -------------------------------------------------------------------------
    # 7. Redirección o bloqueo de todas las rutas privadas sin sesión
    # -------------------------------------------------------------------------
    def test_07_bloqueo_todas_las_rutas_privadas_sin_sesion(self):
        private_url_names = [
            "dashboard",
            "pos",
            "ticket",
            "productos",
            "menus",
            "mesas",
            "usuarios",
            "fiados",
            "distribucion",
            "cocina",
            "bar",
            "estadisticas",
            "reportes",
            "configuracion",
        ]
        for name in private_url_names:
            url = reverse(name)
            res = self.client.get(url)
            self.assertRedirects(
                res,
                reverse("login"),
                msg_prefix=f"La ruta privada '{name}' ({url}) permitió acceso sin sesión.",
            )

        # Petición AJAX sin sesión debe recibir 401 JSON
        ajax_res = self.client.post(
            reverse("caja_operacion"),
            {"accion": "apertura"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(ajax_res.status_code, 401)

    # -------------------------------------------------------------------------
    # 8. Cierre real de sesión e imposibilidad de reutilizar la sesión anterior
    # -------------------------------------------------------------------------
    def test_08_cierre_real_de_sesion_post_e_invalidacion(self):
        self._login("jvalenzuela", self.pass_cajero)
        self.assertIsNotNone(self.client.session.get("usuario_id"))

        # GET a /logout/ debe ser rechazado (405 Method Not Allowed)
        get_logout = self.client.get(reverse("logout"))
        self.assertEqual(get_logout.status_code, 405)

        # POST a /logout/ debe cerrar sesión, registrar LOGOUT y redirigir a login
        post_logout = self.client.post(reverse("logout"))
        self.assertRedirects(post_logout, reverse("login"))
        self.assertIsNone(self.client.session.get("usuario_id"))
        self.assertTrue(
            LogAuditoria.objects.filter(
                usuario=self.user_cajero, accion="LOGOUT"
            ).exists()
        )

        # Intentar acceder a ruta privada después de logout debe redirigir a login
        after_logout = self.client.get(reverse("dashboard"))
        self.assertRedirects(after_logout, reverse("login"))

    # -------------------------------------------------------------------------
    # 9. Bloqueo por rol (RBAC) cuando un usuario intenta entrar a ruta ajena
    # -------------------------------------------------------------------------
    def test_09_bloqueo_rbac_rutas_no_permitidas_por_rol(self):
        # Cocina solo puede acceder a dashboard, cocina y distribucion
        self._login("mtorres", self.pass_cocina)
        forbidden_for_cocina = [
            "pos",
            "ticket",
            "mesas",
            "bar",
            "productos",
            "menus",
            "usuarios",
            "fiados",
            "estadisticas",
            "reportes",
            "configuracion",
        ]
        for route_name in forbidden_for_cocina:
            res = self.client.get(reverse(route_name))
            self.assertEqual(
                res.status_code,
                403,
                f"El rol 'cocina' no debe tener acceso a '{route_name}'.",
            )

        # Cocina tampoco puede abrir/cerrar caja
        res_caja = self.client.post(
            reverse("caja_operacion"),
            {"accion": "cierre"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_caja.status_code, 403)

        # Garzón no puede abrir/cerrar caja ni acceder a módulos de administración
        self.client.post(reverse("logout"))
        self._login("rmorales", self.pass_garzon)
        self.assertEqual(self.client.get(reverse("usuarios")).status_code, 403)
        self.assertEqual(self.client.get(reverse("configuracion")).status_code, 403)
        res_caja_garzon = self.client.post(
            reverse("caja_operacion"),
            {"accion": "apertura"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_caja_garzon.status_code, 403)

    # -------------------------------------------------------------------------
    # 10. Acceso permitido cuando el rol sí tiene autorización
    # -------------------------------------------------------------------------
    def test_10_acceso_permitido_segun_matriz_de_roles(self):
        # Admin tiene acceso total
        self._login("cmendoza", self.pass_admin)
        for route_name in (
            "dashboard",
            "pos",
            "ticket",
            "productos",
            "menus",
            "mesas",
            "usuarios",
            "fiados",
            "distribucion",
            "cocina",
            "bar",
            "estadisticas",
            "reportes",
            "configuracion",
        ):
            res = self.client.get(reverse(route_name))
            self.assertEqual(res.status_code, 200, f"Admin debe acceder a {route_name}")

        res_caja_admin = self.client.post(
            reverse("caja_operacion"),
            {"accion": "apertura"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_caja_admin.status_code, 200)

        # Cajero tiene acceso a dashboard, pos, ticket, mesas, distribucion y caja_operacion
        self.client.post(reverse("logout"))
        self._login("jvalenzuela", self.pass_cajero)
        for route_name in ("dashboard", "pos", "ticket", "mesas", "distribucion"):
            res = self.client.get(reverse(route_name))
            self.assertEqual(res.status_code, 200, f"Cajero debe acceder a {route_name}")
        res_caja_cajero = self.client.post(
            reverse("caja_operacion"),
            {"accion": "cierre"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(res_caja_cajero.status_code, 200)

        # Bar tiene acceso a dashboard, bar y distribucion
        self.client.post(reverse("logout"))
        self._login("pgomez", self.pass_bar)
        for route_name in ("dashboard", "bar", "distribucion"):
            res = self.client.get(reverse(route_name))
            self.assertEqual(res.status_code, 200, f"Bar debe acceder a {route_name}")

    # -------------------------------------------------------------------------
    # 11. Coherencia del usuario mostrado en la interfaz con la sesión activa
    # -------------------------------------------------------------------------
    def test_11_coherencia_identidad_usuario_en_interfaz_sin_sobrescritura(self):
        self._login("pgomez", self.pass_bar)
        res = self.client.get(reverse("bar"))
        self.assertEqual(res.status_code, 200)
        html = res.content.decode("utf-8")

        # Debe mostrar a Patricia Gómez (Bar) en la barra superior y lateral
        self.assertIn("Patricia Gómez", html)
        self.assertIn('id="navUserName">Patricia Gómez</div>', html)
        self.assertIn("ROL: BAR", html)
        # No debe aparecer Jean Valenzuela fijo en el modal ni en la cabecera
        self.assertNotIn("Jean Valenzuela", html)

    # -------------------------------------------------------------------------
    # 12. Almacenamiento de contraseñas como hash y nunca en texto plano
    # -------------------------------------------------------------------------
    def test_12_almacenamiento_hash_e_idempotencia_migracion(self):
        for u in Usuario.objects.all():
            self.assertTrue(
                is_password_hashed(u.password),
                f"La contraseña de {u.usuario} no está almacenada como hash.",
            )
            # Verificar que identify_hasher reconoce el formato PBKDF2 de Django
            hasher = identify_hasher(u.password)
            self.assertIsNotNone(hasher)

        self.assertNotEqual(self.user_admin.password, self.pass_admin)
        self.assertTrue(check_password(self.pass_admin, self.user_admin.password))

        # Verificar idempotencia: volver a guardar el usuario no vuelve a hashear el hash
        original_hash = self.user_admin.password
        self.user_admin.caja_asignada = "Caja Central"
        self.user_admin.save()
        self.user_admin.refresh_from_db()
        self.assertEqual(self.user_admin.password, original_hash)
        self.assertTrue(self.user_admin.check_password(self.pass_admin))

    # -------------------------------------------------------------------------
    # 13. Validación aislada de la migración 0002 con registros ficticios
    #     (conversión, conservación de hashes, login post-migración,
    #      ausencia de pérdida de campos e interrupción/re-ejecución)
    # -------------------------------------------------------------------------
    def test_13_migracion_0002_aislada_interrupcion_y_conservacion_campos(self):
        pre_hashed = make_password("ClaveYaHasheada#2026")
        initial_count = Usuario.objects.count()

        # Insertar registros ficticios mediante bulk_create para simular filas
        # heredadas con contraseñas en texto plano en PostgreSQL (sin pasar por save())
        Usuario.objects.bulk_create(
            [
                Usuario(
                    nombre="Legado Texto Plano 1",
                    usuario="legado_plano_1",
                    email="legado1@parquesafari.cl",
                    password="123",
                    cargo=self.cargo_cajero,
                    caja_asignada="Caja Test 1",
                    estado="Activo",
                ),
                Usuario(
                    nombre="Legado Prefijo Algoritmo",
                    usuario="legado_prefijo",
                    email="legado2@parquesafari.cl",
                    password="pbkdf2_sha256",
                    cargo=self.cargo_garzon,
                    caja_asignada="Caja Test 2",
                    estado="Activo",
                ),
                Usuario(
                    nombre="Legado Ya Hasheado",
                    usuario="legado_hasheado",
                    email="legado3@parquesafari.cl",
                    password=pre_hashed,
                    cargo=self.cargo_admin,
                    caja_asignada="Caja Test 3",
                    estado="Activo",
                ),
            ]
        )
        self.assertEqual(Usuario.objects.count(), initial_count + 3)

        # Ejecutar la función de migración 0002 por primera vez
        migration_0002.hash_existing_plain_passwords(apps, None)

        u1 = Usuario.objects.get(usuario="legado_plano_1")
        u2 = Usuario.objects.get(usuario="legado_prefijo")
        u3 = Usuario.objects.get(usuario="legado_hasheado")

        # 1. Conversión correcta de texto plano a hash válido (y longitud <= 255)
        self.assertTrue(is_password_hashed(u1.password))
        self.assertLessEqual(len(u1.password), 255)
        self.assertTrue(u1.check_password("123"))

        self.assertTrue(is_password_hashed(u2.password))
        self.assertTrue(u2.check_password("pbkdf2_sha256"))

        # 2. Conservación exacta de hashes ya válidos
        self.assertEqual(u3.password, pre_hashed)
        self.assertTrue(u3.check_password("ClaveYaHasheada#2026"))

        # 3. Ausencia de pérdida de usuarios o alteración de otros campos
        self.assertEqual(Usuario.objects.count(), initial_count + 3)
        self.assertEqual(u1.nombre, "Legado Texto Plano 1")
        self.assertEqual(u1.email, "legado1@parquesafari.cl")
        self.assertEqual(u1.cargo_id, "cajero")
        self.assertEqual(u1.caja_asignada, "Caja Test 1")
        self.assertEqual(u1.estado, "Activo")

        # 4. Simular interrupción parcial: se inserta otro usuario en texto plano
        #    y se re-ejecuta la migración sobre toda la tabla
        hash_u1_before_rerun = u1.password
        Usuario.objects.bulk_create(
            [
                Usuario(
                    nombre="Legado Post Interrupción",
                    usuario="legado_post_interrupcion",
                    email="legado4@parquesafari.cl",
                    password="ClavePostInterrupcion!99",
                    cargo=self.cargo_bar,
                    caja_asignada="Barra 2",
                    estado="Activo",
                )
            ]
        )
        migration_0002.hash_existing_plain_passwords(apps, None)

        u1.refresh_from_db()
        u3.refresh_from_db()
        u4 = Usuario.objects.get(usuario="legado_post_interrupcion")
        self.assertEqual(u1.password, hash_u1_before_rerun)
        self.assertEqual(u3.password, pre_hashed)
        self.assertTrue(is_password_hashed(u4.password))

        # 5. Inicio de sesión exitoso con credenciales convertidas y rechazo de clave errónea
        res_ok = self._login("legado_plano_1", "123")
        self.assertRedirects(res_ok, reverse("dashboard"))
        self.client.post(reverse("logout"))

        res_bad = self._login("legado_plano_1", "clave_equivocada")
        self.assertEqual(res_bad.status_code, 200)
        self.assertIsNone(self.client.session.get("usuario_id"))

    # -------------------------------------------------------------------------
    # 14. Defensas ante IP malformada en X-Forwarded-For, contraseña vacía
    #     y reinicio de contador de fallos tras login legítimo
    # -------------------------------------------------------------------------
    def test_14_defensas_adicionales_ip_malformada_y_reset_rate_limit(self):
        # 1. X-Forwarded-For malformado no debe provocar DataError / 503
        res_bad_ip = self.client.post(
            reverse("login"),
            {"username": "jvalenzuela", "password": "wrong"},
            HTTP_X_FORWARDED_FOR="not-a-valid-ip-address, 999.999.999.999",
            REMOTE_ADDR="invalid_remote_addr",
        )
        self.assertEqual(res_bad_ip.status_code, 200)
        self.assertContains(res_bad_ip, GENERIC_AUTH_ERROR)

        # 2. Usuario.save() debe rechazar contraseña vacía
        with self.assertRaises(ValueError):
            Usuario.objects.create(
                nombre="Sin Clave",
                usuario="sin_clave",
                email="sinclave@parquesafari.cl",
                password="",
                cargo=self.cargo_cajero,
            )

        # 3. 3 intentos fallidos seguidos de un LOGIN exitoso reinician el conteo del usuario
        for _ in range(3):
            self._login("cmendoza", "wrong_pass")
        res_login = self._login("cmendoza", self.pass_admin)
        self.assertRedirects(res_login, reverse("dashboard"))
        self.client.post(reverse("logout"))

        # Dos fallos más después del login exitoso no deben bloquear la cuenta (total desde éxito = 2 < 5)
        for _ in range(2):
            r = self._login("cmendoza", "wrong_pass")
            self.assertEqual(r.status_code, 200)


class Fase2IntegridadSemillasTests(TestCase):
    """
    Verificación integral de la Fase 2:
    - Restricciones de integridad (validadores de aplicación + CheckConstraints de BD)
    - Integridad referencial y protección de claves foráneas (PROTECT / SET_NULL / CASCADE)
    - Excepciones comerciales legítimas (diferencias de arqueo negativas, abonos en fiados)
    - Idempotencia, separación catálogo/demo y corrección de mapeos en seed_neon.py
    - Sincronización exacta entre modelos y migraciones de Django
    """

    def setUp(self):
        self.cargo_cajero = Cargo.objects.create(
            id="cajero", nombre="Cajero", nivel="Operativo"
        )
        self.cargo_garzon = Cargo.objects.create(
            id="garzon", nombre="Garzón / Mesero", nivel="Operativo"
        )
        self.user_cajero = Usuario.objects.create(
            nombre="Jean Valenzuela",
            usuario="jvalenzuela",
            email="jvalenzuela@parquesafari.cl",
            password="CajeroPassword#2026!",
            cargo=self.cargo_cajero,
            estado="Activo",
        )
        self.categoria = Categoria.objects.create(
            id="platos", nombre="Platos Calientes", icono="bi-egg-fried", color="danger"
        )
        self.producto = Producto.objects.create(
            codigo="PROD-TEST-01",
            nombre="Burger León King",
            categoria=self.categoria,
            precio=6890,
            tipo="Requiere preparación",
            destino="Cocina",
            estado="Activo",
        )
        self.menu = MenuCombo.objects.create(
            codigo="MENU-TEST-01",
            nombre="Combo Safari Familiar",
            productos_incluidos="2x Burger + 2x Bebidas",
            precio=15990,
            ahorro_estimado=2290,
            estado="Activo",
        )

    # -------------------------------------------------------------------------
    # 15. Rechazo de precios, cantidades y estados inválidos (App + DB CheckConstraint)
    # -------------------------------------------------------------------------
    def test_15_rechazo_precios_y_cantidades_invalidas_app_y_db(self):
        # A. Producto con precio <= 0 (0 o negativo) rechazado por full_clean() en save()
        for invalid_price in (0, -1, -5000):
            with self.assertRaises(ValidationError):
                Producto.objects.create(
                    codigo=f"PROD-BAD-{invalid_price}",
                    nombre="Producto Inválido",
                    categoria=self.categoria,
                    precio=invalid_price,
                )

        # B. Producto con precio <= 0 intentando eludir save() con QuerySet.update()
        #    debe ser bloqueado directamente por el CheckConstraint en la base de datos
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.filter(pk=self.producto.pk).update(precio=0)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.filter(pk=self.producto.pk).update(precio=-2500)

        # C. MenuCombo con precio <= 0 o ahorro_estimado < 0 rechazado
        with self.assertRaises(ValidationError):
            MenuCombo.objects.create(
                codigo="MENU-BAD-PRICE",
                nombre="Menú Precio Cero",
                productos_incluidos="Items",
                precio=0,
                ahorro_estimado=500,
            )
        with self.assertRaises(ValidationError):
            MenuCombo.objects.create(
                codigo="MENU-BAD-AHORRO",
                nombre="Menú Ahorro Negativo",
                productos_incluidos="Items",
                precio=9990,
                ahorro_estimado=-100,
            )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MenuCombo.objects.filter(pk=self.menu.pk).update(ahorro_estimado=-1)

        # D. Mesa con capacidad <= 0, consumo_actual < 0, comensales_actuales < 0 o estado inválido
        with self.assertRaises(ValidationError):
            Mesa.objects.create(
                numero="Mesa Test 0",
                zona="Salón Principal",
                capacidad=0,
            )
        mesa_ok = Mesa.objects.create(
            numero="Mesa Test OK",
            zona="Salón Principal",
            capacidad=4,
            consumo_actual=0,
            comensales_actuales=0,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mesa.objects.filter(pk=mesa_ok.pk).update(consumo_actual=-500)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Mesa.objects.filter(pk=mesa_ok.pk).update(estado="EstadoInexistente")

        # E. DetalleVenta: cantidad <= 0 y restricción XOR (producto vs menu)
        venta = Venta.objects.create(
            venta_num="#90001",
            modalidad="MESA",
            mesa=mesa_ok,
            usuario=self.user_cajero,
            subtotal=6890,
            iva=1309,
            total=6890,
            metodo_pago="Efectivo",
            estado="Pagado",
        )
        # Ni producto ni menú -> rechazado
        with self.assertRaises(ValidationError):
            DetalleVenta.objects.create(
                venta=venta,
                producto=None,
                menu=None,
                nombre_item="Huérfano",
                cantidad=1,
                precio_unitario=1000,
                subtotal=1000,
            )
        # Ambos producto y menú -> rechazado
        with self.assertRaises(ValidationError):
            DetalleVenta.objects.create(
                venta=venta,
                producto=self.producto,
                menu=self.menu,
                nombre_item="Doble Referencia",
                cantidad=1,
                precio_unitario=1000,
                subtotal=1000,
            )
        # Cantidad <= 0 -> rechazado
        with self.assertRaises(ValidationError):
            DetalleVenta.objects.create(
                venta=venta,
                producto=self.producto,
                nombre_item=self.producto.nombre,
                cantidad=0,
                precio_unitario=self.producto.precio,
                subtotal=0,
            )

        # F. CuadraturaCaja con conteo negativo de billetes/monedas -> rechazado
        sesion = SesionCaja.objects.create(
            cajero=self.user_cajero,
            monto_apertura=50000,
            estado="Abierta",
        )
        with self.assertRaises(ValidationError):
            CuadraturaCaja.objects.create(
                sesion=sesion,
                billetes_20000=-1,
                total_efectivo_contado=0,
            )

    # -------------------------------------------------------------------------
    # 16. Excepciones comerciales legítimas y valores borde permitidos
    # -------------------------------------------------------------------------
    def test_16_excepciones_comerciales_legitimas_y_casos_borde(self):
        # 1. MenuCombo admite ahorro_estimado = 0 (combos sin descuento promocional)
        menu_sin_ahorro = MenuCombo.objects.create(
            codigo="MENU-CERO-AHORRO",
            nombre="Pack Básico",
            productos_incluidos="1x Café + 1x Muffin",
            precio=4500,
            ahorro_estimado=0,
        )
        self.assertEqual(menu_sin_ahorro.ahorro_estimado, 0)

        # 2. SesionCaja admite diferencia negativa (faltante de caja en arqueo real)
        sesion_faltante = SesionCaja.objects.create(
            cajero=self.user_cajero,
            monto_apertura=50000,
            monto_cierre_sistema=180000,
            monto_cierre_real=175000,
            diferencia=-5000,
            estado="Cerrada",
        )
        self.assertEqual(sesion_faltante.diferencia, -5000)

        # Pero monto_apertura negativo debe ser rechazado
        with self.assertRaises(ValidationError):
            SesionCaja.objects.create(
                cajero=self.user_cajero,
                monto_apertura=-1000,
            )

        # 3. FiadoMovimiento admite monto positivo (cargo) y negativo (abono/descuento por planilla),
        #    pero rechaza monto == 0
        fiado = FiadoPersonal.objects.create(
            rut="15.111.222-3",
            trabajador="Colaborador Prueba",
            cargo_grupo="Veterinaria / Fauna",
            limite_credito=50000,
            total_acumulado=12000,
            consumos_mes=2,
            estado="Por descontar",
        )
        mov_cargo = FiadoMovimiento.objects.create(
            fiado=fiado,
            detalle="Almuerzo menú",
            cantidad=1,
            monto=6000,
        )
        mov_abono = FiadoMovimiento.objects.create(
            fiado=fiado,
            detalle="Abono descuento planilla mensual",
            cantidad=1,
            monto=-6000,
        )
        self.assertEqual(mov_cargo.monto, 6000)
        self.assertEqual(mov_abono.monto, -6000)

        with self.assertRaises(ValidationError):
            FiadoMovimiento.objects.create(
                fiado=fiado,
                detalle="Movimiento nulo inválido",
                cantidad=1,
                monto=0,
            )

        # 4. ConfiguracionPOS valida rango 0..100 para iva_porcentaje
        with self.assertRaises(ValidationError):
            ConfiguracionPOS.objects.create(
                id=99,
                iva_porcentaje=Decimal("120.00"),
            )

    # -------------------------------------------------------------------------
    # 17. Protección de claves foráneas (PROTECT / SET_NULL / CASCADE)
    # -------------------------------------------------------------------------
    def test_17_proteccion_claves_foraneas_integridad_referencial(self):
        # 1. No se puede eliminar un Cargo que tiene Usuarios asignados (PROTECT)
        with self.assertRaises(ProtectedError):
            self.cargo_cajero.delete()

        # 2. No se puede eliminar una Categoría que tiene Productos asociados (PROTECT)
        with self.assertRaises(ProtectedError):
            self.categoria.delete()

        # 3. Crear una Venta con DetalleVenta y verificar PROTECT sobre Producto, MenuCombo y Usuario
        mesa = Mesa.objects.create(numero="Mesa FK", zona="Salón Principal", capacidad=4)
        venta = Venta.objects.create(
            venta_num="#90002",
            modalidad="MESA",
            mesa=mesa,
            usuario=self.user_cajero,
            subtotal=22880,
            iva=4347,
            total=22880,
            metodo_pago="Efectivo",
            estado="Pagado",
        )
        DetalleVenta.objects.create(
            venta=venta,
            producto=self.producto,
            nombre_item=self.producto.nombre,
            cantidad=1,
            precio_unitario=self.producto.precio,
            subtotal=self.producto.precio,
        )
        DetalleVenta.objects.create(
            venta=venta,
            menu=self.menu,
            nombre_item=self.menu.nombre,
            cantidad=1,
            precio_unitario=self.menu.precio,
            subtotal=self.menu.precio,
        )

        with self.assertRaises(ProtectedError):
            self.producto.delete()
        with self.assertRaises(ProtectedError):
            self.menu.delete()
        with self.assertRaises(ProtectedError):
            self.user_cajero.delete()

        # 4. Eliminar una Mesa histórica no destruye la Venta, sino que deja venta.mesa = NULL (SET_NULL)
        mesa.delete()
        venta.refresh_from_db()
        self.assertIsNone(venta.mesa)

    # -------------------------------------------------------------------------
    # 18. Semillas (seed_neon.py): idempotencia, mapeos corregidos y separación demo
    # -------------------------------------------------------------------------
    def test_18_semillas_idempotencia_mapeos_corregidos_y_separacion_demo(self):
        # Limpiar datos previos del setUp para probar el sembrado desde cero
        DetalleVenta.objects.all().delete()
        Venta.objects.all().delete()
        Producto.objects.all().delete()
        MenuCombo.objects.all().delete()
        Categoria.objects.all().delete()
        Mesa.objects.all().delete()
        SesionCaja.objects.all().delete()
        FiadoPersonal.objects.all().delete()
        LogAuditoria.objects.all().delete()
        Usuario.objects.all().delete()
        Cargo.objects.all().delete()
        ConfiguracionPOS.objects.all().delete()

        # A. Ejecución en modo PRODUCCIÓN / CATÁLOGO BASE (incluir_datos_demo=False)
        seed_neon.poblar_base_de_datos(incluir_datos_demo=False)

        self.assertEqual(Cargo.objects.count(), 5)
        self.assertEqual(Usuario.objects.count(), 7)
        self.assertEqual(Categoria.objects.count(), 6)
        self.assertEqual(Producto.objects.count(), 14)
        self.assertEqual(MenuCombo.objects.count(), 4)
        self.assertEqual(Mesa.objects.count(), 12)
        # En modo catálogo base NO se cargan deudas de colaboradores, ni sesiones de caja demo,
        # ni mesas ocupadas con consumo ficticio
        self.assertEqual(FiadoPersonal.objects.count(), 0)
        self.assertEqual(SesionCaja.objects.count(), 0)
        self.assertEqual(Mesa.objects.filter(estado="Ocupada").count(), 0)
        self.assertEqual(Mesa.objects.filter(consumo_actual__gt=0).count(), 0)

        # Verificar corrección del mapeo de ahorro_estimado en los 4 menús
        ahorros = dict(MenuCombo.objects.values_list("codigo", "ahorro_estimado"))
        self.assertEqual(
            ahorros,
            {
                "MENU-SAF-01": 2290,
                "MENU-SAF-02": 2990,
                "MENU-SAF-03": 1700,
                "MENU-SAF-04": 1310,
            },
        )

        # Personalizar la contraseña de un usuario existente para comprobar que una re-ejecución
        # de semillas NO sobrescribe hashes existentes
        admin_user = Usuario.objects.get(usuario="cmendoza")
        admin_user.password = "ClavePersonalizadaAdmin#2026"
        admin_user.save()
        custom_hash = admin_user.password

        # B. Ejecución repetida en modo DEMOSTRATIVO (incluir_datos_demo=True) dos veces seguidas
        seed_neon.poblar_base_de_datos(incluir_datos_demo=True)
        seed_neon.poblar_base_de_datos(incluir_datos_demo=True)

        # Conteos exactos sin duplicados (idempotencia garantizada)
        self.assertEqual(Cargo.objects.count(), 5)
        self.assertEqual(Usuario.objects.count(), 7)
        self.assertEqual(Categoria.objects.count(), 6)
        self.assertEqual(Producto.objects.count(), 14)
        self.assertEqual(MenuCombo.objects.count(), 4)
        self.assertEqual(Mesa.objects.count(), 12)
        self.assertEqual(FiadoPersonal.objects.count(), 5)
        self.assertEqual(SesionCaja.objects.filter(estado="Abierta").count(), 1)
        self.assertEqual(
            LogAuditoria.objects.filter(
                modulo="Sistema",
                accion="LOGIN",
                descripcion__startswith="Carga inicial de semillas",
            ).count(),
            1,
        )

        # La contraseña personalizada del administrador NO fue sobrescrita
        admin_user.refresh_from_db()
        self.assertEqual(admin_user.password, custom_hash)
        self.assertTrue(admin_user.check_password("ClavePersonalizadaAdmin#2026"))

        # Verificar asignación de mozos reales (Rodrigo Morales y Camila Silva, NUNCA el cajero Jean Valenzuela)
        for num_mesa in ("Mesa 01", "Mesa 06", "Mesa 12"):
            m = Mesa.objects.select_related("mozo_asignado").get(numero=num_mesa)
            self.assertEqual(m.estado, "Ocupada")
            self.assertIsNotNone(m.mozo_asignado)
            self.assertEqual(m.mozo_asignado.usuario, "rmorales")
            self.assertEqual(m.mozo_asignado.cargo_id, "garzon")

        for num_mesa in ("Mesa 03", "Mesa 09"):
            m = Mesa.objects.select_related("mozo_asignado").get(numero=num_mesa)
            self.assertEqual(m.estado, "Ocupada")
            self.assertIsNotNone(m.mozo_asignado)
            self.assertEqual(m.mozo_asignado.usuario, "csilva")
            self.assertEqual(m.mozo_asignado.cargo_id, "garzon")

        # Verificar corrección de cargo_grupo y limite_credito en FiadoPersonal
        fiado_hector = FiadoPersonal.objects.get(rut="15.421.890-3")
        self.assertEqual(fiado_hector.cargo_grupo, "Guía Safari Leones")
        self.assertEqual(fiado_hector.limite_credito, 50000)
        self.assertEqual(fiado_hector.total_acumulado, 24500)

        fiado_fernando = FiadoPersonal.objects.get(rut="13.882.104-K")
        self.assertEqual(fiado_fernando.cargo_grupo, "Veterinario Fauna Mayor")
        self.assertEqual(fiado_fernando.limite_credito, 60000)
        self.assertEqual(fiado_fernando.total_acumulado, 18900)

        fiado_rosa = FiadoPersonal.objects.get(rut="18.334.901-2")
        self.assertEqual(fiado_rosa.cargo_grupo, "Educación Ambiental")
        self.assertEqual(fiado_rosa.limite_credito, 35000)
        self.assertEqual(fiado_rosa.total_acumulado, 5400)
        self.assertEqual(fiado_rosa.estado, "Al día")

    # -------------------------------------------------------------------------
    # 19. Coherencia estricta entre modelos y migraciones (sin cambios pendientes)
    # -------------------------------------------------------------------------
    def test_19_coherencia_modelos_y_migraciones_django(self):
        # Si existiera cualquier divergencia entre pos_app/models.py y pos_app/migrations/,
        # makemigrations --check lanzaría SystemExit(1)
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)


class Fase3FlujoTransaccionalPosTests(TestCase):
    """
    Pruebas de aceptación de la Fase 03: Flujo Transaccional del Punto de Venta.
    Verifica extremo a extremo:
    - Venta inmediata (BAR) con cálculo exacto en CLP de Subtotal Neto, IVA (19%) y Total.
    - Pedido en MESA con boleta diferida, bloqueo de mesas ocupadas y descomposición de combos.
    - Persistencia y visualización en POS, Mesas, Tickets, Cocina KDS, Bar BDS y Distribución.
    - Secuencia de estados de comandas en Cocina y Bar hasta la entrega + RBAC por estación.
    - Inmunidad ante manipulación de precios/totales desde DevTools.
    - Prevención de ventas duplicadas mediante clave de idempotencia.
    - Casos de error, validación de cantidades/inactivos y rollback transaccional.
    """

    @classmethod
    def setUpTestData(cls):
        seed_neon.poblar_base_de_datos(incluir_datos_demo=False)

    def setUp(self):
        self.client = Client()
        self.seed_password = "Safari2026!"

    def _login(self, username: str):
        res = self.client.post(
            reverse("login"),
            {"username": username, "password": self.seed_password},
        )
        self.assertRedirects(res, reverse("dashboard"))

    def _post_json(self, url_name: str, payload: dict):
        import json as _json

        return self.client.post(
            reverse(url_name),
            data=_json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    # -------------------------------------------------------------------------
    # 20. Venta inmediata válida (BAR), pestaña Menús & Combos y cálculo Neto/IVA/Total
    # -------------------------------------------------------------------------
    def test_20_venta_inmediata_bar_y_calculo_exacto_neto_iva_total(self):
        self._login("jvalenzuela")

        # 1. Comprobar que /pos/ renderiza los 4 Menús & Combos en el grid del catálogo
        res_pos = self.client.get(reverse("pos"))
        self.assertEqual(res_pos.status_code, 200)
        pos_html = res_pos.content.decode("utf-8")
        self.assertIn('data-item-type="menu"', pos_html)
        self.assertIn("Menú Safari Aventura", pos_html)
        self.assertIn("Pack Explorador León", pos_html)
        self.assertIn('id="cartIva"', pos_html)

        # 2. Emitir venta inmediata en BAR: 2x Hamburguesa ($6.990) + 1x Jugo Guayaba-Mango ($3.200)
        prod_burger = Producto.objects.get(codigo="COM-001")
        prod_jugo = Producto.objects.get(codigo="BEB-001")

        res_venta = self._post_json(
            "procesar_venta",
            {
                "idempotency_key": "idem-bar-venta-01",
                "modalidad": "BAR",
                "metodo_pago": "Tarjeta Débito",
                "notas": "Hamburguesas sin pepinillos; jugo con poco hielo",
                "items": [
                    {"tipo": "producto", "id": prod_burger.id, "cantidad": 2},
                    {"tipo": "producto", "id": prod_jugo.id, "cantidad": 1},
                ],
            },
        )
        self.assertEqual(res_venta.status_code, 201)
        body = res_venta.json()
        self.assertTrue(body["ok"])
        self.assertFalse(body["idempotent_replay"])

        venta_data = body["venta"]
        venta_num = venta_data["venta_num"]

        # Total esperado: 2 * 6990 + 3200 = 17180
        # Subtotal neto: round(17180 / 1.19) = 14437; IVA: 17180 - 14437 = 2743
        self.assertEqual(venta_data["total"], 17180)
        self.assertEqual(venta_data["subtotal"], 14437)
        self.assertEqual(venta_data["iva"], 2743)
        self.assertEqual(venta_data["subtotal"] + venta_data["iva"], venta_data["total"])

        # 3. Verificar persistencia en PostgreSQL / BD
        venta_db = Venta.objects.get(venta_num=venta_num)
        self.assertEqual(venta_db.estado, "Pagado")
        self.assertTrue(venta_db.boleta_emitida)
        self.assertEqual(venta_db.metodo_pago, "Tarjeta Débito")
        self.assertEqual(venta_db.detalles.count(), 2)
        self.assertEqual(venta_db.comandas.count(), 2)
        self.assertTrue(ComandaProduccion.objects.filter(venta=venta_db, area_destino="COCINA").exists())
        self.assertTrue(ComandaProduccion.objects.filter(venta=venta_db, area_destino="BAR").exists())

        # 4. Recargar /ticket/ y /distribucion/ y verificar que los datos reales persisten
        res_ticket = self.client.get(reverse("ticket") + f"?venta_num={venta_num}")
        self.assertEqual(res_ticket.status_code, 200)
        ticket_html = res_ticket.content.decode("utf-8")
        self.assertIn(venta_num, ticket_html)
        self.assertIn("$17.180", ticket_html)
        self.assertIn("$14.437", ticket_html)
        self.assertIn("$2.743", ticket_html)
        self.assertIn("TARJETA DÉBITO", ticket_html)
        self.assertNotIn("$3.500", ticket_html)  # El precio fijo antiguo ya no existe

        res_dist = self.client.get(reverse("distribucion"))
        self.assertEqual(res_dist.status_code, 200)
        dist_html = res_dist.content.decode("utf-8")
        self.assertIn(venta_num, dist_html)
        self.assertIn("Hamburguesa Safari Especial", dist_html)
        self.assertIn("Jugo Natural Guayaba-Mango", dist_html)

    # -------------------------------------------------------------------------
    # 21. Pedido para una Mesa (boleta diferida) y descomposición de Combo en Cocina y Bar
    # -------------------------------------------------------------------------
    def test_21_pedido_mesa_boleta_diferida_ocupacion_y_descomposicion_combo(self):
        self._login("rmorales")

        menu_explorador = MenuCombo.objects.get(codigo="MENU-SAF-02")  # $11.500 (Churrasco + Jugo + Sundae)
        mesa_02 = Mesa.objects.get(numero="Mesa 02")
        self.assertEqual(mesa_02.estado, "Disponible")

        res = self._post_json(
            "procesar_venta",
            {
                "idempotency_key": "idem-mesa-combo-01",
                "modalidad": "MESA",
                "mesa_numero": "Mesa 02",
                "metodo_pago": "Efectivo",
                "notas": "Churrasco bien jugoso",
                "items": [
                    {"tipo": "menu", "id": menu_explorador.id, "cantidad": 1},
                ],
            },
        )
        self.assertEqual(res.status_code, 201)
        venta_data = res.json()["venta"]
        venta_num = venta_data["venta_num"]

        # 1. Verificar que el combo NO duplica su precio al descomponerse
        self.assertEqual(venta_data["total"], 11500)
        self.assertEqual(venta_data["subtotal"], 9664)
        self.assertEqual(venta_data["iva"], 1836)
        self.assertFalse(venta_data["boleta_emitida"])
        self.assertEqual(venta_data["estado"], "Pendiente")

        venta_db = Venta.objects.get(venta_num=venta_num)
        self.assertEqual(venta_db.detalles.count(), 1)
        det = venta_db.detalles.first()
        self.assertEqual(det.menu_id, menu_explorador.id)
        self.assertEqual(det.precio_unitario, 11500)
        self.assertEqual(det.subtotal, 11500)

        # 2. Verificar que Mesa 02 quedó Ocupada en PostgreSQL con consumo $11.500 y mozo Rodrigo Morales
        mesa_02.refresh_from_db()
        self.assertEqual(mesa_02.estado, "Ocupada")
        self.assertEqual(mesa_02.consumo_actual, 11500)
        self.assertEqual(mesa_02.mozo_asignado.usuario, "rmorales")

        # 3. Verificar que se generaron comandas tanto para COCINA (Churrasco) como para BAR (Jugo + Sundae)
        self.assertIsNotNone(venta_data["comanda_cocina"])
        self.assertIsNotNone(venta_data["comanda_bar"])
        self.assertEqual(len(venta_data["comanda_cocina"]["items"]), 1)
        self.assertIn("Churrasco León Italiano", venta_data["comanda_cocina"]["items"][0]["nombre"])
        self.assertEqual(len(venta_data["comanda_bar"]["items"]), 2)

        # 4. Recargar /mesas/, /cocina/ y /bar/ para comprobar persistencia real
        res_mesas = self.client.get(reverse("mesas"))
        self.assertEqual(res_mesas.status_code, 200)
        self.assertIn("$11.500", res_mesas.content.decode("utf-8"))

        self.client.post(reverse("logout"))
        self._login("mtorres")  # Rol Cocina
        res_cocina = self.client.get(reverse("cocina"))
        self.assertEqual(res_cocina.status_code, 200)
        self.assertIn(f"C-{venta_num}", res_cocina.content.decode("utf-8"))
        self.assertIn("Churrasco León Italiano", res_cocina.content.decode("utf-8"))

        self.client.post(reverse("logout"))
        self._login("pgomez")  # Rol Bar
        res_bar = self.client.get(reverse("bar"))
        self.assertEqual(res_bar.status_code, 200)
        self.assertIn(f"B-{venta_num}", res_bar.content.decode("utf-8"))
        self.assertIn("Jugo Natural Guayaba-Mango", res_bar.content.decode("utf-8"))
        self.assertIn("Copa Sundae León Chocolate", res_bar.content.decode("utf-8"))

    # -------------------------------------------------------------------------
    # 22. Avance de estados en Cocina KDS y Bar BDS hasta entrega y RBAC por estación
    # -------------------------------------------------------------------------
    def test_22_avance_estados_comandas_cocina_y_bar_hasta_entrega_y_rbac(self):
        self._login("jvalenzuela")
        prod_cocina = Producto.objects.get(codigo="COM-001")
        prod_bar = Producto.objects.get(codigo="BEB-002")

        res_v = self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Efectivo",
                "items": [
                    {"tipo": "producto", "id": prod_cocina.id, "cantidad": 1},
                    {"tipo": "producto", "id": prod_bar.id, "cantidad": 1},
                ],
            },
        )
        venta_num = res_v.json()["venta"]["venta_num"]
        cod_cocina = f"C-{venta_num}"
        cod_bar = f"B-{venta_num}"

        # 1. Usuario de Cocina avanza C-<num>: Pendiente -> En preparación -> Preparado -> Entregado
        self.client.post(reverse("logout"))
        self._login("mtorres")

        # Cocina NO puede modificar comanda de BAR (403)
        res_forbidden = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_bar, "accion": "preparar"},
        )
        self.assertEqual(res_forbidden.status_code, 403)

        # Cocina inicia preparación
        r1 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_cocina, "accion": "preparar"},
        )
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json()["estado_actual"], "En preparación")
        self.assertEqual(r1.json()["contadores"]["en_preparacion"], 1)

        # Cocina marca como Preparado
        r2 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_cocina, "accion": "completar"},
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["estado_actual"], "Preparado")
        self.assertEqual(r2.json()["contadores"]["listos"], 1)

        # Cocina despacha / entrega
        r3 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_cocina, "accion": "entregar"},
        )
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["estado_actual"], "Entregado")
        self.assertEqual(r3.json()["contadores"]["todos"], 0)

        # 2. Usuario de Bar avanza B-<num>: Pendiente -> En preparación -> Listo -> Entregado
        self.client.post(reverse("logout"))
        self._login("pgomez")

        # Bar NO puede modificar comanda de COCINA (403)
        res_forbidden_bar = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_cocina, "accion": "preparar"},
        )
        self.assertEqual(res_forbidden_bar.status_code, 403)

        b1 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_bar, "accion": "preparar"},
        )
        self.assertEqual(b1.status_code, 200)
        self.assertEqual(b1.json()["estado_actual"], "En preparación")

        b2 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_bar, "accion": "completar"},
        )
        self.assertEqual(b2.status_code, 200)
        self.assertEqual(b2.json()["estado_actual"], "Listo")

        b3 = self._post_json(
            "actualizar_estado_comanda",
            {"codigo_comanda": cod_bar, "accion": "entregar"},
        )
        self.assertEqual(b3.status_code, 200)
        self.assertEqual(b3.json()["estado_actual"], "Entregado")

        # 3. Verificar en base de datos que tanto ComandaProduccion como DetalleVenta quedaron en 'Entregado'
        self.assertEqual(ComandaProduccion.objects.get(codigo_comanda=cod_cocina).estado, "Entregado")
        self.assertEqual(ComandaProduccion.objects.get(codigo_comanda=cod_bar).estado, "Entregado")
        for det in DetalleVenta.objects.filter(venta__venta_num=venta_num):
            self.assertEqual(det.estado_produccion, "Entregado")

    # -------------------------------------------------------------------------
    # 23. Intento de alterar precios/totales desde DevTools ignorado por el servidor
    # -------------------------------------------------------------------------
    def test_23_manipulacion_precios_devtools_ignorada_por_servidor(self):
        self._login("jvalenzuela")
        churrasco = Producto.objects.get(codigo="COM-002")  # Precio oficial: $7.490

        res = self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Efectivo",
                "subtotal": 10,
                "iva": 0,
                "total": 10,
                "descuento": 7480,
                "items": [
                    {
                        "tipo": "producto",
                        "id": churrasco.id,
                        "cantidad": 2,
                        "precio": 5,
                        "precio_unitario": 5,
                        "subtotal": 10,
                    }
                ],
            },
        )
        self.assertEqual(res.status_code, 201)
        venta_data = res.json()["venta"]

        # El servidor DEBE usar el precio oficial de PostgreSQL: 2 * $7.490 = $14.980
        self.assertEqual(venta_data["total"], 14980)
        venta_db = Venta.objects.get(venta_num=venta_data["venta_num"])
        self.assertEqual(venta_db.total, 14980)
        self.assertEqual(venta_db.detalles.first().precio_unitario, 7490)
        self.assertEqual(venta_db.detalles.first().subtotal, 14980)

    # -------------------------------------------------------------------------
    # 24. Prevención de ventas duplicadas (idempotencia en envíos repetidos)
    # -------------------------------------------------------------------------
    def test_24_idempotencia_doble_envio_no_duplica_venta_ni_consumo_mesa(self):
        self._login("rmorales")
        prod = Producto.objects.get(codigo="COM-001")  # $6.990

        payload = {
            "idempotency_key": "idem-unique-retry-key-999",
            "modalidad": "MESA",
            "mesa_numero": "Mesa 05",
            "metodo_pago": "Efectivo",
            "items": [{"tipo": "producto", "id": prod.id, "cantidad": 1}],
        }

        res1 = self._post_json("procesar_venta", payload)
        self.assertEqual(res1.status_code, 201)
        self.assertFalse(res1.json()["idempotent_replay"])

        # Segundo envío idéntico (simulando doble clic o reintento de red)
        res2 = self._post_json("procesar_venta", payload)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.json()["idempotent_replay"])
        self.assertEqual(res1.json()["venta"]["venta_num"], res2.json()["venta"]["venta_num"])

        # Solo existe 1 venta y el consumo de Mesa 05 NO se duplicó ($6.990, no $13.980)
        self.assertEqual(Venta.objects.count(), 1)
        mesa_05 = Mesa.objects.get(numero="Mesa 05")
        self.assertEqual(mesa_05.consumo_actual, 6990)

    # -------------------------------------------------------------------------
    # 25. Rechazo de mesas ocupadas, cantidades inválidas, inactivos, sin permisos y rollback
    # -------------------------------------------------------------------------
    def test_25_rechazo_mesa_ocupada_cantidades_invalidas_productos_inactivos_y_rollback(self):
        self._login("jvalenzuela")
        prod_activo = Producto.objects.get(codigo="COM-001")

        # 1. Ocupar Mesa 07 legítimamente
        r_ok = self._post_json(
            "procesar_venta",
            {
                "modalidad": "MESA",
                "mesa_numero": "Mesa 07",
                "items": [{"tipo": "producto", "id": prod_activo.id, "cantidad": 1}],
            },
        )
        self.assertEqual(r_ok.status_code, 201)
        self.assertEqual(Venta.objects.count(), 1)

        # 2. Intentar abrir un nuevo pedido seleccionando la Mesa 07 que ya está Ocupada -> 409 Conflict
        r_conflict = self._post_json(
            "procesar_venta",
            {
                "modalidad": "MESA",
                "mesa_numero": "Mesa 07",
                "items": [{"tipo": "producto", "id": prod_activo.id, "cantidad": 1}],
            },
        )
        self.assertEqual(r_conflict.status_code, 409)
        self.assertEqual(Venta.objects.count(), 1)

        # 3. Intentar vender cantidades inválidas (0, negativa, booleana, excesiva) -> 400 Bad Request
        for bad_qty in (0, -2, True, 500):
            r_bad_qty = self._post_json(
                "procesar_venta",
                {
                    "modalidad": "BAR",
                    "items": [{"tipo": "producto", "id": prod_activo.id, "cantidad": bad_qty}],
                },
            )
            self.assertEqual(r_bad_qty.status_code, 400)
        self.assertEqual(Venta.objects.count(), 1)

        # 4. Intentar vender un producto Agotado / Inactivo -> 400 y rollback total
        prod_agotado = Producto.objects.get(codigo="COM-005")
        prod_agotado.estado = "Agotado"
        prod_agotado.save()

        r_inactive = self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "items": [
                    {"tipo": "producto", "id": prod_activo.id, "cantidad": 1},
                    {"tipo": "producto", "id": prod_agotado.id, "cantidad": 1},
                ],
            },
        )
        self.assertEqual(r_inactive.status_code, 400)
        # Verificar rollback: tampoco se registró el producto válido de esa misma transacción
        self.assertEqual(Venta.objects.count(), 1)

        # 5. Rol no autorizado (Cocina) intentando procesar una venta en POS -> 403 Forbidden
        self.client.post(reverse("logout"))
        self._login("mtorres")
        r_forbidden = self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "items": [{"tipo": "producto", "id": prod_activo.id, "cantidad": 1}],
            },
        )
        self.assertEqual(r_forbidden.status_code, 403)

    # -------------------------------------------------------------------------
    # 26. Reasignación y cobro/liberación transaccional de mesas
    # -------------------------------------------------------------------------
    def test_26_reasignacion_y_liberacion_transaccional_de_mesa(self):
        self._login("rmorales")
        prod = Producto.objects.get(codigo="COM-001")  # $6.990

        # Abrir pedido en Mesa 08
        r_venta = self._post_json(
            "procesar_venta",
            {
                "modalidad": "MESA",
                "mesa_numero": "Mesa 08",
                "items": [{"tipo": "producto", "id": prod.id, "cantidad": 2}],
            },
        )
        self.assertEqual(r_venta.status_code, 201)
        venta_num = r_venta.json()["venta"]["venta_num"]

        # Reasignar de Mesa 08 (Ocupada) a Mesa 10 (Disponible)
        r_reasignar = self._post_json(
            "mesa_operacion",
            {
                "accion": "reasignar",
                "mesa_origen": "Mesa 08",
                "mesa_destino": "Mesa 10",
            },
        )
        self.assertEqual(r_reasignar.status_code, 200)

        m08 = Mesa.objects.get(numero="Mesa 08")
        m10 = Mesa.objects.get(numero="Mesa 10")
        self.assertEqual(m08.estado, "Disponible")
        self.assertEqual(m08.consumo_actual, 0)
        self.assertEqual(m10.estado, "Ocupada")
        self.assertEqual(m10.consumo_actual, 13980)
        self.assertEqual(Venta.objects.get(venta_num=venta_num).mesa, m10)

        # Cobrar y liberar Mesa 10
        r_liberar = self._post_json(
            "mesa_operacion",
            {
                "accion": "liberar",
                "mesa_origen": "Mesa 10",
                "metodo_pago": "Tarjeta Crédito",
            },
        )
        self.assertEqual(r_liberar.status_code, 200)

        m10.refresh_from_db()
        venta_cerrada = Venta.objects.get(venta_num=venta_num)
        self.assertEqual(m10.estado, "Disponible")
        self.assertEqual(m10.consumo_actual, 0)
        self.assertEqual(venta_cerrada.estado, "Pagado")
        self.assertTrue(venta_cerrada.boleta_emitida)
        self.assertEqual(venta_cerrada.metodo_pago, "Tarjeta Crédito")


class Fase4a7IntegralTests(TestCase):
    """
    Suite integral para Fases 04, 05, 06 y 07:
    - Fase 04: Caja, Cuadratura (efectivo esperado vs otros medios) y Fiados (alta, cargo, límite, abono, idempotencia, inmutabilidad).
    - Fase 05: Mantenedores administrativos (Productos, Menús, Usuarios con PBKDF2, Configuración y RBAC).
    - Fase 06: Dashboard, Estadísticas, Reportes (con exportación CSV) y Página 404 personalizada con HTTP 404.
    - Fase 07: Flujo extremo a extremo completo en base de datos.
    """

    @classmethod
    def setUpTestData(cls):
        seed_neon.poblar_base_de_datos(incluir_datos_demo=False)

    def setUp(self):
        self.client = Client()
        self.seed_password = "Safari2026!"

    def _login(self, username: str):
        res = self.client.post(
            reverse("login"),
            {"username": username, "password": self.seed_password},
        )
        self.assertEqual(res.status_code, 302)
        return res

    def _post_json(self, url_name: str, payload: dict):
        import json

        return self.client.post(
            reverse(url_name),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    # -------------------------------------------------------------------------
    # 27. Fase 04 — Caja: apertura, distinción de medios de pago, cuadratura y cierre
    # -------------------------------------------------------------------------
    def test_27_fase4_caja_apertura_efectivo_esperado_cuadratura_y_cierre(self):
        self._login("jvalenzuela")

        # 1. Apertura de caja con fondo inicial $50.000
        r_open = self._post_json(
            "caja_operacion",
            {"accion": "apertura", "monto_apertura": 50000, "idempotency_key": "open-01"},
        )
        self.assertEqual(r_open.status_code, 200)
        self.assertTrue(r_open.json()["ok"])
        self.assertEqual(SesionCaja.objects.filter(estado="Abierta").count(), 1)

        # 2. Intento de doble apertura incompatible -> 400 Bad Request (caja_ya_abierta)
        r_dup_open = self._post_json(
            "caja_operacion",
            {"accion": "apertura", "monto_apertura": 30000},
        )
        self.assertEqual(r_dup_open.status_code, 400)
        self.assertEqual(r_dup_open.json()["code"], "caja_ya_abierta")

        # 3. Registrar ventas en distintos medios de pago
        prod_1 = Producto.objects.get(codigo="COM-001")  # $6.990
        prod_2 = Producto.objects.get(codigo="COM-003")  # $3.200

        # Venta Efectivo: 2 x $6.990 = $13.980
        self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Efectivo",
                "items": [{"tipo": "producto", "id": prod_1.id, "cantidad": 2}],
            },
        )
        # Venta Tarjeta Débito: 1 x $3.200 = $3.200 (NO entra al efectivo físico esperado)
        self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Tarjeta Débito",
                "items": [{"tipo": "producto", "id": prod_2.id, "cantidad": 1}],
            },
        )
        # Venta Vale Fiado: 1 x $6.990 = $6.990 (NO entra al efectivo físico esperado)
        self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Vale Fiado",
                "items": [{"tipo": "producto", "id": prod_1.id, "cantidad": 1}],
            },
        )

        # 4. Consultar estado de caja en vivo
        r_estado = self._post_json("caja_operacion", {"accion": "estado"})
        self.assertEqual(r_estado.status_code, 200)
        estado_caja = r_estado.json()["caja"]
        self.assertEqual(estado_caja["monto_apertura"], 50000)
        self.assertEqual(estado_caja["ventas_efectivo"], 13980)
        self.assertEqual(estado_caja["ventas_tarjetas"], 3200)
        self.assertEqual(estado_caja["ventas_fiado"], 6990)
        # Efectivo esperado = $50.000 (apertura) + $13.980 (solo efectivo) = $63.980
        self.assertEqual(estado_caja["efectivo_esperado"], 63980)

        # 5. Cerrar caja registrando denominaciones físicas por $64.000 (diferencia +$20)
        r_close = self._post_json(
            "caja_operacion",
            {
                "accion": "cierre",
                "billetes_20000": 3,
                "billetes_1000": 4,
                "observaciones": "Sobrante de $20 por redondeo en efectivo.",
            },
        )
        self.assertEqual(r_close.status_code, 200)
        cierre_data = r_close.json()
        self.assertEqual(cierre_data["monto_cierre_sistema"], 63980)
        self.assertEqual(cierre_data["monto_cierre_real"], 64000)
        self.assertEqual(cierre_data["diferencia"], 20)

        sesion = SesionCaja.objects.first()
        self.assertEqual(sesion.estado, "Cerrada")
        cuadratura = sesion.cuadratura
        self.assertIsNotNone(cuadratura)
        self.assertEqual(cuadratura.total_efectivo_contado, 64000)
        self.assertEqual(sesion.diferencia, 20)

        # 6. Intento de cerrar nuevamente una caja ya cerrada -> 400 Bad Request (caja_no_abierta)
        r_dup_close = self._post_json("caja_operacion", {"accion": "cierre"})
        self.assertEqual(r_dup_close.status_code, 400)
        self.assertEqual(r_dup_close.json()["code"], "caja_no_abierta")

    # -------------------------------------------------------------------------
    # 28. Fase 04 — Fiados: alta, cargo, control de límite, abono, idempotencia e inmutabilidad
    # -------------------------------------------------------------------------
    def test_28_fase4_fiados_alta_cargo_limite_credito_abono_idempotencia_e_inmutabilidad(self):
        self._login("cmendoza")

        # 1. Crear cuenta de fiado con límite de $20.000
        r_alta = self._post_json(
            "fiado_operacion",
            {
                "accion": "crear_cuenta",
                "rut": "17.654.321-8",
                "trabajador": "Camila Soto",
                "cargo_grupo": "Veterinaria",
                "limite_credito": 20000,
            },
        )
        self.assertIn(r_alta.status_code, (200, 201))
        fiado_id = r_alta.json()["fiado_id"]

        # 2. Registrar cargo con idempotency_key por $12.000
        r_cargo = self._post_json(
            "fiado_operacion",
            {
                "accion": "cargo",
                "fiado_id": fiado_id,
                "detalle": "Almuerzo Ejecutivo + Bebida",
                "cantidad": 1,
                "monto": 12000,
                "idempotency_key": "fiado-cargo-001",
            },
        )
        self.assertEqual(r_cargo.status_code, 200)
        cuenta = FiadoPersonal.objects.get(pk=fiado_id)
        self.assertEqual(cuenta.total_acumulado, 12000)
        self.assertEqual(cuenta.consumos_mes, 1)
        self.assertEqual(cuenta.estado, "Por descontar")

        # 3. Reintentar el mismo cargo con idempotency_key -> no duplica saldo ni movimiento
        r_replay = self._post_json(
            "fiado_operacion",
            {
                "accion": "cargo",
                "fiado_id": fiado_id,
                "detalle": "Almuerzo Ejecutivo + Bebida",
                "cantidad": 1,
                "monto": 12000,
                "idempotency_key": "fiado-cargo-001",
            },
        )
        self.assertEqual(r_replay.status_code, 200)
        self.assertTrue(r_replay.json()["idempotent_replay"])
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.total_acumulado, 12000)
        self.assertEqual(cuenta.movimientos.count(), 1)

        # 4. Intentar cargo que excede el límite de crédito ($12.000 + $10.000 > $20.000) -> 400
        r_exceso = self._post_json(
            "fiado_operacion",
            {
                "accion": "cargo",
                "fiado_id": fiado_id,
                "detalle": "Consumo Excesivo",
                "cantidad": 1,
                "monto": 10000,
            },
        )
        self.assertEqual(r_exceso.status_code, 400)
        self.assertEqual(r_exceso.json()["code"], "fiado_cupo_excedido")
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.total_acumulado, 12000)

        # 5. Registrar abono / descuento por nómina de $7.000 -> deja saldo en $5.000 y conserva historial
        r_abono = self._post_json(
            "fiado_operacion",
            {
                "accion": "abono",
                "fiado_id": fiado_id,
                "monto": 7000,
                "motivo": "Abono parcial por caja",
            },
        )
        self.assertEqual(r_abono.status_code, 200)
        cuenta.refresh_from_db()
        self.assertEqual(cuenta.total_acumulado, 5000)
        self.assertEqual(cuenta.movimientos.count(), 2)
        self.assertTrue(cuenta.movimientos.filter(monto=-7000).exists())

        # 6. Verificar inmutabilidad del historial: rechazar borrar o editar movimientos históricos
        for bad_action in ("eliminar_movimiento", "editar_movimiento"):
            r_inmut = self._post_json(
                "fiado_operacion",
                {"accion": bad_action, "fiado_id": fiado_id, "movimiento_id": 1},
            )
            self.assertEqual(r_inmut.status_code, 400)
            self.assertEqual(r_inmut.json()["code"], "fiado_historial_inmutable")

    # -------------------------------------------------------------------------
    # 29. Fase 05 — Mantenedores Administrativos (Productos, Menús, Usuarios, Config y RBAC)
    # -------------------------------------------------------------------------
    def test_29_fase5_mantenedores_productos_menus_usuarios_configuracion_y_rbac(self):
        # 1. Rol no administrador (Cajero) bloqueado en todos los endpoints de mantenedores -> 403
        self._login("jvalenzuela")
        for endpoint in (
            "producto_operacion",
            "menu_operacion",
            "usuario_operacion",
            "configuracion_operacion",
        ):
            r_forb = self._post_json(endpoint, {"accion": "crear"})
            self.assertEqual(r_forb.status_code, 403, f"Cajero debe recibir 403 en {endpoint}")

        self.client.post(reverse("logout"))
        self._login("cmendoza")

        # 2. Productos: Crear, Editar, Vender y Desactivar sin destruir historial de DetalleVenta
        r_prod_create = self._post_json(
            "producto_operacion",
            {
                "accion": "crear",
                "codigo": "COM-099",
                "nombre": "Sandwich Búfalo Especial",
                "categoria_id": "comidas",
                "precio": 7990,
                "destino": "Cocina",
                "tipo": "Requiere preparación",
                "descripcion": "Pan brioche con carne grillada y queso cheddar",
            },
        )
        self.assertIn(r_prod_create.status_code, (200, 201))
        prod_id = r_prod_create.json()["producto_id"]

        r_prod_edit = self._post_json(
            "producto_operacion",
            {
                "accion": "editar",
                "producto_id": prod_id,
                "codigo": "COM-099",
                "nombre": "Sandwich Búfalo Premium",
                "categoria_id": "comidas",
                "precio": 8490,
                "tipo": "Requiere preparación",
                "destino": "Cocina",
                "estado": "Activo",
            },
        )
        self.assertEqual(r_prod_edit.status_code, 200)
        self.assertEqual(Producto.objects.get(pk=prod_id).precio, 8490)

        # Registrar venta real de este producto para vincular DetalleVenta histórico
        self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "items": [{"tipo": "producto", "id": prod_id, "cantidad": 1}],
            },
        )
        self.assertTrue(DetalleVenta.objects.filter(producto_id=prod_id).exists())

        # Intentar eliminar físicamente un producto con ventas históricas -> bloqueado (400)
        r_prod_del = self._post_json(
            "producto_operacion",
            {"accion": "eliminar", "producto_id": prod_id},
        )
        self.assertEqual(r_prod_del.status_code, 400)

        # Desactivar producto -> estado pasa a Inactivo/Agotado, registro y DetalleVenta se conservan
        r_prod_toggle = self._post_json(
            "producto_operacion",
            {"accion": "cambiar_estado", "producto_id": prod_id, "estado": "Agotado"},
        )
        self.assertEqual(r_prod_toggle.status_code, 200)
        self.assertEqual(Producto.objects.get(pk=prod_id).estado, "Agotado")
        self.assertTrue(DetalleVenta.objects.filter(producto_id=prod_id).exists())

        # 3. Menús y Combos: Crear, Editar y Alternar estado
        r_menu_create = self._post_json(
            "menu_operacion",
            {
                "accion": "crear",
                "codigo": "MENU-099",
                "nombre": "Combo Aventura Familiar",
                "productos_incluidos": "2 Hamburguesas Safari + 2 Jugos Naturales",
                "precio": 18990,
                "ahorro_estimado": 2990,
            },
        )
        self.assertIn(r_menu_create.status_code, (200, 201))
        menu_id = r_menu_create.json()["menu_id"]

        r_menu_toggle = self._post_json(
            "menu_operacion",
            {"accion": "cambiar_estado", "menu_id": menu_id},
        )
        self.assertEqual(r_menu_toggle.status_code, 200)
        self.assertEqual(MenuCombo.objects.get(pk=menu_id).estado, "Inactivo")

        # 4. Usuarios y Cargos: Crear con hash PBKDF2, editar, cambiar clave y proteger auto-desactivación
        r_user_create = self._post_json(
            "usuario_operacion",
            {
                "accion": "crear",
                "nombre": "Lucía Fernández",
                "usuario": "lfernandez",
                "email": "lfernandez@parquesafari.cl",
                "cargo_id": "cajero",
                "caja_asignada": "Caja 02 - Acceso Norte",
                "password": "LuciaPos#2026!",
            },
        )
        self.assertIn(r_user_create.status_code, (200, 201))
        nuevo_user = Usuario.objects.get(usuario="lfernandez")
        self.assertTrue(is_password_hashed(nuevo_user.password))
        self.assertTrue(nuevo_user.check_password("LuciaPos#2026!"))

        # Impedir que el administrador desactive su propia sesión activa
        admin_user = Usuario.objects.get(usuario="cmendoza")
        r_self_deact = self._post_json(
            "usuario_operacion",
            {"accion": "cambiar_estado", "usuario_id": admin_user.id, "estado": "Inactivo"},
        )
        self.assertEqual(r_self_deact.status_code, 400)

        # 5. Configuración del Sistema: Guardar y verificar persistencia en PostgreSQL
        r_cfg = self._post_json(
            "configuracion_operacion",
            {
                "nombre_parque": "Parque Safari Chile — Rancagua",
                "razon_social": "Parque Safari S.A.",
                "rut": "76.543.210-K",
                "telefono": "+56 72 223 4567",
                "direccion": "Ruta H-30 Km 5, Rancagua",
                "terminal_caja": "CAJA-CENTRAL-01",
                "impresora_tickets": "EPSON TM-T20III (USB)",
                "impresora_cocina": "BIXOLON SRP-330II (LAN 192.168.1.50)",
                "impresora_bar": "BIXOLON SRP-330II (LAN 192.168.1.51)",
                "iva_incluido": True,
                "iva_porcentaje": "19.00",
                "alerta_acustica": True,
                "modo_full_hd": True,
            },
        )
        self.assertEqual(r_cfg.status_code, 200)
        cfg_db = ConfiguracionPOS.objects.first()
        self.assertEqual(cfg_db.terminal_caja, "CAJA-CENTRAL-01")

    # -------------------------------------------------------------------------
    # 30. Fase 06 — Dashboard, Estadísticas, Reportes (CSV) y Página 404 personalizada
    # -------------------------------------------------------------------------
    def test_30_fase6_dashboard_estadisticas_reportes_csv_y_pagina_404(self):
        self._login("cmendoza")
        prod = Producto.objects.get(codigo="COM-001")
        self._post_json(
            "procesar_venta",
            {
                "modalidad": "BAR",
                "metodo_pago": "Efectivo",
                "items": [{"tipo": "producto", "id": prod.id, "cantidad": 2}],
            },
        )

        # 1. Dashboard, Estadísticas y los 4 tipos de Reportes responden 200 con datos reales
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("estadisticas")).status_code, 200)
        for tipo in ("ventas", "productos", "tiempos", "fiados"):
            r_rep = self.client.get(reverse("reportes"), {"tipo": tipo})
            self.assertEqual(r_rep.status_code, 200)

        # 2. Exportación CSV real del reporte
        r_csv = self.client.get(reverse("reportes"), {"tipo": "ventas", "formato": "csv"})
        self.assertEqual(r_csv.status_code, 200)
        self.assertIn("text/csv", r_csv["Content-Type"])

        # 3. Rutas inexistentes devuelven HTTP 404 con templates/404.html (nunca página debug de Django)
        for bad_url in ("/pagina-que-no-existe", "/modulo-fantasma/123/xyz"):
            r_404 = self.client.get(bad_url)
            self.assertEqual(r_404.status_code, 404)
            html_404 = r_404.content.decode("utf-8")
            self.assertIn("Página no encontrada", html_404)
            self.assertNotIn("You're seeing this error because you have", html_404)

    # -------------------------------------------------------------------------
    # 31. Fase 07 — Flujo E2E completo: Apertura Caja -> Mesa -> KDS/BDS -> Cobro -> Cierre Caja
    # -------------------------------------------------------------------------
    def test_31_fase7_flujo_integral_extremo_a_extremo(self):
        self._login("cmendoza")

        # 1. Abrir sesión de caja con $40.000
        self.assertEqual(
            self._post_json("caja_operacion", {"accion": "apertura", "monto_apertura": 40000}).status_code,
            200,
        )

        # 2. Tomar pedido en Mesa 04 con productos de Cocina y Bar ($6.990 + $3.200 = $10.190)
        p_cocina = Producto.objects.get(codigo="COM-001")  # $6.990
        p_bar = Producto.objects.get(codigo="BEB-001")     # $3.200
        r_venta = self._post_json(
            "procesar_venta",
            {
                "modalidad": "MESA",
                "mesa_numero": "Mesa 04",
                "items": [
                    {"tipo": "producto", "id": p_cocina.id, "cantidad": 1},
                    {"tipo": "producto", "id": p_bar.id, "cantidad": 1},
                ],
            },
        )
        self.assertEqual(r_venta.status_code, 201)
        v_data = r_venta.json()["venta"]
        venta_num = v_data["venta_num"]
        self.assertEqual(v_data["total"], 10190)

        # 3. Procesar y despachar comandas en Cocina KDS y Bar BDS
        for codigo in (f"C-{venta_num}", f"B-{venta_num}"):
            for accion in ("iniciar", "completar", "entregar"):
                r_cmd = self._post_json(
                    "actualizar_estado_comanda",
                    {"codigo_comanda": codigo, "accion": accion},
                )
                self.assertEqual(r_cmd.status_code, 200)

        self.assertEqual(ComandaProduccion.objects.get(codigo_comanda=f"C-{venta_num}").estado, "Entregado")
        self.assertEqual(ComandaProduccion.objects.get(codigo_comanda=f"B-{venta_num}").estado, "Entregado")
        # La venta en MESA conserva estado 'Pendiente' hasta el cobro/liberación de la mesa
        self.assertEqual(Venta.objects.get(venta_num=venta_num).estado, "Pendiente")

        # 4. Cobrar y liberar Mesa 04 en Efectivo
        r_lib = self._post_json(
            "mesa_operacion",
            {"accion": "liberar", "mesa_origen": "Mesa 04", "metodo_pago": "Efectivo"},
        )
        self.assertEqual(r_lib.status_code, 200)
        self.assertEqual(Mesa.objects.get(numero="Mesa 04").estado, "Disponible")
        self.assertEqual(Venta.objects.get(venta_num=venta_num).estado, "Pagado")

        # 5. Cerrar caja con $50.190 exactos ($40.000 apertura + $10.190 venta efectivo -> diferencia $0)
        r_close = self._post_json(
            "caja_operacion",
            {
                "accion": "cierre",
                "billetes_20000": 2,
                "billetes_10000": 1,
                "monedas_100": 1,
                "monedas_50": 1,
                "monedas_5": 8,
            },
        )
        self.assertEqual(r_close.status_code, 200)
        self.assertEqual(r_close.json()["monto_cierre_sistema"], 50190)
        self.assertEqual(r_close.json()["monto_cierre_real"], 50190)
        self.assertEqual(r_close.json()["diferencia"], 0)




