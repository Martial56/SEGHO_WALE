from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class LogActivite(models.Model):
    TYPE_CHOICES = [
        ('note', 'Note'),
        ('statut', 'Changement de statut'),
        ('modif', 'Modification'),
        ('system', 'Système'),
        ('suppression', 'Suppression'),
        ('connexion', 'Connexion'),
        ('consultation', 'Consultation'),
    ]
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    objet        = GenericForeignKey('content_type', 'object_id')
    type         = models.CharField(max_length=12, choices=TYPE_CHOICES, default='note')
    message      = models.TextField()
    user         = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    date         = models.DateTimeField(auto_now_add=True)
    ip_address   = models.GenericIPAddressField(null=True, blank=True, verbose_name="Adresse IP")
    duree_secondes = models.PositiveIntegerField(null=True, blank=True, verbose_name="Durée (secondes)")
    module       = models.CharField(
        max_length=50, blank=True, verbose_name="Module",
        help_text="Nom de l'app Django concernée — indépendant de l'objet lié, "
                   "nécessaire pour les événements sans objet précis (consultation d'une page, connexion).",
    )

    class Meta:
        verbose_name = "Log d'activité"
        verbose_name_plural = "Logs d'activité"
        ordering = ['-date']
        indexes = [models.Index(fields=['content_type', 'object_id'], name='core_logact_content_d92fc0_idx')]

    def __str__(self):
        return f"[{self.type}] {self.message[:50]}"

    @property
    def duree_affichee(self):
        if self.duree_secondes is None:
            return None
        heures, reste = divmod(self.duree_secondes, 3600)
        minutes, secondes = divmod(reste, 60)
        if heures:
            return f"{heures} h {minutes:02d} min"
        if minutes:
            return f"{minutes} min {secondes:02d} s"
        return f"{secondes} s"


class UserProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    photo        = models.ImageField(upload_to='profiles/', blank=True, null=True)
    accent_color = models.CharField(max_length=7, blank=True, null=True,
                                     help_text="Couleur d'accent personnalisée (hex, ex: #3e6f3e). Vide = couleur par défaut du logo.")
    luminosite = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(70), MaxValueValidator(100)],
        help_text="Luminosité de l'interface, en pourcentage (70 à 100). "
                  "100 = aucun assombrissement, rendu d'origine. Les validateurs "
                  "sont le seul rempart contre une valeur saisie ici qui rendrait "
                  "l'interface illisible pour l'utilisateur, sans issue de son côté.",
    )
    session_timeout_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Délai d'inactivité avant déconnexion automatique, en minutes. 0 = désactivé.",
    )
    centres = models.ManyToManyField(
        'centres.Centre', blank=True, related_name='profils',
        help_text="Centres auxquels cet utilisateur a accès. Le personnel fixe n'en a qu'un ; "
                  "un médecin intervenant dans plusieurs centres peut en avoir plusieurs.",
    )
    centre_actif = models.ForeignKey(
        'centres.Centre', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='profils_actifs', help_text="Centre actuellement sélectionné par l'utilisateur.",
    )

    def peut_acceder(self, centre):
        if self.user.is_superuser:
            return True
        return self.centres.filter(pk=centre.pk).exists()

    def __str__(self):
        return f"Profil de {self.user.username}"


@receiver(post_save, sender=User)
def create_or_save_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)
