from django.contrib import admin
from .models import Consultation, Constante, Ordonnance, Diagnostic, DiagnosticCIM


class ConstanteInline(admin.StackedInline):
    model = Constante
    extra = 0


class DiagnosticInline(admin.TabularInline):
    model = Diagnostic
    extra = 1


class OrdonnanceInline(admin.TabularInline):
    model = Ordonnance
    extra = 0
    fields = ['numero', 'type_ordonnance', 'statut', 'date_expiration']
    readonly_fields = ['numero']


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'medecin', 'date_heure', 'statut']
    search_fields = ['numero', 'patient__nom', 'patient__prenoms']
    list_filter = ['statut', 'medecin']
    inlines = [ConstanteInline, DiagnosticInline, OrdonnanceInline]
    readonly_fields = ['numero', 'date_heure']


@admin.register(DiagnosticCIM)
class DiagnosticCIMAdmin(admin.ModelAdmin):
    list_display = ['code', 'libelle', 'categorie']
    search_fields = ['code', 'libelle']
