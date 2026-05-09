from django.db import models
from django.contrib.auth.models import Group, User


class Module(models.Model):
    code = models.SlugField(
        max_length=50,
        unique=True,
        help_text="Identifiant technique du module (ex: patients, pharmacie…)"
    )
    name = models.CharField(max_length=255, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    icon = models.CharField(max_length=10, default='📦', help_text="Emoji du module")
    url_name = models.CharField(
        max_length=100, blank=True,
        help_text="Nom de l'URL Django (ex: patients_list). Vide = pas de lien."
    )
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Ordre")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.icon} {self.name}"


class GroupModule(models.Model):
    """Lie un groupe Django aux modules qu'il est autorisé à voir."""
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE,
        related_name='group_modules', verbose_name="Groupe"
    )
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE,
        related_name='group_modules', verbose_name="Module"
    )

    class Meta:
        unique_together = ('group', 'module')
        verbose_name = "Module par groupe"
        verbose_name_plural = "Modules par groupe"

    def __str__(self):
        return f"{self.group.name} → {self.module.name}"


class UserModuleOverride(models.Model):
    """Override individuel : accorder ou retirer un module à un utilisateur spécifique."""
    OVERRIDE_TYPE = [
        ('grant',  'Accorder (en plus du groupe)'),
        ('revoke', 'Retirer (même si dans le groupe)'),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='module_overrides', verbose_name="Utilisateur"
    )
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE,
        related_name='user_overrides', verbose_name="Module"
    )
    override_type = models.CharField(
        max_length=10, choices=OVERRIDE_TYPE, default='grant', verbose_name="Type"
    )

    class Meta:
        unique_together = ('user', 'module')
        verbose_name = "Override module utilisateur"
        verbose_name_plural = "Overrides modules utilisateurs"

    def __str__(self):
        return f"{self.user.username} — {self.override_type} — {self.module.name}"


def get_user_modules(user):
    """
    Retourne le queryset des modules accessibles pour un utilisateur.
    - Superuser : tous les modules actifs.
    - Sinon : union des modules de ses groupes + grants individuels - revokes individuels.
    """
    if user.is_superuser:
        return Module.objects.filter(is_active=True)

    group_module_ids = set(
        GroupModule.objects.filter(group__in=user.groups.all())
        .values_list('module_id', flat=True)
    )
    grants = set(
        UserModuleOverride.objects.filter(user=user, override_type='grant')
        .values_list('module_id', flat=True)
    )
    revokes = set(
        UserModuleOverride.objects.filter(user=user, override_type='revoke')
        .values_list('module_id', flat=True)
    )
    allowed_ids = (group_module_ids | grants) - revokes
    return Module.objects.filter(id__in=allowed_ids, is_active=True).order_by('order', 'name')
