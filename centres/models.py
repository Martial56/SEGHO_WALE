from django.db import models


class Centre(models.Model):
    """Un centre de santé (établissement) desservi par ce déploiement."""
    nom = models.CharField(max_length=150)
    code = models.CharField(max_length=20, unique=True)
    actif = models.BooleanField(default=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Centre"
        ordering = ['nom']


class CentreManager(models.Manager):
    """Ne renvoie que les enregistrements du centre actif (thread-local).

    Un superuser sans centre actif voit tout, comme dans l'admin
    (voir centres.admin.ModeleCentreAdmin.get_queryset) — évite qu'un
    superuser sans centre assigné ne voie des pages vides sur le site."""

    def get_queryset(self):
        from core.middleware import get_current_centre, get_current_user
        centre = get_current_centre()
        qs = super().get_queryset()
        if centre is None:
            user = get_current_user()
            if user is not None and getattr(user, 'is_superuser', False):
                return qs
        return qs.filter(centre=centre)


class ModeleCentre(models.Model):
    """Modèle abstrait pour toute donnée propre à un centre.

    `objects` filtre automatiquement sur le centre actif (voir
    core.middleware.get_current_centre) ; `all_objects` reste non filtré et
    doit être réservé à l'admin (superuser), aux migrations de données et aux
    scripts hors requête. `base_manager_name` pointe vers `all_objects` pour
    que les mécanismes internes de Django (suppression en cascade, etc.) ne
    soient jamais bridés par le filtre de centre.
    """
    centre = models.ForeignKey(
        Centre, on_delete=models.PROTECT, null=True, blank=True, editable=False,
        related_name='%(app_label)s_%(class)s_set',
    )

    objects = CentreManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = 'all_objects'

    def save(self, *args, **kwargs):
        if self.centre_id is None:
            from core.middleware import get_current_centre
            centre = get_current_centre()
            if centre is not None:
                self.centre = centre
        super().save(*args, **kwargs)
