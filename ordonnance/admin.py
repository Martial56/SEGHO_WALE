from django.contrib import admin
from consultations.models import Ordonnance, LigneOrdonnance


class LigneOrdonnanceInline(admin.TabularInline):
    model = LigneOrdonnance
    extra = 1
    fields = ['produit', 'medicament_libre', 'posologie', 'duree', 'quantite', 'notes']
    autocomplete_fields = ['produit']


@admin.register(Ordonnance)
class OrdonnanceAdmin(admin.ModelAdmin):
    list_display = ['numero', 'get_patient', 'get_medecin', 'date_emission', 'type_ordonnance', 'statut', 'nb_lignes']
    list_filter  = ['statut', 'type_ordonnance', 'date_emission']
    search_fields = ['numero', 'consultation__patient__nom', 'consultation__patient__prenoms']
    readonly_fields = ['numero', 'date_emission']
    inlines = [LigneOrdonnanceInline]
    actions = ['marquer_delivree', 'marquer_expiree']

    # Une ordonnance libre n'a pas de consultation : elle porte le patient et le
    # médecin directement. Ces deux colonnes ne lisaient que la consultation, et
    # la liste de l'admin tombait en erreur dès la première ordonnance libre.
    @admin.display(description='Patient')
    def get_patient(self, obj):
        return obj.patient or (obj.consultation.patient if obj.consultation else None)

    @admin.display(description='Medecin')
    def get_medecin(self, obj):
        return obj.medecin or (obj.consultation.medecin if obj.consultation else None)

    @admin.display(description='Lignes')
    def nb_lignes(self, obj):
        return obj.lignes.count()

    @admin.action(description='Marquer comme delivrees')
    def marquer_delivree(self, request, queryset):
        queryset.update(statut='delivree')

    @admin.action(description='Marquer comme expirees')
    def marquer_expiree(self, request, queryset):
        queryset.update(statut='expiree')
