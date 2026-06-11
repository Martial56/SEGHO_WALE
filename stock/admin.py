from django.contrib import admin
from .models import (
    CategorieStock, Fournisseur, Produit,
    LotProduit, MouvementStock, CommandeStock, LigneCommande,
    Inventaire, LigneInventaire,
    DemandePharmacie, LigneDemande,
    FicheBesoins, LigneFicheBesoins,
)


@admin.register(CategorieStock)
class CategorieStockAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'type', 'actif']
    list_filter   = ['type', 'actif']
    search_fields = ['nom']


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display  = ['code', 'nom', 'telephone', 'email', 'actif']
    search_fields = ['nom', 'code']
    list_filter   = ['actif']


class LotProduitInline(admin.TabularInline):
    model  = LotProduit
    extra  = 0
    fields = ['numero_lot', 'date_peremption', 'quantite_actuelle', 'prix_achat_lot']


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display  = ['code', 'nom', 'type', 'categorie', 'stock_actuel', 'stock_alerte', 'prix_vente', 'actif']
    list_filter   = ['type', 'categorie', 'actif']
    search_fields = ['nom', 'code', 'dci']
    inlines       = [LotProduitInline]
    fieldsets = [
        ('Identité',    {'fields': ['code', 'nom', 'type', 'categorie', 'unite_mesure', 'description', 'actif']}),
        ('Médicament',  {'fields': ['dci', 'dosage', 'forme', 'prescription_obligatoire'], 'classes': ['collapse']}),
        ('Stock',       {'fields': ['stock_actuel', 'stock_alerte', 'stock_minimum']}),
        ('Prix',        {'fields': ['prix_achat', 'prix_vente', 'fournisseur_principal']}),
    ]


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ['date', 'produit', 'type', 'motif', 'quantite', 'stock_avant', 'stock_apres']
    list_filter  = ['type', 'motif']
    search_fields = ['produit__nom', 'reference']
    date_hierarchy = 'date'


class LigneCommandeInline(admin.TabularInline):
    model  = LigneCommande
    extra  = 1
    fields = ['produit', 'quantite_commandee', 'quantite_recue', 'prix_unitaire', 'notes']


@admin.register(CommandeStock)
class CommandeStockAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'fournisseur', 'statut', 'date_commande', 'montant_total']
    list_filter   = ['statut']
    search_fields = ['numero', 'fournisseur__nom']
    inlines       = [LigneCommandeInline]


class LigneInventaireInline(admin.TabularInline):
    model = LigneInventaire
    extra = 0
    fields = ['produit', 'stock_theorique', 'stock_reel', 'ecart', 'notes']
    readonly_fields = ['ecart']


@admin.register(Inventaire)
class InventaireAdmin(admin.ModelAdmin):
    list_display = ['numero', 'date_inventaire', 'statut', 'cree_par']
    list_filter  = ['statut']
    inlines      = [LigneInventaireInline]


class LigneDemandeInline(admin.TabularInline):
    model  = LigneDemande
    extra  = 0
    fields = ['produit', 'quantite_demandee', 'quantite_approuvee', 'notes']


@admin.register(DemandePharmacie)
class DemandePharmacieAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'pharmacie', 'statut', 'date_demande', 'cree_par', 'traite_par']
    list_filter   = ['statut', 'pharmacie']
    search_fields = ['numero']
    date_hierarchy = 'date_demande'
    inlines       = [LigneDemandeInline]
    readonly_fields = ['date_traitement']


class LigneFicheInline(admin.TabularInline):
    model  = LigneFicheBesoins
    extra  = 0
    fields = ['produit', 'stock_initial', 'qte_recue', 'qte_dispensee', 'cmm', 'qte_commander', 'qte_accordee']


@admin.register(FicheBesoins)
class FicheBesoinAdmin(admin.ModelAdmin):
    list_display  = ['numero', 'pharmacie', 'periode_debut', 'periode_fin', 'statut', 'cree_par', 'valide_par']
    list_filter   = ['statut', 'pharmacie']
    search_fields = ['numero']
    date_hierarchy = 'date_creation'
    readonly_fields = ['date_creation', 'date_validation']
    inlines       = [LigneFicheInline]
