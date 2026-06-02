from django.contrib import admin
from .models import RapportMedical, Vaccination


@admin.register(RapportMedical)
class RapportMedicalAdmin(admin.ModelAdmin):
    list_display = ['titre', 'type_rapport', 'periode_debut', 'periode_fin', 'redige_par', 'valide']
    list_filter = ['type_rapport', 'valide']
    search_fields = ['titre']


@admin.register(Vaccination)
class VaccinationAdmin(admin.ModelAdmin):
    list_display = ['patient', 'vaccin', 'date_vaccination', 'dose', 'prochain_rappel']
    search_fields = ['patient__nom', 'vaccin']
    list_filter = ['vaccin']
    date_hierarchy = 'date_vaccination'
