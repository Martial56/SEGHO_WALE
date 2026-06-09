from django.apps import AppConfig


class HospitalisationConfig(AppConfig):
    name = 'hospitalisation'

    def ready(self):
        from .signals import register
        register()
