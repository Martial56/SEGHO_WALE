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

