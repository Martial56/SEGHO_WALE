from django.contrib import admin

from .models import Centre
from core.middleware import get_current_centre


@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']
    list_filter = ['actif']


class ModeleCentreAdmin(admin.ModelAdmin):
    """ModelAdmin de base pour les modèles cloisonnés par centre (ModeleCentre).

    Un superuser voit les données de tous les centres ; tout autre utilisateur
    ne voit que celles de son centre actif. Le centre est affecté
    automatiquement à la création et n'est jamais modifiable ensuite.
    """

    def get_queryset(self, request):
        qs = self.model.all_objects.all()
        if request.user.is_superuser:
            return qs
        return qs.filter(centre=get_current_centre())

    def save_model(self, request, obj, form, change):
        if not change:
            obj.centre = get_current_centre()
        super().save_model(request, obj, form, change)
