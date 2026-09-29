"""Le catalogue des types de visite CPN.

Il n'est pas saisi à la main : la migration `0002_seed_types_visite` le pose à
l'installation de la base, comme les départements et les diagnostics retenus.
Ce qui est vérifié ici, c'est le contrat entre ce catalogue et le rapport de
maternité — qui cite les codes un par un.
"""
from django.test import TestCase

from .models import TypeVisite


class TestCatalogueDesTypesDeVisite(TestCase):
    """Une base neuve arrive déjà garnie.

    La base de test est créée en rejouant toutes les migrations : ce que ces
    tests constatent, c'est exactement ce que trouvera une installation neuve.
    """

    def test_les_sept_types_sont_poses_a_l_installation(self):
        self.assertEqual(TypeVisite.objects.count(), 7)

    def test_tous_sont_actifs(self):
        """Un type inactif ne s'offre pas dans la fiche de rendez-vous."""
        self.assertEqual(TypeVisite.objects.filter(actif=True).count(), 7)

    def test_les_codes_sont_ceux_que_le_rapport_de_maternite_reclame(self):
        """Le vrai contrat.

        `rapports/maternite.py` ventile les consultations prénatales en citant
        ces codes. Un code renommé ici, et la ligne correspondante du rapport
        tombe à zéro sans un mot — c'est ce silence que ce test casse.
        """
        import re
        from pathlib import Path

        from django.conf import settings

        source = Path(settings.BASE_DIR, 'rapports', 'maternite.py').read_text(encoding='utf-8')
        reclames = set(re.findall(r"CODE_CPN\w* = '([^']+)'", source))
        self.assertEqual(len(reclames), 7, f'Codes lus dans le rapport : {reclames}')
        self.assertEqual(reclames, set(TypeVisite.objects.values_list('code', flat=True)))

    def test_chaque_code_porte_un_nom(self):
        for type_visite in TypeVisite.objects.all():
            with self.subTest(code=type_visite.code):
                self.assertTrue(type_visite.nom.strip())

    def test_la_migration_ne_repasse_pas_sur_un_nom_retouche(self):
        """Elle pose ce qui manque, elle n'écrase rien.

        Un nom changé depuis l'écran de configuration doit survivre à la
        prochaine migration : c'est `get_or_create` et non `update_or_create`.
        """
        from gynecologie.migrations import __name__ as paquet
        from importlib import import_module

        migration = import_module(f'{paquet}.0002_seed_types_visite')

        TypeVisite.objects.filter(code='CPN02').update(nom='Deuxième visite')
        TypeVisite.objects.filter(code='CPN03').delete()

        class _Apps:
            def get_model(self, app_label, nom):
                return TypeVisite

        migration.seed(_Apps(), None)

        self.assertEqual(TypeVisite.objects.get(code='CPN02').nom, 'Deuxième visite',
                         'Le nom retouché a été écrasé')
        self.assertTrue(TypeVisite.objects.filter(code='CPN03').exists(),
                        'Le type supprimé n’a pas été reposé')
        self.assertEqual(TypeVisite.objects.count(), 7)
