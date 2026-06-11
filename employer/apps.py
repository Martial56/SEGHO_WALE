from django.apps import AppConfig


class EmployerConfig(AppConfig):
    name = 'employer'
    verbose_name = 'Employés'

    def ready(self):
        import employer.signals  # noqa: F401
