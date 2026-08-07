from django.db import models
from django.contrib.auth.models import User
from datetime import time


class PlanningPermanence(models.Model):
    """Planification hebdomadaire des permanences.

    Un planning par (semaine, type) : le personnel et les médecins ont des
    créneaux distincts et indépendants, gérés par des rôles différents
    (RH pour 'personnel', médecin chef pour 'medecins')."""
    TYPE_CHOICES = [
        ('personnel', 'Personnel'),
        ('medecins',  'Médecins'),
    ]
    semaine_du       = models.DateField(verbose_name="Semaine du (lundi)")
    type_permanence  = models.CharField(max_length=20, choices=TYPE_CHOICES, default='personnel')
    heure_debut      = models.TimeField(default=time(8, 0),  verbose_name="Heure d'arrivée")
    heure_fin        = models.TimeField(default=time(15, 0), verbose_name="Heure de départ")
    cree_par         = models.ForeignKey(User, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name='+')
    cree_le          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Permanences {self.get_type_permanence_display()} semaine du {self.semaine_du:%d/%m/%Y}"

    @property
    def heures_verrouillees(self):
        """Dès qu'au moins un employé (personnel ou médecin) est affecté à ce
        planning pour un jour de la semaine, le créneau horaire est
        définitivement figé — y compris pour la RH et les administrateurs.
        Un planning sans aucune affectation reste librement modifiable."""
        if self.pk is None:
            return False
        return self.affectations.exists()

    def save(self, *args, **kwargs):
        if self.pk:
            original = PlanningPermanence.objects.filter(pk=self.pk).values(
                'heure_debut', 'heure_fin'
            ).first()
            if original and self.affectations.exists() and (
                self.heure_debut != original['heure_debut'] or self.heure_fin != original['heure_fin']
            ):
                raise ValueError(
                    "Le créneau horaire de cette permanence est verrouillé "
                    "(un employé y est déjà affecté) et ne peut plus être modifié."
                )
        super().save(*args, **kwargs)

    class Meta:
        unique_together = ['semaine_du', 'type_permanence']
        verbose_name = "Planning permanence"
        verbose_name_plural = "Plannings permanence"
        ordering = ['-semaine_du']


class RegistreVerrou(models.Model):
    """Verrouille définitivement le registre d'une journée — posé par la RH
    quand elle confirme l'enregistrement (y compris si des créneaux restent
    manquants, après avertissement). Plus aucune modification n'est possible
    ce jour-là tant qu'un administrateur ne le déverrouille pas explicitement."""
    date           = models.DateField(unique=True, verbose_name="Jour verrouillé")
    verrouille_par = models.ForeignKey(User, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name='+')
    verrouille_le  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Registre verrouillé — {self.date:%d/%m/%Y}"

    class Meta:
        verbose_name = "Verrou registre"
        verbose_name_plural = "Verrous registre"
        ordering = ['-date']


class AffectationPermanence(models.Model):
    """Affectation d'un employé en permanence pour un jour précis."""
    planning = models.ForeignKey(PlanningPermanence, on_delete=models.CASCADE,
                                  related_name='affectations')
    employe  = models.ForeignKey('employer.Employe', on_delete=models.CASCADE,
                                  related_name='permanences')
    date     = models.DateField(verbose_name="Date de permanence")

    def __str__(self):
        return f"{self.employe} — permanence {self.date:%d/%m/%Y}"

    class Meta:
        unique_together = ['employe', 'date']
        verbose_name = "Affectation permanence"
        verbose_name_plural = "Affectations permanence"
        ordering = ['date', 'employe__nom']


class ConfigurationBiometrique(models.Model):
    """Réglage (singleton) du lecteur d'empreinte digitale du kiosque de
    pointage. Aucun matériel n'existe encore au moment de l'implémentation :
    ce réglage prépare le branchement — la plupart des lecteurs biométriques
    pour kiosque web fournissent un petit service tournant sur la machine du
    kiosque (127.0.0.1) exposant une URL locale que le navigateur peut
    appeler directement, sans jamais transiter par le serveur Django."""
    actif = models.BooleanField(
        default=False,
        verbose_name="Lecteur d'empreinte activé",
        help_text="Tant que désactivé, le kiosque affiche le message générique « lecteur non configuré ».",
    )
    url_agent = models.URLField(
        blank=True,
        verbose_name="URL du service local du lecteur",
        help_text="Fournie par le SDK du lecteur une fois installé sur le poste du kiosque, ex. http://127.0.0.1:8734/scan",
    )
    modifie_par = models.ForeignKey(User, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='+')
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuration biométrique"
        verbose_name_plural = "Configuration biométrique"

    def __str__(self):
        return "Lecteur d'empreinte digitale"

    @classmethod
    def actuelle(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
