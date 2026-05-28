from django.contrib import admin
from .models import (
    Medicament, CategorieMedicament, CompagniePharma,
    EffetTherapeutique, DosageMedicament, RouteMedicament, FormulaireType,
    GroupeMedicament, LigneMedicamentGroupe,
)


@admin.register(CategorieMedicament)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(CompagniePharma)
class CompagnieAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'partenaire']


@admin.register(EffetTherapeutique)
class EffetAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(DosageMedicament)
class DosageAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'frequence', 'qte_totale_par_jour', 'jours']


@admin.register(RouteMedicament)
class RouteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(FormulaireType)
class FormulaireAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'designation', 'forme', 'dosage', 'prix_vente', 'stock_actuel', 'stock_alerte', 'actif']
    search_fields = ['code', 'designation', 'dci']
    list_filter   = ['forme', 'categorie', 'actif']


class LigneMedicamentGroupeInline(admin.TabularInline):
    model = LigneMedicamentGroupe
    extra = 1


@admin.register(GroupeMedicament)
class GroupeMedicamentAdmin(admin.ModelAdmin):
    list_display = ['nom', 'medecin', 'limite']
    inlines      = [LigneMedicamentGroupeInline]
