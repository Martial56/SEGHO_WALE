import re
from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase, Client
from django.urls import reverse

from patients.models import Patient

from .models import Acte, Caisse, Facture, LigneFacture, Paiement
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


# ─── Prestations gratuites : encaisser 0 F pour garder la trace ────────────────

class TestPaiementAZeroFranc(TestCase):
    """Une prestation gratuite doit pouvoir être encaissée.

    Le champ portait `min="1"` en dur : sur une facture à 0 F il s'affichait
    `min="1" max="0"`, deux bornes qu'aucune valeur ne satisfait, et le
    navigateur refusait l'envoi. Côté serveur, deux gardes écartaient en plus
    tout montant nul — sans message. La facture ne passait donc jamais à
    « payée », et un soin gratuit restait bloqué en attente de paiement.
    """

    def setUp(self):
        self.patient = _patient('Z')
        self.user = _caisse_user('u_zero')

    def _gratuite(self):
        return _facture(self.patient, statut='emise', montant_total=Decimal('0'))

    def _due(self):
        return _facture(self.patient, statut='emise', montant_total=Decimal('5000'))

    # ── La règle ──

    def test_zero_accepte_sur_facture_gratuite(self):
        facture = self._gratuite()
        _handle_paiement(facture, {'pay_montant': '0', 'pay_mode': 'especes'},
                         self.user, Decimal('0'))
        facture.refresh_from_db()
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 1)
        self.assertEqual(facture.statut, 'payee')

    def test_zero_refuse_sur_facture_due(self):
        """Un 0 sur une facture de 5 000 F est un champ vidé par mégarde."""
        facture = self._due()
        _handle_paiement(facture, {'pay_montant': '0'}, self.user, Decimal('5000'))
        facture.refresh_from_db()
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)
        self.assertEqual(facture.statut, 'emise')

    # ── Le piège ouvert par l'acceptation de 0 ──

    def test_un_champ_vide_ne_cree_rien_meme_sur_facture_gratuite(self):
        """`float('')` lève, et l'ancien code rabattait l'échec sur 0."""
        facture = self._gratuite()
        _handle_paiement(facture, {'pay_montant': ''}, self.user, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_un_champ_absent_ne_cree_rien(self):
        facture = self._gratuite()
        _handle_paiement(facture, {}, self.user, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_un_montant_illisible_ne_cree_rien(self):
        facture = self._gratuite()
        _handle_paiement(facture, {'pay_montant': 'abc'}, self.user, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_un_montant_negatif_ne_cree_rien(self):
        facture = self._gratuite()
        _handle_paiement(facture, {'pay_montant': '-1'}, self.user, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    # ── Par la vue d'encaissement ──

    def test_la_vue_encaisse_zero_sur_facture_gratuite(self):
        facture = self._gratuite()
        client = Client()
        client.login(username='u_zero', password='x')
        client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                    {'pay_montant': '0', 'pay_mode': 'especes'})
        facture.refresh_from_db()
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 1)
        self.assertEqual(facture.statut, 'payee')

    def test_la_vue_refuse_zero_sur_facture_due_et_le_dit(self):
        facture = self._due()
        client = Client()
        client.login(username='u_zero', password='x')
        reponse = client.post(reverse('facturation:payer', kwargs={'pk': facture.pk}),
                              {'pay_montant': '0'}, follow=True)
        facture.refresh_from_db()
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)
        messages = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('0 F' in m for m in messages), messages)

    # ── Le champ du gabarit ──

    def test_le_plancher_du_champ_suit_le_solde(self):
        client = Client()
        client.login(username='u_zero', password='x')
        gratuite = client.get(reverse('facturation:detail', kwargs={'pk': self._gratuite().pk}))
        self.assertContains(gratuite, 'min="0"')
        due = client.get(reverse('facturation:detail', kwargs={'pk': self._due().pk}))
        self.assertContains(due, 'min="1"')

    # ── La conséquence en bout de chaîne ──

    def test_un_soin_gratuit_demarre_une_fois_encaisse(self):
        """C'est tout l'intérêt : sans encaissement, le soin restait bloqué."""
        from soins.models import ProcedureSoin, Soin
        facture = self._gratuite()
        soin = Soin.objects.create(patient=self.patient, statut='en_attente_de_paiement',
                                   facture=facture)
        procedure = ProcedureSoin.objects.create(patient=self.patient, soin=soin,
                                                 prix=Decimal('0'), statut='brouillon')
        _handle_paiement(facture, {'pay_montant': '0', 'pay_mode': 'especes'},
                         self.user, Decimal('0'))
        soin.refresh_from_db()
        procedure.refresh_from_db()
        self.assertEqual(soin.statut, 'en_cours')
        self.assertEqual(procedure.statut, 'en_cours')


# ─── Le plafond du paiement tient côté serveur ────────────────────────────────

class TestPaiementNeDepassePasLeSolde(TestCase):
    """`max` est posé sur le champ, mais c'est le navigateur qui l'applique.

    Une requête envoyée hors de la page passait outre, et la caisse
    enregistrait plus que ce qui était dû.
    """

    def setUp(self):
        self.patient = _patient('Plaf')
        self.user = _caisse_user('u_plafond')

    def test_un_montant_superieur_au_solde_est_refuse(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('15000'))
        _handle_paiement(facture, {'pay_montant': '50000'}, self.user, Decimal('15000'))
        facture.refresh_from_db()
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)
        self.assertEqual(facture.montant_paye, Decimal('0'))

    def test_un_montant_positif_sur_facture_gratuite_est_refuse(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('0'))
        _handle_paiement(facture, {'pay_montant': '5000'}, self.user, Decimal('0'))
        self.assertEqual(Paiement.objects.filter(facture=facture).count(), 0)

    def test_le_solde_exact_passe(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('15000'))
        _handle_paiement(facture, {'pay_montant': '15000'}, self.user, Decimal('15000'))
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'payee')

    def test_le_plafond_suit_les_paiements_deja_recus(self):
        """Après un acompte, la borne est le reste, pas le total."""
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('15000'))
        _handle_paiement(facture, {'pay_montant': '10000'}, self.user, Decimal('15000'))
        facture.refresh_from_db()
        _handle_paiement(facture, {'pay_montant': '9000'}, self.user, Decimal('15000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('10000'), "Le trop-perçu doit être refusé")
        _handle_paiement(facture, {'pay_montant': '5000'}, self.user, Decimal('15000'))
        facture.refresh_from_db()
        self.assertEqual(facture.montant_paye, Decimal('15000'))
        self.assertEqual(facture.statut, 'payee')


# ─── Porte unique de création de facture ───────────────────────────────────────

class TestPorteUniqueDeFacturation(TestCase):
    """Il n'existe qu'une seule vue de création de facture.

    Il y en avait deux : `facturation:create` et une copie dans `core`, atteinte
    depuis la fiche d'ordonnance et depuis les rendez-vous. Elles avaient
    divergé de 251 lignes, et la copie créait le paiement **sans vérifier
    `can_manage_paiement`** : le même utilisateur était refusé par une porte et
    accepté par l'autre. Ces tests interdisent le retour d'une seconde porte.
    """

    def setUp(self):
        self.patient = _patient('PU')
        self.plain = User.objects.create_user('u_pu_plain', password='x')
        self.caisse = _caisse_user('u_pu_caisse')

    #: Ce que poste le formulaire : une ligne, et un encaissement immédiat.
    POST = {
        'type_facture': 'consultation',
        'montant_assurance': '0',
        'ticket_moderateur': '0',
        'notes': '',
        'ligne_libelle_0': 'Consultation',
        'ligne_qte_0': '1',
        'ligne_prix_0': '5000',
        'ligne_remise_0': '0',
        'pay_montant': '5000',
        'pay_mode': 'especes',
    }

    def _creer(self, username):
        client = Client()
        client.login(username=username, password='x')
        return client.post(
            reverse('facturation:create') + f'?patient={self.patient.pk}',
            self.POST, follow=True,
        )

    def test_la_route_en_double_n_existe_plus(self):
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('facture_create')

    def test_sans_groupe_caisse_la_facture_passe_mais_pas_le_paiement(self):
        self._creer('u_pu_plain')
        self.assertEqual(Facture.objects.count(), 1, "La facture doit être créée")
        self.assertEqual(
            Paiement.objects.count(), 0,
            "Un compte hors Caisse ne doit pas pouvoir encaisser par cette porte",
        )

    def test_avec_le_groupe_caisse_le_paiement_passe(self):
        # Sans ce test le précédent réussirait même si la vue refusait tout le
        # monde, y compris la Caisse.
        self._creer('u_pu_caisse')
        self.assertEqual(Paiement.objects.count(), 1)
        self.assertEqual(Paiement.objects.first().montant, Decimal('5000'))

    def test_aucun_gabarit_ne_pointe_plus_sur_l_ancienne_route(self):
        import subprocess
        from django.conf import settings

        racine = str(settings.BASE_DIR)
        trouve = subprocess.run(
            ['grep', '-rl', "url 'facture_create'", 'templates'],
            cwd=racine, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(trouve, '', f"Gabarits pointant encore sur l'ancienne route : {trouve}")


# ─── Configuration des caisses ─────────────────────────────────────────────────

class TestConfigurationCaisses(TestCase):
    """Écran Configuration → Caisses, qui remplace l'application `caisse`.

    Celle-ci ne savait qu'afficher une liste figée : aucun écran ne permettait
    d'ajouter une caisse, et ses noms étaient écrits en dur dans une des deux
    modales de paiement.
    """

    URLS_LECTURE = ['caisses_list', 'caisse_create']

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse principale', code='CP01')
        self.plain = User.objects.create_user('u_cfg_plain', password='x')
        self.gestionnaire = User.objects.create_user('u_cfg_gest', password='x')
        self.gestionnaire.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='facturation', codename__endswith='_caisse'))

    def _client(self, username):
        client = Client()
        client.login(username=username, password='x')
        return client

    # ── Permissions ──
    def test_sans_permission_tout_est_refuse(self):
        client = self._client('u_cfg_plain')
        for nom in self.URLS_LECTURE:
            self.assertEqual(client.get(reverse('facturation:%s' % nom)).status_code, 403, nom)
        self.assertEqual(
            client.get(reverse('facturation:caisse_edit', args=[self.caisse.pk])).status_code, 403)
        self.assertEqual(
            client.post(reverse('facturation:caisse_delete', args=[self.caisse.pk])).status_code, 403)
        self.assertTrue(Caisse.objects.filter(pk=self.caisse.pk).exists(),
                        "Un POST refusé ne doit rien supprimer")

    def test_avec_les_permissions_tout_s_ouvre(self):
        client = self._client('u_cfg_gest')
        for nom in self.URLS_LECTURE:
            self.assertEqual(client.get(reverse('facturation:%s' % nom)).status_code, 200, nom)

    # ── Création, modification, suppression ──
    def test_creation(self):
        client = self._client('u_cfg_gest')
        client.post(reverse('facturation:caisse_create'),
                    {'nom': 'Caisse Toumbokro', 'code': 'CTB1', 'actif': 'on'})
        self.assertTrue(Caisse.objects.filter(code='CTB1', actif=True).exists())

    def test_le_code_est_mis_en_majuscules_et_les_espaces_coupes(self):
        # Saisi « ctb1 » ici et « CTB1 » là, le même code passerait deux fois :
        # `unique=True` ne voit pas ces deux écritures comme un doublon.
        client = self._client('u_cfg_gest')
        client.post(reverse('facturation:caisse_create'),
                    {'nom': '  Caisse labo  ', 'code': '  clb1  ', 'actif': 'on'})
        caisse = Caisse.objects.get(code='CLB1')
        self.assertEqual(caisse.nom, 'Caisse labo')

    def test_un_code_deja_pris_est_refuse(self):
        client = self._client('u_cfg_gest')
        avant = Caisse.objects.count()
        reponse = client.post(reverse('facturation:caisse_create'),
                              {'nom': 'Doublon', 'code': 'cp01', 'actif': 'on'})
        self.assertEqual(Caisse.objects.count(), avant)
        self.assertContains(reponse, 'déjà pris')

    def test_modification_sans_toucher_au_code(self):
        client = self._client('u_cfg_gest')
        client.post(reverse('facturation:caisse_edit', args=[self.caisse.pk]),
                    {'nom': 'Caisse accueil', 'code': 'CP01', 'actif': 'on'})
        self.caisse.refresh_from_db()
        self.assertEqual(self.caisse.nom, 'Caisse accueil')

    def test_case_actif_decochee_desactive_la_caisse(self):
        client = self._client('u_cfg_gest')
        client.post(reverse('facturation:caisse_edit', args=[self.caisse.pk]),
                    {'nom': 'Caisse principale', 'code': 'CP01'})
        self.caisse.refresh_from_db()
        self.assertFalse(self.caisse.actif)

    def test_suppression(self):
        client = self._client('u_cfg_gest')
        client.post(reverse('facturation:caisse_delete', args=[self.caisse.pk]))
        self.assertFalse(Caisse.objects.filter(pk=self.caisse.pk).exists())

    def test_la_suppression_refuse_le_get(self):
        # Un lien visité par un robot d'indexation ou un préchargement de
        # navigateur ne doit pas effacer une caisse.
        client = self._client('u_cfg_gest')
        client.get(reverse('facturation:caisse_delete', args=[self.caisse.pk]))
        self.assertTrue(Caisse.objects.filter(pk=self.caisse.pk).exists())

    # ── Ce que voit l'écran de facturation ──
    def test_seules_les_caisses_actives_sont_proposees_a_l_encaissement(self):
        Caisse.objects.create(nom='Caisse fermée', code='OLD1', actif=False)
        client = self._client('u_cfg_gest')
        client.force_login(User.objects.create_superuser('su_cfg', password='x'))
        contenu = client.get(
            reverse('facturation:create') + '?patient=%s' % _patient('CFG').pk
        ).content.decode()
        self.assertIn('CAISSE PRINCIPALE', contenu)
        self.assertNotIn('CAISSE FERMÉE', contenu)

    def test_les_permissions_sont_en_francais(self):
        # Le libellé est ce que lit la personne qui compose un groupe.
        libelles = dict(Permission.objects
                        .filter(content_type__app_label='facturation',
                                codename__endswith='_caisse')
                        .values_list('codename', 'name'))
        self.assertEqual(libelles['add_caisse'], 'Peut créer une caisse')
        self.assertEqual(libelles['view_caisse'], 'Peut consulter les caisses')
        for nom in libelles.values():
            self.assertFalse(nom.startswith('Can '), "Libellé anglais resté : %s" % nom)


# ─── Le paiement retient sa caisse ─────────────────────────────────────────────

class TestCaisseDuPaiement(TestCase):
    """« Où l'argent est-il entré ? »

    Le champ « Journal » existait sur les deux écrans d'encaissement, mais le
    navigateur ne le transmettait pas et le serveur ne le lisait pas : le choix
    du caissier était perdu, et `Paiement` n'avait aucun lien vers une caisse.
    """

    def setUp(self):
        self.patient = _patient('CAI')
        self.caisse = Caisse.objects.create(nom='Caisse Toumbokro', code='CTB1')
        self.caissier = _caisse_user('u_pay_caisse')

    def _client(self):
        client = Client()
        client.login(username='u_pay_caisse', password='x')
        return client

    def test_la_modale_de_la_fiche_enregistre_la_caisse(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('3000'))
        self._client().post(reverse('facturation:payer', args=[facture.pk]),
                            {'pay_journal': str(self.caisse.pk),
                             'pay_montant': '3000', 'pay_mode': 'especes'})
        paiement = Paiement.objects.get(facture=facture)
        self.assertEqual(paiement.caisse, self.caisse)

    def test_la_creation_de_facture_enregistre_la_caisse(self):
        self._client().post(
            reverse('facturation:create') + '?patient=%s' % self.patient.pk,
            {'type_facture': 'consultation', 'montant_assurance': '0',
             'ticket_moderateur': '0', 'notes': '',
             'ligne_libelle_0': 'Consultation', 'ligne_qte_0': '1',
             'ligne_prix_0': '5000', 'ligne_remise_0': '0',
             'pay_journal': str(self.caisse.pk), 'pay_montant': '5000',
             'pay_mode': 'especes'})
        self.assertEqual(Paiement.objects.first().caisse, self.caisse)

    def test_un_journal_illisible_n_empeche_pas_l_encaissement(self):
        # Perdre un encaissement parce qu'un identifiant est malformé serait
        # pire que d'enregistrer le paiement sans caisse.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        self._client().post(reverse('facturation:payer', args=[facture.pk]),
                            {'pay_journal': 'nimporte-quoi',
                             'pay_montant': '1000', 'pay_mode': 'especes'})
        paiement = Paiement.objects.get(facture=facture)
        self.assertIsNone(paiement.caisse)

    def test_une_caisse_inexistante_n_empeche_pas_l_encaissement(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('500'))
        self._client().post(reverse('facturation:payer', args=[facture.pk]),
                            {'pay_journal': '999999',
                             'pay_montant': '500', 'pay_mode': 'especes'})
        self.assertIsNone(Paiement.objects.get(facture=facture).caisse)

    def test_supprimer_une_caisse_ne_supprime_pas_ses_paiements(self):
        # SET_NULL et non CASCADE : l'historique comptable survit au ménage
        # dans la configuration.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('2000'))
        self._client().post(reverse('facturation:payer', args=[facture.pk]),
                            {'pay_journal': str(self.caisse.pk),
                             'pay_montant': '2000', 'pay_mode': 'especes'})
        self.caisse.delete()
        paiement = Paiement.objects.get(facture=facture)
        self.assertEqual(paiement.montant, Decimal('2000'))
        self.assertIsNone(paiement.caisse)

    def test_la_fiche_facture_propose_les_vraies_caisses(self):
        # L'écran proposait cinq journaux écrits en dur, dont aucun n'existait
        # en base : « CAISSE ACCUEIL », « CAISSE SOINS », « BANQUE »…
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        contenu = self._client().get(
            reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('value="%d"' % self.caisse.pk, contenu)
        self.assertIn('>CAISSE TOUMBOKRO</option>', contenu)
        for disparu in ('caisse_accueil', 'caisse_soins'):
            self.assertNotIn('value="%s"' % disparu, contenu)

    def test_la_caisse_apparait_sur_le_recapitulatif_des_paiements(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = self._client()
        client.post(reverse('facturation:payer', args=[facture.pk]),
                    {'pay_journal': str(self.caisse.pk),
                     'pay_montant': '1000', 'pay_mode': 'especes'})
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('<th>Caisse</th>', contenu)
        self.assertIn('<td>Caisse Toumbokro</td>', contenu)

    def test_le_gabarit_de_creation_transmet_bien_le_journal(self):
        """Le JS doit poster `pay_journal`.

        Les tests ci-dessus l'envoient directement à la vue : ils ne verraient
        donc pas le bug d'origine, où le champ s'affichait mais n'était jamais
        joint au formulaire. Ce garde-fou surveille la ligne qui le joint.
        """
        contenu = self._client().get(
            reverse('facturation:create') + '?patient=%s' % self.patient.pk
        ).content.decode()
        self.assertIn("addHidden('pay_journal'", contenu,
                      "Le formulaire de création n'envoie plus le journal au serveur")


# ─── Le total encaissé d'une caisse ────────────────────────────────────────────

class TestTotalEncaisse(TestCase):
    """Le total d'une caisse se calcule, il ne se stocke plus.

    `Caisse.solde_actuel` existait mais n'était écrit par aucun code : ses
    quatre valeurs totalisaient 1 326 040 F quand l'ensemble des paiements
    jamais enregistrés en pesait 79 701. Un nombre que personne ne tient finit
    par mentir, et celui-là s'affichait à l'écran.
    """

    def setUp(self):
        self.patient = _patient('TOT')
        self.caisse = Caisse.objects.create(nom='Caisse Toumbokro', code='CTB1')
        self.autre = Caisse.objects.create(nom='Caisse pharmacie', code='CPH1')
        self.caissier = _caisse_user('u_tot_caisse')

    def _encaisser(self, montant, caisse):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal(montant))
        client = Client()
        client.login(username='u_tot_caisse', password='x')
        client.post(reverse('facturation:payer', args=[facture.pk]),
                    {'pay_journal': str(caisse.pk), 'pay_montant': str(montant),
                     'pay_mode': 'especes'})

    def test_une_caisse_sans_paiement_est_a_zero(self):
        self.assertEqual(self.caisse.total_encaisse, 0)

    def test_le_total_suit_les_encaissements(self):
        self._encaisser(3000, self.caisse)
        self._encaisser(2000, self.caisse)
        self.assertEqual(self.caisse.total_encaisse, Decimal('5000'))

    def test_chaque_caisse_a_son_propre_total(self):
        self._encaisser(3000, self.caisse)
        self._encaisser(1000, self.autre)
        self.assertEqual(self.caisse.total_encaisse, Decimal('3000'))
        self.assertEqual(self.autre.total_encaisse, Decimal('1000'))

    def test_un_paiement_sans_caisse_ne_compte_nulle_part(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('700'))
        Paiement.objects.create(facture=facture, montant=Decimal('700'),
                                mode_paiement='especes')
        self.assertEqual(self.caisse.total_encaisse, 0)
        self.assertEqual(self.autre.total_encaisse, 0)

    def test_le_tableau_affiche_le_total_et_non_un_solde(self):
        self._encaisser(3000, self.caisse)
        client = Client()
        client.login(username='u_tot_caisse', password='x')
        client.force_login(User.objects.create_superuser('su_tot', password='x'))
        contenu = client.get(reverse('facturation:caisses_list')).content.decode()
        self.assertIn('Total encaissé', contenu)
        self.assertIn('<td class="cfg-solde">3000 F</td>', contenu)

    def test_le_tableau_reste_trie_par_nom(self):
        # L'annotation ajoute un GROUP BY, qui fait tomber l'ordre du Meta.
        client = Client()
        client.force_login(User.objects.create_superuser('su_tri', password='x'))
        contenu = client.get(reverse('facturation:caisses_list')).content.decode()
        noms = re.findall(r'<td style="font-weight:600;">([^<]+)</td>', contenu)
        self.assertEqual(noms, sorted(noms))


# ─── Modes de paiement acceptés par caisse ─────────────────────────────────────

class TestModesParCaisse(TestCase):
    """Chaque caisse déclare les modes qu'elle accepte, l'encaissement s'y réduit."""

    def setUp(self):
        self.patient = _patient('MOD')
        self.caisse = Caisse.objects.create(nom='Caisse Toumbokro', code='CTB1')
        self.gestionnaire = User.objects.create_user('u_mod_gest', password='x')
        self.gestionnaire.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='facturation', codename__endswith='_caisse'))

    def _client(self, username='u_mod_gest'):
        client = Client()
        client.login(username=username, password='x')
        return client

    # ── Le modèle ──
    def test_une_caisse_neuve_accepte_les_especes(self):
        # Le défaut du modèle, et la reprise appliquée aux caisses existantes.
        self.assertEqual(self.caisse.modes, ['especes'])

    def test_le_reglage_restreint_les_modes(self):
        self.caisse.modes_paiement = 'especes,mobile_money'
        self.assertEqual(self.caisse.modes, ['especes', 'mobile_money'])
        self.assertEqual(self.caisse.modes_libelles, ['Espèces', 'Mobile Money'])

    def test_les_modes_gardent_l_ordre_du_modele(self):
        self.caisse.modes_paiement = 'bon,especes'
        self.assertEqual(self.caisse.modes, ['especes', 'bon'])

    def test_un_code_inconnu_est_ignore(self):
        self.caisse.modes_paiement = 'especes,bitcoin'
        self.assertEqual(self.caisse.modes, ['especes'])

    def test_le_mode_bon_est_proposable(self):
        self.caisse.modes_paiement = 'especes,bon'
        self.assertEqual(self.caisse.modes_libelles, ['Espèces', 'Bon'])

    # ── Le formulaire ──
    def test_le_formulaire_enregistre_les_cases_cochees(self):
        self._client().post(reverse('facturation:caisse_edit', args=[self.caisse.pk]),
                            {'nom': self.caisse.nom, 'code': self.caisse.code, 'actif': 'on',
                             'modes_paiement': ['especes', 'cheque']})
        self.caisse.refresh_from_db()
        self.assertEqual(self.caisse.modes, ['especes', 'cheque'])

    def test_tout_cocher_enregistre_tous_les_modes(self):
        tous = [code for code, _ in Paiement.MODE]
        self._client().post(reverse('facturation:caisse_edit', args=[self.caisse.pk]),
                            {'nom': self.caisse.nom, 'code': self.caisse.code,
                             'actif': 'on', 'modes_paiement': tous})
        self.caisse.refresh_from_db()
        self.assertEqual(self.caisse.modes, tous)

    def test_tout_decocher_retombe_sur_les_especes(self):
        # Une caisse qui n'accepterait rien ne serait pas une caisse.
        self._client().post(reverse('facturation:caisse_edit', args=[self.caisse.pk]),
                            {'nom': self.caisse.nom, 'code': self.caisse.code, 'actif': 'on'})
        self.caisse.refresh_from_db()
        self.assertEqual(self.caisse.modes, ['especes'])

    def test_un_code_inconnu_seul_retombe_sur_les_especes(self):
        self.caisse.modes_paiement = 'bitcoin'
        self.assertEqual(self.caisse.modes, ['especes'])

    # ── Les écrans d'encaissement ──
    def test_la_caisse_porte_ses_modes_dans_la_page(self):
        # C'est cet attribut que lit le script qui réduit le menu.
        self.caisse.modes_paiement = 'especes,bon'
        self.caisse.save()
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = self._client()
        client.force_login(User.objects.create_superuser('su_mod', password='x'))
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('data-modes="especes,bon"', contenu)

    def test_le_mode_bon_est_proposé_comme_les_autres(self):
        # Les gabarits listaient cinq modes en dur ; `bon` manquait alors que
        # Paiement.MODE le connaît, et un paiement par bon était insaisissable.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = Client()
        client.force_login(User.objects.create_superuser('su_bon', password='x'))
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('<option value="bon">Bon</option>', contenu)

    def test_le_champ_compte_bancaire_a_disparu_des_deux_ecrans(self):
        # Sa liste n'a jamais eu la moindre option, et le serveur ne lisait
        # même pas le champ de la fiche facture.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = Client()
        client.force_login(User.objects.create_superuser('su_cb', password='x'))
        for url in (reverse('facturation:detail', args=[facture.pk]),
                    reverse('facturation:create') + '?patient=%s' % self.patient.pk):
            contenu = client.get(url).content.decode()
            self.assertNotIn('pay_compte', contenu, url)
            self.assertNotIn('pay-compte', contenu, url)


# ─── Monnaie à rendre ──────────────────────────────────────────────────────────

class TestMonnaieARendre(TestCase):
    """Ce que le patient tend, et ce qu'on lui rend.

    `montant` reste ce qui était dû : compter le billet entier gonflerait le
    total de la caisse de la monnaie rendue.
    """

    def setUp(self):
        self.patient = _patient('MON')
        self.caisse = Caisse.objects.create(nom='Caisse Toumbokro', code='CTB1',
                                            modes_paiement='especes,mobile_money')
        _caisse_user('u_mon_caisse')

    def _encaisser(self, montant, **extra):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal(montant))
        client = Client()
        client.login(username='u_mon_caisse', password='x')
        donnees = {'pay_journal': str(self.caisse.pk), 'pay_montant': str(montant),
                   'pay_mode': 'especes'}
        donnees.update(extra)
        client.post(reverse('facturation:payer', args=[facture.pk]), donnees)
        return Paiement.objects.get(facture=facture)

    def test_la_monnaie_est_la_difference(self):
        paiement = self._encaisser(6000, pay_recu='10000')
        self.assertEqual(paiement.montant, Decimal('6000'))
        self.assertEqual(paiement.montant_recu, Decimal('10000'))
        self.assertEqual(paiement.monnaie_rendue, Decimal('4000'))

    def test_le_montant_du_paiement_reste_le_du_et_non_le_billet(self):
        # Sinon le total encaissé de la caisse gonflerait de la monnaie rendue.
        self._encaisser(6000, pay_recu='10000')
        self.assertEqual(self.caisse.total_encaisse, Decimal('6000'))

    def test_l_appoint_exact_ne_rend_rien(self):
        self.assertEqual(self._encaisser(5000, pay_recu='5000').monnaie_rendue, 0)

    def test_moins_que_le_du_ne_rend_pas_de_monnaie_negative(self):
        # Le règlement partiel en espèces est un cas réel : on ne le refuse pas.
        paiement = self._encaisser(5000, pay_recu='3000')
        self.assertEqual(paiement.monnaie_rendue, 0)

    def test_sans_saisie_il_n_y_a_pas_de_monnaie(self):
        paiement = self._encaisser(5000)
        self.assertIsNone(paiement.montant_recu)
        self.assertIsNone(paiement.monnaie_rendue)

    def test_hors_especes_le_recu_est_ignore(self):
        # Un champ resté rempli d'un mode précédent fausserait le reçu.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('2000'))
        client = Client()
        client.login(username='u_mon_caisse', password='x')
        client.post(reverse('facturation:payer', args=[facture.pk]),
                    {'pay_journal': str(self.caisse.pk), 'pay_montant': '2000',
                     'pay_mode': 'mobile_money', 'pay_recu': '5000'})
        self.assertIsNone(Paiement.objects.get(facture=facture).montant_recu)

    def test_une_saisie_illisible_n_empeche_pas_l_encaissement(self):
        paiement = self._encaisser(1000, pay_recu='beaucoup')
        self.assertEqual(paiement.montant, Decimal('1000'))
        self.assertIsNone(paiement.montant_recu)

    def test_les_colonnes_recu_et_rendu_apparaissent(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('6000'))
        client = Client()
        client.login(username='u_mon_caisse', password='x')
        client.post(reverse('facturation:payer', args=[facture.pk]),
                    {'pay_journal': str(self.caisse.pk), 'pay_montant': '6000',
                     'pay_mode': 'especes', 'pay_recu': '10000'})
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('<th class="td-right">Reçu</th>', contenu)
        self.assertIn('<th class="td-right">Rendu</th>', contenu)

    def test_le_champ_de_saisie_est_present_sur_la_modale(self):
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = Client()
        client.login(username='u_mon_caisse', password='x')
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('id="pay-recu"', contenu)
        self.assertIn('id="pay-monnaie"', contenu)

    def test_les_listes_passent_au_dessus_de_la_modale(self):
        # Rendues dans le <body>, elles s'affichaient derrière : on cliquait et
        # rien n'apparaissait.
        facture = _facture(self.patient, statut='emise', montant_total=Decimal('1000'))
        client = Client()
        client.login(username='u_mon_caisse', password='x')
        contenu = client.get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('.ts-dropdown { z-index: 10000 !important; }', contenu)


# ─── Le type de facture se déduit du contenu ───────────────────────────────────

class TestTypeDeduitDesLignes(TestCase):
    """Une facture peut mélanger les natures, et son type suit ce qu'on y met.

    L'écran de création l'interdisait : le type filtrait les désignations
    proposées, et changer de type vidait toutes les lignes déjà saisies. Il ne
    reste plus rien de ce filtre — c'est le type qui suit le contenu, et non
    l'inverse.
    """

    def setUp(self):
        self.patient = _patient('TYP')
        self.user = User.objects.create_superuser('su_typ', password='x')
        self.consultation = self._article('CS', 'Consultations', 'CONSULTATION ADULTE', 5000)
        self.soin = self._article('SN', 'Soins', 'PANSEMENT', 3000)
        self.radio = self._article('RD', 'Radiologies', 'ASP FACE', 12000)

    def _article(self, code, nom_cat, nom, prix):
        from services.models import CategorieArticle, Articleservice
        categorie, _ = CategorieArticle.objects.get_or_create(
            code=code, defaults={'nom': nom_cat})
        return Articleservice.objects.create(
            nom=nom, categorie=categorie, prix_vente=Decimal(prix))

    def _creer(self, articles):
        donnees = {'type_facture': 'consultation', 'montant_assurance': '0',
                   'ticket_moderateur': '0', 'notes': ''}
        for i, article in enumerate(articles):
            donnees.update({
                'ligne_libelle_%d' % i: article.nom,
                'ligne_service_%d' % i: str(article.pk),
                'ligne_qte_%d' % i: '1',
                'ligne_prix_%d' % i: str(int(article.prix_vente)),
                'ligne_remise_%d' % i: '0',
            })
        client = Client()
        client.force_login(self.user)
        client.post(reverse('facturation:create') + '?patient=%s' % self.patient.pk,
                    donnees, follow=True)
        return Facture.objects.order_by('-pk').first()

    def test_une_seule_nature_donne_ce_type(self):
        self.assertEqual(self._creer([self.consultation]).type_facture, 'consultation')
        self.assertEqual(self._creer([self.soin]).type_facture, 'soins')
        self.assertEqual(self._creer([self.radio]).type_facture, 'imagerie')

    def test_deux_natures_donnent_mixte(self):
        facture = self._creer([self.consultation, self.soin])
        self.assertEqual(facture.type_facture, 'mixte')
        self.assertEqual(facture.types_des_lignes(), ['consultation', 'soins'])

    def test_plusieurs_lignes_de_la_meme_nature_ne_donnent_pas_mixte(self):
        autre_soin = self._article('SN', 'Soins', 'SUTURE', 4000)
        self.assertEqual(self._creer([self.soin, autre_soin]).type_facture, 'soins')

    def test_le_type_poste_par_le_navigateur_est_ignore(self):
        # Le champ est `disabled` : ce que le navigateur enverrait ne compte pas.
        facture = self._creer([self.radio])
        self.assertEqual(facture.type_facture, 'imagerie')

    def test_une_ligne_sans_article_ne_compte_pour_aucune_nature(self):
        # Libellé tapé à la main : on ne sait pas ce que c'est, et le deviner
        # d'après le texte serait un pari.
        facture = _facture(self.patient, statut='brouillon', montant_total=Decimal('0'))
        LigneFacture.objects.create(facture=facture, libelle='Divers',
                                    quantite=1, prix_unitaire=Decimal('1000'))
        self.assertEqual(facture.types_des_lignes(), [])
        self.assertIsNone(facture.deduire_type())

    def test_sans_rien_pour_trancher_le_type_existant_est_conserve(self):
        facture = _facture(self.patient, statut='brouillon', montant_total=Decimal('0'))
        facture.type_facture = 'hospitalisation'
        facture.save(update_fields=['type_facture'])
        facture.appliquer_type_deduit()
        facture.refresh_from_db()
        self.assertEqual(facture.type_facture, 'hospitalisation')

    def test_mixte_fait_partie_des_types(self):
        self.assertIn('mixte', dict(Facture.TYPE))

    def test_l_ecran_ne_filtre_plus_les_designations(self):
        # `_TYPE_CATS` interdisait les lignes d'une autre nature ; le vidage des
        # lignes au changement de type allait avec.
        client = Client()
        client.force_login(self.user)
        contenu = client.get(
            reverse('facturation:create') + '?patient=%s' % self.patient.pk).content.decode()
        self.assertNotIn('_TYPE_CATS', contenu)
        self.assertNotIn('getActiveCategories', contenu)

    def test_la_ligne_transmet_l_identifiant_de_l_article(self):
        client = Client()
        client.force_login(self.user)
        contenu = client.get(
            reverse('facturation:create') + '?patient=%s' % self.patient.pk).content.decode()
        self.assertIn('name="ligne_service_0"', contenu)

    def test_rouvrir_une_facture_ne_perd_pas_la_nature_des_lignes(self):
        facture = self._creer([self.consultation, self.soin])
        client = Client()
        client.force_login(self.user)
        contenu = client.get(reverse('facturation:edit', args=[facture.pk])).content.decode()
        for article in (self.consultation, self.soin):
            self.assertIn('value="%d"' % article.pk, contenu)
