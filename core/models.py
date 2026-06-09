from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey


class LogActivite(models.Model):
    TYPE = [
        ('note',   'Note'),
        ('statut', 'Changement de statut'),
        ('modif',  'Modification'),
        ('system', 'Système'),
    ]

    # Lien générique vers n'importe quel modèle
    content_type   = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id      = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    user    = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    type    = models.CharField(max_length=10, choices=TYPE, default='note')
    message = models.TextField()
    date    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Log d'activité"
        verbose_name_plural = "Logs d'activité"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"[{self.get_type_display()}] {self.message[:60]}"
