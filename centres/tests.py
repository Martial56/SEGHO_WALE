from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from core.middleware import CurrentUserMiddleware, centre_actif, get_current_centre
from patients.models import Patient

from .models import Centre
from .views import changer_centre


class CloisonnementPatientTests(TestCase):
    """(a) Cloisonnement d'un modèle clé (Patient) entre deux centres."""

    def setUp(self):
        self.wale = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-TEST')
        self.toumbokro = Centre.objects.create(nom='CMS WALE Toumbokro', code='TOUMBOKRO-TEST')
        with centre_actif(self.wale):
            self.patient_wale = Patient.objects.create(
                nom='Kouassi', prenoms='Awa', date_naissance=date(1990, 1, 1),
                sexe='F', telephone='0102030405',
            )
        with centre_actif(self.toumbokro):
            self.patient_toumbokro = Patient.objects.create(
                nom='Yao', prenoms='Kofi', date_naissance=date(1985, 5, 5),
                sexe='M', telephone='0102030406',
            )

    def test_objects_filtre_par_centre_actif(self):
        with centre_actif(self.wale):
            self.assertEqual(list(Patient.objects.all()), [self.patient_wale])
        with centre_actif(self.toumbokro):
            self.assertEqual(list(Patient.objects.all()), [self.patient_toumbokro])

    def test_aucun_centre_actif_ne_renvoie_rien(self):
        self.assertEqual(Patient.objects.count(), 0)

    def test_all_objects_voit_tout(self):
        self.assertEqual(Patient.all_objects.count(), 2)

    def test_centre_affecte_automatiquement_a_la_creation(self):
        with centre_actif(self.wale):
            p = Patient.objects.create(
                nom='Test', prenoms='X', date_naissance=date(2000, 1, 1),
                sexe='M', telephone='000',
            )
        self.assertEqual(p.centre, self.wale)


class BasculeMultiCentreTests(TestCase):
    """(b) Un médecin multi-centres ne voit que le centre actif, et la
    bascule (changer_centre) change effectivement le périmètre."""

    def setUp(self):
        self.wale = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-TEST2')
        self.toumbokro = Centre.objects.create(nom='CMS WALE Toumbokro', code='TOUMBOKRO-TEST2')
        self.medecin = User.objects.create_user('dr.multi', password='xxx')
        self.medecin.profile.centres.set([self.wale, self.toumbokro])
        self.medecin.profile.save()

        with centre_actif(self.wale):
            self.patient_wale = Patient.objects.create(
                nom='A', prenoms='B', date_naissance=date(1990, 1, 1), sexe='F', telephone='1',
            )
        with centre_actif(self.toumbokro):
            self.patient_toumbokro = Patient.objects.create(
                nom='C', prenoms='D', date_naissance=date(1990, 1, 1), sexe='M', telephone='2',
            )

        self.factory = RequestFactory()

    def _run_middleware(self, user):
        captured = {}

        def get_response(request):
            captured['centre'] = get_current_centre()
            captured['patients'] = list(Patient.objects.all())
            return HttpResponse('ok')

        middleware = CurrentUserMiddleware(get_response)
        request = self.factory.get('/')
        request.user = user
        middleware(request)
        return captured

    def test_bascule_change_le_perimetre(self):
        # Deux centres autorisés, aucun centre_actif choisi -> pas d'auto-
        # sélection possible, périmètre vide (fail-closed).
        result = self._run_middleware(self.medecin)
        self.assertIsNone(result['centre'])
        self.assertEqual(result['patients'], [])

        self.medecin.profile.centre_actif = self.wale
        self.medecin.profile.save()
        result = self._run_middleware(self.medecin)
        self.assertEqual(result['centre'], self.wale)
        self.assertEqual(result['patients'], [self.patient_wale])

        self.medecin.profile.centre_actif = self.toumbokro
        self.medecin.profile.save()
        result = self._run_middleware(self.medecin)
        self.assertEqual(result['centre'], self.toumbokro)
        self.assertEqual(result['patients'], [self.patient_toumbokro])

    def test_changer_centre_verifie_lacces_et_bascule(self):
        self.medecin.profile.centre_actif = self.wale
        self.medecin.profile.save()
        autre_centre = Centre.objects.create(nom='Autre centre', code='AUTRE-TEST')

        request = self.factory.post(f'/centres/changer/{autre_centre.pk}/', HTTP_REFERER='/dashboard/')
        request.user = self.medecin
        with self.assertRaises(PermissionDenied):
            changer_centre(request, autre_centre.pk)

        request2 = self.factory.post(f'/centres/changer/{self.toumbokro.pk}/', HTTP_REFERER='/dashboard/')
        request2.user = self.medecin
        response = changer_centre(request2, self.toumbokro.pk)
        self.assertEqual(response.status_code, 302)
        self.medecin.profile.refresh_from_db()
        self.assertEqual(self.medecin.profile.centre_actif, self.toumbokro)

    def test_mono_centre_est_auto_selectionne(self):
        infirmier = User.objects.create_user('inf.wale', password='xxx')
        infirmier.profile.centres.set([self.wale])
        infirmier.profile.save()

        result = self._run_middleware(infirmier)
        self.assertEqual(result['centre'], self.wale)
        infirmier.profile.refresh_from_db()
        self.assertEqual(infirmier.profile.centre_actif, self.wale)
