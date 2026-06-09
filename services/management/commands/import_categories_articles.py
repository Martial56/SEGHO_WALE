"""
Commande d'import pour CategorieArticle depuis un fichier JSON.

Usage :
    python manage.py import_categories_articles chemin/vers/fichier.json
    python manage.py import_categories_articles chemin/vers/fichier.json --update

Format JSON attendu (champs exportés depuis l'autre système) :
    [{"id": 1, "code": "AE", "nom": "AE", "description": "...",
      "parent_id": null, "methode_cout": "prix_standard", ...}, ...]
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from services.models import CategorieArticle


class Command(BaseCommand):
    help = "Importe les catégories d'articles depuis un fichier JSON"

    def add_arguments(self, parser):
        parser.add_argument('fichier', type=str, help='Chemin vers le fichier JSON')
        parser.add_argument(
            '--update',
            action='store_true',
            help='Mettre à jour les catégories existantes (par défaut : skip si le code existe)',
        )

    def handle(self, *args, **options):
        chemin = Path(options['fichier'])
        if not chemin.exists():
            raise CommandError(f'Fichier introuvable : {chemin}')

        with open(chemin, encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise CommandError(f'JSON invalide : {e}')

        # ── Passe 1 : créer/mettre à jour toutes les catégories SANS parent ────
        # On garde un mapping json_id → code pour résoudre les parents ensuite
        id_to_code = {item['id']: item['code'] for item in data}
        created = updated = skipped = 0

        self.stdout.write(f'→ Import de {len(data)} catégorie(s)…')

        for item in data:
            defaults = {
                'nom':                        item.get('nom', item['code']),
                'description':                item.get('description', ''),
                'methode_cout':               item.get('methode_cout', 'prix_standard'),
                'valorisation_inventaire':    item.get('valorisation_inventaire', 'manuelle'),
                'reservation_conditionnement':item.get('reservation_conditionnement', 'partiels'),
                'bloquer_serie_lot':          bool(item.get('bloquer_serie_lot', False)),
                'routes':                     item.get('routes', ''),
                'strategie_enlevement':       item.get('strategie_enlevement', ''),
                'sequence_code_barres':       item.get('sequence_code_barres', ''),
                'compte_revenus':             item.get('compte_revenus', ''),
                'compte_charges':             item.get('compte_charges', ''),
                'parent':                     None,  # résolu en passe 2
            }

            obj, was_created = CategorieArticle.objects.get_or_create(
                code=item['code'],
                defaults=defaults,
            )

            if was_created:
                created += 1
            elif options['update']:
                for champ, valeur in defaults.items():
                    if champ == 'parent':
                        continue  # géré en passe 2
                    setattr(obj, champ, valeur)
                obj.save()
                updated += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'  Passe 1 — {created} créées, {updated} mises à jour, {skipped} ignorées'
        ))

        # ── Passe 2 : résoudre les relations parent ──────────────────────────
        parent_liens = [
            (item['code'], id_to_code[item['parent_id']])
            for item in data
            if item.get('parent_id') is not None
        ]

        liens_ok = liens_ko = 0
        for code_enfant, code_parent in parent_liens:
            try:
                enfant = CategorieArticle.objects.get(code=code_enfant)
                parent = CategorieArticle.objects.get(code=code_parent)
                if enfant.parent_id != parent.pk:
                    enfant.parent = parent
                    enfant.save()
                liens_ok += 1
            except CategorieArticle.DoesNotExist as e:
                self.stdout.write(self.style.WARNING(f'  Lien parent ignoré ({code_enfant} → {code_parent}) : {e}'))
                liens_ko += 1

        if parent_liens:
            self.stdout.write(self.style.SUCCESS(
                f'  Passe 2 — {liens_ok} lien(s) parent résolu(s), {liens_ko} ignoré(s)'
            ))

        self.stdout.write(self.style.SUCCESS('✓ Import catégories terminé.'))
