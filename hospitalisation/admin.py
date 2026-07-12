from django.contrib import admin
from .models import Batiment, Chambre, Hospitalisation, FicheVisite


@admin.register(Batiment)
class BatimentAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'description']
    search_fields = ['nom']


@admin.register(Chambre)
class ChambreAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'salle_no', 'type_chambre', 'nombre_lits', 'statut']
    list_filter   = ['type_chambre', 'statut', 'prive', 'genre']
    search_fields = ['nom', 'salle_no']
    readonly_fields = ['salle_no']

    fieldsets = (
        (None, {
            'fields': (
                ('nom', 'salle_no'),
                ('type_chambre', 'nombre_lits', 'statut'),
                ('prive', 'genre'),
            )
        }),
        ('Établissement', {
            'fields': (
                ('acces_internet',     'lit_visiteur'),
                ('climatisation',      'four_micro_onde'),
                ('salle_bains_privee', 'danger_biologique'),
                ('television',         'refrigerateur'),
                ('telephone_chambre',),
            )
        }),
        ('Détails', {
            'fields': ('description',),
            'classes': ('collapse',),
        }),
    )


class FicheVisiteInline(admin.TabularInline):
    model = FicheVisite
    extra = 0
    readonly_fields = ['date_visite']


@admin.register(Hospitalisation)
class HospitalisationAdmin(admin.ModelAdmin):
    list_display    = ['numero', 'patient', 'medecin_traitant', 'chambre', 'date_admission', 'statut', 'duree_observation']
    search_fields   = ['numero', 'patient__nom', 'patient__prenoms']
    list_filter     = ['statut', 'medecin_traitant']
    readonly_fields = ['numero', 'date_admission']
    inlines         = [FicheVisiteInline]
