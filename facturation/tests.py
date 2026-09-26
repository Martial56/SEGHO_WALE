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
    """Utilisateur habilité à encaisser.

    Le groupe porte volontairement un nom fantaisiste : c'est la permission qui
    ouvre la caisse, jamais le nom du groupe. Si ce test passe avec « Guichet du
    lundi », il passera avec n'importe quel nom choisi dans /admin/.
    """
    user = User.objects.create_user(username, password='x')
    groupe, _ = Group.objects.get_or_create(name='Guichet du lundi')
    groupe.permissions.add(
        Permission.objects.get(content_type__app_label='facturation',
                               codename='can_encaisser'))
    user.groups.add(groupe)
    return user


# ─── Tests can_manage_paiement ──────────────────────────────────────────────────

class TestCanManagePaiement(TestCase):

    def test_superuser_autorise(self):
        su = User.objects.create_superuser('su_cmp', password='x')
        self.assertTrue(can_manage_paiement(su))

    def test_user_sans_groupe_refuse(self):
        user = User.objects.create_user('u_cmp', password='x')
        self.assertFalse(can_manage_paiement(user))

    def test_un_groupe_portant_la_permission_autorise(self):
        user = _caisse_user('u_cmp_caisse')
        self.assertTrue(can_manage_paiement(user))

    def test_un_groupe_sans_la_permission_refuse(self):
        user = User.objects.create_user('u_cmp_autre', password='x')
        autre, _ = Group.objects.get_or_create(name='Accueil')
        user.groups.add(autre)
        self.assertFalse(can_manage_paiement(user))

    def test_la_permission_accordee_en_direct_autorise(self):
        """Sans aucun groupe : l'onglet « Permissions de l'utilisateur » suffit."""
        user = User.objects.create_user('u_cmp_direct', password='x')
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label='facturation',
                                   codename='can_encaisser'))
        self.assertTrue(can_manage_paiement(User.objects.get(pk=user.pk)))


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

    def test_facture_payer_autorise_avec_la_permission(self):
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

    def test_avec_la_permission_le_paiement_passe(self):
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
                # Référence préfixée depuis que les produits de la pharmacie
                # partagent la liste : « a: » pour un article du catalogue,
                # « p: » pour un produit du stock. Les deux numérotent chacun
                # de leur côté.
                'ligne_service_%d' % i: 'a:%s' % article.pk,
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
            # Préfixée « a: » : l'article 12 et le produit 12 se ressemblent
            # trop depuis que les deux catalogues partagent la même liste.
            self.assertIn('value="a:%d"' % article.pk, contenu)


# ─── Liste des factures : filtres avancés et regroupements ──────────────────────

class TestListeDesFactures(TestCase):
    """La liste passe par core.listing, comme les autres modules.

    Son menu était écrit à la main dans le gabarit : un statut, un type, un
    intervalle de dates, aucun regroupement. Ce qui est vérifié ici, ce sont les
    trois promesses de la brique — les valeurs d'une famille se cumulent en OU,
    les familles se croisent en ET, et les comptes des bandes de groupe sont
    ceux de la sélection entière.
    """

    def setUp(self):
        from services.models import Articleservice, CategorieArticle

        self.user = User.objects.create_superuser('su_liste', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        self.homme = _patient('LH')
        self.femme = Patient.objects.create(
            nom='TestLF', prenoms='Patiente', date_naissance='1992-03-04',
            sexe='F', telephone='0700000001')

        def article(code, nom_cat, nom):
            categorie, _ = CategorieArticle.objects.get_or_create(
                code=code, defaults={'nom': nom_cat})
            return Articleservice.objects.create(
                nom=nom, categorie=categorie, prix_vente=Decimal('5000'))

        self.art_cs = article('CS', 'Consultations', 'CONSULTATION ADULTE')
        self.art_rd = article('RD', 'Radiologies', 'ASP FACE')

    # ── Fabriques ──────────────────────────────────────────────────────────

    def _facture(self, patient=None, statut='emise', type_facture='consultation',
                 total='10000', paye='0', articles=()):
        facture = Facture.objects.create(
            patient=patient or self.homme, type_facture=type_facture,
            statut=statut, montant_total=Decimal(total),
            montant_paye=Decimal(paye), cree_par=self.user)
        for art in articles:
            LigneFacture.objects.create(
                facture=facture, article=art, libelle=art.nom,
                quantite=1, prix_unitaire=art.prix_vente, remise=0)
        return facture

    def _page(self, requete=''):
        reponse = self.client.get(reverse('facturation:list') + requete)
        self.assertEqual(reponse.status_code, 200)
        return reponse

    def _numeros(self, requete=''):
        """Numéros des factures affichées, quel que soit le regroupement."""
        return set(re.findall(r'VTES/\d{4}/\d+',
                              self._page(requete).content.decode()))

    def _groupes(self, requete):
        """Bandes de groupe rendues : {libellé: compte}."""
        html = self._page(requete).content.decode()
        motif = (r'<tr class="lst-groupe[^"]*"[^>]*>.*?</i>\s*(.+?)\s*'
                 r'<span class="lst-compte">(\d+)</span>')
        return {m.group(1): int(m.group(2))
                for m in re.finditer(motif, html, re.S)}

    # ── La colonne Type ────────────────────────────────────────────────────

    def test_la_colonne_type_a_quitte_le_tableau(self):
        """Cinq natures dans une cellule ne se lisent pas : on les voit ailleurs."""
        self._facture(articles=[self.art_cs])
        html = self._page('?filter=').content.decode()

        self.assertIn('<span class="col-label">Statut</span>', html)
        self.assertNotIn('<span class="col-label">Type</span>', html)
        # Mais le type reste filtrable et regroupable.
        self.assertIn('Type de facture', html)

    # ── Cumul et croisement ────────────────────────────────────────────────

    def test_deux_valeurs_d_une_meme_famille_se_cumulent(self):
        emise = self._facture(statut='emise')
        payee = self._facture(statut='payee')
        annulee = self._facture(statut='annulee')

        retenus = self._numeros('?filter=&filter=statut_emise&filter=statut_payee')
        self.assertIn(emise.numero, retenus)
        self.assertIn(payee.numero, retenus)
        self.assertNotIn(annulee.numero, retenus)

    def test_deux_familles_differentes_se_croisent(self):
        cible = self._facture(patient=self.femme, statut='payee')
        bon_genre = self._facture(patient=self.femme, statut='emise')
        bon_statut = self._facture(patient=self.homme, statut='payee')

        retenus = self._numeros('?filter=&filter=statut_payee&filter=genre_F')
        self.assertEqual(retenus, {cible.numero})
        self.assertNotIn(bon_genre.numero, retenus)
        self.assertNotIn(bon_statut.numero, retenus)

    # ── Le contenu, et non le seul type enregistré ──────────────────────────

    def test_une_facture_mixte_se_retrouve_sous_chacune_de_ses_natures(self):
        """« Contient des actes de » lit les lignes ; « Type de facture » lit le champ.

        C'est ce qui rend la colonne Type superflue : une facture qui mêle une
        consultation et une radio reste trouvable sous l'une comme sous l'autre.
        """
        mixte = self._facture(type_facture='mixte',
                              articles=[self.art_cs, self.art_rd])

        self.assertIn(mixte.numero, self._numeros('?filter=&filter=contient_consultation'))
        self.assertIn(mixte.numero, self._numeros('?filter=&filter=contient_imagerie'))
        # Le type enregistré, lui, ne répond qu'à « Mixte ».
        self.assertIn(mixte.numero, self._numeros('?filter=&filter=type_mixte'))
        self.assertNotIn(mixte.numero, self._numeros('?filter=&filter=type_consultation'))

    def test_une_ligne_sans_article_ne_compte_pour_aucune_nature(self):
        """Saisie libre : on ne sait pas ce que c'est, on ne le devine pas."""
        facture = self._facture(type_facture='consultation')
        LigneFacture.objects.create(facture=facture, libelle='Pansement spécial',
                                    quantite=1, prix_unitaire=Decimal('2000'), remise=0)

        for nature in ('consultation', 'soins', 'imagerie'):
            self.assertNotIn(facture.numero,
                             self._numeros(f'?filter=&filter=contient_{nature}'))

    # ── Regroupements ──────────────────────────────────────────────────────

    def test_le_regroupement_par_type_compte_toute_la_selection(self):
        for _ in range(3):
            self._facture(type_facture='soins')
        self._facture(type_facture='mixte')

        groupes = self._groupes('?filter=&group=type')
        self.assertEqual(groupes.get('Soins'), 3)
        self.assertEqual(groupes.get('Mixte'), 1)

    def test_deux_versements_dans_la_meme_caisse_ne_comptent_qu_une_fois(self):
        """Le piège de la jointure : core.listing n'appelle jamais `distinct()`.

        Les familles et dimensions qui passent par les paiements sont donc
        écrites en sous-requête. Sans cela, une facture réglée en deux fois
        apparaîtrait deux fois sous sa caisse, et le compte de la bande aussi.
        """
        caisse = Caisse.objects.create(nom='Caisse centrale', code='CC')
        facture = self._facture(total='10000', paye='10000')
        for montant in ('6000', '4000'):
            Paiement.objects.create(facture=facture, montant=Decimal(montant),
                                    mode_paiement='especes', caisse=caisse)

        self.assertEqual(self._groupes('?filter=&group=caisse').get('Caisse centrale'), 1)
        # Et le filtre par cette caisse ne la sort qu'une fois non plus.
        self.assertEqual(
            self._page(f'?filter=&filter=caisse_{caisse.pk}').context['total'], 1)

    def test_une_facture_reglee_dans_deux_caisses_apparait_sous_les_deux(self):
        accueil = Caisse.objects.create(nom='Accueil', code='ACC')
        centrale = Caisse.objects.create(nom='Centrale', code='CEN')
        facture = self._facture(total='10000', paye='10000')
        Paiement.objects.create(facture=facture, montant=Decimal('4000'),
                                mode_paiement='especes', caisse=accueil)
        Paiement.objects.create(facture=facture, montant=Decimal('6000'),
                                mode_paiement='especes', caisse=centrale)

        groupes = self._groupes('?filter=&group=caisse')
        self.assertEqual(groupes.get('Accueil'), 1)
        self.assertEqual(groupes.get('Centrale'), 1)

    def test_une_facture_sans_encaissement_a_son_propre_groupe(self):
        facture = self._facture()
        self.assertEqual(self._groupes('?filter=&group=caisse').get('Non encaissée'), 1)
        self.assertIn(facture.numero, self._numeros('?filter=&filter=caisse_aucune'))

    # ── Période et tri ─────────────────────────────────────────────────────

    def test_la_liste_s_ouvre_sur_les_factures_du_jour(self):
        from datetime import timedelta

        from django.utils import timezone

        aujourdhui = self._facture()
        ancienne = self._facture()
        # `date_emission` est en auto_now_add : seul un UPDATE la déplace.
        Facture.objects.filter(pk=ancienne.pk).update(
            date_emission=timezone.now() - timedelta(days=40))

        sans_parametre = self._numeros()
        self.assertIn(aujourdhui.numero, sans_parametre)
        self.assertNotIn(ancienne.numero, sans_parametre)
        # Le marqueur « filter= » vide lève la période par défaut.
        self.assertIn(ancienne.numero, self._numeros('?filter='))

    def test_la_colonne_reste_est_triable(self):
        """`solde_restant` est une propriété : sans annotation, rien à trier."""
        petit = self._facture(total='10000', paye='9000')     # reste 1 000
        gros = self._facture(total='10000', paye='1000')      # reste 9 000

        html = self._page('?filter=&tri=reste&sens=desc').content.decode()
        self.assertLess(html.index(gros.numero), html.index(petit.numero))


class TestCartesSuiventLaSelection(TestCase):
    """Total facturé, Reçu et En attente portent sur ce qui est affiché.

    Elles additionnaient tout le centre : la liste s'ouvrant sur la journée, on
    lisait le total depuis l'ouverture au-dessus des deux factures du jour. Deux
    nombres côte à côte qui ne parlaient pas de la même chose.
    """

    def setUp(self):
        self.user = User.objects.create_superuser('su_cartes', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.patient = _patient('CAR')

    def _facture(self, type_facture='consultation', total='10000', paye='0'):
        return Facture.objects.create(
            patient=self.patient, type_facture=type_facture, statut='emise',
            montant_total=Decimal(total), montant_paye=Decimal(paye),
            cree_par=self.user)

    def _stats(self, requete):
        reponse = self.client.get(reverse('facturation:list') + requete)
        self.assertEqual(reponse.status_code, 200)
        return reponse.context['stats']

    def test_un_filtre_de_type_restreint_les_montants(self):
        self._facture('consultation', '10000', '10000')
        self._facture('soins', '4000', '1000')

        tout = self._stats('?filter=')
        self.assertEqual(tout['montant_total'], 14000)
        self.assertEqual(tout['montant_recu'], 11000)
        self.assertEqual(tout['montant_attente'], 3000)
        self.assertEqual(tout['nb_factures'], 2)

        soins = self._stats('?filter=&filter=type_soins')
        self.assertEqual(soins['montant_total'], 4000)
        self.assertEqual(soins['montant_recu'], 1000)
        self.assertEqual(soins['montant_attente'], 3000)
        self.assertEqual(soins['nb_factures'], 1)

    def test_la_periode_restreint_les_montants(self):
        from datetime import timedelta

        from django.utils import timezone

        self._facture(total='10000', paye='10000')
        ancienne = self._facture(total='7000', paye='7000')
        Facture.objects.filter(pk=ancienne.pk).update(
            date_emission=timezone.now() - timedelta(days=40))

        self.assertEqual(self._stats('')['montant_total'], 10000)       # aujourd'hui
        self.assertEqual(self._stats('?filter=')['montant_total'], 17000)

    def test_une_recherche_sans_resultat_ramene_les_cartes_a_zero(self):
        self._facture(total='10000', paye='10000')
        vide = self._stats('?filter=&q=zzzzintrouvable')
        self.assertEqual(vide['montant_total'], 0)
        self.assertEqual(vide['montant_recu'], 0)
        self.assertEqual(vide['montant_attente'], 0)
        self.assertEqual(vide['nb_factures'], 0)

    def test_les_cartes_sont_dans_la_zone_echangee_par_l_ajax(self):
        """Sans cela les montants resteraient ceux de l'affichage précédent.

        Le rafraîchissement n'échange que `subheader-controls`, `list-stats` et
        `list-result` : des cartes laissées à l'extérieur seraient justes au
        chargement de la page et fausses dès le premier clic sur un filtre.
        """
        self._facture(total='10000', paye='10000')
        html = self.client.get(reverse('facturation:list') + '?filter=').content.decode()

        debut = html.index('id="list-stats"')
        fin = html.index('<!-- ══ Subheader ══ -->')
        self.assertLess(debut, fin)
        self.assertIn('Total facturé', html[debut:fin])
        self.assertIn('En attente', html[debut:fin])

        # Et la brique sait échanger cette zone.
        from django.template.loader import render_to_string
        self.assertIn("'list-stats'",
                      render_to_string('includes/listing/page_js.html'))


class TestOngletActifDuModule(TestCase):
    """L'onglet du haut doit dire où l'on est.

    Le test portait sur les seuls noms `list`, `create` et `edit` : la fiche
    d'une facture, son encaissement et son impression laissaient l'onglet
    éteint. Il portait de surcroît sur `list` alors que `/facturation/` était
    servie par une route en double déclarée dans core, nommée `facturation_list`
    — l'onglet restait donc éteint jusque sur la liste elle-même.
    """

    def setUp(self):
        self.user = User.objects.create_superuser('su_nav', password='x')
        self.client = Client()
        self.client.force_login(self.user)

    def _onglets(self, url):
        """(Factures actif ?, Configuration actif ?) lus dans le balisage."""
        html = self.client.get(url).content.decode()
        nav = html[html.index('<nav class="o-nav">'):html.index('</nav>')]
        etats = re.findall(r'class="(o-nav-link ?[a-z]*)"', nav)
        self.assertEqual(len(etats), 2, nav)
        return tuple('active' in e for e in etats)

    def test_l_onglet_factures_est_allume_sur_la_liste(self):
        self.assertEqual(self._onglets(reverse('facturation:list')), (True, False))

    def test_l_onglet_factures_reste_allume_sur_les_ecrans_de_facture(self):
        facture = Facture.objects.create(
            patient=_patient('NAV'), type_facture='consultation',
            statut='emise', montant_total=Decimal('1000'), cree_par=self.user)

        for url in (reverse('facturation:create'),
                    reverse('facturation:detail', args=[facture.pk]),
                    reverse('facturation:edit', args=[facture.pk])):
            self.assertEqual(self._onglets(url), (True, False), url)

    def test_l_onglet_configuration_prend_le_relais_sur_les_caisses(self):
        for url in (reverse('facturation:caisses_list'),
                    reverse('facturation:caisse_create')):
            self.assertEqual(self._onglets(url), (False, True), url)


class TestLienDeLaPastille(TestCase):
    """La pastille du tableau de bord doit tomber sur la bonne sélection.

    Elle visait `filter=statut:emise`, le vocabulaire de l'ancien menu écrit à
    la main. La liste refaite lit `statut_emise` : le lien s'ouvrait donc sans
    aucun filtre, et affichait tout au lieu des seules factures à encaisser.
    Rien ne l'aurait signalé — la page répondait 200.
    """

    def setUp(self):
        self.user = User.objects.create_superuser('su_past', password='x')
        self.client = Client()
        self.client.force_login(self.user)
        self.patient = _patient('PAS')

    def _facture(self, statut):
        return Facture.objects.create(
            patient=self.patient, type_facture='consultation', statut=statut,
            montant_total=Decimal('5000'), cree_par=self.user)

    def test_le_lien_de_la_pastille_ne_montre_que_les_factures_a_encaisser(self):
        from core.pastilles import _facturation

        emise = self._facture('emise')
        payee = self._facture('payee')

        pastille = _facturation(self.user)
        self.assertEqual(pastille['total'], 1)

        reponse = self.client.get(pastille['url'])
        self.assertEqual(reponse.status_code, 200)
        numeros = {f.numero for f in reponse.context['page_obj']}
        self.assertEqual(numeros, {emise.numero})
        self.assertNotIn(payee.numero, numeros)
        # Et sans restriction de période : une facture en attente depuis la
        # semaine dernière est justement celle qu'on veut voir.
        self.assertEqual(reponse.context['periode_libelle'], 'toutes périodes')

    def test_la_liste_n_a_plus_qu_une_seule_route(self):
        """`/facturation/` était déclarée deux fois dans core/urls.py.

        La première, sans espace de noms, l'emportait : `resolver_match.url_name`
        valait `facturation_list`, et tout ce qui raisonnait sur le nom de la
        route — à commencer par l'onglet du menu — se trompait.
        """
        from django.urls import NoReverseMatch, resolve, reverse

        correspondance = resolve('/facturation/')
        self.assertEqual(correspondance.url_name, 'list')
        self.assertEqual(correspondance.namespace, 'facturation')

        with self.assertRaises(NoReverseMatch):
            reverse('facturation_list')


# ─── Les produits de la pharmacie sur la facture ───────────────────────────────

class TestProduitsSurLaFacture(TestCase):
    """On peut enfin facturer un médicament ou une paire de gants.

    L'écran ne proposait que `services.Articleservice` — 50 prestations et 100
    examens, aucun produit. Les médicaments et les consommables vivent dans
    `stock.Produit`, et ce qu'on peut remettre au patient est ce que la
    pharmacie du centre a en rayon, pas ce que dort la réserve centrale.
    """

    def setUp(self):
        from centres.models import Centre
        from pharmacie.models import StockPharmacie
        from stock.models import Produit

        self.toumbokro = Centre.objects.get_or_create(
            code='TOUMBOKRO', defaults={'nom': 'CMS WALE Toumbokro'})[0]
        self.yamoussoukro = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]

        self.user = User.objects.create_superuser('su_prod', password='x')
        profil = self.user.profile
        profil.centres.add(self.toumbokro, self.yamoussoukro)
        profil.centre_actif = self.toumbokro
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)
        # Le patient doit relever du centre actif : les écrans le cherchent avec
        # le gestionnaire cloisonné, et un patient sans centre sort en 404.
        self.patient = Patient.objects.create(
            nom='TestPrd', prenoms='Patient', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000', centre=self.toumbokro)

        self.gants = Produit.objects.create(
            nom='Gants de test', type='consommable',
            prix_achat=Decimal('50'), prix_vente=Decimal('200'))
        self.sirop = Produit.objects.create(
            nom='Sirop de test', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))

        for pharmacie, produit, qte in (
            ('wale_toumbokro', self.gants, '20'),
            ('wale_toumbokro', self.sirop, '0'),
            ('wale_yamoussoukro', self.gants, '3'),
            ('wale_yamoussoukro', self.sirop, '40'),
        ):
            sp, _ = StockPharmacie.objects.get_or_create(
                pharmacie=pharmacie, produit=produit)
            sp.quantite = Decimal(qte)
            sp.save(update_fields=['quantite'])

    # ── Outils ─────────────────────────────────────────────────────────────

    def _centre_actif(self, centre):
        profil = self.user.profile
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])

    def _designations(self):
        reponse = self.client.get(reverse('facturation:create'))
        self.assertEqual(reponse.status_code, 200)
        brut = re.search(
            r'id="donnees-designations" type="application/json">(.*?)</script>',
            reponse.content.decode(), re.S)
        self.assertIsNotNone(brut, "bloc de désignations introuvable")
        import json
        return {d['nom']: d for d in json.loads(brut.group(1))}

    def _creer_facture(self, lignes, payer=None):
        """`lignes` : liste de (référence, libellé, prix, quantité)."""
        donnees = {'type_facture': 'consultation', 'montant_assurance': '0',
                   'ticket_moderateur': '0', 'notes': ''}
        for i, (ref, libelle, prix, qte) in enumerate(lignes):
            donnees.update({
                f'ligne_libelle_{i}': libelle,
                f'ligne_service_{i}': ref,
                f'ligne_qte_{i}': str(qte),
                f'ligne_prix_{i}': str(prix),
                f'ligne_remise_{i}': '0',
            })
        if payer is not None:
            donnees.update({'pay_montant': str(payer), 'pay_mode': 'especes'})
        self.client.post(
            reverse('facturation:create') + f'?patient={self.patient.pk}',
            donnees, follow=True)
        # `all_objects` : hors requête, le gestionnaire cloisonné ne voit rien,
        # la facture appartenant au centre actif de l'utilisateur du test.
        return Facture.all_objects.order_by('-pk').first()

    def _en_rayon(self, produit, pharmacie='wale_toumbokro'):
        from pharmacie.models import StockPharmacie

        return StockPharmacie.objects.get(
            pharmacie=pharmacie, produit=produit).quantite

    # ── La liste proposée ──────────────────────────────────────────────────

    def test_les_produits_rejoignent_les_prestations(self):
        propose = self._designations()
        self.assertIn('Gants de test', propose)
        self.assertEqual(propose['Gants de test']['src'], 'p')
        self.assertEqual(propose['Gants de test']['stock'], 20)

    def test_le_stock_affiche_suit_le_centre(self):
        self.assertEqual(self._designations()['Gants de test']['stock'], 20)
        self._centre_actif(self.yamoussoukro)
        self.assertEqual(self._designations()['Gants de test']['stock'], 3)

    def test_une_rupture_est_proposee_mais_grisee(self):
        propose = self._designations()
        self.assertTrue(propose['Sirop de test']['rupture'])
        self.assertFalse(propose['Gants de test']['rupture'])

    # ── L'enregistrement ───────────────────────────────────────────────────

    def test_une_ligne_de_produit_retient_son_produit(self):
        facture = self._creer_facture([(f'p:{self.gants.pk}', 'Gants de test', 200, 2)])
        ligne = facture.lignes.first()
        self.assertEqual(ligne.produit_id, self.gants.pk)
        self.assertIsNone(ligne.article_id)

    def test_un_produit_en_rupture_n_est_pas_rattache(self):
        """L'écran grise, mais une liste déroulante ne protège de rien."""
        facture = self._creer_facture([(f'p:{self.sirop.pk}', 'Sirop de test', 500, 1)])
        self.assertIsNone(facture.lignes.first().produit_id)

    def test_un_produit_devient_une_facture_pharmacie(self):
        facture = self._creer_facture([(f'p:{self.gants.pk}', 'Gants de test', 200, 1)])
        self.assertEqual(facture.type_facture, 'pharmacie')

    def test_un_produit_et_une_consultation_donnent_mixte(self):
        from services.models import Articleservice, CategorieArticle

        categorie, _ = CategorieArticle.objects.get_or_create(
            code='CS', defaults={'nom': 'Consultations'})
        consultation = Articleservice.objects.create(
            nom='CONSULTATION TEST', categorie=categorie, prix_vente=Decimal('5000'))

        facture = self._creer_facture([
            (f'a:{consultation.pk}', 'CONSULTATION TEST', 5000, 1),
            (f'p:{self.gants.pk}', 'Gants de test', 200, 1),
        ])
        self.assertEqual(facture.type_facture, 'mixte')

    # ── La sortie de stock ─────────────────────────────────────────────────

    def test_le_stock_ne_bouge_pas_tant_que_la_facture_n_est_pas_soldee(self):
        """Un brouillon n'immobilise rien : le produit reste à qui le paiera."""
        self._creer_facture([(f'p:{self.gants.pk}', 'Gants de test', 200, 3)])
        self.assertEqual(self._en_rayon(self.gants), Decimal('20'))

    def test_le_paiement_sort_les_produits_du_stock(self):
        from pharmacie.models import MouvementPharmacie

        facture = self._creer_facture(
            [(f'p:{self.gants.pk}', 'Gants de test', 200, 3)], payer=600)
        self.assertEqual(facture.statut, 'payee')
        self.assertEqual(self._en_rayon(self.gants), Decimal('17'))

        mouvement = MouvementPharmacie.objects.get(
            reference=facture.numero, type='facture')
        self.assertEqual(mouvement.quantite, Decimal('3'))
        self.assertEqual(mouvement.stock_avant, Decimal('20'))
        self.assertEqual(mouvement.stock_apres, Decimal('17'))
        self.assertEqual(mouvement.pharmacie, 'wale_toumbokro')

    def test_un_reglement_partiel_ne_sort_rien(self):
        facture = self._creer_facture(
            [(f'p:{self.gants.pk}', 'Gants de test', 200, 3)], payer=200)
        self.assertNotEqual(facture.statut, 'payee')
        self.assertEqual(self._en_rayon(self.gants), Decimal('20'))

    def test_une_prestation_ne_touche_pas_au_stock(self):
        from pharmacie.models import MouvementPharmacie

        facture = self._creer_facture([('', 'Acte saisi à la main', 1000, 1)], payer=1000)
        self.assertEqual(facture.statut, 'payee')
        self.assertFalse(MouvementPharmacie.objects.filter(
            reference=facture.numero).exists())

    def test_le_stock_ne_sort_jamais_deux_fois(self):
        """Un double clic, un rejeu : le mouvement porte le numéro de facture."""
        from pharmacie.disponibilite import pharmacie_active
        from pharmacie.sorties import sortir_les_produits

        facture = self._creer_facture(
            [(f'p:{self.gants.pk}', 'Gants de test', 200, 3)], payer=600)
        self.assertEqual(self._en_rayon(self.gants), Decimal('17'))

        self.assertEqual(sortir_les_produits(facture, 'wale_toumbokro', self.user), 0)
        self.assertEqual(self._en_rayon(self.gants), Decimal('17'))

    def test_le_paiement_est_refuse_si_la_pharmacie_ne_peut_plus_servir(self):
        """La dernière boîte est partie entre la saisie et l'encaissement."""
        from pharmacie.models import StockPharmacie

        facture = self._creer_facture([(f'p:{self.gants.pk}', 'Gants de test', 200, 5)])
        StockPharmacie.objects.filter(
            pharmacie='wale_toumbokro', produit=self.gants).update(quantite=Decimal('2'))

        reponse = self.client.post(
            reverse('facturation:payer', args=[facture.pk]),
            {'pay_montant': '1000', 'pay_mode': 'especes'}, follow=True)

        facture.refresh_from_db()
        self.assertNotEqual(facture.statut, 'payee')
        self.assertEqual(self._en_rayon(self.gants), Decimal('2'))
        avertissements = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('ne peut plus servir' in m for m in avertissements),
                        avertissements)

    def test_annuler_une_facture_payee_rend_les_produits(self):
        facture = self._creer_facture(
            [(f'p:{self.gants.pk}', 'Gants de test', 200, 3)], payer=600)
        self.assertEqual(self._en_rayon(self.gants), Decimal('17'))

        self.client.post(reverse('facturation:edit', args=[facture.pk]),
                         {'action_annuler': '1'}, follow=True)

        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'annulee')
        self.assertEqual(self._en_rayon(self.gants), Decimal('20'))

    def test_annuler_une_facture_jamais_payee_ne_rend_rien(self):
        """Sinon l'annulation créditerait un stock qui n'a rien donné."""
        facture = self._creer_facture([(f'p:{self.gants.pk}', 'Gants de test', 200, 3)])
        self.client.post(reverse('facturation:edit', args=[facture.pk]),
                         {'action_annuler': '1'}, follow=True)
        self.assertEqual(self._en_rayon(self.gants), Decimal('20'))


class TestRetirerUneLigneNeFaitPasPerdreLesAutres(TestCase):
    """Retirer une ligne au milieu de la facture ne doit rien coûter.

    Le bouton « × » retire la ligne du tableau **sans renuméroter** les
    suivantes, et les indices viennent d'un compteur qui ne redescend jamais.
    La lecture s'arrêtait au premier indice absent : retirer une ligne du
    milieu de cinq n'en facturait plus que deux, et retirer la première
    laissait une facture **vide, à zéro franc**.

    C'est le geste le plus courant de la caisse — le patient annonce qu'il a
    déjà tel médicament, on l'enlève — et il faisait perdre le reste de la
    facture, sans un mot.
    """

    def test_un_trou_au_milieu_ne_perd_rien(self):
        facture = _facture(_patient('Trou'))
        total = _save_lignes(facture, {
            'ligne_libelle_0': 'Acte 1', 'ligne_qte_0': '1',
            'ligne_prix_0': '1000', 'ligne_remise_0': '0',
            # indice 1 : la ligne retirée par la caissière
            'ligne_libelle_2': 'Acte 3', 'ligne_qte_2': '1',
            'ligne_prix_2': '3000', 'ligne_remise_2': '0',
            'ligne_libelle_3': 'Acte 4', 'ligne_qte_3': '1',
            'ligne_prix_3': '4000', 'ligne_remise_3': '0',
        })
        self.assertEqual(total, 8000)
        self.assertEqual(facture.lignes.count(), 3)

    def test_la_premiere_ligne_retiree_ne_vide_pas_la_facture(self):
        facture = _facture(_patient('Prem'))
        total = _save_lignes(facture, {
            'ligne_libelle_1': 'Acte 2', 'ligne_qte_1': '1',
            'ligne_prix_1': '2000', 'ligne_remise_1': '0',
            'ligne_libelle_2': 'Acte 3', 'ligne_qte_2': '1',
            'ligne_prix_2': '3000', 'ligne_remise_2': '0',
        })
        self.assertEqual(total, 5000)
        self.assertEqual(facture.lignes.count(), 2)

    def test_les_lignes_restent_dans_l_ordre_du_formulaire(self):
        """Les indices se lisent en ordre numérique, pas alphabétique :
        sans ça la ligne 10 passerait avant la ligne 2."""
        facture = _facture(_patient('Ordre'))
        donnees = {}
        for i in (0, 2, 10):
            donnees[f'ligne_libelle_{i}'] = f'Acte {i}'
            donnees[f'ligne_qte_{i}'] = '1'
            donnees[f'ligne_prix_{i}'] = '100'
            donnees[f'ligne_remise_{i}'] = '0'
        _save_lignes(facture, donnees)
        self.assertEqual(
            [l.libelle for l in facture.lignes.order_by('pk')],
            ['Acte 0', 'Acte 2', 'Acte 10'])


class TestLesMontantsNAffichentPasDeDecimalesInutiles(TestCase):
    """4 000, pas 4 000,0000.

    Multiplier deux Decimal additionne leurs décimales : `quantite` (2) ×
    `prix_unitaire` (2) donne un montant à 4 décimales, et la remise le pousse
    à 6. Le montant était arrondi au moment d'être enregistré dans la facture,
    mais la propriété `montant_ligne`, elle, sortait brute — et c'est elle que
    les écrans affichent.
    """

    def test_le_montant_d_une_ligne_s_arrete_au_centime(self):
        from decimal import Decimal

        from .models import LigneFacture

        ligne = LigneFacture(quantite=Decimal('1.00'),
                             prix_unitaire=Decimal('4000.00'),
                             remise=Decimal('0.00'))
        self.assertEqual(str(ligne.montant_ligne), '4000.00')

    def test_une_remise_ne_fait_pas_trainer_six_decimales(self):
        from decimal import Decimal

        from .models import LigneFacture

        ligne = LigneFacture(quantite=Decimal('3.00'),
                             prix_unitaire=Decimal('1500.00'),
                             remise=Decimal('12.50'))
        self.assertEqual(str(ligne.montant_ligne), '3937.50')

    def test_l_arrondi_ne_perd_pas_les_centimes(self):
        from decimal import Decimal

        from .models import LigneFacture

        ligne = LigneFacture(quantite=Decimal('3.00'),
                             prix_unitaire=Decimal('333.33'),
                             remise=Decimal('0.00'))
        self.assertEqual(str(ligne.montant_ligne), '999.99')


class TestLesCasesDeMontantSontLisibles(TestCase):
    """Un champ numérique HTML ne lit que le point décimal.

    Rendu sous une langue française, un Decimal devient « 4 000,00 » et le
    navigateur, ne sachant pas le lire, **affiche la case vide** : la quantité
    d'une facture qu'on rouvrait pour la corriger disparaissait de l'écran, et
    il suffisait d'enregistrer pour la perdre. `unlocalize` réglait le point
    mais laissait « 4000.00 » et « 15000.0 » dans la case Prix.
    """

    def test_un_montant_rond_n_a_pas_de_decimales(self):
        from decimal import Decimal

        from core.templatetags.core_tags import valeur_champ

        self.assertEqual(valeur_champ(Decimal('4000.0000')), '4000')
        self.assertEqual(valeur_champ(Decimal('4000.00')), '4000')
        self.assertEqual(valeur_champ(1.0), '1')

    def test_les_centimes_reels_restent(self):
        from decimal import Decimal

        from core.templatetags.core_tags import valeur_champ

        self.assertEqual(valeur_champ(Decimal('4000.25')), '4000.25')

    def test_le_separateur_est_le_point(self):
        """Une virgule vide la case du navigateur."""
        from decimal import Decimal

        from core.templatetags.core_tags import valeur_champ

        self.assertNotIn(',', valeur_champ(Decimal('4000.25')))

    def test_une_case_vide_le_reste(self):
        from core.templatetags.core_tags import valeur_champ

        self.assertEqual(valeur_champ(None), '')
        self.assertEqual(valeur_champ(''), '')

    def test_le_texte_affiche_suit_la_langue(self):
        """Pour du texte, on garde la virgule française."""
        from decimal import Decimal

        from django.utils import translation

        from core.templatetags.core_tags import nombre

        with translation.override('fr-fr'):
            self.assertEqual(nombre(Decimal('4000.0000')), '4000')
            self.assertEqual(nombre(Decimal('4000.25')), '4000,25')
