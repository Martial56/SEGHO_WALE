from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from facturation.models import Facture
from patients.models import Patient

from .models import ProcedureSoin, Soin
from .views import _has_at_least_one_ligne, _parse_prix, _sync_procedures


# ─── Helpers de création ───────────────────────────────────────────────────────

def _patient(suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance='1990-06-01', sexe='M',
        telephone='0700000000',
    )


def _soin(patient=None, statut='brouillon', facture=None, creator=None):
    return Soin.objects.create(
        patient=patient or _patient(),
        motif='Motif de test',
        statut=statut,
        facture=facture,
        cree_par=creator,
    )


def _facture(patient, statut='emise', montant_total=Decimal('5000')):
    return Facture.objects.create(
        patient=patient,
        type_facture='soins',
        statut=statut,
        montant_total=montant_total,
    )


def _procedure(soin=None, patient=None, statut='brouillon', prix=Decimal('1000')):
    return ProcedureSoin.objects.create(
        soin=soin,
        patient=patient or (soin.patient if soin else _patient()),
        prix=prix,
        statut=statut,
    )


def _soins_user(username, perms=()):
    user = User.objects.create_user(username, password='x')
    for codename in perms:
        # Plusieurs apps définissent des permissions du même nom (ex. can_creer_facture
        # existe aussi sur hospitalisation.Hospitalisation) : on précise l'app.
        perm = Permission.objects.get(codename=codename, content_type__app_label='soins')
        user.user_permissions.add(perm)
    return user


# ─── Tests génération de numéros uniques ───────────────────────────────────────

class TestNumerosUniques(TestCase):

    def setUp(self):
        self.patient = _patient('A')

    def test_deux_soins_numeros_distincts(self):
        s1 = _soin(self.patient)
        s2 = _soin(self.patient)
        self.assertNotEqual(s1.numero, s2.numero)

    def test_format_numero_soin(self):
        s = _soin(self.patient)
        annee_courte = str(timezone.now().year)[2:]
        prefix = f'SN{annee_courte}'
        self.assertTrue(s.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{s.numero}'")
        suffixe = s.numero[len(prefix):]
        self.assertEqual(len(suffixe), 5, "Le suffixe doit être sur 5 chiffres")
        self.assertTrue(suffixe.isdigit())

    def test_deux_procedures_numeros_distincts(self):
        p1 = _procedure(patient=self.patient)
        p2 = _procedure(patient=self.patient)
        self.assertNotEqual(p1.numero, p2.numero)

    def test_format_numero_procedure(self):
        p = _procedure(patient=self.patient)
        annee_courte = str(timezone.now().year)[2:]
        prefix = f'DP{annee_courte}'
        self.assertTrue(p.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{p.numero}'")
        suffixe = p.numero[len(prefix):]
        self.assertEqual(len(suffixe), 5, "Le suffixe doit être sur 5 chiffres")
        self.assertTrue(suffixe.isdigit())


# ─── Tests des fonctions utilitaires de views.py ───────────────────────────────

class TestHasAtLeastOneLigne(TestCase):

    def test_vrai_si_une_ligne_a_un_service(self):
        post_data = {'lignes[0][service]': '3', 'lignes[0][patient]': '1'}
        self.assertTrue(_has_at_least_one_ligne(post_data))

    def test_faux_si_service_vide(self):
        post_data = {'lignes[0][service]': '', 'lignes[0][patient]': '1'}
        self.assertFalse(_has_at_least_one_ligne(post_data))

    def test_faux_si_aucune_ligne(self):
        self.assertFalse(_has_at_least_one_ligne({}))

    def test_vrai_si_une_parmi_plusieurs_lignes_valide(self):
        post_data = {
            'lignes[0][service]': '',
            'lignes[1][service]': '7',
        }
        self.assertTrue(_has_at_least_one_ligne(post_data))


class TestParsePrix(TestCase):

    def test_valeur_vide_retourne_zero(self):
        self.assertEqual(_parse_prix(''), 0)
        self.assertEqual(_parse_prix(None), 0)

    def test_valeur_numerique_simple(self):
        self.assertEqual(_parse_prix('1500'), 1500)

    def test_ignore_les_caracteres_non_numeriques(self):
        self.assertEqual(_parse_prix('1 500 FCFA'), 1500)

    def test_uniquement_texte_retourne_zero(self):
        self.assertEqual(_parse_prix('FCFA'), 0)


class TestSyncProcedures(TestCase):

    def test_met_a_jour_toutes_les_procedures_du_soin(self):
        soin = _soin(statut='en_cours')
        p1 = _procedure(soin=soin, statut='en_cours')
        p2 = _procedure(soin=soin, statut='en_cours')
        autre_soin = _soin(statut='en_cours')
        p3 = _procedure(soin=autre_soin, statut='en_cours')

        _sync_procedures(soin, 'termine')

        p1.refresh_from_db()
        p2.refresh_from_db()
        p3.refresh_from_db()
        self.assertEqual(p1.statut, 'termine')
        self.assertEqual(p2.statut, 'termine')
        self.assertEqual(p3.statut, 'en_cours',
                         "Les procédures d'un autre soin ne doivent pas être affectées")


# ─── Tests de la vue soins_administrer ─────────────────────────────────────────

class TestSoinsAdministrerView(TestCase):

    def setUp(self):
        self.patient = _patient('B')
        self.superuser = User.objects.create_superuser('su_sa', password='x')

    def _client_avec_perm(self, username='u_sa_ok'):
        user = _soins_user(username, perms=['can_administrer_soin'])
        client = Client()
        client.login(username=username, password='x')
        return client

    def test_refuse_sans_permission(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='payee'))
        user = _soins_user('u_sa_noperm')
        client = Client()
        client.login(username='u_sa_noperm', password='x')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours',
                         "Le statut ne doit pas changer sans la permission can_administrer_soin")

    def test_refuse_si_statut_pas_en_cours(self):
        soin = _soin(self.patient, statut='brouillon', facture=_facture(self.patient, statut='payee'))
        client = self._client_avec_perm()
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'brouillon')

    def test_refuse_si_facture_non_payee(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='emise'))
        client = self._client_avec_perm('u_sa_impaye')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')

    def test_refuse_sans_facture(self):
        soin = _soin(self.patient, statut='en_cours', facture=None)
        client = self._client_avec_perm('u_sa_sansfacture')
        client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')

    def test_autorise_avec_facture_payee_et_permission(self):
        soin = _soin(self.patient, statut='en_cours', facture=_facture(self.patient, statut='payee'))
        procedure = _procedure(soin=soin, statut='en_cours')
        client = self._client_avec_perm('u_sa_ok2')
        resp = client.post(reverse('soins:administrer', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        procedure.refresh_from_db()
        self.assertEqual(soin.statut, 'termine')
        self.assertIsNotNone(soin.date_termine)
        self.assertEqual(procedure.statut, 'termine',
                         "Les procédures du soin doivent être synchronisées à 'termine'")


# ─── Tests de la vue soins_creer_facture ───────────────────────────────────────

class TestSoinsCreerFactureView(TestCase):

    def setUp(self):
        self.patient = _patient('C')

    def _client_avec_perm(self, username='u_scf_ok'):
        _soins_user(username, perms=['can_creer_facture'])
        client = Client()
        client.login(username=username, password='x')
        return client

    def test_refuse_sans_permission(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        _procedure(soin=soin, prix=Decimal('2000'))
        user = _soins_user('u_scf_noperm')
        client = Client()
        client.login(username='u_scf_noperm', password='x')
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_refuse_si_statut_incorrect(self):
        soin = _soin(self.patient, statut='brouillon')
        _procedure(soin=soin, prix=Decimal('2000'))
        client = self._client_avec_perm()
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_refuse_sans_procedures(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        client = self._client_avec_perm('u_scf_sansligne')
        client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        soin.refresh_from_db()
        self.assertIsNone(soin.facture_id)

    def test_cree_facture_avec_permission_et_procedures(self):
        soin = _soin(self.patient, statut='en_attente_de_paiement')
        _procedure(soin=soin, prix=Decimal('2000'))
        _procedure(soin=soin, prix=Decimal('3000'))
        client = self._client_avec_perm('u_scf_ok2')
        resp = client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        self.assertIsNotNone(soin.facture_id)
        self.assertEqual(soin.facture.montant_total, Decimal('5000'))

    def test_redirige_vers_facture_existante_sans_recreer(self):
        facture = _facture(self.patient)
        soin = _soin(self.patient, statut='en_attente_de_paiement', facture=facture)
        client = self._client_avec_perm('u_scf_deja')
        resp = client.post(reverse('soins:creer_facture', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        soin.refresh_from_db()
        self.assertEqual(soin.facture_id, facture.pk)


# ─── Tests du verrouillage de la vue soins_edit ────────────────────────────────

class TestSoinsEditLocking(TestCase):

    def setUp(self):
        self.patient = _patient('D')
        self.superuser = User.objects.create_superuser('su_se', password='x')
        self.user = User.objects.create_user('u_se', password='x')

    def test_edit_bloque_si_hospitalisation_liee_pour_non_superuser(self):
        from hospitalisation.models import Hospitalisation
        from medecins.models import Medecin, Specialite
        from employer.models import Employe
        specialite, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
        employe = Employe.objects.create(
            nom='Doc', prenoms='Test', telephone='0700000001', date_embauche='2020-01-01',
        )
        medecin = Medecin.objects.create(employe=employe, specialite=specialite)
        hosp = Hospitalisation.objects.create(
            patient=self.patient, medecin_traitant=medecin,
            date_admission=timezone.now(), statut='hospitalise',
        )
        soin = _soin(self.patient, statut='brouillon')
        soin.hospitalisation = hosp
        soin.save(update_fields=['hospitalisation'])

        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('soins:detail', kwargs={'pk': soin.pk}))

    def test_edit_autorise_pour_superuser_malgre_hospitalisation(self):
        from hospitalisation.models import Hospitalisation
        from medecins.models import Medecin, Specialite
        from employer.models import Employe
        specialite, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
        employe = Employe.objects.create(
            nom='Doc', prenoms='Test2', telephone='0700000001', date_embauche='2020-01-01',
        )
        medecin = Medecin.objects.create(employe=employe, specialite=specialite)
        hosp = Hospitalisation.objects.create(
            patient=self.patient, medecin_traitant=medecin,
            date_admission=timezone.now(), statut='hospitalise',
        )
        soin = _soin(self.patient, statut='brouillon')
        soin.hospitalisation = hosp
        soin.save(update_fields=['hospitalisation'])

        client = Client()
        client.login(username='su_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_edit_bloque_si_statut_non_brouillon_pour_non_superuser(self):
        soin = _soin(self.patient, statut='en_cours')
        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('soins:detail', kwargs={'pk': soin.pk}))

    def test_edit_autorise_si_statut_brouillon(self):
        soin = _soin(self.patient, statut='brouillon')
        client = Client()
        client.login(username='u_se', password='x')
        resp = client.get(reverse('soins:edit', kwargs={'pk': soin.pk}))
        self.assertEqual(resp.status_code, 200)
