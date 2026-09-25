from django.contrib import admin, messages

from .models import AncrageBlockchain
from .services import verifier_integrite


@admin.register(AncrageBlockchain)
class AncrageBlockchainAdmin(admin.ModelAdmin):
    list_display = ('id_evenement', 'type_entite', 'id_entite', 'code_patient', 'code_centre', 'statut', 'date_creation')
    list_filter = ('type_entite', 'statut', 'code_centre')
    search_fields = ('id_entite', 'code_patient', 'tx_id')
    readonly_fields = [f.name for f in AncrageBlockchain._meta.fields]
    actions = ['verifier_integrite_action']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Le registre applicatif reflète un registre immuable : on ne
        # supprime pas une preuve d'ancrage a posteriori.
        return False

    @admin.action(description="Vérifier l'intégrité (recalcule le hash depuis la base actuelle)")
    def verifier_integrite_action(self, request, queryset):
        for ancrage in queryset:
            resultat = verifier_integrite(ancrage)
            if resultat is None:
                self.message_user(
                    request,
                    f"{ancrage.id_evenement} : intégration blockchain désactivée (BLOCKCHAIN_ENABLED=False)",
                    level=messages.WARNING,
                )
            elif resultat.get('conforme'):
                self.message_user(request, f'{ancrage.id_evenement} : intégrité confirmée.', level=messages.SUCCESS)
            else:
                self.message_user(
                    request,
                    f"{ancrage.id_evenement} : ALTÉRATION DÉTECTÉE ou vérification impossible — {resultat}",
                    level=messages.ERROR,
                )
