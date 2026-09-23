from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta


class Bureau(models.Model):
    nom = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    def __str__(self): return self.nom
    class Meta:
        ordering = ['ordre']
        verbose_name = "Bureau / Service"
        verbose_name_plural = "Bureaux / Services"


class PlageHoraire(models.Model):
    bureau = models.ForeignKey(Bureau, on_delete=models.CASCADE, related_name='plages')
    code = models.CharField(max_length=20)
    ordre = models.PositiveSmallIntegerField(default=0)

    def __str__(self): return f"{self.bureau.nom} — {self.code}"
    class Meta:
        ordering = ['bureau__ordre', 'ordre']
        verbose_name = "Plage horaire"
        verbose_name_plural = "Plages horaires"


class PermanenceCreneauModele(models.Model):
    """Modèle de créneau de permanence (ex. « 18h-08h »), proposé par défaut
    à la création d'un nouveau planning — reste librement modifiable ensuite,
    semaine par semaine, sur le planning lui-même (PermanenceCreneau)."""
    libelle = models.CharField(max_length=40, verbose_name="Créneau (ex. 18h-08h)")
    ordre   = models.PositiveSmallIntegerField(default=0)

    def __str__(self): return self.libelle
    class Meta:
        ordering = ['ordre', 'pk']
        verbose_name = "Modèle de créneau de permanence"
        verbose_name_plural = "Modèles de créneaux de permanence"


class PlanningHebdomadaire(models.Model):
    semaine_debut = models.DateField(unique=True)
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='plannings_crees')
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)
    publie = models.BooleanField(default=False)
    signataire = models.ForeignKey(
        'MedecinSignataire', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='plannings',
    )
    note = models.TextField(blank=True)

    @property
    def semaine_fin(self):
        return self.semaine_debut + timedelta(days=5)

    def __str__(self):
        return f"Planning semaine du {self.semaine_debut.strftime('%d/%m/%Y')}"

    class Meta:
        ordering = ['-semaine_debut']
        verbose_name = "Planning hebdomadaire"
        verbose_name_plural = "Plannings hebdomadaires"


JOURS = [
    (0, 'Lundi'), (1, 'Mardi'), (2, 'Mercredi'),
    (3, 'Jeudi'), (4, 'Vendredi'), (5, 'Samedi'),
]


class PlanningVu(models.Model):
    """Enregistre qu'un utilisateur a consulté un planning publié."""
    user     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='plannings_vus')
    planning = models.ForeignKey(PlanningHebdomadaire, on_delete=models.CASCADE, related_name='vus_par')
    vu_le    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'planning']
        verbose_name = "Planning vu"


class PlanningModification(models.Model):
    planning     = models.ForeignKey(PlanningHebdomadaire, on_delete=models.CASCADE, related_name='modifications')
    modifie_par  = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='modifications_planning')
    modifie_le   = models.DateTimeField(auto_now_add=True)
    resume       = models.TextField(blank=True)

    class Meta:
        ordering = ['-modifie_le']
        verbose_name = "Modification"


class Affectation(models.Model):
    planning = models.ForeignKey(PlanningHebdomadaire, on_delete=models.CASCADE, related_name='affectations')
    plage = models.ForeignKey(PlageHoraire, on_delete=models.CASCADE, related_name='affectations')
    jour = models.PositiveSmallIntegerField(choices=JOURS)
    personnel = models.CharField(max_length=200, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = ['planning', 'plage', 'jour']
        verbose_name = "Affectation"
        verbose_name_plural = "Affectations"


class PermanenceCreneau(models.Model):
    """Un créneau de permanence, propre à un planning donné — les horaires ne
    sont pas fixés une fois pour toutes (contrairement aux plages des
    bureaux) : ils sont saisis librement à chaque édition du planning."""
    planning = models.ForeignKey(PlanningHebdomadaire, on_delete=models.CASCADE, related_name='permanence_creneaux')
    libelle  = models.CharField(max_length=40, verbose_name="Créneau (ex. 18h-08h)")
    ordre    = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['ordre', 'pk']
        verbose_name = "Créneau de permanence"
        verbose_name_plural = "Créneaux de permanence"

    def __str__(self):
        return self.libelle


class LignePermanence(models.Model):
    creneau   = models.ForeignKey(PermanenceCreneau, on_delete=models.CASCADE, related_name='affectations')
    jour      = models.PositiveSmallIntegerField(choices=JOURS)
    personnel = models.CharField(max_length=200, blank=True)
    note      = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = ['creneau', 'jour']
        verbose_name = "Ligne de permanence"
        verbose_name_plural = "Lignes de permanence"

    def __str__(self):
        return f"Permanence {JOURS[self.jour][1]} — {self.creneau}"


FONCTION_SIGNATAIRE_CHOICES = [
    ('directeur_medical', 'Directeur Médical'),
    ('directrice_medicale', 'Directrice Médicale'),
    ('directeur_medical_adjoint', 'Directeur Médical Adjoint'),
    ('directrice_medicale_adjointe', 'Directrice Médicale Adjointe'),
]


class MedecinSignataire(models.Model):
    nom = models.CharField(max_length=200)
    fonction = models.CharField(
        max_length=40, choices=FONCTION_SIGNATAIRE_CHOICES, blank=True, default='',
        verbose_name="Fonction",
        help_text="Affichée au-dessus du nom sur les plannings imprimés/publiés signés par ce médecin.",
    )
    actif = models.BooleanField(default=True)
    ordre = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return self.nom

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = "Médecin signataire"
        verbose_name_plural = "Médecins signataires"


class PlanningConfig(models.Model):
    medecin_defaut = models.ForeignKey(
        MedecinSignataire, on_delete=models.SET_NULL, null=True, blank=True,
    )

    class Meta:
        verbose_name = "Configuration planning"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
