from django.contrib import admin
from .models import Employe, Poste, Conge, Presence


@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code', 'service']


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenoms', 'poste', 'telephone', 'date_embauche', 'statut']
    search_fields = ['matricule', 'nom', 'prenoms']
    list_filter = ['statut', 'poste']


@admin.register(Conge)
class CongeAdmin(admin.ModelAdmin):
    list_display = ['employe', 'type_conge', 'date_debut', 'date_fin', 'duree', 'statut']
    list_filter = ['statut', 'type_conge']


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ['employe', 'date', 'heure_arrivee', 'heure_depart', 'present']
    list_filter = ['present', 'date']
    date_hierarchy = 'date'
