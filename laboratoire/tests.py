from datetime import date

from django.test import TestCase

from centres.models import Centre
from core.middleware import centre_actif
from patients.models import Patient

from .models import ConfigurationHPRIM, DemandeExamen, EchangeHPRIM, LigneDemandeExamen


class SignalHPRIMCentreTests(TestCase):
    """(c) Le signal d'envoi HPRIM ne se déclenche pas pour un centre sans
    configuration HPRIM active (ex. CMS WALE Toumbokro, sans SYSLAM)."""

    def setUp(self):
        self.wale = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-TEST3')
        self.toumbokro = Centre.objects.create(nom='CMS WALE Toumbokro', code='TOUMBOKRO-TEST3')

        with centre_actif(self.wale):
            ConfigurationHPRIM.objects.create(nom='Config WALE', actif=True)
            self.patient_wale = Patient.objects.create(
                nom='Kouassi', prenoms='Awa', date_naissance=date(1990, 1, 1),
                sexe='F', telephone='0102030405',
            )
        with centre_actif(self.toumbokro):
            self.patient_toumbokro = Patient.objects.create(
                nom='Yao', prenoms='Kofi', date_naissance=date(1985, 5, 5),
                sexe='M', telephone='0102030406',
            )

    def _creer_demande_avec_ligne(self, centre, patient):
        with centre_actif(centre):
            demande = DemandeExamen.objects.create(patient=patient, statut='brouillon')
            LigneDemandeExamen.objects.create(demande=demande, libelle='NFS', prix=5000)
            return demande

    def test_silence_total_pour_centre_sans_config(self):
        demande = self._creer_demande_avec_ligne(self.toumbokro, self.patient_toumbokro)

        with centre_actif(self.toumbokro):
            with self.captureOnCommitCallbacks(execute=True):
                demande.statut = 'demande'
                demande.save()

        self.assertEqual(EchangeHPRIM.all_objects.filter(demande=demande).count(), 0)

    def test_signal_se_declenche_pour_centre_avec_config(self):
        demande = self._creer_demande_avec_ligne(self.wale, self.patient_wale)

        with centre_actif(self.wale):
            with self.captureOnCommitCallbacks(execute=True):
                demande.statut = 'demande'
                demande.save()

        echanges = EchangeHPRIM.all_objects.filter(demande=demande)
        self.assertEqual(echanges.count(), 1)
        self.assertEqual(echanges.first().centre, self.wale)
