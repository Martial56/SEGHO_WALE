from django.core.management.base import BaseCommand
from stock.models import UniteMesure


# (nom, code)
DONNEES = [
    ('Unités',     'Unité'),
    ('Dizaines',   'Diz'),

    ('Kilogramme', 'kg'),
    ('Tonnes',     't'),
    ('Grammes',    'g'),
    ('Livre',      'livre'),
    ('Once',       'once'),

    ('Jours',      'jours'),
    ('Heure',      'h'),

    ('Mètre',      'm'),
    ('Kilomètre',  'km'),
    ('Centimètre', 'cm'),
    ('Millimètre', 'mm'),
    ('Pied',       'pied'),
    ('Dans',       'dans'),
    ('Mi',         'mi'),
]


class Command(BaseCommand):
    help = "Seed des unités de mesure de base"

    def handle(self, *args, **options):
        self.stdout.write('→ Unités de mesure...')
        created_count = updated_count = 0

        for nom, code in DONNEES:
            unite, created = UniteMesure.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'actif': True},
            )
            if created:
                created_count += 1
            elif unite.nom != nom:
                unite.nom = nom
                unite.save(update_fields=['nom'])
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {created_count} unités créées, {updated_count} mises à jour.'
        ))
        self.stdout.write(self.style.SUCCESS('✓ Seed unités terminé.'))
