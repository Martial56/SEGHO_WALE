from django.apps import AppConfig


class PharmacieConfig(AppConfig):
    name = 'pharmacie'

    def ready(self):
        from . import signals  # noqa: F401
