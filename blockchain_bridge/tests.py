from datetime import date
from unittest.mock import patch

from django.test import TestCase

from centres.models import Centre
from core.middleware import centre_actif
from patients.models import Patient

from . import hashing
from .signals import ancrer_analyse_laboratoire_validee


class AncrageEchangeHPRIMTests(TestCase):
    """L'échange HPRIM (demandes et résultats d'examens avec le laboratoire
    externe) est un point d'interopérabilité inter-systèmes central pour ce
    projet : ces tests vérifient que l'ancrage se déclenche au bon moment,
    sans dépendre du réseau (ancrer_evenement est mocké)."""

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

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_envoi_transmis_declenche_ancrage(self, mock_ancrer):
        from laboratoire.models import EchangeHPRIM
        demande = self._creer_demande()
        with centre_actif(self.centre):
            EchangeHPRIM.objects.create(
                sens='envoi', contexte='ORM', nom_fichier='WALE0001.HPR',
                demande=demande, contenu='H|...', statut='transmis', centre=self.centre,
            )
        self.assertTrue(mock_ancrer.called)
        args, kwargs = mock_ancrer.call_args
        self.assertEqual(args[0], 'echange_hprim')
        self.assertEqual(kwargs['code_patient'], self.patient.code_patient)

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_envoi_en_erreur_ne_declenche_pas_ancrage(self, mock_ancrer):
        from laboratoire.models import EchangeHPRIM
        demande = self._creer_demande()
        with centre_actif(self.centre):
            EchangeHPRIM.objects.create(
                sens='envoi', contexte='ORM', nom_fichier='WALE0002.HPR',
                demande=demande, contenu='H|...', statut='erreur', centre=self.centre,
            )
        mock_ancrer.assert_not_called()

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_reception_traitee_declenche_ancrage(self, mock_ancrer):
        from laboratoire.models import EchangeHPRIM
        with centre_actif(self.centre):
            EchangeHPRIM.objects.create(
                sens='reception', contexte='ORU', nom_fichier='LABO0001.HPR',
                contenu='H|...résultats...', statut='traite', centre=self.centre,
            )
        self.assertTrue(mock_ancrer.called)
        args, _ = mock_ancrer.call_args
        self.assertEqual(args[0], 'echange_hprim')

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_reception_recue_non_traitee_ne_declenche_pas_ancrage(self, mock_ancrer):
        from laboratoire.models import EchangeHPRIM
        with centre_actif(self.centre):
            EchangeHPRIM.objects.create(
                sens='reception', contexte='ORU', nom_fichier='LABO0002.HPR',
                contenu='H|...', statut='recu', centre=self.centre,
            )
        mock_ancrer.assert_not_called()


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

        ancrer_analyse_laboratoire_validee(analyse)

        mock_ancrer.assert_called_once()
        args, kwargs = mock_ancrer.call_args
        self.assertEqual(args[0], 'analyse_laboratoire')
        self.assertEqual(args[1], analyse.numero)
        self.assertEqual(args[2], hashing.empreinte_analyse_laboratoire(analyse))

    @patch('blockchain_bridge.signals.ancrer_evenement')
    def test_pas_dancrage_si_non_valide(self, mock_ancrer):
        from laboratoire.models import AnalyseLaboratoire

        analyse = AnalyseLaboratoire.objects.create(patient=self.patient, statut='resultat')
        ancrer_analyse_laboratoire_validee(analyse)
        mock_ancrer.assert_not_called()
