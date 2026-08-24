from django.contrib import admin
from .models import Soin
from centres.admin import ModeleCentreAdmin


@admin.register(Soin)
class SoinAdmin(ModeleCentreAdmin):
    list_display = ['patient', 'statut', 'date_creation']
    list_filter = ['statut', 'date_creation']
    search_fields = ['patient__nom', 'patient__prenoms']
