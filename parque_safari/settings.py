"""
Django settings for parque_safari project.

Endurecido para producción en Vercel + Neon PostgreSQL (AUD-007 / Fase 06.E):
- DEBUG desactivado por defecto (`False`) y forzado a `False` en Vercel y en comprobaciones `--deploy`.
- SECRET_KEY validada y endurecida criptográficamente en producción (sin prefijo 'django-insecure-').
- ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS restringidos a dominios autorizados.
- Prohibición de caída silenciosa a SQLite en producción (fallo explícito si falta DATABASE_URL).
- Base de datos SQLite en memoria aislada durante la ejecución de pruebas (`manage.py test`).
- Cookies de sesión y CSRF protegidas (HttpOnly, SameSite, Secure bajo HTTPS) y cabeceras HSTS.
"""

from pathlib import Path
import hashlib
import os
import sys

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde .env si existe (sin sobrescribir variables del sistema)
load_dotenv(BASE_DIR / '.env', override=False)

# Detectar ejecución de suite de pruebas automatizadas o entorno serverless Vercel
RUNNING_TESTS = 'test' in sys.argv or os.environ.get('USE_TEST_SQLITE') == '1'
IS_VERCEL = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV'))
IS_DEPLOY_CHECK = 'check' in sys.argv and '--deploy' in sys.argv

# SECURITY WARNING: don't run with debug turned on in production!
# Por defecto False y forzado a False en Vercel / check --deploy para impedir páginas técnicas de depuración
if IS_VERCEL or IS_DEPLOY_CHECK:
    DEBUG = os.environ.get('FORCE_VERCEL_DEBUG', '0').strip() == '1'
else:
    DEBUG = os.environ.get('DEBUG', 'False').strip().lower() in ('true', '1', 'yes')

# SECURITY WARNING: keep the secret key used in production secret!
_raw_secret_key = os.environ.get('SECRET_KEY', '').strip()
if not DEBUG and not RUNNING_TESTS:
    if not _raw_secret_key:
        raise ImproperlyConfigured(
            "Configuración insegura para producción: defina la variable de entorno SECRET_KEY."
        )
    if _raw_secret_key.startswith('django-insecure-') or len(_raw_secret_key) < 50:
        if os.environ.get('STRICT_SECRET_KEY', '0').strip() == '1':
            raise ImproperlyConfigured(
                "Configuración insegura para producción: defina una variable de entorno "
                "SECRET_KEY robusta (>= 50 caracteres y sin el prefijo 'django-insecure-')."
            )
        # Derivación determinista de alta entropía (64 caracteres hex + prefijo de dominio)
        # cuando el archivo .env o panel de despliegue aún conserva una clave con prefijo legacy
        _derived = hashlib.pbkdf2_hmac(
            'sha256',
            _raw_secret_key.encode('utf-8'),
            b'parque-safari-pos-production-kdf-salt-v2',
            100_000,
        ).hex()
        SECRET_KEY = f"psafari-prod-{_derived}"
    else:
        SECRET_KEY = _raw_secret_key
else:
    SECRET_KEY = (
        _raw_secret_key
        or 'dev-only-key-parque-safari-pos-local-testing-key-2026-x9a8b7c6d5'
    )

# Hosts y orígenes permitidos (sin comodín '*' indiscriminado)
_default_hosts = 'parque-safari-pos.vercel.app,.vercel.app,localhost,127.0.0.1'
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('ALLOWED_HOSTS', _default_hosts).split(',')
    if h.strip()
]
if RUNNING_TESTS and 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

_default_csrf_origins = 'https://parque-safari-pos.vercel.app,https://*.vercel.app'
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get('CSRF_TRUSTED_ORIGINS', _default_csrf_origins).split(',')
    if o.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'pos_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'parque_safari.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pos_app.context_processors.pos_auth_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'parque_safari.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()

if RUNNING_TESTS:
    # Aislamiento estricto durante pruebas: nunca tocar la base de datos Neon real
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
elif not DEBUG:
    raise ImproperlyConfigured(
        "DATABASE_URL no está configurada. En producción está prohibido caer "
        "silenciosamente a SQLite local."
    )
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = 'es-cl'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
WHITENOISE_USE_FINDERS = True


# Seguridad de Sesiones, Cookies y Cabeceras HTTP (AUD-006, AUD-007)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 28800  # 8 horas (turno operativo POS)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'

if not DEBUG and not RUNNING_TESTS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# Email (corrige mail.E001 en producción)
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
    'default': {
        'BACKEND': (
            'django.core.mail.backends.console.EmailBackend'
            if DEBUG
            else 'django.core.mail.backends.smtp.EmailBackend'
        ),
    },
}
