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
    # `quantite` ne doit être modifiée qu'en passant par les vues applicatives
    # (dispensation, vente, livraison, retour, inventaire), qui créent
    # systématiquement un MouvementPharmacie associé. Un édit direct ici
    # casserait silencieusement la traçabilité (journal des mouvements).
    readonly_fields = ['quantite']

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
    # Modifier une ligne après coup ne resynchronise pas le stock déjà déduit —
    # voir StockPharmacieAdmin.readonly_fields pour la même raison.
    readonly_fields = ['produit', 'medicament_libre', 'quantite_prescrite', 'quantite_dispensee']

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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
    # Le stock a déjà été déduit au moment de la vente (MouvementPharmacie) —
    # modifier montant_total/remise après coup désynchronise la marchandise
    # sortie de la recette déclarée, sans que rien ne le détecte. Seul
    # `statut` reste éditable (utiliser "Annulée" pour corriger une erreur).
    readonly_fields = ['date_vente', 'montant_total', 'remise', 'montant_net']
    inlines        = [LigneVenteInline]

class LigneInventairePhInline(admin.TabularInline):
    model = LigneInventairePharmacie
    extra = 0
    fields = ['produit', 'stock_theorique', 'stock_reel']

    def get_readonly_fields(self, request, obj=None):
        # Une fois l'inventaire validé, le stock a déjà été ajusté en
        # conséquence des écarts saisis — les rendre modifiables après coup
        # désynchroniserait la ligne du mouvement d'ajustement déjà créé.
        if obj is not None and obj.statut == 'valide':
            return ['produit', 'stock_theorique', 'stock_reel']
        return ['stock_theorique']

@admin.register(InventairePharmacie)
class InventairePharmacieAdmin(admin.ModelAdmin):
    list_display   = ['numero', 'pharmacie', 'date_inventaire', 'statut', 'cree_par', 'valide_par']
    list_filter    = ['pharmacie', 'statut']
    date_hierarchy = 'date_inventaire'
    readonly_fields = ['date_validation']
    inlines        = [LigneInventairePhInline]

    def has_delete_permission(self, request, obj=None):
        # Même garde-fou que pharmacie_inventaire_supprimer — un inventaire
        # validé a déjà ajusté le stock ; le supprimer effacerait la
        # justification de cet ajustement sans annuler le mouvement lui-même.
        if obj is not None and obj.statut == 'valide':
            return False
        return super().has_delete_permission(request, obj)
