from django.contrib import admin

from .models import (Avoir, Bailleur, BordereauAssurance, CompteTresorerie, LigneReleve, RejetAssurance, RemiseBanque, Compte, Convention, Don, ReglementAssurance, Versement, Correspondance, Ecriture, Exercice, Journal, JourneeCaisse,
                     LigneEcriture, MotifGratuite, MotifSortie, SessionCaissiere, SortieCaisse)


class SessionInline(admin.TabularInline):
    model = SessionCaissiere
    extra = 0
    can_delete = False
    fields = ['numero', 'caissiere', 'statut', 'fonds_initial', 'montant_theorique',
              'montant_compte', 'ecart']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JourneeCaisse)
class JourneeCaisseAdmin(admin.ModelAdmin):
    list_display = ['date_journee', 'caisse', 'statut', 'cloturee_par']
    list_filter = ['statut', 'caisse']
    date_hierarchy = 'date_journee'
    readonly_fields = ['caisse', 'date_journee', 'date_ouverture', 'ouverte_par',
                       'date_cloture', 'cloturee_par']
    inlines = [SessionInline]

    def get_queryset(self, request):
        return JourneeCaisse.all_objects.select_related('caisse', 'cloturee_par')


@admin.register(SessionCaissiere)
class SessionCaissiereAdmin(admin.ModelAdmin):
    """Consultation seule : une session ne se corrige pas à la main, elle se
    clôture et se valide depuis les écrans de caisse."""
    list_display = ['numero', 'journee', 'caissiere', 'statut', 'montant_theorique',
                    'montant_compte', 'ecart']
    list_filter = ['statut', 'journee__caisse']
    search_fields = ['numero', 'caissiere__username', 'caissiere__last_name']

    def get_queryset(self, request):
        return SessionCaissiere.all_objects.select_related('journee__caisse', 'caissiere')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False


@admin.register(MotifSortie)
class MotifSortieAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'actif']
    list_filter = ['actif']


@admin.register(MotifGratuite)
class MotifGratuiteAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'remise_max', 'actif']
    list_filter = ['actif']


@admin.register(SortieCaisse)
class SortieCaisseAdmin(admin.ModelAdmin):
    """Consultation seule : une sortie se demande et se décide depuis les
    écrans de caisse."""
    list_display = ['numero', 'session', 'motif', 'libelle', 'montant', 'statut']
    list_filter = ['statut', 'motif']
    search_fields = ['numero', 'libelle', 'beneficiaire']

    def get_queryset(self, request):
        return SortieCaisse.all_objects.select_related('session', 'motif')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Avoir)
class AvoirAdmin(admin.ModelAdmin):
    """Consultation seule : un avoir naît de l'annulation d'une facture."""
    list_display = ['numero', 'facture', 'montant', 'montant_rembourse', 'mode_remboursement', 'date_creation']
    search_fields = ['numero', 'facture__numero']

    def get_queryset(self, request):
        return Avoir.all_objects.select_related('facture')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ['numero', 'intitule', 'actif', 'a_valider']
    list_filter = ['actif', 'a_valider']
    search_fields = ['numero', 'intitule']


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ['code', 'libelle', 'type', 'caisse', 'actif']


@admin.register(Correspondance)
class CorrespondanceAdmin(admin.ModelAdmin):
    list_display = ['cle', 'libelle', 'compte']
    search_fields = ['cle', 'libelle']


@admin.register(Exercice)
class ExerciceAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'date_debut', 'date_fin', 'statut']


class LigneEcritureInline(admin.TabularInline):
    model = LigneEcriture
    extra = 0
    can_delete = False
    readonly_fields = ['compte', 'libelle', 'tiers', 'debit', 'credit']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Ecriture)
class EcritureAdmin(admin.ModelAdmin):
    """Consultation seule : une écriture se génère, se saisit et se valide
    depuis les écrans de comptabilité, jamais ici."""
    list_display = ['date', 'journal', 'numero', 'libelle', 'statut']
    list_filter = ['statut', 'journal']
    search_fields = ['libelle', 'piece']
    inlines = [LigneEcritureInline]

    def get_queryset(self, request):
        return Ecriture.all_objects.select_related('journal')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(Bailleur)
class BailleurAdmin(admin.ModelAdmin):
    list_display = ['nom', 'sigle', 'type', 'actif']
    search_fields = ['nom', 'sigle']


@admin.register(Convention)
class ConventionAdmin(admin.ModelAdmin):
    list_display = ['code', 'intitule', 'bailleur', 'date_debut', 'date_fin', 'montant_accorde', 'statut']
    list_filter = ['statut', 'bailleur']

    def get_queryset(self, request):
        return Convention.all_objects.select_related('bailleur')


@admin.register(Versement)
class VersementAdmin(admin.ModelAdmin):
    list_display = ['numero', 'convention', 'date', 'montant', 'mode']

    def get_queryset(self, request):
        return Versement.all_objects.select_related('convention')


@admin.register(Don)
class DonAdmin(admin.ModelAdmin):
    list_display = ['numero', 'date', 'donateur', 'donateur_nom', 'nature', 'montant']

    def get_queryset(self, request):
        return Don.all_objects.select_related('donateur')



@admin.register(BordereauAssurance)
class BordereauAssuranceAdmin(admin.ModelAdmin):
    list_display = ['numero', 'assurance', 'date_debut', 'date_fin', 'statut', 'date_envoi']
    list_filter = ['statut', 'assurance']

    def get_queryset(self, request):
        return BordereauAssurance.all_objects.select_related('assurance')


@admin.register(ReglementAssurance)
class ReglementAssuranceAdmin(admin.ModelAdmin):
    """Consultation seule : un règlement se saisit et se répartit depuis l'écran
    des assurances."""
    list_display = ['numero', 'assurance', 'date', 'montant', 'mode', 'bordereau']

    def get_queryset(self, request):
        return ReglementAssurance.all_objects.select_related('assurance', 'bordereau')

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(CompteTresorerie)
class CompteTresorerieAdmin(admin.ModelAdmin):
    list_display = ['libelle', 'type', 'compte', 'etablissement', 'actif']


@admin.register(RemiseBanque)
class RemiseBanqueAdmin(admin.ModelAdmin):
    list_display = ['numero', 'date', 'caisse', 'compte_tresorerie', 'montant']

    def get_queryset(self, request):
        return RemiseBanque.all_objects.select_related('caisse', 'compte_tresorerie')

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LigneReleve)
class LigneReleveAdmin(admin.ModelAdmin):
    list_display = ['compte_tresorerie', 'date', 'libelle', 'montant', 'ligne_ecriture']
    list_filter = ['compte_tresorerie']


@admin.register(RejetAssurance)
class RejetAssuranceAdmin(admin.ModelAdmin):
    list_display = ['numero', 'date', 'assurance', 'facture', 'decision', 'montant']

    def get_queryset(self, request):
        return RejetAssurance.all_objects.select_related('assurance', 'facture')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
