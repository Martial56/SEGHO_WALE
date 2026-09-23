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


class ReglesConge(models.Model):
    """Réglages du calcul du quota annuel (Art. 25.10 CODI) — singleton, comme
    PlanningConfig. Le taux de base légal est 2,2 jours ouvrés par mois."""
    jours_par_mois = models.DecimalField(
        max_digits=4, decimal_places=2, default=2.2,
        verbose_name="Jours acquis par mois travaillé",
        help_text="Base légale ivoirienne : 2,2 jours ouvrés par mois (soit 26,4 jours/an).",
    )

    class Meta:
        verbose_name = "Règles de calcul du quota"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PalierAnciennete(models.Model):
    """Un palier de bonus d'ancienneté : à partir de `annees_min` ans
    d'ancienneté, `jours_bonus` jours s'ajoutent au quota annuel de base."""
    annees_min = models.PositiveSmallIntegerField(
        unique=True, verbose_name="Ancienneté minimale (années)",
    )
    jours_bonus = models.DecimalField(
        max_digits=4, decimal_places=2, verbose_name="Jours bonus",
    )

    def __str__(self):
        return f"{self.annees_min} ans → +{self.jours_bonus}j"

    class Meta:
        ordering = ['annees_min']
        verbose_name = "Palier d'ancienneté"
        verbose_name_plural = "Paliers d'ancienneté"


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
