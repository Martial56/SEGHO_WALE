from django.contrib import admin
from .models import GroupeMedicaments, Maladie, Ordonnance, LigneOrdonnance


@admin.register(Maladie)
class MaladieAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom']
    search_fields = ['nom', 'code']


@admin.register(GroupeMedicaments)
class GroupeMedicamentsAdmin(admin.ModelAdmin):
    list_display = ['nom', 'medecin', 'maladie', 'limite']
    search_fields = ['nom']


class LigneOrdonnanceInline(admin.TabularInline):
    model = LigneOrdonnance
    extra = 1
    fields = ['medicament', 'medicament_libre', 'quantite', 'unite_dosage', 'qte_par_jour', 'jours', 'commentaire']
    readonly_fields = []


@admin.register(Ordonnance)
class OrdonnanceAdmin(admin.ModelAdmin):
    list_display = ['date_ordonnance', 'numero', 'patient', 'medecin', 'statut']
    list_display_links = ['numero', 'patient']
    list_filter = ['statut', 'type_ordonnance', 'avertissement_grossesse', 'date_ordonnance']
    search_fields = ['numero', 'patient__nom', 'patient__prenoms', 'medecin__nom']
    date_hierarchy = 'date_ordonnance'
    ordering = ['-date_ordonnance']
    readonly_fields = ['numero']
    inlines = [LigneOrdonnanceInline]

    fieldsets = (
        (None, {
            'fields': (
                'numero',
                ('patient', 'maladie'),
                ('medecin', 'date_ordonnance'),
                ('groupe_medicaments', 'avertissement_grossesse'),
                ('ancienne_ordonnance', 'type_ordonnance'),
                'statut',
            )
        }),
        ('Informations générales', {
            'classes': ('collapse',),
            'fields': (
                ('rendez_vous', 'police_assurance'),
                ('facture', 'compagnie_assurance'),
                ('cueillettes', 'reclamation'),
                ('livre', 'hospitalisation'),
            )
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
    )


class OrdonnanceInline(admin.TabularInline):
    """Inline utilisé dans ConsultationAdmin."""
    model = Ordonnance
    extra = 0
    fields = ['numero', 'medecin', 'date_ordonnance', 'type_ordonnance', 'statut']
    readonly_fields = ['numero']
    show_change_link = True
