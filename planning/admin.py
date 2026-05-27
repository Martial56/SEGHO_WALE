from django.contrib import admin
from .models import Bureau, PlageHoraire, PlanningHebdomadaire, Affectation


class PlageHoraireInline(admin.TabularInline):
    model = PlageHoraire
    extra = 1
    fields = ['code', 'ordre']


@admin.register(Bureau)
class BureauAdmin(admin.ModelAdmin):
    list_display = ['nom', 'ordre', 'actif']
    list_editable = ['ordre', 'actif']
    inlines = [PlageHoraireInline]


class AffectationInline(admin.TabularInline):
    model = Affectation
    extra = 0
    fields = ['plage', 'jour', 'personnel']


@admin.register(PlanningHebdomadaire)
class PlanningHebdomadaireAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'semaine_debut', 'cree_par', 'publie', 'cree_le']
    list_filter = ['publie']
    search_fields = ['semaine_debut']
    inlines = [AffectationInline]
