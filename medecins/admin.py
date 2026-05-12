from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Medecin, Specialite, Departement, Service, Diplome, MedecinDiplome, TypeArticle, CategorieArticle, UniteMesure


# ─── Configuration ────────────────────────────────────────────────────────────

@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'description']
    search_fields = ['nom', 'code']
    ordering = ['nom']


@admin.register(Diplome)
class DiplomeAdmin(admin.ModelAdmin):
    list_display = ['titre', 'description']
    search_fields = ['titre']
    ordering = ['titre']


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'actif']
    list_filter = ['actif']
    search_fields = ['nom', 'code']
    list_editable = ['actif']


@admin.register(TypeArticle)
class TypeArticleAdmin(admin.ModelAdmin):
    list_display = ['nom']
    search_fields = ['nom']


@admin.register(CategorieArticle)
class CategorieArticleAdmin(admin.ModelAdmin):
    list_display = ['nom']
    search_fields = ['nom']


@admin.register(UniteMesure)
class UniteMesureAdmin(admin.ModelAdmin):
    list_display = ['nom']
    search_fields = ['nom']


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = [
        'nom', 'reference_interne', 'code_barres',
        'type_article', 'categorie_article', 'prix_vente', 'cout',
        'quantite_stock', 'quantite_prevue', 'unite', 'actif'
    ]
    list_filter = ['type_article', 'categorie_article', 'actif']
    search_fields = ['nom', 'reference_interne', 'code_barres']
    list_editable = ['actif']
    fieldsets = (
        ('Identification', {
            'fields': ('nom', 'reference_interne', 'code_barres', 'valeur_variante', 'actif'),
        }),
        ('Classification', {
            'fields': ('type_article', 'categorie_article'),
        }),
        ('Tarification', {
            'fields': ('prix_vente', 'cout', 'unite'),
        }),
        ('Stock', {
            'fields': ('quantite_stock', 'quantite_prevue'),
        }),
        ('Description', {
            'fields': ('description',),
            'classes': ('collapse',),
        }),
    )


# ─── Inline Diplômes dans la fiche médecin ────────────────────────────────────

class MedecinDiplomeInline(admin.TabularInline):
    model = MedecinDiplome
    extra = 1
    verbose_name = "Diplôme"
    verbose_name_plural = "Diplômes obtenus"


# ─── Médecin ──────────────────────────────────────────────────────────────────

@admin.register(Medecin)
class MedecinAdmin(admin.ModelAdmin):
    inlines = [MedecinDiplomeInline]

    list_display = [
        'photo_miniature', 'code', 'nom_complet', 'fonction',
        'specialite', 'departements_liste', 'chirurgien_principal', 'actif'
    ]
    list_filter = ['specialite', 'departements', 'chirurgien_principal', 'actif']
    search_fields = ['nom', 'prenoms', 'code']
    readonly_fields = [
        'code', 'date_creation', 'photo_miniature',
        'compteur_rdv', 'compteur_consultations', 'compteur_ordonnances', 'compteur_hospitalisations',
    ]

    fieldsets = (
        ('Statistiques', {
            'fields': ('compteur_rdv', 'compteur_consultations', 'compteur_ordonnances', 'compteur_hospitalisations'),
            'description': 'Mis à jour automatiquement',
        }),
        ('Identification', {
            'fields': ('code', 'user', 'photo', 'photo_miniature', 'nom', 'prenoms', 'fonction', 'actif'),
        }),
        ('Informations médicales', {
            'fields': (
                'specialite', 'departements', 'chirurgien_principal',
                'service_consultation', 'service_suivi',
                'duree_consultation', 'ordre_medecin',
            ),
        }),
        ('Informations personnelles', {
            'fields': ('adresse', 'telephone', 'mobile', 'email', 'tva_numero_fiscal'),
            'classes': ('collapse',),
        }),
        ('Système', {
            'fields': ('date_creation',),
            'classes': ('collapse',),
        }),
    )

    filter_horizontal = ('departements',)

    # ── Méthodes d'affichage ──────────────────────────────────────────────────

    def photo_miniature(self, obj):
        if obj.photo:
            return format_html('<img src="{}" style="width:45px;height:45px;border-radius:50%;object-fit:cover;">', obj.photo.url)
        return mark_safe('<div style="width:45px;height:45px;border-radius:50%;background:#e0e0e0;display:flex;align-items:center;justify-content:center;font-size:18px;">👤</div>')
    photo_miniature.short_description = 'Photo'

    def nom_complet(self, obj):
        return f"{obj.nom} {obj.prenoms}"
    nom_complet.short_description = 'Nom complet'
    nom_complet.admin_order_field = 'nom'

    def departements_liste(self, obj):
        deps = obj.departements.all()
        if not deps:
            return '—'
        badges = ' '.join(
            f'<span style="background:#e8f5e9;padding:2px 8px;border-radius:10px;font-size:11px;margin:1px;display:inline-block">{d.nom}</span>'
            for d in deps
        )
        return mark_safe(badges)
    departements_liste.short_description = 'Départements'

    def compteur_rdv(self, obj):
        if not obj.pk:
            return '—'
        count = obj.rendez_vous.count()
        return format_html(
            '<span style="font-size:16px;font-weight:bold;color:#1976d2">{}</span> <span style="color:#888">rendez-vous</span>',
            count
        )
    compteur_rdv.short_description = 'Rendez-vous'

    def compteur_consultations(self, obj):
        if not obj.pk:
            return '—'
        count = obj.consultations.count()
        return format_html(
            '<span style="font-size:16px;font-weight:bold;color:#388e3c">{}</span> <span style="color:#888">consultations</span>',
            count
        )
    compteur_consultations.short_description = 'Consultations'

    def compteur_ordonnances(self, obj):
        if not obj.pk:
            return '—'
        from consultations.models import Ordonnance
        count = Ordonnance.objects.filter(consultation__medecin=obj).count()
        return format_html(
            '<span style="font-size:16px;font-weight:bold;color:#7b1fa2">{}</span> <span style="color:#888">ordonnances</span>',
            count
        )
    compteur_ordonnances.short_description = 'Ordonnances'

    def compteur_hospitalisations(self, obj):
        if not obj.pk:
            return '—'
        count = obj.hospitalisation_set.count()
        return format_html(
            '<span style="font-size:16px;font-weight:bold;color:#f57c00">{}</span> <span style="color:#888">hospitalisations</span>',
            count
        )
    compteur_hospitalisations.short_description = 'Hospitalisations'
