from django.contrib import admin
from .models import Soin


@admin.register(Soin)
class SoinAdmin(admin.ModelAdmin):
    list_display = ['patient', 'statut', 'date_creation']
    list_filter = ['statut', 'date_creation']
    search_fields = ['patient__nom', 'patient__prenoms']
