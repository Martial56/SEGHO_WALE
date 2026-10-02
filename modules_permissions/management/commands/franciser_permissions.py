from django.core.management.base import BaseCommand

from modules_permissions.francisation import franciser_permissions


class Command(BaseCommand):
    help = ("Renomme en français les permissions qui portent encore le nom "
            "anglais de Django (« Can add … »). Fait aussi après chaque migrate.")

    def handle(self, *args, **options):
        nombre = franciser_permissions()
        self.stdout.write(self.style.SUCCESS(f"{nombre} permission(s) francisée(s)."))
