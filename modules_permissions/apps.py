from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ModulesPermissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'modules_permissions'
    verbose_name = "Gestion des Modules et des Permissions"

    def ready(self):
        from .francisation import franciser_apres_migration
        post_migrate.connect(
            franciser_apres_migration,
            dispatch_uid='modules_permissions.franciser_permissions',
        )
