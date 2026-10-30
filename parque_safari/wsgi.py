"""
WSGI config for parque_safari project.

It exposes the WSGI callable as a module-level variable named ``application``.
Also exposes ``app`` for Vercel Serverless Function compatibility (@vercel/python).

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'parque_safari.settings')

try:
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
    app = application
except Exception:
    _init_error = traceback.format_exc()
    sys.stderr.write(f"[WSGI FATAL STARTUP ERROR]\n{_init_error}\n")

    def _fallback_error_app(environ, start_response):
        status = '500 Internal Server Error'
        headers = [
            ('Content-Type', 'text/html; charset=utf-8'),
            ('Cache-Control', 'no-store, no-cache, must-revalidate'),
        ]
        start_response(status, headers)
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error de Inicio - Parque Safari POS</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 1rem;
            box-sizing: border-box;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 2rem;
            max-width: 680px;
            width: 100%;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
        }}
        h1 {{ color: #ef4444; font-size: 1.5rem; margin-top: 0; }}
        p {{ color: #cbd5e1; line-height: 1.6; font-size: 0.95rem; }}
        .badge {{
            display: inline-block;
            background: #dc2626;
            color: #fff;
            padding: 0.2rem 0.6rem;
            border-radius: 4px;
            font-weight: 700;
            font-size: 0.8rem;
            margin-bottom: 1rem;
        }}
        .hint {{
            background: #0c4a6e;
            border-left: 4px solid #38bdf8;
            padding: 0.8rem 1.2rem;
            border-radius: 4px;
            margin: 1.2rem 0;
            font-size: 0.92rem;
            color: #e0f2fe;
            line-height: 1.5;
        }}
        pre {{
            background: #0b1120;
            color: #fca5a5;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 0.82rem;
            line-height: 1.4;
            border: 1px solid #7f1d1d;
            white-space: pre-wrap;
            word-break: break-all;
        }}
        code {{
            background: #334155;
            color: #38bdf8;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div class="card">
        <span class="badge">DJANGO STARTUP ERROR</span>
        <h1>⚠️ Error al inicializar Parque Safari POS en Vercel</h1>
        <p>El servidor serverless no pudo completar el arranque de Django debido a un problema de configuración o dependencias.</p>
        <div class="hint">
            <strong>Acción recomendada:</strong><br>
            Asegúrese de configurar la variable de entorno <code>DATABASE_URL</code> en el panel de Vercel:<br>
            <strong>Vercel Dashboard &rarr; Project Settings &rarr; Environment Variables &rarr; DATABASE_URL</strong>.
        </div>
        <p><strong>Detalle técnico del error:</strong></p>
        <pre>{_init_error}</pre>
    </div>
</body>
</html>"""
        return [html.encode('utf-8')]

    application = _fallback_error_app
    app = _fallback_error_app
