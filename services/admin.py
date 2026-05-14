from django.contrib import admin
from .models import (
    UniteMesure, CategorieArticle, FamilleArticle, CompagniePharma,
    ArticleService, LigneFournisseurArticle, ConditionnementArticle,
    VarianteAttributArticle, ReglePrix,
)


@admin.register(UniteMesure)
class UniteMesureAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'categorie')
    list_filter = ('categorie',)
    search_fields = ('nom', 'code')
    ordering = ('nom',)


@admin.register(CategorieArticle)
class CategorieArticleAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'description')
    search_fields = ('code', 'nom')
    ordering = ('code',)


@admin.register(FamilleArticle)
class FamilleArticleAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code')
    search_fields = ('nom', 'code')


@admin.register(CompagniePharma)
class CompagniePharmaAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'telephone', 'email')
    search_fields = ('nom', 'code')


class LigneFournisseurInline(admin.TabularInline):
    model = LigneFournisseurArticle
    extra = 0


class ConditionnementInline(admin.TabularInline):
    model = ConditionnementArticle
    extra = 0


class VarianteInline(admin.TabularInline):
    model = VarianteAttributArticle
    extra = 0


class ReglePrixInline(admin.TabularInline):
    model = ReglePrix
    extra = 0


@admin.register(ArticleService)
class ArticleServiceAdmin(admin.ModelAdmin):
    list_display = ('reference_interne', 'nom', 'categorie', 'type_produit_hospitalier', 'prix_vente', 'actif')
    list_filter = ('actif', 'categorie', 'type_produit_hospitalier', 'type_article')
    search_fields = ('nom', 'reference_interne', 'code_barres')
    ordering = ('nom',)
    inlines = [LigneFournisseurInline, ConditionnementInline, VarianteInline, ReglePrixInline]
    fieldsets = (
        ('En-tête', {'fields': ('nom', 'reference_interne', 'photo', 'favori', 'peut_etre_vendu', 'peut_etre_achete', 'actif')}),
        ('Informations générales', {'fields': ('type_article', 'type_produit_hospitalier', 'categorie', 'famille', 'unite_mesure', 'unite_achat', 'prix_vente', 'cout', 'code_barres')}),
        ('Détails médicament', {'classes': ('collapse',), 'fields': ('forme', 'voie_administration', 'dosage', 'dosage_unite', 'composant_actif', 'compagnie_pharmaceutique')}),
        ('Notes', {'classes': ('collapse',), 'fields': ('notes_internes', 'indications', 'remarques')}),
    )
