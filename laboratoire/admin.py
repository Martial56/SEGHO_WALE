from django.contrib import admin
from django.contrib import messages
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from .models import (
    TypeExamen, AnalyseLaboratoire, ResultatAnalyse, ExamenImagerie,
    DemandeExamen, LigneDemandeExamen, ConfigurationHPRIM, EchangeHPRIM,
    ErreurHPRIM,
)


@admin.register(TypeExamen)
class TypeExamenAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'categorie', 'prix', 'delai_resultat_heures']
    search_fields = ['code', 'nom']


class ResultatInline(admin.TabularInline):
    model = ResultatAnalyse
    extra = 1


@admin.register(AnalyseLaboratoire)
class AnalyseAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'type_examen', 'date_prelevement', 'statut', 'urgent']
    search_fields = ['numero', 'patient__nom']
    list_filter = ['statut', 'urgent']
    readonly_fields = ['numero']
    inlines = [ResultatInline]


@admin.register(ExamenImagerie)
class ExamenImagerieAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'type_imagerie', 'zone_examinee', 'date_examen', 'statut']
    list_filter = ['statut', 'type_imagerie']
    readonly_fields = ['numero']


class LigneDemandeInlineFormSet(BaseInlineFormSet):
    """Empêche d'enregistrer une demande au statut « Demandé » sans au moins
    une ligne d'examen."""

    def clean(self):
        super().clean()
        statut = getattr(self.instance, "statut", None)
        if statut != "demande":
            return
        lignes_restantes = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            cd = form.cleaned_data
            if not cd:
                continue
            if cd.get("DELETE"):
                continue
            lignes_restantes += 1
        if lignes_restantes == 0:
            raise ValidationError(
                "Impossible de passer la demande au statut « Demandé » sans "
                "aucun examen. Ajoutez au moins une ligne d'examen, ou laissez "
                "la demande en « Brouillon »."
            )


class LigneDemandeInline(admin.TabularInline):
    model = LigneDemandeExamen
    formset = LigneDemandeInlineFormSet
    extra = 1


@admin.action(description="Envoyer au laboratoire (HPRIM / FTP)")
def action_envoyer_hprim(modeladmin, request, queryset):
    from .hprim.services import envoyer_demande
    succes, erreurs = 0, 0
    for demande in queryset:
        try:
            echange = envoyer_demande(demande)
        except Exception as exc:
            erreurs += 1
            modeladmin.message_user(
                request, f"{demande.numero} : {exc}", level=messages.ERROR)
            continue
        if echange.statut in ("transmis", "en_attente"):
            succes += 1
            modeladmin.message_user(
                request,
                f"{demande.numero} → {echange.nom_fichier} : {echange.get_statut_display()}.",
                level=messages.SUCCESS if echange.statut == "transmis" else messages.WARNING)
        else:
            erreurs += 1
            modeladmin.message_user(
                request, f"{demande.numero} : {echange.message_log}",
                level=messages.ERROR)
    if succes:
        modeladmin.message_user(
            request, f"{succes} demande(s) traitée(s).", level=messages.INFO)


@admin.register(DemandeExamen)
class DemandeExamenAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'type_test', 'statut', 'urgent', 'date_creation']
    list_filter = ['statut', 'type_test', 'urgent']
    search_fields = ['numero', 'patient__nom', 'patient__prenoms']
    readonly_fields = ['numero']
    inlines = [LigneDemandeInline]
    actions = [action_envoyer_hprim]


@admin.register(ConfigurationHPRIM)
class ConfigurationHPRIMAdmin(admin.ModelAdmin):
    list_display = ['nom', 'actif', 'emetteur_code', 'recepteur_code',
                    'ftp_host', 'date_modification']
    list_filter = ['actif']
    fieldsets = (
        ("Général", {'fields': ('nom', 'actif')}),
        ("Identités HPRIM (segment H)", {
            'fields': ('emetteur_code', 'emetteur_nom', 'recepteur_code',
                       'recepteur_nom', 'type_liaison', 'prefixe_fichier')}),
        ("Connexion FTP", {
            'fields': ('ftp_host', 'ftp_port', 'ftp_user', 'ftp_password',
                       'ftp_tls', 'repertoire_envoi', 'repertoire_reception',
                       'extension_temoin')}),
    )


@admin.action(description="Réintégrer le résultat (ORU)")
def action_reintegrer_oru(modeladmin, request, queryset):
    from .hprim.integration import integrer_oru
    for e in queryset.filter(sens="reception"):
        try:
            _p, synthese = integrer_oru(e.contenu.encode("iso-8859-1", "replace"))
            e.statut = "traite"
            e.message_log = (f"Réintégré : {synthese['resultats']} résultat(s).")
            e.save(update_fields=["statut", "message_log"])
            modeladmin.message_user(request, f"{e.nom_fichier} réintégré.",
                                    level=messages.SUCCESS)
        except Exception as exc:
            modeladmin.message_user(request, f"{e.nom_fichier} : {exc}",
                                    level=messages.ERROR)


class ErreurHPRIMInline(admin.TabularInline):
    model = ErreurHPRIM
    extra = 0
    can_delete = False
    readonly_fields = ['gravite', 'type_erreur', 'numero_ligne',
                       'adresse_segment', 'donnee_erronee', 'valeur_erronee',
                       'designation', 'demande']
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(EchangeHPRIM)
class EchangeHPRIMAdmin(admin.ModelAdmin):
    list_display = ['nom_fichier', 'sens', 'contexte', 'statut',
                    'demande', 'date_creation', 'date_traitement']
    list_filter = ['sens', 'contexte', 'statut']
    search_fields = ['nom_fichier', 'demande__numero']
    readonly_fields = ['date_creation', 'date_traitement']
    actions = [action_reintegrer_oru]
    inlines = [ErreurHPRIMInline]


@admin.register(ErreurHPRIM)
class ErreurHPRIMAdmin(admin.ModelAdmin):
    list_display = ['date_creation', 'gravite', 'type_erreur',
                    'nom_fichier_errone', 'demande', 'designation']
    list_filter = ['gravite', 'type_erreur']
    search_fields = ['nom_fichier_errone', 'designation', 'demande__numero']
    readonly_fields = ['echange', 'demande', 'nom_fichier_errone', 'gravite',
                       'type_erreur', 'numero_ligne', 'adresse_segment',
                       'donnee_erronee', 'valeur_erronee', 'designation',
                       'date_creation']
