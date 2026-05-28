from django.contrib import admin
from .models import Fournisseur, LotMedicament, MouvementStock, CommandePharmacies


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'telephone', 'actif']


@admin.register(LotMedicament)
class LotMedicamentAdmin(admin.ModelAdmin):
    list_display = ['medicament', 'numero_lot', 'quantite_actuelle', 'date_peremption']


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ['medicament', 'type_mouvement', 'motif', 'quantite', 'stock_avant', 'stock_apres', 'date_mouvement']
    list_filter = ['type_mouvement', 'motif']
    readonly_fields = ['date_mouvement']


@admin.register(CommandePharmacies)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ['numero', 'fournisseur', 'date_commande', 'statut', 'montant_total']
