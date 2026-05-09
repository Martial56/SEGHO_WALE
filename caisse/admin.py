from django.contrib import admin
from .models import Caisse, SessionCaisse, TransactionCaisse


@admin.register(Caisse)
class CaisseAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'solde_actuel', 'responsable', 'actif']


@admin.register(SessionCaisse)
class SessionCaisseAdmin(admin.ModelAdmin):
    list_display = ['caisse', 'caissier', 'date_ouverture', 'date_fermeture', 'solde_ouverture', 'solde_fermeture', 'statut']
    list_filter = ['statut', 'caisse']
    readonly_fields = ['date_ouverture']


@admin.register(TransactionCaisse)
class TransactionCaisseAdmin(admin.ModelAdmin):
    list_display = ['numero', 'session', 'type_transaction', 'mode_paiement', 'montant', 'date_transaction']
    list_filter = ['type_transaction', 'mode_paiement']
    readonly_fields = ['numero', 'date_transaction']
