from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase, Client
from django.urls import reverse

from patients.models import Patient

from .models import Acte, Facture, LigneFacture, Paiement
from .views import can_manage_paiement, _handle_paiement, _save_lignes


# ─── Helpers de création ───────────────────────────────────────────────────────

def _patient(suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance='1990-06-01', sexe='M',
        telephone='0700000000',
    )


def _facture(patient=None, statut='emise', montant_total=Decimal('10000'), creator=None):
    return Facture.objects.create(
        patient=patient or _patient(),
        type_facture='consultation',
        statut=statut,
        montant_total=montant_total,
        cree_par=creator,
    )


def _acte(suffix=''):
    return Acte.objects.create(
        code=f'ACT{suffix}{Acte.objects.count():03d}',
        libelle=f'Acte {suffix}',
        prix=Decimal('5000'),
    )


def _caisse_user(username):
    user = User.objects.create_user(username, password='x')
    caisse, _ = Group.objects.get_or_create(name='Caisse')
    user.groups.add(caisse)
    return user


# ─── Tests can_manage_paiement ──────────────────────────────────────────────────

class TestCanManagePaiement(TestCase):

    def test_superuser_autorise(self):
        su = User.objects.create_superuser('su_cmp', password='x')
        self.assertTrue(can_manage_paiement(su))

    def test_user_sans_groupe_refuse(self):
        user = User.objects.create_user('u_cmp', password='x')
        self.assertFalse(can_manage_paiement(user))

    def test_user_groupe_caisse_autorise(self):
        user = _caisse_user('u_cmp_caisse')
        self.assertTrue(can_manage_paiement(user))

    def test_user_autre_groupe_refuse(self):
        user = User.objects.create_user('u_cmp_autre', password='x')
        autre, _ = Group.objects.get_or_create(name='Accueil')
        user.groups.add(autre)
        self.assertFalse(can_manage_paiement(user))


# ─── Tests numéros uniques ──────────────────────────────────────────────────────

class TestNumerosUniques(TestCase):

    def test_deux_factures_numeros_distincts(self):
        patient = _patient('A')
        f1 = _facture(patient, statut='brouillon')
        f2 = _facture(patient, statut='brouillon')
        self.assertNotEqual(f1.numero, f2.numero)

    def test_deux_paiements_numeros_distincts(self):
        facture = _facture(_patient('B'))
        p1 = Paiement.objects.create(facture=facture, montant=1000, mode_paiement='especes')
        p2 = Paiement.objects.create(facture=facture, montant=1000, mode_paiement='especes')
        self.assertNotEqual(p1.numero, p2.numero)

    def test_format_numero_paiement(self):
        facture = _facture(_patient('C'))
        p = Paiement.objects.create(facture=facture, montant=1000, mode_paiement='especes')
        self.assertTrue(p.numero.startswith('PAI'))


# ─── Tests calculs (solde_restant, montant_ligne, recalculer_total) ────────────

class TestCalculs(TestCase):

    def test_solde_restant(self):
        facture = _facture(_patient('D'), montant_total=Decimal('10000'))
        facture.montant_paye = Decimal('4000')
        facture.save(update_fields=['montant_paye'])
        self.assertEqual(facture.solde_restant, Decimal('6000'))

    def test_montant_ligne_sans_remise(self):
        facture = _facture(_patient('E'))
        ligne = LigneFacture.objects.create(
            facture=facture, libelle='Test', quantite=2, prix_unitaire=Decimal('1500'),
        )
        ligne.refresh_from_db()
        self.assertEqual(ligne.montant_ligne, Decimal('3000'))

    def test_montant_ligne_avec_remise(self):
        facture = _facture(_patient('F'))
        ligne = LigneFacture.objects.create(
            facture=facture, libelle='Test', quantite=2, prix_unitaire=Decimal('1000'), remise=Decimal('10'),
        )
        self.assertEqual(ligne.montant_ligne, Decimal('1800'))

    def test_recalculer_total_est_idempotent(self):
        facture = _facture(_patient('G'), montant_total=Decimal('0'))
        LigneFacture.objects.create(facture=facture, libelle='A', quantite=1, prix_unitaire=Decimal('2000'))
        LigneFacture.objects.create(facture=facture, libelle='B', quantite=1, prix_unitaire=Decimal('3000'))
        premier = facture.recalculer_total()
        deuxieme = facture.recalculer_total()
        self.assertEqual(premier, Decimal('5000'))
        self.assertEqual(deuxieme, Decimal('5000'))


# ─── Tests _handle_paiement (logique métier d'enregistrement d'un paiement) ────

class TestHandlePaiement(TestCase):

    def setUp(self):
        self.patient = _patient('H')

    def test_refuse_sans_permission(self):
        user = User.objects.create_user('u_hp_noperm', password='x')
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        _handle_paiement(facture, {'pay_montant': '5000'}, user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('0'))
        self.assertEqual(facture.statut, 'emise')
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_accepte_avec_permission_caisse(self):
        user = _caisse_user('u_hp_caisse')
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        _handle_paiement(facture, {'pay_montant': '5000', 'pay_mode': 'especes'}, user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('5000'))
        self.assertEqual(facture.statut, 'payee')

    def test_paiement_partiel_laisse_facture_emise(self):
        user = _caisse_user('u_hp_partiel')
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        _handle_paiement(facture, {'pay_montant': '2000'}, user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('2000'))
        self.assertEqual(facture.statut, 'emise')

    def test_montant_vide_ne_fait_rien(self):
        user = _caisse_user('u_hp_vide')
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        _handle_paiement(facture, {'pay_montant': ''}, user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_montant_negatif_ignore(self):
        user = _caisse_user('u_hp_neg')
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        _handle_paiement(facture, {'pay_montant': '-100'}, user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('0'))


# ─── Tests _save_lignes ─────────────────────────────────────────────────────────

class TestSaveLignes(TestCase):

    def test_ignore_lignes_vides(self):
        facture = _facture(_patient('I'))
        total = _save_lignes(facture, {
            'ligne_libelle_0': '',
            'ligne_prix_0': '1000',
        })
        self.assertEqual(total, 0)
        self.assertEqual(facture.lignes.count(), 0)

    def test_cumule_plusieurs_lignes(self):
        facture = _facture(_patient('J'))
        total = _save_lignes(facture, {
            'ligne_libelle_0': 'Acte 1', 'ligne_qte_0': '1', 'ligne_prix_0': '2000', 'ligne_remise_0': '0',
            'ligne_libelle_1': 'Acte 2', 'ligne_qte_1': '2', 'ligne_prix_1': '1000', 'ligne_remise_1': '0',
        })
        self.assertEqual(total, 4000)
        self.assertEqual(facture.lignes.count(), 2)


# ─── Tests des vues : autorisations HTTP ───────────────────────────────────────

class TestVuesPermissions(TestCase):

    def setUp(self):
        self.patient = _patient('K')
        self.plain = User.objects.create_user('u_vp_plain', password='x')
        self.plain.set_password('x')
        self.plain.save()
        self.caisse = _caisse_user('u_vp_caisse')
        self.caisse.set_password('x')
        self.caisse.save()

    def test_facture_detail_reste_ouverte_a_tout_utilisateur_connecte(self):
        facture = _facture(self.patient)
        client = Client()
        client.login(username='u_vp_plain', password='x')
        resp = client.get(reverse('facturation:detail', kwargs={'pk': facture.pk}))
        self.assertEqual(resp.status_code, 200)

    def test_facture_payer_refuse_sans_groupe_caisse(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        client = Client()
        client.login(username='u_vp_plain', password='x')
        resp = client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}), {'pay_montant': '5000'})
        self.assertEqual(resp.status_code, 403)
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('0'))

    def test_facture_payer_autorise_pour_groupe_caisse(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        client = Client()
        client.login(username='u_vp_caisse', password='x')
        resp = client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}), {'pay_montant': '5000'})
        self.assertEqual(resp.status_code, 302)
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('5000'))
        self.assertEqual(facture.statut, 'payee')

    def test_facture_edit_action_payer_refuse_sans_groupe_caisse(self):
        from django.contrib.auth.models import Permission
        # facture_edit exige désormais la permission 'change_facture' pour être
        # accessible du tout (sinon redirection 302) — on l'accorde ici pour
        # exercer spécifiquement le blocage plus profond de l'action "payer"
        # (réservée au groupe Caisse), qui est bien l'objet de ce test.
        self.plain.user_permissions.add(
            Permission.objects.get(codename='change_facture', content_type__app_label='facturation')
        )
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('5000'))
        client = Client()
        client.login(username='u_vp_plain', password='x')
        resp = client.post(
            reverse('facturation:edit', kwargs={'pk': facture.pk}),
            {'action_payer': '1'},
        )
        self.assertEqual(resp.status_code, 403)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'emise')
