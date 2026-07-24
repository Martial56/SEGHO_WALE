from django.contrib import admin, messages
from .models import Bureau, PlageHoraire, PlanningHebdomadaire, Affectation, PlanningConfig, MedecinSignataire


class PlageHoraireInline(admin.TabularInline):
    model = PlageHoraire
    extra = 1
    fields = ['code', 'ordre']

    def has_delete_permission(self, request, obj=None):
        # Même garde-fou que planning_plage_delete — l'admin ne doit pas pouvoir
        # contourner la règle métier "pas de suppression si des affectations existent".
        if obj is not None and Affectation.objects.filter(plage__bureau=obj).exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Bureau)
class BureauAdmin(admin.ModelAdmin):
    list_display = ['nom', 'ordre', 'actif']
    list_editable = ['ordre', 'actif']
    inlines = [PlageHoraireInline]

    def has_delete_permission(self, request, obj=None):
        # Même garde-fou que planning_bureau_delete — sans ça, supprimer un Bureau
        # depuis /admin/ efface en cascade ses PlageHoraire et Affectation sans avertissement.
        if obj is not None and Affectation.objects.filter(plage__bureau=obj).exists():
            return False
        return super().has_delete_permission(request, obj)


class AffectationInline(admin.TabularInline):
    model = Affectation
    extra = 0
    fields = ['plage', 'jour', 'personnel']


@admin.register(PlanningHebdomadaire)
class PlanningHebdomadaireAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'semaine_debut', 'cree_par', 'publie', 'cree_le']
    list_filter = ['publie']
    search_fields = ['semaine_debut']
    inlines = [AffectationInline]

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Les Affectation créées/éditées via cet inline ne passent pas par
        # validate_planning() (contrairement au formulaire de saisie) — on ne peut
        # pas bloquer l'enregistrement à ce stade (déjà commité par super()), mais
        # on peut au moins alerter immédiatement plutôt que de laisser un conflit
        # silencieux (double affectation, etc.).
        from .views import get_bureaux, validate_planning, _posted_from_affectations
        planning = form.instance
        posted = _posted_from_affectations(planning.affectations.all())
        errors = validate_planning(posted, get_bureaux())
        for err in errors:
            self.message_user(request, f"Conflit non résolu : {err}", level=messages.ERROR)


@admin.register(PlanningConfig)
class PlanningConfigAdmin(admin.ModelAdmin):
    list_display = ['fonction_signataire', 'medecin_defaut']

    def has_add_permission(self, request):
        # Singleton (PlanningConfig.get() ne crée que pk=1) — pas d'ajout d'une 2e ligne.
        return not PlanningConfig.objects.exists()


@admin.register(MedecinSignataire)
class MedecinSignataireAdmin(admin.ModelAdmin):
    list_display = ['nom', 'actif', 'ordre']
    list_editable = ['actif', 'ordre']
