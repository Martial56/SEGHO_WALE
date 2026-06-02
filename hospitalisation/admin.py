from django.contrib import admin
from .models import Chambre, Hospitalisation, FicheVisite, ProtocoleHospitalisation


@admin.register(Chambre)
class ChambreAdmin(admin.ModelAdmin):
    list_display = ['numero', 'type_chambre', 'service', 'capacite', 'prix_jour', 'disponible']
    list_filter = ['type_chambre', 'service', 'disponible']


class FicheVisiteInline(admin.TabularInline):
    model = FicheVisite
    extra = 0
    readonly_fields = ['date_visite']


@admin.register(Hospitalisation)
class HospitalisationAdmin(admin.ModelAdmin):
    list_display = ['numero', 'patient', 'medecin_traitant', 'chambre', 'date_admission', 'statut', 'duree_sejour']
    search_fields = ['numero', 'patient__nom', 'patient__prenoms']
    list_filter = ['statut', 'medecin_traitant']
    readonly_fields = ['numero', 'date_admission']
    inlines = [FicheVisiteInline]
