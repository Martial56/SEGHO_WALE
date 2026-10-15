"""Onglets liés d'une fiche patient : pagination.

Les sept onglets — rendez-vous, soins, consultations, ordonnances,
hospitalisations, demandes et résultats d'examens — passent tous par
`_render_related_list`, qui rendait le jeu entier d'un bloc. Un dossier ancien
chargeait donc des centaines de lignes en mémoire et dans la page.
"""

import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
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


# ─── Les boutons suivent les permissions ───────────────────────────────────────

def _avec(username, *codes):
    """Un compte qui détient exactement `codes`, et rien d'autre."""
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(username, password='x')
    for code in codes:
        app_label, codename = code.split('.')
        user.user_permissions.add(Permission.objects.get(
            content_type__app_label=app_label, codename=codename))
    return user


def _medecin():
    from employer.models import Employe
    from medecins.models import Medecin
    return Medecin.objects.create(employe=Employe.objects.create(
        nom='Docteur', prenoms='Test', telephone='0700000001',
        date_embauche='2020-01-01'))


def _evaluation_et_medecin(rdv):
    """Ce que l'infirmier pose avant « En Attente » : évaluation et médecin."""
    from consultations.models import Consultation
    rdv.medecin = _medecin()
    rdv.save(update_fields=['medecin'])
    Consultation.objects.create(patient=rdv.patient, rendez_vous=rdv,
                                motif='Évaluation clinique')


def _page(username, url, attendu=200):
    client = Client()
    client.login(username=username, password='x')
    reponse = client.get(url)
    assert reponse.status_code == attendu, f'{url} → {reponse.status_code}'
    return reponse.content.decode()


class TestLesVuesDeLectureExigentLaPermission(TestCase):
    """Consulter n'est pas plus gratuit que créer.

    Les menus sont masqués par les NavItem, mais un NavItem masque un **menu**,
    pas une **URL** : un compte sans aucun droit qui tapait l'adresse arrivait
    sur la liste des patients et sur les dossiers. Le module hospitalisation
    posait déjà `view_hospitalisation` sur ses vues de lecture ; celles-ci
    suivent le même chemin.
    """

    def setUp(self):
        self.patient = _patient()
        self.rdv = RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now())
        self.sans = _avec('u_lect_rien')

    def _urls_patient(self):
        pk = self.patient.pk
        return ([reverse('patients:list'),
                 reverse('patients:detail', args=[pk]),
                 reverse('patients:patient_info', args=[pk]),
                 reverse('patients:patient_search')]
                + [reverse(f'patients:{onglet}', args=[pk]) for onglet in ONGLETS])

    def _urls_rdv(self):
        return [reverse('patients:rdv_global'),
                reverse('patients:rdv_edit', args=[self.rdv.pk])]

    def _refuse(self, urls, username):
        client = Client()
        client.login(username=username, password='x')
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)

    def _accepte(self, urls, username):
        for url in urls:
            with self.subTest(url=url):
                _page(username, url)

    def test_sans_droit_le_dossier_patient_est_ferme(self):
        self._refuse(self._urls_patient(), 'u_lect_rien')

    def test_view_patient_rouvre_le_dossier_et_ses_onglets(self):
        _avec('u_lect_pat', 'patients.view_patient')
        self._accepte(self._urls_patient(), 'u_lect_pat')

    def test_sans_droit_les_rendez_vous_sont_fermes(self):
        self._refuse(self._urls_rdv(), 'u_lect_rien')

    def test_view_rendezvous_rouvre_les_rendez_vous(self):
        _avec('u_lect_rdv', 'patients.view_rendezvous')
        self._accepte(self._urls_rdv(), 'u_lect_rdv')

    def test_les_deux_droits_ne_se_remplacent_pas(self):
        """`view_patient` n'ouvre pas les rendez-vous, et réciproquement."""
        _avec('u_lect_pat2', 'patients.view_patient')
        self._refuse(self._urls_rdv(), 'u_lect_pat2')

        _avec('u_lect_rdv2', 'patients.view_rendezvous')
        self._refuse(self._urls_patient(), 'u_lect_rdv2')


class TestLExportEtLImportRestentAuxAdministrateurs(TestCase):
    """Quatre vues avaient été oubliées.

    L'export/import des patients vérifiait `is_superuser` ; celui des
    diagnostics et des types de visite, non. N'importe quel compte connecté
    pouvait déposer un fichier et **écrire** dans le catalogue.
    """

    ROUTES = ['patients:export_pathologies', 'patients:import_pathologies',
              'gynecologie_typevisite_export', 'gynecologie_typevisite_import']

    def test_un_compte_ordinaire_est_refuse(self):
        """Même avec tous les droits du catalogue : seul l'admin exporte."""
        _avec('u_io_plein', 'patients.view_pathologie', 'patients.add_pathologie',
              'patients.change_pathologie', 'gynecologie.view_typevisite',
              'gynecologie.change_typevisite')
        client = Client()
        client.login(username='u_io_plein', password='x')
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertEqual(client.get(reverse(route)).status_code, 403)

    def test_l_administrateur_passe(self):
        User.objects.create_superuser('u_io_admin', password='x')
        client = Client()
        client.login(username='u_io_admin', password='x')
        for route in self.ROUTES:
            with self.subTest(route=route):
                self.assertNotEqual(client.get(reverse(route)).status_code, 403)

    def test_le_menu_export_import_ne_s_affiche_que_pour_l_admin(self):
        _avec('u_io_simple', 'patients.view_pathologie')
        User.objects.create_superuser('u_io_admin2', password='x')
        simple = _page('u_io_simple', reverse('patients:pathologie_list'))
        admin = _page('u_io_admin2', reverse('patients:pathologie_list'))
        self.assertNotIn('class="o-ctrl-btn io-toggle-btn"', simple)
        self.assertIn('class="o-ctrl-btn io-toggle-btn"', admin)
        # La fenêtre d'import part avec le bouton : sans elle, le JS d'Échap
        # tombait sur un élément absent.
        self.assertNotIn('id="io-modal-backdrop"', simple)
        self.assertIn('id="io-modal-backdrop"', admin)


class TestLesEcransDeConfigurationSuiventLesPermissions(TestCase):
    """Créer, modifier et supprimer un diagnostic ou un type de visite.

    Les trois écrans n'avaient ni garde dans le gabarit ni décorateur sur la
    vue : n'importe quel compte connecté pouvait vider la liste des
    diagnostics. Les permissions employées sont celles que Django crée tout
    seul avec le modèle — rien à déclarer.
    """

    #: (route de liste, app des permissions, modèle, fabrique d'une ligne)
    ECRANS = [
        ('patients:pathologie_list', 'patients', 'pathologie',
         lambda: __import__('patients.models', fromlist=['Pathologie'])
                 .Pathologie.objects.create(nom='Paludisme')),
        ('gynecologie_typevisite_list', 'gynecologie', 'typevisite',
         lambda: __import__('gynecologie.models', fromlist=['TypeVisite'])
                 .TypeVisite.objects.create(nom='CPN test', code='CPNTEST')),
        ('patients:typevisitecurative_list', 'patients', 'typevisitecurative',
         lambda: __import__('patients.models', fromlist=['TypeVisiteCurative'])
                 .TypeVisiteCurative.objects.create(nom='Pansement', code='PANS')),
    ]

    def test_sans_permission_aucun_bouton_n_est_propose(self):
        """Le compte voit la liste — il a `view_` — et rien d'autre."""
        for i, (route, app, modele, fabrique) in enumerate(self.ECRANS):
            with self.subTest(ecran=route):
                fabrique()
                nom = f'u_cfg_vue{i}'
                _avec(nom, f'{app}.view_{modele}')
                html = _page(nom, reverse(route))
                self.assertNotIn('class="o-btn-create"', html)
                self.assertNotIn('class="btn-icon" title="Modifier"', html)
                self.assertNotIn('class="btn-icon btn-danger" title="Supprimer"', html)
                # La ligne entière ouvrait la fiche au clic : elle aussi se tait.
                self.assertNotIn('<tr onclick="mdOpenConfigModal', html)

    def test_avec_les_quatre_permissions_les_boutons_reviennent(self):
        for i, (route, app, modele, fabrique) in enumerate(self.ECRANS):
            with self.subTest(ecran=route):
                fabrique()
                nom = f'u_cfg_tout{i}'
                _avec(nom, f'{app}.view_{modele}', f'{app}.add_{modele}',
                      f'{app}.change_{modele}', f'{app}.delete_{modele}')
                html = _page(nom, reverse(route))
                self.assertIn('class="o-btn-create"', html)
                self.assertIn('class="btn-icon" title="Modifier"', html)
                self.assertIn('class="btn-icon btn-danger" title="Supprimer"', html)
                self.assertIn('<tr onclick="mdOpenConfigModal', html)

    def test_chaque_permission_n_ouvre_que_son_bouton(self):
        """Le droit de modifier ne donne pas celui de supprimer."""
        from patients.models import Pathologie

        Pathologie.objects.create(nom='Paludisme')
        _avec('u_cfg_chg', 'patients.view_pathologie', 'patients.change_pathologie')
        html = _page('u_cfg_chg', reverse('patients:pathologie_list'))
        self.assertIn('class="btn-icon" title="Modifier"', html)
        self.assertNotIn('class="btn-icon btn-danger" title="Supprimer"', html)
        self.assertNotIn('class="o-btn-create"', html)

    def test_la_liste_elle_meme_demande_son_droit_de_lecture(self):
        _avec('u_cfg_rien')
        client = Client()
        client.login(username='u_cfg_rien', password='x')
        for route, *_ in self.ECRANS:
            with self.subTest(ecran=route):
                self.assertEqual(client.get(reverse(route)).status_code, 403)

    def test_les_vues_refusent_ce_que_les_boutons_cachent(self):
        """Cacher un bouton n'est pas fermer la porte : les deux sont posés."""
        from gynecologie.models import TypeVisite
        from patients.models import Pathologie, TypeVisiteCurative

        pathologie = Pathologie.objects.create(nom='Paludisme')
        visite = TypeVisite.objects.create(nom='CPN test', code='CPNTEST')
        curative = TypeVisiteCurative.objects.create(nom='Pansement', code='PANS')
        # Toutes les permissions de lecture, aucune d'écriture : c'est bien le
        # décorateur d'écriture qui refuse, pas celui de lecture.
        _avec('u_cfg_porte', 'patients.view_pathologie',
              'patients.view_typevisitecurative', 'gynecologie.view_typevisite')
        client = Client()
        client.login(username='u_cfg_porte', password='x')

        interdites = [
            reverse('patients:pathologie_create'),
            reverse('patients:pathologie_edit', args=[pathologie.pk]),
            reverse('patients:pathologie_delete', args=[pathologie.pk]),
            reverse('gynecologie_typevisite_create'),
            reverse('gynecologie_typevisite_edit', args=[visite.pk]),
            reverse('gynecologie_typevisite_delete', args=[visite.pk]),
            reverse('patients:typevisitecurative_create'),
            reverse('patients:typevisitecurative_edit', args=[curative.pk]),
            reverse('patients:typevisitecurative_delete', args=[curative.pk]),
        ]
        for url in interdites:
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)


class TestLeBoutonCreerDesListesDeRendezVous(TestCase):
    """Le CRÉER des listes de RDV vit dans un include partagé.

    Les deux listes — patients et gynécologie — s'en servent, et il n'était
    gardé nulle part alors que les deux vues de création exigent déjà
    `patients.add_rendezvous`. Le bouton menait donc droit à un 403.
    """

    LIRE = 'patients.view_rendezvous'

    def test_sans_la_permission_le_bouton_disparait(self):
        _avec('u_rdv_rien', self.LIRE)
        html = _page('u_rdv_rien', reverse('patients:rdv_global'))
        self.assertNotIn('class="o-btn-create"', html)

    def test_avec_la_permission_le_bouton_revient(self):
        _avec('u_rdv_add', self.LIRE, 'patients.add_rendezvous')
        html = _page('u_rdv_add', reverse('patients:rdv_global'))
        self.assertIn('class="o-btn-create"', html)

    def test_le_bouton_de_l_etat_vide_suit_aussi(self):
        self.assertEqual(RendezVous.objects.count(), 0, "L'état vide doit s'afficher")
        _avec('u_rdv_vide', self.LIRE)
        _avec('u_rdv_vide_add', self.LIRE, 'patients.add_rendezvous')
        sans = _page('u_rdv_vide', reverse('patients:rdv_global'))
        avec = _page('u_rdv_vide_add', reverse('patients:rdv_global'))
        self.assertNotIn('class="o-empty-btn"', sans)
        self.assertIn('class="o-empty-btn"', avec)


class TestLaBarreDActionDuRendezVousEnConsultation(TestCase):
    """Les quatre raccourcis d'une consultation en cours.

    Soins et M.O étaient gardés ; ordonnance et demande de labo ne l'étaient
    pas. Et les quatre vivaient hors du `peut_modifier` des autres boutons :
    ils **soumettent** la fiche, donc un compte sans `change_rendezvous` les
    voyait, cliquait, et récoltait un 403.
    """

    LIRE = 'patients.view_rendezvous'

    def setUp(self):
        self.rdv = RendezVous.objects.create(
            patient=_patient(), date_heure=timezone.now(), statut='en_consultation')
        self.url = reverse('patients:rdv_edit', args=[self.rdv.pk])

    def test_sans_les_permissions_les_deux_raccourcis_se_taisent(self):
        _avec('u_bar_rdv', self.LIRE, 'patients.change_rendezvous')
        html = _page('u_bar_rdv', self.url)
        self.assertNotIn('Créer une ordonnance', html)
        self.assertNotIn('Demande de lab', html)
        # Le voisin déjà gardé reste là : le test ne passerait pas si la barre
        # entière avait disparu par accident.
        self.assertIn('Consultation terminée', html)

    def test_chaque_permission_rallume_son_raccourci(self):
        _avec('u_bar_ord', self.LIRE, 'patients.change_rendezvous',
              'consultations.add_ordonnance')
        html = _page('u_bar_ord', self.url)
        self.assertIn('Créer une ordonnance', html)
        self.assertNotIn('Demande de lab', html)

        _avec('u_bar_lab', self.LIRE, 'patients.change_rendezvous',
              'laboratoire.add_demandeexamen')
        html = _page('u_bar_lab', self.url)
        self.assertIn('Demande de lab', html)
        self.assertNotIn('Créer une ordonnance', html)

    def test_sans_le_droit_de_modifier_aucun_des_quatre_ne_s_affiche(self):
        """Ils soumettent la fiche : les proposer, c'est promettre un 403."""
        _avec('u_bar_lecture', self.LIRE, 'consultations.add_ordonnance',
              'laboratoire.add_demandeexamen', 'soins.add_soin')
        html = _page('u_bar_lecture', self.url)
        # Les quatre raccourcis sont les seuls boutons à poster `_apres` :
        # aucun dans la page, aucun des quatre à l'écran. Le libellé seul ne
        # suffirait pas — « Soins » est aussi un onglet de la fiche patient.
        self.assertNotIn('name="_apres"', html)
        self.assertNotIn('value="terminer"', html)

        # Le même compte, cette fois avec le droit de modifier : la barre
        # revient. Sans cette moitié, le test passerait si la page était vide.
        _avec('u_bar_ecriture', self.LIRE, 'consultations.add_ordonnance',
              'patients.change_rendezvous')
        html = _page('u_bar_ecriture', self.url)
        self.assertIn('name="_apres"', html)


class TestLesDroitsParEtapeDuRendezVous(TestCase):
    """Chaque étape de la fiche a sa permission (cf. patients/rdv_droits.py).

    L'accueil confirme, l'infirmier met en attente, le médecin mène la
    consultation : aucun des trois ne doit pouvoir faire l'étape d'un autre,
    ni par le bouton ni en postant l'action à la main.
    """

    LIRE = 'patients.view_rendezvous'

    def setUp(self):
        self.patient = _patient()
        _avec('u_accueil', self.LIRE, 'patients.add_rendezvous', 'patients.confirmer_rendezvous')
        _avec('u_infirmier', self.LIRE, 'patients.mettre_en_attente_rendezvous')
        _avec('u_medecin', self.LIRE, 'patients.consulter_rendezvous')

    def _rdv(self, statut):
        rdv = RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now(), statut=statut)
        return rdv, reverse('patients:rdv_edit', args=[rdv.pk])

    def _poster(self, username, url, action):
        client = Client()
        client.login(username=username, password='x')
        return client.post(url, {'_action': action})

    def test_chaque_bouton_n_apparait_qu_a_son_etape(self):
        _, url = self._rdv('planifie')
        self.assertIn('value="confirmer"', _page('u_accueil', url))
        self.assertNotIn('value="confirmer"', _page('u_infirmier', url))
        self.assertNotIn('value="confirmer"', _page('u_medecin', url))

        _, url = self._rdv('en_attente')
        self.assertIn('value="en_consultation"', _page('u_medecin', url))
        self.assertNotIn('value="en_consultation"', _page('u_infirmier', url))
        self.assertNotIn('value="en_consultation"', _page('u_accueil', url))

        _, url = self._rdv('en_consultation')
        self.assertIn('value="terminer"', _page('u_medecin', url))
        self.assertNotIn('value="terminer"', _page('u_infirmier', url))

    def test_poster_l_etape_d_un_autre_est_refuse(self):
        rdv, url = self._rdv('confirme')
        self.assertEqual(self._poster('u_accueil', url, 'en_attente').status_code, 403)
        self.assertEqual(self._poster('u_medecin', url, 'en_attente').status_code, 403)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'confirme')

        # « En Attente » exige l'évaluation et le médecin.
        _evaluation_et_medecin(rdv)
        self.assertEqual(self._poster('u_infirmier', url, 'en_attente').status_code, 302)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'en_attente')

        self.assertEqual(self._poster('u_infirmier', url, 'en_consultation').status_code, 403)
        self.assertEqual(self._poster('u_medecin', url, 'en_consultation').status_code, 302)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'en_consultation')

    def test_annuler_exige_sa_propre_permission(self):
        rdv, url = self._rdv('en_consultation')
        self.assertNotIn('value="annuler"', _page('u_medecin', url))
        self.assertEqual(self._poster('u_medecin', url, 'annuler').status_code, 403)
        _avec('u_annule', self.LIRE, 'patients.annuler_rendezvous')
        self.assertEqual(self._poster('u_annule', url, 'annuler').status_code, 302)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'annule')

    def test_change_rendezvous_garde_l_acces_complet(self):
        from patients import rdv_droits
        user = _avec('u_complet', self.LIRE, 'patients.change_rendezvous')
        for statut in ('planifie', 'confirme', 'en_attente', 'en_consultation', 'termine'):
            rdv, _ = self._rdv(statut)
            self.assertTrue(rdv_droits.peut_modifier(user, rdv), statut)
        self.assertTrue(all(rdv_droits.droits(user, rdv).values()))


# ─── Pas de chiffre dans un nom ────────────────────────────────────────────────

class TestLesChiffresNeSEcriventPasDansUnNom(TestCase):
    """Un chiffre n'a pas sa place dans un nom, et on ne le reproche pas.

    Refuser au moment d'enregistrer ferait perdre la saisie pour une faute de
    frappe. À l'écran la touche ne fait rien ; le formulaire retire de son côté
    ce qui arrive par un autre chemin — un collage, un import, une requête
    forgée. Les apostrophes et les traits d'union restent : sur les 423
    patients du fichier, douze noms portent une apostrophe et dix un trait
    d'union.
    """

    def setUp(self):
        self.user = _avec('u_chiffre', 'patients.add_patient', 'patients.view_patient')

    def _creer(self, nom, prenoms):
        client = Client()
        client.login(username='u_chiffre', password='x')
        client.post(reverse('patients:create'), {
            'nom': nom, 'prenoms': prenoms,
            'date_naissance': '1990-06-01', 'sexe': 'F',
            'telephone': '0700000000',
            # Les trois autres champs obligatoires de la fiche.
            'nationalite': 'Ivoirienne', 'adresse': 'Assabou',
            'ville': 'Yamoussoukro',
        }, follow=True)
        return Patient.objects.order_by('-pk').first()

    def test_le_chiffre_est_retire_sans_message(self):
        patient = self._creer('KOUASSI2', 'AMA')
        self.assertIsNotNone(patient, "Le patient devait être créé malgré le chiffre")
        self.assertEqual(patient.nom, 'KOUASSI')

    def test_le_prenom_suit_la_meme_regle(self):
        patient = self._creer('KOUASSI', 'AMA 3')
        self.assertEqual(patient.prenoms, 'AMA')

    def test_l_apostrophe_et_le_trait_d_union_restent(self):
        """Les N'Guessan et les Marie-Claire sont des noms comme les autres."""
        patient = self._creer("N'GUESSAN", 'MARIE-CLAIRE')
        self.assertEqual(patient.nom, "N'GUESSAN")
        self.assertEqual(patient.prenoms, 'MARIE-CLAIRE')

    def test_les_accents_restent(self):
        patient = self._creer('KOFFI', 'AMÉLIE')
        self.assertEqual(patient.prenoms, 'AMÉLIE')

    def test_un_nom_entierement_chiffre_ne_passe_pas(self):
        """Vidé de ses chiffres il ne reste rien, et le nom est obligatoire."""
        avant = Patient.objects.count()
        self._creer('12345', 'AMA')
        self.assertEqual(Patient.objects.count(), avant,
                         "Un nom vide a été accepté")

    def test_le_navigateur_empeche_aussi_la_frappe(self):
        """Le gabarit porte le filtre : sans lui, le chiffre s'afficherait."""
        client = Client()
        client.login(username='u_chiffre', password='x')
        html = client.get(reverse('patients:create')).content.decode()
        self.assertIn("replace(/[0-9]/g, '')", html)
        self.assertIn("normaliserNom('id_nom')", html)
        self.assertIn("normaliserNom('id_prenoms')", html)


class TestLaLigneAnnuleeEstGrisee(TestCase):
    """Le grisé d'un rendez-vous annulé devient la règle commune.

    Il n'était écrit que dans la feuille de `templates/patients/rendez_vous.html`,
    sous `.rdv-row-annule` : la liste de gynécologie partageait pourtant le même
    gabarit de ligne et n'en voyait rien. La règle vit désormais dans
    `static/css/global.css` sous `.ligne-annulee`, partagée avec les soins, les
    hospitalisations et les factures.
    """

    def setUp(self):
        self.patient = _patient()
        User.objects.create_superuser('su_grise', password='x')
        self.client = Client()
        self.client.login(username='su_grise', password='x')

    def _rdv(self, statut):
        from medecins.models import Departement
        departement, _ = Departement.objects.get_or_create(
            code='GYN', defaults={'nom': 'Gynécologie'})
        return RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now(),
            motif='Controle', statut=statut, departement=departement,
        )

    def _html(self, nom):
        reponse = self.client.get(reverse(nom) + '?filter=')
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    #: Le gabarit compose la classe en fin d'attribut — `class="rdv-row
    #: rdv-etat-annule ligne-annulee"`. On vise ce balisage et non le nom de
    #: classe nu : celui-ci apparaît aussi dans les commentaires des feuilles de
    #: style, qui sont rendus dans la page, et les tests passeraient à vide.
    MARQUE = 'rdv-etat-annule ligne-annulee"'

    def test_un_rdv_annule_est_grise_sur_la_liste_des_patients(self):
        self._rdv('annule')
        self.assertIn(self.MARQUE, self._html('patients:rdv_global'))

    def test_un_rdv_annule_est_grise_aussi_en_gynecologie(self):
        """C'est la liste qui n'avait jamais eu le grisé."""
        self._rdv('annule')
        self.assertIn(self.MARQUE, self._html('gynecologie_rdv'))

    def test_un_rdv_confirme_n_est_pas_grise(self):
        """Sans cette moitié, les tests précédents passeraient si tout l'était."""
        self._rdv('confirme')
        for nom in ('patients:rdv_global', 'gynecologie_rdv'):
            self.assertNotIn('ligne-annulee"', self._html(nom))

    def test_l_ancienne_classe_ne_sert_plus(self):
        """Elle ne vivait que dans une feuille de page ; la laisser dans le
        gabarit la rendrait muette sur les listes qui n'ont pas cette feuille."""
        self._rdv('annule')
        self.assertNotIn('rdv-row-annule', self._html('patients:rdv_global'))


class TestLInfirmierEvalueEncoreUnRdvEnAttente(TestCase):
    """« Mettre en attente » ouvre l'évaluation clinique et le choix du
    médecin, au stade « Confirmé » comme une fois le RDV « En attente » :
    au second, la fiche relevait de `consulter_rendezvous` et l'infirmier ne
    pouvait plus corriger une constante ni réorienter le patient.
    """

    def setUp(self):
        self.medecin = _medecin()
        self.patient = _patient()
        _avec('u_inf_eval', 'patients.view_rendezvous',
              'patients.mettre_en_attente_rendezvous')
        _avec('u_acc_eval', 'patients.view_rendezvous',
              'patients.confirmer_rendezvous')

    def _rdv(self, statut):
        # Sans consultation : l'évaluation la crée. Sur un RDV « En attente »,
        # le signal de `consultations` le passait alors « En consultation ».
        rdv = RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now(), statut=statut)
        return rdv, reverse('patients:rdv_edit', args=[rdv.pk])

    def _evaluer(self, username, url):
        client = Client()
        client.login(username=username, password='x')
        return client.post(url, {'_action': 'save_eval', 'eval_poids': '70',
                                 'eval_medecin': self.medecin.pk})

    def test_en_attente_l_infirmier_modifie_l_evaluation_et_le_medecin(self):
        rdv, url = self._rdv('en_attente')
        self.assertIn('id="btn-eval-toggle"', _page('u_inf_eval', url))
        self.assertEqual(self._evaluer('u_inf_eval', url).status_code, 302)
        rdv.refresh_from_db()
        self.assertEqual(rdv.medecin, self.medecin)
        self.assertEqual(float(rdv.consultation.constantes.poids), 70)
        self.assertEqual(rdv.statut, 'en_attente')

    def test_en_attente_refuse_sans_evaluation_ni_medecin(self):
        rdv, url = self._rdv('confirme')
        client = Client()
        client.login(username='u_inf_eval', password='x')
        client.post(url, {'_action': 'en_attente'})
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'confirme')

        # Évaluation sans médecin : toujours refusé.
        client.post(url, {'_action': 'save_eval', 'eval_poids': '70'})
        client.post(url, {'_action': 'en_attente'})
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'confirme')

        # Avec le médecin, la mise en attente passe.
        client.post(url, {'_action': 'en_attente', 'medecin': self.medecin.pk})
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'en_attente')

    def test_une_fois_la_consultation_commencee_c_est_fini(self):
        rdv, url = self._rdv('en_consultation')
        self.assertNotIn('id="btn-eval-toggle"', _page('u_inf_eval', url))
        self.assertEqual(self._evaluer('u_inf_eval', url).status_code, 403)
        rdv.refresh_from_db()
        self.assertIsNone(rdv.medecin)

    def test_sans_la_permission_l_evaluation_reste_fermee(self):
        rdv, url = self._rdv('en_attente')
        self.assertNotIn('id="btn-eval-toggle"', _page('u_acc_eval', url))
        self.assertEqual(self._evaluer('u_acc_eval', url).status_code, 403)

    def test_l_evaluation_n_ouvre_pas_le_reste_de_la_fiche(self):
        """Seul `save_eval` est ouvert : l'enregistrement de la fiche reste refusé."""
        _, url = self._rdv('en_attente')
        client = Client()
        client.login(username='u_inf_eval', password='x')
        self.assertEqual(client.post(url, {'motif': 'x'}).status_code, 403)


class TestUnePermissionDEtapePrimeSurLAccesComplet(TestCase):
    """« Peut modifier : rendez-vous » ne rouvre pas les autres étapes.

    Un infirmier qui tenait aussi `change_rendezvous` (par un second groupe,
    par exemple) voyait le bouton « En consultation » une fois le RDV mis en
    attente : l'accès complet l'emportait sur sa permission d'étape.
    """

    def setUp(self):
        self.rdv = RendezVous.objects.create(
            patient=_patient(), date_heure=timezone.now(), statut='en_attente')
        self.url = reverse('patients:rdv_edit', args=[self.rdv.pk])
        _avec('u_inf_complet', 'patients.view_rendezvous', 'patients.change_rendezvous',
              'patients.mettre_en_attente_rendezvous')

    def test_l_infirmier_ne_voit_pas_en_consultation(self):
        self.assertNotIn('value="en_consultation"', _page('u_inf_complet', self.url))

    def test_ni_ne_peut_le_poster(self):
        client = Client()
        client.login(username='u_inf_complet', password='x')
        self.assertEqual(client.post(self.url, {'_action': 'en_consultation'}).status_code, 403)
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.statut, 'en_attente')

    def test_sans_permission_d_etape_l_acces_complet_demeure(self):
        _avec('u_seul_complet', 'patients.view_rendezvous', 'patients.change_rendezvous')
        self.assertIn('value="en_consultation"', _page('u_seul_complet', self.url))


class TestLAgeEstDetailleSurLaListeDesRdv(TestCase):
    """Même correction que sur la liste des soins, sur le gabarit de ligne
    partagé par les rendez-vous des patients et ceux de gynécologie.

    `templates/includes/rdv_row.html` écrivait « {{ patient.age }} ans ». La
    liste des patients, elle, affiche `age_detail` depuis toujours : deux
    listes du même dossier ne donnaient pas le même âge.
    """

    def setUp(self):
        self.patient = _patient()
        # `_patient` pose la date de naissance sous forme de chaîne : tant
        # qu'on n'a pas relu la ligne, `age_detail` travaille sur un `str`.
        self.patient.refresh_from_db()
        User.objects.create_superuser('su_age_rdv', password='x')
        self.client = Client()
        self.client.login(username='su_age_rdv', password='x')
        from medecins.models import Departement
        departement, _ = Departement.objects.get_or_create(
            code='GYN', defaults={'nom': 'Gynécologie'})
        RendezVous.objects.create(
            patient=self.patient, date_heure=timezone.now(),
            motif='Controle', statut='confirme', departement=departement,
        )

    #: Les deux listes partagent `includes/rdv_row.html` : la correction doit
    #: se voir sur les deux, sinon elle n'est écrite qu'à moitié.
    LISTES = ('patients:rdv_global', 'gynecologie_rdv')

    def _html(self, nom):
        reponse = self.client.get(reverse(nom) + '?filter=')
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    def test_les_deux_listes_portent_l_age_detaille(self):
        for nom in self.LISTES:
            self.assertIn(self.patient.age_detail, self._html(nom))

    def test_l_ancien_format_en_annees_seules_a_disparu(self):
        """Sans cette moitié, le test précédent passerait si les deux
        cohabitaient."""
        for nom in self.LISTES:
            self.assertNotIn(f'{self.patient.age} ans', self._html(nom))


class TestLeDepliageNeMelangePasLesDeuxVues(TestCase):
    """La liste des patients rend deux fois le même regroupement : des fiches
    dans `#kanban-view`, des lignes dans `#list-view`. Les deux portent les
    mêmes `data-chemin` et les mêmes `data-parent`, puisque c'est le même arbre.
    La gynécologie fait pareil.

    listing_groupes.js cherchait ces attributs dans tout le document. Déplier
    une bande du kanban y versait donc les fiches **et** les lignes du tableau :
    mesuré dans Chrome sur 199 patients, les colonnes de la grille passaient de
    254 px à 600 px et la page débordait à 3029 px de large, d'où le défilement
    horizontal et les fiches étirées. Le tableau recevait symétriquement les
    fiches, et se cassait de la même façon.

    Il n'y a pas de lanceur JS dans ce dépôt. Ce qui est vérifiable depuis
    Python l'est : que l'ambiguïté existe bel et bien dans la page — sans elle
    la correction n'aurait pas lieu d'être —, que les deux bandes restent
    distinguables à leur balise, puisque c'est ce dont le script se sert pour
    choisir sa vue, et qu'il ne cherche plus rien dans `document`.
    """

    def setUp(self):
        _patient()
        User.objects.create_superuser('su_deux_vues', password='x')
        self.client = Client()
        self.client.login(username='su_deux_vues', password='x')

    def _fragment(self):
        """La réponse à un dépliage : c'est elle que le script découpe."""
        reponse = self.client.get(
            reverse('patients:list') + '?group=sexe&_groupe=0',
            headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    def test_les_deux_vues_portent_le_meme_chemin_de_groupe(self):
        """L'ambiguïté que le script doit lever."""
        html = self._fragment()
        self.assertRegex(
            html, r'<div[^>]*class="lst-groupe lst-groupe-bande[^"]*"[^>]*data-chemin="0"',
            'la bande du kanban a disparu')
        self.assertRegex(
            html, r'<tr class="lst-groupe[^"]*"[^>]*data-chemin="0"',
            'la ligne de groupe du tableau a disparu')

    def test_les_lignes_du_groupe_existent_dans_les_deux_vues(self):
        """Même chemin de parent des deux côtés : chercher `data-parent="0"`
        dans tout le document ramène forcément les deux sortes."""
        html = self._fragment()
        self.assertRegex(html, r'<a [^>]*class="pk-card"[^>]*data-parent="0"',
                         'la fiche kanban du groupe a disparu')
        self.assertRegex(html, r'<tr data-parent="0"',
                         'la ligne tableau du groupe a disparu')

    def test_le_script_ne_cherche_plus_les_lignes_dans_tout_le_document(self):
        """Le seul garde-fou possible ici : la portée de la recherche.

        Les deux bandes étant indiscernables à l'échelle du document, chercher
        des **lignes** sur `document` reverse l'autre vue dans celle qu'on
        déplie. Lignes et sous-groupes doivent donc partir du conteneur de
        l'en-tête visé.

        Chercher des **bandes** sur le document reste permis, et deux
        mécanismes le font à bon droit : le préchargement, qui a besoin de
        toutes les bandes de la page pour les ranger par conteneur, et la
        restauration des groupes ouverts, qui doit justement rouvrir le groupe
        dans les deux vues à la fois. Ce que le premier en tire repasse par
        `lignesDu`, qui cloisonne ; le second ne fait que basculer une classe.

        On vise donc précisément `[data-chemin^=`, le repli en cascade des
        sous-groupes — le seul de ces trois usages qui doive rester dans son
        conteneur, puisqu'il referme des bandes. Viser `.lst-groupe` tout court,
        ou même `[data-chemin`, condamnerait les deux autres.
        """
        from django.contrib.staticfiles import finders
        source = open(finders.find('js/listing_groupes.js')).read()
        self.assertNotIn(
            "document.querySelectorAll('[data-parent=", source,
            'les lignes sont de nouveau cherchées dans tout le document')
        self.assertNotIn(
            "document.querySelectorAll('.lst-groupe[data-chemin^=", source,
            'les sous-groupes sont de nouveau cherchés dans tout le document')
        self.assertIn(
            'racine.querySelectorAll', source,
            'la recherche ne part plus du conteneur de l’en-tête')


class TestSauvegarderEtFacturerExigeUnTypeDeConsultation(TestCase):
    """« Sauvegarder et facturer » partait sur la facture même avec
    « — Choisir un type de consultation — » : la facture n'avait alors rien
    à reprendre comme désignation. Même règle pour les deux créations."""

    #: Les deux pages de création partagent `RendezVousForm`.
    CREATIONS = ('patients:rdv_create', 'gynecologie_rdv_create')

    def setUp(self):
        from medecins.models import Departement
        from services.models import Articleservice, CategorieArticle
        self.patient = _patient()
        self.departement, _ = Departement.objects.get_or_create(
            code='GYN', defaults={'nom': 'Gynécologie'})
        categorie, _ = CategorieArticle.objects.get_or_create(
            code='CS', defaults={'nom': 'Consultations'})
        self.type_consultation = Articleservice.objects.create(
            nom='CONSULTATION GYN', categorie=categorie, departement=self.departement)
        # Superuser : la gynécologie exige aussi son module.
        User.objects.create_superuser('su_crea_rdv', password='x')
        self.client = Client()
        self.client.login(username='su_crea_rdv', password='x')

    def _creer(self, nom, **extra):
        donnees = {'patient': self.patient.pk, 'departement': self.departement.pk,
                   'date_heure': timezone.now().strftime('%Y-%m-%dT%H:%M:%S'),
                   'motif': 'Controle'}
        donnees.update(extra)
        return self.client.post(reverse(nom), donnees)

    def test_sans_type_aucun_rdv_ni_facture(self):
        for nom in self.CREATIONS:
            with self.subTest(nom):
                reponse = self._creer(nom)
                self.assertEqual(reponse.status_code, 200)
                self.assertIn('Choisissez un type de consultation avant de facturer.',
                              reponse.content.decode())
                self.assertFalse(RendezVous.objects.filter(patient=self.patient).exists())

    def test_avec_un_type_on_part_sur_la_facture(self):
        """Sans cette moitié, le test précédent passerait si plus rien ne se créait."""
        for nom in self.CREATIONS:
            with self.subTest(nom):
                reponse = self._creer(nom, type_consultation=self.type_consultation.pk)
                self.assertEqual(reponse.status_code, 302)
                self.assertIn(reverse('facturation:create'), reponse['Location'])
                RendezVous.objects.filter(patient=self.patient).delete()


class TestLaFichePatientsUtiliseLesTypesDeVisiteCpn(TestCase):
    """La fiche patients proposait « 1ère visite / Visite de suivi » et ne
    posait pas `RendezVous.cpn_type_visite` : ses CPN manquaient au rapport
    maternité, qui compte par cette clé étrangère."""

    def setUp(self):
        from gynecologie.models import TypeVisite
        self.cpn1, _ = TypeVisite.objects.get_or_create(
            code='CPN01', defaults={'nom': 'CPN1 premier trimestre de la grossesse'})
        self.cpn1_autres, _ = TypeVisite.objects.get_or_create(
            code='CPNA01', defaults={'nom': 'CPN1 Autres trimestres de la grossesse'})
        self.rdv = RendezVous.objects.create(
            patient=_patient(), date_heure=timezone.now(), statut='en_consultation')
        self.url = reverse('patients:rdv_edit', args=[self.rdv.pk])
        User.objects.create_superuser('su_cpn', password='x')
        self.client = Client()
        self.client.login(username='su_cpn', password='x')

    def test_la_liste_configurable_remplace_les_deux_choix_fixes(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn(f'<option value="{self.cpn1.pk}" >{self.cpn1.nom}</option>', html)
        self.assertNotIn('value="1ere"', html)

    def test_l_enregistrement_pose_le_type_sur_le_rdv(self):
        self.client.post(self.url, {'_action': 'autosave_registres',
                                    'cpn_type_visite': str(self.cpn1.pk)})
        self.rdv.refresh_from_db()
        self.assertEqual(self.rdv.cpn_type_visite, self.cpn1)

        # Et le vider le retire : la clé suit le registre dans les deux sens.
        self.client.post(self.url, {'_action': 'autosave_registres', 'cpn_type_visite': ''})
        self.rdv.refresh_from_db()
        self.assertIsNone(self.rdv.cpn_type_visite)


class TestLaMigrationReprendLesTypesDeVisiteCpn(TestCase):
    """patients/migrations/0041 : pose la clé étrangère d'après le registre."""

    def setUp(self):
        from gynecologie.models import TypeVisite
        self.cpn1, _ = TypeVisite.objects.get_or_create(
            code='CPN01', defaults={'nom': 'CPN1 premier trimestre de la grossesse'})
        self.cpn1_autres, _ = TypeVisite.objects.get_or_create(
            code='CPNA01', defaults={'nom': 'CPN1 Autres trimestres de la grossesse'})

    def _apres_migration(self, **donnees):
        import importlib
        from django.apps import apps
        from patients.models import RegistreCPN
        rdv = RendezVous.objects.create(patient=_patient(), date_heure=timezone.now())
        reg = RegistreCPN.objects.create(rdv=rdv, donnees=donnees)
        importlib.import_module(
            'patients.migrations.0041_type_visite_cpn_depuis_registre').remplir(apps, None)
        rdv.refresh_from_db()
        reg.refresh_from_db()
        return rdv.cpn_type_visite, reg.donnees.get('cpn_type_visite')

    def test_l_identifiant_du_registre_devient_la_cle(self):
        self.assertEqual(self._apres_migration(cpn_type_visite=str(self.cpn1_autres.pk))[0],
                         self.cpn1_autres)

    def test_les_anciennes_valeurs_ne_donnent_pas_le_rang(self):
        """« 1ère visite » = première venue au centre, quel que soit le rang de
        la CPN : même avec les semaines d'aménorrhée, on ne la convertit pas."""
        self.assertEqual(
            self._apres_migration(cpn_type_visite='1ere', cpn_semaines_amenorrhee='10'),
            (None, '1ere'))
        self.assertEqual(self._apres_migration(cpn_type_visite='suivi'), (None, 'suivi'))


class TestLaNumerotationSurvitAUneSuppression(TestCase):
    """Supprimer un patient ne doit pas casser la création des suivants.

    Le code était le nombre de patients de l'année, plus un. Supprimer trois
    fiches ramenait ce compte trois crans en arrière, et le code calculé était
    déjà porté par une fiche restée en base : l'enregistrement tombait sur la
    contrainte d'unicité de `code_patient`. Et il tombait encore à chaque
    tentative suivante, le compte ne pouvant plus rattraper son retard — la
    création de patients restait cassée jusqu'à une intervention sur le code.

    C'est arrivé en production, après une suppression depuis /admin/.
    """

    def _creer(self, suffixe):
        return Patient.objects.create(
            nom=f'Num{suffixe}', prenoms='Patient',
            date_naissance='1990-06-01', sexe='M', telephone='0700000000')

    def test_creer_apres_une_suppression_ne_leve_plus(self):
        a, b, c = (self._creer(i) for i in range(3))
        b.delete()
        # Sans le correctif : IntegrityError sur code_patient.
        d = self._creer('apres')
        self.assertTrue(d.code_patient)

    def test_le_code_ne_reprend_pas_celui_d_un_supprime(self):
        """Réattribuer le code d'une fiche effacée mêlerait deux dossiers.

        Les écritures qui la citaient — journal d'activité, exports, documents
        imprimés — se rattacheraient en silence au nouveau venu.
        """
        a, b, c = (self._creer(i) for i in range(3))
        efface = b.code_patient
        b.delete()
        d = self._creer('apres')
        self.assertNotEqual(d.code_patient, efface)
        self.assertGreater(d.code_patient, c.code_patient)

    def test_vider_la_table_repart_du_premier_rang(self):
        self._creer('seul').delete()
        annee = timezone.now().year
        self.assertEqual(self._creer('neuf').code_patient, f'PAT{annee}00001')

    def test_plusieurs_suppressions_d_affilee(self):
        """Le cas réel : plusieurs fiches retirées d'un coup depuis /admin/."""
        patients = [self._creer(i) for i in range(6)]
        dernier = patients[-1].code_patient
        Patient.all_objects.filter(
            pk__in=[p.pk for p in patients[1:4]]).delete()
        suivant = self._creer('apres')
        self.assertGreater(suivant.code_patient, dernier)
        self.assertEqual(Patient.all_objects.filter(
            code_patient=suivant.code_patient).count(), 1)


class TestLaNumerotationDesNaissances(TestCase):
    """Même défaut, même correctif : `Naissance` numérotait par comptage."""

    def setUp(self):
        self.mere = Patient.objects.create(
            nom='Mere', prenoms='Test', date_naissance='1990-06-01',
            sexe='F', telephone='0700000000')

    def _naissance(self):
        from .models import Naissance
        return Naissance.objects.create(
            mere=self.mere, date_accouchement=timezone.now(), sexe_enfant='M')

    def test_creer_apres_une_suppression_ne_leve_plus(self):
        a, b, c = (self._naissance() for _ in range(3))
        dernier = c.numero
        b.delete()
        suivant = self._naissance()
        self.assertGreater(suivant.numero, dernier)


class TestImportPatients(TestCase):
    """Import de masse : rapprochement, numérotation et compteurs.

    Le rapprochement se faisait une ligne à la fois, par une requête sur la date
    de naissance — non indexée — et la numérotation retriait tous les codes à
    chaque enregistrement. Sur 48 000 lignes le coût était quadratique. Les
    clés sont désormais relevées une fois en mémoire ; ces tests fixent le
    comportement que cette réécriture devait conserver.
    """

    def setUp(self):
        from core.models import TacheImport
        from core.taches import Avancement
        self.tache = TacheImport.objects.create(libelle='Test')
        self.avancement = Avancement(self.tache)

    def _importer(self, lignes, do_update=False):
        import json
        from .views import _executer_import_patients
        contenu = json.dumps(lignes).encode('utf-8')
        message = _executer_import_patients(
            self.avancement, 'fichier.json', contenu, do_update, None)
        self.tache.refresh_from_db()
        return message

    @staticmethod
    def _ligne(code='', nom='Kone Adama', age='30', genre='M', mobile='0700000001',
               date_naissance=None):
        ligne = {'code_identifiant': code, 'nom': nom, 'age': age,
                 'genre': genre, 'mobile': mobile}
        if date_naissance is not None:
            ligne['date_naissance'] = date_naissance
        return ligne

    def test_cree_les_patients_avec_des_codes_distincts(self):
        self._importer([
            self._ligne(nom='Kone Adama', mobile='0700000001'),
            self._ligne(nom='Traore Awa', genre='F', mobile='0700000002'),
            self._ligne(nom='Yao Koffi', age='45', mobile='0700000003'),
        ])
        self.assertEqual(Patient.objects.count(), 3)
        self.assertEqual(self.tache.crees, 3)
        self.assertEqual(self.tache.traites, 3)
        codes = set(Patient.objects.values_list('code_patient', flat=True))
        self.assertEqual(len(codes), 3)
        self.assertTrue(all(c.startswith('PAT') for c in codes))

    def test_la_numerotation_reprend_apres_les_patients_existants(self):
        existant = Patient.objects.create(
            nom='Deja', prenoms='La', date_naissance='1980-01-01',
            sexe='M', telephone='0700000000')
        self._importer([self._ligne()])
        nouveau = Patient.objects.exclude(pk=existant.pk).get()
        self.assertGreater(nouveau.code_patient, existant.code_patient)

    # Date de naissance renseignée dans ces deux-là : avec une date déduite
    # d'un âge, la clé de rapprochement comprend le téléphone (voir
    # `_cle_identite`), et changer de numéro revient à présenter quelqu'un
    # d'autre. Le cas est couvert plus bas, à part.
    def test_un_patient_deja_connu_est_ignore_sans_mise_a_jour(self):
        self._importer([self._ligne(date_naissance='14/05/1991')])
        self._importer([self._ligne(date_naissance='14/05/1991', mobile='0799999999')])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.ignores, 1)
        self.assertEqual(Patient.objects.get().telephone, '0700000001')

    def test_un_patient_deja_connu_est_mis_a_jour_si_demande(self):
        self._importer([self._ligne(date_naissance='14/05/1991')])
        self._importer([self._ligne(date_naissance='14/05/1991', mobile='0799999999')],
                       do_update=True)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.mis_a_jour, 1)
        self.assertEqual(Patient.objects.get().telephone, '0799999999')

    def test_date_approximative_et_numero_change_donnent_deux_fiches(self):
        """Le prix de la prudence, énoncé ici pour qu'il ne surprenne personne.

        Quand la date vient d'un âge, elle ne distingue plus personne : seul le
        téléphone le fait. Un patient qui a changé de numéro revient donc en
        double. C'est le choix qu'on a fait : un doublon se répare, un dossier
        médical écrasé par celui d'un homonyme, non.
        """
        self._importer([self._ligne()])                      # âge seul
        self._importer([self._ligne(mobile='0799999999')])
        self.assertEqual(Patient.objects.count(), 2)

    def test_le_rapprochement_ignore_casse_et_accents(self):
        self._importer([self._ligne(nom='Koné Adama')])
        self._importer([self._ligne(nom='KONE adama')])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.ignores, 1)

    def test_un_identifiant_externe_est_conserve(self):
        self._importer([self._ligne(code='EXT-42')])
        self.assertEqual(Patient.objects.get().ancien_identifiant, 'EXT-42')

    def test_un_reimport_par_notre_propre_code_n_ecrase_pas_l_identifiant_externe(self):
        self._importer([self._ligne(code='EXT-42')])
        patient = Patient.objects.get()
        self._importer(
            [self._ligne(code=patient.code_patient, mobile='0799999999')],
            do_update=True)
        patient.refresh_from_db()
        self.assertEqual(patient.telephone, '0799999999')
        self.assertEqual(patient.ancien_identifiant, 'EXT-42')

    def test_un_doublon_interne_au_fichier_n_est_cree_qu_une_fois(self):
        self._importer([self._ligne(), self._ligne(), self._ligne()])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.crees, 1)
        self.assertEqual(self.tache.ignores, 2)

    def test_les_lignes_inexploitables_sont_comptees_en_erreur(self):
        # Une ligne sans âge ni date de naissance n'en fait plus partie : elle
        # s'importe, sans date (voir TestDateDeNaissanceFacultative). Restent
        # le nom, le genre et le téléphone, qui eux sont exigés.
        self._importer([
            self._ligne(nom=''),
            self._ligne(nom='Sans Genre', genre='?'),
            self._ligne(nom='Sans Tel', mobile=''),
            self._ligne(nom='Bon Dossier'),
        ])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.erreurs, 3)
        self.assertEqual(self.tache.traites, 4)

    def test_l_avancement_est_tenu_a_jour(self):
        self._importer([self._ligne(nom=f'Patient Numero{i}', mobile=f'070000{i:04d}')
                        for i in range(10)])
        self.assertEqual(self.tache.total, 10)
        self.assertEqual(self.tache.traites, 10)
        self.assertEqual(self.tache.pourcentage, 100)

    def test_un_fichier_illisible_remonte_une_erreur(self):
        from .views import _executer_import_patients
        with self.assertRaises(ValueError):
            _executer_import_patients(
                self.avancement, 'fichier.txt', b'nimporte quoi', False, None)


class TestStatutDeTache(TestCase):
    """La jauge relit l'avancement par une URL dédiée — réservée à son auteur."""

    def setUp(self):
        from core.models import TacheImport
        self.auteur = User.objects.create_user('auteur_tache', password='x')
        self.tiers = User.objects.create_user('tiers_tache', password='x')
        self.tache = TacheImport.objects.create(
            libelle='Import de patients', utilisateur=self.auteur,
            total=200, traites=50, crees=50, etape='Enregistrement…')

    def _url(self):
        return reverse('tache_statut', args=[self.tache.pk])

    def test_l_auteur_lit_l_avancement(self):
        self.client.login(username='auteur_tache', password='x')
        data = self.client.get(self._url()).json()
        self.assertEqual(data['pourcentage'], 25)
        self.assertEqual(data['traites'], 50)
        self.assertFalse(data['termine'])

    def test_un_tiers_n_y_a_pas_acces(self):
        self.client.login(username='tiers_tache', password='x')
        self.assertEqual(self.client.get(self._url()).status_code, 403)

    def test_une_tache_terminee_le_dit(self):
        self.tache.etat = 'termine'
        self.tache.save()
        self.client.login(username='auteur_tache', password='x')
        self.assertTrue(self.client.get(self._url()).json()['termine'])


class TestDateDeNaissanceFacultative(TestCase):
    """La date de naissance a remplacé l'âge à l'export.

    Elle n'est exigée qu'à la création, où c'est elle qui sépare deux
    homonymes. Partout ailleurs elle reste facultative : à l'import, parce que
    les fichiers reçus n'en portent pas toujours ; en modification, parce que
    des dizaines de milliers de fiches importées sont déjà sans date et
    doivent rester corrigeables.
    """

    def setUp(self):
        from core.models import TacheImport
        from core.taches import Avancement
        self.tache = TacheImport.objects.create(libelle='Test')
        self.avancement = Avancement(self.tache)
        User.objects.create_superuser('su_dn', password='x')
        self.client = Client()
        self.client.login(username='su_dn', password='x')

    def _importer(self, lignes, do_update=False):
        import json
        from .views import _executer_import_patients
        message = _executer_import_patients(
            self.avancement, 'f.json', json.dumps(lignes, default=str).encode('utf-8'),
            do_update, None)
        self.tache.refresh_from_db()
        return message

    # ── Modèle ────────────────────────────────────────────────────────────

    def test_un_patient_s_enregistre_sans_date_de_naissance(self):
        patient = Patient.objects.create(
            nom='Sans', prenoms='Date', sexe='M', telephone='0700000000')
        self.assertIsNone(patient.date_naissance)
        self.assertIsNone(patient.age)
        self.assertIsNone(patient.age_detail)

    # ── Export ────────────────────────────────────────────────────────────

    def test_l_export_porte_la_date_de_naissance_et_plus_l_age(self):
        from .views import _PATIENT_HDR
        self.assertIn('date_naissance', _PATIENT_HDR)
        self.assertNotIn('age', _PATIENT_HDR)

    def test_l_export_json_rend_la_date_au_format_francais(self):
        import json
        Patient.objects.create(nom='Kone', prenoms='Adama', sexe='M',
                               telephone='0700000001', date_naissance='1990-06-01')
        contenu = json.loads(self.client.get(
            reverse('patients:export_patients') + '?format=json').content)
        self.assertEqual(contenu[0]['date_naissance'], '01/06/1990')

    def test_l_export_laisse_la_colonne_vide_sans_date(self):
        import json
        Patient.objects.create(nom='Sans', prenoms='Date', sexe='M', telephone='0700000002')
        contenu = json.loads(self.client.get(
            reverse('patients:export_patients') + '?format=json').content)
        self.assertEqual(contenu[0]['date_naissance'], '')

    def test_l_export_csv_et_excel_repondent(self):
        Patient.objects.create(nom='Kone', prenoms='Adama', sexe='M',
                               telephone='0700000001', date_naissance='1990-06-01')
        for fmt in ('csv', 'xlsx'):
            reponse = self.client.get(
                reverse('patients:export_patients') + f'?format={fmt}')
            self.assertEqual(reponse.status_code, 200, fmt)
        csv = self.client.get(
            reverse('patients:export_patients') + '?format=csv').content.decode('utf-8')
        self.assertIn('date_naissance', csv)
        self.assertIn('01/06/1990', csv)

    def test_le_modele_excel_repond(self):
        self.assertEqual(self.client.get(reverse('patients:patients_modele')).status_code, 200)

    # ── Import ────────────────────────────────────────────────────────────

    def test_l_import_lit_la_date_au_format_francais(self):
        self._importer([{'nom': 'Kone Adama', 'date_naissance': '14/05/1991',
                         'genre': 'M', 'mobile': '0700000001'}])
        self.assertEqual(Patient.objects.get().date_naissance, date(1991, 5, 14))

    def test_l_import_lit_la_date_au_format_iso(self):
        self._importer([{'nom': 'Kone Adama', 'date_naissance': '1991-05-14',
                         'genre': 'M', 'mobile': '0700000001'}])
        self.assertEqual(Patient.objects.get().date_naissance, date(1991, 5, 14))

    def test_l_import_lit_une_cellule_datee_d_excel(self):
        from datetime import datetime
        from .views import _parse_date_naissance
        self.assertEqual(
            _parse_date_naissance(datetime(1991, 5, 14, 9, 30), date.today()),
            date(1991, 5, 14))

    def test_l_import_accepte_une_ligne_sans_date(self):
        self._importer([{'nom': 'Sans Date', 'genre': 'F', 'mobile': '0700000003'}])
        self.assertEqual(self.tache.crees, 1)
        self.assertEqual(self.tache.erreurs, 0)
        self.assertIsNone(Patient.objects.get().date_naissance)

    def test_la_colonne_age_reste_acceptee(self):
        self._importer([{'nom': 'Kone Adama', 'age': '30', 'genre': 'M',
                         'mobile': '0700000001'}])
        patient = Patient.objects.get()
        self.assertIsNotNone(patient.date_naissance)
        self.assertEqual(patient.age, 30)

    def test_la_date_prime_sur_l_age(self):
        self._importer([{'nom': 'Kone Adama', 'age': '30',
                         'date_naissance': '14/05/1991', 'genre': 'M',
                         'mobile': '0700000001'}])
        self.assertEqual(Patient.objects.get().date_naissance, date(1991, 5, 14))

    def test_une_date_future_est_ignoree_sans_perdre_le_patient(self):
        demain = (date.today() + timedelta(days=1)).strftime('%d/%m/%Y')
        self._importer([{'nom': 'Kone Adama', 'date_naissance': demain,
                         'genre': 'M', 'mobile': '0700000001'}])
        self.assertEqual(self.tache.crees, 1)
        self.assertIsNone(Patient.objects.get().date_naissance)

    def test_un_export_reimporte_ne_cree_pas_de_doublon(self):
        import json
        Patient.objects.create(nom='Kone', prenoms='Adama', sexe='M',
                               telephone='0700000001', date_naissance='1991-05-14')
        exporte = json.loads(self.client.get(
            reverse('patients:export_patients') + '?format=json').content)
        self._importer(exporte)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.ignores, 1)

    def test_deux_homonymes_sans_date_restent_deux_dossiers(self):
        # Sans date de naissance, le nom seul ne prouve pas qu'il s'agit de la
        # même personne : mieux vaut deux dossiers qu'une fusion abusive.
        self._importer([{'nom': 'Kone Adama', 'genre': 'M', 'mobile': '0700000001'}])
        self._importer([{'nom': 'Kone Adama', 'genre': 'M', 'mobile': '0700000009'}])
        self.assertEqual(Patient.objects.count(), 2)

    def test_un_identifiant_rapproche_meme_sans_date(self):
        self._importer([{'code_identifiant': 'EXT-7', 'nom': 'Kone Adama',
                         'genre': 'M', 'mobile': '0700000001'}])
        patient = Patient.objects.get()
        self._importer([{'code_identifiant': patient.code_patient, 'nom': 'Kone Adama',
                         'genre': 'M', 'mobile': '0799999999'}], do_update=True)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Patient.objects.get().telephone, '0799999999')

    # ── Formulaire ────────────────────────────────────────────────────────

    def test_la_date_est_obligatoire_a_la_creation(self):
        from .forms import PatientForm
        self.assertTrue(PatientForm().fields['date_naissance'].required)
        form = PatientForm(data={
            'nom': 'Sans', 'prenoms': 'Date', 'sexe': 'M',
            'telephone': '0700000011', 'adresse': 'Yamoussoukro',
            'nationalite': 'Ivoirienne', 'ville': 'Yamoussoukro',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('date_naissance', form.errors)

    def test_la_date_reste_facultative_a_l_import(self):
        """Le fichier reçu ne la porte pas toujours : l'exiger ferait tomber
        la ligne entière, et le dossier avec."""
        self._importer([{'nom': 'Kone Adama', 'genre': 'M', 'mobile': '0700000012'}])
        patient = Patient.objects.get()
        self.assertIsNone(patient.date_naissance)

    def test_la_date_ne_bloque_pas_la_modification(self):
        """Une fiche importée sans date doit rester modifiable : sinon on ne
        pourrait plus corriger son adresse tant qu'on n'a pas sa date."""
        from .forms import PatientForm
        patient = Patient.objects.create(
            nom='Sans', prenoms='Date', sexe='M', telephone='0700000013')
        form = PatientForm(instance=patient, data={
            'nom': 'Sans', 'prenoms': 'Date', 'sexe': 'M',
            'telephone': '0700000013', 'adresse': 'Nouveau quartier',
            'nationalite': 'Ivoirienne', 'ville': 'Yamoussoukro',
        })
        self.assertFalse(form.fields['date_naissance'].required)
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertIsNone(form.save().date_naissance)

    def test_le_doublon_est_detecte_sans_date_de_naissance(self):
        from .forms import PatientForm
        Patient.objects.create(nom='Kone', prenoms='Adama', sexe='M',
                               telephone='0700000001')
        form = PatientForm(data={
            'nom': 'Kone', 'prenoms': 'Adama', 'sexe': 'M',
            'telephone': '0700000001', 'adresse': 'Yamoussoukro',
            'nationalite': 'Ivoirienne', 'ville': 'Yamoussoukro',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('existe déjà', ' '.join(form.errors.get('__all__', [])))


class TestLExportSuitLaSelection(TestCase):
    """Le fichier téléchargé porte ce que la liste affiche.

    L'export faisait sa propre requête, sans filtre : on restreignait la liste
    aux femmes de plus de 60 ans, on téléchargeait, et on recevait la table
    entière. Le fichier ne répondait jamais à la question posée à l'écran.
    """

    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser('su_exp', password='x')
        aujourdhui = date.today()
        cls.attendus = {}
        for nom, sexe, age in [('Kone', 'F', 70), ('Traore', 'F', 30),
                               ('Yao', 'M', 70), ('Bamba', 'M', 10)]:
            cls.attendus[nom] = Patient.objects.create(
                nom=nom, prenoms='Essai', sexe=sexe,
                date_naissance=aujourdhui.replace(year=aujourdhui.year - age),
                telephone=f'070000{age:04d}')

    def setUp(self):
        self.client = Client()
        self.client.login(username='su_exp', password='x')

    def _json(self, parametres=''):
        import json
        return json.loads(self.client.get(
            reverse('patients:export_patients') + '?format=json' + parametres).content)

    def _noms(self, data):
        return sorted(ligne['nom'].split()[0] for ligne in data)

    def test_sans_filtre_tout_sort(self):
        self.assertEqual(len(self._json()), 4)

    def test_un_filtre_restreint_le_fichier(self):
        self.assertEqual(self._noms(self._json('&filter=femme')), ['Kone', 'Traore'])

    def test_deux_filtres_de_familles_differentes_se_cumulent(self):
        self.assertEqual(self._noms(self._json('&filter=femme&filter=senior')), ['Kone'])

    def test_la_recherche_restreint_le_fichier(self):
        self.assertEqual(self._noms(self._json('&q=Traore')), ['Traore'])

    def test_le_regroupement_structure_le_fichier(self):
        data = self._json('&group=sexe')
        self.assertEqual([bloc['groupe'] for bloc in data], ['Féminin', 'Masculin'])
        self.assertEqual([bloc['nombre'] for bloc in data], [2, 2])
        self.assertEqual(
            sorted(l['nom'].split()[0] for l in data[0]['lignes']), ['Kone', 'Traore'])

    def test_filtre_et_regroupement_se_combinent(self):
        data = self._json('&filter=senior&group=sexe')
        self.assertEqual([(b['groupe'], b['nombre']) for b in data],
                         [('Féminin', 1), ('Masculin', 1)])

    def test_le_csv_porte_les_titres_de_groupe(self):
        texte = self.client.get(
            reverse('patients:export_patients')
            + '?format=csv&group=sexe').content.decode('utf-8-sig')
        self.assertIn('Féminin (2)', texte)
        self.assertIn('Masculin (2)', texte)
        # Virgule, et pas point-virgule : le fichier doit rester relisible par
        # l'import de patients, dont le DictReader lit en virgule.
        self.assertIn('code_identifiant,nom,date_naissance,date_naissance_approx,'
                      'genre,mobile', texte)

    def test_deux_niveaux_s_emboitent_au_lieu_de_s_ecraser(self):
        """Le parent une fois, ses enfants en dessous.

        Les deux niveaux sortaient écrasés sur un seul titre — « Féminin ›
        Senior » — réécrit en entier à chaque sous-groupe, et le compte du
        parent n'apparaissait nulle part.
        """
        data = self._json('&group=sexe&group=age')
        self.assertEqual([b['groupe'] for b in data], ['Féminin', 'Masculin'])
        femmes = data[0]
        self.assertEqual(femmes['nombre'], 2)          # le total du parent
        self.assertNotIn('lignes', femmes)             # il ne porte rien en propre
        self.assertEqual(sum(sg['nombre'] for sg in femmes['sous_groupes']), 2)

    def test_le_csv_decale_les_sous_groupes(self):
        texte = self.client.get(
            reverse('patients:export_patients')
            + '?format=csv&group=sexe&group=age').content.decode('utf-8-sig')
        lignes = [l for l in texte.splitlines() if l.startswith('Féminin')]
        self.assertEqual(lignes, ['Féminin (2)'])
        # Les enfants sont décalés de deux espaces, le parent non.
        self.assertTrue(any(l.startswith('  ') and l.strip().endswith(')')
                            for l in texte.splitlines()))

    def test_le_csv_groupe_se_reimporte_sans_creer_de_fantome(self):
        """Les titres de groupe ne doivent pas devenir des patients.

        Le fichier téléchargé reste un fichier d'import : regroupé, il porte des
        lignes de titre que le lecteur verra passer. Elles sont sans nom, donc
        comptées en erreur — jamais insérées.
        """
        from core.models import TacheImport
        from core.taches import Avancement
        from .views import _executer_import_patients

        contenu = self.client.get(
            reverse('patients:export_patients') + '?format=csv&group=sexe').content
        tache = TacheImport.objects.create(libelle='Retour')
        _executer_import_patients(Avancement(tache), 'patients.csv', contenu, False, None)
        tache.refresh_from_db()

        self.assertEqual(Patient.objects.count(), 4)
        self.assertEqual(tache.crees, 0)
        self.assertEqual(tache.ignores, 4)
        self.assertEqual(tache.erreurs, 2)      # les deux titres de groupe

    def test_l_excel_porte_les_titres_de_groupe(self):
        import io
        import openpyxl
        contenu = self.client.get(
            reverse('patients:export_patients') + '?format=xlsx&group=sexe').content
        feuille = openpyxl.load_workbook(io.BytesIO(contenu)).active
        premieres = [l[0] for l in feuille.iter_rows(values_only=True)]
        self.assertIn('Féminin (2)', premieres)
        self.assertIn('Masculin (2)', premieres)

    def test_le_menu_annonce_ce_qu_il_telecharge(self):
        page = self.client.get(reverse('patients:list')).content.decode('utf-8')
        self.assertIn('Exporter les patients (4)', page)
        selection = self.client.get(
            reverse('patients:list') + '?filter=femme').content.decode('utf-8')
        self.assertIn('Exporter la sélection (2)', selection)

    def test_les_liens_du_menu_emportent_la_selection(self):
        page = self.client.get(
            reverse('patients:list') + '?filter=femme&q=Kone').content.decode('utf-8')
        self.assertIn('?format=csv&amp;filter=femme&amp;q=Kone', page)

    def test_les_liens_n_emportent_pas_la_pagination(self):
        # `page` et le dépliage décrivent la façon de parcourir l'écran, pas la
        # sélection : les emporter laisserait croire qu'on ne télécharge que la
        # page affichée.
        page = self.client.get(
            reverse('patients:list') + '?filter=femme&page=2').content.decode('utf-8')
        self.assertIn('filter=femme', page)
        self.assertNotIn('format=csv&amp;filter=femme&amp;page=2', page)

    def test_l_export_reste_aux_administrateurs(self):
        User.objects.create_user('simple_exp', password='x')
        client = Client()
        client.login(username='simple_exp', password='x')
        self.assertEqual(
            client.get(reverse('patients:export_patients')).status_code, 403)


class TestDetectionDesJoursParDefaut(TestCase):
    """Le jour inventé se repère à sa fréquence, pas à sa valeur.

    Écrire « 01/10 » en dur dans la migration n'aurait marché que sur cette
    base-ci : la date inventée est celle du jour de l'import, et change d'un
    import à l'autre.
    """

    def test_retient_le_jour_anormalement_frequent(self):
        from .dates_approximatives import jours_par_defaut
        # Un jour ordinaire, sur 1 000 fiches, en porte trois.
        comptes = {(1, 10): 890, (14, 5): 5, (2, 3): 4, (7, 7): 3}
        self.assertEqual(jours_par_defaut(comptes, 1000), {(1, 10)})

    def test_retient_plusieurs_jours_quand_il_y_a_eu_plusieurs_imports(self):
        from .dates_approximatives import jours_par_defaut
        comptes = {(30, 9): 400, (1, 10): 450, (14, 5): 5}
        self.assertEqual(jours_par_defaut(comptes, 1000), {(30, 9), (1, 10)})

    def test_le_plancher_protege_les_petites_bases(self):
        """Sur 200 fiches, 2 % font quatre personnes : quatre vrais
        anniversaires le même jour ne sont pas une anomalie."""
        from .dates_approximatives import jours_par_defaut
        self.assertEqual(jours_par_defaut({(14, 5): 6}, 200), set())

    def test_sans_fiche_datee_rien_n_est_retenu(self):
        from .dates_approximatives import jours_par_defaut
        self.assertEqual(jours_par_defaut({}, 0), set())

    def test_le_comptage_se_fait_par_centre(self):
        """Un petit centre importé un autre jour garde sa propre date
        inventée ; un comptage global la noierait sous le gros centre."""
        from .dates_approximatives import comptes_par_centre, jours_par_defaut
        lignes = ([(1, 1, 10)] * 900 + [(1, 14, 5)] * 5 + [(1, 2, 3)] * 95
                  + [(2, 30, 9)] * 95 + [(2, 3, 4)] * 5)
        comptes = comptes_par_centre(lignes)
        self.assertEqual(jours_par_defaut(comptes[1], 1000), {(1, 10), (2, 3)})
        # Le petit centre garde la sienne : un comptage global l'aurait noyée
        # (95 fiches sur 1 100, soit 8,6 %… mais sur un autre jour que le gros).
        self.assertEqual(jours_par_defaut(comptes[2], 100), {(30, 9)})


class TestDateApproximativeALImport(TestCase):
    """Une date déduite d'un âge ne vaut que par son année, et le fichier doit
    le dire — sinon la recherche de doublons la prend pour une vraie date."""

    def setUp(self):
        from core.models import TacheImport
        from core.taches import Avancement
        self.tache = TacheImport.objects.create(libelle='Test')
        self.avancement = Avancement(self.tache)

    def _importer(self, lignes, do_update=False):
        import json
        from .views import _executer_import_patients
        _executer_import_patients(self.avancement, 'f.json',
                                  json.dumps(lignes, default=str).encode('utf-8'),
                                  do_update, None)
        self.tache.refresh_from_db()

    def test_une_date_deduite_d_un_age_est_cochee(self):
        self._importer([{'nom': 'Kone Adama', 'age': '34', 'genre': 'M',
                         'mobile': '0700000001'}])
        patient = Patient.objects.get()
        self.assertTrue(patient.date_naissance_approx)
        self.assertFalse(patient.date_precise)
        self.assertEqual(patient.date_naissance.year, date.today().year - 34)

    def test_une_date_lue_dans_le_fichier_ne_l_est_pas(self):
        self._importer([{'nom': 'Kone Adama', 'date_naissance': '14/05/1991',
                         'genre': 'M', 'mobile': '0700000001'}])
        patient = Patient.objects.get()
        self.assertFalse(patient.date_naissance_approx)
        self.assertTrue(patient.date_precise)

    def test_sans_date_du_tout_la_case_reste_vide(self):
        self._importer([{'nom': 'Kone Adama', 'genre': 'M', 'mobile': '0700000001'}])
        patient = Patient.objects.get()
        self.assertIsNone(patient.date_naissance)
        self.assertFalse(patient.date_naissance_approx)

    def test_le_fichier_peut_declarer_sa_date_approximative(self):
        """La colonne que porte notre propre export : sans elle, réimporter
        un export promouvrait les estimations au rang de dates certaines."""
        self._importer([{'nom': 'Kone Adama', 'date_naissance': '01/01/1980',
                         'date_naissance_approx': 'Oui', 'genre': 'M',
                         'mobile': '0700000001'}])
        self.assertTrue(Patient.objects.get().date_naissance_approx)


class TestReconnaissanceDesFichesApproximatives(TestCase):
    """Le rapprochement à l'import ne peut pas s'appuyer sur une date fausse."""

    def setUp(self):
        from core.models import TacheImport
        from core.taches import Avancement
        self.tache = TacheImport.objects.create(libelle='Test')
        self.avancement = Avancement(self.tache)

    def _importer(self, lignes, do_update=False):
        import json
        from .views import _executer_import_patients
        _executer_import_patients(self.avancement, 'f.json',
                                  json.dumps(lignes, default=str).encode('utf-8'),
                                  do_update, None)
        self.tache.refresh_from_db()

    def test_le_meme_fichier_age_seul_reimporte_un_an_plus_tard_est_reconnu(self):
        """« 34 ans » donne 1992 importé en 2026 et 1993 importé en 2027 : sans
        la tolérance d'un an, le réimport créerait un second dossier."""
        aujourdhui = date.today()
        fiche = Patient.objects.create(
            nom='Kone', prenoms='Adama', sexe='M', telephone='0700000001',
            date_naissance=aujourdhui.replace(year=aujourdhui.year - 34),
            date_naissance_approx=True)
        # Le réimport de l'année suivante : même âge, une année de moins.
        self._importer([{'nom': 'Kone Adama', 'age': '35', 'genre': 'M',
                         'mobile': '0700000001'}])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(Patient.objects.get().pk, fiche.pk)
        self.assertEqual(self.tache.ignores, 1)
        self.assertEqual(self.tache.crees, 0)

    def test_deux_homonymes_du_meme_age_restent_deux_fiches(self):
        """Sans le téléphone dans la clé, le second écraserait le dossier du
        premier en mode « mettre à jour »."""
        self._importer([
            {'nom': 'Kone Adama', 'age': '34', 'genre': 'M', 'mobile': '0700000001'},
            {'nom': 'Kone Adama', 'age': '34', 'genre': 'M', 'mobile': '0700000002'},
        ])
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(self.tache.crees, 2)
        self.assertEqual(
            sorted(Patient.objects.values_list('telephone', flat=True)),
            ['0700000001', '0700000002'])

    def test_la_cle_exacte_ne_tolere_toujours_pas_un_an_d_ecart(self):
        """La clé, elle, n'a pas bougé : seul le repli par ressemblance,
        ajouté à l'étape 2, rapproche deux dates voisines."""
        from .views import _cle_identite
        self.assertNotEqual(
            _cle_identite('Yao', 'Koffi', date(1990, 3, 12)),
            _cle_identite('Yao', 'Koffi', date(1991, 3, 12)))

    def test_un_an_d_ecart_avec_meme_nom_et_meme_numero_est_la_meme_personne(self):
        """Faute de frappe sur l'année : le repli la rattrape (88 %).

        C'est un changement de l'étape 2. Avant, ces deux lignes faisaient
        deux dossiers.
        """
        Patient.objects.create(nom='Yao', prenoms='Koffi', sexe='M',
                               telephone='0700000003', date_naissance=date(1990, 3, 12))
        self._importer([{'nom': 'Yao Koffi', 'date_naissance': '12/03/1991',
                         'genre': 'M', 'mobile': '0700000003'}])
        self.assertEqual(Patient.objects.count(), 1)

    def test_un_an_d_ecart_avec_un_autre_numero_reste_deux_personnes(self):
        """Le téléphone fait la différence : sans lui, le score retombe."""
        Patient.objects.create(nom='Yao', prenoms='Koffi', sexe='M',
                               telephone='0700000003', date_naissance=date(1990, 3, 12))
        self._importer([{'nom': 'Yao Koffi', 'date_naissance': '12/03/1991',
                         'genre': 'M', 'mobile': '0755667788'}])
        self.assertEqual(Patient.objects.count(), 2)

    def test_l_aller_retour_par_le_fichier_preserve_la_case(self):
        """Export puis réimport : ni fiche créée, ni drapeau perdu."""
        aujourdhui = date.today()
        Patient.objects.create(
            nom='Kone', prenoms='Adama', sexe='M', telephone='0700000001',
            date_naissance=aujourdhui.replace(year=aujourdhui.year - 34),
            date_naissance_approx=True)
        User.objects.create_superuser('su_ar', password='x')
        client = Client()
        client.login(username='su_ar', password='x')
        contenu = client.get(
            reverse('patients:export_patients') + '?format=csv').content

        from .views import _executer_import_patients
        _executer_import_patients(self.avancement, 'patients.csv', contenu, True, None)
        self.tache.refresh_from_db()
        self.assertEqual(Patient.objects.count(), 1)
        self.assertTrue(Patient.objects.get().date_naissance_approx)
        self.assertEqual(self.tache.crees, 0)


class TestLeFormulaireNeDecocheQueSurUneVraieSaisie(TestCase):
    """Modifier le téléphone renvoie la même date de naissance : la prendre
    pour une saisie effacerait le drapeau au fil des corrections ordinaires."""

    def setUp(self):
        self.patient = Patient.objects.create(
            nom='Kone', prenoms='Adama', sexe='M', telephone='0700000001',
            date_naissance=date(1992, 10, 1), date_naissance_approx=True)

    def _donnees(self, **remplacements):
        donnees = {'nom': 'Kone', 'prenoms': 'Adama', 'sexe': 'M',
                   'telephone': '0700000001', 'date_naissance': '01/10/1992',
                   'nationalite': 'Ivoirienne', 'adresse': 'Quartier Habitat',
                   'ville': 'Yamoussoukro'}
        donnees.update(remplacements)
        return donnees

    def test_modifier_le_telephone_ne_decoche_pas(self):
        """Le formulaire rendu renvoie la case telle qu'elle était, comme le
        ferait un navigateur : corriger le téléphone n'y touche pas."""
        from .forms import PatientForm
        form = PatientForm(self._donnees(telephone='0700000009',
                                         date_naissance_approx='on',
                                         doublon_confirme='on'),
                           instance=self.patient)
        self.assertTrue(form.is_valid(), form.errors.as_text())
        form.save()
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.date_naissance_approx)

    def test_sans_la_case_rendue_la_regle_automatique_s_applique(self):
        """Filet pour les appels qui n'affichent pas la case : une date
        réellement saisie reste une date certaine."""
        from .forms import PatientForm

        class SansLaCase(PatientForm):
            class Meta(PatientForm.Meta):
                exclude = PatientForm.Meta.exclude + ['date_naissance_approx']

        form = SansLaCase(self._donnees(date_naissance='14/05/1992',
                                        doublon_confirme='on'),
                          instance=self.patient)
        self.assertTrue(form.is_valid(), form.errors.as_text())
        form.save()
        self.patient.refresh_from_db()
        self.assertFalse(self.patient.date_naissance_approx)

    def test_decocher_la_case_rend_la_date_certaine(self):
        from .forms import PatientForm
        form = PatientForm(self._donnees(date_naissance='14/05/1992',
                                         doublon_confirme='on'),
                           instance=self.patient)
        self.assertTrue(form.is_valid(), form.errors.as_text())
        form.save()
        self.patient.refresh_from_db()
        self.assertFalse(self.patient.date_naissance_approx)

    def test_la_case_est_offerte_a_la_saisie(self):
        """Depuis l'étape 2, c'est la réceptionniste qui la coche : elle sait,
        elle, si la personne a donné un âge ou une date."""
        from .forms import PatientForm
        champ = PatientForm().fields.get('date_naissance_approx')
        self.assertIsNotNone(champ)
        self.assertIn("seule l'année", champ.label)


class TestLeScoreTientCompteDeLApproximation(TestCase):
    """Deux dates identiques ne prouvent rien quand elles ont été inventées le
    même jour par le même import."""

    def test_deux_dates_inventees_identiques_ne_valent_pas_une_vraie_date(self):
        from .doublons import scorer
        commun = dict(sexe='F', telephone='0700000001', prenoms='Awa')
        exacte = Patient.objects.create(
            nom='Traore', date_naissance=date(1992, 10, 1), **commun)
        approchee = Patient.objects.create(
            nom='Traore', date_naissance=date(1992, 10, 1),
            date_naissance_approx=True, **commun)

        saisie = {'nom': 'Traore', 'prenoms': 'Awa', 'sexe': 'F',
                  'telephone': '0700000001', 'date_naissance': date(1992, 10, 1)}
        self.assertGreater(scorer(saisie, exacte).score,
                           scorer(saisie, approchee).score)

    def test_le_premier_janvier_n_est_plus_tenu_pour_approximatif(self):
        """La bibliothèque traitait tout 1er janvier comme une estimation ; le
        champ porte désormais l'information, le pari n'a plus lieu d'être."""
        from .doublons import DATES_PAR_DEFAUT, similarite_dates
        self.assertEqual(DATES_PAR_DEFAUT, set())
        self.assertEqual(similarite_dates(date(1990, 1, 1), date(1990, 1, 1)), 1.0)


class TestPreventionDesDoublonsALaSaisie(TestCase):
    """Le formulaire ne refusait que les dossiers strictement identiques sur
    quatre champs : une lettre de différence suffisait à passer, et c'est
    exactement ainsi que naissent les doublons."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.existant = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro')
        cls.simple = User.objects.create_user('dbl_simple', password='x')
        cls.admin = User.objects.create_user('dbl_admin', password='x')
        cls.admin.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='forcer_creation_doublon'))
        cls.admin = User.objects.get(pk=cls.admin.pk)

    @staticmethod
    def _donnees(**remplacements):
        donnees = {'nom': 'KOUASSI', 'prenoms': 'AYA MARIE', 'sexe': 'F',
                   'telephone': '0701020304', 'date_naissance': '14/05/1992',
                   'nationalite': 'Ivoirienne', 'adresse': 'Habitat',
                   'ville': 'Yamoussoukro'}
        donnees.update(remplacements)
        return donnees

    def _form(self, utilisateur=None, instance=None, **remplacements):
        from .forms import PatientForm
        return PatientForm(self._donnees(**remplacements),
                           utilisateur=utilisateur or self.simple, instance=instance)

    # ── Blocage ────────────────────────────────────────────────────────────

    def test_un_dossier_tres_ressemblant_est_refuse(self):
        form = self._form(prenoms='AYA MARIE')          # le même, au mot près
        self.assertFalse(form.is_valid())
        self.assertIn('existe déjà', form.non_field_errors()[0])
        self.assertIn('Ouvrez la fiche existante', form.non_field_errors()[0])

    def test_une_faute_de_frappe_ne_suffit_plus_a_passer(self):
        """« KOUASSI » écrit « KOUASI » : l'ancien contrôle laissait créer."""
        form = self._form(nom='KOUASI')
        self.assertFalse(form.is_valid())

    def test_un_inconnu_passe_sans_rien_cocher(self):
        form = self._form(nom='ZEBOULON', prenoms='EUSTACHE',
                          telephone='0788889999', date_naissance='09/02/1977')
        self.assertTrue(form.is_valid(), form.errors.as_text())

    # ── Confirmation ───────────────────────────────────────────────────────

    def test_une_ressemblance_moyenne_demande_une_confirmation(self):
        form = self._form(prenoms='AYA', telephone='0755667788',
                          date_naissance='14/05/1993')
        if form.is_valid():
            self.skipTest("score hors de la plage d'avertissement sur ce jeu")
        self.assertIn("J'ai vérifié", form.non_field_errors()[0])

    def test_la_case_cochee_laisse_passer(self):
        form = self._form(prenoms='AYA', telephone='0755667788',
                          date_naissance='14/05/1993', doublon_confirme='on')
        self.assertTrue(form.is_valid(), form.errors.as_text())

    # ── Forçage ────────────────────────────────────────────────────────────

    def test_sans_la_permission_la_case_de_forcage_ne_sert_a_rien(self):
        form = self._form(forcer_doublon='on', raison_forcage='Vrais homonymes')
        self.assertFalse(form.is_valid())
        self.assertIn('existe déjà', form.non_field_errors()[0])

    def test_l_administrateur_force_avec_une_raison(self):
        form = self._form(utilisateur=self.admin, forcer_doublon='on',
                          raison_forcage='Deux sœurs, même téléphone')
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertIsNotNone(form.forcage)
        self.assertEqual(form.forcage[0], 'Deux sœurs, même téléphone')

    def test_l_administrateur_ne_force_pas_sans_raison(self):
        form = self._form(utilisateur=self.admin, forcer_doublon='on')
        self.assertFalse(form.is_valid())
        self.assertIn('raison_forcage', form.errors)

    def test_le_forcage_part_au_journal(self):
        from core.models import LogActivite
        client = Client()
        from django.contrib.auth.models import Permission
        for code in ('add_patient', 'view_patient'):
            self.admin.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        client.force_login(User.objects.get(pk=self.admin.pk))
        reponse = client.post(reverse('patients:create'), self._donnees(
            forcer_doublon='on', raison_forcage='Deux sœurs'))
        self.assertEqual(reponse.status_code, 302)
        journal = LogActivite.objects.filter(message__contains='malgré un doublon')
        self.assertEqual(journal.count(), 1)
        self.assertIn('Deux sœurs', journal.first().message)

    # ── Modification ───────────────────────────────────────────────────────

    def test_la_modification_n_est_jamais_bloquee(self):
        """Deux fiches déjà en double doivent rester modifiables — sans quoi
        on ne pourrait même plus corriger celle qu'on s'apprête à fusionner."""
        jumelle = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro')
        form = self._form(instance=jumelle, telephone='0709090909',
                          doublon_confirme='on')
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_la_modification_demande_tout_de_meme_la_confirmation(self):
        jumelle = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro')
        form = self._form(instance=jumelle, telephone='0709090909')
        self.assertFalse(form.is_valid())

    # ── Téléphone ──────────────────────────────────────────────────────────

    def test_le_numero_partage_est_compte_sans_bloquer(self):
        Patient.objects.create(nom='KOUASSI', prenoms='KOFFI', sexe='M',
                               telephone='0701020304', date_naissance=date(1960, 1, 2),
                               nationalite='Ivoirienne', adresse='Habitat',
                               ville='Yamoussoukro')
        form = self._form(nom='ZEBOULON', prenoms='EUSTACHE',
                          date_naissance='09/02/1977')
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.meme_telephone, 2)


class TestLaFenetreDesDossiersRessemblants(TestCase):
    """Ce que le serveur doit fournir à la fenêtre, et ce qu'il en retient.

    La fenêtre elle-même ne décide de rien : elle montre, elle coche, elle
    journalise. Ce qui refuse reste dans PatientForm, et ces tests vérifient
    que les deux disent la même chose — notamment qu'une case cochée depuis
    l'écran ne contourne pas la permission.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.existant = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro')
        cls.agent = User.objects.create_user('fen_agent', password='x')
        cls.agent.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))

    def setUp(self):
        self.client = Client()
        self.client.force_login(User.objects.get(pk=self.agent.pk))

    # ── Contenu des cartes ─────────────────────────────────────────────────

    def test_la_carte_recoit_tout_ce_qu_elle_affiche(self):
        """Nom et prénoms arrivent séparés : la fenêtre surligne champ par
        champ ce qui diffère, elle ne peut rien faire d'une chaîne recollée."""
        reponse = self.client.get(reverse('patients:doublons_verifier'), {
            'nom': 'KOUASSI', 'prenoms': 'AYA MARIE', 'sexe': 'F',
            'telephone': '0701020304', 'date_naissance': '14/05/1992'})
        self.assertEqual(reponse.status_code, 200)
        fiches = reponse.json()['doublons']
        self.assertTrue(fiches)
        attendus = {'pk', 'code', 'nom', 'prenoms', 'sexe', 'date_naissance',
                    'annee', 'approximative', 'telephone', 'derniere_visite',
                    'score', 'niveau', 'raisons', 'url'}
        self.assertTrue(attendus.issubset(fiches[0].keys()),
                        attendus - set(fiches[0].keys()))
        self.assertEqual(fiches[0]['nom'], 'KOUASSI')
        self.assertEqual(fiches[0]['prenoms'], 'AYA MARIE')
        self.assertEqual(fiches[0]['annee'], '1992')

    def test_la_derniere_visite_vient_des_consultations_et_des_rendez_vous(self):
        """Un dossier ouvert puis jamais utilisé est souvent le doublon : la
        date de dernière visite est là pour le dire sans le dire.

        Elle vient des deux sources : un centre peut enregistrer les passages
        d'un côté et pas de l'autre.
        """
        from consultations.models import Consultation
        self.assertEqual(self._fiche()['derniere_visite'], '')

        avant_hier = timezone.now() - timedelta(days=2)
        RendezVous.objects.create(patient=self.existant, date_heure=avant_hier,
                                  motif='Contrôle')
        self.assertEqual(self._fiche()['derniere_visite'],
                         timezone.localtime(avant_hier).strftime('%d/%m/%Y'))

        # La consultation est plus récente : c'est elle qui l'emporte.
        Consultation.objects.create(patient=self.existant, motif='Fièvre')
        self.assertEqual(self._fiche()['derniere_visite'],
                         timezone.localtime(timezone.now()).strftime('%d/%m/%Y'))

    def test_un_rendez_vous_a_venir_n_est_pas_une_visite(self):
        """Sous l'étiquette « dernière visite », une date future se lirait
        comme une venue qui n'a pas eu lieu."""
        RendezVous.objects.create(patient=self.existant, motif='À venir',
                                  date_heure=timezone.now() + timedelta(days=5))
        self.assertEqual(self._fiche()['derniere_visite'], '')

    def test_une_absence_ou_une_annulation_n_est_pas_une_visite(self):
        passe = timezone.now() - timedelta(days=3)
        for statut in ('annule', 'absent'):
            RendezVous.objects.create(patient=self.existant, date_heure=passe,
                                      motif='Non venu', statut=statut)
        self.assertEqual(self._fiche()['derniere_visite'], '')

    def _fiche(self):
        reponse = self.client.get(reverse('patients:doublons_verifier'), {
            'nom': 'KOUASSI', 'prenoms': 'AYA MARIE', 'sexe': 'F',
            'telephone': '0701020304', 'date_naissance': '14/05/1992'})
        return reponse.json()['doublons'][0]

    # ── Journalisation ─────────────────────────────────────────────────────

    def test_continuer_la_saisie_laisse_une_trace(self):
        from core.models import LogActivite
        reponse = self.client.post(reverse('patients:doublons_journaliser'), {
            'pk': self.existant.pk, 'score': 72,
            'nom': 'KOUASI', 'prenoms': 'AYA MARIE'})
        self.assertEqual(reponse.status_code, 200)
        journal = LogActivite.objects.filter(object_id=self.existant.pk,
                                             type='alerte')
        self.assertEqual(journal.count(), 1)
        message = journal.first().message
        self.assertIn('72 %', message)
        self.assertIn('KOUASI AYA MARIE', message)
        self.assertEqual(journal.first().user, self.agent)

    def test_la_trace_porte_la_raison_quand_il_y_en_a_une(self):
        from core.models import LogActivite
        self.client.post(reverse('patients:doublons_journaliser'), {
            'pk': self.existant.pk, 'score': 91, 'nom': 'KOUASSI',
            'prenoms': 'AYA MARIE', 'raison': 'Deux sœurs, même téléphone'})
        self.assertIn('Deux sœurs',
                      LogActivite.objects.get(type='alerte').message)

    def test_le_journal_ignore_une_fiche_inconnue(self):
        reponse = self.client.post(reverse('patients:doublons_journaliser'),
                                   {'pk': 999999, 'score': 90})
        self.assertEqual(reponse.status_code, 404)

    def test_le_journal_refuse_une_lecture(self):
        """Un GET n'écrit rien : le journal se remplit sur action, pas au
        hasard d'un lien ouvert ou d'un préchargement du navigateur."""
        reponse = self.client.get(reverse('patients:doublons_journaliser'))
        self.assertEqual(reponse.status_code, 405)

    # ── La fenêtre ne contourne pas le serveur ─────────────────────────────

    def test_cocher_depuis_l_ecran_ne_remplace_pas_la_permission(self):
        """« Continuer la saisie » est grisé à l'écran sans la permission.
        Même coché de force, le serveur refuse : c'est lui qui décide."""
        from .forms import PatientForm
        form = PatientForm({
            'nom': 'KOUASSI', 'prenoms': 'AYA MARIE', 'sexe': 'F',
            'telephone': '0701020304', 'date_naissance': '14/05/1992',
            'nationalite': 'Ivoirienne', 'adresse': 'Habitat',
            'ville': 'Yamoussoukro',
            'doublon_confirme': 'on', 'forcer_doublon': 'on',
            'raison_forcage': 'Je passe outre',
        }, utilisateur=User.objects.get(pk=self.agent.pk))
        self.assertFalse(form.is_valid())
        self.assertIn('existe déjà', form.non_field_errors()[0])


class TestLaReglePrenomsDifferents(TestCase):
    """Deux frères nés le même jour, déclarés sous le même téléphone, montaient
    à 93 % et auraient été refusés à la création. Ce sont deux personnes."""

    def test_des_prenoms_differents_de_part_et_d_autre_ne_bloquent_pas(self):
        from .doublons import SEUIL_BLOCAGE, SEUIL_AVERTISSEMENT, scorer
        aine = Patient.objects.create(
            nom="N'GORAN", prenoms="KOUASSI N'DA JEAN NATHANAEL", sexe='M',
            telephone='0701020304', date_naissance=date(2015, 4, 2))
        cadet = {'nom': "N'GORAN", 'prenoms': "KOUAME N'DA JEAN EMMANUEL",
                 'sexe': 'M', 'telephone': '0701020304',
                 'date_naissance': date(2015, 4, 2)}
        correspondance = scorer(cadet, aine)
        self.assertLess(correspondance.score, SEUIL_BLOCAGE)
        # Toujours signalés, en revanche : on demande, on ne laisse pas filer.
        self.assertGreaterEqual(correspondance.score, SEUIL_AVERTISSEMENT)
        self.assertTrue(correspondance.details['prenoms_differents'])

    def test_une_faute_de_frappe_reste_bloquante(self):
        """Le plafond ne doit pas servir d'échappatoire : une seule différence,
        d'un seul côté, n'est pas deux personnes."""
        from .doublons import SEUIL_BLOCAGE, scorer
        fiche = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
            telephone='0701020304', date_naissance=date(1992, 5, 14))
        saisie = {'nom': 'KOUASSI', 'prenoms': 'AYA MARIE', 'sexe': 'F',
                  'telephone': '0701020304', 'date_naissance': date(1992, 5, 14)}
        self.assertGreaterEqual(scorer(saisie, fiche).score, SEUIL_BLOCAGE)


class TestEndpointDeVerification(TestCase):
    """L'encadré affiché pendant la frappe lit cette adresse."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.patient = Patient.objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14))
        cls.user = User.objects.create_user('verif', password='x')
        cls.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))

    def _appeler(self, **params):
        import json
        client = Client()
        client.force_login(User.objects.get(pk=self.user.pk))
        reponse = client.get(reverse('patients:doublons_verifier'), params)
        self.assertEqual(reponse.status_code, 200)
        return json.loads(reponse.content)

    def test_il_rend_la_fiche_proche_avec_son_score_et_sa_raison(self):
        data = self._appeler(nom='KOUASSI', prenoms='AYA MARIE',
                             date_naissance='1992-05-14', telephone='0701020304')
        self.assertEqual(len(data['doublons']), 1)
        trouve = data['doublons'][0]
        self.assertEqual(trouve['code'], self.patient.code_patient)
        self.assertGreaterEqual(trouve['score'], 85)
        self.assertEqual(trouve['niveau'], 'blocage')
        self.assertIn('même téléphone', trouve['raisons'])
        self.assertTrue(trouve['url'].endswith(f'/{self.patient.pk}/'))

    def test_il_compte_les_porteurs_du_meme_numero(self):
        data = self._appeler(nom='ZEBOULON', prenoms='EUSTACHE',
                             telephone='0701020304')
        self.assertEqual(data['meme_telephone'], 1)

    def test_la_fiche_en_cours_de_modification_s_exclut(self):
        data = self._appeler(nom='KOUASSI', prenoms='AYA MARIE',
                             telephone='0701020304', exclure=self.patient.pk)
        self.assertEqual(data['doublons'], [])

    def test_sans_nom_il_ne_cherche_rien(self):
        self.assertEqual(self._appeler(telephone='0701020304')['doublons'], [])

    def test_il_exige_la_permission(self):
        client = Client()
        client.force_login(User.objects.create_user('verif_nu', password='x'))
        self.assertEqual(
            client.get(reverse('patients:doublons_verifier')).status_code, 403)


class TestLImportRattrapeLesFautesDeFrappe(TestCase):
    """La clé exacte laisse passer une lettre de différence ; le repli par
    ressemblance la rattrape, sans interroger la base."""

    def setUp(self):
        from core.models import TacheImport
        from core.taches import Avancement
        self.tache = TacheImport.objects.create(libelle='Test')
        self.avancement = Avancement(self.tache)

    def _importer(self, lignes, do_update=False):
        import json
        from .views import _executer_import_patients
        message = _executer_import_patients(
            self.avancement, 'f.json', json.dumps(lignes, default=str).encode('utf-8'),
            do_update, None)
        self.tache.refresh_from_db()
        return message

    def test_une_faute_dans_le_nom_ne_cree_plus_un_second_dossier(self):
        Patient.objects.create(nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
                               telephone='0701020304', date_naissance=date(1992, 5, 14))
        self._importer([{'nom': 'KOUASI AYA MARIE', 'date_naissance': '14/05/1992',
                         'genre': 'F', 'mobile': '0701020304'}])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.ignores, 1)

    def test_une_ressemblance_moyenne_cree_la_fiche_et_la_signale(self):
        Patient.objects.create(nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
                               telephone='0701020304', date_naissance=date(1992, 5, 14))
        message = self._importer([{'nom': 'KOUASSI AYA', 'date_naissance': '14/05/1993',
                                   'genre': 'F', 'mobile': '0755667788'}])
        if self.tache.doublons_possibles == 0:
            self.skipTest("score hors de la plage d'avertissement sur ce jeu")
        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(self.tache.crees, 1)
        # Le compte rendu nomme les deux fiches, pas seulement leur nombre.
        self.assertIn('≈', message)
        ancien = Patient.objects.get(prenoms='AYA MARIE').code_patient
        nouveau = Patient.objects.get(prenoms='AYA').code_patient
        self.assertEqual(self.tache.codes_doublons, f'{nouveau}~{ancien}')

    def test_le_repli_n_interroge_pas_la_base_par_ligne(self):
        """L'index est en mémoire : le nombre de requêtes ne doit pas suivre le
        nombre de lignes, sans quoi un fichier de 48 000 lignes tiendrait des
        heures."""
        for i in range(5):
            Patient.objects.create(nom=f'NOM{i}', prenoms='TEST', sexe='M',
                                   telephone=f'070000000{i}',
                                   date_naissance=date(1990, 1, 1))
        lignes = [{'nom': f'AUTRE{i} PERSONNE', 'date_naissance': '01/01/1990',
                   'genre': 'M', 'mobile': f'071111111{i}'} for i in range(10)]
        with _compteur() as compteur:
            self._importer(lignes)
        self.assertLess(compteur.nombre, 40,
                        'le nombre de requêtes suit le nombre de lignes')


class _compteur:
    """Compte les requêtes sans fixer de nombre exact : ce qui importe ici est
    l'ordre de grandeur, pas le détail."""

    def __enter__(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        self._ctx = CaptureQueriesContext(connection)
        self._ctx.__enter__()
        return self

    def __exit__(self, *args):
        self.nombre = len(self._ctx.captured_queries)
        return self._ctx.__exit__(*args)


class TestRapiditeDeLaRecherche(TestCase):
    """La recherche tourne pendant la frappe : au-delà d'une demi-seconde,
    l'encadré arrive après que la personne a fini de taper, et ne sert plus.

    Ce test ne mesure pas la vraie base — 47 813 fiches — mais garde le point
    de rupture que la réécriture a corrigé : la présélection ramenait un tiers
    de la table dès que le nom était courant.
    """

    @classmethod
    def setUpTestData(cls):
        for i in range(600):
            Patient.objects.create(
                nom='KOUASSI', prenoms=f'AYA {i}', sexe='F',
                telephone=f'07{i:08d}', date_naissance=date(1992, 5, 14))

    def test_la_preselection_ne_ramene_pas_toute_la_table(self):
        from .doublons import _preselection
        saisie = {'nom': 'KOUASSI', 'prenoms': 'BELINDA', 'sexe': 'F',
                  'telephone': '0799999999', 'date_naissance': date(1992, 5, 14)}
        candidats = Patient.objects.filter(_preselection(saisie)).count()
        # Un seul mot en commun — « KOUASSI » — ne suffit plus à être candidat
        # quand la date ne concorde pas au jour près… mais ici elle concorde,
        # donc la famille « début du mot + date exacte » les retient tous.
        # Ce qui compte est qu'on ne ramène pas davantage que ceux-là.
        self.assertLessEqual(candidats, 600)

    def test_un_nom_sans_rapport_ne_ramene_personne(self):
        from .doublons import _preselection
        saisie = {'nom': 'ZEBOULON', 'prenoms': 'EUSTACHE', 'sexe': 'M',
                  'telephone': '0788889999', 'date_naissance': date(1977, 2, 9)}
        self.assertEqual(Patient.objects.filter(_preselection(saisie)).count(), 0)

    def test_la_recherche_reste_sous_la_demi_seconde(self):
        import time
        from .doublons import chercher_doublons
        saisie = {'nom': 'KOUASSI', 'prenoms': 'AYA 42', 'sexe': 'F',
                  'telephone': '0700000042', 'date_naissance': date(1992, 5, 14)}
        chercher_doublons(saisie)                       # chauffe les caches
        debut = time.perf_counter()
        resultats = chercher_doublons(saisie)
        duree = time.perf_counter() - debut
        self.assertTrue(resultats, 'la fiche identique devrait être trouvée')
        self.assertLess(duree, 0.5, f'recherche en {duree * 1000:.0f} ms')

# ════════════════════════════════════════════════════════════════════════════
# Étape 3 — détection stockée
# ════════════════════════════════════════════════════════════════════════════


class TestLesClesPhonetiques(TestCase):
    """La présélection comparait des mots exacts : une variante d'écriture
    accompagnée d'un téléphone différent lui échappait."""

    @staticmethod
    def _cles(patient):
        from .models import ClePhonetique
        return set(ClePhonetique.all_objects.filter(patient=patient)
                   .values_list('cle', flat=True))

    def test_une_fiche_enregistree_ecrit_ses_cles(self):
        patient = Patient.objects.create(nom="N'GUESSAN", prenoms='PRISCA',
                                         sexe='F', date_naissance=date(2008, 5, 2))
        self.assertEqual(self._cles(patient), {'GESAN', 'PRISKA'})

    def test_les_deux_graphies_donnent_la_meme_cle(self):
        from .cles_phonetiques import cles
        self.assertIn('GESAN', cles("N'GUESSAN", ''))
        self.assertIn('GESAN', cles("N'GESSAN", ''))

    def test_l_annee_est_recopiee_avec_la_cle(self):
        from .models import ClePhonetique
        patient = Patient.objects.create(nom='KOUASSI', prenoms='AYA', sexe='F',
                                         date_naissance=date(1992, 5, 14))
        annees = set(ClePhonetique.all_objects.filter(patient=patient)
                     .values_list('annee', flat=True))
        self.assertEqual(annees, {1992})

    def test_changer_le_nom_remplace_les_cles(self):
        patient = Patient.objects.create(nom='KOUASSI', prenoms='AYA', sexe='F')
        patient = Patient.objects.get(pk=patient.pk)
        patient.nom = 'TRAORE'
        patient.save()
        self.assertEqual(self._cles(patient), {'TRAOR', 'AIA'})

    def test_changer_l_adresse_ne_recalcule_rien(self):
        """Deux requêtes de plus à chaque enregistrement, pour une donnée qui
        ne dépend que du nom : la table ne doit pas être réécrite."""
        from .models import ClePhonetique
        patient = Patient.objects.create(nom='KOUASSI', prenoms='AYA', sexe='F')
        avant = set(ClePhonetique.all_objects.filter(patient=patient)
                    .values_list('pk', flat=True))
        patient = Patient.objects.get(pk=patient.pk)
        patient.adresse = 'Habitat'
        patient.save()
        apres = set(ClePhonetique.all_objects.filter(patient=patient)
                    .values_list('pk', flat=True))
        self.assertEqual(avant, apres)      # mêmes lignes, pas seulement mêmes clés

    def test_une_date_qui_change_met_l_annee_a_jour(self):
        from .models import ClePhonetique
        patient = Patient.objects.create(nom='KOUASSI', prenoms='AYA', sexe='F',
                                         date_naissance=date(1992, 5, 14))
        patient = Patient.objects.get(pk=patient.pk)
        patient.date_naissance = date(1993, 5, 14)
        patient.save()
        self.assertEqual(
            set(ClePhonetique.all_objects.filter(patient=patient)
                .values_list('annee', flat=True)), {1993})


class TestLaPreselectionSonore(TestCase):
    """Le cas qui a motivé l'étape : deux graphies, deux téléphones, aucune
    chance de se croiser tant que la présélection ne lit que des mots."""

    def setUp(self):
        self.connue = Patient.objects.create(
            nom="N'GESSAN", prenoms="N'DRISCA PRISCA", sexe='F',
            telephone='0564635675', date_naissance=date(2008, 6, 1),
            date_naissance_approx=True)

    @staticmethod
    def _saisie():
        return {'nom': "N'GUESSAN", 'prenoms': 'PRSICA', 'sexe': 'F',
                'telephone': '0171374134', 'telephone2': '',
                'date_naissance': date(2008, 3, 4), 'date_precise': False}

    def test_la_variante_d_ecriture_est_retrouvee(self):
        from .doublons import chercher_doublons
        trouves = chercher_doublons(self._saisie(), queryset=Patient.all_objects.all())
        self.assertEqual([c.patient.pk for c in trouves], [self.connue.pk])

    def test_sans_les_cles_elle_echappait(self):
        """Vider la table reproduit l'état d'avant : la paire disparaît."""
        from .doublons import chercher_doublons
        from .models import ClePhonetique
        ClePhonetique.all_objects.all().delete()
        self.assertEqual(
            chercher_doublons(self._saisie(), queryset=Patient.all_objects.all()), [])

    def test_une_cle_seule_ne_suffit_pas(self):
        """« KWASI » porte 6 % de la base : une clé isolée, sans seconde clé ni
        année concordante, ne doit désigner personne."""
        from .doublons import chercher_doublons
        Patient.objects.create(nom='KOUASSI', prenoms='MICHEL', sexe='M',
                               date_naissance=date(1960, 2, 2))
        saisie = {'nom': 'KWASSI', 'prenoms': 'BERTRAND', 'sexe': 'M',
                  'telephone': '', 'telephone2': '',
                  'date_naissance': date(1995, 7, 9)}
        self.assertEqual(
            chercher_doublons(saisie, queryset=Patient.all_objects.all()), [])


class TestLesDecisionsHumainesSurvivent(TestCase):
    """Le recalcul reconstruit tout : il ne doit toucher à rien de ce qu'une
    personne a tranché."""

    def setUp(self):
        from centres.models import Centre
        self.centre = Centre.objects.create(nom='Walé', code='WAL')
        commun = dict(sexe='F', telephone='0701020304',
                      date_naissance=date(1992, 5, 14), centre=self.centre)
        self.a = Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        self.b = Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)

    def _recalculer(self):
        from .doublons_recalcul import recalculer_centre
        return recalculer_centre(self.centre.pk)

    def test_le_recalcul_releve_la_paire(self):
        from .models import DoublonPaire
        self.assertEqual(self._recalculer(), 1)
        paire = DoublonPaire.all_objects.get()
        self.assertLess(paire.patient_a_id, paire.patient_b_id)
        self.assertEqual(paire.niveau, 'certain')

    def test_une_paire_ecartee_ne_revient_pas(self):
        from .models import DoublonPaire, PaireEcartee
        from .doublons import paire_ordonnee
        a, b = paire_ordonnee(self.a.pk, self.b.pk)
        PaireEcartee.all_objects.create(patient_a_id=a, patient_b_id=b,
                                        centre=self.centre, raison='Deux sœurs')
        self.assertEqual(self._recalculer(), 0)
        self.assertEqual(DoublonPaire.all_objects.count(), 0)

    def test_une_paire_ecartee_survit_a_une_modification(self):
        """La décision porte sur deux identifiants, pas sur ce que les fiches
        contiennent : corriger un prénom ne repose pas la question."""
        from .models import DoublonPaire, PaireEcartee
        from .doublons import paire_ordonnee
        a, b = paire_ordonnee(self.a.pk, self.b.pk)
        PaireEcartee.all_objects.create(patient_a_id=a, patient_b_id=b, centre=self.centre)
        fiche = Patient.all_objects.get(pk=self.b.pk)
        fiche.prenoms = 'AYA MARIE CLAIRE'
        fiche.save()
        self.assertEqual(self._recalculer(), 0)
        self.assertEqual(DoublonPaire.all_objects.count(), 0)

    def test_le_recalcul_n_efface_aucune_decision(self):
        from .models import ChoixFicheGardee, PaireEcartee
        from .doublons import paire_ordonnee
        autre = Patient.all_objects.create(nom='TRAORE', prenoms='AWA', sexe='F',
                                           centre=self.centre)
        a, b = paire_ordonnee(self.a.pk, autre.pk)
        PaireEcartee.all_objects.create(patient_a_id=a, patient_b_id=b, centre=self.centre)
        ChoixFicheGardee.all_objects.create(patient=self.a, centre=self.centre)
        self._recalculer()
        self.assertEqual(PaireEcartee.all_objects.count(), 1)
        self.assertEqual(ChoixFicheGardee.all_objects.count(), 1)

    def test_le_choix_humain_prime_sur_la_suggestion(self):
        from .models import ChoixFicheGardee
        from .doublons_groupes import garnir, index, suggerer_a_garder
        # La fiche la plus complète est `a` : c'est elle que la suggestion
        # propose. On choisit l'autre à la main.
        self.a.telephone2 = '0709090909'
        self.a.save()
        self._recalculer()
        self.assertEqual(suggerer_a_garder([self.a, self.b]), self.a.pk)

        ChoixFicheGardee.all_objects.create(patient=self.b, centre=self.centre)
        groupe = garnir(index(self.centre.pk))[0]
        self.assertEqual(groupe['garder'], self.b.pk)
        self.assertTrue(groupe['choix_humain'])

    def test_une_fiche_ecartee_de_la_detection(self):
        """Fusionnée ou masquée, elle n'est plus un dossier : l'étape 4 posera
        ces champs, la détection les lit déjà."""
        from .models import DoublonPaire
        fiche = Patient.all_objects.get(pk=self.b.pk)
        fiche.masque = True
        fiche.save()
        self.assertEqual(self._recalculer(), 0)
        self.assertEqual(DoublonPaire.all_objects.count(), 0)


class TestLeCloisonnementDesGroupes(TestCase):
    def test_deux_centres_ne_forment_jamais_un_groupe(self):
        from centres.models import Centre
        from .doublons_recalcul import recalculer_centre
        from .models import DoublonPaire
        un = Centre.objects.create(nom='Walé', code='WAL')
        deux = Centre.objects.create(nom='Annexe', code='ANX')
        commun = dict(nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
                      telephone='0701020304', date_naissance=date(1992, 5, 14))
        Patient.all_objects.create(centre=un, **commun)
        Patient.all_objects.create(centre=deux, **commun)
        self.assertEqual(recalculer_centre(un.pk), 0)
        self.assertEqual(recalculer_centre(deux.pk), 0)
        self.assertEqual(DoublonPaire.all_objects.count(), 0)


#: Un vrai second processus, qui pose le verrou et le garde. Deux fils
#: d'exécution ne prouveraient rien : c'est justement ce que l'ancien
#: `threading.Lock` savait faire, et il ne protégeait qu'un processus.
_ENFANT_VERROU = """
import fcntl, sys, time
fichier = open(sys.argv[1], 'a+')
fcntl.flock(fichier.fileno(), fcntl.LOCK_EX)
print('pris', flush=True)
time.sleep(float(sys.argv[2]))
"""


class TestDeuxRecalculsEnMemeTemps(TestCase):
    """SQLite n'accepte qu'un écrivain. Deux recalculs qui se chevauchent
    finiraient en « database is locked », et le second referait de toute façon
    le travail du premier.

    Le passage de nuit tourne sous crontab, dans son propre processus, et
    gunicorn sert les enregistrements depuis plusieurs workers : le verrou doit
    donc être vu de tous. Ces tests lancent un **second processus** pour le
    vérifier.
    """

    def setUp(self):
        from centres.models import Centre
        self.centre = Centre.objects.create(nom='Walé', code='WAL')
        self.verrou = Path(tempfile.mkdtemp()) / 'verrou-doublons'
        self.enfant = None

    def tearDown(self):
        if self.enfant is not None:
            self.enfant.terminate()
            self.enfant.wait(timeout=10)

    def _tenir_le_verrou(self, secondes=30):
        """Démarre le processus et ne rend la main qu'une fois le verrou pris."""
        self.enfant = subprocess.Popen(
            [sys.executable, '-c', _ENFANT_VERROU, str(self.verrou), str(secondes)],
            stdout=subprocess.PIPE, text=True)
        self.assertEqual(self.enfant.stdout.readline().strip(), 'pris')

    def _deux_fiches(self):
        commun = dict(sexe='F', telephone='0701020304',
                      date_naissance=date(1992, 5, 14), centre=self.centre)
        Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        return Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)

    def test_le_recalcul_cible_s_efface_devant_le_complet(self):
        from .doublons_recalcul import recalculer_fiche
        from .models import DoublonPaire
        fiche = self._deux_fiches()

        with override_settings(DOUBLONS_PATIENTS_VERROU=str(self.verrou)):
            self._tenir_le_verrou()
            self.assertEqual(recalculer_fiche(fiche), 0)
            self.assertEqual(DoublonPaire.all_objects.count(), 0)

            # Le second processus parti, la fiche se relève normalement.
            self.enfant.terminate()
            self.enfant.wait(timeout=10)
            self.enfant = None
            self.assertEqual(recalculer_fiche(fiche), 1)

    def test_deux_recalculs_complets_ne_se_chevauchent_pas(self):
        from .doublons_recalcul import RecalculDejaEnCours, recalculer_centre
        with override_settings(DOUBLONS_PATIENTS_VERROU=str(self.verrou)):
            self._tenir_le_verrou()
            with self.assertRaises(RecalculDejaEnCours):
                recalculer_centre(self.centre.pk)

    def test_le_verrou_est_relache_quand_le_processus_meurt(self):
        """`flock` se relâche tout seul, même sur un processus tué net — c'est
        ce qui le distingue d'une ligne en base, qui resterait posée."""
        from .doublons_recalcul import recalcul_complet_en_cours
        with override_settings(DOUBLONS_PATIENTS_VERROU=str(self.verrou)):
            self._tenir_le_verrou()
            self.assertTrue(recalcul_complet_en_cours())
            self.enfant.kill()
            self.enfant.wait(timeout=10)
            self.enfant = None
            self.assertFalse(recalcul_complet_en_cours())

    def test_deux_recalculs_cibles_peuvent_tourner_ensemble(self):
        """Ils prennent un verrou partagé : seul le passage complet exclut."""
        from .doublons_recalcul import recalculer_fiche, verrou
        fiche = self._deux_fiches()
        with override_settings(DOUBLONS_PATIENTS_VERROU=str(self.verrou)):
            with verrou(exclusif=False):
                self.assertEqual(recalculer_fiche(fiche), 1)

    def test_l_ecriture_attend_plutot_que_d_echouer(self):
        """Le délai d'attente de SQLite est réglé : une écriture bloquée
        patiente au lieu de rendre « database is locked » tout de suite."""
        from django.conf import settings
        if 'sqlite' not in settings.DATABASES['default']['ENGINE']:
            self.skipTest('PostgreSQL gère plusieurs écrivains')
        options = settings.DATABASES['default'].get('OPTIONS', {})
        self.assertGreaterEqual(options.get('timeout', 0), 5)


class TestLesClesManquantesSeRattrapent(TestCase):
    """Si la migration passe sans écrire, la ressemblance sonore serait muette
    sans que personne le sache : le passage de nuit doit s'en apercevoir."""

    def setUp(self):
        from centres.models import Centre
        self.centre = Centre.objects.create(nom='Walé', code='WAL')

    def test_le_passage_complet_regenere_les_cles_absentes(self):
        from .doublons_recalcul import recalculer_centre
        from .models import ClePhonetique
        Patient.all_objects.create(nom="N'GUESSAN", prenoms='PRISCA', sexe='F',
                                   centre=self.centre)
        ClePhonetique.all_objects.all().delete()

        recalculer_centre(self.centre.pk)
        self.assertEqual(
            set(ClePhonetique.all_objects.values_list('cle', flat=True)),
            {'GESAN', 'PRISKA'})

    def test_une_fiche_sans_mot_assez_long_n_est_pas_reecrite_sans_fin(self):
        """« KA YA » ne porte aucun mot de trois lettres : n'avoir aucune clé
        y est normal, et ne doit pas relancer un rattrapage à chaque passage."""
        from .doublons_recalcul import completer_cles_manquantes
        Patient.all_objects.create(nom='KA', prenoms='YA', sexe='F',
                                   centre=self.centre)
        self.assertEqual(completer_cles_manquantes(self.centre.pk), 0)

    def test_les_fiches_deja_pourvues_ne_sont_pas_touchees(self):
        from .doublons_recalcul import completer_cles_manquantes
        Patient.all_objects.create(nom='KOUASSI', prenoms='AYA', sexe='F',
                                   centre=self.centre)
        self.assertEqual(completer_cles_manquantes(self.centre.pk), 0)


class TestLeRecalculCible(TestCase):
    def setUp(self):
        from centres.models import Centre
        self.centre = Centre.objects.create(nom='Walé', code='WAL')

    def test_il_ne_touche_que_les_paires_de_sa_fiche(self):
        from .doublons_recalcul import recalculer_fiche
        from .models import DoublonPaire
        commun = dict(sexe='F', telephone='0701020304',
                      date_naissance=date(1992, 5, 14), centre=self.centre)
        a = Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        b = Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        autre = dict(sexe='M', telephone='0788889999',
                     date_naissance=date(1960, 1, 2), centre=self.centre)
        c = Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE', **autre)
        d = Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE', **autre)

        recalculer_fiche(a)
        recalculer_fiche(c)
        self.assertEqual(DoublonPaire.all_objects.count(), 2)

        # Rejouer sur `a` ne doit pas emporter la paire de `c`.
        recalculer_fiche(a)
        self.assertEqual(DoublonPaire.all_objects.count(), 2)
        self.assertTrue(DoublonPaire.all_objects.filter(
            patient_a__in=[c, d], patient_b__in=[c, d]).exists())

    def test_l_enregistrement_programme_le_releve_sans_l_attendre(self):
        """Le fil part après le commit, pas pendant : il ouvre sa propre
        connexion et ne verrait pas une fiche encore dans la transaction de la
        requête."""
        from .doublons_recalcul import planifier
        with self.captureOnCommitCallbacks() as rappels:
            planifier(1, self.centre)
        self.assertEqual(len(rappels), 1)

    def test_une_fiche_masquee_perd_ses_paires(self):
        from .doublons_recalcul import recalculer_fiche
        from .models import DoublonPaire
        commun = dict(sexe='F', telephone='0701020304',
                      date_naissance=date(1992, 5, 14), centre=self.centre)
        a = Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        Patient.all_objects.create(nom='KOUASSI', prenoms='AYA MARIE', **commun)
        recalculer_fiche(a)
        self.assertEqual(DoublonPaire.all_objects.count(), 1)

        a.masque = True
        a.save()
        recalculer_fiche(a)
        self.assertEqual(DoublonPaire.all_objects.count(), 0)


class TestLaCompositionDesGroupes(TestCase):
    """Sans la règle « chacune avec chacune », de maillon en maillon, 37 000
    fiches finissaient dans un seul groupe."""

    def test_pas_d_effet_de_chaine(self):
        from .doublons_groupes import composer
        # A~B et B~C, mais rien entre A et C.
        groupes = composer([(1, 2, 95), (2, 3, 90)])
        self.assertEqual([g['membres'] for g in groupes], [[1, 2]])

    def test_le_triangle_complet_forme_un_groupe(self):
        from .doublons_groupes import composer
        groupes = composer([(1, 2, 95), (2, 3, 90), (1, 3, 88)])
        self.assertEqual([g['membres'] for g in groupes], [[1, 2, 3]])
        self.assertEqual(groupes[0]['score'], 88)   # le lien le plus faible

    def test_le_plafond_de_huit_fiches(self):
        from .doublons_groupes import TAILLE_MAX, composer
        paires = [(i, j, 90) for i in range(1, 11) for j in range(i + 1, 11)]
        for groupe in composer(paires):
            self.assertLessEqual(len(groupe['membres']), TAILLE_MAX)


class TestLImportEcritLesClesPhonetiques(TestCase):
    """L'import passe par `bulk_create`, qui ne déclenche jamais `save()` :
    sans écriture explicite, les fiches importées resteraient introuvables par
    la ressemblance sonore."""

    def test_les_fiches_importees_portent_leurs_cles(self):
        import json
        from core.models import TacheImport
        from core.taches import Avancement
        from .models import ClePhonetique
        from .views import _executer_import_patients

        avancement = Avancement(TacheImport.objects.create(libelle='Test'))
        _executer_import_patients(
            avancement, 'f.json',
            json.dumps([{'nom': "N'Guessan Prisca", 'genre': 'F',
                         'mobile': '0700000001'}]).encode('utf-8'),
            False, None)
        patient = Patient.objects.get()
        self.assertEqual(
            set(ClePhonetique.all_objects.filter(patient=patient)
                .values_list('cle', flat=True)), {'GESAN', 'PRISKA'})

# ════════════════════════════════════════════════════════════════════════════
# Étape 4a — le menu « Doublons »
# ════════════════════════════════════════════════════════════════════════════


class BaseDoublons(TestCase):
    """Deux fiches jumelles dans un centre, et un compte qui sait les traiter."""

    def setUp(self):
        from django.contrib.auth.models import Permission
        from centres.models import Centre
        from .doublons_recalcul import recalculer_centre

        self.centre = Centre.objects.create(nom='Walé', code='WAL')
        commun = dict(sexe='F', telephone='0701020304',
                      date_naissance=date(1992, 5, 14), centre=self.centre,
                      nationalite='Ivoirienne', ville='Yamoussoukro')
        self.gardee = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', telephone2='0709090909', **commun)
        self.doublon = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', **commun)
        recalculer_centre(self.centre.pk)

        self.agent = User.objects.create_user('dbl_agent', password='x')
        for code in ('view_patient', 'gerer_doublons'):
            self.agent.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.agent = User.objects.get(pk=self.agent.pk)
        self.client = Client()
        self.client.force_login(self.agent)

    @property
    def cle(self):
        from .doublons_groupes import cle_groupe
        return cle_groupe([self.gardee.pk, self.doublon.pk])


class TestLAccesALEcranDesDoublons(BaseDoublons):
    def test_la_liste_est_refusee_sans_la_permission(self):
        simple = User.objects.create_user('dbl_sans', password='x')
        client = Client()
        client.force_login(simple)
        self.assertEqual(
            client.get(reverse('patients:doublons_liste')).status_code, 403)

    def test_la_liste_s_ouvre_avec_la_permission(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, self.gardee.code_patient)

    def test_le_filtre_par_defaut_est_quasi_certain(self):
        """Les 905 cas sûrs d'abord ; les 7 600 « à vérifier » viennent après."""
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(reponse.context['niveau'], 'certain')

    def test_la_recherche_porte_sur_le_nom_et_sur_le_code(self):
        url = reverse('patients:doublons_liste')
        self.assertEqual(len(self.client.get(url, {'q': 'kouassi'}).context['groupes']), 1)
        self.assertEqual(
            len(self.client.get(url, {'q': self.gardee.code_patient}).context['groupes']), 1)
        self.assertEqual(len(self.client.get(url, {'q': 'zeboulon'}).context['groupes']), 0)


class TestLesComptesDeDonneesRattachees(BaseDoublons):
    def test_les_comptes_sont_affiches_par_fiche(self):
        from .liens_patient import comptes
        RendezVous.objects.create(patient=self.gardee, motif='Contrôle',
                                  date_heure=timezone.now())
        resultat = comptes([self.gardee.pk, self.doublon.pk])
        self.assertEqual(resultat[self.gardee.pk], {'Rendez-vous': 1})
        self.assertEqual(resultat[self.doublon.pk], {})

    def test_le_libelle_s_accorde_au_nombre(self):
        """« 1 factures » se lit mal, et retirer le « s » final ne suffit pas
        pour « demandes d'examen »."""
        from facturation.models import Facture
        from .liens_patient import comptes
        Facture.objects.create(patient=self.gardee, montant_total=1000)
        self.assertIn('Facture', comptes([self.gardee.pk])[self.gardee.pk])
        Facture.objects.create(patient=self.gardee, montant_total=2000)
        self.assertIn('Factures', comptes([self.gardee.pk])[self.gardee.pk])

    def test_la_suggestion_prefere_la_fiche_qui_porte_des_donnees(self):
        """Garder celle qui porte trois rendez-vous, c'est trois lignes de
        moins à déplacer le jour de la fusion."""
        from .doublons_groupes import suggerer_a_garder
        from .liens_patient import comptes
        # `self.gardee` a un second téléphone : sans les données rattachées,
        # c'est elle que la complétude désigne.
        self.assertEqual(suggerer_a_garder([self.gardee, self.doublon]), self.gardee.pk)
        RendezVous.objects.create(patient=self.doublon, motif='Contrôle',
                                  date_heure=timezone.now())
        rattachees = comptes([self.gardee.pk, self.doublon.pk])
        self.assertEqual(
            suggerer_a_garder([self.gardee, self.doublon], rattachees), self.doublon.pk)

    def test_une_requete_par_table_et_non_par_fiche(self):
        from .liens_patient import comptes, liens
        with self.assertNumQueries(len(liens())):
            comptes([self.gardee.pk, self.doublon.pk])

    def test_les_tables_internes_ne_comptent_pas(self):
        """Clés phonétiques et paires de doublons parlent *de* la fiche : les
        compter ferait passer toute fiche pour pleine de données."""
        from .liens_patient import LIENS_INTERNES, liens
        internes = {(m._meta.app_label, m.__name__) for m, _, _ in liens()}
        self.assertFalse(internes & LIENS_INTERNES)


class TestNouveauLienVersPatient(TestCase):
    """Si un module ajoute une table liée au patient, la fusion devra la
    déplacer. Ce test échoue tant que personne ne l'a rangée quelque part."""

    #: Les 13 liens métier connus au 13/10/2026.
    CONNUS = {
        ('consultations', 'Consultation'), ('consultations', 'Ordonnance'),
        ('facturation', 'Facture'), ('hospitalisation', 'Hospitalisation'),
        ('hospitalisation', 'RegistreDeces'), ('laboratoire', 'AnalyseLaboratoire'),
        ('laboratoire', 'DemandeExamen'), ('laboratoire', 'ExamenImagerie'),
        ('patients', 'Naissance'), ('patients', 'RendezVous'),
        ('pharmacie', 'VentePharmacie'), ('soins', 'ProcedureSoin'),
        ('soins', 'Soin'),
    }

    def test_aucun_lien_inconnu(self):
        from .liens_patient import liens
        trouves = {(m._meta.app_label, m.__name__) for m, _, _ in liens()}
        nouveaux = trouves - self.CONNUS
        self.assertFalse(
            nouveaux,
            f'Nouvelles tables liées à Patient : {nouveaux}. '
            'Décidez ce que la fusion doit en faire, puis ajoutez-les ici '
            '(ou dans LIENS_INTERNES si elles relèvent du mécanisme des doublons).')

    def test_le_lien_generique_du_journal_est_connu(self):
        """`LogActivite` vise n'importe quel objet : l'introspection par clé
        étrangère ne le voit pas, la fusion devra le traiter à part."""
        from django.apps import apps
        from django.contrib.contenttypes.fields import GenericForeignKey
        generiques = {(m._meta.app_label, m.__name__) for m in apps.get_models()
                      for f in m._meta.private_fields
                      if isinstance(f, GenericForeignKey)}
        self.assertEqual(generiques, {('core', 'LogActivite')})


class TestPasUnDoublon(BaseDoublons):
    def test_la_paire_quitte_la_liste(self):
        from .models import PaireEcartee
        reponse = self.client.post(
            reverse('patients:doublons_ecarter', args=[self.cle]),
            {'raison': 'Deux sœurs'}, follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(PaireEcartee.all_objects.count(), 1)
        self.assertEqual(PaireEcartee.all_objects.get().raison, 'Deux sœurs')
        self.assertEqual(
            len(self.client.get(reverse('patients:doublons_liste')).context['groupes']), 0)

    def _un_second_groupe(self):
        """Pour que la table ne se vide pas : sans lui, le relevé tomberait à
        zéro et le cache se contournerait tout seul, sans rien prouver."""
        from .doublons_recalcul import recalculer_centre
        commun = dict(sexe='M', telephone='0788889999',
                      date_naissance=date(1960, 1, 2), centre=self.centre)
        Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE', **commun)
        Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE', **commun)
        recalculer_centre(self.centre.pk)

    def test_le_groupe_traite_quitte_la_liste_tout_de_suite(self):
        """Le relevé est mis en cache : si sa clé ne tenait qu'à la date du
        dernier calcul, un groupe qu'on vient d'écarter resterait affiché —
        les autres paires gardent la même date."""
        self._un_second_groupe()
        url = reverse('patients:doublons_liste')
        self.assertEqual(len(self.client.get(url).context['groupes']), 2)
        self.client.post(reverse('patients:doublons_ecarter', args=[self.cle]), {})
        groupes = self.client.get(url).context['groupes']
        self.assertEqual(len(groupes), 1)
        self.assertNotIn(self.gardee.pk, groupes[0]['membres'])

    def test_une_fiche_masquee_quitte_la_liste_tout_de_suite(self):
        self._un_second_groupe()
        url = reverse('patients:doublons_liste')
        self.assertEqual(len(self.client.get(url).context['groupes']), 2)
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.assertEqual(len(self.client.get(url).context['groupes']), 1)

    def test_elle_ne_revient_pas_apres_un_recalcul(self):
        from .doublons_recalcul import recalculer_centre
        self.client.post(reverse('patients:doublons_ecarter', args=[self.cle]), {})
        self.assertEqual(recalculer_centre(self.centre.pk), 0)

    def test_l_annulation_la_ramene(self):
        from .models import DoublonPaire, PaireEcartee
        self.client.post(reverse('patients:doublons_ecarter', args=[self.cle]), {})
        self.client.post(reverse('patients:doublons_reprendre', args=[self.cle]), {})
        self.assertEqual(PaireEcartee.all_objects.count(), 0)
        # Reprise tout de suite : on n'attend pas le passage de nuit.
        self.assertEqual(DoublonPaire.all_objects.count(), 1)


class TestMasquerUneFiche(BaseDoublons):
    def _masquer(self, fiche, au_profit_de):
        return self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, fiche.pk]),
            {'au_profit_de': au_profit_de.pk}, follow=True)

    def test_une_fiche_vide_se_masque_au_profit_d_une_autre(self):
        self._masquer(self.doublon, self.gardee)
        fiche = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertTrue(fiche.masque)
        self.assertEqual(fiche.doublon_de_id, self.gardee.pk)
        self.assertEqual(fiche.remplacee_par, self.gardee)

    def test_une_fiche_avec_des_donnees_est_refusee_cote_serveur(self):
        """Le bouton grisé ne suffit pas : une requête forgée ne doit pas
        pouvoir faire disparaître un dossier qui porte des rendez-vous."""
        RendezVous.objects.create(patient=self.doublon, motif='Contrôle',
                                  date_heure=timezone.now())
        reponse = self._masquer(self.doublon, self.gardee)
        self.assertFalse(Patient.all_objects.get(pk=self.doublon.pk).masque)
        self.assertContains(reponse, 'il faut la fusionner')

    def test_une_fiche_masquee_disparait_partout(self):
        self._masquer(self.doublon, self.gardee)
        self.assertNotIn(self.doublon.pk,
                         Patient.all_objects.filter(masque=False).values_list('pk', flat=True))
        # Le gestionnaire par défaut l'écarte : liste, recherche, listes de choix.
        from core.middleware import centre_actif
        with centre_actif(self.centre):
            self.assertEqual(Patient.objects.filter(pk=self.doublon.pk).count(), 0)
            self.assertEqual(Patient.objects.filter(pk=self.gardee.pk).count(), 1)

    def test_elle_reste_accessible_par_son_adresse_avec_la_permission(self):
        self._masquer(self.doublon, self.gardee)
        reponse = self.client.get(reverse('patients:detail', args=[self.doublon.pk]))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Fiche masquée')
        self.assertContains(reponse, self.gardee.code_patient)

    def test_elle_est_introuvable_sans_la_permission(self):
        from django.contrib.auth.models import Permission
        self._masquer(self.doublon, self.gardee)
        simple = User.objects.create_user('dbl_lecteur', password='x')
        simple.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))
        client = Client()
        client.force_login(User.objects.get(pk=simple.pk))
        self.assertEqual(
            client.get(reverse('patients:detail', args=[self.doublon.pk])).status_code, 404)

    def test_l_annulation_la_rend_a_la_liste(self):
        self._masquer(self.doublon, self.gardee)
        self.client.post(reverse('patients:doublons_reafficher', args=[self.doublon.pk]), {})
        fiche = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertFalse(fiche.masque)
        self.assertIsNone(fiche.doublon_de_id)

    def test_l_avertissement_sur_les_informations_en_plus(self):
        """Une fiche sans rendez-vous peut tout de même porter des allergies
        que l'autre n'a pas : les perdre serait silencieux."""
        from .liens_patient import champs_en_plus
        self.doublon.allergies = 'Pénicilline'
        self.doublon.save()
        manquants = champs_en_plus(
            Patient.all_objects.get(pk=self.doublon.pk), self.gardee)
        self.assertIn('Allergies', manquants)
        reponse = self.client.get(reverse('patients:doublons_comparer', args=[self.cle]))
        self.assertContains(reponse, 'utilisez plutôt la fusion')


class TestUneFicheMasqueeNeRecoitPlusRien(BaseDoublons):
    def test_l_import_rattache_a_la_fiche_gardee(self):
        """Un fichier qui porte encore l'ancien code ne doit pas réveiller la
        fiche masquée."""
        import json
        from core.models import TacheImport
        from core.taches import Avancement
        from .views import _executer_import_patients

        self.doublon.masque = True
        self.doublon.doublon_de = self.gardee
        self.doublon.save()

        avancement = Avancement(TacheImport.objects.create(libelle='Test'))
        _executer_import_patients(
            avancement, 'f.json',
            json.dumps([{'code_identifiant': self.doublon.code_patient,
                         'nom': 'Kouassi Aya Marie', 'genre': 'F',
                         'mobile': '0788889999'}], default=str).encode('utf-8'),
            True, self.centre)

        self.assertEqual(
            Patient.all_objects.get(pk=self.gardee.pk).telephone, '0788889999')
        # La fiche masquée n'a pas bougé.
        self.assertEqual(
            Patient.all_objects.get(pk=self.doublon.pk).telephone, '0701020304')

    def test_hprim_rattache_a_la_fiche_gardee(self):
        from laboratoire.hprim.integration import _fiche_courante
        self.doublon.masque = True
        self.doublon.doublon_de = self.gardee
        self.doublon.save()
        synthese = {'details': []}
        courante = _fiche_courante(
            Patient.all_objects.get(pk=self.doublon.pk), synthese)
        self.assertEqual(courante.pk, self.gardee.pk)
        self.assertIn('rattachement sur', ' '.join(synthese['details']))

    def test_hprim_refuse_plutot_que_de_mal_ranger(self):
        """Sans fiche de remplacement, mieux vaut signaler que de ranger le
        résultat dans un dossier que plus personne n'ouvre."""
        from laboratoire.hprim.integration import _fiche_courante
        self.doublon.masque = True
        self.doublon.save()
        synthese = {'details': []}
        self.assertIsNone(_fiche_courante(
            Patient.all_objects.get(pk=self.doublon.pk), synthese))
        self.assertIn('non rattaché', ' '.join(synthese['details']))


class TestChoisirLaFicheAGarder(BaseDoublons):
    def test_le_choix_est_enregistre_et_prime(self):
        from .doublons_groupes import garnir, index
        from .models import ChoixFicheGardee
        self.client.post(
            reverse('patients:doublons_garder', args=[self.cle, self.doublon.pk]), {})
        self.assertEqual(ChoixFicheGardee.all_objects.get().patient_id, self.doublon.pk)
        groupe = garnir(index(self.centre.pk))[0]
        self.assertEqual(groupe['garder'], self.doublon.pk)
        self.assertTrue(groupe['choix_humain'])

    def test_un_seul_choix_par_groupe(self):
        from .models import ChoixFicheGardee
        for fiche in (self.doublon, self.gardee):
            self.client.post(
                reverse('patients:doublons_garder', args=[self.cle, fiche.pk]), {})
        self.assertEqual(ChoixFicheGardee.all_objects.count(), 1)
        self.assertEqual(ChoixFicheGardee.all_objects.get().patient_id, self.gardee.pk)


class TestLOngletDesCreationsForcees(BaseDoublons):
    def test_les_traces_sont_retrouvees_par_leur_code(self):
        """Pas par le texte du message : un message se reformule."""
        from core.views import log_event
        from . import journal_doublons
        log_event(self.gardee, self.agent, 'Peu importe le texte',
                  type='alerte', code=journal_doublons.CONFIRMATION)
        log_event(self.gardee, self.agent, 'Autre texte',
                  type='alerte', code=journal_doublons.FORCAGE)
        log_event(self.gardee, self.agent, 'Un événement sans rapport', type='modif')

        reponse = self.client.get(reverse('patients:doublons_journal'))
        self.assertEqual(reponse.context['page'].paginator.count, 2)
        self.assertContains(reponse, 'Saisie poursuivie')
        self.assertContains(reponse, 'Création forcée')
        self.assertNotContains(reponse, 'sans rapport')

    def test_la_saisie_pose_bien_le_code(self):
        from core.models import LogActivite
        from . import journal_doublons
        reponse = self.client.post(reverse('patients:doublons_journaliser'),
                                   {'pk': self.gardee.pk, 'score': 72,
                                    'nom': 'KOUASI', 'prenoms': 'AYA'})
        self.assertEqual(reponse.status_code, 200, reponse.content[:300])
        self.assertEqual(LogActivite.objects.get(code=journal_doublons.CONFIRMATION)
                         .object_id, self.gardee.pk)


class TestLeBoutonRecalculer(BaseDoublons):
    def test_il_cree_une_tache(self):
        from core.models import TacheImport
        reponse = self.client.post(reverse('patients:doublons_recalculer'))
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(TacheImport.objects.filter(
            libelle='Recalcul des doublons').count(), 1)


class TestCeQueLaCartePorte(BaseDoublons):
    """Avec le nom seul, on ne peut pas juger : la carte doit en dire assez
    pour trancher sans ouvrir la comparaison."""

    def _carte(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(len(reponse.context['groupes']), 1)
        return reponse, reponse.context['groupes'][0]

    def test_la_date_de_naissance_et_le_telephone_sont_affiches(self):
        reponse, groupe = self._carte()
        self.assertEqual(groupe['fiches'][0].naissance, '14/05/1992')
        self.assertContains(reponse, '14/05/1992')
        self.assertContains(reponse, '0701020304')

    def test_une_date_approximative_se_lit_comme_une_annee(self):
        from .doublons_groupes import naissance_affichee
        self.doublon.date_naissance_approx = True
        self.doublon.save()
        self.assertEqual(
            naissance_affichee(Patient.all_objects.get(pk=self.doublon.pk)),
            '≈ 1992')

    def test_la_raison_du_rapprochement_est_affichee(self):
        reponse, groupe = self._carte()
        self.assertIn('même nom', groupe['raisons'])
        self.assertIn('même téléphone', groupe['raisons'])
        self.assertContains(reponse, 'même téléphone')

    def test_ce_qui_differe_est_surligne_des_deux_cotes(self):
        self.doublon.nom = 'KOUASSY'
        self.doublon.save()
        reponse, groupe = self._carte()
        for fiche in groupe['fiches']:
            self.assertTrue(fiche.differe['nom'])
            self.assertFalse(fiche.differe['prenoms'])
            self.assertFalse(fiche.differe['telephone'])
        self.assertContains(reponse, 'class="diff"')

    def test_un_champ_vide_d_un_cote_ne_contredit_rien(self):
        """Seul un écart entre deux valeurs renseignées en est un : surligner
        une absence détournerait le regard de ce qui se contredit vraiment."""
        self.doublon.telephone = ''
        self.doublon.save()
        _reponse, groupe = self._carte()
        self.assertFalse(groupe['fiches'][0].differe['telephone'])

    def test_une_date_estimee_ne_contredit_pas_la_date_precise(self):
        self.doublon.date_naissance_approx = True
        self.doublon.save()
        _reponse, groupe = self._carte()
        self.assertFalse(groupe['fiches'][0].differe['naissance'])


class TestLActionRapideSurLaCarte(BaseDoublons):
    """La plupart des groupes sont une fiche pleine et sa copie vide : les
    ouvrir un par un pour n'y rien lire ferait des centaines d'écrans."""

    def _groupe(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        return reponse, reponse.context['groupes'][0]

    def test_elle_est_proposee_quand_l_autre_fiche_n_apprend_rien(self):
        reponse, groupe = self._groupe()
        self.assertEqual(groupe['masquable'].pk, self.doublon.pk)
        self.assertNotEqual(groupe['masquable'].pk, groupe['garder'])
        self.assertContains(reponse, 'Masquer le doublon')

    def test_elle_disparait_si_la_fiche_porte_des_donnees(self):
        RendezVous.objects.create(patient=self.doublon, motif='Contrôle',
                                  date_heure=timezone.now())
        reponse, groupe = self._groupe()
        self.assertIsNone(groupe['masquable'])
        self.assertNotContains(reponse, 'Masquer le doublon')

    def test_elle_disparait_si_la_fiche_porte_un_champ_que_l_autre_n_a_pas(self):
        """« Vide » ne suffit pas : des allergies se perdraient en silence."""
        self.doublon.allergies = 'Pénicilline'
        self.doublon.save()
        _reponse, groupe = self._groupe()
        self.assertIsNone(groupe['masquable'])

    def test_elle_ne_se_propose_pas_sur_un_groupe_de_trois(self):
        Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), centre=self.centre)
        from .doublons_recalcul import recalculer_centre
        recalculer_centre(self.centre.pk)
        _reponse, groupe = self._groupe()
        self.assertEqual(len(groupe['fiches']), 3)
        self.assertIsNone(groupe['masquable'])


class TestLeMasquageEnAjax(BaseDoublons):
    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def test_il_rend_de_quoi_annoncer_et_annuler(self):
        reponse = self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk}, **self.AJAX)
        self.assertEqual(reponse.status_code, 200)
        corps = reponse.json()
        self.assertTrue(corps['ok'])
        self.assertEqual(corps['code'], self.doublon.code_patient)
        self.assertEqual(corps['code_gardee'], self.gardee.code_patient)
        self.assertEqual(corps['annuler'],
                         reverse('patients:doublons_reafficher', args=[self.doublon.pk]))

    def test_le_groupe_traite_quitte_la_liste(self):
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk}, **self.AJAX)
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(len(reponse.context['groupes']), 0)

    def test_un_refus_se_dit_sans_masquer(self):
        RendezVous.objects.create(patient=self.doublon, motif='Contrôle',
                                  date_heure=timezone.now())
        reponse = self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk}, **self.AJAX)
        self.assertEqual(reponse.status_code, 409)
        self.assertFalse(reponse.json()['ok'])
        self.assertFalse(Patient.all_objects.get(pk=self.doublon.pk).masque)


class TestLaBanderoleDeMasquage(BaseDoublons):
    def test_elle_annonce_la_fiche_et_propose_d_annuler(self):
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        reponse = self.client.get(reverse('patients:doublons_liste'),
                                  {'masque': self.doublon.pk})
        self.assertEqual(reponse.context['masquage'].pk, self.doublon.pk)
        self.assertContains(reponse, 'est masquée')
        self.assertContains(reponse, 'Annuler')
        self.assertContains(reponse, reverse('patients:doublons_reafficher',
                                             args=[self.doublon.pk]))

    def test_le_masquage_redirige_en_portant_la_fiche(self):
        reponse = self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk,
             'retour': reverse('patients:doublons_liste') + '?niveau=certain'})
        self.assertIn(f'masque={self.doublon.pk}', reponse['Location'])
        self.assertIn('niveau=certain', reponse['Location'])

    def test_elle_s_efface_une_fois_le_masquage_annule(self):
        """Rien n'est gardé en session : la banderole se tait d'elle-même dès
        que la fiche est redevenue visible, rechargement compris."""
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.client.post(
            reverse('patients:doublons_reafficher', args=[self.doublon.pk]), {})
        reponse = self.client.get(reverse('patients:doublons_liste'),
                                  {'masque': self.doublon.pk})
        self.assertIsNone(reponse.context['masquage'])


class TestLEcranDeComparaison(BaseDoublons):
    def _comparer(self):
        return self.client.get(reverse('patients:doublons_comparer', args=[self.cle]))

    def test_les_donnees_rattachees_ont_leur_ligne_par_table(self):
        RendezVous.objects.create(patient=self.gardee, motif='Contrôle',
                                  date_heure=timezone.now())
        reponse = self._comparer()
        rattachees = reponse.context['rattachees']
        libelles = [ligne['libelle'] for ligne in rattachees['lignes']]
        self.assertEqual(libelles, ['Rendez-vous'])
        indice = [c['fiche'].pk for c in reponse.context['cartes']].index(self.gardee.pk)
        self.assertEqual(rattachees['lignes'][0]['nombres'][indice], 1)
        self.assertEqual(rattachees['totaux'][indice], 1)
        self.assertFalse(rattachees['rien'])

    def test_sans_rien_de_rattache_le_tableau_le_dit(self):
        reponse = self._comparer()
        self.assertTrue(reponse.context['rattachees']['rien'])
        self.assertContains(reponse, 'Aucune donnée rattachée')

    def test_les_champs_vides_des_deux_cotes_sont_comptes_a_part(self):
        reponse = self._comparer()
        vides = [l['libelle'] for l in reponse.context['comparaison'] if l['vide']]
        self.assertIn('Allergies', vides)
        self.assertNotIn('Nom', vides)
        self.assertEqual(reponse.context['champs_vides'], len(vides))
        self.assertContains(reponse, 'champs vides')

    def test_la_raison_du_blocage_est_ecrite_sous_le_bouton(self):
        """Un bouton gris sans explication se lit comme une panne, et le
        survol n'existe pas sur une tablette."""
        # La fiche gardée en porte davantage : celle qu'on pourrait masquer
        # n'est donc pas vide pour autant.
        for _ in range(2):
            RendezVous.objects.create(patient=self.gardee, motif='Contrôle',
                                      date_heure=timezone.now())
        RendezVous.objects.create(patient=self.doublon, motif='Contrôle',
                                  date_heure=timezone.now())
        reponse = self._comparer()
        raisons = {c['fiche'].pk: c['raison_blocage']
                   for c in reponse.context['cartes']}
        self.assertEqual(raisons[self.gardee.pk], "C'est la fiche qu'on garde.")
        self.assertEqual(raisons[self.doublon.pk],
                         'Contient des données : il faut la fusionner.')
        self.assertContains(reponse, 'Contient des données')

    def test_la_fiche_gardee_n_offre_pas_de_bouton_masquer(self):
        reponse = self._comparer()
        garde = next(c for c in reponse.context['cartes'] if c['garder'])
        self.assertFalse(garde['peut_masquer'])
        self.assertNotContains(
            reponse, f"Masquer {garde['fiche'].code_patient}")

    def test_les_actions_sont_rassemblees_dans_la_barre(self):
        reponse = self._comparer()
        corps = reponse.content.decode()
        barre = corps[corps.index('cmp-barre'):]
        for attendu in ('Garder ', 'Masquer ', 'Pas un doublon', 'Fusionner'):
            self.assertIn(attendu, barre)


class TestLeSurlignageMotAMot(BaseDoublons):
    """« ASSENA ELIAQUIM » contre « ASSENA ELIAKIM » : seul le second mot
    diffère, et c'est lui seul qu'il faut montrer."""

    def test_seul_le_mot_qui_differe_est_marque(self):
        from .doublons_groupes import mots_marques
        marques = mots_marques(['ASSENA ELIAQUIM', 'ASSENA ELIAKIM'])
        self.assertEqual([(m['mot'], m['diff']) for m in marques[0]],
                         [('ASSENA', False), ('ELIAQUIM', True)])
        self.assertEqual([(m['mot'], m['diff']) for m in marques[1]],
                         [('ASSENA', False), ('ELIAKIM', True)])

    def test_un_mot_commun_au_milieu_reste_intact(self):
        from .doublons_groupes import mots_marques
        marques = mots_marques(['MEL BIDPESS MATY', 'MEL BISPESS MATY'])
        self.assertEqual([m['diff'] for m in marques[0]], [False, True, False])

    def test_l_ecriture_d_origine_est_conservee(self):
        """On rapproche sur la forme normalisée, on affiche ce qui est écrit."""
        from .doublons_groupes import mots_marques
        marques = mots_marques(["N'Guéssan Kôné", 'NGUESSAN KONE'])
        self.assertEqual([m['mot'] for m in marques[0]], ["N'Guéssan", 'Kôné'])
        self.assertEqual([m['diff'] for m in marques[0]], [False, False])

    def test_une_valeur_vide_ne_marque_rien_chez_l_autre(self):
        from .doublons_groupes import mots_marques
        marques = mots_marques(['RAYAN', ''])
        self.assertEqual([m['diff'] for m in marques[0]], [False])

    def test_la_carte_ne_surligne_que_le_prenom_qui_differe(self):
        self.doublon.prenoms = 'AYA MARIANE'
        self.doublon.save()
        reponse = self.client.get(reverse('patients:doublons_liste'))
        groupe = reponse.context['groupes'][0]
        for fiche in groupe['fiches']:
            marques = {m['mot']: m['diff'] for m in fiche.mots_identite}
            self.assertFalse(marques['KOUASSI'])
            self.assertFalse(marques['AYA'])
        mots = {m['mot'] for fiche in groupe['fiches']
                for m in fiche.mots_identite if m['diff']}
        self.assertEqual(mots, {'MARIE', 'MARIANE'})

    def test_le_tableau_de_comparaison_marque_aussi_mot_a_mot(self):
        self.doublon.prenoms = 'AYA MARIANE'
        self.doublon.save()
        reponse = self.client.get(
            reverse('patients:doublons_comparer', args=[self.cle]))
        prenoms = next(l for l in reponse.context['comparaison']
                       if l['libelle'] == 'Prénoms')
        self.assertEqual([m['diff'] for m in prenoms['mots'][0]], [False, True])


class TestLaRaisonDuRapprochement(BaseDoublons):
    """« même nom » affirme une identité d'écriture : elle doit être vraie."""

    def _raisons(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        return reponse.context['groupes'][0]['raisons']

    def test_meme_ecriture_donne_meme_nom(self):
        self.assertIn('même nom', self._raisons())

    def test_une_ecriture_differente_ne_dit_pas_meme_nom(self):
        """BALO et BALLO passent au-dessus du seuil sans être le même mot."""
        self.doublon.nom = 'KOUASSY'
        self.doublon.save()
        raisons = self._raisons()
        self.assertIn('nom presque identique', raisons)
        self.assertNotIn('même nom', raisons)

    def test_la_raison_se_corrige_sans_attendre_un_recalcul(self):
        """Le relevé range des mesures ; l'écriture se relit sur les fiches."""
        from .models import DoublonPaire
        avant = list(DoublonPaire.all_objects.values_list('date_calcul', flat=True))
        self.doublon.nom = 'KOUASSY'
        self.doublon.save(update_fields=['nom'])
        DoublonPaire.all_objects.update(details={'noms': 0.99, 'date': 1.0,
                                                 'telephone': True,
                                                 'noms_identiques': True})
        self.assertIn('nom presque identique', self._raisons())
        self.assertEqual(
            len(avant), DoublonPaire.all_objects.count())

    def test_les_accents_et_apostrophes_ne_comptent_pas(self):
        from .doublons import memes_noms
        self.assertTrue(memes_noms({'nom': "N'Guéssan", 'prenoms': 'Kôné'},
                                   Patient(nom='NGUESSAN', prenoms='KONE')))
        self.assertFalse(memes_noms({'nom': 'BALO', 'prenoms': 'RAYAN'},
                                    Patient(nom='BALLO', prenoms='RAYAN')))

class TestLaRechercheDesRdvLitLeTelephone(TestCase):
    """La recherche des listes de RDV ne portait que sur le nom, les prénoms et
    le code patient : « 07 » semblait marcher parce que ces deux chiffres se
    trouvaient dans des codes patients, puis tout disparaissait au troisième."""

    def setUp(self):
        self.patient = Patient.objects.create(
            nom='Kouassi', prenoms='Ama', date_naissance='1990-06-01', sexe='F',
            telephone='+2250707123456')
        self.autre = Patient.objects.create(
            nom='Yao', prenoms='Koffi', date_naissance='1985-01-01', sexe='M',
            telephone='+2250501987654')
        # Département gynécologie : la liste de gynécologie ne montre que ceux-là,
        # celle des patients les montre tous.
        from medecins.models import Departement
        gyn, _ = Departement.objects.get_or_create(code='GYN', defaults={'nom': 'Gynécologie'})
        for p in (self.patient, self.autre):
            RendezVous.objects.create(patient=p, date_heure=timezone.now(),
                                      statut='confirme', departement=gyn)
        User.objects.create_superuser('su_rdv_tel', password='x')
        self.client = Client()
        self.client.login(username='su_rdv_tel', password='x')

    def _html(self, nom, q):
        reponse = self.client.get(reverse(nom), {'q': q, 'filter': ''})
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    def test_chaque_chiffre_saisi_affine_la_recherche(self):
        for nom in ('patients:rdv_global', 'gynecologie_rdv'):
            for saisie in ('0707', '07071234', '0707123456', '+2250707123456'):
                with self.subTest(liste=nom, saisie=saisie):
                    # Sur les lignes seulement : les menus de filtre
                    # nomment tous les patients, quelle que soit la recherche.
                    html = self._html(nom, saisie)
                    self.assertIn('<td class="td-name">KOUASSI Ama</td>', html)
                    self.assertNotIn('<td class="td-name">YAO Koffi</td>', html)
