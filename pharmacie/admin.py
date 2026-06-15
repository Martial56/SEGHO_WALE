from django.contrib import admin
from .models import Medicament, StockPharmacie, MouvementPharmacie, DispensationOrdonnance, LigneDispensation, VentePharmacie, LigneVente, InventairePharmacie, LigneInventairePharmacie


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'designation', 'forme', 'dosage', 'stock_actuel', 'actif']
    search_fields = ['code', 'designation', 'dci']
    list_filter   = ['forme', 'actif']

@admin.register(StockPharmacie)
class StockPharmacieAdmin(admin.ModelAdmin):
    list_display = ['pharmacie', 'produit', 'quantite', 'date_maj']
    list_filter  = ['pharmacie']
    search_fields = ['produit__nom', 'produit__code']

@admin.register(MouvementPharmacie)
class MouvementPharmacieAdmin(admin.ModelAdmin):
    list_display = ['date', 'pharmacie', 'produit', 'type', 'quantite', 'stock_avant', 'stock_apres']
    list_filter  = ['pharmacie', 'type']
    search_fields = ['produit__nom', 'reference']
    date_hierarchy = 'date'

class LigneDispensationInline(admin.TabularInline):
    model  = LigneDispensation
    extra  = 0
    fields = ['produit', 'medicament_libre', 'quantite_prescrite', 'quantite_dispensee']

@admin.register(DispensationOrdonnance)
class DispensationOrdonnanceAdmin(admin.ModelAdmin):
    list_display = ['pharmacie', 'ordonnance', 'statut', 'date', 'dispense_par']
    list_filter  = ['pharmacie', 'statut']
    date_hierarchy = 'date'
    inlines = [LigneDispensationInline]

class LigneVenteInline(admin.TabularInline):
    model  = LigneVente
    extra  = 0
    fields = ['produit', 'quantite', 'prix_unitaire', 'montant']
    readonly_fields = ['montant']

@admin.register(VentePharmacie)
class VentePharmacieAdmin(admin.ModelAdmin):
    list_display   = ['numero', 'pharmacie', 'date_vente', 'mode_paiement', 'montant_total', 'remise', 'montant_net', 'statut', 'cree_par']
    list_filter    = ['pharmacie', 'statut', 'mode_paiement']
    search_fields  = ['numero']
    date_hierarchy = 'date_vente'
    readonly_fields = ['date_vente', 'montant_net']
    inlines        = [LigneVenteInline]

class LigneInventairePhInline(admin.TabularInline):
    model = LigneInventairePharmacie
    extra = 0
    fields = ['produit', 'stock_theorique', 'stock_reel']
    readonly_fields = ['stock_theorique']

@admin.register(InventairePharmacie)
class InventairePharmacieAdmin(admin.ModelAdmin):
    list_display   = ['numero', 'pharmacie', 'date_inventaire', 'statut', 'cree_par', 'valide_par']
    list_filter    = ['pharmacie', 'statut']
    date_hierarchy = 'date_inventaire'
    readonly_fields = ['date_validation']
    inlines        = [LigneInventairePhInline]
