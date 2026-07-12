from django.contrib import admin
from .models import (
    Fournisseur, BesoinAchat, LigneBesoin,
    Proforma, LigneProforma,
    CommandeAchat, LigneCommandeAchat,
    ReceptionAchat, LigneReceptionAchat,
)


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display  = ['code', 'nom', 'telephone', 'email', 'ville', 'actif']
    search_fields = ['nom', 'code', 'email']
    list_filter   = ['actif', 'pays']


class LigneBesoinInline(admin.TabularInline):
    model = LigneBesoin
    extra = 0
    fields = ['produit', 'designation', 'quantite', 'unite', 'notes']


@admin.register(BesoinAchat)
class BesoinAchatAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'titre', 'statut', 'date_besoin_souhaite', 'cree_par']
    list_filter   = ['statut']
    search_fields = ['numero', 'titre']
    inlines       = [LigneBesoinInline]


class LigneProformaInline(admin.TabularInline):
    model = LigneProforma
    extra = 0
    fields = ['designation', 'quantite', 'prix_unitaire', 'ligne_besoin']


@admin.register(Proforma)
class ProformaAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'besoin', 'fournisseur', 'montant_total', 'statut', 'date_reception']
    list_filter   = ['statut']
    search_fields = ['numero', 'fournisseur__nom']
    inlines       = [LigneProformaInline]


class LigneCommandeInline(admin.TabularInline):
    model = LigneCommandeAchat
    extra = 0
    fields = ['designation', 'quantite_commandee', 'prix_unitaire']


@admin.register(CommandeAchat)
class CommandeAchatAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'fournisseur', 'statut', 'montant_total', 'date_commande']
    list_filter   = ['statut']
    search_fields = ['numero', 'fournisseur__nom']
    inlines       = [LigneCommandeInline]


class LigneReceptionInline(admin.TabularInline):
    model = LigneReceptionAchat
    extra = 0
    fields = ['ligne_commande', 'quantite_recue', 'conforme', 'numero_lot', 'date_peremption', 'notes']


@admin.register(ReceptionAchat)
class ReceptionAchatAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'commande', 'statut', 'date_reception', 'receptionne_par']
    list_filter   = ['statut']
    inlines       = [LigneReceptionInline]
