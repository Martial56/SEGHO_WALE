from django.apps import AppConfig


class LaboratoireConfig(AppConfig):
    name = 'laboratoire'

    def ready(self):
        # Enregistre les signaux (envoi HPRIM automatique au statut « demandé »)
        from . import signals  # noqa: F401
