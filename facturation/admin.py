from django.contrib import admin
from .models import Acte, Facture, LigneFacture, Paiement


@admin.register(Acte)
class ActeAdmin(admin.ModelAdmin):
    list_display = ['code', 'libelle', 'categorie', 'prix', 'actif']
    search_fields = ['code', 'libelle']
    list_filter = ['categorie', 'actif']


class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 1


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0
    readonly_fields = ['numero', 'date_paiement']


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'type_facture', 'montant_total', 'montant_paye', 'solde_restant', 'statut', 'date_emission']
    search_fields = ['numero', 'patient__nom', 'patient__prenoms']
    list_filter = ['statut', 'type_facture']
    readonly_fields = ['numero', 'date_emission']
    inlines = [LigneFactureInline, PaiementInline]


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['numero', 'facture', 'montant', 'mode_paiement', 'date_paiement']
    list_filter = ['mode_paiement']
    readonly_fields = ['numero', 'date_paiement']
