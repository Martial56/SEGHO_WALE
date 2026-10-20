from datetime import date
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings

from centres.models import Centre
from core.middleware import centre_actif
from patients.models import Patient

from . import hashing
from .models import AncrageBlockchain
from .services import (
    ancrer_evenement,
    verifier_integrite,
    identifiant_public,
    normaliser_metadonnees,
    pseudonymiser_code_patient,
)
from .signals import ancrer_analyse_laboratoire_validee

CLE_TEST = 'cle-de-pseudonymisation-reservee-aux-tests'
EMPREINTE_TEST = 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'


def _est_hexa(valeur, longueur):
    return len(valeur) == longueur and all(c in '0123456789abcdef' for c in valeur)


@override_settings(BLOCKCHAIN_ENABLED=True, BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST)
class AncrageEchangeHPRIMTests(TestCase):
    """L'échange HPRIM (demandes et résultats d'examens avec le laboratoire
    externe) est un point d'interopérabilité inter-systèmes central pour ce
    projet : ces tests vérifient que l'ancrage se déclenche au bon moment,
    uniquement après validation de la transaction, sans dépendre du réseau
    (ancrer_evenement est mocké)."""

    def setUp(self):
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-BC-TEST')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Kouassi', prenoms='Awa', date_naissance=date(1990, 1, 1),
                sexe='F', telephone='0102030405',
            )

    def _creer_demande(self):
        from laboratoire.models import DemandeExamen
        with centre_actif(self.centre):
            return DemandeExamen.objects.create(patient=self.patient, statut='demande')

    def _creer_echange(self, **champs):
        from laboratoire.models import EchangeHPRIM
        with centre_actif(self.centre):
            return EchangeHPRIM.objects.create(centre=self.centre, contenu='H|...', **champs)

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_envoi_transmis_declenche_ancrage(self, mock_ancrer):
        demande = self._creer_demande()
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0001.HPR',
                                demande=demande, statut='transmis')
        self.assertTrue(mock_ancrer.called)
        args, kwargs = mock_ancrer.call_args
        self.assertEqual(args[0], 'echange_hprim')
        self.assertEqual(kwargs['code_patient'], self.patient.code_patient)

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_metadonnees_hprim_conformes_a_la_liste_blanche(self, mock_ancrer):
        demande = self._creer_demande()
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0003.HPR',
                                demande=demande, statut='transmis')
        _, kwargs = mock_ancrer.call_args
        self.assertEqual(kwargs['metadonnees'], {'type_document': 'hprim-envoi', 'type_message_hprim': 'ORM'})
        # Les métadonnées doivent passer la normalisation sans erreur.
        self.assertEqual(normaliser_metadonnees(kwargs['metadonnees']), kwargs['metadonnees'])

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_envoi_en_erreur_ne_declenche_pas_ancrage(self, mock_ancrer):
        demande = self._creer_demande()
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0002.HPR',
                                demande=demande, statut='erreur')
        mock_ancrer.assert_not_called()

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_reception_traitee_declenche_ancrage(self, mock_ancrer):
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='reception', contexte='ORU', nom_fichier='LABO0001.HPR', statut='traite')
        self.assertTrue(mock_ancrer.called)
        args, kwargs = mock_ancrer.call_args
        self.assertEqual(args[0], 'echange_hprim')
        self.assertEqual(kwargs['metadonnees']['type_document'], 'hprim-reception')

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_reception_recue_non_traitee_ne_declenche_pas_ancrage(self, mock_ancrer):
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='reception', contexte='ORU', nom_fichier='LABO0002.HPR', statut='recu')
        mock_ancrer.assert_not_called()

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_pas_dancrage_avant_validation_de_la_transaction(self, mock_ancrer):
        demande = self._creer_demande()
        self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0004.HPR',
                            demande=demande, statut='transmis')
        # La transaction de test n'est pas encore validée : rien ne doit être ancré.
        mock_ancrer.assert_not_called()

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_transaction_annulee_ne_declenche_pas_ancrage(self, mock_ancrer):
        demande = self._creer_demande()
        with self.captureOnCommitCallbacks(execute=True) as rappels:
            try:
                with transaction.atomic():
                    self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0005.HPR',
                                        demande=demande, statut='transmis')
                    raise RuntimeError('annulation simulée')
            except RuntimeError:
                pass
        self.assertEqual(len(rappels), 0)
        mock_ancrer.assert_not_called()

    @patch('blockchain_bridge.signals.ancrer_evenement', side_effect=RuntimeError('panne simulée'))
    def test_erreur_dancrage_journalisee_sans_bloquer(self, mock_ancrer):
        demande = self._creer_demande()
        with self.assertLogs('blockchain_bridge.signals', level='ERROR'):
            with self.captureOnCommitCallbacks(execute=True):
                echange = self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0006.HPR',
                                              demande=demande, statut='transmis')
        self.assertIsNotNone(echange.pk)

    @override_settings(BLOCKCHAIN_ENABLED=False)
    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_aucun_ancrage_si_blockchain_desactivee(self, mock_ancrer):
        demande = self._creer_demande()
        with self.captureOnCommitCallbacks(execute=True):
            self._creer_echange(sens='envoi', contexte='ORM', nom_fichier='WALE0007.HPR',
                                demande=demande, statut='transmis')
        mock_ancrer.assert_not_called()


@override_settings(BLOCKCHAIN_ENABLED=True, BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST)
class AncrageAnalyseLaboratoireTests(TestCase):
    """Vérifie que l'ancrage d'une analyse validée n'a lieu qu'une fois ses
    résultats attachés (voir signals.ancrer_analyse_laboratoire_validee) :
    l'empreinte doit refléter le jeu de résultats complet, pas un état
    intermédiaire sans aucun résultat."""

    def setUp(self):
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-BC-TEST2')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Yao', prenoms='Kofi', date_naissance=date(1985, 5, 5),
                sexe='M', telephone='0102030406',
            )

    def test_empreinte_inclut_les_resultats_attaches(self):
        from laboratoire.models import AnalyseLaboratoire, ResultatAnalyse

        analyse = AnalyseLaboratoire.objects.create(patient=self.patient, statut='valide')
        empreinte_sans_resultats = hashing.empreinte_analyse_laboratoire(analyse)

        ResultatAnalyse.objects.create(analyse=analyse, parametre='Hémoglobine', valeur='13.5', unite='g/dL')

        empreinte_avec_resultats = hashing.empreinte_analyse_laboratoire(analyse)

        self.assertNotEqual(
            empreinte_sans_resultats, empreinte_avec_resultats,
            "l'empreinte doit changer une fois le résultat attaché — sinon un ancrage "
            "déclenché avant l'attachement des résultats figerait un état incomplet.",
        )

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_ancrage_explicite_utilise_les_resultats_attaches(self, mock_ancrer):
        from laboratoire.models import AnalyseLaboratoire, ResultatAnalyse

        analyse = AnalyseLaboratoire.objects.create(patient=self.patient, statut='valide')
        ResultatAnalyse.objects.create(analyse=analyse, parametre='Hémoglobine', valeur='13.5', unite='g/dL')

        with self.captureOnCommitCallbacks(execute=True):
            ancrer_analyse_laboratoire_validee(analyse)

        mock_ancrer.assert_called_once()
        args, kwargs = mock_ancrer.call_args
        self.assertEqual(args[0], 'analyse_laboratoire')
        self.assertEqual(args[1], analyse.numero)
        self.assertEqual(args[2], hashing.empreinte_analyse_laboratoire(analyse))
        self.assertEqual(kwargs['metadonnees'], {'type_document': 'analyse_laboratoire'})

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_pas_dancrage_si_non_valide(self, mock_ancrer):
        from laboratoire.models import AnalyseLaboratoire

        analyse = AnalyseLaboratoire.objects.create(patient=self.patient, statut='resultat')
        with self.captureOnCommitCallbacks(execute=True):
            ancrer_analyse_laboratoire_validee(analyse)
        mock_ancrer.assert_not_called()


@override_settings(BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST)
class ConfidentialiteTests(SimpleTestCase):
    """Règle de confidentialité : aucune donnée nominative ou clinique ne
    doit atteindre la chaîne (immuable et répliquée chez Org2)."""

    def test_pseudonyme_patient_format_et_determinisme(self):
        pseudonyme = pseudonymiser_code_patient('PAT20250001')
        self.assertTrue(_est_hexa(pseudonyme, 64))
        self.assertNotIn('PAT20250001', pseudonyme)
        self.assertEqual(pseudonyme, pseudonymiser_code_patient('PAT20250001'))
        self.assertNotEqual(pseudonyme, pseudonymiser_code_patient('PAT20250002'))

    def test_pseudonyme_depend_de_la_cle(self):
        pseudonyme = pseudonymiser_code_patient('PAT20250001')
        with self.settings(BLOCKCHAIN_CLE_PSEUDONYMISATION='autre-cle'):
            self.assertNotEqual(pseudonyme, pseudonymiser_code_patient('PAT20250001'))

    def test_pseudonyme_vide_sans_code_patient(self):
        self.assertEqual(pseudonymiser_code_patient(''), '')

    @override_settings(BLOCKCHAIN_CLE_PSEUDONYMISATION='')
    def test_cle_absente_refusee(self):
        with self.assertRaises(ImproperlyConfigured):
            pseudonymiser_code_patient('PAT20250001')
        with self.assertRaises(ImproperlyConfigured):
            identifiant_public('consultation', 'CONS20250001')

    def test_identifiant_public_masque_lidentifiant_interne(self):
        id_public = identifiant_public('consultation', 'CONS20250001')
        self.assertTrue(_est_hexa(id_public, 32))
        self.assertNotIn('CONS', id_public)
        self.assertEqual(id_public, identifiant_public('consultation', 'CONS20250001'))
        self.assertNotEqual(id_public, identifiant_public('facture', 'CONS20250001'))

    def test_normalisation_des_metadonnees(self):
        self.assertEqual(
            normaliser_metadonnees({'version_schema': 1, 'code_examen': 'GE', 'type_document': None}),
            {'version_schema': '1', 'code_examen': 'GE'},
        )
        self.assertEqual(normaliser_metadonnees(None), {})

    def test_metadonnees_non_conformes_refusees(self):
        cas = [
            {'nom_patient': 'KOUASSI'},
            {'type_document': 'consultation fièvre'},
            {'code_examen': ['GE', 'NFS']},
            {'code_examen': 'x' * 65},
        ]
        for metadonnees in cas:
            with self.subTest(metadonnees=metadonnees):
                with self.assertRaises(ValueError):
                    normaliser_metadonnees(metadonnees)


def _reponse(status_code, corps):
    return Mock(status_code=status_code, json=Mock(return_value=corps), text=str(corps))


@override_settings(
    BLOCKCHAIN_ENABLED=True,
    BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST,
    BLOCKCHAIN_GATEWAY_URL='http://passerelle-test',
)
class AncrerEvenementTests(TestCase):
    """Comportement de ancrer_evenement face à la passerelle (mockée)."""

    def _ancrer(self, metadonnees=None):
        return ancrer_evenement(
            'consultation', 'CONS20250001', EMPREINTE_TEST,
            code_patient='PAT20250001', code_centre='WALE', metadonnees=metadonnees,
        )

    @patch('requests.post')
    def test_aucune_donnee_interne_en_clair_dans_la_requete(self, mock_post):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx-1'})

        ancrage = self._ancrer(metadonnees={'version_schema': 1})

        payload = mock_post.call_args.kwargs['json']
        self.assertEqual(payload['codePatient'], pseudonymiser_code_patient('PAT20250001'))
        self.assertEqual(payload['idEntite'], identifiant_public('consultation', 'CONS20250001'))
        self.assertEqual(payload['idEvenement'], f"consultation:{payload['idEntite']}:v1")
        self.assertEqual(payload['metadonnees'], {'version_schema': '1'})
        self.assertNotIn('PAT20250001', str(payload))
        self.assertNotIn('CONS20250001', str(payload))
        # La correspondance avec l'identifiant interne reste en local.
        self.assertEqual(ancrage.id_entite, 'CONS20250001')
        self.assertEqual(ancrage.statut, 'confirme')
        self.assertEqual(ancrage.tx_id, 'tx-1')
        self.assertEqual(ancrage.version, 1)

    @patch('requests.post')
    def test_ancrage_confirme_jamais_renvoye(self, mock_post):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx-1'})
        self._ancrer()
        self._ancrer()
        self.assertEqual(mock_post.call_count, 1)

    @patch('requests.post')
    def test_ancrage_en_erreur_retente(self, mock_post):
        import requests

        mock_post.side_effect = [requests.ConnectionError('passerelle injoignable'),
                                 _reponse(201, {'txIdCreation': 'tx-2'})]

        premier = self._ancrer()
        self.assertEqual(premier.statut, 'erreur')

        second = self._ancrer()
        self.assertEqual(second.statut, 'confirme')
        self.assertEqual(second.erreur_message, '')
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(AncrageBlockchain.objects.count(), 1)

    @patch('requests.get')
    @patch('requests.post')
    def test_reponse_perdue_recuperee_si_deja_enregistre(self, mock_post, mock_get):
        mock_post.return_value = _reponse(502, {'erreur': 'un événement X est déjà enregistré, le registre est immuable'})
        mock_get.return_value = _reponse(200, {'empreinteHash': EMPREINTE_TEST, 'txIdCreation': 'tx-3'})

        ancrage = self._ancrer()

        self.assertEqual(ancrage.statut, 'confirme')
        self.assertEqual(ancrage.tx_id, 'tx-3')

    @patch('requests.get')
    @patch('requests.post')
    def test_version_deja_inscrite_avec_autre_empreinte(self, mock_post, mock_get):
        """La chaîne fait foi : la version déjà inscrite est enregistrée telle
        quelle, puis l'état courant est ancré comme version suivante."""
        mock_post.side_effect = [
            _reponse(502, {'erreur': 'un événement X est déjà enregistré, le registre est immuable'}),
            _reponse(201, {'txIdCreation': 'tx-5'}),
        ]
        mock_get.return_value = _reponse(200, {'empreinteHash': 'f' * 64, 'txIdCreation': 'tx-4'})

        ancrage = self._ancrer()

        self.assertEqual(ancrage.version, 2)
        self.assertEqual(ancrage.statut, 'confirme')
        self.assertEqual(ancrage.empreinte_hash, EMPREINTE_TEST)
        premiere = AncrageBlockchain.objects.get(version=1)
        self.assertEqual(premiere.statut, 'confirme')
        self.assertEqual(premiere.empreinte_hash, 'f' * 64)
        self.assertTrue(mock_post.call_args.kwargs['json']['idEvenement'].endswith(':v2'))

    @patch('requests.post')
    def test_metadonnees_non_conformes_jamais_envoyees(self, mock_post):
        with self.assertLogs('blockchain_bridge.services', level='ERROR'):
            ancrage = self._ancrer(metadonnees={'nom_patient': 'KOUASSI'})

        mock_post.assert_not_called()
        self.assertEqual(ancrage.statut, 'erreur')
        self.assertIn('non conformes', ancrage.erreur_message)

    @patch('requests.post')
    def test_rejet_de_la_passerelle_conserve_le_motif(self, mock_post):
        mock_post.return_value = _reponse(400, {'erreur': 'clé de métadonnée non autorisée'})

        ancrage = self._ancrer()

        self.assertEqual(ancrage.statut, 'erreur')
        self.assertIn('HTTP 400', ancrage.erreur_message)
        self.assertIn('non autorisée', ancrage.erreur_message)




EMPREINTE_MODIFIEE = 'a' * 64


@override_settings(
    BLOCKCHAIN_ENABLED=True,
    BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST,
    BLOCKCHAIN_GATEWAY_URL='http://passerelle-test',
)
class VersionnementTests(TestCase):
    """Chaque état distinct d'un enregistrement est ancré sous une version
    propre ; un état inchangé n'est jamais renvoyé."""

    def _ancrer(self, empreinte):
        return ancrer_evenement('consultation', 'CONS20250001', empreinte,
                                code_patient='PAT20250001', code_centre='WALE')

    @patch('requests.post')
    def test_modification_ancree_comme_nouvelle_version(self, mock_post):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx'})

        v1 = self._ancrer(EMPREINTE_TEST)
        v2 = self._ancrer(EMPREINTE_MODIFIEE)

        self.assertEqual((v1.version, v2.version), (1, 2))
        self.assertEqual(v2.statut, 'confirme')
        premier, second = [c.kwargs['json'] for c in mock_post.call_args_list]
        self.assertTrue(premier['idEvenement'].endswith(':v1'))
        self.assertTrue(second['idEvenement'].endswith(':v2'))
        # Même identifiant public d'entité : l'historique sur la chaîne regroupe les versions.
        self.assertEqual(premier['idEntite'], second['idEntite'])
        self.assertEqual(second['empreinteHash'], EMPREINTE_MODIFIEE)

    @patch('requests.post')
    def test_etat_inchange_jamais_renvoye(self, mock_post):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx'})
        self._ancrer(EMPREINTE_TEST)
        self.assertIsNone(self._ancrer(EMPREINTE_TEST))
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(AncrageBlockchain.objects.count(), 1)

    @patch('requests.post')
    def test_retour_a_un_etat_anterieur_est_une_nouvelle_version(self, mock_post):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx'})
        self._ancrer(EMPREINTE_TEST)
        self._ancrer(EMPREINTE_MODIFIEE)
        v3 = self._ancrer(EMPREINTE_TEST)
        self.assertEqual(v3.version, 3)
        self.assertEqual(AncrageBlockchain.objects.count(), 3)

    @patch('requests.post')
    def test_version_en_erreur_retentee_sans_nouvelle_version(self, mock_post):
        import requests

        mock_post.side_effect = [
            _reponse(201, {'txIdCreation': 'tx-1'}),
            requests.ConnectionError('passerelle injoignable'),
            _reponse(201, {'txIdCreation': 'tx-2'}),
        ]
        self._ancrer(EMPREINTE_TEST)
        en_erreur = self._ancrer(EMPREINTE_MODIFIEE)
        self.assertEqual((en_erreur.version, en_erreur.statut), (2, 'erreur'))

        reprise = self._ancrer(EMPREINTE_MODIFIEE)
        self.assertEqual((reprise.version, reprise.statut), (2, 'confirme'))
        self.assertEqual(AncrageBlockchain.objects.count(), 2)

    @patch('blockchain_bridge.services.hashing.recalculer_empreinte', return_value=EMPREINTE_MODIFIEE)
    @patch('requests.post')
    def test_verification_porte_sur_la_derniere_version(self, mock_post, _mock_empreinte):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx'})
        v1 = self._ancrer(EMPREINTE_TEST)
        v2 = self._ancrer(EMPREINTE_MODIFIEE)

        mock_post.return_value = _reponse(200, {'conforme': True})
        resultat = verifier_integrite(v1)

        url = mock_post.call_args.args[0]
        self.assertIn(v2.id_evenement, url)
        self.assertTrue(resultat['conforme'])
        self.assertEqual(resultat['version_verifiee'], 2)
        self.assertIn('remplacée par la version 2', resultat['remarque'])


@override_settings(BLOCKCHAIN_ENABLED=True, BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST)
class VersionnementSignauxTests(TestCase):
    """Les modifications d'un patient déclenchent un nouvel ancrage
    (la déduplication par empreinte est assurée par ancrer_evenement)."""

    def setUp(self):
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-BC-TEST3')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Koffi', prenoms='Ama', date_naissance=date(1992, 3, 3),
                sexe='F', telephone='0102030407',
            )

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_modification_patient_declenche_ancrage(self, mock_ancrer):
        with self.captureOnCommitCallbacks(execute=True):
            with centre_actif(self.centre):
                self.patient.allergies = 'Pénicilline'
                self.patient.save()
        self.assertTrue(mock_ancrer.called)
        args, _ = mock_ancrer.call_args
        self.assertEqual(args[0], 'patient')
        self.assertEqual(args[2], hashing.empreinte_patient(self.patient))



# --- Reprise des ancrages en erreur (commande reessayer_ancrages) ---

from io import StringIO  # noqa: E402

from django.core.management import call_command  # noqa: E402


@override_settings(
    BLOCKCHAIN_ENABLED=True,
    BLOCKCHAIN_CLE_PSEUDONYMISATION=CLE_TEST,
    BLOCKCHAIN_GATEWAY_URL='http://passerelle-test',
)
class RepriseAncragesTests(TestCase):

    def _creer_ancrage_en_erreur(self, type_entite='paiement', id_entite='PAI20250001'):
        return AncrageBlockchain.objects.create(
            id_evenement=f'{type_entite}:{identifiant_public(type_entite, id_entite)}:v1',
            version=1,
            type_entite=type_entite, id_entite=id_entite,
            code_patient='PAT20250001', code_centre='WALE',
            empreinte_hash=EMPREINTE_TEST, statut='erreur',
            erreur_message='passerelle injoignable',
        )

    @patch('blockchain_bridge.management.commands.reessayer_ancrages.hashing.recalculer_empreinte',
           return_value=EMPREINTE_TEST)
    @patch('requests.post')
    def test_ancrage_en_erreur_repris_et_confirme(self, mock_post, _mock_empreinte):
        mock_post.return_value = _reponse(201, {'txIdCreation': 'tx-reprise'})
        ancrage = self._creer_ancrage_en_erreur()

        sortie = StringIO()
        call_command('reessayer_ancrages', stdout=sortie)

        ancrage.refresh_from_db()
        self.assertEqual(ancrage.statut, 'confirme')
        self.assertEqual(ancrage.tx_id, 'tx-reprise')
        self.assertEqual(AncrageBlockchain.objects.count(), 1)
        self.assertIn('1 confirmé', sortie.getvalue())
        self.assertEqual(mock_post.call_args.kwargs['json']['metadonnees'], {'type_document': 'paiement'})

    @patch('blockchain_bridge.management.commands.reessayer_ancrages.hashing.recalculer_empreinte',
           return_value=None)
    @patch('requests.post')
    def test_entite_supprimee_signalee_sans_envoi(self, mock_post, _mock_empreinte):
        ancrage = self._creer_ancrage_en_erreur()

        call_command('reessayer_ancrages', stdout=StringIO())

        mock_post.assert_not_called()
        ancrage.refresh_from_db()
        self.assertEqual(ancrage.statut, 'erreur')
        self.assertIn('introuvable', ancrage.erreur_message)

    @override_settings(BLOCKCHAIN_ENABLED=False)
    @patch('requests.post')
    def test_aucune_reprise_si_blockchain_desactivee(self, mock_post):
        self._creer_ancrage_en_erreur()

        call_command('reessayer_ancrages', stdout=StringIO())

        mock_post.assert_not_called()
