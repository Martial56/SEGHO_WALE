from django.contrib import admin
from .models import TypeExamen, AnalyseLaboratoire, ResultatAnalyse, ExamenImagerie


@admin.register(TypeExamen)
class TypeExamenAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'categorie', 'prix', 'delai_resultat_heures']


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
