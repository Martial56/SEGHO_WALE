from django.db import models


class TypeConge(models.Model):
    NATURE_CHOICES = [
        ('conge', 'Congé'),
        ('permission', 'Permission'),
        ('absence', 'Absence'),
    ]
    code = models.SlugField(max_length=20, unique=True, verbose_name="Code")
    nom = models.CharField(max_length=100, verbose_name="Nom")
    nature = models.CharField(
        max_length=12, choices=NATURE_CHOICES, default='conge', verbose_name="Nature",
        help_text="Détermine le libellé affiché sur le bon et l'attestation (Congé, Permission ou Absence).",
    )
    couleur = models.CharField(max_length=20, default='blue', verbose_name="Couleur (calendrier)")
    deductible = models.BooleanField(
        default=True,
        verbose_name="Déductible du solde annuel",
        help_text="Décocher pour les congés qui ne consomment pas le quota annuel (ex. congé sans solde)."
    )
    duree_forfaitaire = models.PositiveSmallIntegerField(
        null=True, blank=True,
        verbose_name="Durée forfaitaire (jours)",
        help_text="Nombre de jours fixé par le Code du travail pour ce type (ex. mariage, décès). Laisser vide si la durée est libre (congé annuel, maladie...)."
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    ordre = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre d'affichage")

    def __str__(self):
        return self.nom

    class Meta:
        db_table = 'conges_typeconge'
        ordering = ['ordre', 'nom']
        verbose_name = "Type de demande"
        verbose_name_plural = "Types de demande"


def type_conge_choices():
    """Choix dynamiques pour Conge.type_conge (voir employer/models.py) — inclut les types inactifs
    pour que get_type_conge_display() reste correct sur les anciens congés déjà enregistrés.

    Django évalue les choices callables pendant les system checks, qui tournent AVANT toute
    migration — sur une base neuve, la table conges_typeconge n'existe pas encore à ce moment-là.
    On retombe alors sur une liste vide (sans effet, elle sera repeuplée dès que `migrate` aura
    créé la table et exécuté la migration de seed)."""
    from django.db.utils import Error as DBError
    try:
        return list(TypeConge.objects.order_by('ordre', 'nom').values_list('code', 'nom'))
    except DBError:
        return []
