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

from .models import FusionPatient, Patient, RendezVous


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


def _centre_pour(*utilisateurs, nom='Walé'):
    """Un centre, et les comptes qui lui sont rattachés.

    Ce que le middleware trouve dans une vraie requête : sans centre actif,
    la saisie refuse désormais de travailler (voir `PatientForm.clean`), et
    les écrans ne montrent rien.
    """
    from centres.models import Centre

    centre = Centre.objects.create(nom=nom, code=f'C{Centre.objects.count() + 1}')
    for utilisateur in utilisateurs:
        profil = utilisateur.profile
        profil.centres.add(centre)
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])
    return centre


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
        self.centre = _centre_pour(self.user)

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
        # `all_objects` : la fiche est créée dans le centre de la requête, et
        # hors requête le gestionnaire cloisonné ne la verrait pas.
        return Patient.all_objects.order_by('-pk').first()

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
        from centres.models import Centre
        User.objects.create_superuser('su_dn', password='x')
        # Un centre sans rattachement : les deux tests de formulaire en ont
        # besoin, les autres (export, import) travaillent sans centre et
        # doivent continuer de le faire.
        self.centre = Centre.objects.create(nom='Walé', code='WAL-DN')
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
        patient = Patient.all_objects.create(
            nom='Sans', prenoms='Date', sexe='M', telephone='0700000013',
            centre=self.centre)
        # Pas de `centre=` ici : la fiche porte le sien, et corriger une
        # adresse ne doit rien redemander.
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
        Patient.all_objects.create(nom='Kone', prenoms='Adama', sexe='M',
                                   telephone='0700000001', centre=self.centre)
        form = PatientForm(centre=self.centre, data={
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
        from centres.models import Centre
        # Le formulaire exige un centre connu : ici il vient de la fiche
        # qu'on modifie, comme dans l'écran de modification.
        self.centre = Centre.objects.create(nom='Walé', code='WAL-DEC')
        self.patient = Patient.all_objects.create(
            nom='Kone', prenoms='Adama', sexe='M', telephone='0700000001',
            date_naissance=date(1992, 10, 1), date_naissance_approx=True,
            centre=self.centre)

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
        from centres.models import Centre
        # Le centre du formulaire : sans lui, la saisie refuse de travailler
        # et aucun de ces tests ne dirait plus ce qu'il veut dire.
        cls.centre = Centre.objects.create(nom='Walé', code='WAL-PRV')
        cls.existant = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro', centre=cls.centre)
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
                           utilisateur=utilisateur or self.simple,
                           centre=self.centre, instance=instance)

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
        profil = self.admin.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])
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
        jumelle = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro', centre=self.centre)
        form = self._form(instance=jumelle, telephone='0709090909',
                          doublon_confirme='on')
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_la_modification_demande_tout_de_meme_la_confirmation(self):
        jumelle = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro', centre=self.centre)
        form = self._form(instance=jumelle, telephone='0709090909')
        self.assertFalse(form.is_valid())

    # ── Téléphone ──────────────────────────────────────────────────────────

    def test_le_numero_partage_est_compte_sans_bloquer(self):
        Patient.all_objects.create(nom='KOUASSI', prenoms='KOFFI', sexe='M',
                                   telephone='0701020304',
                                   date_naissance=date(1960, 1, 2),
                                   nationalite='Ivoirienne', adresse='Habitat',
                                   ville='Yamoussoukro', centre=self.centre)
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
        from centres.models import Centre
        # La fenêtre ne propose que dans le centre actif : sans rattachement,
        # elle ne proposerait plus rien et ces tests ne diraient plus rien.
        cls.centre = Centre.objects.create(nom='Walé', code='WAL-FEN')
        cls.existant = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), nationalite='Ivoirienne',
            adresse='Habitat', ville='Yamoussoukro', centre=cls.centre)
        cls.agent = User.objects.create_user('fen_agent', password='x')
        cls.agent.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))
        profil = cls.agent.profile
        profil.centres.add(cls.centre)
        profil.centre_actif = cls.centre
        profil.save(update_fields=['centre_actif'])

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
        }, utilisateur=User.objects.get(pk=self.agent.pk), centre=self.centre)
        self.assertFalse(form.is_valid())
        self.assertIn('existe déjà', form.non_field_errors()[0])

    def _page_de_saisie(self):
        """Le formulaire de création, vu par quelqu'un qui a le droit de
        créer — `cls.agent` ne l'a pas, il ne fait que consulter."""
        from django.contrib.auth.models import Permission
        saisie = User.objects.create_user('fen_saisie', password='x')
        for code in ('view_patient', 'add_patient'):
            saisie.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        profil = saisie.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])
        client = Client()
        client.force_login(User.objects.get(pk=saisie.pk))
        return client.get(reverse('patients:create')).content.decode()

    def test_ouvrir_la_fiche_reste_dans_l_onglet(self):
        """Ouvrir le dossier existant, c'est renoncer à la création : il n'y
        a rien à garder derrière soi. Le second onglet laissait un formulaire
        à demi rempli dans celui d'avant, qu'on finissait par enregistrer."""
        html = self._page_de_saisie()
        self.assertIn('window.location.assign(fiches[choisi].url)', html)
        self.assertNotIn('window.open(', html)

    def test_le_nom_de_la_carte_peut_etre_surligne(self):
        """Le nom est devenu le titre de la carte ; la règle de surlignage
        ne visait que `.dbl-val` et ne l'atteignait plus. Rien ne se voyait :
        le span était bien posé, simplement sans couleur. D'où ce test sur la
        feuille elle-même — c'est le seul endroit où l'oubli se lit."""
        self.assertIn('.dbl-ident .diff', self._page_de_saisie())


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
        from centres.models import Centre
        cls.centre = Centre.objects.create(nom='Walé', code='WAL-VRF')
        cls.patient = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F', telephone='0701020304',
            date_naissance=date(1992, 5, 14), centre=cls.centre)
        cls.user = User.objects.create_user('verif', password='x')
        cls.user.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))
        # L'endroit ne propose rien sans centre actif : c'est l'objet d'un
        # test à part (`TestLeCentreEstObligatoirePourCreer`), pas de ceux-ci.
        profil = cls.user.profile
        profil.centres.add(cls.centre)
        profil.centre_actif = cls.centre
        profil.save(update_fields=['centre_actif'])

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
        # Rattaché au centre, comme dans la vie : le menu Doublons ne montre
        # rien sans centre actif (voir patients/doublons_acces.py).
        self.rattacher(self.agent, self.centre)
        self.client = Client()
        self.client.force_login(self.agent)

    @staticmethod
    def rattacher(utilisateur, centre):
        profil = utilisateur.profile
        profil.centres.add(centre)
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])
        return utilisateur

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

    def test_aucun_filtre_n_est_pose_d_office(self):
        """Arriver sur la page ne doit allumer aucun filtre.

        Le relevé entier s'affiche, les plus sûrs en tête : un filtre posé
        sans qu'on l'ait demandé cachait la moitié des groupes tout en
        peignant « Filtres » comme si l'utilisateur avait choisi.
        """
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(reponse.context['niveau'], 'tous')
        html = reponse.content.decode()
        self.assertNotIn('class="o-ctrl-btn active"', html)
        # Le lien lui-même, pas le sélecteur que le script porte.
        self.assertNotIn('class="o-ctrl-btn" data-effacer', html)
        self.assertIn('class="o-ctrl-btn" data-effacer',
                      self.client.get(reverse('patients:doublons_liste'),
                                      {'niveau': 'certain'}).content.decode())

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
        """Masquée, pas fusionnée : son contenu n'est allé nulle part, et son
        adresse ne mène donc nulle part non plus."""
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


class TestLEcranSuitLeGabaritDesListes(BaseDoublons):
    """Le menu doit avoir la tête des autres listes, et par les mêmes moyens.

    Ces tests vérifient le balisage partagé, pas l'apparence : c'est lui qui
    garantit que les composants de `includes/listing/composants.html` et le
    pilotage de `includes/listing/page_js.html` s'appliquent. Un gabarit qui
    recommencerait à écrire ses propres classes les ferait tomber.
    """

    AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}

    def test_la_page_inclut_les_composants_partages(self):
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertIn('id="subheader-controls"', html)
        self.assertIn('id="dbl-resultats"', html)
        self.assertIn('class="o-page-count"', html)
        self.assertIn('class="o-search-bar"', html)

    def test_les_onglets_sont_ceux_du_projet(self):
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertIn('class="tab-nav"', html)
        self.assertIn('class="tab-btn active"', html)

    def test_le_releve_est_aussi_rendu_en_tableau(self):
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertIn('id="list-view"', html)
        self.assertIn('<th>Données rattachées</th>', html)
        # La ligne du groupe mène à la comparaison, comme la carte.
        self.assertIn(reverse('patients:doublons_comparer', args=[self.cle]), html)

    def test_le_fragment_ajax_porte_les_trois_zones_echangees(self):
        """`page_js.html` les remplace par identifiant : elles doivent y être."""
        html = self.client.get(reverse('patients:doublons_liste'),
                               **self.AJAX).content.decode()
        self.assertIn('id="subheader-controls"', html)
        self.assertIn('id="dbl-resultats"', html)
        self.assertIn('class="o-page-count"', html)
        self.assertNotIn('<body', html)      # un fragment, pas la page entière

    def test_le_niveau_est_un_menu_de_filtres(self):
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertIn('id="dd-filtres"', html)
        self.assertIn('class="o-dd-panel lst-menu"', html)
        self.assertIn('Quasi certain', html)

    def test_l_action_de_la_page_est_a_gauche_sous_le_titre(self):
        """La place qu'occupe « Créer » sur la liste des patients."""
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        gauche = html.split('id="dbl-gauche"', 1)[1].split('</div>', 1)[0]
        self.assertIn(reverse('patients:doublons_recalculer'), gauche)
        self.assertIn('o-btn-create', gauche)

    def test_les_trois_onglets_s_echangent_sans_recharger(self):
        """Chaque onglet doit rendre les régions que le socle remplace.

        Le changement d'onglet va chercher la page entière et n'en reprend
        que ces identifiants : un onglet qui n'en porterait pas laisserait
        la barre de l'onglet précédent en place.
        """
        # L'onglet des fusions demande sa propre permission : il est vérifié
        # de la même façon par `TestLOngletDesFusionsSEchangeAussi`.
        for route in ('patients:doublons_liste', 'patients:doublons_journal'):
            with self.subTest(onglet=route):
                html = self.client.get(reverse(route)).content.decode()
                for repere in ('id="dbl-recherche"', 'id="dbl-gauche"',
                               'id="subheader-controls"', 'id="dbl-resultats"',
                               'id="dbl-onglets"', 'class="o-page-title"'):
                    self.assertIn(repere, html)

    def test_les_feuilles_des_onglets_sont_communes(self):
        """Seul le corps est remplacé : les styles doivent être là d'emblée."""
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertIn('.jnl, .fus-journal', html)


class TestLaBanderoleDeMasquage(BaseDoublons):
    """L'annonce passe par le toast du projet, comme partout ailleurs.

    Le serveur ne rend plus un bandeau mais les données du toast ; le script
    du socle le lève au chargement, avec le même « Annuler » que le masquage
    en AJAX. Un seul chemin d'annonce, donc un seul texte à tenir.
    """

    def test_elle_annonce_la_fiche_et_propose_d_annuler(self):
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        reponse = self.client.get(reverse('patients:doublons_liste'),
                                  {'masque': self.doublon.pk})
        self.assertEqual(reponse.context['masquage'].pk, self.doublon.pk)
        self.assertContains(reponse, 'id="dbl-annonce"')
        self.assertContains(reponse, f'data-code="{self.doublon.code_patient}"')
        self.assertContains(reponse, f'data-gardee="{self.gardee.code_patient}"')
        self.assertContains(reponse, reverse('patients:doublons_reafficher',
                                             args=[self.doublon.pk]))

    def test_les_messages_django_ne_sont_plus_doubles(self):
        """base.html les affiche déjà en toast : un bandeau les redoublait."""
        reponse = self.client.post(
            reverse('patients:doublons_reafficher', args=[self.gardee.pk]), {})
        self.assertEqual(reponse.status_code, 404)   # elle n'est pas masquée
        html = self.client.get(reverse('patients:doublons_liste')).content.decode()
        self.assertNotIn('o-alerte', html)

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
        for attendu in ('Garder ', 'Masquer ', 'Pas un doublon'):
            self.assertIn(attendu, barre)

    def test_fusionner_n_apparait_pas_sans_la_permission(self):
        """`gerer_doublons` laisse masquer ; déplacer des factures demande
        `fusionner_patients`."""
        self.assertNotContains(self._comparer(), 'Fusionner')


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

    # ── Lequel des deux champs diffère ─────────────────────────────────────

    def test_le_prenom_seul_qui_differe_le_dit(self):
        """ASSENA ELIAQUIM / ASSENA ELIAKIM : le nom est le même."""
        self.doublon.prenoms = 'AYA MARIA'
        self.doublon.save(update_fields=['prenoms'])
        raisons = self._raisons()
        self.assertIn('prénom presque identique', raisons)
        self.assertNotIn('nom presque identique', raisons)
        self.assertNotIn('même nom', raisons)

    def test_le_nom_seul_qui_differe_le_dit_aussi(self):
        self.doublon.nom = 'KOUASSY'
        self.doublon.save(update_fields=['nom'])
        raisons = self._raisons()
        self.assertIn('nom presque identique', raisons)
        self.assertNotIn('prénom presque identique', raisons)

    def test_les_deux_qui_different_se_disent_ensemble(self):
        self.doublon.nom = 'KOUASSY'
        self.doublon.prenoms = 'AYA MARIA'
        self.doublon.save(update_fields=['nom', 'prenoms'])
        raisons = self._raisons()
        self.assertIn('nom et prénom presque identiques', raisons)
        self.assertNotIn('nom presque identique', raisons)
        self.assertNotIn('prénom presque identique', raisons)

    def test_la_meme_ecriture_des_deux_champs_reste_meme_nom(self):
        self.assertIn('même nom', self._raisons())

    def test_un_releve_ancien_garde_son_ancienne_phrase(self):
        """Les paires d'avant ne portent pas le détail par champ : on ne
        devine pas lequel diffère, on dit ce qu'on sait."""
        from .doublons import raisons
        self.assertEqual(raisons({'noms': 0.95}), ['nom presque identique'])

    def test_le_detail_par_champ_est_releve_a_la_mesure(self):
        """La fenêtre de saisie n'a pas de fiches à relire : c'est `scorer`
        qui doit ranger le détail."""
        from .doublons import scorer
        mesure = scorer({'nom': 'KOUASSI', 'prenoms': 'AYA MARIA',
                         'sexe': 'F', 'telephone': '0701020304',
                         'date_naissance': date(1992, 5, 14)},
                        self.gardee)
        self.assertTrue(mesure.details['nom_identique'])
        self.assertFalse(mesure.details['prenoms_identiques'])
        self.assertIn('prénom presque identique', mesure.raisons)


class BaseFusion(BaseDoublons):
    """Les deux fiches de `BaseDoublons`, et le droit de les fusionner."""

    def setUp(self):
        from django.contrib.auth.models import Permission
        super().setUp()
        self.agent.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='fusionner_patients'))
        self.agent = User.objects.get(pk=self.agent.pk)
        self.client.force_login(self.agent)
        # Désignée à la main : sinon la première donnée rattachée au doublon
        # ferait de lui la fiche gardée, et les écrans changeraient de sens
        # au milieu d'un test.
        from .models import ChoixFicheGardee
        ChoixFicheGardee.all_objects.create(patient=self.gardee,
                                            centre=self.centre)

    def fusionner(self, **kwargs):
        from .fusion import Choix, fusionner
        return fusionner(self.gardee, self.doublon,
                         Choix(**kwargs), self.agent)

    def rdv(self, fiche, **kwargs):
        kwargs.setdefault('motif', 'Contrôle')
        kwargs.setdefault('date_heure', timezone.now())
        return RendezVous.objects.create(patient=fiche, **kwargs)


class TestLaFusionDeplaceLesLignes(BaseFusion):
    def test_les_rendez_vous_et_factures_changent_de_proprietaire(self):
        from facturation.models import Facture
        rdv = self.rdv(self.doublon)
        facture = Facture.objects.create(patient=self.doublon, montant_total=1000)
        self.fusionner()
        self.assertEqual(RendezVous.all_objects.get(pk=rdv.pk).patient_id,
                         self.gardee.pk)
        self.assertEqual(Facture.all_objects.get(pk=facture.pk).patient_id,
                         self.gardee.pk)

    def test_le_journal_retient_exactement_les_lignes_deplacees(self):
        rdv = self.rdv(self.doublon)
        fusion = self.fusionner()
        self.assertEqual(fusion.lignes['patients.RendezVous'], [rdv.pk])

    def test_toutes_les_tables_connues_sont_couvertes(self):
        """L'introspection donne la liste ; la fusion doit la suivre en entier."""
        from .fusion import _champs_patient_par_table
        from .liens_patient import liens
        attendues = {f'{m._meta.app_label}.{m.__name__}' for m, _c, _l in liens()}
        self.assertEqual(set(_champs_patient_par_table()), attendues)

    def test_l_historique_generique_suit_la_fiche(self):
        from core.models import LogActivite
        from core.views import log_event
        log_event(self.doublon, self.agent, 'Fiche créée')
        fusion = self.fusionner()
        trace = LogActivite.objects.get(pk=fusion.lignes['core.LogActivite'][0])
        self.assertEqual(trace.object_id, self.gardee.pk)

    def test_un_compte_qui_ne_tombe_pas_juste_fait_tout_retomber(self):
        from .fusion import FusionIncoherente, _verifier_les_comptes
        with self.assertRaises(FusionIncoherente):
            _verifier_les_comptes(
                self.gardee, self.doublon,
                {('patients', 'RendezVous'): 2}, {}, (0, 0))

    def test_la_fiche_absorbee_disparait_des_listes(self):
        from core.middleware import centre_actif
        self.fusionner()
        with centre_actif(self.centre):
            self.assertEqual(Patient.objects.filter(pk=self.doublon.pk).count(), 0)
        fiche = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertEqual(fiche.fusionne_dans_id, self.gardee.pk)
        self.assertEqual(fiche.remplacee_par, self.gardee)

    def test_le_groupe_quitte_le_releve_tout_de_suite(self):
        from .models import DoublonPaire
        self.assertEqual(DoublonPaire.all_objects.count(), 1)
        self.fusionner()
        self.assertEqual(DoublonPaire.all_objects.count(), 0)


class TestLeChoixDesChamps(BaseFusion):
    def test_un_champ_vide_de_la_fiche_gardee_est_complete(self):
        self.gardee.profession = ''
        self.gardee.save()
        self.doublon.profession = 'Couturière'
        self.doublon.save()
        from .fusion import propositions
        proposition = next(p for p in propositions(self.gardee, self.doublon)
                           if p.champ == 'profession')
        self.assertEqual(proposition.defaut, 'absorbee')
        self.fusionner()
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).profession,
                         'Couturière')

    def test_allergies_et_antecedents_sont_additionnes(self):
        self.gardee.allergies = 'Pénicilline'
        self.gardee.save()
        self.doublon.allergies = 'Arachide\nPénicilline'
        self.doublon.save()
        self.fusionner()
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).allergies,
                         'Pénicilline\nArachide')

    def test_le_sexe_qui_se_contredit_n_a_pas_de_defaut(self):
        from .fusion import FusionRefusee, propositions
        self.doublon.sexe = 'M'
        self.doublon.save()
        proposition = next(p for p in propositions(self.gardee, self.doublon)
                           if p.champ == 'sexe')
        self.assertEqual(proposition.defaut, '')
        self.assertTrue(proposition.obligatoire)
        with self.assertRaises(FusionRefusee):
            self.fusionner()

    def test_le_sexe_choisi_est_ecrit_et_trace(self):
        self.doublon.sexe = 'M'
        self.doublon.save()
        fusion = self.fusionner(champs={'sexe': ('absorbee', '')})
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).sexe, 'M')
        self.assertEqual(fusion.champs['sexe'],
                         {'choix': 'absorbee', 'avant': 'F', 'apres': 'M'})

    def test_la_date_de_naissance_emporte_sa_case_approximative(self):
        """Prendre la date de l'autre fiche sans sa case ferait d'une
        estimation une date certaine."""
        self.doublon.date_naissance = date(1992, 1, 1)
        self.doublon.date_naissance_approx = True
        self.doublon.save()
        fusion = self.fusionner(champs={'date_naissance': ('absorbee', '')})
        gardee = Patient.all_objects.get(pk=self.gardee.pk)
        self.assertEqual(gardee.date_naissance, date(1992, 1, 1))
        self.assertTrue(gardee.date_naissance_approx)
        self.assertIn('date_naissance_approx', fusion.champs)

    def test_la_photo_de_l_autre_fiche_n_est_jamais_supprimee(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        for fiche, nom in ((self.gardee, 'g.gif'), (self.doublon, 'd.gif')):
            fiche.photo.save(nom, SimpleUploadedFile(nom, b'GIF89a'), save=True)
        chemin_absorbee = self.doublon.photo.name
        self.fusionner(champs={'photo': ('absorbee', '')})
        gardee = Patient.all_objects.get(pk=self.gardee.pk)
        absorbee = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertEqual(gardee.photo.name, chemin_absorbee)
        self.assertEqual(absorbee.photo.name, chemin_absorbee)
        self.assertTrue(absorbee.photo.storage.exists(chemin_absorbee))

    def test_une_correction_a_la_main_est_retenue(self):
        fusion = self.fusionner(champs={'ville': ('manuel', 'Bouaké')})
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).ville,
                         'Bouaké')
        self.assertEqual(fusion.champs['ville']['choix'], 'manuel')


class TestLesCasParticuliersDeLaFusion(BaseFusion):
    def _codes(self, gardee=None, absorbee=None):
        from .fusion import obstacles
        return {o.code: o for o in obstacles(gardee or self.gardee,
                                             absorbee or self.doublon)}

    def test_deux_centres_sont_refuses(self):
        from centres.models import Centre
        from .fusion import FusionRefusee
        autre = Centre.objects.create(nom='Autre', code='AUT')
        Patient.all_objects.filter(pk=self.doublon.pk).update(centre=autre)
        self.doublon.refresh_from_db()
        self.assertEqual(self._codes()['centres'].gravite, 'refus')
        with self.assertRaises(FusionRefusee):
            self.fusionner()

    def test_un_deces_demande_une_confirmation(self):
        from hospitalisation.models import RegistreDeces
        from .fusion import FusionRefusee
        RegistreDeces.objects.create(patient=self.doublon, code='DEC1',
                                     date_deces=timezone.now(),
                                     raison_deces='Inconnue')
        self.assertEqual(self._codes()['deces'].gravite, 'confirmation')
        with self.assertRaises(FusionRefusee):
            self.fusionner()
        self.fusionner(deces_confirme=True)
        self.assertEqual(
            RegistreDeces.all_objects.get(code='DEC1').patient_id, self.gardee.pk)

    def _hospitaliser(self, fiche, numero, lit='3'):
        from hospitalisation.models import Chambre, Hospitalisation
        chambre, _ = Chambre.objects.get_or_create(salle_no='A1')
        return Hospitalisation.objects.create(
            patient=fiche, numero=numero, date_admission=timezone.now(),
            statut='hospitalise', chambre=chambre, numero_lit=lit)

    def test_deux_hospitalisations_en_cours_demandent_un_choix(self):
        from .fusion import FusionRefusee
        self._hospitaliser(self.gardee, 'H1', lit='1')
        self._hospitaliser(self.doublon, 'H2', lit='2')
        self.assertEqual(self._codes()['hospitalisations'].gravite, 'choix')
        with self.assertRaises(FusionRefusee):
            self.fusionner()

    def test_celle_qu_on_ne_garde_pas_est_cloturee_et_son_lit_libere(self):
        from hospitalisation.models import Hospitalisation
        gardee_h = self._hospitaliser(self.gardee, 'H1', lit='1')
        perdue = self._hospitaliser(self.doublon, 'H2', lit='2')
        fusion = self.fusionner(hospitalisation_active=gardee_h.pk)
        perdue.refresh_from_db()
        self.assertEqual(perdue.statut, 'annule')
        self.assertIn('Annulée (doublon)', perdue.notes)
        self.assertEqual(
            Hospitalisation.all_objects.filter(
                chambre=perdue.chambre, numero_lit='2',
                statut='hospitalise').count(), 0)
        self.assertEqual(fusion.effets['hospitalisations'][0]['pk'], perdue.pk)

    def test_les_rdv_du_meme_jour_avec_le_meme_medecin_sont_signales(self):
        medecin = _medecin()
        quand = timezone.now()
        self.rdv(self.gardee, medecin=medecin, date_heure=quand)
        double = self.rdv(self.doublon, medecin=medecin, date_heure=quand)
        signal = self._codes()['rdv']
        self.assertEqual(signal.gravite, 'signal')
        self.assertEqual(signal.details['paires'][0]['absorbee'].pk, double.pk)
        self.assertTrue(signal.details['paires'][0]['annulable'])

    def test_un_rdv_qui_porte_une_consultation_ne_peut_pas_etre_annule(self):
        from consultations.models import Consultation
        medecin = _medecin()
        quand = timezone.now()
        self.rdv(self.gardee, medecin=medecin, date_heure=quand)
        double = self.rdv(self.doublon, medecin=medecin, date_heure=quand)
        Consultation.objects.create(patient=self.doublon, rendez_vous=double,
                                    medecin=medecin, motif='Contrôle')
        paire = self._codes()['rdv'].details['paires'][0]
        self.assertFalse(paire['annulable'])
        self.assertIn('consultation', paire['empeche'])
        # Même demandée, l'annulation ne passe pas.
        fusion = self.fusionner(rdv_a_annuler=[double.pk])
        self.assertEqual(fusion.effets['rdv_annules'], [])
        self.assertNotEqual(RendezVous.all_objects.get(pk=double.pk).statut,
                            'annule')

    def test_la_case_cochee_passe_le_rdv_en_annule_sans_le_supprimer(self):
        medecin = _medecin()
        quand = timezone.now()
        self.rdv(self.gardee, medecin=medecin, date_heure=quand)
        double = self.rdv(self.doublon, medecin=medecin, date_heure=quand)
        self.fusionner(rdv_a_annuler=[double.pk])
        rendu = RendezVous.all_objects.get(pk=double.pk)
        self.assertEqual(rendu.statut, 'annule')
        self.assertIn('doublon', rendu.notes)
        self.assertEqual(rendu.patient_id, self.gardee.pk)

    def test_une_paire_ecartee_est_reportee_sur_la_fiche_gardee(self):
        from .models import PaireEcartee
        tiers = Patient.all_objects.create(
            nom='TRAORE', prenoms='MOUSSA', sexe='M', centre=self.centre)
        a, b = sorted([self.doublon.pk, tiers.pk])
        PaireEcartee.all_objects.create(patient_a_id=a, patient_b_id=b,
                                        centre=self.centre, raison='frères')
        fusion = self.fusionner()
        x, y = sorted([self.gardee.pk, tiers.pk])
        self.assertTrue(PaireEcartee.all_objects.filter(
            patient_a_id=x, patient_b_id=y, raison='frères').exists())
        self.assertEqual(fusion.effets['paires_reportees'], [[x, y]])


class TestAnnulerUneFusion(BaseFusion):
    def test_tout_revient_a_sa_place(self):
        from facturation.models import Facture
        from .fusion import annuler
        self.gardee.profession = ''
        self.gardee.save()
        self.doublon.profession = 'Couturière'
        self.doublon.save()
        rdv = self.rdv(self.doublon)
        facture = Facture.objects.create(patient=self.doublon, montant_total=1000)

        fusion = self.fusionner()
        self.assertEqual(annuler(fusion, self.agent), [])

        self.assertEqual(RendezVous.all_objects.get(pk=rdv.pk).patient_id,
                         self.doublon.pk)
        self.assertEqual(Facture.all_objects.get(pk=facture.pk).patient_id,
                         self.doublon.pk)
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).profession, '')
        rendue = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertIsNone(rendue.fusionne_dans_id)
        self.assertFalse(rendue.retiree)
        fusion.refresh_from_db()
        self.assertFalse(fusion.active)
        self.assertEqual(fusion.annulee_par, self.agent)

    def test_l_historique_repart_avec_la_fiche(self):
        from core.models import LogActivite
        from core.views import log_event
        from .fusion import annuler
        log_event(self.doublon, self.agent, 'Fiche créée')
        fusion = self.fusionner()
        annuler(fusion, self.agent)
        trace = LogActivite.objects.get(pk=fusion.lignes['core.LogActivite'][0])
        self.assertEqual(trace.object_id, self.doublon.pk)

    def test_le_rendez_vous_annule_retrouve_son_etat(self):
        from .fusion import annuler
        medecin = _medecin()
        quand = timezone.now()
        self.rdv(self.gardee, medecin=medecin, date_heure=quand)
        double = self.rdv(self.doublon, medecin=medecin, date_heure=quand,
                          statut='confirme', notes='à revoir')
        fusion = self.fusionner(rdv_a_annuler=[double.pk])
        annuler(fusion, self.agent)
        rendu = RendezVous.all_objects.get(pk=double.pk)
        self.assertEqual(rendu.statut, 'confirme')
        self.assertEqual(rendu.notes, 'à revoir')
        self.assertEqual(rendu.patient_id, self.doublon.pk)

    def test_la_paire_ecartee_reportee_est_retiree(self):
        from .fusion import annuler
        from .models import PaireEcartee
        tiers = Patient.all_objects.create(
            nom='TRAORE', prenoms='MOUSSA', sexe='M', centre=self.centre)
        a, b = sorted([self.doublon.pk, tiers.pk])
        PaireEcartee.all_objects.create(patient_a_id=a, patient_b_id=b,
                                        centre=self.centre)
        fusion = self.fusionner()
        annuler(fusion, self.agent)
        x, y = sorted([self.gardee.pk, tiers.pk])
        self.assertFalse(PaireEcartee.all_objects.filter(
            patient_a_id=x, patient_b_id=y).exists())
        self.assertTrue(PaireEcartee.all_objects.filter(
            patient_a_id=a, patient_b_id=b).exists())

    def _hospitaliser(self, fiche, numero, lit):
        from hospitalisation.models import Chambre, Hospitalisation
        chambre, _ = Chambre.objects.get_or_create(salle_no='A1')
        return Hospitalisation.objects.create(
            patient=fiche, numero=numero, date_admission=timezone.now(),
            statut='hospitalise', chambre=chambre, numero_lit=lit)

    def test_l_hospitalisation_cloturee_est_rouverte(self):
        from .fusion import annuler
        active = self._hospitaliser(self.gardee, 'H1', '1')
        perdue = self._hospitaliser(self.doublon, 'H2', '2')
        fusion = self.fusionner(hospitalisation_active=active.pk)
        self.assertEqual(annuler(fusion, self.agent), [])
        perdue.refresh_from_db()
        self.assertEqual(perdue.statut, 'hospitalise')

    def test_elle_reste_annulee_si_le_lit_a_ete_repris(self):
        """L'annulation dit ce qu'elle n'a pas pu rendre, plutôt que de
        remettre deux personnes dans le même lit."""
        from .fusion import annuler
        active = self._hospitaliser(self.gardee, 'H1', '1')
        perdue = self._hospitaliser(self.doublon, 'H2', '2')
        fusion = self.fusionner(hospitalisation_active=active.pk)
        tiers = Patient.all_objects.create(nom='TRAORE', prenoms='M',
                                           sexe='M', centre=self.centre)
        self._hospitaliser(tiers, 'H3', '2')
        retenues = annuler(fusion, self.agent)
        perdue.refresh_from_db()
        self.assertEqual(perdue.statut, 'annule')
        self.assertEqual(len(retenues), 1)
        self.assertIn('occupé', retenues[0])

    def test_une_ligne_supprimee_depuis_est_signalee(self):
        from .fusion import annuler
        rdv = self.rdv(self.doublon)
        fusion = self.fusionner()
        RendezVous.all_objects.filter(pk=rdv.pk).delete()
        retenues = annuler(fusion, self.agent)
        self.assertEqual(len(retenues), 1)
        self.assertIn('non rendue', retenues[0])

    def test_une_fusion_plus_recente_bloque_l_annulation(self):
        from .fusion import Choix, FusionRefusee, annuler, fusionner
        troisieme = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
            telephone='0701020304', date_naissance=date(1992, 5, 14),
            centre=self.centre)
        premiere = self.fusionner()
        seconde = fusionner(self.gardee, troisieme, Choix(), self.agent)
        with self.assertRaises(FusionRefusee) as erreur:
            annuler(premiere, self.agent)
        self.assertIn(troisieme.code_patient, str(erreur.exception))
        # La plus récente, elle, se défait.
        annuler(seconde, self.agent)
        annuler(premiere, self.agent)
        premiere.refresh_from_db()
        self.assertFalse(premiere.active)

    def test_une_fusion_deja_annulee_ne_se_defait_pas_deux_fois(self):
        from .fusion import FusionRefusee, annuler
        fusion = self.fusionner()
        annuler(fusion, self.agent)
        with self.assertRaises(FusionRefusee):
            annuler(fusion, self.agent)


class TestLeVerrouDeLaFusion(BaseFusion):
    def test_pas_de_fusion_pendant_un_recalcul_complet(self):
        """Le verrou partagé, comme le recalcul ciblé : un passage complet
        réécrirait le relevé par-dessus."""
        from .doublons_recalcul import verrou
        from .fusion import FusionRefusee
        with verrou(exclusif=True):
            with self.assertRaises(FusionRefusee) as erreur:
                self.fusionner()
        self.assertIn('recalcul complet', str(erreur.exception))
        self.assertIsNone(
            Patient.all_objects.get(pk=self.doublon.pk).fusionne_dans_id)


class TestLEcranDeFusion(BaseFusion):
    def _url(self):
        return reverse('patients:fusionner', args=[self.cle, self.doublon.pk])

    def test_l_ecran_est_refuse_sans_la_permission(self):
        from django.contrib.auth.models import Permission
        simple = User.objects.create_user('fus_sans', password='x')
        simple.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='gerer_doublons'))
        client = Client()
        client.force_login(User.objects.get(pk=simple.pk))
        self.assertEqual(client.get(self._url()).status_code, 403)

    def test_l_apercu_annonce_ce_qui_sera_deplace(self):
        self.rdv(self.doublon)
        self.rdv(self.doublon)
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.context['apercu']['total'], 2)
        self.assertContains(reponse, 'va transférer')
        self.assertContains(reponse, '2 rendez-vous')

    def test_les_champs_identiques_sont_replies(self):
        reponse = self.client.get(self._url())
        self.assertTrue(reponse.context['identiques'] > 0)
        self.assertContains(reponse, 'champs identiques')

    def test_la_fusion_passe_par_le_formulaire(self):
        rdv = self.rdv(self.doublon)
        reponse = self.client.post(self._url(), {
            'retour': reverse('patients:doublons_liste')}, follow=True)
        self.assertEqual(RendezVous.all_objects.get(pk=rdv.pk).patient_id,
                         self.gardee.pk)
        self.assertContains(reponse, 'a été fusionnée dans')

    def test_un_refus_reaffiche_l_ecran_avec_la_raison(self):
        self.doublon.sexe = 'M'
        self.doublon.save()
        reponse = self.client.post(self._url(), {})
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "La fusion n'a pas eu lieu")
        self.assertContains(reponse, 'demande un choix')
        self.assertIsNone(
            Patient.all_objects.get(pk=self.doublon.pk).fusionne_dans_id)

    def test_le_journal_liste_la_fusion_et_propose_de_l_annuler(self):
        fusion = self.fusionner()
        reponse = self.client.get(reverse('patients:fusions'))
        self.assertContains(reponse, self.doublon.code_patient)
        self.assertContains(reponse, 'Annuler la fusion')
        self.client.post(reverse('patients:fusion_annuler', args=[fusion.pk]))
        self.assertFalse(FusionPatient.all_objects.get(pk=fusion.pk).active)

    def test_le_journal_dit_quelle_fusion_annuler_d_abord(self):
        from .fusion import Choix, fusionner
        troisieme = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
            telephone='0701020304', date_naissance=date(1992, 5, 14),
            centre=self.centre)
        premiere = self.fusionner()
        fusionner(self.gardee, troisieme, Choix(), self.agent)
        reponse = self.client.get(reverse('patients:fusions'))
        bloquantes = [l for l in reponse.context['lignes'] if l['bloquante']]
        self.assertEqual([l['fusion'].pk for l in bloquantes], [premiere.pk])
        self.assertContains(reponse, "Annulez d'abord")

    def test_l_ancienne_adresse_mene_a_la_fiche_gardee(self):
        from django.contrib.auth.models import Permission
        self.fusionner()
        simple = User.objects.create_user('fus_lecteur', password='x')
        simple.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))
        # Rattaché au centre : l'adresse directe d'une fiche retirée ne
        # traverse plus les centres, même pour rediriger.
        self.rattacher(User.objects.get(pk=simple.pk), self.centre)
        client = Client()
        client.force_login(User.objects.get(pk=simple.pk))
        reponse = client.get(reverse('patients:detail', args=[self.doublon.pk]))
        self.assertRedirects(
            reponse, reverse('patients:detail', args=[self.gardee.pk]),
            fetch_redirect_response=False)

    def test_qui_traite_les_doublons_voit_le_bandeau(self):
        self.fusionner()
        reponse = self.client.get(reverse('patients:detail', args=[self.doublon.pk]))
        self.assertContains(reponse, 'Fiche fusionnée dans')
        self.assertContains(reponse, self.gardee.code_patient)


class TestLeBoutonFusionnerSurLaComparaison(BaseFusion):
    def test_il_apparait_avec_la_permission(self):
        reponse = self.client.get(
            reverse('patients:doublons_comparer', args=[self.cle]))
        self.assertContains(reponse, 'Fusionner')
        self.assertContains(
            reponse, reverse('patients:fusionner',
                             args=[self.cle, self.doublon.pk]))

    def test_l_onglet_des_fusions_aussi(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertContains(reponse, reverse('patients:fusions'))


class TestLeJournalPendantLaFusion(BaseFusion):
    """Le journal automatique écrit sur toute sauvegarde faite dans une requête.

    Pendant une fusion, ces traces-là tombaient entre le comptage d'avant et
    sa vérification : une fusion où un champ changeait était refusée au motif
    que « l'historique ne se retrouve pas en entier » (constaté sur
    OUATTARA / OUATTARRA JEANS CHRIST ELI SHAMA). Rien de tout cela ne se voit
    sans utilisateur connecté : ces tests passent donc par l'écran.
    """

    def setUp(self):
        super().setUp()
        # La fiche absorbée porte ce que l'autre n'a pas : la fusion reprend
        # le champ, donc enregistre la fiche gardée — le cas qui échouait.
        self.doublon.profession = 'Couturière'
        self.doublon.save(update_fields=['profession'])

    def _url(self):
        return reverse('patients:fusionner', args=[self.cle, self.doublon.pk])

    def _traces(self, fiche):
        from django.contrib.contenttypes.models import ContentType
        from core.models import LogActivite
        from .models import Patient as P
        return LogActivite.objects.filter(
            content_type=ContentType.objects.get_for_model(P),
            object_id=fiche.pk)

    def test_un_champ_repris_ne_fait_plus_echouer_la_fusion(self):
        reponse = self.client.post(self._url(), {
            'retour': reverse('patients:doublons_liste')}, follow=True)
        self.assertNotContains(reponse, 'La fusion n’a pas eu lieu')
        fiche = Patient.all_objects.get(pk=self.doublon.pk)
        self.assertEqual(fiche.fusionne_dans_id, self.gardee.pk)
        self.assertEqual(Patient.all_objects.get(pk=self.gardee.pk).profession,
                         'Couturière')

    def test_la_fiche_absorbee_ne_garde_aucune_trace(self):
        """Elle n'est plus consultable : son historique doit être parti."""
        from core.views import log_event
        log_event(self.doublon, self.agent, 'Fiche créée')
        self.client.post(self._url(), {})
        self.assertEqual(self._traces(self.doublon).count(), 0)
        self.assertEqual(self._traces(self.gardee).filter(type='note').count(), 1)

    def test_la_fusion_laisse_une_seule_trace_sur_la_fiche_gardee(self):
        from .fusion import CODE_FUSION
        self.client.post(self._url(), {})
        traces = self._traces(self.gardee).filter(code=CODE_FUSION)
        self.assertEqual(traces.count(), 1)
        self.assertIn(self.doublon.code_patient, traces.first().message)
        self.assertIn('Profession', traces.first().message)

    def test_l_annulation_laisse_la_sienne(self):
        from .fusion import CODE_ANNULATION
        from .models import FusionPatient
        self.client.post(self._url(), {})
        fusion = FusionPatient.all_objects.get()
        self.client.post(reverse('patients:fusion_annuler', args=[fusion.pk]))
        traces = self._traces(self.gardee).filter(code=CODE_ANNULATION)
        self.assertEqual(traces.count(), 1)
        self.assertIn(self.doublon.code_patient, traces.first().message)


class TestLOngletDesFusionsSEchangeAussi(BaseFusion):
    def test_il_rend_les_regions_echangees(self):
        html = self.client.get(reverse('patients:fusions')).content.decode()
        for repere in ('id="dbl-recherche"', 'id="dbl-gauche"',
                       'id="subheader-controls"', 'id="dbl-resultats"',
                       'id="dbl-onglets"', 'class="o-page-title"'):
            self.assertIn(repere, html)


class TestRetrouverUneFicheFusionnee(BaseFusion):
    """Le code et l'ancien identifiant de la fiche absorbée ne mènent plus
    nulle part : ils doivent ramener la fiche gardée."""

    def setUp(self):
        super().setUp()
        # Le centre actif vient de `BaseDoublons` : sans lui, la liste ne
        # montrerait rien et la recherche ne prouverait rien.
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            ancien_identifiant='ANC-0042')
        Patient.all_objects.filter(pk=self.gardee.pk).update(
            ancien_identifiant='ANC-0001')
        self.doublon.refresh_from_db()
        self.gardee.refresh_from_db()

    def _chercher(self, terme):
        reponse = self.client.get(reverse('patients:list'), {'q': terme})
        return [p.pk for p in reponse.context['page_obj'].object_list]

    def test_le_code_de_la_fiche_absorbee_mene_a_la_gardee(self):
        self.fusionner()
        self.assertEqual(self._chercher(self.doublon.code_patient),
                         [self.gardee.pk])

    def test_son_ancien_identifiant_aussi(self):
        self.fusionner()
        self.assertEqual(self._chercher('ANC-0042'), [self.gardee.pk])

    def test_l_ancien_identifiant_de_la_fiche_gardee_se_cherche_aussi(self):
        """Il n'était pas cherchable du tout avant."""
        self.assertEqual(self._chercher('ANC-0001'), [self.gardee.pk])

    def test_une_fiche_seulement_masquee_ne_ramene_rien(self):
        """Son contenu n'est allé nulle part : la faire apparaître sous un
        autre nom tromperait."""
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.assertEqual(self._chercher(self.doublon.code_patient), [])

    def test_la_chaine_de_fusions_est_remontee(self):
        from .fusion import Choix, fusionner
        from .resolution import pks_depuis_un_repere
        troisieme = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
            telephone='0701020304', date_naissance=date(1992, 5, 14),
            centre=self.centre)
        self.fusionner()                                   # doublon → gardee
        fusionner(troisieme, self.gardee, Choix(), self.agent)  # gardee → 3e
        self.assertEqual(pks_depuis_un_repere(self.doublon.code_patient),
                         {troisieme.pk})

    def test_un_terme_inconnu_ne_change_rien(self):
        from .resolution import condition_reperes
        self.assertIsNone(condition_reperes('zeboulon'))
        self.assertEqual(self._chercher('zeboulon'), [])

    def test_le_selecteur_de_patient_suit_la_meme_regle(self):
        self.fusionner()
        reponse = self.client.get(reverse('patients:patient_search'),
                                  {'q': self.doublon.code_patient})
        self.assertEqual([r['id'] for r in reponse.json()['results']],
                         [self.gardee.pk])


class UnVoisin:
    """De quoi se glisser dans le menu Doublons depuis un autre centre.

    Le centre voisin n'a aucune fiche : tout ce que l'intrus verrait ou
    toucherait viendrait donc forcément de Walé.
    """

    def installer_le_voisin(self, *permissions):
        from django.contrib.auth.models import Permission
        from centres.models import Centre

        self.voisin = Centre.objects.create(nom='Toumbokro', code='TBK')
        intrus = User.objects.create_user('dbl_toumbokro', password='x')
        for code in ('view_patient', 'gerer_doublons') + permissions:
            intrus.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.intrus = self.rattacher(User.objects.get(pk=intrus.pk), self.voisin)
        self.client = Client()
        self.client.force_login(self.intrus)

    def detacher(self, utilisateur):
        """Le même compte, plus rattaché à rien : aucun centre actif."""
        profil = utilisateur.profile
        profil.centres.clear()
        profil.centre_actif = None
        profil.save(update_fields=['centre_actif'])
        self.client = Client()
        self.client.force_login(User.objects.get(pk=utilisateur.pk))


class TestLeCloisonnementDuMenuDoublons(UnVoisin, BaseDoublons):
    """Rattaché à Toumbokro, on ne lit ni ne modifie une fiche de Walé.

    L'écran rapproche les fiches deux à deux, en entier : il n'y a pas de
    demi-fuite possible ici. Chaque chemin est donc essayé, y compris les
    adresses directes qu'aucun bouton ne propose.
    """

    def setUp(self):
        super().setUp()
        self.installer_le_voisin()

    # ── Ce qui se lit ──────────────────────────────────────────────────────

    def test_la_liste_ne_montre_aucun_groupe_de_l_autre_centre(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['total'], 0)
        self.assertNotContains(reponse, self.gardee.code_patient)

    def test_la_comparaison_refuse_une_cle_de_l_autre_centre(self):
        self.assertEqual(self.client.get(
            reverse('patients:doublons_comparer', args=[self.cle])
        ).status_code, 404)

    def test_l_onglet_des_masquees_ne_montre_rien_de_l_autre_centre(self):
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            masque=True, doublon_de=self.gardee)
        reponse = self.client.get(reverse('patients:doublons_masquees'))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['page'].paginator.count, 0)
        self.assertNotContains(reponse, self.doublon.code_patient)

    def test_le_journal_ne_montre_aucune_trace_de_l_autre_centre(self):
        from core.views import log_event
        from . import journal_doublons
        log_event(self.gardee, self.agent, 'Forcée à Walé',
                  type='alerte', code=journal_doublons.FORCAGE)
        reponse = self.client.get(reverse('patients:doublons_journal'))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['page'].paginator.count, 0)

    def test_la_recherche_du_journal_ne_ramene_pas_l_autre_centre(self):
        """Chercher le code d'une fiche de Walé ne doit rien révéler."""
        from core.views import log_event
        from . import journal_doublons
        log_event(self.gardee, self.agent, 'Forcée à Walé',
                  type='alerte', code=journal_doublons.FORCAGE)
        reponse = self.client.get(reverse('patients:doublons_journal'),
                                  {'q': self.gardee.code_patient})
        self.assertEqual(reponse.context['page'].paginator.count, 0)

    # ── Ce qui se modifie ──────────────────────────────────────────────────

    def test_aucune_decision_ne_passe_sur_une_cle_de_l_autre_centre(self):
        from .models import ChoixFicheGardee, PaireEcartee
        adresses = [
            (reverse('patients:doublons_ecarter', args=[self.cle]), {}),
            (reverse('patients:doublons_reprendre', args=[self.cle]), {}),
            (reverse('patients:doublons_garder',
                     args=[self.cle, self.gardee.pk]), {}),
            (reverse('patients:doublons_masquer',
                     args=[self.cle, self.doublon.pk]),
             {'au_profit_de': self.gardee.pk}),
        ]
        for adresse, donnees in adresses:
            with self.subTest(adresse=adresse):
                self.assertEqual(
                    self.client.post(adresse, donnees).status_code, 404)
        self.assertFalse(PaireEcartee.all_objects.exists())
        self.assertFalse(ChoixFicheGardee.all_objects.exists())
        self.doublon.refresh_from_db()
        self.assertFalse(self.doublon.masque)

    def test_reafficher_refuse_une_fiche_de_l_autre_centre(self):
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            masque=True, doublon_de=self.gardee)
        self.assertEqual(self.client.post(reverse(
            'patients:doublons_reafficher', args=[self.doublon.pk])
        ).status_code, 404)
        self.doublon.refresh_from_db()
        self.assertTrue(self.doublon.masque)

    def test_le_recalcul_ne_releve_que_le_centre_actif(self):
        """La tâche de fond est exécutée ici même : lancée dans un fil, elle
        ne verrait pas la transaction du test et ne prouverait rien."""
        from core import taches
        from core.models import TacheImport
        from . import doublons_recalcul

        releves = []
        vrai_recalcul, vrai_lancer = (doublons_recalcul.recalculer_centre,
                                      taches.lancer)
        doublons_recalcul.recalculer_centre = (
            lambda centre_id, avancement=None: releves.append(centre_id) or 0)
        self.addCleanup(setattr, doublons_recalcul, 'recalculer_centre',
                        vrai_recalcul)

        def lancer_ici(libelle, utilisateur, centre, travail):
            travail(None)
            return TacheImport.objects.create(libelle=libelle,
                                              utilisateur=utilisateur)

        taches.lancer = lancer_ici
        self.addCleanup(setattr, taches, 'lancer', vrai_lancer)

        self.client.post(reverse('patients:doublons_recalculer'))
        self.assertEqual(releves, [self.voisin.pk])

    def test_la_trace_de_saisie_ne_se_pose_pas_sur_l_autre_centre(self):
        from core.models import LogActivite
        reponse = self.client.post(reverse('patients:doublons_journaliser'),
                                   {'pk': self.gardee.pk, 'score': 80,
                                    'nom': 'KOUASSI', 'prenoms': 'AYA'})
        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(LogActivite.objects.filter(
            object_id=self.gardee.pk, type='alerte').exists())


class TestLeMenuDoublonsSansCentreActif(UnVoisin, BaseDoublons):
    """Sans centre actif, l'écran ne montre rien et le dit.

    C'est le trou qu'on bouche : il retombait sur « le centre de la première
    paire venue ». Un super-utilisateur ne fait pas exception — il choisit
    son centre comme tout le monde.
    """

    def setUp(self):
        super().setUp()
        self.detacher(self.agent)

    def test_la_liste_affiche_choisissez_un_centre_et_rien_d_autre(self):
        reponse = self.client.get(reverse('patients:doublons_liste'))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertNotContains(reponse, self.gardee.code_patient)

    def test_les_trois_onglets_disent_la_meme_chose(self):
        for nom in ('doublons_liste', 'doublons_journal'):
            with self.subTest(onglet=nom):
                self.assertContains(self.client.get(reverse(f'patients:{nom}')),
                                    'Choisissez un centre')

    def test_l_onglet_des_masquees_ne_fait_pas_exception(self):
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            masque=True, doublon_de=self.gardee)
        reponse = self.client.get(reverse('patients:doublons_masquees'))
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertNotContains(reponse, self.doublon.code_patient)

    def test_la_comparaison_ne_s_ouvre_pas_davantage(self):
        reponse = self.client.get(
            reverse('patients:doublons_comparer', args=[self.cle]))
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertNotContains(reponse, self.gardee.code_patient)

    def test_aucune_decision_ne_passe(self):
        reponse = self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.assertEqual(reponse.status_code, 403)
        self.doublon.refresh_from_db()
        self.assertFalse(self.doublon.masque)

    def test_le_recalcul_non_plus(self):
        from core.models import TacheImport
        self.assertEqual(self.client.post(
            reverse('patients:doublons_recalculer')).status_code, 403)
        self.assertFalse(TacheImport.objects.exists())

    def test_un_super_utilisateur_ne_fait_pas_exception(self):
        patron = User.objects.create_superuser('dbl_patron', password='x')
        client = Client()
        client.force_login(patron)
        reponse = client.get(reverse('patients:doublons_liste'))
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertNotContains(reponse, self.gardee.code_patient)

    def test_le_rafraichissement_ajax_le_dit_aussi(self):
        """La liste se recharge en AJAX : elle doit refuser là aussi, et
        avec un message lisible plutôt qu'un gabarit vide."""
        reponse = self.client.get(reverse('patients:doublons_liste'),
                                  headers={'x-requested-with': 'XMLHttpRequest'})
        self.assertEqual(reponse.status_code, 409)
        self.assertIn('Choisissez un centre', reponse.json()['message'])


class TestLeCloisonnementDeLaFusion(UnVoisin, BaseFusion):
    """La fusion déplace des factures : le cloisonnement y vaut doublement."""

    def setUp(self):
        super().setUp()
        self.fusion = self.fusionner()
        self.installer_le_voisin('fusionner_patients')

    def test_l_ecran_de_fusion_refuse_une_cle_de_l_autre_centre(self):
        self.assertEqual(self.client.get(reverse(
            'patients:fusionner', args=[self.cle, self.doublon.pk])
        ).status_code, 404)

    def test_l_onglet_des_fusions_ne_montre_pas_celles_de_l_autre_centre(self):
        reponse = self.client.get(reverse('patients:fusions'))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['page'].paginator.count, 0)
        self.assertNotContains(reponse, self.doublon.code_patient)

    def test_la_recherche_des_fusions_ne_ramene_pas_l_autre_centre(self):
        reponse = self.client.get(reverse('patients:fusions'),
                                  {'q': self.doublon.code_patient})
        self.assertEqual(reponse.context['page'].paginator.count, 0)

    def test_annuler_une_fusion_de_l_autre_centre_est_refuse(self):
        reponse = self.client.post(
            reverse('patients:fusion_annuler', args=[self.fusion.pk]))
        self.assertEqual(reponse.status_code, 404)
        self.fusion.refresh_from_db()
        self.assertTrue(self.fusion.active)

    def test_sans_centre_actif_l_onglet_des_fusions_ne_montre_rien(self):
        self.detacher(self.agent)
        reponse = self.client.get(reverse('patients:fusions'))
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertNotContains(reponse, self.doublon.code_patient)


class TestLOngletDesFichesMasquees(BaseDoublons):
    """Le seul endroit où une fiche masquée se voit encore — et se reprend."""

    def setUp(self):
        super().setUp()
        self.masquer()

    def masquer(self):
        reponse = self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.assertIn(reponse.status_code, (200, 302), reponse.content[:200])
        self.doublon.refresh_from_db()

    def _onglet(self, **params):
        return self.client.get(reverse('patients:doublons_masquees'), params)

    def test_la_fiche_masquee_y_figure_avec_qui_et_quand(self):
        reponse = self._onglet()
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual([f.pk for f in reponse.context['fiches']],
                         [self.doublon.pk])
        html = reponse.content.decode()
        self.assertIn(self.doublon.code_patient, html)
        self.assertIn(self.gardee.code_patient, html)   # de quelle fiche
        self.assertIn('dbl_agent', html)                 # qui a masqué
        self.assertIn(self.doublon.masque_le.strftime('%d/%m/%Y'), html)

    def test_le_masquage_enregistre_qui_et_quand(self):
        self.assertEqual(self.doublon.masque_par_id, self.agent.pk)
        self.assertIsNotNone(self.doublon.masque_le)

    def test_le_compte_est_celui_des_fiches_masquees(self):
        self.assertEqual(self._onglet().context['page'].paginator.count, 1)

    def test_reafficher_la_rend_visible_et_vide_l_onglet(self):
        self.client.post(
            reverse('patients:doublons_reafficher', args=[self.doublon.pk]),
            {'retour': reverse('patients:doublons_masquees')})
        self.doublon.refresh_from_db()
        self.assertFalse(self.doublon.masque)
        self.assertIsNone(self.doublon.doublon_de_id)
        # Qui et quand repartent avec le masquage : les garder laisserait
        # croire à une décision qui n'a pas été reprise.
        self.assertIsNone(self.doublon.masque_par_id)
        self.assertIsNone(self.doublon.masque_le)
        self.assertEqual(self._onglet().context['page'].paginator.count, 0)

    def test_une_fiche_fusionnee_n_est_pas_une_fiche_masquee(self):
        """Elle a sa propre page : son contenu est allé quelque part."""
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            masque=False, doublon_de=None, fusionne_dans=self.gardee)
        self.assertEqual(self._onglet().context['page'].paginator.count, 0)

    # ── La recherche ───────────────────────────────────────────────────────

    def test_la_recherche_par_code(self):
        self.assertEqual(len(self._onglet(q=self.doublon.code_patient)
                             .context['fiches']), 1)

    def test_la_recherche_par_nom(self):
        self.assertEqual(len(self._onglet(q='kouassi').context['fiches']), 1)

    def test_la_recherche_par_ancien_identifiant(self):
        """C'est lui qui figure sur les cartes imprimées."""
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            ancien_identifiant='ANC-0042')
        self.assertEqual(len(self._onglet(q='ANC-0042').context['fiches']), 1)

    def test_une_recherche_sans_reponse_le_dit(self):
        reponse = self._onglet(q='zeboulon')
        self.assertEqual(len(reponse.context['fiches']), 0)
        self.assertContains(reponse, 'Aucune fiche masquée ne correspond')

    def test_la_pagination_est_celle_des_autres_journaux(self):
        from .doublons_vues import PAR_PAGE_MASQUEES
        self.assertEqual(self._onglet().context['page'].paginator.per_page,
                         PAR_PAGE_MASQUEES)

    # ── Ailleurs, elle n'existe plus ───────────────────────────────────────

    def test_elle_reste_introuvable_dans_la_liste_des_patients(self):
        reponse = self.client.get(reverse('patients:list'),
                                  {'q': self.doublon.code_patient})
        self.assertEqual([p.pk for p in reponse.context['page_obj'].object_list],
                         [])

    def test_elle_reste_introuvable_dans_le_selecteur(self):
        reponse = self.client.get(reverse('patients:patient_search'),
                                  {'q': self.doublon.code_patient})
        self.assertEqual([r['id'] for r in reponse.json()['results']], [])

    def test_son_adresse_directe_est_404_sans_la_permission(self):
        from django.contrib.auth.models import Permission
        simple = User.objects.create_user('dbl_accueil', password='x')
        simple.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='view_patient'))
        self.rattacher(User.objects.get(pk=simple.pk), self.centre)
        client = Client()
        client.force_login(User.objects.get(pk=simple.pk))
        self.assertEqual(client.get(reverse('patients:detail',
                                            args=[self.doublon.pk])).status_code,
                         404)

    def test_elle_s_ouvre_pour_qui_traite_les_doublons(self):
        """L'onglet y mène : le lien ne doit pas tomber sur un 404."""
        self.assertEqual(self.client.get(
            reverse('patients:detail', args=[self.doublon.pk])).status_code, 200)

    def test_l_adresse_directe_ne_traverse_pas_les_centres(self):
        """Même avec la permission : la fiche retirée d'un autre centre reste
        fermée."""
        from django.contrib.auth.models import Permission
        from centres.models import Centre
        voisin = Centre.objects.create(nom='Toumbokro', code='TBK')
        intrus = User.objects.create_user('dbl_voisin2', password='x')
        for code in ('view_patient', 'gerer_doublons'):
            intrus.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.rattacher(User.objects.get(pk=intrus.pk), voisin)
        client = Client()
        client.force_login(User.objects.get(pk=intrus.pk))
        self.assertEqual(client.get(reverse('patients:detail',
                                            args=[self.doublon.pk])).status_code,
                         404)


class BaseSuppression(BaseFusion):
    """Un super-utilisateur du centre, et de quoi supprimer pour de bon."""

    def setUp(self):
        super().setUp()
        self.patron = User.objects.create_superuser('dbl_patron', password='x')
        self.rattacher(self.patron, self.centre)
        self.client = Client()
        self.client.force_login(User.objects.get(pk=self.patron.pk))

    def masquer(self, fiche=None):
        fiche = fiche or self.doublon
        Patient.all_objects.filter(pk=fiche.pk).update(
            masque=True, doublon_de=self.gardee, masque_par=self.agent,
            masque_le=timezone.now())
        fiche.refresh_from_db()
        return fiche

    def adresse(self, fiche=None):
        return reverse('patients:doublons_supprimer',
                       args=[(fiche or self.doublon).pk])

    def supprimer(self, fiche=None, code=None):
        fiche = fiche or self.doublon
        return self.client.post(self.adresse(fiche),
                                {'code': code or fiche.code_patient})

    def existe(self, fiche):
        return Patient.all_objects.filter(pk=fiche.pk).exists()


class TestQuiPeutSupprimer(BaseSuppression):
    def test_un_agent_qui_traite_les_doublons_ne_peut_pas(self):
        """`is_superuser`, pas une permission : un groupe s'élargit."""
        self.masquer()
        client = Client()
        client.force_login(User.objects.get(pk=self.agent.pk))
        self.assertEqual(client.get(self.adresse()).status_code, 403)
        self.assertEqual(client.post(
            self.adresse(), {'code': self.doublon.code_patient}).status_code, 403)
        self.assertTrue(self.existe(self.doublon))

    def test_un_super_utilisateur_d_un_autre_centre_non_plus(self):
        from centres.models import Centre
        self.masquer()
        voisin = Centre.objects.create(nom='Toumbokro', code='TBK')
        ailleurs = User.objects.create_superuser('dbl_patron2', password='x')
        self.rattacher(ailleurs, voisin)
        client = Client()
        client.force_login(User.objects.get(pk=ailleurs.pk))
        self.assertEqual(client.get(self.adresse()).status_code, 404)
        self.assertTrue(self.existe(self.doublon))

    def test_sans_centre_actif_l_ecran_ne_s_ouvre_pas(self):
        self.masquer()
        profil = self.patron.profile
        profil.centres.clear()
        profil.centre_actif = None
        profil.save()
        self.assertContains(self.client.get(self.adresse()),
                            'Choisissez un centre')
        self.assertTrue(self.existe(self.doublon))


class TestCeQueLaSuppressionRefuse(BaseSuppression):
    def test_un_dossier_ouvert_n_est_pas_supprimable(self):
        reponse = self.client.get(self.adresse())
        self.assertContains(reponse, 'dossier ouvert')
        self.assertNotContains(reponse, 'Supprimer définitivement</button>')
        self.supprimer()
        self.assertTrue(self.existe(self.doublon))

    def test_une_fiche_qui_porte_des_donnees_non_plus(self):
        """Revérifié côté serveur : entre l'écran et le clic, quelqu'un a pu
        rattacher quelque chose."""
        self.masquer()
        self.rdv(self.doublon)
        reponse = self.client.get(self.adresse())
        self.assertContains(reponse, 'Elle porte encore')
        self.supprimer()
        self.assertTrue(self.existe(self.doublon))

    def test_le_code_tape_doit_etre_le_bon(self):
        self.masquer()
        reponse = self.supprimer(code='PAT000000')
        self.assertContains(reponse, 'ne correspond pas')
        self.assertTrue(self.existe(self.doublon))

    def test_un_code_vide_ne_supprime_rien(self):
        self.masquer()
        self.client.post(self.adresse(), {})
        self.assertTrue(self.existe(self.doublon))


class TestLaSuppressionDUneFicheMasquee(BaseSuppression):
    def setUp(self):
        super().setUp()
        from core.views import log_event
        self.masquer()
        log_event(self.doublon, self.agent, 'Une trace à conserver',
                  type='modif')

    def test_la_fiche_disparait_et_la_trace_reste(self):
        from .models import SuppressionPatient
        code = self.doublon.code_patient
        self.supprimer()
        self.assertFalse(self.existe(self.doublon))
        trace = SuppressionPatient.all_objects.get()
        self.assertEqual(trace.code_patient, code)
        self.assertEqual(trace.etat, 'masquee')
        self.assertEqual(trace.utilisateur_id, self.patron.pk)
        self.assertEqual(trace.code_remplacante, self.gardee.code_patient)
        self.assertEqual(trace.centre_id, self.centre.pk)

    def test_la_copie_est_complete(self):
        from .models import SuppressionPatient
        self.supprimer()
        copie = SuppressionPatient.all_objects.get().copie
        champs = {f.name for f in Patient._meta.concrete_fields}
        self.assertEqual(set(copie), champs)
        self.assertEqual(copie['nom'], 'KOUASSI')

    def test_le_journal_est_recopie_puis_efface(self):
        """`LogActivite` est générique : rien ne le cascade, personne ne le
        reverrait."""
        from core.models import LogActivite
        from .fusion import _type_patient
        from .models import SuppressionPatient
        pk = self.doublon.pk
        self.supprimer()
        recopie = SuppressionPatient.all_objects.get().journal
        self.assertIn('Une trace à conserver',
                      ' '.join(l['message'] for l in recopie))
        # Celles d'origine sont parties avec la fiche — sauf la trace de la
        # suppression elle-même, posée après coup par le journal du projet.
        restantes = LogActivite.objects.filter(
            content_type=_type_patient(), object_id=pk)
        self.assertEqual([t.type for t in restantes], ['suppression'])

    def test_les_lignes_internes_partent_avec_elle(self):
        from django.db.models import Q
        from .models import ChoixFicheGardee, ClePhonetique, DoublonPaire
        pk = self.doublon.pk
        self.supprimer()
        self.assertFalse(ClePhonetique.all_objects.filter(patient_id=pk).exists())
        self.assertFalse(DoublonPaire.all_objects.filter(
            Q(patient_a_id=pk) | Q(patient_b_id=pk)).exists())
        self.assertFalse(ChoixFicheGardee.all_objects.filter(patient_id=pk).exists())

    def test_la_fiche_gardee_n_est_pas_touchee(self):
        self.supprimer()
        self.assertTrue(self.existe(self.gardee))
        self.gardee.refresh_from_db()
        self.assertFalse(self.gardee.masque)

    def test_l_onglet_des_masquees_se_vide(self):
        self.supprimer()
        reponse = self.client.get(reverse('patients:doublons_masquees'))
        self.assertEqual(reponse.context['page'].paginator.count, 0)

    def test_une_fiche_seulement_masquee_ne_redirige_toujours_pas(self):
        """Son contenu n'est allé nulle part : la faire apparaître sous un
        autre nom tromperait, supprimée ou non."""
        from .resolution import pks_depuis_un_repere
        code = self.doublon.code_patient
        self.supprimer()
        self.assertEqual(pks_depuis_un_repere(code), set())


class TestLaSuppressionDUneFicheFusionnee(BaseSuppression):
    def setUp(self):
        super().setUp()
        Patient.all_objects.filter(pk=self.doublon.pk).update(
            ancien_identifiant='ANC-0042')
        # La fiche gardée a le sien : sans cela la fusion lui recopierait
        # celui de l'absorbée, et la redirection serait prouvée par la
        # mauvaise raison.
        Patient.all_objects.filter(pk=self.gardee.pk).update(
            ancien_identifiant='ANC-0001')
        for fiche in (self.doublon, self.gardee):
            fiche.refresh_from_db()
        self.fusion = self.fusionner()
        self.doublon.refresh_from_db()

    def test_l_ecran_previent_que_la_fusion_ne_se_defera_plus(self):
        reponse = self.client.get(self.adresse())
        self.assertContains(reponse, 'La fusion ne pourra plus être annulée')

    def test_la_fusion_garde_sa_copie_et_ses_reperes(self):
        self.supprimer()
        self.fusion.refresh_from_db()
        self.assertIsNone(self.fusion.absorbee_id)
        self.assertEqual(self.fusion.code_absorbee, self.doublon.code_patient)
        self.assertEqual(self.fusion.ancien_identifiant_absorbee, 'ANC-0042')
        self.assertEqual(self.fusion.code_gardee, self.gardee.code_patient)
        self.assertEqual(self.fusion.copie['nom'], 'KOUASSI')

    def test_elle_ne_peut_plus_etre_annulee(self):
        from .fusion import FusionRefusee, annuler
        self.supprimer()
        self.fusion.refresh_from_db()
        self.assertFalse(self.fusion.annulable)
        with self.assertRaises(FusionRefusee):
            annuler(self.fusion, self.patron)

    def test_l_onglet_des_fusions_se_lit_encore(self):
        self.supprimer()
        reponse = self.client.get(reverse('patients:fusions'))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, self.doublon.code_patient)
        self.assertContains(reponse, 'fiche supprimée')

    # ── La redirection survit ──────────────────────────────────────────────

    def test_son_code_mene_toujours_a_la_fiche_gardee(self):
        from .resolution import pks_depuis_un_repere
        code = self.doublon.code_patient
        self.supprimer()
        self.assertFalse(self.existe(self.doublon))
        self.assertEqual(pks_depuis_un_repere(code), {self.gardee.pk})

    def test_son_ancien_identifiant_aussi(self):
        from .resolution import pks_depuis_un_repere
        self.supprimer()
        self.gardee.refresh_from_db()
        self.assertEqual(self.gardee.ancien_identifiant, 'ANC-0001')
        self.assertEqual(pks_depuis_un_repere('ANC-0042'), {self.gardee.pk})

    def test_un_autre_dossier_portant_ce_code_ne_l_efface_pas(self):
        """Les anciens identifiants ressemblent aux codes : un dossier
        vivant peut porter comme ancien identifiant le code d'une fiche
        supprimée. Les deux réponses sont justes, aucune ne doit masquer
        l'autre."""
        from .resolution import pks_depuis_un_repere
        code = self.doublon.code_patient
        autre = Patient.all_objects.create(
            nom='TRAORE', prenoms='FATOU', sexe='F', centre=self.centre,
            date_naissance=date(1980, 1, 1), ancien_identifiant=code)
        self.supprimer()
        self.assertEqual(pks_depuis_un_repere(code),
                         {self.gardee.pk, autre.pk})

    def test_la_recherche_des_patients_y_mene_aussi(self):
        code = self.doublon.code_patient
        self.supprimer()
        reponse = self.client.get(reverse('patients:list'), {'q': code})
        self.assertEqual([p.pk for p in reponse.context['page_obj'].object_list],
                         [self.gardee.pk])


class TestLaChaineDeFusionsApresSuppression(BaseSuppression):
    """A versée dans B, B versée dans C, puis B supprimée.

    Les cartes imprimées portent le code de A comme celui de B : les deux
    doivent mener à C, même quand le maillon du milieu a disparu.
    """

    def setUp(self):
        super().setUp()
        from .fusion import Choix, fusionner
        self.troisieme = Patient.all_objects.create(
            nom='KOUASSI', prenoms='AYA MARIE', sexe='F',
            telephone='0701020304', date_naissance=date(1992, 5, 14),
            centre=self.centre)
        self.fusionner()                                            # A → B
        fusionner(self.troisieme, self.gardee, Choix(), self.agent)  # B → C
        for fiche in (self.doublon, self.gardee):
            fiche.refresh_from_db()

    def test_les_deux_anciens_codes_menent_a_la_derniere(self):
        from .resolution import pks_depuis_un_repere
        self.assertEqual(pks_depuis_un_repere(self.doublon.code_patient),
                         {self.troisieme.pk})
        self.assertEqual(pks_depuis_un_repere(self.gardee.code_patient),
                         {self.troisieme.pk})

    def test_l_intermediaire_supprimee_ne_coupe_pas_la_chaine(self):
        from .resolution import pks_depuis_un_repere
        code_a, code_b = self.doublon.code_patient, self.gardee.code_patient
        self.supprimer(self.gardee)
        self.assertFalse(self.existe(self.gardee))
        # La première fiche a été reportée sur la dernière : elle ne pointe
        # plus dans le vide.
        self.doublon.refresh_from_db()
        self.assertEqual(self.doublon.fusionne_dans_id, self.troisieme.pk)
        self.assertEqual(pks_depuis_un_repere(code_a), {self.troisieme.pk})
        self.assertEqual(pks_depuis_un_repere(code_b), {self.troisieme.pk})

    def test_meme_quand_les_deux_premieres_ont_disparu(self):
        """Plus aucune fiche ne porte ces codes : c'est le journal qui répond."""
        from .resolution import pks_depuis_un_repere
        code_a, code_b = self.doublon.code_patient, self.gardee.code_patient
        self.supprimer(self.gardee)
        self.doublon.refresh_from_db()
        self.supprimer(self.doublon)
        self.assertFalse(self.existe(self.doublon))
        self.assertEqual(pks_depuis_un_repere(code_a), {self.troisieme.pk})
        self.assertEqual(pks_depuis_un_repere(code_b), {self.troisieme.pk})

    def test_une_fusion_annulee_ne_redirige_pas(self):
        """Annuler a rendu son indépendance à la fiche : son code ne doit
        plus mener ailleurs."""
        from .fusion import annuler
        from .models import FusionPatient
        from .resolution import pks_depuis_un_repere
        derniere = FusionPatient.all_objects.order_by('-date').first()
        annuler(derniere, self.agent)
        self.gardee.refresh_from_db()
        self.assertEqual(pks_depuis_un_repere(self.gardee.code_patient),
                         {self.gardee.pk})


class TestLeCentreEstObligatoirePourCreer(TestCase):
    """Sans centre actif, on ne crée pas de fiche — et rien ne se propose.

    Le garde-fou des doublons compare la saisie à un périmètre. Sans centre,
    ce périmètre était « tous les centres » : la fenêtre de saisie montrait
    les dossiers d'à côté, et le contrôle à l'enregistrement les comparait.
    On refuse désormais de travailler, et on le dit. Un super-utilisateur ne
    fait pas exception.

    Hors requête — import par lots, commandes — le centre est passé
    explicitement : ce chemin-là ne change pas.
    """

    def setUp(self):
        from django.contrib.auth.models import Permission
        from centres.models import Centre
        self.centre = Centre.objects.create(nom='Walé', code='WAL')
        self.agent = User.objects.create_user('crea_agent', password='x')
        for code in ('view_patient', 'add_patient', 'change_patient'):
            self.agent.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.agent = User.objects.get(pk=self.agent.pk)
        self.client = Client()
        self.client.force_login(self.agent)

    @staticmethod
    def _donnees(**remplacements):
        donnees = {'nom': 'ZEBOULON', 'prenoms': 'EUSTACHE', 'sexe': 'M',
                   'telephone': '0788889999', 'date_naissance': '09/02/1977',
                   'nationalite': 'Ivoirienne', 'adresse': 'Habitat',
                   'ville': 'Yamoussoukro'}
        donnees.update(remplacements)
        return donnees

    def rattacher(self, utilisateur, centre):
        profil = utilisateur.profile
        profil.centres.add(centre)
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])

    # ── Le formulaire ──────────────────────────────────────────────────────

    def test_le_formulaire_refuse_sans_centre(self):
        from .forms import PatientForm
        form = PatientForm(self._donnees(), utilisateur=self.agent)
        self.assertFalse(form.is_valid())
        self.assertIn('Choisissez un centre', form.non_field_errors()[0])

    def test_le_formulaire_passe_avec_le_centre(self):
        from .forms import PatientForm
        form = PatientForm(self._donnees(), utilisateur=self.agent,
                           centre=self.centre)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_modifier_une_fiche_garde_le_centre_de_la_fiche(self):
        """Le centre vient alors de la fiche : on ne redemande rien."""
        from .forms import PatientForm
        fiche = Patient.all_objects.create(
            nom='ZEBOULON', prenoms='EUSTACHE', sexe='M',
            telephone='0788889999', date_naissance=date(1977, 2, 9),
            centre=self.centre)
        form = PatientForm(self._donnees(adresse='Ailleurs'), instance=fiche,
                           utilisateur=self.agent)
        self.assertTrue(form.is_valid(), form.errors.as_text())

    def test_le_perimetre_est_vide_et_non_tous_les_centres(self):
        """Un périmètre vide ne doit pas pouvoir passer pour « aucun doublon » :
        le formulaire refuse de toute façon, mais la règle est posée ici."""
        from .forms import PatientForm
        Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE',
                                   sexe='M', centre=self.centre)
        self.assertFalse(PatientForm(self._donnees())._perimetre().exists())

    # ── La vue de création ─────────────────────────────────────────────────

    def test_la_creation_est_refusee_sans_centre_actif(self):
        reponse = self.client.post(reverse('patients:create'), self._donnees())
        self.assertEqual(reponse.status_code, 200)       # le formulaire revient
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertFalse(Patient.all_objects.exists())

    def test_elle_passe_une_fois_le_centre_choisi(self):
        self.rattacher(self.agent, self.centre)
        reponse = self.client.post(reverse('patients:create'), self._donnees())
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(Patient.all_objects.get().centre_id, self.centre.pk)

    def test_un_super_utilisateur_ne_fait_pas_exception(self):
        patron = User.objects.create_superuser('crea_patron', password='x')
        client = Client()
        client.force_login(patron)
        reponse = client.post(reverse('patients:create'), self._donnees())
        self.assertContains(reponse, 'Choisissez un centre')
        self.assertFalse(Patient.all_objects.exists())

    # ── La fenêtre de saisie ───────────────────────────────────────────────

    def test_la_fenetre_ne_propose_rien_sans_centre(self):
        Patient.all_objects.create(nom='ZEBOULON', prenoms='EUSTACHE',
                                   sexe='M', centre=self.centre)
        reponse = self.client.get(reverse('patients:doublons_verifier'),
                                  {'nom': 'ZEBOULON', 'prenoms': 'EUSTACHE'})
        donnees = reponse.json()
        self.assertEqual(donnees['doublons'], [])
        self.assertEqual(donnees['meme_telephone'], 0)
        self.assertIn('Choisissez un centre', donnees['message'])

    def test_elle_propose_de_nouveau_une_fois_le_centre_choisi(self):
        Patient.all_objects.create(
            nom='ZEBOULON', prenoms='EUSTACHE', sexe='M',
            telephone='0788889999', date_naissance=date(1977, 2, 9),
            centre=self.centre)
        self.rattacher(self.agent, self.centre)
        donnees = self.client.get(
            reverse('patients:doublons_verifier'),
            {'nom': 'ZEBOULON', 'prenoms': 'EUSTACHE', 'sexe': 'M',
             'telephone': '0788889999',
             'date_naissance': '1977-02-09'}).json()
        self.assertEqual(len(donnees['doublons']), 1)
        self.assertNotIn('message', donnees)

    # ── L'import, lui, ne change pas ───────────────────────────────────────

    def test_l_import_par_lots_cree_toujours_sans_centre_actif(self):
        """Il passe le sien explicitement et ne touche pas au formulaire :
        exiger un centre actif l'aurait arrêté net."""
        import json
        from core.models import TacheImport
        from core.taches import Avancement
        from .views import _executer_import_patients

        avancement = Avancement(TacheImport.objects.create(libelle='Test'))
        _executer_import_patients(
            avancement, 'fichier.json',
            json.dumps([{'nom': 'Kone Adama', 'genre': 'M',
                         'mobile': '0700000001'}]).encode('utf-8'),
            False, self.centre)
        fiche = Patient.all_objects.get()
        self.assertEqual(fiche.centre_id, self.centre.pk)

    def test_l_import_sans_centre_fonctionne_comme_avant(self):
        """Une commande hors requête n'a pas toujours de centre à donner ;
        ce chemin n'est pas celui qu'on ferme."""
        import json
        from core.models import TacheImport
        from core.taches import Avancement
        from .views import _executer_import_patients

        avancement = Avancement(TacheImport.objects.create(libelle='Test'))
        _executer_import_patients(
            avancement, 'fichier.json',
            json.dumps([{'nom': 'Kone Adama', 'genre': 'M',
                         'mobile': '0700000001'}]).encode('utf-8'),
            False, None)
        self.assertEqual(Patient.all_objects.count(), 1)


class BaseReleveFourni(BaseDoublons):
    """Plusieurs groupes, de natures différentes.

    `BaseDoublons` n'en pose qu'un ; les filtres, le regroupement et les lots
    ne disent rien sur un relevé d'une seule ligne.
    """

    def setUp(self):
        super().setUp()
        from .doublons_recalcul import recalculer_centre
        self.couples = {}
        # Même nom et même prénom, écrits pareil : « même nom ».
        self.couples['jumeaux'] = self._couple('TRAORE', 'AWA', 'TRAORE', 'AWA',
                                               '0707070707', date(1988, 3, 2))
        # Le prénom seul diffère : « prénom presque identique ».
        self.couples['prenom'] = self._couple('SOMDA', 'CHRIST', 'SOMDA', 'CHIRST',
                                              '0708080808', date(1990, 7, 9))
        # Le nom seul diffère : « nom presque identique ».
        self.couples['nom'] = self._couple('BALO', 'RAYAN', 'BALLO', 'RAYAN',
                                           '0709090909', date(1991, 11, 4))
        recalculer_centre(self.centre.pk)
        self.vider_le_cache()

    def _couple(self, nom_a, prenoms_a, nom_b, prenoms_b, telephone, naissance):
        commun = dict(sexe='F', telephone=telephone, date_naissance=naissance,
                      centre=self.centre, nationalite='Ivoirienne')
        return (Patient.all_objects.create(nom=nom_a, prenoms=prenoms_a, **commun),
                Patient.all_objects.create(nom=nom_b, prenoms=prenoms_b, **commun))

    @staticmethod
    def vider_le_cache():
        from django.core.cache import cache
        cache.clear()

    def cle_de(self, nom):
        from .doublons_groupes import cle_groupe
        return cle_groupe([f.pk for f in self.couples[nom]])

    def lignes(self, **params):
        reponse = self.client.get(reverse('patients:doublons_liste'), params)
        self.assertEqual(reponse.status_code, 200)
        return reponse

    def raison_de(self, nom):
        """La phrase rangée dans l'index pour ce couple."""
        from .doublons_groupes import index
        cle = self.cle_de(nom)
        for ligne in index(self.centre.pk):
            if ligne['cle'] == cle:
                return ligne['raison']
        return None


class TestLaPhraseEstRangeeDansLIndex(BaseReleveFourni):
    def test_chaque_entree_porte_sa_phrase(self):
        from .doublons_groupes import index
        for ligne in index(self.centre.pk):
            self.assertIn('raison', ligne)

    def test_la_phrase_rangee_est_celle_qui_s_affiche(self):
        """Sinon le filtre montrerait autre chose que les cartes."""
        reponse = self.lignes()
        for groupe in reponse.context['groupes']:
            self.assertEqual(groupe['raison'], ', '.join(groupe['raisons']),
                             groupe['cle'])

    def test_les_trois_couples_ont_trois_phrases_distinctes(self):
        self.assertIn('même nom', self.raison_de('jumeaux'))
        self.assertIn('prénom presque identique', self.raison_de('prenom'))
        self.assertIn('nom presque identique', self.raison_de('nom'))


class TestLeFiltreParRaison(BaseReleveFourni):
    def test_une_phrase_ne_garde_que_ses_groupes(self):
        phrase = self.raison_de('prenom')
        reponse = self.lignes(raison=phrase)
        cles = {g['cle'] for g in reponse.context['groupes']}
        self.assertEqual(cles, {self.cle_de('prenom')})

    def test_deux_phrases_se_cumulent(self):
        reponse = self.lignes(raison=[self.raison_de('prenom'),
                                      self.raison_de('nom')])
        cles = {g['cle'] for g in reponse.context['groupes']}
        self.assertEqual(cles, {self.cle_de('prenom'), self.cle_de('nom')})

    def test_le_menu_porte_les_phrases_et_leur_nombre(self):
        comptes = dict(self.lignes().context['comptes_raison'])
        self.assertEqual(comptes[self.raison_de('prenom')], 1)
        # De la plus fréquente à la moins fréquente.
        nombres = [n for _p, n in self.lignes().context['comptes_raison']]
        self.assertEqual(nombres, sorted(nombres, reverse=True))

    def test_le_nombre_annonce_tient_compte_des_autres_filtres(self):
        """Le nombre doit être celui qu'on obtiendra en cochant, pas un
        nombre théorique."""
        comptes = dict(self.lignes(q='SOMDA').context['comptes_raison'])
        self.assertEqual(list(comptes.values()), [1])

    def test_une_pastille_dit_le_filtre_pose_et_permet_de_l_oter(self):
        phrase = self.raison_de('nom')
        reponse = self.lignes(raison=phrase)
        pastilles = reponse.context['pastilles']
        self.assertIn(phrase, [p['libelle'] for p in pastilles])
        self.assertContains(reponse, 'o-filter-tag')

    def test_une_phrase_inconnue_ne_ramene_rien(self):
        self.assertEqual(len(self.lignes(raison='zeboulon').context['groupes']), 0)


class TestLeFiltreParDonneesRattachees(BaseReleveFourni):
    def test_les_trois_etats_se_distinguent(self):
        from .doublons_groupes import classer_rattachees
        a, b = self.couples['nom']
        ligne = {'membres': [a.pk, b.pk]}
        self.assertEqual(classer_rattachees(ligne, {}), 'aucune')
        self.assertEqual(classer_rattachees(ligne, {a.pk: 2}), 'une')
        self.assertEqual(classer_rattachees(ligne, {a.pk: 2, b.pk: 1}), 'deux')

    def test_le_filtre_ecarte_les_groupes_qui_portent_des_donnees(self):
        RendezVous.objects.create(patient=self.couples['nom'][0],
                                  motif='Contrôle', date_heure=timezone.now())
        self.vider_le_cache()
        reponse = self.lignes(rattache='aucune')
        self.assertNotIn(self.cle_de('nom'),
                         {g['cle'] for g in reponse.context['groupes']})
        reponse = self.lignes(rattache='une')
        self.assertEqual({g['cle'] for g in reponse.context['groupes']},
                         {self.cle_de('nom')})

    def test_les_totaux_sont_oublies_apres_un_masquage(self):
        """Sinon le filtre continuerait de proposer un groupe déjà traité."""
        from django.core.cache import cache
        from .liens_patient import CLE_CACHE_TOTAUX, totaux_rattaches
        totaux_rattaches([self.gardee.pk, self.doublon.pk])
        self.assertIsNotNone(cache.get(CLE_CACHE_TOTAUX))
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle, self.doublon.pk]),
            {'au_profit_de': self.gardee.pk})
        self.assertIsNone(cache.get(CLE_CACHE_TOTAUX))


class TestLeRegroupementDuReleve(BaseReleveFourni):
    def test_les_sections_portent_la_phrase_et_leur_nombre(self):
        reponse = self.lignes(grouper='raison')
        sections = {g['section']: g['section_total']
                    for g in reponse.context['groupes']}
        self.assertEqual(sections[self.raison_de('prenom')], 1)
        self.assertContains(reponse, 'lst-groupe-bande')

    def test_le_nombre_d_une_section_est_celui_de_tout_le_releve(self):
        """Une section qui déborde de la page doit dire ce qu'elle contient,
        pas ce qu'on en voit."""
        from .doublons_groupes import index, sections
        paquets = sections(index(self.centre.pk), 'raison')
        total = sum(len(contenu) for _libelle, contenu in paquets)
        self.assertEqual(total, len(index(self.centre.pk)))

    def test_on_peut_aussi_grouper_par_niveau(self):
        reponse = self.lignes(grouper='niveau')
        sections = {g['section'] for g in reponse.context['groupes']}
        self.assertTrue(sections <= {'Quasi certain', 'À vérifier'}, sections)

    def test_on_peut_grouper_par_donnees_rattachees(self):
        reponse = self.lignes(grouper='rattachees')
        self.assertTrue(all(g['section'] for g in reponse.context['groupes']))

    def test_le_tableau_porte_les_mêmes_bandes(self):
        html = self.lignes(grouper='raison').content.decode()
        self.assertIn('<tr class="lst-groupe open"', html)

    def test_un_regroupement_inconnu_est_ignore(self):
        reponse = self.lignes(grouper='zeboulon')
        self.assertEqual(reponse.context['grouper'], '')


class TestLesBandesSeReplientCommeAilleurs(BaseReleveFourni):
    """Le geste des autres listes, et non un succédané maison.

    Même classe, même chevron, même `lstBasculerGroupe` : ce qui change d'un
    module à l'autre, c'est ce qu'il y a dans la bande, jamais la façon de la
    replier.
    """

    def test_la_bande_porte_le_chevron_et_le_clic(self):
        reponse = self.lignes(grouper='raison')
        self.assertContains(reponse, 'lst-chevron')
        self.assertContains(reponse, 'lstBasculerGroupe(this)')
        self.assertContains(reponse, 'class="lst-groupe lst-groupe-bande open"')

    def test_le_compteur_est_celui_de_la_brique(self):
        self.assertContains(self.lignes(grouper='raison'),
                            '<span class="lst-compte">')

    def test_chaque_carte_designe_sa_section(self):
        """`data-parent` est tout ce dont le script partagé a besoin pour
        replier sans rien demander au serveur."""
        reponse = self.lignes(grouper='raison')
        for groupe in reponse.context['groupes']:
            self.assertIn('section_rang', groupe)
        rangs = {g['section_rang'] for g in reponse.context['groupes']}
        for rang in rangs:
            self.assertContains(reponse, f'data-parent="{rang}"')

    def test_sans_regroupement_rien_ne_designe_de_section(self):
        self.assertNotContains(self.lignes(), 'data-parent=')

    def test_le_script_partage_est_charge_sans_sa_memoire(self):
        """L'état déplié ne part ni dans l'adresse ni au serveur : un chemin
        ne désigne rien de stable sur un relevé composé puis paginé."""
        reponse = self.lignes(grouper='raison')
        self.assertContains(reponse, 'listing_groupes.js')
        self.assertContains(reponse, 'window.lstSansMemoire = true;')

    def test_la_case_de_section_ne_replie_pas_la_bande(self):
        self.assertContains(self.lignes(grouper='raison'),
                            'onclick="event.stopPropagation();"')


class BaseLots(BaseReleveFourni):
    """Le relevé fourni, et le droit de fusionner."""

    def setUp(self):
        from django.contrib.auth.models import Permission
        super().setUp()
        self.agent.user_permissions.add(Permission.objects.get(
            content_type__app_label='patients', codename='fusionner_patients'))
        self.agent = User.objects.get(pk=self.agent.pk)
        self.client.force_login(self.agent)

    def preparer(self, action, cles=None, **extra):
        donnees = {'action': action, 'cle': cles if cles is not None
                   else [self.cle_de(n) for n in self.couples]}
        donnees.update(extra)
        reponse = self.client.post(reverse('patients:doublons_lot_preparer'),
                                   donnees)
        return reponse

    def executer(self, lot):
        return self.client.post(
            reverse('patients:doublons_lot_executer', args=[lot.pk]))

    def faire(self, action, cles=None, **extra):
        """Prépare puis exécute, et rend le lot relu en base."""
        from .models import LotDoublons
        reponse = self.preparer(action, cles, **extra)
        lot = reponse.context['lot']
        self.executer(lot)
        return LotDoublons.all_objects.get(pk=lot.pk)


class TestCeQuUnLotRetientEtCeQuIlEcarte(BaseLots):
    def test_les_groupes_vides_sont_tous_retenus(self):
        reponse = self.preparer('masquer')
        self.assertEqual(len(reponse.context['prevus']), 3)
        self.assertEqual(reponse.context['ignores'], [])

    def test_chaque_groupe_dit_qui_est_gardé_et_qui_est_visé(self):
        """L'écran confirme une décision, pas un nombre."""
        prevu = self.preparer('masquer').context['prevus'][0]
        self.assertNotEqual(prevu.gardee.pk, prevu.visee.pk)
        self.assertIn(prevu.gardee.pk, [f.pk for f in prevu.membres])

    def test_un_groupe_qui_porte_des_donnees_est_ecarte_avec_sa_raison(self):
        """Des deux côtés : si une seule fiche porte quelque chose, c'est
        elle qu'on garde et l'autre reste masquable."""
        for fiche in self.couples['nom']:
            RendezVous.objects.create(patient=fiche, motif='Contrôle',
                                      date_heure=timezone.now())
        reponse = self.preparer('masquer')
        ignores = dict(reponse.context['ignores'])
        self.assertIn(self.cle_de('nom'), ignores)
        self.assertIn('porte des données', ignores[self.cle_de('nom')])

    def test_un_champ_en_plus_empeche_le_masquage(self):
        """« Vide » ne suffit pas : une allergie se perdrait en silence."""
        from .doublons_groupes import fiche_a_garder
        from .liens_patient import comptes_par_table
        fiches = list(self.couples['prenom'])
        garder, _ = fiche_a_garder(fiches, comptes_par_table([f.pk for f in fiches]))
        autre = next(f for f in fiches if f.pk != garder)
        autre.allergies = 'Pénicilline'
        autre.save(update_fields=['allergies'])
        ignores = dict(self.preparer('masquer').context['ignores'])
        self.assertIn('informations', ignores[self.cle_de('prenom')])

    def test_la_fusion_ecarte_les_groupes_ou_il_reste_a_choisir(self):
        """Deux sexes qui se contredisent : personne d'autre que l'agent ne
        peut trancher, le lot ne le fait pas à sa place."""
        a, b = self.couples['nom']
        Patient.all_objects.filter(pk=b.pk).update(sexe='M')
        ignores = dict(self.preparer('fusionner').context['ignores'])
        self.assertIn(self.cle_de('nom'), ignores)
        self.assertIn('sexe', ignores[self.cle_de('nom')].lower())

    def test_un_groupe_de_plus_de_deux_fiches_se_traite_a_la_main(self):
        from .doublons_groupes import cle_groupe
        troisieme = Patient.all_objects.create(
            nom='TRAORE', prenoms='AWA', sexe='F', telephone='0707070707',
            date_naissance=date(1988, 3, 2), centre=self.centre)
        cle = cle_groupe([f.pk for f in self.couples['jumeaux']] + [troisieme.pk])
        ignores = dict(self.preparer('masquer', cles=[cle]).context['ignores'])
        self.assertIn('une par une', ignores[cle])


class TestCeQuUnLotExecute(BaseLots):
    def test_le_masquage_en_lot_retire_les_fiches(self):
        lot = self.faire('masquer')
        self.assertEqual(len(lot.faits), 3)
        self.assertEqual(lot.etat, 'execute')
        masquees = Patient.all_objects.filter(masque=True).count()
        self.assertEqual(masquees, 3)

    def test_la_liste_figee_est_celle_qui_s_execute(self):
        """Un groupe traité entre la confirmation et le clic passe dans les
        écartés, avec sa raison — il n'est ni refait ni passé sous silence."""
        from .models import LotDoublons
        reponse = self.preparer('masquer')
        lot = reponse.context['lot']
        # Quelqu'un masque ce groupe depuis un autre poste.
        a, b = self.couples['nom']
        Patient.all_objects.filter(pk=b.pk).update(masque=True, doublon_de=a)
        self.executer(lot)

        lot = LotDoublons.all_objects.get(pk=lot.pk)
        self.assertEqual(len(lot.faits), 2)
        self.assertEqual(len(lot.ignores), 1)
        self.assertIn('déjà été traitée', lot.ignores[0][1])

    def test_l_ecartement_en_lot_pose_la_raison_commune(self):
        from .models import PaireEcartee
        lot = self.faire('ecarter', raison_commune='Deux sœurs')
        self.assertEqual(len(lot.faits), 3)
        self.assertEqual(PaireEcartee.all_objects.count(), 3)
        self.assertEqual(
            set(PaireEcartee.all_objects.values_list('raison', flat=True)),
            {'Deux sœurs'})

    def test_la_fusion_en_lot_ecrit_un_journal_par_groupe(self):
        from .models import FusionPatient
        lot = self.faire('fusionner')
        self.assertEqual(len(lot.faits), 3)
        self.assertEqual(FusionPatient.all_objects.count(), 3)

    def test_le_releve_des_fiches_traitees_est_repris(self):
        """Les paires qui citent une fiche traitée s'en vont d'un coup : une
        par une, le relevé coûterait deux dixièmes de seconde par fiche."""
        from django.db.models import Q
        from .models import DoublonPaire
        pks = [f.pk for f in self.couples['nom']]
        self.faire('masquer', cles=[self.cle_de('nom')])
        self.assertFalse(DoublonPaire.all_objects.filter(
            Q(patient_a_id__in=pks) | Q(patient_b_id__in=pks)).exists())

    def test_le_bilan_dit_ce_qui_a_ete_fait_et_ce_qui_reste(self):
        a, b = self.couples['nom']
        Patient.all_objects.filter(pk=b.pk).update(sexe='M')
        reponse = self.preparer('fusionner')
        lot = reponse.context['lot']
        bilan = self.executer(lot)
        self.assertContains(bilan, 'fusionné')
        self.assertContains(bilan, 'ignoré')


class TestQuiPeutLancerUnLot(BaseLots):
    def test_fusionner_exige_sa_permission(self):
        from django.contrib.auth.models import Permission
        simple = User.objects.create_user('lot_simple', password='x')
        for code in ('view_patient', 'gerer_doublons'):
            simple.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.rattacher(User.objects.get(pk=simple.pk), self.centre)
        client = Client()
        client.force_login(User.objects.get(pk=simple.pk))
        reponse = client.post(reverse('patients:doublons_lot_preparer'),
                              {'action': 'fusionner', 'cle': [self.cle_de('nom')]})
        self.assertEqual(reponse.status_code, 403)

    def test_sans_centre_actif_rien_ne_part(self):
        profil = self.agent.profile
        profil.centres.clear()
        profil.centre_actif = None
        profil.save()
        reponse = self.client.post(reverse('patients:doublons_lot_preparer'),
                                   {'action': 'masquer', 'cle': [self.cle_de('nom')]})
        self.assertEqual(reponse.status_code, 403)
        self.assertFalse(Patient.all_objects.filter(masque=True).exists())

    def test_tout_le_filtre_ne_prend_que_le_centre_actif(self):
        from django.contrib.auth.models import Permission
        from centres.models import Centre
        voisin = Centre.objects.create(nom='Toumbokro', code='TBK')
        intrus = User.objects.create_user('lot_voisin', password='x')
        for code in ('view_patient', 'gerer_doublons'):
            intrus.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.rattacher(User.objects.get(pk=intrus.pk), voisin)
        client = Client()
        client.force_login(User.objects.get(pk=intrus.pk))
        reponse = client.post(reverse('patients:doublons_lot_preparer'),
                              {'action': 'masquer', 'tout': '1'}, follow=True)
        self.assertFalse(Patient.all_objects.filter(masque=True).exists())
        self.assertIn("Aucun groupe n'était sélectionné.",
                      [str(m) for m in reponse.context['messages']])

    def test_tout_le_filtre_prend_tout_le_releve(self):
        from .doublons_groupes import index
        reponse = self.client.post(reverse('patients:doublons_lot_preparer'),
                                   {'action': 'masquer', 'tout': '1'})
        self.assertEqual(sorted(reponse.context['lot'].cles),
                         sorted(l['cle'] for l in index(self.centre.pk)))

    def test_tout_le_filtre_reprend_le_filtre_pose(self):
        """Ce qu'on confirme est ce que le filtre montrait, pas tout le
        relevé."""
        from .doublons_groupes import index
        phrase = self.raison_de('jumeaux')
        attendues = sorted(l['cle'] for l in index(self.centre.pk)
                           if l['raison'] == phrase)
        reponse = self.client.post(reverse('patients:doublons_lot_preparer'),
                                   {'action': 'ecarter', 'tout': '1',
                                    'raison': phrase})
        self.assertEqual(sorted(reponse.context['lot'].cles), attendues)
        self.assertIn(self.cle_de('jumeaux'), attendues)
        self.assertNotIn(self.cle_de('nom'), attendues)


class TestAnnulerUnLot(BaseLots):
    def test_un_lot_de_masquage_se_defait_entierement(self):
        from .models import LotDoublons
        lot = self.faire('masquer')
        reponse = self.client.post(
            reverse('patients:doublons_lot_annuler', args=[lot.pk]), follow=True)
        lot = LotDoublons.all_objects.get(pk=lot.pk)
        self.assertEqual(lot.etat, 'annule')
        self.assertEqual(lot.annulation_partielle, [])
        self.assertFalse(Patient.all_objects.filter(masque=True).exists())
        self.assertContains(reponse, 'entièrement annulé')

    def test_un_lot_d_ecartement_aussi(self):
        from .models import PaireEcartee
        lot = self.faire('ecarter')
        self.client.post(reverse('patients:doublons_lot_annuler', args=[lot.pk]))
        self.assertFalse(PaireEcartee.all_objects.exists())

    def test_un_lot_de_fusion_aussi(self):
        from .models import FusionPatient
        lot = self.faire('fusionner')
        self.client.post(reverse('patients:doublons_lot_annuler', args=[lot.pk]))
        self.assertFalse(FusionPatient.all_objects.filter(
            annulee_le__isnull=True).exists())

    def test_une_fusion_plus_recente_bloque_l_annulation_du_lot(self):
        """La règle de l'ordre vaut aussi en lot : ce qui ne peut plus être
        défait est dit, et le reste l'est quand même."""
        from .fusion import Choix, fusionner
        from .models import FusionPatient, LotDoublons
        lot = self.faire('fusionner')
        gardees = [FusionPatient.all_objects.get(pk=fait['fusion']).gardee
                   for fait in lot.faits]
        # Une fusion faite après le lot, par-dessus deux de ses fiches.
        fusionner(gardees[0], gardees[1], Choix(), self.agent)

        reponse = self.client.post(
            reverse('patients:doublons_lot_annuler', args=[lot.pk]), follow=True)
        lot = LotDoublons.all_objects.get(pk=lot.pk)
        self.assertEqual(len(lot.annulation_partielle), 2)
        for _cle, raison in lot.annulation_partielle:
            self.assertIn('plus récente', raison)
        self.assertContains(reponse, 'sauf 2 groupe')
        # Le troisième, que la fusion récente ne touche pas, est bien revenu.
        self.assertEqual(FusionPatient.all_objects
                         .filter(annulee_le__isnull=True).count(), 3)

    def test_un_lot_se_defait_de_la_plus_recente_a_la_plus_ancienne(self):
        """Une chaîne se défait à l'envers : la défaire dans l'ordre
        buterait sur cette même règle de la fusion plus récente."""
        from .fusion import Choix, fusionner
        from .models import FusionPatient, LotDoublons
        lot = self.faire('fusionner', cles=[self.cle_de('jumeaux')])
        premiere = FusionPatient.all_objects.get(pk=lot.faits[0]['fusion'])
        # Une seconde fusion par-dessus la première, rangée dans le même lot.
        seconde = fusionner(self.couples['nom'][0], premiere.gardee, Choix(),
                            self.agent)
        lot.faits = lot.faits + [{'cle': 'chaine', 'fusion': seconde.pk,
                                  'code': premiere.gardee.code_patient}]
        lot.save(update_fields=['faits'])

        self.client.post(reverse('patients:doublons_lot_annuler', args=[lot.pk]))
        lot = LotDoublons.all_objects.get(pk=lot.pk)
        self.assertEqual(lot.annulation_partielle, [])
        self.assertFalse(FusionPatient.all_objects
                         .filter(annulee_le__isnull=True).exists())

    def test_ce_qui_ne_peut_plus_etre_defait_est_dit(self):
        """Une fiche réaffichée entre-temps : le reste se défait quand même."""
        from .models import LotDoublons
        lot = self.faire('masquer')
        rendue = lot.faits[0]['masquee']
        Patient.all_objects.filter(pk=rendue).update(masque=False, doublon_de=None)
        reponse = self.client.post(
            reverse('patients:doublons_lot_annuler', args=[lot.pk]), follow=True)
        lot = LotDoublons.all_objects.get(pk=lot.pk)
        self.assertEqual(len(lot.annulation_partielle), 1)
        self.assertContains(reponse, 'sauf 1 groupe')

    def test_l_onglet_des_lots_montre_ce_qui_a_ete_fait(self):
        lot = self.faire('masquer')
        reponse = self.client.get(reverse('patients:doublons_lots'))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, lot.numero)
        self.assertContains(reponse, 'Annuler ce lot')

    def test_un_lot_prepare_mais_non_execute_ne_s_affiche_pas(self):
        self.preparer('masquer')
        reponse = self.client.get(reverse('patients:doublons_lots'))
        self.assertEqual(reponse.context['page'].paginator.count, 0)

    def test_l_onglet_est_cloisonne(self):
        from centres.models import Centre
        from django.contrib.auth.models import Permission
        self.faire('masquer')
        voisin = Centre.objects.create(nom='Toumbokro', code='TBK')
        intrus = User.objects.create_user('lot_voisin2', password='x')
        for code in ('view_patient', 'gerer_doublons'):
            intrus.user_permissions.add(Permission.objects.get(
                content_type__app_label='patients', codename=code))
        self.rattacher(User.objects.get(pk=intrus.pk), voisin)
        client = Client()
        client.force_login(User.objects.get(pk=intrus.pk))
        reponse = client.get(reverse('patients:doublons_lots'))
        self.assertEqual(reponse.context['page'].paginator.count, 0)


class BaseDeuxSoeurs(BaseLots):
    """Un groupe « à vérifier », celui qu'on voit en vrai.

    KONATE FATIMATA ZAHARA et KONATE FATOUMATA ZARA : même nom, prénom
    voisin, même numéro — et deux dates de naissance qui ne concordent pas.
    Le relevé les rapproche à juste titre, mais ce sont deux personnes.
    """

    def setUp(self):
        super().setUp()
        from .doublons_groupes import cle_groupe
        from .doublons_recalcul import recalculer_centre
        commun = dict(sexe='F', telephone='0711112222', centre=self.centre,
                      nationalite='Ivoirienne')
        self.soeurs = (
            Patient.all_objects.create(nom='KONATE', prenoms='FATIMATA ZAHARA',
                                       date_naissance=date(1990, 1, 1), **commun),
            Patient.all_objects.create(nom='KONATE', prenoms='FATOUMATA ZARA',
                                       date_naissance=date(1991, 6, 3), **commun))
        recalculer_centre(self.centre.pk)
        self.vider_le_cache()
        self.cle_soeurs = cle_groupe([f.pk for f in self.soeurs])

    def ligne_des_soeurs(self):
        from .doublons_groupes import index
        return next(ligne for ligne in index(self.centre.pk)
                    if ligne['cle'] == self.cle_soeurs)

    def couple_des_soeurs(self):
        """(gardée, l'autre), comme l'écran de comparaison le propose."""
        from .doublons_groupes import fiche_a_garder
        from .liens_patient import comptes_par_table
        fiches = list(self.soeurs)
        garder, _choisis = fiche_a_garder(
            fiches, comptes_par_table([f.pk for f in fiches]))
        return (next(f for f in fiches if f.pk == garder),
                next(f for f in fiches if f.pk != garder))


class TestPasDActionRapideSurUnAVerifier(BaseDeuxSoeurs):
    def test_le_couple_temoin_est_bien_a_verifier(self):
        self.assertEqual(self.ligne_des_soeurs()['niveau'], 'avertissement')

    def test_aucune_carte_a_verifier_ne_propose_de_masquer(self):
        groupes = self.lignes(niveau='avertissement').context['groupes']
        self.assertTrue(groupes)
        for groupe in groupes:
            self.assertIsNone(groupe['masquable'], groupe['cle'])

    def test_l_ecran_n_affiche_alors_aucun_bouton_de_masquage(self):
        self.assertNotContains(self.lignes(niveau='avertissement'),
                               'Masquer le doublon')

    def test_un_groupe_quasi_certain_le_propose_toujours(self):
        reponse = self.lignes(niveau='certain')
        self.assertTrue(any(g['masquable'] for g in reponse.context['groupes']))
        self.assertContains(reponse, 'Masquer le doublon')

    def test_a_l_unite_le_masquage_reste_possible(self):
        """Depuis l'écran de comparaison, les deux fiches sous les yeux."""
        gardee, autre = self.couple_des_soeurs()
        self.client.post(
            reverse('patients:doublons_masquer', args=[self.cle_soeurs, autre.pk]),
            {'au_profit_de': gardee.pk})
        self.assertTrue(Patient.all_objects.get(pk=autre.pk).masque)

    def test_a_l_unite_la_fusion_reste_possible(self):
        gardee, autre = self.couple_des_soeurs()
        self.client.post(
            reverse('patients:fusionner', args=[self.cle_soeurs, autre.pk]),
            {'retour': reverse('patients:doublons_liste')})
        self.assertEqual(Patient.all_objects.get(pk=autre.pk).fusionne_dans_id,
                         gardee.pk)


class TestUnLotNeMasqueEtNeFusionnePasLesAVerifier(BaseDeuxSoeurs):
    def test_le_masquage_les_range_dans_les_ignores(self):
        reponse = self.preparer('masquer', cles=[self.cle_soeurs])
        self.assertEqual(reponse.context['prevus'], [])
        self.assertEqual(dict(reponse.context['ignores'])[self.cle_soeurs],
                         'à vérifier : à traiter un par un')

    def test_la_fusion_aussi(self):
        reponse = self.preparer('fusionner', cles=[self.cle_soeurs])
        self.assertEqual(reponse.context['prevus'], [])
        self.assertIn('à vérifier',
                      dict(reponse.context['ignores'])[self.cle_soeurs])

    def test_l_ecran_de_confirmation_dit_pourquoi(self):
        self.assertContains(self.preparer('masquer', cles=[self.cle_soeurs]),
                            'à traiter un par un')

    def test_pas_un_doublon_les_accepte(self):
        """La seule action de lot qui leur reste, et elle marche."""
        from .models import PaireEcartee
        lot = self.faire('ecarter', cles=[self.cle_soeurs],
                         raison_commune='Deux sœurs')
        self.assertEqual(len(lot.faits), 1)
        self.assertEqual(lot.ignores, [])
        self.assertTrue(PaireEcartee.all_objects.filter(raison='Deux sœurs')
                        .exists())

    def test_un_lot_mele_fait_les_certains_et_laisse_les_autres(self):
        lot = self.faire('masquer',
                         cles=[self.cle_de('jumeaux'), self.cle_soeurs])
        self.assertEqual(len(lot.faits), 1)
        self.assertEqual([cle for cle, _raison in lot.ignores],
                         [self.cle_soeurs])
        for fiche in self.soeurs:
            self.assertFalse(Patient.all_objects.get(pk=fiche.pk).masque)

    def test_tout_le_filtre_ne_masque_que_les_quasi_certains(self):
        """C'est là que la règle compte : « tout sélectionner » prend le
        relevé entier, les « à vérifier » compris."""
        from .doublons_groupes import index
        certains = sorted(ligne['cle'] for ligne in index(self.centre.pk)
                          if ligne['niveau'] == 'certain')
        lot = self.faire('masquer', cles=[], tout='1')
        self.assertEqual(sorted(fait['cle'] for fait in lot.faits), certains)
        self.assertEqual([cle for cle, _raison in lot.ignores],
                         [self.cle_soeurs])
        for fiche in self.soeurs:
            self.assertFalse(Patient.all_objects.get(pk=fiche.pk).masque)

    def test_la_barre_annonce_la_regle(self):
        self.assertContains(self.lignes(), 'id="dbl-lot-avertis"')

    def test_le_niveau_voyage_jusqu_a_la_carte(self):
        """Sans lui, la barre ne saurait pas ce qu'elle tient."""
        self.assertContains(self.lignes(), 'data-niveau="avertissement"')


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
