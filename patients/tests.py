"""Onglets liés d'une fiche patient : pagination.

Les sept onglets — rendez-vous, soins, consultations, ordonnances,
hospitalisations, demandes et résultats d'examens — passent tous par
`_render_related_list`, qui rendait le jeu entier d'un bloc. Un dossier ancien
chargeait donc des centaines de lignes en mémoire et dans la page.
"""

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Patient, RendezVous


ONGLETS = [
    'rdv_list', 'soin_list', 'consultation_list', 'ordonnance_list',
    'hospitalisation_list', 'demande_examens_list', 'resultat_examens_list',
]


def _patient():
    return Patient.objects.create(
        nom='Kouassi', prenoms='Ama', date_naissance='1990-06-01',
        sexe='F', telephone='0700000000',
    )


class TestPaginationDesOngletsLies(TestCase):

    def setUp(self):
        self.patient = _patient()
        User.objects.create_superuser('su_rl', password='x')
        self.client = Client()
        self.client.login(username='su_rl', password='x')

    def _rendez_vous(self, nombre):
        for i in range(nombre):
            RendezVous.objects.create(
                patient=self.patient,
                date_heure=timezone.now() - timezone.timedelta(days=i),
                motif='Controle %s' % i,
            )

    def _url(self, onglet='rdv_list', suffixe=''):
        return reverse('patients:%s' % onglet, kwargs={'pk': self.patient.pk}) + suffixe

    def test_les_sept_onglets_repondent(self):
        for onglet in ONGLETS:
            with self.subTest(onglet=onglet):
                self.assertEqual(self.client.get(self._url(onglet)).status_code, 200)

    def test_dix_lignes_par_page(self):
        self._rendez_vous(25)
        page = self.client.get(self._url())
        self.assertEqual(len(page.context['items']), 10)
        self.assertEqual(page.context['page_obj'].paginator.num_pages, 3)

    def test_le_compteur_annonce_le_total_pas_la_page(self):
        """Il lisait `items|length`, qui ne vaut plus que 10 une fois paginé."""
        self._rendez_vous(25)
        self.assertContains(self.client.get(self._url()), '<strong>25</strong>')

    def test_la_derniere_page_porte_le_reste(self):
        self._rendez_vous(25)
        page = self.client.get(self._url(suffixe='?page=3'))
        self.assertEqual(len(page.context['items']), 5)

    def test_un_numero_hors_limites_retombe_sur_la_derniere(self):
        self._rendez_vous(25)
        page = self.client.get(self._url(suffixe='?page=99'))
        self.assertEqual(page.context['page_obj'].number, 3)

    def test_pas_de_pagination_sous_dix_lignes(self):
        # Sur le fragment et non la page pleine : celle-ci porte la feuille de
        # style, où le nom de classe apparaît forcément.
        self._rendez_vous(4)
        frag = self.client.get(self._url(),
                               headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertNotContains(frag, 'rl-pagination')

    def test_la_provenance_survit_au_changement_de_page(self):
        """Sans elle, tourner la page depuis la gynécologie rebasculerait
        l'utilisatrice dans le module Patients."""
        self._rendez_vous(25)
        page = self.client.get(self._url(suffixe='?origine=gynecologie'))
        self.assertContains(page, 'origine=gynecologie&amp;page=2')

    def test_le_fragment_ajax_porte_sa_pagination(self):
        """Elle vit dans le fragment : restée dehors, elle annoncerait les pages
        de l'onglet précédent."""
        self._rendez_vous(25)
        frag = self.client.get(self._url(suffixe='?page=2'),
                               headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertContains(frag, 'rl-pagination')
        self.assertContains(frag, 'Page 2 sur 3')

    def test_seule_la_page_affichee_calcule_sa_destination(self):
        """`url_fiche` est posé par ligne : le faire sur tout le jeu annulerait
        le bénéfice de la pagination."""
        self._rendez_vous(25)
        page = self.client.get(self._url())
        poses = [r for r in page.context['items'] if hasattr(r, 'url_fiche')]
        self.assertEqual(len(poses), 10)
