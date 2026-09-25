from django.contrib import admin

from .models import GuideCategorie, GuideArticle


class GuideArticleInline(admin.TabularInline):
    model = GuideArticle
    extra = 0
    fields = ['titre', 'icone', 'contenu', 'ordre']


@admin.register(GuideCategorie)
class GuideCategorieAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code', 'groupe', 'groupe_ordre', 'ordre', 'nb_articles')
    list_filter = ('groupe',)
    search_fields = ('nom', 'code')
    ordering = ('groupe_ordre', 'ordre', 'nom')
    inlines = [GuideArticleInline]

    def nb_articles(self, obj):
        return obj.articles.count()
    nb_articles.short_description = "Articles"


@admin.register(GuideArticle)
class GuideArticleAdmin(admin.ModelAdmin):
    list_display = ('titre', 'categorie', 'icone', 'ordre', 'date_modification')
    list_filter = ('categorie',)
    search_fields = ('titre', 'contenu')
