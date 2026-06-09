from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
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
    ]
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    objet        = GenericForeignKey('content_type', 'object_id')
    type         = models.CharField(max_length=10, choices=TYPE_CHOICES, default='note')
    message      = models.TextField()
    user         = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    date         = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log d'activité"
        verbose_name_plural = "Logs d'activité"
        ordering = ['-date']
        indexes = [models.Index(fields=['content_type', 'object_id'], name='core_logact_content_d92fc0_idx')]

    def __str__(self):
        return f"[{self.type}] {self.message[:50]}"


class UserProfile(models.Model):
    user  = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    photo = models.ImageField(upload_to='profiles/', blank=True, null=True)

    def __str__(self):
        return f"Profil de {self.user.username}"


@receiver(post_save, sender=User)
def create_or_save_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)
