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


class NavItem(models.Model):
    """Un lien ou sous-menu de la barre de navigation interne d'un module (nav.html)."""
    code = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Identifiant technique (ex: patients.pathologie_config)"
    )
    label = models.CharField(max_length=255, verbose_name="Libellé")
    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, null=True, blank=True,
        related_name='nav_items', verbose_name="Module parent"
    )
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Élément de menu"
        verbose_name_plural = "Éléments de menu"
        ordering = ['module__order', 'label']

    def __str__(self):
        return f"{self.module.name if self.module else '—'} → {self.label}"


class GroupNavItemRestriction(models.Model):
    """Masque un élément de menu pour tout un groupe (visible par défaut sinon)."""
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE,
        related_name='hidden_nav_items', verbose_name="Groupe"
    )
    nav_item = models.ForeignKey(
        NavItem, on_delete=models.CASCADE,
        related_name='group_restrictions', verbose_name="Élément de menu"
    )

    class Meta:
        unique_together = ('group', 'nav_item')
        verbose_name = "Menu masqué pour un groupe"
        verbose_name_plural = "Menus masqués par groupe"

    def __str__(self):
        return f"{self.group.name} ✕ {self.nav_item.label}"


class UserNavItemOverride(models.Model):
    """Override individuel : forcer l'affichage ou le masquage d'un menu pour un utilisateur précis."""
    OVERRIDE_TYPE = [
        ('hide', 'Masquer (même si le groupe l’autorise)'),
        ('show', 'Afficher (même si le groupe le masque)'),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='nav_item_overrides', verbose_name="Utilisateur"
    )
    nav_item = models.ForeignKey(
        NavItem, on_delete=models.CASCADE,
        related_name='user_overrides', verbose_name="Élément de menu"
    )
    override_type = models.CharField(
        max_length=10, choices=OVERRIDE_TYPE, default='hide', verbose_name="Type"
    )

    class Meta:
        unique_together = ('user', 'nav_item')
        verbose_name = "Override menu utilisateur"
        verbose_name_plural = "Overrides menus utilisateurs"

    def __str__(self):
        return f"{self.user.username} — {self.get_override_type_display()} — {self.nav_item.label}"


def get_navitems_grouped():
    """
    Retourne les NavItem actifs groupés par module, pour l'affichage en checklist
    dans l'admin (fiche Groupe / Utilisateur). Clé = instance Module ou None
    (menus sans module parent, ex: tableau de bord, soins).
    """
    items = (
        NavItem.objects
        .filter(is_active=True)
        .select_related('module')
        .order_by('module__order', 'module__name', 'label')
    )
    grouped = {}
    for item in items:
        grouped.setdefault(item.module, []).append(item)
    return grouped


def get_hidden_navitem_codes(user):
    """
    Retourne l'ensemble des codes de menu à masquer pour cet utilisateur.
    Un menu est visible par défaut : seuls les codes retournés ici doivent être cachés dans le template.
    """
    if not user.is_authenticated or user.is_superuser:
        return set()

    group_hidden = set(
        GroupNavItemRestriction.objects.filter(group__in=user.groups.all())
        .values_list('nav_item__code', flat=True)
    )
    user_hide = set(
        UserNavItemOverride.objects.filter(user=user, override_type='hide')
        .values_list('nav_item__code', flat=True)
    )
    user_show = set(
        UserNavItemOverride.objects.filter(user=user, override_type='show')
        .values_list('nav_item__code', flat=True)
    )
    return (group_hidden | user_hide) - user_show


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
