from django.contrib import admin
from .models import (Employe, Fonction, Grade, TypeContrat,
                     DocumentEmploye, InfoSupplementaire, Conge, Presence, JourFerie)


@admin.register(Fonction)
class FonctionAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(TypeContrat)
class TypeContratAdmin(admin.ModelAdmin):
    list_display = ['nom']


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display = ['matricule', 'nom', 'prenoms', 'service', 'fonction', 'grade',
                    'type_contrat', 'date_embauche', 'statut']
    search_fields = ['matricule', 'nom', 'prenoms', 'email', 'telephone']
    list_filter = ['statut', 'service', 'fonction', 'grade', 'type_contrat', 'sexe']
    readonly_fields = ['matricule', 'cree_le', 'modifie_le']


@admin.register(DocumentEmploye)
class DocumentEmployeAdmin(admin.ModelAdmin):
    list_display = ['employe', 'type_document', 'titre', 'date_ajout']
    list_filter = ['type_document']
    search_fields = ['employe__nom', 'titre']


@admin.register(InfoSupplementaire)
class InfoSupplementaireAdmin(admin.ModelAdmin):
    list_display = ['employe', 'cle', 'valeur']
    search_fields = ['employe__nom', 'cle']


@admin.register(Conge)
class CongeAdmin(admin.ModelAdmin):
    list_display = ['employe', 'type_conge', 'date_debut', 'date_fin', 'duree', 'statut']
    list_filter = ['statut', 'type_conge']


@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display = ['employe', 'date', 'heure_arrivee_matin', 'heure_depart_soir', 'present']
    list_filter = ['present', 'date']
    date_hierarchy = 'date'


@admin.register(JourFerie)
class JourFerieAdmin(admin.ModelAdmin):
    list_display = ['date', 'description']
    ordering = ['date']
