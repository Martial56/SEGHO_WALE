"""Onglets liés d'une fiche patient : pagination.

Les sept onglets — rendez-vous, soins, consultations, ordonnances,
hospitalisations, demandes et résultats d'examens — passent tous par
`_render_related_list`, qui rendait le jeu entier d'un bloc. Un dossier ancien
chargeait donc des centaines de lignes en mémoire et dans la page.
"""

from datetime import date, timedelta

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

    def test_un_patient_deja_connu_est_ignore_sans_mise_a_jour(self):
        self._importer([self._ligne()])
        self._importer([self._ligne(mobile='0799999999')])
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.ignores, 1)
        self.assertEqual(Patient.objects.get().telephone, '0700000001')

    def test_un_patient_deja_connu_est_mis_a_jour_si_demande(self):
        self._importer([self._ligne()])
        self._importer([self._ligne(mobile='0799999999')], do_update=True)
        self.assertEqual(Patient.objects.count(), 1)
        self.assertEqual(self.tache.mis_a_jour, 1)
        self.assertEqual(Patient.objects.get().telephone, '0799999999')

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
    """La date de naissance a remplacé l'âge à l'export et n'est plus exigée.

    Elle manque parfois à l'ouverture d'un dossier — patient hors d'état de la
    donner, pièce d'identité absente. La refuser empêchait d'enregistrer
    quelqu'un qu'on est en train de soigner.
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

    def test_le_formulaire_n_exige_plus_la_date(self):
        from .forms import PatientForm
        self.assertFalse(PatientForm().fields['date_naissance'].required)

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
        self.assertIn('code_identifiant,nom,date_naissance,genre,mobile', texte)

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
