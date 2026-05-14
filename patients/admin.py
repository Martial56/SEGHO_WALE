from django.contrib import admin
from .models import Patient, Assurance, RendezVous


@admin.register(Assurance)
class AssuranceAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'taux_prise_en_charge', 'actif']
    search_fields = ['nom', 'code']
    list_filter = ['actif']


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['code_patient', 'nom', 'prenoms', 'sexe', 'age', 'telephone', 'assurance', 'date_creation']
    search_fields = ['nom', 'prenoms', 'code_patient', 'telephone']
    list_filter = ['sexe', 'actif', 'assurance', 'ville']
    readonly_fields = ['code_patient', 'date_creation']
    fieldsets = (
        ('Identification', {'fields': ('code_patient', 'nom', 'prenoms', 'date_naissance', 'lieu_naissance', 'sexe', 'nationalite', 'profession', 'photo')}),
        ('Contact', {'fields': ('telephone', 'telephone2', 'email', 'adresse', 'ville')}),
        ('Médical', {'fields': ('groupe_sanguin', 'allergies', 'antecedents')}),
        ('Assurance', {'fields': ('assurance', 'numero_assurance', 'date_expiration_assurance')}),
        ('Urgence', {'fields': ('contact_urgence_nom', 'contact_urgence_telephone')}),
    )


@admin.register(RendezVous)
class RendezVousAdmin(admin.ModelAdmin):
    list_display = ['patient', 'medecin', 'date_heure', 'service', 'statut']
    list_filter = ['statut', 'service']
    search_fields = ['patient__nom', 'patient__prenoms']
    date_hierarchy = 'date_heure'
