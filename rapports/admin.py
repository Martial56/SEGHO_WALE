from django.contrib import admin

from .models import HistoriqueRapport


@admin.register(HistoriqueRapport)
class HistoriqueRapportAdmin(admin.ModelAdmin):
    list_display = ('nom', 'utilisateur', 'periode_debut', 'periode_fin', 'format_fichier', 'nb_lignes', 'date_generation')
    list_filter = ('slug', 'format_fichier', 'date_generation')
    search_fields = ('nom', 'utilisateur__username')
    date_hierarchy = 'date_generation'
    readonly_fields = [f.name for f in HistoriqueRapport._meta.fields]

    def has_add_permission(self, request):
        return False
