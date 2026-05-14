from django.contrib import admin
from .models import Medecin, Specialite, Diplome, Departement, Service, DocteurReferent


@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(Diplome)
class DiplomeAdmin(admin.ModelAdmin):
    list_display = ['titre']
    search_fields = ['titre']


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']
    list_filter = ['actif']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']
    list_filter = ['actif']


@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'prenoms', 'specialite', 'telephone', 'actif']
    search_fields = ['nom', 'prenoms', 'code', 'matricule']
    list_filter = ['specialite', 'actif']
    filter_horizontal = ['departements']


@admin.register(DocteurReferent)
class DocteurReferentAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'prenoms', 'specialite', 'etablissement', 'telephone', 'actif']
    search_fields = ['nom', 'prenoms', 'code', 'etablissement']
    list_filter = ['specialite', 'actif', 'est_referent']
