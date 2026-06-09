from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone

from facturation.models import Facture
from medecins.models import Medecin, Specialite
from patients.models import Patient
from services.models import Articleservice

from .models import Chambre, Hospitalisation, RegistreDeces, ResumeDecharge, ServiceAFacturer
from .services import check_action, get_actions_disponibles
from .views import _sync_soins_only, _transition_installer


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
    return Medecin.objects.create(
        matricule=f'MED{suffix}{Medecin.objects.count():03d}',
        nom='Docteur', prenoms=f'Test{suffix}',
        specialite=_specialite(), telephone='0700000001',
    )


def _article():
    return Articleservice.objects.create(
        nom='Soin test', prix_vente=Decimal('3000'), actif=True,
    )


def _chambre(statut=True):
    return Chambre.objects.create(nom=f'Ch-{Chambre.objects.count()}', statut=statut)


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

    def test_superuser_voit_et_active_tout(self):
        hosp = self._hosp()
        actions = get_actions_disponibles(hosp, self.superuser)
        for key in ('confirmer', 'creer_facture', 'installer', 'decharger', 'terminer', 'annuler'):
            self.assertTrue(actions[key]['visible'], f"{key} devrait être visible pour le superuser")
            self.assertTrue(actions[key]['enabled'], f"{key} devrait être activé pour le superuser")

    def test_user_sans_permission_tout_invisible(self):
        hosp = self._hosp()
        actions = get_actions_disponibles(hosp, self.user)
        for key in ('confirmer', 'creer_facture', 'installer', 'decharger', 'terminer', 'annuler'):
            self.assertFalse(actions[key]['visible'],
                             f"{key} devrait être invisible pour un user sans permission")

    def test_confirmer_bloque_sans_soin(self):
        perm = Permission.objects.get(codename='can_confirmer_demande')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='brouillon')
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['confirmer']['enabled'])
        self.assertIn('soin', actions['confirmer']['raison_blocage'].lower())

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

    def test_decharger_bloque_sans_diagnostic(self):
        perm = Permission.objects.get(codename='can_decharger_patient')
        self.user.user_permissions.add(perm)
        hosp = self._hosp(statut='hospitalise')
        # Pas de ResumeDecharge créé → resume_ok = False
        actions = get_actions_disponibles(hosp, self.user)
        self.assertFalse(actions['decharger']['enabled'])
        self.assertIn('diagnostic', actions['decharger']['raison_blocage'].lower())

    def test_decharger_activé_avec_diagnostic(self):
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
