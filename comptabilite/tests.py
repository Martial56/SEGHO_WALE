from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from facturation.models import Caisse, Facture, Paiement
from patients.models import Patient

from . import caisse as regles
from .models import JourneeCaisse, SessionCaissiere


def _perm(user, app, codename):
    user.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codename))
    # Le cache des permissions est posé au premier `has_perm` : on repart d'un
    # objet neuf pour qu'il voie la permission ajoutée.
    return User.objects.get(pk=user.pk)


def _caissiere(nom):
    user = User.objects.create_user(nom, password='x', first_name=nom.capitalize())
    user = _perm(user, 'facturation', 'can_encaisser')
    return _perm(user, 'facturation', 'add_facture')


def _superviseur(nom='chef'):
    user = User.objects.create_user(nom, password='x')
    return _perm(user, 'comptabilite', 'superviser_caisse')


def _patient():
    return Patient.objects.create(nom='Kouassi', prenoms='Ama', date_naissance='1990-06-01',
                                  sexe='F', telephone='0700000000')


def _facture(montant=Decimal('5000'), patient=None):
    return Facture.objects.create(patient=patient or _patient(), type_facture='consultation',
                                  statut='emise', montant_total=montant)


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def _annulable(user):
    return _perm(user, 'facturation', 'can_annuler_facture')


def _payer(user, facture, montant, mode='especes', operateur='Wave', transaction=None):
    donnees = {'pay_montant': str(montant), 'pay_mode': mode}
    if mode == 'mobile_money':
        from .models import CompteTresorerie
        donnees['pay_operateur'] = CompteTresorerie.objects.get(libelle=operateur).pk
        donnees['pay_transaction'] = transaction or f'TX-{facture.pk}-{montant}'
    return _client(user).post(reverse('facturation:payer', args=[facture.pk]), donnees)


class TestOuverture(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        self.mariam = _caissiere('mariam')

    def test_ouvrir_cree_la_journee_et_la_session(self):
        session = regles.ouvrir_session(self.awa, self.caisse, Decimal('20000'))
        self.assertEqual(session.journee.caisse, self.caisse)
        self.assertEqual(session.journee.date_journee, timezone.localdate())
        self.assertEqual(session.fonds_initial, Decimal('20000'))
        self.assertTrue(session.numero.startswith('SES'))

    def test_deux_caissieres_partagent_la_meme_journee(self):
        s1 = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        s2 = regles.ouvrir_session(self.mariam, self.caisse, Decimal('0'))
        self.assertEqual(s1.journee_id, s2.journee_id)
        self.assertEqual(JourneeCaisse.objects.count(), 1)
        self.assertEqual(SessionCaissiere.objects.filter(statut='ouverte').count(), 2)

    def test_une_seule_session_ouverte_par_caissiere(self):
        autre = Caisse.objects.create(nom='Caisse Pharmacie', code='PHA')
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.ouvrir_session(self.awa, autre, Decimal('0'))

    def test_caisse_reservee_a_ses_caissieres(self):
        self.caisse.caissiers.add(self.awa)
        with self.assertRaises(regles.ErreurCaisse):
            regles.ouvrir_session(self.mariam, self.caisse, Decimal('0'))
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))

    def test_caisse_sans_caissiere_designee_ouverte_a_tous(self):
        self.assertIn(self.caisse, regles.caisses_autorisees(self.mariam))

    def test_sans_droit_d_encaisser_pas_de_session(self):
        accueil = User.objects.create_user('accueil', password='x')
        with self.assertRaises(regles.ErreurCaisse):
            regles.ouvrir_session(accueil, self.caisse, Decimal('0'))

    def test_journee_cloturee_refuse_une_nouvelle_session(self):
        session = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        regles.cloturer_session(session, self.awa, {}, Decimal('0'))
        regles.cloturer_journee(session.journee, self.awa)
        with self.assertRaises(regles.ErreurCaisse):
            regles.ouvrir_session(self.mariam, self.caisse, Decimal('0'))

    def test_ecran_d_ouverture(self):
        client = _client(self.awa)
        self.assertEqual(client.get(reverse('comptabilite:ouvrir')).status_code, 200)
        reponse = client.post(reverse('comptabilite:ouvrir'),
                              {'caisse': self.caisse.pk, 'fonds_initial': '15000'})
        self.assertEqual(reponse.status_code, 302)
        self.assertEqual(regles.session_ouverte(self.awa).fonds_initial, Decimal('15000'))

    def test_la_connexion_d_une_caissiere_mene_a_l_ouverture(self):
        reponse = Client().post(reverse('login'), {'username': 'awa', 'password': 'x'})
        self.assertIn(reverse('comptabilite:ouvrir'), reponse.url.replace('%2F', '/'))


class TestEncaissement(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        self.mariam = _caissiere('mariam')

    def test_le_paiement_porte_la_session_et_la_caisse(self):
        session = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        facture = _facture()
        _payer(self.awa, facture, 5000)
        paiement = Paiement.objects.get(facture=facture)
        self.assertEqual(paiement.session, session)
        self.assertEqual(paiement.caisse, self.caisse)
        self.assertEqual(paiement.recu_par, self.awa)

    def test_sans_session_pas_d_encaissement(self):
        facture = _facture()
        _payer(self.awa, facture, 5000)
        self.assertFalse(Paiement.objects.filter(facture=facture).exists())
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'emise')

    def test_session_de_la_veille_refusee(self):
        session = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        JourneeCaisse.objects.filter(pk=session.journee_id).update(
            date_journee=timezone.localdate() - timedelta(days=1))
        facture = _facture()
        _payer(self.awa, facture, 5000)
        self.assertFalse(Paiement.objects.filter(facture=facture).exists())

    def test_deux_caissieres_sur_la_meme_caisse_sont_distinguees(self):
        s_awa = regles.ouvrir_session(self.awa, self.caisse, Decimal('10000'))
        s_mariam = regles.ouvrir_session(self.mariam, self.caisse, Decimal('5000'))
        _payer(self.awa, _facture(Decimal('3000')), 3000)
        _payer(self.awa, _facture(Decimal('2000')), 2000, mode='mobile_money')
        _payer(self.mariam, _facture(Decimal('7000')), 7000)

        r_awa = regles.resume_session(s_awa)
        self.assertEqual(r_awa['especes_encaissees'], Decimal('3000'))
        self.assertEqual(r_awa['autres_modes'], Decimal('2000'))
        self.assertEqual(r_awa['especes_attendues'], Decimal('13000'))
        r_mariam = regles.resume_session(s_mariam)
        self.assertEqual(r_mariam['especes_attendues'], Decimal('12000'))

        journee = regles.resume_journee(s_awa.journee)
        self.assertEqual(len(journee['lignes']), 2)
        self.assertEqual(journee['totaux']['especes'], Decimal('10000'))
        self.assertEqual(journee['totaux']['total_encaisse'], Decimal('12000'))

    def test_le_remboursement_sort_de_la_pochette_de_qui_rembourse(self):
        # Awa encaisse ; Mariam annule et rend l'argent : c'est la pochette de
        # Mariam qui baisse, celle d'Awa garde l'encaissement.
        s_awa = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        s_mariam = regles.ouvrir_session(self.mariam, self.caisse, Decimal('5000'))
        facture = _facture(Decimal('4000'))
        _payer(self.awa, facture, 4000)
        _client(_annulable(self.mariam)).post(
            reverse('facturation:annuler', args=[facture.pk]),
            {'motif_annulation': 'Erreur de prestation'})
        self.assertEqual(regles.resume_session(s_awa)['especes_attendues'], Decimal('4000'))
        r = regles.resume_session(s_mariam)
        self.assertEqual(r['especes_remboursees'], Decimal('4000'))
        self.assertEqual(r['especes_attendues'], Decimal('1000'))

    def test_creation_de_facture_renvoie_la_caissiere_ouvrir_sa_caisse(self):
        reponse = _client(self.awa).get(reverse('facturation:create'))
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(reponse.url.startswith(reverse('comptabilite:ouvrir')))

    def test_la_fiche_ne_propose_que_la_caisse_de_la_session(self):
        Caisse.objects.create(nom='Caisse Pharmacie', code='PHA')
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        contenu = _client(self.awa).get(
            reverse('facturation:detail', args=[_facture().pk])).content.decode()
        self.assertIn('>CAISSE ACCUEIL</option>', contenu)
        self.assertNotIn('>CAISSE PHARMACIE</option>', contenu)


class TestCloture(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        self.mariam = _caissiere('mariam')
        self.chef = _superviseur()
        self.session = regles.ouvrir_session(self.awa, self.caisse, Decimal('1000'))
        _payer(self.awa, _facture(Decimal('2500')), 2500)

    def test_billetage(self):
        billetage, total = regles.lire_billetage({'n_b2000': '1', 'n_p500': '3', 'n_b1000': ''})
        self.assertEqual(billetage, {'b2000': 1, 'p500': 3})
        self.assertEqual(total, Decimal('3500'))

    def test_billetage_negatif_refuse(self):
        with self.assertRaises(regles.ErreurCaisse):
            regles.lire_billetage({'n_b2000': '-1'})

    def test_cloture_juste(self):
        regles.cloturer_session(self.session, self.awa, {'b2000': 1, 'p500': 3}, Decimal('3500'))
        self.session.refresh_from_db()
        self.assertEqual(self.session.statut, 'cloturee')
        self.assertEqual(self.session.montant_theorique, Decimal('3500'))
        self.assertEqual(self.session.ecart, Decimal('0'))

    def test_ecart_sans_justification_refuse(self):
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_session(self.session, self.awa, {}, Decimal('3000'))
        regles.cloturer_session(self.session, self.awa, {}, Decimal('3000'),
                                justification='Erreur de monnaie')
        self.assertEqual(self.session.ecart, Decimal('-500'))

    def test_ecran_de_cloture(self):
        client = _client(self.awa)
        self.assertEqual(client.get(reverse('comptabilite:cloturer', args=[self.session.pk])).status_code, 200)
        client.post(reverse('comptabilite:cloturer', args=[self.session.pk]),
                    {'n_b2000': '1', 'n_b1000': '1', 'n_p500': '1'})
        self.session.refresh_from_db()
        self.assertEqual(self.session.statut, 'cloturee')
        self.assertEqual(self.session.billetage, {'b2000': 1, 'b1000': 1, 'p500': 1})
        self.assertEqual(client.get(reverse('comptabilite:imprimer', args=[self.session.pk])).status_code, 200)

    def test_une_collegue_ne_cloture_pas_la_session_d_une_autre(self):
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_session(self.session, self.mariam, {}, Decimal('3500'))

    def test_une_collegue_ne_voit_pas_la_session_d_une_autre(self):
        reponse = _client(self.mariam).get(reverse('comptabilite:session', args=[self.session.pk]))
        self.assertEqual(reponse.status_code, 403)

    def test_cloture_d_office_exige_un_motif(self):
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_session(self.session, self.chef, {}, Decimal('3500'))
        regles.cloturer_session(self.session, self.chef, {}, Decimal('3500'),
                                motif_office='Caissière malade, comptage devant témoin')
        self.assertTrue(self.session.cloture_d_office)

    def test_validation(self):
        regles.cloturer_session(self.session, self.awa, {}, Decimal('3500'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.valider_session(self.session, self.awa)
        regles.valider_session(self.session, self.chef, 'Pochette reçue')
        self.assertEqual(self.session.statut, 'validee')

    def test_paiement_refuse_apres_cloture(self):
        regles.cloturer_session(self.session, self.awa, {}, Decimal('3500'))
        facture = _facture()
        _payer(self.awa, facture, 5000)
        self.assertFalse(Paiement.objects.filter(facture=facture).exists())


class TestJournee(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        self.mariam = _caissiere('mariam')
        self.koffi = _caissiere('koffi')
        self.chef = _superviseur()
        self.s_awa = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        self.s_mariam = regles.ouvrir_session(self.mariam, self.caisse, Decimal('0'))
        self.journee = self.s_awa.journee

    def test_refusee_tant_qu_une_session_est_ouverte(self):
        regles.cloturer_session(self.s_awa, self.awa, {}, Decimal('0'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_journee(self.journee, self.awa)

    def test_la_caissiere_presente_peut_cloturer(self):
        regles.cloturer_session(self.s_awa, self.awa, {}, Decimal('0'))
        regles.cloturer_session(self.s_mariam, self.mariam, {}, Decimal('0'))
        regles.cloturer_journee(self.journee, self.mariam)
        self.assertEqual(self.journee.statut, 'cloturee')

    def test_une_caissiere_absente_ne_peut_pas_cloturer(self):
        regles.cloturer_session(self.s_awa, self.awa, {}, Decimal('0'))
        regles.cloturer_session(self.s_mariam, self.mariam, {}, Decimal('0'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_journee(self.journee, self.koffi)

    def test_le_superviseur_cloture_et_rouvre(self):
        regles.cloturer_session(self.s_awa, self.awa, {}, Decimal('0'))
        regles.cloturer_session(self.s_mariam, self.mariam, {}, Decimal('0'))
        regles.cloturer_journee(self.journee, self.chef)
        with self.assertRaises(regles.ErreurCaisse):
            regles.rouvrir_journee(self.journee, self.awa)
        regles.rouvrir_journee(self.journee, self.chef)
        self.assertEqual(self.journee.statut, 'ouverte')

    def test_ecrans(self):
        client = _client(self.chef)
        self.assertEqual(client.get(reverse('comptabilite:journees')).status_code, 200)
        contenu = client.get(reverse('comptabilite:journee', args=[self.journee.pk])).content.decode()
        self.assertIn('Awa', contenu)
        self.assertIn('Mariam', contenu)
        self.assertEqual(_client(User.objects.create_user('medecin', password='x'))
                         .get(reverse('comptabilite:journees')).status_code, 403)


# ─── Lot 2 ─────────────────────────────────────────────────────────────────────

from .models import Avoir, MotifGratuite, MotifSortie, SortieCaisse  # noqa: E402


class TestSorties(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC', seuil_sortie=5000)
        self.awa = _caissiere('awa')
        self.chef = _superviseur()
        self.motif = MotifSortie.objects.get(libelle='Transport / course')
        self.session = regles.ouvrir_session(self.awa, self.caisse, Decimal('2000'))
        _payer(self.awa, _facture(Decimal('20000')), 20000)   # pochette : 22 000

    def test_sous_le_seuil_payee_tout_de_suite(self):
        sortie = regles.creer_sortie(self.session, self.awa, self.motif, 'Course taxi', Decimal('3000'))
        self.assertEqual(sortie.statut, 'payee')
        self.assertTrue(sortie.numero.startswith('SOR'))
        self.assertEqual(regles.resume_session(self.session)['especes_attendues'], Decimal('19000'))

    def test_au_dessus_du_seuil_attend_le_superviseur(self):
        sortie = regles.creer_sortie(self.session, self.awa, self.motif, 'Réparation', Decimal('8000'))
        self.assertEqual(sortie.statut, 'en_attente')
        self.assertEqual(regles.resume_session(self.session)['especes_attendues'], Decimal('22000'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.decider_sortie(sortie, self.awa, True)            # pas superviseur
        regles.decider_sortie(sortie, self.chef, True)
        self.assertEqual(sortie.statut, 'payee')
        self.assertEqual(regles.resume_session(self.session)['especes_attendues'], Decimal('14000'))

    def test_refus_exige_une_raison(self):
        sortie = regles.creer_sortie(self.session, self.awa, self.motif, 'Achat', Decimal('8000'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.decider_sortie(sortie, self.chef, False)
        regles.decider_sortie(sortie, self.chef, False, 'Passer par le bon de commande')
        self.assertEqual(sortie.statut, 'refusee')

    def test_pas_plus_que_la_pochette(self):
        with self.assertRaises(regles.ErreurCaisse):
            regles.creer_sortie(self.session, self.awa, self.motif, 'Trop', Decimal('30000'))

    def test_cloture_bloquee_par_une_demande_en_attente(self):
        sortie = regles.creer_sortie(self.session, self.awa, self.motif, 'Achat', Decimal('8000'))
        with self.assertRaises(regles.ErreurCaisse):
            regles.cloturer_session(self.session, self.awa, {}, Decimal('22000'))
        regles.annuler_demande_sortie(sortie, self.awa)
        regles.cloturer_session(self.session, self.awa, {}, Decimal('22000'))
        self.assertEqual(self.session.ecart, Decimal('0'))

    def test_ecran_de_sortie(self):
        client = _client(self.awa)
        self.assertEqual(client.get(reverse('comptabilite:sortie_creer', args=[self.session.pk])).status_code, 200)
        client.post(reverse('comptabilite:sortie_creer', args=[self.session.pk]),
                    {'motif': self.motif.pk, 'libelle': 'Course', 'montant': '1500'})
        self.assertEqual(SortieCaisse.objects.get().montant, Decimal('1500'))

    def test_le_superviseur_decide_depuis_les_journees(self):
        sortie = regles.creer_sortie(self.session, self.awa, self.motif, 'Achat', Decimal('8000'))
        client = _client(self.chef)
        self.assertIn(sortie.numero, client.get(reverse('comptabilite:journees')).content.decode())
        client.post(reverse('comptabilite:sortie_decider', args=[sortie.pk]), {'decision': 'accepter'})
        sortie.refresh_from_db()
        self.assertEqual(sortie.statut, 'payee')


class TestAvoirs(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _annulable(_caissiere('awa'))

    def _annuler(self, facture, **extra):
        donnees = {'motif_annulation': 'Erreur'}
        donnees.update(extra)
        return _client(self.awa).post(reverse('facturation:annuler', args=[facture.pk]), donnees)

    def test_facture_payee_annulee_donne_un_avoir_rembourse(self):
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        facture = _facture(Decimal('6000'))
        _payer(self.awa, facture, 6000)
        self._annuler(facture)
        avoir = Avoir.objects.get(facture=facture)
        self.assertTrue(avoir.numero.startswith('AV'))
        self.assertEqual(avoir.montant, Decimal('6000'))
        self.assertEqual(avoir.montant_rembourse, Decimal('6000'))
        self.assertEqual(avoir.mode_remboursement, 'especes')
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'annulee')

    def test_rembourser_en_especes_exige_une_caisse_ouverte(self):
        facture = _facture(Decimal('6000'))
        Facture.objects.filter(pk=facture.pk).update(montant_paye=6000, statut='payee')
        self._annuler(facture)
        facture.refresh_from_db()
        self.assertEqual(facture.statut, 'payee')
        self.assertFalse(Avoir.objects.exists())

    def test_rembourser_autrement_sans_caisse(self):
        facture = _facture(Decimal('6000'))
        Facture.objects.filter(pk=facture.pk).update(montant_paye=6000, statut='payee')
        self._annuler(facture, mode_remboursement='mobile_money', reference_remboursement='MM123')
        avoir = Avoir.objects.get(facture=facture)
        self.assertEqual(avoir.mode_remboursement, 'mobile_money')
        self.assertIsNone(avoir.session)

    def test_facture_impayee_avoir_sans_remboursement(self):
        facture = _facture(Decimal('6000'))
        self._annuler(facture)
        avoir = Avoir.objects.get(facture=facture)
        self.assertEqual(avoir.montant_rembourse, Decimal('0'))
        self.assertEqual(avoir.mode_remboursement, '')

    def test_un_brouillon_s_annule_sans_avoir(self):
        facture = _facture(Decimal('6000'))
        Facture.objects.filter(pk=facture.pk).update(statut='brouillon')
        self._annuler(facture)
        self.assertFalse(Avoir.objects.exists())

    def test_l_avoir_parait_sur_la_fiche(self):
        facture = _facture(Decimal('6000'))
        self._annuler(facture)
        avoir = Avoir.objects.get(facture=facture)
        self.assertIn(avoir.numero, _client(self.awa).get(
            reverse('facturation:detail', args=[facture.pk])).content.decode())


class TestGratuites(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        self.patient = _patient()
        self.indigent = MotifGratuite.objects.get(libelle='Patient indigent')
        self.personnel = MotifGratuite.objects.get(libelle='Personnel du centre')
        self.personnel.remise_max = 50
        self.personnel.save()

    def _creer(self, remise, motif=None):
        avant = Facture.objects.count()
        donnees = {'type_facture': 'consultation', 'montant_assurance': '0',
                   'ticket_moderateur': '0', 'notes': '',
                   'ligne_libelle_0': 'Consultation', 'ligne_qte_0': '1',
                   'ligne_prix_0': '10000', 'ligne_remise_0': str(remise)}
        if motif:
            donnees['motif_remise'] = str(motif.pk)
        _client(self.awa).post(reverse('facturation:create') + f'?patient={self.patient.pk}', donnees)
        if Facture.objects.count() == avant:
            return None
        return Facture.objects.order_by('-pk').first()

    def test_remise_sans_motif_refusee(self):
        self.assertIsNone(self._creer(20))

    def test_remise_avec_motif_acceptee(self):
        facture = self._creer(100, self.indigent)
        self.assertEqual(facture.motif_remise, self.indigent)
        self.assertEqual(facture.montant_total, Decimal('0'))

    def test_plafond_du_motif(self):
        self.assertIsNone(self._creer(80, self.personnel))
        self.awa = _perm(self.awa, 'comptabilite', 'accorder_remise_hors_plafond')
        self.assertIsNotNone(self._creer(80, self.personnel))

    def test_sans_remise_le_motif_est_efface(self):
        facture = self._creer(0, self.indigent)
        self.assertIsNone(facture.motif_remise)

    def test_etat_des_gratuites(self):
        from .gratuites import etat_gratuites
        facture = self._creer(50, self.indigent)
        Facture.objects.filter(pk=facture.pk).update(statut='emise')
        jour = timezone.localdate()
        etat = etat_gratuites(jour.replace(day=1), jour)
        self.assertEqual(etat['total'], Decimal('5000'))
        self.assertEqual(etat['par_motif'][0]['motif'], 'Patient indigent')
        reponse = _client(_perm(self.awa, 'facturation', 'view_facture')).get(reverse('comptabilite:gratuites'))
        self.assertContains(reponse, 'Patient indigent')

    def test_configuration_des_motifs(self):
        admin = User.objects.create_superuser('admin_cfg', password='x')
        client = _client(admin)
        self.assertEqual(client.get(reverse('comptabilite:motifs', args=['gratuite'])).status_code, 200)
        client.post(reverse('comptabilite:motifs', args=['gratuite']),
                    {'libelle': 'Campagne de vaccination', 'remise_max': '100', 'actif': 'on'})
        self.assertTrue(MotifGratuite.objects.filter(libelle='Campagne de vaccination').exists())
        self.assertEqual(_client(self.awa).get(
            reverse('comptabilite:motifs', args=['sortie'])).status_code, 403)



# ─── Lot 3 : plan comptable et écritures automatiques ─────────────────────────

from datetime import date as _date  # noqa: E402

from facturation.models import LigneFacture  # noqa: E402

from . import ecritures as moteur  # noqa: E402
from .models import Compte, Ecriture, Exercice, Journal  # noqa: E402


def _lignes(ecriture):
    """{numéro de compte: (débit, crédit)} d'une écriture."""
    res = {}
    for l in ecriture.lignes.select_related('compte'):
        d, c = res.get(l.compte.numero, (Decimal('0'), Decimal('0')))
        res[l.compte.numero] = (d + l.debit, c + l.credit)
    return res


class TestPlanComptable(TestCase):

    def test_plan_seme(self):
        for numero in ('4111', '4112', '571', '552', '7061', '701', '709', '658', '758'):
            self.assertTrue(Compte.objects.filter(numero=numero).exists(), numero)
        self.assertTrue(Compte.objects.filter(numero='101', a_valider=True).exists())
        self.assertEqual(moteur.compte('nature:pharmacie').numero, '701')

    def test_ecrans_reserves(self):
        caissiere = _caissiere('awa')
        self.assertEqual(_client(caissiere).get(reverse('comptabilite:ecritures')).status_code, 403)
        admin = User.objects.create_superuser('admin3', password='x')
        client = _client(admin)
        for nom in ('ecritures', 'od_saisie', 'plan_comptable', 'correspondances'):
            self.assertEqual(client.get(reverse(f'comptabilite:{nom}')).status_code, 200, nom)

    def test_ajouter_un_compte(self):
        admin = User.objects.create_superuser('admin3b', password='x')
        _client(admin).post(reverse('comptabilite:plan_comptable'),
                            {'numero': '7066', 'intitule': 'Vaccinations', 'actif': 'on'})
        self.assertTrue(Compte.objects.filter(numero='7066').exists())


class TestEcrituresAutomatiques(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _annulable(_caissiere('awa'))
        self.session = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        self.jour = timezone.localdate()

    def _facture_avec_remise(self):
        facture = _facture(Decimal('8000'))
        LigneFacture.objects.create(facture=facture, libelle='Consultation', quantite=1,
                                    prix_unitaire=Decimal('10000'), remise=Decimal('20'))
        return facture

    def test_vente_au_prix_plein_et_remise_a_part(self):
        facture = self._facture_avec_remise()
        ecriture = moteur.ecriture_facture(facture)
        self.assertEqual(ecriture.journal.code, 'VTE')
        self.assertEqual(_lignes(ecriture), {'4111': (Decimal('8000'), 0), '709': (Decimal('2000'), 0),
                                             '7061': (0, Decimal('10000'))})

    def test_paiement_especes_dans_le_journal_de_la_caisse(self):
        facture = _facture(Decimal('5000'))
        _payer(self.awa, facture, 5000)
        ecriture = moteur.ecriture_paiement(Paiement.objects.get(facture=facture))
        self.assertEqual(ecriture.journal.code, 'CA-ACC')
        lignes = _lignes(ecriture)
        self.assertEqual(lignes['4111'], (0, Decimal('5000')))
        compte_caisse = [n for n in lignes if n.startswith('571')][0]
        self.assertNotEqual(compte_caisse, '571')          # sous-compte propre à la caisse
        self.assertEqual(lignes[compte_caisse], (Decimal('5000'), 0))

    def test_paiement_mobile_money(self):
        facture = _facture(Decimal('5000'))
        _payer(self.awa, facture, 5000, mode='mobile_money')
        ecriture = moteur.ecriture_paiement(Paiement.objects.get(facture=facture))
        self.assertEqual(ecriture.journal.code, 'MM')
        # Sur le sous-compte de l'opérateur choisi à l'encaissement.
        self.assertEqual(_lignes(ecriture)['5521'], (Decimal('5000'), 0))

    def test_avoir_et_remboursement(self):
        facture = _facture(Decimal('5000'))
        _payer(self.awa, facture, 5000)
        _client(self.awa).post(reverse('facturation:annuler', args=[facture.pk]),
                               {'motif_annulation': 'Erreur'})
        resultat = moteur.generer(self.jour, self.jour)
        self.assertEqual(resultat['erreurs'], [])
        avoir = Ecriture.objects.get(origine__startswith='avoir:')
        self.assertEqual(_lignes(avoir)['4111'], (0, Decimal('5000')))
        remboursement = Ecriture.objects.get(origine__startswith='remboursement:')
        self.assertEqual(remboursement.journal.code, 'CA-ACC')
        self.assertEqual(_lignes(remboursement)['4111'], (Decimal('5000'), 0))

    def test_sortie_et_ecart(self):
        _payer(self.awa, _facture(Decimal('20000')), 20000)
        motif = MotifSortie.objects.get(libelle='Transport / course')
        sortie = regles.creer_sortie(self.session, self.awa, motif, 'Course', Decimal('2000'))
        self.assertEqual(_lignes(moteur.ecriture_sortie(sortie))['618'], (Decimal('2000'), 0))
        regles.cloturer_session(self.session, self.awa, {}, Decimal('17500'), justification='Erreur de monnaie')
        ecart = moteur.ecriture_ecart(self.session)
        self.assertEqual(_lignes(ecart)['658'], (Decimal('500'), 0))

    def test_generation_sans_doublon_et_equilibree(self):
        _payer(self.awa, self._facture_avec_remise(), 8000)
        premiere = moteur.generer(self.jour, self.jour)
        self.assertEqual(premiere['crees'], 2)
        self.assertEqual(moteur.generer(self.jour, self.jour)['crees'], 0)
        for e in Ecriture.objects.all():
            debit, credit = e.totaux()
            self.assertEqual(debit, credit)

    def test_une_facture_brouillon_n_est_pas_une_vente(self):
        facture = _facture(Decimal('5000'))
        Facture.objects.filter(pk=facture.pk).update(statut='brouillon')
        moteur.generer(self.jour, self.jour)
        self.assertFalse(Ecriture.objects.filter(origine=f'facture:{facture.pk}').exists())

    def test_la_cloture_de_la_journee_prepare_les_ecritures(self):
        _payer(self.awa, _facture(Decimal('3000')), 3000)
        regles.cloturer_session(self.session, self.awa, {}, Decimal('3000'))
        _client(self.awa).post(reverse('comptabilite:journee_cloturer', args=[self.session.journee_id]))
        self.assertEqual(Ecriture.objects.filter(statut='brouillon').count(), 2)


class TestPassageDesEcritures(TestCase):

    def setUp(self):
        self.comptable = User.objects.create_superuser('comptable', password='x')
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        for montant in (1000, 2000, 3000):
            moteur.ecriture_facture(_facture(Decimal(montant)))

    def test_numerotation_continue_a_la_validation(self):
        self.assertTrue(all(e.numero is None for e in Ecriture.objects.all()))
        moteur.valider(list(Ecriture.objects.all()), self.comptable)
        numeros = sorted(Ecriture.objects.values_list('numero', flat=True))
        self.assertEqual(numeros, [1, 2, 3])
        self.assertTrue(Exercice.objects.filter(libelle=str(timezone.localdate().year)).exists())

    def test_validation_par_l_ecran(self):
        ids = list(Ecriture.objects.values_list('pk', flat=True))
        _client(self.comptable).post(reverse('comptabilite:ecritures'),
                                     {'action': 'valider', 'ecriture': ids})
        self.assertEqual(Ecriture.objects.filter(statut='validee').count(), 3)

    def test_une_ecriture_validee_se_contre_passe_et_ne_se_supprime_pas(self):
        ecriture = Ecriture.objects.first()
        moteur.valider([ecriture], self.comptable)
        with self.assertRaises(moteur.ErreurCompta):
            moteur.supprimer_brouillon(ecriture)
        inverse = moteur.contre_passer(ecriture, self.comptable)
        self.assertEqual(inverse.statut, 'brouillon')
        for numero, (d, c) in _lignes(ecriture).items():
            self.assertEqual(_lignes(inverse)[numero], (c, d))
        with self.assertRaises(moteur.ErreurCompta):
            moteur.contre_passer(ecriture, self.comptable)

    def test_exercice_cloture_refuse_les_ecritures(self):
        Exercice.objects.update(statut='cloture')
        with self.assertRaises(moteur.ErreurCompta):
            moteur.valider(list(Ecriture.objects.all()), self.comptable)

    def test_saisie_d_une_operation_diverse(self):
        client = _client(self.comptable)
        od = Journal.objects.get(code='OD')
        base = {'journal': od.pk, 'date': timezone.localdate().isoformat(), 'libelle': 'Salaires',
                'compte_0': '661 Rémunérations', 'debit_0': '150000', 'credit_0': '',
                'compte_1': '521', 'debit_1': '', 'credit_1': '150000'}
        client.post(reverse('comptabilite:od_saisie'), base)
        ecriture = Ecriture.objects.get(libelle='Salaires')
        self.assertEqual(_lignes(ecriture), {'661': (Decimal('150000'), 0), '521': (0, Decimal('150000'))})
        desequilibre = dict(base, libelle='Faux', credit_1='100000')
        client.post(reverse('comptabilite:od_saisie'), desequilibre)
        self.assertFalse(Ecriture.objects.filter(libelle='Faux').exists())



# ─── Lot 4 : états ─────────────────────────────────────────────────────────────

from .etats import ETATS  # noqa: E402


class TestEtats(TestCase):

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa')
        self.chef = User.objects.create_superuser('chef4', password='x')
        session = regles.ouvrir_session(self.awa, self.caisse, Decimal('1000'))
        _payer(self.awa, _facture(Decimal('3000')), 3000)
        _payer(self.awa, _facture(Decimal('2000')), 2000, mode='mobile_money')
        self.impayee = _facture(Decimal('7000'))
        regles.cloturer_session(session, self.awa, {}, Decimal('3500'), justification='Monnaie')
        jour = timezone.localdate()
        moteur.generer(jour, jour)
        moteur.valider(list(Ecriture.objects.all()), self.chef)
        self.client_chef = _client(self.chef)

    def _etat(self, code, **params):
        params.setdefault('periode', 'jour')
        reponse = self.client_chef.get(reverse('comptabilite:etat', args=[code]), params)
        self.assertEqual(reponse.status_code, 200, code)
        return reponse.context['etat']

    def _total(self, etat, tableau=0):
        return etat['tableaux'][tableau]['lignes'][-1]['cellules']

    def test_tous_les_etats_s_affichent_et_s_exportent(self):
        self.assertEqual(self.client_chef.get(reverse('comptabilite:etats')).status_code, 200)
        for code in ETATS:
            self._etat(code)
            reponse = self.client_chef.get(reverse('comptabilite:etat', args=[code]),
                                           {'periode': 'mois', 'format': 'xlsx'})
            self.assertEqual(reponse['Content-Type'],
                             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', code)

    def test_recettes(self):
        etat = self._etat('recettes')
        self.assertEqual(self._total(etat)[-1], Decimal('5000'))          # par jour et caisse
        self.assertEqual(self._total(etat, 3)[-1], Decimal('5000'))       # recettes nettes

    def test_balance_equilibree(self):
        total = self._total(self._etat('balance'))
        self.assertEqual(total[4], total[5])      # mouvements débit = crédit
        self.assertEqual(total[6], total[7])      # soldes de fin débit = crédit

    def test_grand_livre_d_un_compte(self):
        etat = self._etat('grand_livre', compte='4111')
        groupes = [l['cellules'][0] for l in etat['tableaux'][0]['lignes'] if l['type'] == 'groupe']
        self.assertEqual(len(groupes), 1)
        self.assertTrue(groupes[0].startswith('4111'))

    def test_resultat(self):
        etat = self._etat('resultat')
        # 5 000 de prestations (le paiement suit une facture de 3 000 et une de 2 000 ;
        # la facture impayée de 7 000 est aussi une vente) moins le manquant de 500.
        self.assertEqual(self._total(etat)[-1], Decimal('11500'))

    def test_creances_par_anciennete(self):
        etat = self._etat('creances')
        self.assertEqual(self._total(etat)[5], Decimal('7000'))

    def test_ecarts(self):
        self.assertEqual(self._total(self._etat('ecarts'))[5], Decimal('-500'))

    def test_brouillard(self):
        etat = self._etat('brouillard', caisse=self.caisse.pk)
        # fonds 1 000 + 3 000 encaissés − 500 de manquant = 3 500 comptés
        self.assertEqual(self._total(etat)[5], Decimal('3500'))

    def test_controle_tout_est_comptabilise(self):
        lignes = self._etat('controle')['tableaux'][0]['lignes']
        valeurs = {l['cellules'][0]: l['cellules'][1] for l in lignes}
        self.assertEqual(valeurs['Factures non comptabilisées'], 0)
        self.assertEqual(valeurs['Paiements non comptabilisés'], 0)
        self.assertEqual(valeurs['Écritures en brouillon'], 0)

    def test_droits(self):
        self.assertEqual(_client(self.awa).get(reverse('comptabilite:etats')).status_code, 403)
        lecteur = _perm(User.objects.create_user('lecteur', password='x'), 'facturation', 'view_facture')
        client = _client(lecteur)
        self.assertEqual(client.get(reverse('comptabilite:etat', args=['recettes'])).status_code, 200)
        self.assertEqual(client.get(reverse('comptabilite:etat', args=['balance'])).status_code, 403)

    def test_le_menu_etats_suit_les_groupes_et_les_droits(self):
        html = self.client_chef.get(reverse('comptabilite:etat', args=['balance'])).content.decode()
        nav = html[html.index('<nav class="o-nav">'):html.index('</nav>')]
        self.assertLess(nav.index('Caisse et recettes'), nav.index('Recettes'))
        self.assertLess(nav.index('Comptabilité générale'), nav.index('Grand livre'))
        for code in ETATS:
            self.assertIn(reverse('comptabilite:etat', args=[code]), nav)
        lecteur = _perm(User.objects.create_user('lecteur_menu', password='x'), 'facturation', 'view_facture')
        html = _client(lecteur).get(reverse('comptabilite:etat', args=['recettes'])).content.decode()
        nav = html[html.index('<nav class="o-nav">'):html.index('</nav>')]
        self.assertIn(reverse('comptabilite:etat', args=['recettes']), nav)
        self.assertNotIn(reverse('comptabilite:etat', args=['balance']), nav)



# ─── Lot 5 : financements ──────────────────────────────────────────────────────

from . import financements  # noqa: E402
from .models import Bailleur, Convention, Don, LigneBudget, LigneBudgetaire, Versement  # noqa: E402


class TestFinancements(TestCase):
    """Un projet financé de bout en bout : convention, budget, versement,
    dépense imputée depuis la caisse, don affecté, suivi, fonds dédiés."""

    def setUp(self):
        self.admin = User.objects.create_superuser('admin5', password='x')
        self.client_admin = _client(self.admin)
        self.bailleur = Bailleur.objects.create(nom='Fonds mondial', sigle='FM')
        self.jour = timezone.localdate()
        self.convention = Convention.objects.create(
            bailleur=self.bailleur, intitule='Prise en charge du paludisme', date_debut=self.jour.replace(month=1, day=1),
            date_fin=self.jour.replace(month=12, day=31), montant_accorde=Decimal('1000000'),
            compte_ressource=Compte.objects.get(numero='718'))
        LigneBudgetaire.objects.create(convention=self.convention, libelle='Transport des agents',
                                       compte=Compte.objects.get(numero='618'), montant_prevu=Decimal('100000'))

    def _verser(self, montant):
        v = Versement.objects.create(convention=self.convention, date=self.jour, montant=Decimal(montant), mode='virement')
        return moteur.ecriture_versement(v)

    def _depenser_en_caisse(self, montant):
        caisse = Caisse.objects.create(nom='Caisse Projet', code='PRJ', seuil_sortie=Decimal('1000000'))
        awa = _caissiere('awa_prj')
        session = regles.ouvrir_session(awa, caisse, Decimal(montant))
        sortie = regles.creer_sortie(session, awa, MotifSortie.objects.get(libelle='Transport / course'),
                                     'Déplacement des relais', Decimal(montant), convention=self.convention)
        return moteur.ecriture_sortie(sortie)

    def test_code_de_convention(self):
        self.assertTrue(self.convention.code.startswith('CONV'))

    def test_versement_credite_le_compte_de_la_convention(self):
        ecriture = self._verser(400000)
        self.assertEqual(ecriture.journal.code, 'BQ')
        lignes = {l.compte.numero: l for l in ecriture.lignes.all()}
        self.assertEqual(lignes['521'].debit, Decimal('400000'))
        self.assertEqual(lignes['718'].credit, Decimal('400000'))
        self.assertEqual(lignes['718'].convention, self.convention)

    def test_suivi_et_budget_prevu_realise(self):
        self._verser(400000)
        self._depenser_en_caisse(30000)
        s = financements.suivi(self.convention)
        self.assertEqual(s['recu'], Decimal('400000'))
        self.assertEqual(s['depense'], Decimal('30000'))
        self.assertEqual(s['reste_a_recevoir'], Decimal('600000'))
        self.assertEqual(s['disponible'], Decimal('370000'))
        ligne = s['lignes_budget'][0]
        self.assertEqual((ligne['prevu'], ligne['realise'], ligne['reste']),
                         (Decimal('100000'), Decimal('30000'), Decimal('70000')))
        self.assertEqual(s['hors_budget'], Decimal('0'))

    def test_don_en_nature_et_don_affecte(self):
        don = Don.objects.create(donateur_nom='Pharmacie du Lac', date=self.jour, nature='nature',
                                 montant=Decimal('50000'), description='Paracétamol, 200 boîtes')
        lignes = {l.compte.numero: l for l in moteur.ecriture_don(don).lignes.all()}
        self.assertEqual(lignes['311'].debit, Decimal('50000'))
        self.assertEqual(lignes['7581'].credit, Decimal('50000'))
        affecte = Don.objects.create(donateur=self.bailleur, date=self.jour, nature='especes',
                                     montant=Decimal('20000'), convention=self.convention)
        lignes = {l.compte.numero: l for l in moteur.ecriture_don(affecte).lignes.all()}
        self.assertEqual(lignes['718'].convention, self.convention)
        self.assertEqual(financements.suivi(self.convention)['dons'], Decimal('20000'))

    def test_fonds_dedies(self):
        self._verser(400000)
        self._depenser_en_caisse(30000)
        exercice = Exercice.objects.get(libelle=str(self.jour.year))
        calcul = financements.calcul_fonds_dedies(exercice)
        self.assertEqual(calcul[0]['fonds_dedies'], Decimal('370000'))
        constitution, reprise = financements.ecritures_fonds_dedies(exercice, self.admin)
        lignes = {l.compte.numero: l for l in constitution.lignes.all()}
        self.assertEqual(lignes['689'].debit, Decimal('370000'))
        self.assertEqual(lignes['195'].credit, Decimal('370000'))
        self.assertEqual(reprise.date, exercice.date_fin + timedelta(days=1))
        # La constitution ne compte pas comme une dépense du projet.
        self.assertEqual(financements.suivi(self.convention)['depense'], Decimal('30000'))
        self.assertEqual(financements.ecritures_fonds_dedies(exercice, self.admin), (None, None))

    def test_budget_realise(self):
        self._depenser_en_caisse(30000)
        exercice = Exercice.objects.get(libelle=str(self.jour.year))
        LigneBudget.objects.create(exercice=exercice, compte=Compte.objects.get(numero='618'), montant=Decimal('120000'))
        ligne = financements.budget_realise(exercice, self.jour)[0]
        self.assertEqual((ligne['prevu'], ligne['realise']), (Decimal('120000'), Decimal('30000')))

    def test_ecrans(self):
        self._verser(400000)
        don = Don.objects.create(donateur_nom='Anonyme', date=self.jour, montant=Decimal('5000'))
        for url in [reverse('comptabilite:bailleurs'), reverse('comptabilite:conventions'),
                    reverse('comptabilite:convention_nouvelle'),
                    reverse('comptabilite:convention', args=[self.convention.pk]),
                    reverse('comptabilite:convention_modifier', args=[self.convention.pk]),
                    reverse('comptabilite:dons'), reverse('comptabilite:don_nouveau'),
                    reverse('comptabilite:don_recu', args=[don.pk]), reverse('comptabilite:budget'),
                    reverse('comptabilite:fonds_dedies')]:
            self.assertEqual(self.client_admin.get(url).status_code, 200, url)
        for code in ('conventions', 'rapport_convention', 'budget', 'dons'):
            reponse = self.client_admin.get(reverse('comptabilite:etat', args=[code]),
                                            {'periode': 'annee', 'convention': self.convention.pk})
            self.assertEqual(reponse.status_code, 200, code)

    def test_creer_une_convention_avec_son_budget(self):
        self.client_admin.post(reverse('comptabilite:convention_nouvelle'), {
            'bailleur': self.bailleur.pk, 'intitule': 'Santé maternelle', 'date_debut': '2026-01-01',
            'date_fin': '2027-12-31', 'montant_accorde': '500000', 'statut': 'active',
            'compte_ressource': Compte.objects.get(numero='718').pk,
            'budget-TOTAL_FORMS': '1', 'budget-INITIAL_FORMS': '0',
            'budget-0-libelle': 'Médicaments', 'budget-0-compte': Compte.objects.get(numero='601').pk,
            'budget-0-montant_prevu': '200000'})
        convention = Convention.objects.get(intitule='Santé maternelle')
        self.assertEqual(convention.lignes_budget.get().montant_prevu, Decimal('200000'))

    def test_enregistrer_un_versement_depuis_la_fiche(self):
        self.client_admin.post(reverse('comptabilite:convention', args=[self.convention.pk]),
                               {'date': self.jour.isoformat(), 'montant': '250000', 'mode': 'virement'})
        self.assertEqual(self.convention.versements.get().montant, Decimal('250000'))
        self.assertTrue(Ecriture.objects.filter(origine__startswith='versement:').exists())

    def test_operation_diverse_imputee(self):
        od = Journal.objects.get(code='OD')
        self.client_admin.post(reverse('comptabilite:od_saisie'), {
            'journal': od.pk, 'date': self.jour.isoformat(), 'libelle': 'Prime des relais',
            'compte_0': '661', 'debit_0': '45000', 'convention_0': str(self.convention.pk),
            'compte_1': '521', 'credit_1': '45000'})
        self.assertEqual(financements.suivi(self.convention)['depense'], Decimal('45000'))

    def test_le_menu_financements(self):
        html = self.client_admin.get(reverse('comptabilite:conventions')).content.decode()
        nav = html[html.index('<nav class="o-nav">'):html.index('</nav>')]
        for nom in ('conventions', 'bailleurs', 'dons', 'budget', 'fonds_dedies'):
            self.assertIn(reverse(f'comptabilite:{nom}'), nav)
        self.assertIn('Financements et dons', nav)
        caissiere = _caissiere('sans_fin')
        html = _client(caissiere).get(reverse('facturation:list')).content.decode()
        self.assertNotIn(reverse('comptabilite:conventions'), html)



# ─── Lot 6 : tiers payants ─────────────────────────────────────────────────────

from patients.models import Assurance  # noqa: E402

from . import assurances as tiers  # noqa: E402
from .models import BordereauAssurance, LigneEcriture, ReglementAssurance  # noqa: E402


class TestAssurances(TestCase):
    """Un patient assuré à 80 % : il paie sa part, l'assureur le reste."""

    def setUp(self):
        self.mugef = Assurance.objects.create(nom='MUGEF-CI', code='MUGEF', taux_prise_en_charge=Decimal('80'))
        self.patient = _patient()
        self.patient.assurance = self.mugef
        self.patient.save()
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa6')
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        self.comptable = User.objects.create_superuser('comptable6', password='x')
        self.client_c = _client(self.comptable)

    def _facture(self, total=10000, assurance=8000):
        f = Facture.objects.create(patient=self.patient, type_facture='consultation', statut='emise',
                                   montant_total=Decimal(total), montant_assurance=Decimal(assurance))
        return Facture.objects.get(pk=f.pk)

    def test_la_facture_reprend_l_assureur_du_patient(self):
        f = self._facture()
        self.assertEqual(f.assurance, self.mugef)
        self.assertEqual((f.part_assurance, f.part_patient), (Decimal('8000'), Decimal('2000')))

    def test_le_patient_regle_sa_part_et_repart(self):
        f = self._facture()
        self.assertFalse(f.reglee_par_le_patient)
        _payer(self.awa, f, 2000)
        f = Facture.objects.get(pk=f.pk)
        self.assertEqual(f.statut, 'emise')                 # l'assureur doit encore
        self.assertTrue(f.reglee_par_le_patient)
        self.assertEqual((f.reste_patient, f.reste_assurance), (Decimal('0'), Decimal('8000')))

    def test_la_fiche_propose_la_part_patient(self):
        f = self._facture()
        html = _client(self.awa).get(reverse('facturation:detail', args=[f.pk])).content.decode()
        self.assertIn('value="2000"', html)

    def test_bordereau_puis_reglement(self):
        f1, f2 = self._facture(), self._facture(5000, 4000)
        for f in (f1, f2):
            _payer(self.awa, f, f.part_patient)
        jour = timezone.localdate()
        bordereau = tiers.preparer_bordereau(self.mugef, jour.replace(day=1), jour, self.comptable)
        self.assertTrue(bordereau.numero.startswith('BOR'))
        self.assertEqual(tiers.contenu_bordereau(bordereau)['total'], Decimal('12000'))
        with self.assertRaises(tiers.ErreurAssurance):        # déjà sur un bordereau
            tiers.preparer_bordereau(self.mugef, jour.replace(day=1), jour, self.comptable)
        tiers.marquer_envoye(bordereau)

        reglement, affectations = tiers.enregistrer_reglement(self.mugef, Decimal('8000'), jour, 'virement',
                                                              self.comptable, 'VIR-1', bordereau)
        self.assertEqual(len(affectations), 1)
        bordereau.refresh_from_db()
        self.assertEqual(bordereau.statut, 'regle_partiel')
        self.assertEqual(Facture.objects.get(pk=f1.pk).statut, 'payee')

        tiers.enregistrer_reglement(self.mugef, Decimal('4000'), jour, 'virement', self.comptable, 'VIR-2', bordereau)
        bordereau.refresh_from_db()
        self.assertEqual(bordereau.statut, 'regle')
        self.assertEqual(tiers.creances(self.mugef), [])

    def test_un_reglement_trop_eleve_est_refuse(self):
        self._facture()
        with self.assertRaises(tiers.ErreurAssurance):
            tiers.enregistrer_reglement(self.mugef, Decimal('9000'), timezone.localdate(), 'virement', self.comptable)
        self.assertFalse(ReglementAssurance.objects.exists())

    def test_ecritures_du_tiers_payant(self):
        f = self._facture()
        _payer(self.awa, f, 2000)
        jour = timezone.localdate()
        tiers.enregistrer_reglement(self.mugef, Decimal('8000'), jour, 'virement', self.comptable)
        resultat = moteur.generer(jour, jour)
        self.assertEqual(resultat['erreurs'], [])
        vente = Ecriture.objects.get(origine=f'facture:{f.pk}')
        lignes = {l.compte.numero: l for l in vente.lignes.all()}
        self.assertEqual(lignes['4111'].debit, Decimal('2000'))
        self.assertEqual(lignes['4112'].debit, Decimal('8000'))
        self.assertEqual(lignes['4112'].tiers, 'MUGEF-CI')
        reglement = Ecriture.objects.get(origine__startswith='reglement:')
        lignes = {l.compte.numero: l for l in reglement.lignes.all()}
        self.assertEqual((lignes['521'].debit, lignes['4112'].credit), (Decimal('8000'), Decimal('8000')))
        # Le paiement « Assurance » issu du règlement n'est pas compté deux fois.
        paiement_assurance = Paiement.objects.get(reglement_assurance__isnull=False)
        self.assertFalse(Ecriture.objects.filter(origine=f'paiement:{paiement_assurance.pk}').exists())
        # Plus rien dû : les comptes 4111 et 4112 de la facture sont soldés.
        from django.db.models import Sum
        for numero in ('4111', '4112'):
            t = LigneEcriture.objects.filter(compte__numero=numero).aggregate(d=Sum('debit'), c=Sum('credit'))
            self.assertEqual(t['d'], t['c'], numero)

    def test_balance_agee(self):
        self._facture()
        lignes = tiers.balance_agee(timezone.localdate())
        self.assertEqual(lignes[0]['tranches'][0], Decimal('8000'))

    def test_ecrans_et_etats(self):
        f = self._facture()
        jour = timezone.localdate()
        bordereau = tiers.preparer_bordereau(self.mugef, jour.replace(day=1), jour, self.comptable)
        for url in [reverse('comptabilite:assurances'), reverse('comptabilite:creances_assureur', args=[self.mugef.pk]),
                    reverse('comptabilite:bordereaux'), reverse('comptabilite:bordereau', args=[bordereau.pk]),
                    reverse('comptabilite:bordereau_imprimer', args=[bordereau.pk]), reverse('comptabilite:reglements'),
                    reverse('comptabilite:reglement_nouveau') + f'?bordereau={bordereau.pk}']:
            self.assertEqual(self.client_c.get(url).status_code, 200, url)
        for code in ('creances_assurances', 'reglements_assurances'):
            self.assertEqual(self.client_c.get(reverse('comptabilite:etat', args=[code])).status_code, 200, code)
        self.client_c.post(reverse('comptabilite:reglement_nouveau'), {
            'assurance': self.mugef.pk, 'bordereau': bordereau.pk, 'date': jour.isoformat(),
            'montant': '8000', 'mode': 'cheque', 'reference': 'CHQ-77'})
        f = Facture.objects.get(pk=f.pk)
        # L'assureur a réglé sa part ; le patient n'a pas encore payé la sienne.
        self.assertEqual((f.reste_assurance, f.reste_patient, f.statut), (Decimal('0'), Decimal('2000'), 'emise'))
        html = self.client_c.get(reverse('comptabilite:reglements')).content.decode()
        self.assertIn('CHQ-77', html)


class TestPermissionsEnFrancais(TestCase):
    """Toutes les permissions du module Comptabilité se lisent en français
    dans l'écran d'attribution des droits."""

    def test_aucune_permission_en_anglais(self):
        anglaises = list(Permission.objects.filter(
            content_type__app_label__in=['comptabilite', 'facturation'], name__startswith='Can ')
            .values_list('codename', flat=True))
        self.assertEqual(anglaises, [])

    def test_quelques_libelles(self):
        noms = dict(Permission.objects.filter(content_type__app_label='comptabilite')
                    .values_list('codename', 'name'))
        self.assertEqual(noms['view_ecriture'], 'Peut consulter : écriture comptable')
        self.assertEqual(noms['add_reglementassurance'], "Peut créer : règlement d'assurance")
        self.assertTrue(noms['superviser_caisse'].startswith('Peut superviser les caisses'))
        self.assertTrue(noms['passer_ecritures'].startswith('Peut valider'))



# ─── Lot 7 : trésorerie, rapprochements, refus des assureurs ───────────────────

from . import tresorerie as treso  # noqa: E402
from .models import CompteTresorerie, LigneReleve, RejetAssurance, RemiseBanque  # noqa: E402


class TestTresorerie(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser('admin7', password='x')
        self.client_admin = _client(self.admin)
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa7')
        regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))
        _payer(self.awa, _facture(Decimal('40000')), 40000)
        self.jour = timezone.localdate()
        self.banque = CompteTresorerie.objects.get(libelle='Banque')

    def test_comptes_de_tresorerie_de_depart(self):
        self.assertEqual(self.banque.compte.numero, '521')
        operateurs = {c.libelle: c.compte.numero for c in CompteTresorerie.objects.filter(type='mobile_money', actif=True)}
        self.assertEqual(operateurs, {'Wave': '5521', 'Orange Money': '5522', 'MoMo': '5523'})

    def test_remise_en_banque(self):
        remise = treso.creer_remise(self.caisse, self.banque, Decimal('30000'), self.jour, self.admin, 'BV-1')
        self.assertTrue(remise.numero.startswith('REM'))
        caisse = moteur.compte_de_caisse(self.caisse)
        self.assertEqual(treso.solde_comptable(caisse), Decimal('10000'))
        self.assertEqual(treso.solde_comptable(self.banque.compte), Decimal('30000'))
        self.assertEqual(treso.solde_comptable(moteur.compte('virement_interne')), Decimal('0'))

    def test_pas_de_remise_au_dela_de_la_caisse(self):
        with self.assertRaises(treso.ErreurTresorerie):
            treso.creer_remise(self.caisse, self.banque, Decimal('50000'), self.jour, self.admin)
        self.assertFalse(RemiseBanque.objects.exists())

    def test_import_du_releve_deux_formats(self):
        crees, ignorees = treso.importer_releve(
            self.banque, "Date;Libellé;Montant\n01/10/2026;Virement reçu;150 000\n02/10/2026;Agios;-1 200,50\n",
            self.admin)
        self.assertEqual((crees, ignorees), (2, [1]))
        self.assertEqual(LigneReleve.objects.get(libelle='Agios').montant, Decimal('-1200.50'))
        crees, _ = treso.importer_releve(self.banque, "2026-10-03,Frais SMS,500,,REF9\n", self.admin, 'debit_credit')
        self.assertEqual(LigneReleve.objects.get(libelle='Frais SMS').montant, Decimal('-500'))
        # Réimporter ne double rien.
        crees, _ = treso.importer_releve(self.banque, "01/10/2026;Virement reçu;150 000\n", self.admin)
        self.assertEqual(crees, 0)

    def test_rapprochement_automatique_et_etat(self):
        treso.creer_remise(self.caisse, self.banque, Decimal('30000'), self.jour, self.admin, 'BV-1')
        LigneReleve.objects.create(compte_tresorerie=self.banque, date=self.jour, libelle='Versement espèces',
                                   montant=Decimal('30000'))
        frais = LigneReleve.objects.create(compte_tresorerie=self.banque, date=self.jour, libelle='Frais',
                                           montant=Decimal('-2000'))
        self.assertEqual(treso.rapprochement_automatique(self.banque), 1)
        e = treso.etat_rapprochement(self.banque, self.jour)
        self.assertEqual(e['solde_releve'] - e['solde_explique'], Decimal('0'))
        self.assertEqual(len(e['releve_seul']), 1)
        treso.comptabiliser_ligne_releve(frais, moteur.compte('frais_bancaires'), self.admin)
        e = treso.etat_rapprochement(self.banque, self.jour)
        self.assertEqual((e['solde_releve'], e['solde_compta']), (Decimal('28000'), Decimal('28000')))
        self.assertEqual(e['releve_seul'], [])

    def test_rapprochement_manuel_refuse_un_montant_different(self):
        treso.creer_remise(self.caisse, self.banque, Decimal('30000'), self.jour, self.admin)
        ligne = LigneReleve.objects.create(compte_tresorerie=self.banque, date=self.jour, libelle='X',
                                           montant=Decimal('29000'))
        ecriture = treso.ecritures_non_rapprochees(self.banque)[0]
        with self.assertRaises(treso.ErreurTresorerie):
            treso.rapprocher(ligne, ecriture)

    def test_ecrans_et_etats(self):
        for url in [reverse('comptabilite:tresorerie'), reverse('comptabilite:remises'),
                    reverse('comptabilite:comptes_tresorerie'), reverse('comptabilite:rapprochement', args=[self.banque.pk])]:
            self.assertEqual(self.client_admin.get(url).status_code, 200, url)
        for code in ('position_tresorerie', 'rapprochement', 'rejets_assurances'):
            self.assertEqual(self.client_admin.get(reverse('comptabilite:etat', args=[code])).status_code, 200, code)
        self.client_admin.post(reverse('comptabilite:remises'), {
            'caisse': self.caisse.pk, 'compte_tresorerie': self.banque.pk, 'montant': '10000',
            'date': self.jour.isoformat(), 'reference': 'BV-9'})
        self.assertTrue(RemiseBanque.objects.filter(reference='BV-9').exists())
        html = self.client_admin.get(reverse('comptabilite:tresorerie')).content.decode()
        nav = html[html.index('<nav class="o-nav">'):html.index('</nav>')]
        self.assertIn(reverse('comptabilite:rapprochement', args=[self.banque.pk]), nav)


class TestRefusAssurance(TestCase):

    def setUp(self):
        self.mugef = Assurance.objects.create(nom='MUGEF-CI', code='MUGEF', taux_prise_en_charge=Decimal('80'))
        self.patient = _patient()
        self.patient.assurance = self.mugef
        self.patient.save()
        self.admin = User.objects.create_superuser('admin7b', password='x')
        self.jour = timezone.localdate()
        f = Facture.objects.create(patient=self.patient, type_facture='consultation', statut='emise',
                                   montant_total=Decimal('10000'), montant_assurance=Decimal('8000'),
                                   montant_paye=Decimal('2000'))
        self.facture = Facture.objects.get(pk=f.pk)

    def test_report_sur_le_patient(self):
        tiers.rejeter(self.facture, Decimal('3000'), 'patient', 'Acte non couvert', self.jour, self.admin)
        f = Facture.objects.get(pk=self.facture.pk)
        self.assertEqual((f.reste_assurance, f.reste_patient), (Decimal('5000'), Decimal('3000')))
        self.assertEqual(f.statut, 'emise')

    def test_passage_en_perte_solde_la_facture(self):
        tiers.rejeter(self.facture, Decimal('8000'), 'perte', 'Assuré hors droits', self.jour, self.admin)
        f = Facture.objects.get(pk=self.facture.pk)
        self.assertEqual((f.reste_assurance, f.solde_restant, f.statut), (Decimal('0'), Decimal('0'), 'payee'))

    def test_pas_plus_que_le_du(self):
        with self.assertRaises(tiers.ErreurAssurance):
            tiers.rejeter(self.facture, Decimal('9000'), 'perte', 'x', self.jour, self.admin)
        with self.assertRaises(tiers.ErreurAssurance):
            tiers.rejeter(self.facture, Decimal('1000'), 'perte', '  ', self.jour, self.admin)

    def test_ecritures_des_refus(self):
        rejet = tiers.rejeter(self.facture, Decimal('3000'), 'patient', 'Acte non couvert', self.jour, self.admin)
        ecriture = moteur.ecriture_rejet(rejet)
        lignes = {l.compte.numero: l for l in ecriture.lignes.all()}
        self.assertEqual((lignes['4111'].debit, lignes['4112'].credit), (Decimal('3000'), Decimal('3000')))
        # La vente reconnaît la part d'origine (8 000), le refus en reporte 3 000 sur le patient.
        vente = {l.compte.numero: l for l in Ecriture.objects.get(origine=f'facture:{self.facture.pk}').lignes.all()}
        self.assertEqual(vente['4112'].debit, Decimal('8000'))
        perte = tiers.rejeter(Facture.objects.get(pk=self.facture.pk), Decimal('5000'), 'perte', 'Forclusion',
                              self.jour, self.admin)
        lignes = {l.compte.numero: l for l in moteur.ecriture_rejet(perte).lignes.all()}
        self.assertEqual(lignes['651'].debit, Decimal('5000'))

    def test_ecran_de_refus(self):
        client = _client(self.admin)
        url = reverse('comptabilite:rejet_assurance', args=[self.facture.pk])
        self.assertEqual(client.get(url).status_code, 200)
        client.post(url, {'montant': '8000', 'decision': 'perte', 'motif': 'Hors délai', 'date': self.jour.isoformat()})
        self.assertEqual(RejetAssurance.objects.get().montant, Decimal('8000'))



# ─── Lot 8 : achats, dons en nature en stock, clôture, états financiers ────────

from stock.models import CommandeStock, LigneCommande, MouvementStock, Produit  # noqa: E402

from . import cloture  # noqa: E402
from . import fournisseurs as achats  # noqa: E402
from .models import FactureFournisseur, LigneDon, ReglementFournisseur  # noqa: E402


def _compte(numero):
    return Compte.objects.get(numero=numero)


class TestAchats(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser('admin8', password='x')
        self.jour = timezone.localdate()

    def _facture(self):
        f = FactureFournisseur(fournisseur='LABOREX', reference='F-123', date=self.jour)
        return achats.enregistrer_facture(f, [(_compte('601'), 'Médicaments', Decimal('100000')),
                                              (_compte('604'), 'Gants', Decimal('20000'))], self.admin)

    def test_facture_et_reglement(self):
        f = self._facture()
        self.assertTrue(f.numero.startswith('FFO'))
        achat = Ecriture.objects.get(origine=f'facture_fournisseur:{f.pk}')
        self.assertEqual(achat.journal.code, 'ACH')
        self.assertEqual(_lignes(achat), {'601': (Decimal('100000'), Decimal('0')),
                                          '604': (Decimal('20000'), Decimal('0')),
                                          '401': (Decimal('0'), Decimal('120000'))})
        r = achats.regler(f, Decimal('50000'), self.jour, 'virement', self.admin, reference='VIR-1')
        self.assertEqual(_lignes(Ecriture.objects.get(origine=f'reglement_fournisseur:{r.pk}')),
                         {'401': (Decimal('50000'), Decimal('0')), '521': (Decimal('0'), Decimal('50000'))})
        self.assertEqual(FactureFournisseur.objects.get(pk=f.pk).reste, Decimal('70000'))
        with self.assertRaises(achats.ErreurAchat):
            achats.regler(f, Decimal('80000'), self.jour, 'virement', self.admin)

    def test_reglement_depuis_un_compte_choisi(self):
        f = self._facture()
        mm = CompteTresorerie.objects.get(libelle='Orange Money')
        r = achats.regler(f, Decimal('1000'), self.jour, 'mobile_money', self.admin, compte_tresorerie=mm)
        e = Ecriture.objects.get(origine=f'reglement_fournisseur:{r.pk}')
        self.assertEqual((e.journal.code, _lignes(e)['5522']), ('MM', (Decimal('0'), Decimal('1000'))))

    def test_compte_hors_charges_refuse(self):
        f = FactureFournisseur(fournisseur='X', date=self.jour)
        with self.assertRaises(achats.ErreurAchat):
            achats.enregistrer_facture(f, [(_compte('4111'), '', Decimal('100'))], self.admin)
        with self.assertRaises(achats.ErreurAchat):
            achats.enregistrer_facture(f, [], self.admin)

    def test_reprise_d_une_commande_de_stock(self):
        p = Produit.objects.create(nom='Paracétamol 500', type='medicament', prix_achat=Decimal('25'))
        g = Produit.objects.create(nom='Gants', type='consommable', prix_achat=Decimal('50'))
        cmd = CommandeStock.objects.create(statut='recu')
        LigneCommande.objects.create(commande=cmd, produit=p, quantite_commandee=20, quantite_recue=10,
                                     prix_unitaire=Decimal('500'))
        LigneCommande.objects.create(commande=cmd, produit=g, quantite_commandee=4, quantite_recue=4,
                                     prix_unitaire=Decimal('250'))
        lignes = {c.numero: m for c, _, m in achats.lignes_commande_stock(cmd)}
        self.assertEqual(lignes, {'601': Decimal('5000'), '604': Decimal('1000')})
        reponse = _client(self.admin).get(reverse('comptabilite:facture_fournisseur_nouvelle') + f'?commande_stock={cmd.pk}')
        self.assertContains(reponse, cmd.numero)

    def test_ecrans(self):
        client = _client(self.admin)
        reponse = client.post(reverse('comptabilite:facture_fournisseur_nouvelle'), {
            'fournisseur': 'UBIPHARM', 'reference': 'U-9', 'date': self.jour.isoformat(), 'objet': 'Réassort',
            'nb_lignes': '2', 'compte_0': _compte('601').pk, 'libelle_0': 'Antibiotiques', 'montant_0': '45 000',
            'compte_1': '', 'libelle_1': '', 'montant_1': ''})
        f = FactureFournisseur.objects.get(reference='U-9')
        self.assertRedirects(reponse, reverse('comptabilite:facture_fournisseur', args=[f.pk]))
        self.assertEqual(f.montant_total, Decimal('45000'))
        client.post(reverse('comptabilite:facture_fournisseur', args=[f.pk]),
                    {'montant': '45000', 'mode': 'cheque', 'date': self.jour.isoformat(), 'reference': 'CHQ-1'})
        self.assertEqual(ReglementFournisseur.objects.get().montant, Decimal('45000'))
        for url in [reverse('comptabilite:factures_fournisseurs') + '?filtre=toutes',
                    reverse('comptabilite:facture_fournisseur', args=[f.pk]),
                    reverse('comptabilite:facture_fournisseur_modifier', args=[f.pk])]:
            self.assertEqual(client.get(url).status_code, 200, url)
        for code in ('dettes_fournisseurs', 'bilan', 'compte_resultat'):
            self.assertEqual(client.get(reverse('comptabilite:etat', args=[code])).status_code, 200, code)

    def test_dettes_fournisseurs(self):
        f = self._facture()
        achats.regler(f, Decimal('20000'), self.jour, 'virement', self.admin)
        etat = ETATS['dettes_fournisseurs']['fonction'](self.jour, self.jour, {})
        total = etat['tableaux'][0]['lignes'][-1]
        self.assertEqual(total['cellules'][-1], Decimal('100000'))


class TestDonEnStock(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser('admin8b', password='x')
        self.para = Produit.objects.create(nom='Paracétamol 500', type='medicament', prix_achat=Decimal('25'),
                                           stock_actuel=Decimal('100'))
        self.gants = Produit.objects.create(nom='Gants', type='consommable', prix_achat=Decimal('50'))
        self.don = Don.objects.create(donateur_nom='ONG Santé Plus', date=timezone.localdate(), nature='nature',
                                      montant=Decimal('1'), description='Médicaments et gants')

    def test_entree_en_stock_et_ecriture(self):
        achats.entrer_don_en_stock(self.don, [(self.para, Decimal('10'), Decimal('300'), 'L-1', None),
                                              (self.gants, Decimal('5'), Decimal('100'), '', None)], self.admin)
        self.assertEqual(Produit.objects.get(pk=self.para.pk).stock_actuel, Decimal('110'))
        mvt = MouvementStock.objects.get(produit=self.para)
        self.assertEqual((mvt.type, mvt.motif, mvt.reference), ('entree', 'don', self.don.numero))
        self.assertEqual(mvt.lot.numero_lot, 'L-1')
        self.assertEqual(Don.objects.get(pk=self.don.pk).montant, Decimal('3500'))
        ecriture = Ecriture.objects.get(origine=f'don:{self.don.pk}')
        self.assertEqual(_lignes(ecriture), {'311': (Decimal('3000'), Decimal('0')),
                                             '331': (Decimal('500'), Decimal('0')),
                                             '7581': (Decimal('0'), Decimal('3500'))})
        with self.assertRaises(achats.ErreurAchat):
            achats.entrer_don_en_stock(self.don, [(self.para, Decimal('1'), Decimal('1'), '', None)], self.admin)

    def test_don_en_especes_refuse(self):
        self.don.nature = 'especes'
        self.don.save()
        with self.assertRaises(achats.ErreurAchat):
            achats.entrer_don_en_stock(self.don, [(self.para, Decimal('1'), Decimal('1'), '', None)], self.admin)

    def test_ecran(self):
        client = _client(self.admin)
        url = reverse('comptabilite:don_stock', args=[self.don.pk])
        self.assertEqual(client.get(url).status_code, 200)
        client.post(url, {f'qte_{self.para.pk}': '4', f'valeur_{self.para.pk}': '250', f'lot_{self.para.pk}': 'X'})
        self.assertEqual(LigneDon.objects.get().montant, Decimal('1000'))
        # Entré en stock, le don ne se modifie plus.
        reponse = client.get(reverse('comptabilite:don_modifier', args=[self.don.pk]))
        self.assertRedirects(reponse, reverse('comptabilite:dons'))


class TestCloture(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser('admin8c', password='x')
        self.e2025 = Exercice.objects.create(libelle='2025', date_debut=_date(2025, 1, 1), date_fin=_date(2025, 12, 31))
        od = moteur.journal('OD')
        ecritures = [
            moteur.creer_ecriture(od, _date(2025, 3, 1), 'Subvention reçue',
                                  [(_compte('521'), None, Decimal('100000'), Decimal('0'), ''),
                                   (_compte('718'), None, Decimal('0'), Decimal('100000'), '')]),
            moteur.creer_ecriture(moteur.journal('ACH'), _date(2025, 4, 1), 'Achat médicaments',
                                  [(_compte('601'), None, Decimal('30000'), Decimal('0'), ''),
                                   (_compte('401'), None, Decimal('0'), Decimal('30000'), 'LABOREX')]),
        ]
        moteur.valider(ecritures, self.admin)

    def _cloturer(self):
        return cloture.cloturer(self.e2025, self.admin, malgre_avertissements=True)

    def test_inventaire(self):
        e = cloture.comptabiliser_inventaire(self.e2025, None, {'medicament': Decimal('20000'),
                                                                'consommable': Decimal('0')}, self.admin)
        self.assertEqual(_lignes(e), {'311': (Decimal('20000'), Decimal('0')), '6031': (Decimal('0'), Decimal('20000'))})
        self.assertEqual(e.date, _date(2025, 12, 31))
        # Refaite tant qu'elle est en brouillon : la nouvelle remplace l'ancienne.
        e = cloture.comptabiliser_inventaire(self.e2025, None, {'medicament': Decimal('15000')}, self.admin)
        self.assertEqual(_lignes(e)['311'], (Decimal('15000'), Decimal('0')))
        self.assertEqual(Ecriture.objects.filter(origine__startswith='inventaire:').count(), 1)

    def test_controles(self):
        verif = cloture.controles(self.e2025)
        self.assertEqual(verif['bloquants'], [])
        self.assertTrue(any('inventaire' in a for a in verif['avertissements']))
        moteur.creer_ecriture(moteur.journal('OD'), _date(2025, 5, 1), 'Brouillon',
                              [(_compte('521'), None, Decimal('1'), Decimal('0'), ''),
                               (_compte('758'), None, Decimal('0'), Decimal('1'), '')])
        self.assertTrue(any('brouillon' in b for b in cloture.controles(self.e2025)['bloquants']))
        with self.assertRaises(moteur.ErreurCompta):
            self._cloturer()

    def test_avertissements_a_confirmer(self):
        with self.assertRaises(moteur.ErreurCompta):
            cloture.cloturer(self.e2025, self.admin)
        self.assertEqual(Exercice.objects.get(pk=self.e2025.pk).statut, 'ouvert')

    def test_cloture_et_a_nouveaux(self):
        self._cloturer()
        e = Exercice.objects.get(pk=self.e2025.pk)
        self.assertEqual((e.statut, e.resultat), ('cloture', Decimal('70000')))
        an = Ecriture.objects.get(origine__startswith=f'an:{e.pk}:')
        self.assertEqual((an.journal.code, an.date, an.statut), ('AN', _date(2026, 1, 1), 'validee'))
        self.assertEqual(_lignes(an), {'521': (Decimal('100000'), Decimal('0')),
                                       '401': (Decimal('0'), Decimal('30000')),
                                       '131': (Decimal('0'), Decimal('70000'))})
        self.assertEqual(an.lignes.get(compte__numero='401').tiers, 'LABOREX')
        # L'exercice clos est figé.
        with self.assertRaises(moteur.ErreurCompta):
            moteur.creer_ecriture(moteur.journal('OD'), _date(2025, 6, 1), 'Trop tard',
                                  [(_compte('521'), None, Decimal('1'), Decimal('0'), ''),
                                   (_compte('758'), None, Decimal('0'), Decimal('1'), '')])

    def test_soldes_apres_cloture_sans_double_compte(self):
        self._cloturer()
        fin = _date(2026, 12, 31)
        self.assertEqual(treso.solde_comptable(_compte('521'), fin), Decimal('100000'))
        balance = ETATS['balance']['fonction'](_date(2026, 1, 1), fin, {})
        ligne_521 = next(l for l in balance['tableaux'][0]['lignes'] if l['cellules'][0] == '521')
        # À-nouveau en solde de début, pas en mouvement de la période.
        self.assertEqual(ligne_521['cellules'][2:7], [Decimal('100000'), None, None, None, Decimal('100000')])
        bilan = ETATS['bilan']['fonction'](_date(2026, 1, 1), fin, {})
        self.assertFalse(any('Attention' in n for n in bilan['notes']))
        actif = bilan['tableaux'][0]['lignes'][-1]['cellules']
        passif = bilan['tableaux'][1]['lignes'][-1]['cellules']
        self.assertEqual((actif[3], passif[1]), (Decimal('100000'), Decimal('100000')))
        # Le bilan de 2025 reste lisible après sa clôture.
        bilan_2025 = ETATS['bilan']['fonction'](_date(2025, 1, 1), _date(2025, 12, 31), {})
        self.assertEqual(bilan_2025['tableaux'][1]['lignes'][-1]['cellules'][1], Decimal('100000'))

    def test_compte_de_resultat(self):
        cr = ETATS['compte_resultat']['fonction'](_date(2025, 1, 1), _date(2025, 12, 31), {})
        self.assertEqual(cr['tableaux'][0]['lignes'][-1]['cellules'], ['Excédent net', Decimal('70000')])

    def test_bilan_equilibre_avant_cloture(self):
        bilan = ETATS['bilan']['fonction'](_date(2025, 1, 1), _date(2025, 12, 31), {})
        self.assertFalse(any('Attention' in n for n in bilan['notes']))
        passif = {l['cellules'][0]: l['cellules'][1] for l in bilan['tableaux'][1]['lignes'] if l['type'] == 'ligne'}
        self.assertEqual(passif["Résultat de l'exercice (non clôturé)"], Decimal('70000'))
        self.assertEqual(passif['Fournisseurs'], Decimal('30000'))

    def test_rouvrir(self):
        self._cloturer()
        cloture.rouvrir(Exercice.objects.get(pk=self.e2025.pk), self.admin)
        self.assertEqual(Exercice.objects.get(pk=self.e2025.pk).statut, 'ouvert')
        self.assertFalse(Ecriture.objects.filter(origine__startswith='an:').exists())

    def test_ecrans(self):
        client = _client(self.admin)
        self.assertEqual(client.get(reverse('comptabilite:exercices')).status_code, 200)
        url = reverse('comptabilite:exercice', args=[self.e2025.pk])
        self.assertEqual(client.get(url).status_code, 200)
        self.assertContains(client.post(url, {'action': 'verifier'}), 'Points à examiner')
        client.post(url, {'action': 'inventaire', 'valeur_medicament': '5000', 'valeur_consommable': '0'})
        e = Ecriture.objects.get(origine__startswith='inventaire:')
        moteur.valider([e], self.admin)
        client.post(url, {'action': 'cloturer', 'malgre': '1'})
        self.assertEqual(Exercice.objects.get(pk=self.e2025.pk).statut, 'cloture')
        self.assertEqual(client.get(url).status_code, 200)

    def test_cloture_reservee(self):
        user = _perm(User.objects.create_user('compta8', password='x'), 'comptabilite', 'view_exercice')
        client = _client(user)
        url = reverse('comptabilite:exercice', args=[self.e2025.pk])
        self.assertEqual(client.post(url, {'action': 'cloturer', 'malgre': '1'}).status_code, 403)
        self.assertEqual(Exercice.objects.get(pk=self.e2025.pk).statut, 'ouvert')


class TestEcranAssureurs(TestCase):
    """« Assureurs et taux » s'ouvre dans le module, sans passer par l'admin."""

    def setUp(self):
        self.admin = User.objects.create_superuser('admin_ass', password='x')

    def test_ajout_modification_et_menu(self):
        client = _client(self.admin)
        url = reverse('comptabilite:assureurs')
        self.assertEqual(client.get(url).status_code, 200)
        client.post(url, {'nom': 'MUGEF-CI', 'code': 'mugef', 'telephone': '', 'taux_prise_en_charge': '80',
                          'actif': 'on'})
        a = Assurance.objects.get(code='MUGEF')
        client.post(reverse('comptabilite:assureur_modifier', args=[a.pk]),
                    {'nom': 'MUGEF-CI', 'code': 'MUGEF', 'taux_prise_en_charge': '70', 'actif': 'on'})
        self.assertEqual(Assurance.objects.get(pk=a.pk).taux_prise_en_charge, Decimal('70'))
        html = client.get(url).content.decode()
        self.assertNotIn('/admin/patients/assurance/', html)

    def test_taux_borne(self):
        reponse = _client(self.admin).post(reverse('comptabilite:assureurs'),
                                           {'nom': 'X', 'code': 'X', 'taux_prise_en_charge': '120'})
        self.assertContains(reponse, 'entre 0 et 100')
        self.assertFalse(Assurance.objects.filter(code='X').exists())

    def test_reserve(self):
        user = User.objects.create_user('sans_droit', password='x')
        self.assertEqual(_client(user).get(reverse('comptabilite:assureurs')).status_code, 403)


class TestOperateursMobileMoney(TestCase):
    """Un paiement Mobile Money dit par quel opérateur il est arrivé."""

    def setUp(self):
        self.caisse = Caisse.objects.create(nom='Caisse Accueil', code='ACC')
        self.awa = _caissiere('awa_mm')
        self.session = regles.ouvrir_session(self.awa, self.caisse, Decimal('0'))

    def test_operateur_et_transaction_exiges(self):
        facture = _facture(Decimal('3000'))
        client = _client(self.awa)
        url = reverse('facturation:payer', args=[facture.pk])
        client.post(url, {'pay_montant': '3000', 'pay_mode': 'mobile_money', 'pay_transaction': 'TX1'})
        client.post(url, {'pay_montant': '3000', 'pay_mode': 'mobile_money',
                          'pay_operateur': CompteTresorerie.objects.get(libelle='Wave').pk, 'pay_transaction': ' '})
        self.assertFalse(Paiement.objects.filter(facture=facture).exists())
        _payer(self.awa, facture, 3000, mode='mobile_money', operateur='Orange Money', transaction='OM-778')
        p = Paiement.objects.get(facture=facture)
        self.assertEqual((p.operateur.libelle, p.reference), ('Orange Money', 'OM-778'))

    def test_meme_transaction_refusee(self):
        _payer(self.awa, _facture(Decimal('1000')), 1000, mode='mobile_money', transaction='WV-1')
        doublon = _facture(Decimal('1000'))
        _payer(self.awa, doublon, 1000, mode='mobile_money', transaction='wv-1')
        self.assertFalse(Paiement.objects.filter(facture=doublon).exists())
        # Le même numéro chez un autre opérateur est une autre transaction.
        _payer(self.awa, doublon, 1000, mode='mobile_money', operateur='MoMo', transaction='WV-1')
        self.assertTrue(Paiement.objects.filter(facture=doublon).exists())

    def test_operateur_inactif_refuse(self):
        CompteTresorerie.objects.filter(libelle='Wave').update(actif=False)
        facture = _facture(Decimal('1000'))
        _payer(self.awa, facture, 1000, mode='mobile_money')
        self.assertFalse(Paiement.objects.filter(facture=facture).exists())

    def test_bilan_de_session_et_journee_par_operateur(self):
        _payer(self.awa, _facture(Decimal('2000')), 2000, mode='mobile_money', operateur='Wave')
        _payer(self.awa, _facture(Decimal('3000')), 3000, mode='mobile_money', operateur='Wave')
        _payer(self.awa, _facture(Decimal('1500')), 1500, mode='mobile_money', operateur='Orange Money')
        _payer(self.awa, _facture(Decimal('4000')), 4000)
        modes = {m['libelle']: (m['nb'], m['montant']) for m in regles.resume_session(self.session)['par_mode']}
        self.assertEqual(modes, {'Espèces': (1, Decimal('4000')),
                                 'Mobile Money — Wave': (2, Decimal('5000')),
                                 'Mobile Money — Orange Money': (1, Decimal('1500'))})
        journee = regles.resume_journee(self.session.journee)
        self.assertEqual([m['libelle'] for m in journee['totaux']['par_mode']],
                         ['Espèces', 'Mobile Money — Orange Money', 'Mobile Money — Wave'])
        admin = User.objects.create_superuser('admin_mm', password='x')
        html = _client(admin).get(reverse('comptabilite:journee', args=[self.session.journee.pk])).content.decode()
        self.assertIn('Mobile Money — Wave', html)

    def test_ancien_paiement_sans_operateur(self):
        p = Paiement.objects.create(facture=_facture(Decimal('1000')), montant=Decimal('1000'),
                                    mode_paiement='mobile_money', session=self.session, caisse=self.caisse)
        self.assertEqual(_lignes(moteur.ecriture_paiement(p))['552'], (Decimal('1000'), 0))
        libelles = [m['libelle'] for m in regles.resume_session(self.session)['par_mode']]
        self.assertEqual(libelles, ['Mobile Money (opérateur non précisé)'])

    def test_etat_des_recettes(self):
        _payer(self.awa, _facture(Decimal('2500')), 2500, mode='mobile_money', operateur='MoMo')
        jour = timezone.localdate()
        etat = ETATS['recettes']['fonction'](jour, jour, {})
        par_mode = {l['cellules'][0]: l['cellules'][2] for l in etat['tableaux'][1]['lignes'] if l['type'] == 'ligne'}
        self.assertEqual(par_mode, {'Mobile Money — MoMo': Decimal('2500')})

    def test_ecrans_d_encaissement(self):
        facture = _facture(Decimal('1000'))
        html = _client(self.awa).get(reverse('facturation:detail', args=[facture.pk])).content.decode()
        self.assertIn('name="pay_operateur"', html)
        self.assertIn('Orange Money', html)
