from django.contrib import admin
from .models import (
    Specialite, Diplome, Departement, Etiquette,
    DocteurReferent, ContactAdresse,
    Fonction, Grade, TypeContrat,
    Employe, DiplomePersonnel, DocumentEmploye, InfoSupplementaire,
    HistoriqueEmploye, AlerteContrat, AlerteDocument,
    Conge, HistoriqueConge, SoldeConge, NotificationConge,
    Presence, JourFerie,
)


# ── Données de référence ──────────────────────────────────────────────────────

@admin.register(Specialite)
class SpecialiteAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(Diplome)
class DiplomeAdmin(admin.ModelAdmin):
    list_display  = ['titre']
    search_fields = ['titre']


@admin.register(Departement)
class DepartementAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'code', 'actif']
    search_fields = ['nom', 'code']
    list_filter   = ['actif']


@admin.register(Etiquette)
class EtiquetteAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'couleur']
    search_fields = ['nom']


# ── Grilles RH ────────────────────────────────────────────────────────────────

@admin.register(Fonction)
class FonctionAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display  = ['nom', 'code']
    search_fields = ['nom', 'code']


@admin.register(TypeContrat)
class TypeContratAdmin(admin.ModelAdmin):
    list_display = ['nom', 'droit_au_conge']


# ── Employé ───────────────────────────────────────────────────────────────────

class DiplomePersonnelInline(admin.TabularInline):
    model  = DiplomePersonnel
    extra  = 0
    fields = ['titre', 'etablissement', 'annee']


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display  = ['matricule', 'nom', 'prenoms', 'est_medecin',
                     'specialite', 'fonction', 'statut']
    search_fields = ['matricule', 'nom', 'prenoms', 'email', 'telephone', 'ordre_medecin']
    list_filter   = ['statut', 'est_medecin', 'specialite', 'services', 'fonction', 'grade', 'type_contrat']
    readonly_fields = ['matricule', 'cree_le', 'modifie_le']
    inlines       = [DiplomePersonnelInline]
    fieldsets = [
        ('Identité', {'fields': [
            'titre', 'nom', 'prenoms', 'sexe', 'date_naissance', 'lieu_naissance',
            'nationalite', 'situation_matrimoniale', 'nombre_enfants', 'photo', 'signature',
        ]}),
        ('Contact', {'fields': ['telephone', 'telephone2', 'email', 'adresse']}),
        ('Profil médical', {'fields': [
            'est_medecin', 'est_referent', 'specialite',
            'ordre_medecin', 'duree_consultation', 'chirurgien_principal', 'taux_honoraire',
            'service_consultation', 'service_suivi',
        ], 'classes': ['collapse']}),
        ('RH — Affectation', {'fields': [
            'matricule', 'services', 'fonction', 'grade', 'type_contrat',
            'date_embauche', 'date_fin_contrat', 'salaire_base',
            'etablissement', 'langue', 'statut',
        ]}),
        ('Notes', {'fields': ['notes', 'notes_internes'], 'classes': ['collapse']}),
        ('Compte', {'fields': ['user', 'cree_le', 'modifie_le'], 'classes': ['collapse']}),
    ]


# ── Docteur Référent ──────────────────────────────────────────────────────────

class ContactAdresseInline(admin.TabularInline):
    model  = ContactAdresse
    extra  = 0
    fields = ['type_adresse', 'nom', 'telephone', 'email', 'adresse']


@admin.register(DocteurReferent)
class DocteurReferentAdmin(admin.ModelAdmin):
    list_display  = ['code', 'nom', 'prenoms', 'specialite', 'etablissement', 'telephone', 'actif']
    search_fields = ['nom', 'prenoms', 'code', 'etablissement']
    list_filter   = ['specialite', 'actif', 'est_referent']
    inlines       = [ContactAdresseInline]


# ── Documents ─────────────────────────────────────────────────────────────────

@admin.register(DocumentEmploye)
class DocumentEmployeAdmin(admin.ModelAdmin):
    list_display  = ['employe', 'type_document', 'titre', 'date_ajout']
    list_filter   = ['type_document']
    search_fields = ['employe__nom', 'titre']


# ── Congés ────────────────────────────────────────────────────────────────────

@admin.register(Conge)
class CongeAdmin(admin.ModelAdmin):
    list_display = ['employe', 'type_conge', 'date_debut', 'date_fin', 'statut']
    list_filter  = ['statut', 'type_conge']


@admin.register(SoldeConge)
class SoldeCongeAdmin(admin.ModelAdmin):
    list_display = ['employe', 'annee', 'quota', 'jours_pris', 'solde']
    list_filter  = ['annee']


# ── Présence & Jours fériés ───────────────────────────────────────────────────

@admin.register(Presence)
class PresenceAdmin(admin.ModelAdmin):
    list_display  = ['employe', 'date', 'heure_arrivee_matin', 'heure_depart_soir', 'present']
    list_filter   = ['present', 'date']
    date_hierarchy = 'date'


@admin.register(JourFerie)
class JourFerieAdmin(admin.ModelAdmin):
    list_display = ['date', 'description']
    ordering     = ['date']
