from django.contrib import admin
from .models import Medicament, CategorieMedicament, Fournisseur, LotMedicament, MouvementStock, CommandePharmacies


@admin.register(CategorieMedicament)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'telephone', 'actif']


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display = ['code', 'designation', 'forme', 'dosage', 'prix_vente', 'stock_actuel', 'stock_alerte', 'actif']
    search_fields = ['code', 'designation', 'dci']
    list_filter = ['forme', 'categorie', 'actif']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs

    def stock_status(self, obj):
        if obj.stock_actuel <= obj.stock_minimum:
            return "⚠️ Critique"
        elif obj.stock_actuel <= obj.stock_alerte:
            return "⚡ Alerte"
        return "✅ OK"
    stock_status.short_description = "Statut stock"


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ['medicament', 'type_mouvement', 'motif', 'quantite', 'stock_avant', 'stock_apres', 'date_mouvement']
    list_filter = ['type_mouvement', 'motif']
    readonly_fields = ['date_mouvement']
