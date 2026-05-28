from django.contrib import admin
from .models import Soin


@admin.register(Soin)
class SoinAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'infirmier', 'date_heure', 'statut']
    list_filter = ['statut', 'date_heure']
    search_fields = ['numero', 'patient__nom', 'patient__prenom']
    readonly_fields = ['numero']
