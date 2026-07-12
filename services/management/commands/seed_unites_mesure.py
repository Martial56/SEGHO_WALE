from django.core.management.base import BaseCommand
from stock.models import CategorieUniteMesure, UniteMesure


# (categorie_nom, nom, code, type_unite, ratio, precision_arrondi)
DONNEES = [
    ('Unités',            'Unités',     'Unité', 'umrc',  1,         0.01),
    ('Unités',            'Dizaines',   'Diz',   'pgumr', 12,        0.01),

    ('Poids',             'Kilogramme', 'kg',    'umrc',  1,         0.01),
    ('Poids',             'Tonnes',     't',     'pgumr', 1000,      0.01),
    ('Poids',             'Grammes',    'g',     'ppumr', 1000,      0.01),
    ('Poids',             'Livre',      'livre', 'ppumr', 2.20462,   0.01),
    ('Poids',             'Once',       'once',  'ppumr', 32.274,    0.01),

    ('Temps de travail',  'Jours',      'jours', 'umrc',  1,         0.01),
    ('Temps de travail',  'Heure',      'h',     'ppumr', 8,         0.01),

    ('Longueur/distance', 'Mètre',      'm',     'umrc',  1,         0.01),
    ('Longueur/distance', 'Kilomètre',  'km',    'pgumr', 1000,      0.01),
    ('Longueur/distance', 'Centimètre', 'cm',    'ppumr', 100,       0.01),
    ('Longueur/distance', 'Millimètre', 'mm',    'ppumr', 1000,      0.01),
    ('Longueur/distance', 'Pied',       'pied',  'ppumr', 3.28084,   0.01),
    ('Longueur/distance', 'Dans',       'dans',  'ppumr', 39.3701,   0.01),
    ('Longueur/distance', 'Mi',         'mi',    'pgumr', 1609.34,   0.01),
]


class Command(BaseCommand):
    help = "Seed des unités de mesure (Quantité, Masse, Durée, Longueur)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-categories',
            action='store_true',
            help='Afficher les catégories existantes en base et quitter',
        )

    def handle(self, *args, **options):
        if options['list_categories']:
            cats = CategorieUniteMesure.objects.all().order_by('id')
            if not cats.exists():
                self.stdout.write(self.style.WARNING('Aucune catégorie en base.'))
            else:
                self.stdout.write('Catégories existantes :')
                for c in cats:
                    self.stdout.write(f'  id={c.pk}  nom="{c.nom}"')
            return

        # Résolution des catégories par nom (get_or_create pour rester idempotent)
        cat_cache = {}
        cat_names = {row[0] for row in DONNEES}
        for nom in cat_names:
            obj, created = CategorieUniteMesure.objects.get_or_create(nom=nom)
            cat_cache[nom] = obj
            if created:
                self.stdout.write(self.style.WARNING(f'  Catégorie créée : "{nom}" (id={obj.pk})'))
            else:
                self.stdout.write(f'  Catégorie trouvée : "{nom}" (id={obj.pk})')

        # Création / mise à jour des unités
        self.stdout.write('→ Unités de mesure...')
        created_count = updated_count = 0

        for cat_nom, nom, code, type_unite, ratio, precision in DONNEES:
            categorie = cat_cache[cat_nom]
            unite, created = UniteMesure.objects.get_or_create(
                code=code,
                defaults={
                    'nom':              nom,
                    'categorie':        categorie,
                    'type_unite':       type_unite,
                    'ratio':            ratio,
                    'precision_arrondi': precision,
                    'actif':            True,
                },
            )
            if created:
                created_count += 1
            else:
                # Met à jour les champs si les données ont changé
                changed = False
                for champ, valeur in [
                    ('nom',               nom),
                    ('categorie',         categorie),
                    ('type_unite',        type_unite),
                    ('ratio',             ratio),
                    ('precision_arrondi', precision),
                ]:
                    if getattr(unite, champ) != valeur:
                        setattr(unite, champ, valeur)
                        changed = True
                if changed:
                    unite.save()
                    updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'  {created_count} unités créées, {updated_count} mises à jour.'
        ))
        self.stdout.write(self.style.SUCCESS('✓ Seed unités terminé.'))
