from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "SEGHO-WALE — Centre Médico-Social WALÉ"
admin.site.site_title = "SEGHO-WALE Admin"
admin.site.index_title = "Tableau de bord"

# Admin réservé aux superusers uniquement
admin.site.__class__.has_permission = lambda self, request: request.user.is_active and request.user.is_superuser

urlpatterns = [
    path('admin/', admin.site.urls),
    path('patients/', include('patients.urls')),
    path('ordonnances/', include('ordonnances.urls')),
    path('services/', include('services.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += [path('__reload__/', include('django_browser_reload.urls'))]
