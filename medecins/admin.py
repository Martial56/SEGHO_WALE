from django.contrib import admin
from .models import Medecin, Specialite, Service, Departement, ModuleSpecialise


@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenoms', 'specialite', 'telephone', 'actif']
    search_fields = ['employe__nom', 'employe__prenoms', 'employe__matricule']
    list_filter = ['specialite', 'actif']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employe', 'specialite')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'chef_service', 'actif']


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']


@admin.register(ModuleSpecialise)
class ModuleSpecialiseAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']
    filter_horizontal = ['departements']
