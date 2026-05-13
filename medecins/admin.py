from django.contrib import admin
from .models import Medecin, Specialite, Service


@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenoms', 'specialite', 'telephone', 'actif']
    search_fields = ['nom', 'prenoms', 'matricule']
    list_filter = ['specialite', 'actif']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'chef_service', 'actif']
