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


def _payer(user, facture, montant, mode='especes'):
    return _client(user).post(reverse('facturation:payer', args=[facture.pk]),
                              {'pay_montant': str(montant), 'pay_mode': mode})


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
        self.assertEqual(_lignes(ecriture)['552'], (Decimal('5000'), 0))

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
