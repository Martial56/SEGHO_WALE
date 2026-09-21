from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from facturation.models import Facture
from medecins.models import Medecin, Specialite
from patients.models import Patient
from services.models import Articleservice

from .models import (Chambre, Hospitalisation, ListeControleAdmission,
                     ListeVerificationService, RegistreDeces, ResumeDecharge,
                     ServiceAFacturer)
from .services import check_action, get_actions_disponibles
from .views import _save_resume_decharge, _sync_soins_only, _transition_installer


# ─── Helpers de création ───────────────────────────────────────────────────────

def _specialite():
    s, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
    return s


def _patient(suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance='1990-06-01', sexe='M',
        telephone='0700000000',
    )


def _medecin(suffix=''):
    from employer.models import Employe
    employe = Employe.objects.create(
        nom='Docteur', prenoms=f'Test{suffix}',
        telephone='0700000001', date_embauche='2020-01-01',
    )
    return Medecin.objects.create(employe=employe, specialite=_specialite())


def _article():
    return Articleservice.objects.create(
        nom='Soin test', prix_vente=Decimal('3000'), actif=True,
    )


def _chambre(statut=True):
    return Chambre.objects.create(nom=f'Ch-{Chambre.objects.count()}', statut=statut)


def _facture_payee(hosp):
    return Facture.objects.create(
        patient=hosp.patient, hospitalisation=hosp,
        type_facture='hospitalisation', statut='payee',
    )


def _hosp(patient=None, medecin=None, statut='brouillon', chambre=None, creator=None):
    return Hospitalisation.objects.create(
        patient=patient or _patient(),
        medecin_traitant=medecin or _medecin(),
        date_admission=timezone.now(),
        statut=statut,
        chambre=chambre,
        cree_par=creator,
    )


# ─── Tests get_actions_disponibles ─────────────────────────────────────────────

class TestGetActionsDisponibles(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('su_gad', password='x')
        self.user = User.objects.create_user('u_gad', password='x')
        self.patient = _patient('A')
        self.medecin = _medecin('A')

    def _hosp(self, statut='brouillon', chambre=None):
        return _hosp(self.patient, self.medecin, statut=statut, chambre=chambre,
                     creator=self.superuser)

    def test_superuser_bypasse_permissions_et_regles_metier(self):
        """Le superuser ignore les permissions ET la plupart des règles métier
        « souples » (chambre attribuée, services non facturés...), mais reste
        soumis aux mêmes préconditions de statut que les autres utilisateurs —
        sauf la facture MEO payée avant de confirmer, une règle financière qui
        s'applique à tout le monde, y compris aux superusers."""
        hosp = self._hosp(statut='brouillon')
        actions = get_actions_disponibles(hosp, self.superuser)
        self.assertTrue(actions['confirmer']['visible'])
        self.assertFalse(actions['confirmer']['enabled'])  # facture MEO pas encore payée
        self.assertTrue(actions['annuler']['visible'])
        self.assertTrue(actions['annuler']['enabled'])

        _facture_payee(hosp)
        actions = get_actions_disponibles(hosp, self.superuser)
        self.assertTrue(actions['confirmer']['enabled'])  # payée : se débloque même pour le superuser

        # confirme : installer actif même sans facture payée ni chambre attribuée
        hosp = self._hosp(statut='confirme')
        actions = get_actions_disponibles(hosp, self.superuser)
        self.assertTrue(actions['installer']['visible'])
        self.assertTrue(actions['installer']['enabled'])

        # hospitalise : decharger actif même avec des factures impayées
        hosp = self._hosp(statut='hospitalise')
        actions = get_actions_disponibles(hosp, self.superuser)
        self.assertTrue(actions['decharger']['visible'])
        self.assertTrue(actions['decharger']['enabled'])

        # decharge : terminer actif même avec SAF non facturés / factures impayées
        hosp = self._hosp(statut='decharge')
        actions = get_actions_disponibles(hosp, self.superuser)
        self.assertTrue(actions['terminer']['visible'])
        self.assertTrue(actions['terminer']['enabled'])

    def test_superuser_transitions_verrouillees_hors_statut_precedent(self):
        """Même pour le superuser, chaque transition doit rester cachée hors du
        statut qui la précède directement — sinon un clic (ou un POST direct)
        régresse un dossier déjà avancé (ex. ré-hospitaliser un dossier Terminé,
        ré-occuper une chambre déjà libérée)."""
        cas = (
            ('brouillon',   ('installer', 'decharger', 'terminer')),
            ('confirme',    ('confirmer', 'decharger', 'terminer')),
            ('hospitalise', ('confirmer', 'installer', 'terminer')),
            ('decharge',    ('confirmer', 'installer', 'decharger', 'annuler')),
            ('termine',     ('confirmer', 'installer', 'decharger', 'terminer', 'annuler')),
            ('annule',      ('confirmer', 'installer', 'decharger', 'terminer', 'annuler')),
        )
        for statut, locked_keys in cas:
            hosp = self._hosp(statut=statut)
            actions = get_actions_disponibles(hosp, self.superuser)
            for key in locked_keys:
                self.assertFalse(
                    actions[key]['visible'],
                    f"{key} devrait être caché pour le superuser au statut {statut}"
                )

    def test_user_sans_permission_tout_invisible(self):
        hosp = self._hosp()
        actions = get_actions_disponibles(hosp, self.user)
        for key in ('confirmer', 'creer_facture', 'installer', 'decharger', 'terminer', 'annuler'):
            self.assertFalse(actions[key]['visible'],
                             f"{key} devrait être invisible pour un user sans permission")

    def test_confirmer_actif_meme_sans_soin(self):
        """Avoir déjà ajouté un soin n'est pas une condition pour confirmer
        (décision produit) : patient + médecin traitant + facture MEO payée
        suffisent."""
        perm = Permission.objects.get(codename='can_confirmer_demande')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='brouillon')
        _facture_payee(hosp)
        actions = get_actions_disponibles(hosp, self.user)
        self.assertTrue(actions['confirmer']['enabled'])

    def test_confirmer_visible_mais_desactive_pour_confirme(self):
        perm = Permission.objects.get(codename='can_confirmer_demande')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='confirme')
        actions = get_actions_disponibles(hosp, self.user)
        self.assertTrue(actions['confirmer']['visible'])
        self.assertFalse(actions['confirmer']['enabled'])

    def test_confirmer_visible_mais_desactive_pour_hospitalise(self):
        perm = Permission.objects.get(codename='can_confirmer_demande')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='hospitalise')
        actions = get_actions_disponibles(hosp, self.user)
        self.assertTrue(actions['confirmer']['visible'])
        self.assertFalse(actions['confirmer']['enabled'])

    def test_confirmer_cache_pour_statuts_terminaux(self):
        perm = Permission.objects.get(codename='can_confirmer_demande')
        self.user.user_permissions.add(perm)
        for statut in ('decharge', 'termine', 'annule'):
            hosp = self._hosp(statut=statut)
            actions = get_actions_disponibles(hosp, self.user)
            self.assertFalse(
                actions['confirmer']['visible'],
                f"confirmer devrait être caché pour statut={statut}"
            )

    def test_installer_bloque_sans_facture_payee(self):
        perm = Permission.objects.get(codename='can_installer_patient')
        self.user.user_permissions.add(perm)
        chambre = _chambre()
        hosp = self._hosp(statut='confirme', chambre=chambre)
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['installer']['enabled'])
        self.assertIn('facture', actions['installer']['raison_blocage'].lower())

    def test_installer_bloque_sans_chambre(self):
        perm = Permission.objects.get(codename='can_installer_patient')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='confirme')
        Facture.objects.create(
            patient=self.patient, hospitalisation=hosp,
            type_facture='hospitalisation', statut='payee', montant_total=0,
            cree_par=self.superuser,
        )
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['installer']['enabled'])
        self.assertIn('chambre', actions['installer']['raison_blocage'].lower())

    def test_decharger_actif_meme_sans_diagnostic(self):
        """Le diagnostic de décharge est facultatif (décision produit) :
        Décharger reste actif même sans ResumeDecharge rempli."""
        perm = Permission.objects.get(codename='can_decharger_patient')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='hospitalise')
        actions = get_actions_disponibles(hosp, self.user)
        self.assertTrue(actions['decharger']['enabled'])

    def test_decharger_actif_avec_diagnostic(self):
        perm = Permission.objects.get(codename='can_decharger_patient')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='hospitalise')
        ResumeDecharge.objects.create(
            hospitalisation=hosp,
            diagnostic_decharge='Guérison complète',
        )
        actions = get_actions_disponibles(hosp, self.user)
        self.assertTrue(actions['decharger']['enabled'])

    def test_terminer_bloque_saf_non_factures(self):
        perm = Permission.objects.get(codename='can_cloturer_dossier')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='decharge')
        ServiceAFacturer.objects.create(
            hospitalisation=hosp, service=_article(), quantite=1, source='manuel'
        )
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['terminer']['enabled'])

    def test_terminer_bloque_factures_impayees(self):
        perm = Permission.objects.get(codename='can_cloturer_dossier')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='decharge')
        Facture.objects.create(
            patient=self.patient, hospitalisation=hosp,
            type_facture='hospitalisation', statut='emise', montant_total=5000,
            cree_par=self.superuser,
        )
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['terminer']['enabled'])


# ─── Tests check_action ────────────────────────────────────────────────────────

class TestCheckAction(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('su_ca', password='x')
        self.patient = _patient('B')
        self.medecin = _medecin('B')

    def test_confirmer_check_action_refuse_depuis_hospitalise_pour_user(self):
        """check_action('confirmer') doit retourner False pour confirme/hospitalise
        (visible=True, enabled=False) — la synchro passe par _sync_soins_only, pas check_action."""
        user = User.objects.create_user('u_ca_confirmer', password='x')
        perm = Permission.objects.get(codename='can_confirmer_demande')
        user.user_permissions.add(perm)
        hosp = _hosp(self.patient, self.medecin, statut='hospitalise', creator=self.superuser)
        ok, err = check_action(hosp, user, 'confirmer')
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_action_inconnue_refuse(self):
        hosp = _hosp(self.patient, self.medecin, creator=self.superuser)
        ok, err = check_action(hosp, self.superuser, 'action_qui_nexiste_pas')
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_installer_refuse_statut_brouillon_pour_user(self):
        user = User.objects.create_user('u_ca_installer', password='x')
        perm = Permission.objects.get(codename='can_installer_patient')
        user.user_permissions.add(perm)
        hosp = _hosp(self.patient, self.medecin, statut='brouillon', creator=self.superuser)
        ok, err = check_action(hosp, user, 'installer')
        self.assertFalse(ok)

    def test_annuler_refuse_depuis_decharge_pour_user(self):
        user = User.objects.create_user('u_ca_annuler', password='x')
        perm = Permission.objects.get(codename='can_annuler_demande')
        user.user_permissions.add(perm)
        hosp = _hosp(self.patient, self.medecin, statut='decharge', creator=self.superuser)
        ok, err = check_action(hosp, user, 'annuler')
        self.assertFalse(ok)


# ─── Tests _transition_installer ───────────────────────────────────────────────

class TestTransitionInstaller(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('su_ti', password='x')
        self.patient = _patient('C')
        self.medecin = _medecin('C')

    def test_refuse_chambre_non_disponible(self):
        chambre = _chambre(statut=False)
        hosp = _hosp(self.patient, self.medecin, statut='confirme',
                     chambre=chambre, creator=self.superuser)
        ok, err = _transition_installer(hosp, self.superuser)
        self.assertFalse(ok)
        self.assertIn('disponible', err.lower())

    def test_refuse_sans_chambre(self):
        hosp = _hosp(self.patient, self.medecin, statut='confirme', creator=self.superuser)
        ok, err = _transition_installer(hosp, self.superuser)
        self.assertFalse(ok)
        self.assertIn('chambre', err.lower())

    def test_installe_avec_chambre_disponible(self):
        chambre = _chambre(statut=True)
        hosp = _hosp(self.patient, self.medecin, statut='confirme',
                     chambre=chambre, creator=self.superuser)
        ok, err = _transition_installer(hosp, self.superuser)
        self.assertTrue(ok, err)
        hosp.refresh_from_db()
        self.assertEqual(hosp.statut, 'hospitalise')
        self.assertIsNotNone(hosp.heure_entree)
        chambre.refresh_from_db()
        self.assertFalse(chambre.statut)


# ─── Tests génération de numéros uniques ───────────────────────────────────────

class TestNumerosUniques(TestCase):

    def setUp(self):
        self.patient = _patient('D')
        self.medecin = _medecin('D')

    def test_deux_hospitalisations_numeros_distincts(self):
        h1 = _hosp(self.patient, self.medecin)
        h2 = _hosp(self.patient, self.medecin)
        self.assertNotEqual(h1.numero, h2.numero)

    def test_format_numero_hospitalisation(self):
        hosp = _hosp(self.patient, self.medecin)
        annee = timezone.now().year
        prefix = f'HOSP{annee}'
        self.assertTrue(hosp.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{hosp.numero}'")
        suffixe = hosp.numero[len(prefix):]
        self.assertEqual(len(suffixe), 5, "Le suffixe doit être sur 5 chiffres")
        self.assertTrue(suffixe.isdigit(), "Le suffixe doit être numérique")

    def test_format_code_deces(self):
        patient = _patient('E')
        deces = RegistreDeces.objects.create(
            patient=patient,
            date_deces=timezone.now().date(),
            raison_deces='Cause test',
        )
        self.assertTrue(deces.code.startswith('DEC'),
                        f"Attendu préfixe 'DEC', obtenu '{deces.code}'")
        suffixe = deces.code[3:]
        self.assertEqual(len(suffixe), 4, "Le suffixe DEC doit être sur 4 chiffres")
        self.assertTrue(suffixe.isdigit())

    def test_deux_deces_codes_distincts(self):
        p1 = _patient('F')
        p2 = _patient('G')
        d1 = RegistreDeces.objects.create(patient=p1, date_deces=timezone.now().date(),
                                           raison_deces='Cause 1')
        d2 = RegistreDeces.objects.create(patient=p2, date_deces=timezone.now().date(),
                                           raison_deces='Cause 2')
        self.assertNotEqual(d1.code, d2.code)

    def test_deux_chambres_salle_no_distincts(self):
        c1 = _chambre()
        c2 = _chambre()
        self.assertNotEqual(c1.salle_no, c2.salle_no)


# ─── Tests _sync_soins_only ────────────────────────────────────────────────────

class TestSyncSoinsOnly(TestCase):

    def setUp(self):
        self.superuser = User.objects.create_superuser('su_sso', password='x')
        self.patient = _patient('H')
        self.medecin = _medecin('H')
        self.article = _article()

    def _hosp(self, statut='confirme'):
        return _hosp(self.patient, self.medecin, statut=statut, creator=self.superuser)

    def test_refuse_depuis_statut_terminal(self):
        for statut in ('decharge', 'termine', 'annule'):
            hosp = self._hosp(statut=statut)
            ok, err = _sync_soins_only(hosp, self.superuser)
            self.assertFalse(ok, f"devrait être refusé depuis statut={statut}")
            self.assertIsNotNone(err)

    def test_refuse_sans_permission(self):
        user = User.objects.create_user('u_sso_noperm', password='x')
        hosp = self._hosp(statut='confirme')
        ok, err = _sync_soins_only(hosp, user)
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_accepte_depuis_confirme_avec_permission(self):
        user = User.objects.create_user('u_sso_perm', password='x')
        perm = Permission.objects.get(codename='can_confirmer_demande')
        user.user_permissions.add(perm)
        hosp = self._hosp(statut='confirme')
        ok, err = _sync_soins_only(hosp, user)
        self.assertTrue(ok, err)

    def test_accepte_depuis_hospitalise_avec_permission(self):
        user = User.objects.create_user('u_sso_perm2', password='x')
        perm = Permission.objects.get(codename='can_confirmer_demande')
        user.user_permissions.add(perm)
        hosp = self._hosp(statut='hospitalise')
        ok, err = _sync_soins_only(hosp, user)
        self.assertTrue(ok, err)

    def test_superuser_accepte_tous_statuts_actifs(self):
        for statut in ('confirme', 'hospitalise'):
            hosp = self._hosp(statut=statut)
            ok, err = _sync_soins_only(hosp, self.superuser)
            self.assertTrue(ok, f"superuser devrait être accepté depuis statut={statut}: {err}")


# ─── Verrouillage des vues par permission ──────────────────────────────────────

class TestPermissionsDesVues(TestCase):
    """Chaque URL du module refuse un compte connecté sans la permission.

    Jusqu'ici toutes les vues se contentaient de @login_required : les boutons
    étaient bien calculés par get_actions_disponibles, mais les URL restaient
    ouvertes à n'importe quel compte connecté, qui pouvait créer une admission,
    modifier une chambre ou vider les listes de contrôle en tapant l'adresse.
    """

    @classmethod
    def setUpTestData(cls):
        cls.patient = _patient('Perm')
        cls.medecin = _medecin('Perm')
        cls.hosp = _hosp(cls.patient, cls.medecin, statut='brouillon')
        cls.chambre = _chambre()
        cls.deces = RegistreDeces.objects.create(
            patient=cls.patient, date_deces='2026-01-01', raison_deces='Test',
        )
        cls.item_adm = ListeControleAdmission.objects.create(item='Bracelet posé')
        cls.item_srv = ListeVerificationService.objects.create(item='Lit désinfecté')

    def _urls(self):
        """(nom d'URL, kwargs, permissions requises)."""
        h = {'pk': self.hosp.pk}
        return [
            ('list',                   {},                     ['view_hospitalisation']),
            ('create',                 {},                     ['add_hospitalisation']),
            ('detail',                 h,                      ['view_hospitalisation']),
            ('edit',                   h,                      ['change_hospitalisation']),
            ('etat',                   h,                      ['view_hospitalisation']),
            ('chambres_list',          {},                     ['view_chambre']),
            ('chambre_detail',         {'pk': self.chambre.pk}, ['view_chambre']),
            ('chambre_create',         {},                     ['add_chambre']),
            ('chambre_edit',           {'pk': self.chambre.pk}, ['change_chambre']),
            ('chambres_export',        {},                     ['view_chambre']),
            ('chambres_import',        {},                     ['add_chambre', 'change_chambre']),
            ('deces_list',             {},                     ['view_registredeces']),
            ('deces_create',           {},                     ['add_registredeces']),
            ('deces_detail',           {'pk': self.deces.pk},  ['view_registredeces']),
            ('deces_edit',             {'pk': self.deces.pk},  ['change_registredeces']),
            ('deces_export',           {},                     ['view_registredeces']),
            ('deces_import',           {},                     ['add_registredeces', 'change_registredeces']),
            ('config_batiments',       {},                     ['view_batiment']),
            ('config_liste_admission', {},                     ['view_listecontroleadmission']),
            ('liste_admission_create', {},                     ['add_listecontroleadmission']),
            ('liste_admission_edit',   {'pk': self.item_adm.pk}, ['change_listecontroleadmission']),
            ('liste_admission_delete', {'pk': self.item_adm.pk}, ['delete_listecontroleadmission']),
            ('liste_admission_export', {},                     ['view_listecontroleadmission']),
            ('liste_admission_import', {},                     ['add_listecontroleadmission',
                                                                'change_listecontroleadmission']),
            ('config_liste_service',   {},                     ['view_listeverificationservice']),
            ('liste_service_create',   {},                     ['add_listeverificationservice']),
            ('liste_service_edit',     {'pk': self.item_srv.pk}, ['change_listeverificationservice']),
            ('liste_service_delete',   {'pk': self.item_srv.pk}, ['delete_listeverificationservice']),
            ('liste_service_export',   {},                     ['view_listeverificationservice']),
            ('liste_service_import',   {},                     ['add_listeverificationservice',
                                                                'change_listeverificationservice']),
        ]

    @staticmethod
    def _perm(codename):
        # can_creer_facture existe aussi sur soins.Soin : on filtre toujours
        # par app_label, sinon get() lève MultipleObjectsReturned.
        return Permission.objects.get(
            codename=codename, content_type__app_label='hospitalisation',
        )

    def test_sans_permission_tout_est_refuse(self):
        user = User.objects.create_user('u_vide', password='x')
        self.client.force_login(user)
        for nom, kwargs, _perms in self._urls():
            with self.subTest(url=nom):
                url = reverse(f'hospitalisation:{nom}', kwargs=kwargs)
                self.assertEqual(self.client.get(url).status_code, 403, nom)

    def test_avec_la_permission_l_acces_passe(self):
        for i, (nom, kwargs, perms) in enumerate(self._urls()):
            with self.subTest(url=nom):
                user = User.objects.create_user(f'u_perm_{i}', password='x')
                for codename in perms:
                    user.user_permissions.add(self._perm(codename))
                self.client.force_login(user)
                url = reverse(f'hospitalisation:{nom}', kwargs=kwargs)
                self.assertNotEqual(self.client.get(url).status_code, 403, nom)

    def test_une_permission_voisine_ne_suffit_pas(self):
        """Consulter n'autorise pas à créer, ni à modifier."""
        user = User.objects.create_user('u_lecture', password='x')
        for codename in ('view_hospitalisation', 'view_chambre', 'view_registredeces',
                         'view_listecontroleadmission', 'view_listeverificationservice'):
            user.user_permissions.add(self._perm(codename))
        self.client.force_login(user)
        for nom, kwargs in (
            ('create', {}),
            ('edit', {'pk': self.hosp.pk}),
            ('chambre_create', {}),
            ('chambre_edit', {'pk': self.chambre.pk}),
            ('deces_create', {}),
            ('deces_edit', {'pk': self.deces.pk}),
            ('liste_admission_create', {}),
            ('liste_admission_delete', {'pk': self.item_adm.pk}),
            ('liste_service_create', {}),
            ('liste_service_delete', {'pk': self.item_srv.pk}),
        ):
            with self.subTest(url=nom):
                url = reverse(f'hospitalisation:{nom}', kwargs=kwargs)
                self.assertEqual(self.client.get(url).status_code, 403, nom)

    def test_le_formulaire_s_ouvre_avec_une_seule_permission_d_etape(self):
        """Attribuer une chambre, ajouter un soin ou décharger passent par le
        même formulaire que « Modifier » : exiger change_hospitalisation en
        fermerait la porte aux profils qui n'ont que leur étape."""
        hosp = _hosp(_patient('Etape'), _medecin('Etape'), statut='confirme',
                     chambre=_chambre())
        _facture_payee(hosp)
        url = reverse('hospitalisation:edit', kwargs={'pk': hosp.pk})
        for codename in ('can_installer_patient', 'can_ajouter_soin',
                         'can_decharger_patient'):
            with self.subTest(perm=codename):
                user = User.objects.create_user(f'u_etape_{codename}', password='x')
                user.user_permissions.add(self._perm(codename))
                self.client.force_login(user)
                self.assertNotEqual(self.client.get(url).status_code, 403)

    def test_superuser_passe_partout(self):
        self.client.force_login(User.objects.create_superuser('su_vues', password='x'))
        for nom, kwargs, _perms in self._urls():
            with self.subTest(url=nom):
                url = reverse(f'hospitalisation:{nom}', kwargs=kwargs)
                self.assertNotEqual(self.client.get(url).status_code, 403, nom)


class TestAjouterSoinEndpoint(TestCase):
    """L'endpoint POST /ajouter-soin/ ajoute un acte facturable au dossier.

    Le bouton est masqué sans can_ajouter_soin, mais l'URL reste joignable :
    le contrôle doit être fait dans la vue, pas seulement dans le gabarit.
    """

    @classmethod
    def setUpTestData(cls):
        cls.hosp = _hosp(_patient('AS'), _medecin('AS'), statut='hospitalise')
        cls.article = _article()

    def _url(self):
        return reverse('hospitalisation:ajouter_soin', kwargs={'pk': self.hosp.pk})

    def test_refuse_sans_permission(self):
        self.client.force_login(User.objects.create_user('u_as_non', password='x'))
        reponse = self.client.post(self._url(), {'soin_pk': self.article.pk})
        self.assertEqual(reponse.status_code, 403)
        self.assertFalse(self.hosp.soins_apportes.exists())

    def test_accepte_avec_permission(self):
        user = User.objects.create_user('u_as_oui', password='x')
        user.user_permissions.add(Permission.objects.get(
            codename='can_ajouter_soin', content_type__app_label='hospitalisation',
        ))
        self.client.force_login(user)
        reponse = self.client.post(self._url(), {'soin_pk': self.article.pk})
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.json()['ok'])
        self.assertTrue(self.hosp.soins_apportes.filter(pk=self.article.pk).exists())


class TestLibellesDePermissionEnFrancais(TestCase):

    def test_aucun_libelle_anglais(self):
        anglais = Permission.objects.filter(
            content_type__app_label='hospitalisation', name__startswith='Can ',
        ).values_list('codename', flat=True)
        self.assertEqual(list(anglais), [])

    def test_les_quatre_permissions_de_base_existent_toujours(self):
        """default_permissions = () ne doit pas les avoir supprimées."""
        for modele in ('hospitalisation', 'chambre', 'registredeces',
                       'listecontroleadmission', 'listeverificationservice', 'batiment'):
            for action in ('view', 'add', 'change', 'delete'):
                with self.subTest(perm=f'{action}_{modele}'):
                    self.assertTrue(Permission.objects.filter(
                        content_type__app_label='hospitalisation',
                        codename=f'{action}_{modele}',
                    ).exists())


# ─── Résumé de décharge ────────────────────────────────────────────────────────

class TestResumeDecharge(TestCase):
    """Garde sur _save_resume_decharge, via l'endpoint /decharger/.

    Cet endpoint n'est plus appelé par l'écran (voir TestParcoursDecharge),
    mais l'URL vit toujours et la garde qu'elle éprouve protège les trois
    appelants de la fonction.

    Trois formulaires enregistraient le résumé, et aucun ne portait les mêmes champs.

    L'onglet « Résumé de décharge » les a tous, la modale de la fiche n'a que le
    transfert, celle du formulaire n'a qu'une date. Écraser sans condition
    vidait le résumé dès qu'on déchargeait depuis la fiche : diagnostic, plan de
    sortie et instructions disparaissaient au clic sur « Confirmer la décharge ».
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser('su_resume', password='x')
        self.client.force_login(self.superuser)
        self.hosp = _hosp(_patient('Res'), _medecin('Res'), statut='hospitalise',
                          chambre=_chambre())
        self.resume = ResumeDecharge.objects.create(
            hospitalisation=self.hosp,
            diagnostic_decharge='Paludisme simple guéri',
            plan_sortie='Repos 3 jours',
            instructions='Paracétamol si fièvre',
        )

    def _recharger(self):
        self.resume.refresh_from_db()
        return self.resume

    def _decharger(self, **donnees):
        return self.client.post(
            reverse('hospitalisation:decharger', kwargs={'pk': self.hosp.pk}),
            donnees, HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_decharge_rapide_conserve_le_resume(self):
        reponse = self._decharger(rd_transfert_present='1')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.json()['ok'])
        resume = self._recharger()
        self.assertEqual(resume.diagnostic_decharge, 'Paludisme simple guéri')
        self.assertEqual(resume.plan_sortie, 'Repos 3 jours')
        self.assertEqual(resume.instructions, 'Paracétamol si fièvre')

    def test_decharge_rapide_avec_transfert_conserve_le_resume(self):
        self._decharger(
            rd_transfert_present='1', rd_transfert='1',
            rd_etablissement_destination='CHU Yamoussoukro',
            rd_motif_reference='Plateau technique',
        )
        resume = self._recharger()
        self.assertTrue(resume.transfert)
        self.assertEqual(resume.diagnostic_decharge, 'Paludisme simple guéri')
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.etablissement_destination, 'CHU Yamoussoukro')

    def test_un_formulaire_sans_la_case_transfert_ne_l_efface_pas(self):
        """La modale du formulaire n'a qu'une date : elle ne doit rien décider
        du transfert, sinon elle annule ce que l'onglet 6 a enregistré."""
        self.resume.transfert = True
        self.resume.save()
        self.hosp.etablissement_destination = 'CHU Yamoussoukro'
        self.hosp.save(update_fields=['etablissement_destination'])

        _save_resume_decharge(self.hosp, {'date_sortie_decharge': '2026-09-21'})

        resume = self._recharger()
        self.assertTrue(resume.transfert)
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.etablissement_destination, 'CHU Yamoussoukro')

    def test_l_onglet_resume_peut_vider_un_champ_expres(self):
        """Un <textarea> effacé est envoyé vide : sa clé est présente, la valeur
        doit bien être écrasée. La garde ne doit pas figer le résumé."""
        _save_resume_decharge(self.hosp, {
            'rd_transfert_present': '1',
            'rd_diagnostic': '', 'rd_plan_sortie': 'Repos', 'rd_note_preop': '',
            'rd_cours_post_op': '', 'rd_instructions': '', 'rd_registre_deces': '',
        })
        resume = self._recharger()
        self.assertEqual(resume.diagnostic_decharge, '')
        self.assertEqual(resume.plan_sortie, 'Repos')
        self.assertEqual(resume.instructions, '')

    def test_decocher_le_transfert_efface_bien_l_etablissement(self):
        self.resume.transfert = True
        self.resume.save()
        self.hosp.etablissement_destination = 'CHU Yamoussoukro'
        self.hosp.save(update_fields=['etablissement_destination'])

        _save_resume_decharge(self.hosp, {'rd_transfert_present': '1'})

        self.assertFalse(self._recharger().transfert)
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.etablissement_destination, '')

    def test_appels_repetes_donnent_le_meme_etat(self):
        """Idempotence : hospitalisation_edit appelle la fonction deux fois."""
        donnees = {
            'rd_transfert_present': '1',
            'rd_diagnostic': 'Guéri', 'rd_plan_sortie': 'Repos',
            'rd_note_preop': '', 'rd_cours_post_op': '', 'rd_instructions': '',
            'rd_registre_deces': '',
        }
        _save_resume_decharge(self.hosp, donnees)
        premier = (self._recharger().diagnostic_decharge, self.resume.plan_sortie)
        _save_resume_decharge(self.hosp, donnees)
        self.assertEqual((self._recharger().diagnostic_decharge, self.resume.plan_sortie),
                         premier)

    def test_le_gabarit_declare_bien_le_temoin(self):
        """Sans `rd_transfert_present`, la case redevient muette et le correctif
        ne tient plus. Un seul écran porte désormais la case : l'onglet
        « Résumé de décharge »."""
        self.hosp.statut = 'hospitalise'
        self.hosp.save(update_fields=['statut'])
        page = self.client.get(
            reverse('hospitalisation:edit', kwargs={'pk': self.hosp.pk})
        ).content.decode()
        self.assertIn('name="rd_transfert_present"', page)


class TestParcoursDecharge(TestCase):
    """« Décharger » mène à l'onglet du résumé, plus à une modale.

    Trois formulaires écrivaient le même résumé et deux d'entre eux n'en
    portaient pas les champs : ils le vidaient à chaque décharge. Il n'en reste
    qu'un, l'onglet « Résumé de décharge », dont le bouton « Valider la
    décharge » enregistre et décharge d'un seul geste.
    """

    def setUp(self):
        self.hosp = _hosp(_patient('Parc'), _medecin('Parc'), statut='hospitalise',
                          chambre=_chambre())

    @staticmethod
    def _perm(codename):
        return Permission.objects.get(
            codename=codename, content_type__app_label='hospitalisation')

    def _utilisateur(self, nom, *codes):
        user = User.objects.create_user(nom, password='x')
        for code in codes:
            user.user_permissions.add(self._perm(code))
        self.client.force_login(user)
        return user

    def _url_edit(self):
        return reverse('hospitalisation:edit', kwargs={'pk': self.hosp.pk})

    CHAMPS = {
        'rd_transfert_present': '1',
        'rd_diagnostic': 'Paludisme simple guéri',
        'rd_plan_sortie': 'Repos 3 jours',
        'rd_instructions': 'Paracétamol si fièvre',
        'rd_note_preop': '', 'rd_cours_post_op': '', 'rd_registre_deces': '',
    }

    def test_la_fiche_pointe_vers_l_onglet_du_resume(self):
        self._utilisateur('u_lien', 'view_hospitalisation', 'can_decharger_patient')
        fiche = self.client.get(
            reverse('hospitalisation:detail', kwargs={'pk': self.hosp.pk})
        ).content.decode()
        self.assertIn('%s?tab=resume' % self._url_edit(), fiche)

    def test_plus_aucune_modale_de_decharge(self):
        """Elle réapparaîtrait avec le bug qu'elle portait : le résumé vidé."""
        self._utilisateur('u_modale', 'view_hospitalisation',
                          'change_hospitalisation', 'can_decharger_patient')
        fiche = self.client.get(
            reverse('hospitalisation:detail', kwargs={'pk': self.hosp.pk})
        ).content.decode()
        self.assertNotIn('modal-decharge', fiche)
        self.assertNotIn('confirmDecharge', fiche)

        formulaire = self.client.get(self._url_edit()).content.decode()
        self.assertNotIn('openDechargeModal', formulaire)
        # La modale imposait une date de sortie que le serveur n'a jamais lue :
        # heure_sortie vient de timezone.now() dans _transition_decharger.
        self.assertNotIn('date_sortie_decharge', formulaire)

    def test_tab_resume_ouvre_le_mode_decharge_pour_les_deux_profils(self):
        """Le paramètre valait auparavant pour le seul admin : un utilisateur
        portant change_hospitalisation arrivait en édition normale, sans le
        bouton de validation, et le lien de la fiche ne menait nulle part."""
        profils = [
            ('u_inf', ('view_hospitalisation', 'can_decharger_patient')),
            ('u_maj', ('view_hospitalisation', 'change_hospitalisation',
                       'can_decharger_patient')),
        ]
        for nom, codes in profils:
            with self.subTest(profil=nom):
                self._utilisateur(nom, *codes)
                page = self.client.get(self._url_edit(), {'tab': 'resume'})
                self.assertEqual(page.status_code, 200)
                self.assertIn('Valider la décharge', page.content.decode())

    def test_valider_enregistre_le_resume_et_decharge(self):
        self._utilisateur('u_valide', 'view_hospitalisation', 'can_decharger_patient')
        reponse = self.client.post(self._url_edit() + '?tab=resume', self.CHAMPS)
        self.assertEqual(reponse.status_code, 302)

        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.statut, 'decharge')
        self.assertIsNotNone(self.hosp.heure_sortie)

        resume = ResumeDecharge.objects.get(hospitalisation=self.hosp)
        self.assertEqual(resume.diagnostic_decharge, 'Paludisme simple guéri')
        self.assertEqual(resume.plan_sortie, 'Repos 3 jours')

    def test_aucun_champ_du_resume_n_est_obligatoire(self):
        """Tout laisser vide décharge quand même — sauf transfert coché."""
        self._utilisateur('u_vide2', 'view_hospitalisation', 'can_decharger_patient')
        reponse = self.client.post(self._url_edit() + '?tab=resume',
                                   {'rd_transfert_present': '1'})
        self.assertEqual(reponse.status_code, 302)
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.statut, 'decharge')

    def test_transfert_coche_exige_etablissement_et_motif(self):
        self._utilisateur('u_transf', 'view_hospitalisation', 'can_decharger_patient')
        self.client.post(self._url_edit() + '?tab=resume', {
            'rd_transfert_present': '1', 'rd_transfert': '1',
            'rd_etablissement_destination': '', 'rd_motif_reference': '',
        })
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.statut, 'hospitalise')

    def test_transfert_complet_decharge_et_enregistre_la_destination(self):
        self._utilisateur('u_transf2', 'view_hospitalisation', 'can_decharger_patient')
        self.client.post(self._url_edit() + '?tab=resume', {
            'rd_transfert_present': '1', 'rd_transfert': '1',
            'rd_etablissement_destination': 'CHU Yamoussoukro',
            'rd_motif_reference': 'Plateau technique',
        })
        self.hosp.refresh_from_db()
        self.assertEqual(self.hosp.statut, 'decharge')
        self.assertEqual(self.hosp.etablissement_destination, 'CHU Yamoussoukro')
