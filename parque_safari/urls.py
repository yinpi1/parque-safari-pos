"""
URL configuration for parque_safari project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

from pos_app.views import custom_page_not_found_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('pos_app.urls')),
    # Ruta universal de respaldo para servir estáticos en cualquier entorno serverless
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

# Ruta catch-all final para garantizar que cualquier URL inexistente devuelva templates/404.html con HTTP 404
urlpatterns += [
    re_path(r'^(?P<ruta>.*)$', custom_page_not_found_view),
]

handler404 = 'pos_app.views.custom_page_not_found_view'
handler500 = 'pos_app.views.custom_server_error_view'
