"""
pos_app/migrations/0002_hash_plain_passwords.py
Migración controlada e idempotente para:
1. Eliminar el valor por defecto en texto plano ('123456') de Usuario.password.
2. Añadir eventos de seguridad ('LOGIN_FALLIDO', 'ACCESO_DENEGADO') a LogAuditoria.accion.
3. Transformar de forma idempotente cualquier contraseña en texto plano existente en
   la tabla 'usuarios' a un hash criptográfico PBKDF2-SHA256 de Django sin exponer credenciales.

IMPORTANTE PARA PRODUCCIÓN (Neon PostgreSQL):
Antes de ejecutar `python manage.py migrate` en producción, realizar un respaldo
de la tabla `usuarios` (ej. `CREATE TABLE usuarios_backup_fase1 AS SELECT * FROM usuarios;`).
"""

from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations, models


def _is_hashed(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    if value.count('$') < 3 or len(value) < 40:
        return False
    try:
        hasher = identify_hasher(value)
        return bool(hasher.safe_summary(value))
    except (ValueError, IndexError, TypeError):
        return False


def hash_existing_plain_passwords(apps, schema_editor):
    Usuario = apps.get_model('pos_app', 'Usuario')
    for u in Usuario.objects.all().iterator():
        raw_or_hash = u.password or ''
        if raw_or_hash and not _is_hashed(raw_or_hash):
            u.password = make_password(raw_or_hash)
            u.save(update_fields=['password'])


class Migration(migrations.Migration):

    dependencies = [
        ('pos_app', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usuario',
            name='password',
            field=models.CharField(max_length=255),
        ),
        migrations.AlterField(
            model_name='logauditoria',
            name='accion',
            field=models.CharField(
                choices=[
                    ('LOGIN', 'Inicio de Sesión'),
                    ('LOGIN_FALLIDO', 'Intento de Inicio de Sesión Fallido'),
                    ('LOGOUT', 'Cierre de Sesión'),
                    ('ACCESO_DENEGADO', 'Acceso Denegado por Rol (RBAC)'),
                    ('APERTURA_CAJA', 'Apertura de Caja'),
                    ('CIERRE_CAJA', 'Cierre de Caja y Cuadratura'),
                    ('VENTA_CREADA', 'Emisión de Venta'),
                    ('COMANDA_ENVIADA', 'Envío de Comanda a Cocina/Bar'),
                    ('COMANDA_ESTADO', 'Cambio de Estado en Comanda'),
                    ('MESA_REASIGNADA', 'Reasignación de Mesa'),
                    ('PRODUCTO_MODIFICADO', 'Modificación de Producto'),
                ],
                max_length=50,
            ),
        ),
        migrations.RunPython(
            hash_existing_plain_passwords,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

