from django.contrib import admin
from .models import PlanningPermanence, AffectationPermanence


@admin.register(PlanningPermanence)
class PlanningPermanenceAdmin(admin.ModelAdmin):
    list_display = ('semaine_du', 'heure_debut', 'heure_fin', 'cree_par', 'cree_le')
    ordering = ('-semaine_du',)
    date_hierarchy = 'semaine_du'


@admin.register(AffectationPermanence)
class AffectationPermanenceAdmin(admin.ModelAdmin):
    list_display = ('employe', 'date', 'planning')
    list_filter = ('date',)
    ordering = ('date', 'employe__nom')
