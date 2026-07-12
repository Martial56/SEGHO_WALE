from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from medecins.models import Medecin, Specialite
from patients.models import Patient, RendezVous

from .models import Consultation, Constante, Ordonnance


# ─── Helpers de création ───────────────────────────────────────────────────────

def _specialite():
    s, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
    return s


def _patient(suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance='1990-06-01', sexe='M',
        telephone='0700000000',
    )


def _medecin(suffix=''):
    from employer.models import Employe
    employe = Employe.objects.create(
        nom='Docteur', prenoms=f'Test{suffix}',
        telephone='0700000001', date_embauche='2020-01-01',
    )
    return Medecin.objects.create(employe=employe, specialite=_specialite())


def _rdv(patient=None, statut='en_attente'):
    return RendezVous.objects.create(
        patient=patient or _patient(),
        date_heure=timezone.now(),
        statut=statut,
    )


def _consultation(patient=None, medecin=None, rendez_vous=None, statut='en_cours'):
    return Consultation.objects.create(
        patient=patient or _patient(),
        medecin=medecin or _medecin(),
        rendez_vous=rendez_vous,
        motif='Motif de test',
        statut=statut,
    )


# ─── Tests génération de numéros uniques ───────────────────────────────────────

class TestNumerosUniques(TestCase):

    def setUp(self):
        self.patient = _patient('A')
        self.medecin = _medecin('A')

    def test_deux_consultations_numeros_distincts(self):
        c1 = _consultation(self.patient, self.medecin)
        c2 = _consultation(self.patient, self.medecin)
        self.assertNotEqual(c1.numero, c2.numero)

    def test_format_numero_consultation(self):
        c = _consultation(self.patient, self.medecin)
        annee = timezone.now().year
        prefix = f'CONS{annee}'
        self.assertTrue(c.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{c.numero}'")
        suffixe = c.numero[len(prefix):]
        self.assertEqual(len(suffixe), 6, "Le suffixe doit être sur 6 chiffres")
        self.assertTrue(suffixe.isdigit(), "Le suffixe doit être numérique")

    def test_deux_ordonnances_numeros_distincts(self):
        o1 = Ordonnance.objects.create(patient=self.patient)
        o2 = Ordonnance.objects.create(patient=self.patient)
        self.assertNotEqual(o1.numero, o2.numero)

    def test_format_numero_ordonnance(self):
        o = Ordonnance.objects.create(patient=self.patient)
        annee = timezone.now().year
        prefix = f'ORD{annee}'
        self.assertTrue(o.numero.startswith(prefix),
                        f"Attendu préfixe '{prefix}', obtenu '{o.numero}'")
        suffixe = o.numero[len(prefix):]
        self.assertEqual(len(suffixe), 6, "Le suffixe doit être sur 6 chiffres")
        self.assertTrue(suffixe.isdigit())


# ─── Tests Constante.imc ────────────────────────────────────────────────────────

class TestConstanteImc(TestCase):

    def setUp(self):
        self.consultation = _consultation()

    def test_imc_calcule_correctement(self):
        constante = Constante.objects.create(
            consultation=self.consultation,
            poids=Decimal('70'), taille=Decimal('1.75'),
        )
        self.assertEqual(constante.imc, round(70 / 1.75 ** 2, 2))

    def test_imc_none_sans_poids(self):
        constante = Constante.objects.create(
            consultation=self.consultation, taille=Decimal('1.75'),
        )
        self.assertIsNone(constante.imc)

    def test_imc_none_sans_taille(self):
        constante = Constante.objects.create(
            consultation=self.consultation, poids=Decimal('70'),
        )
        self.assertIsNone(constante.imc)

    def test_imc_none_si_taille_zero(self):
        constante = Constante.objects.create(
            consultation=self.consultation, poids=Decimal('70'), taille=Decimal('0'),
        )
        self.assertIsNone(constante.imc)


# ─── Tests du signal sync_rdv_statut ────────────────────────────────────────────

class TestSignalSyncRdvStatut(TestCase):

    def setUp(self):
        self.patient = _patient('B')
        self.medecin = _medecin('B')

    def test_creation_avec_rdv_en_attente_passe_en_consultation(self):
        rdv = _rdv(self.patient, statut='en_attente')
        _consultation(self.patient, self.medecin, rendez_vous=rdv)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'en_consultation',
                         "Le RDV en_attente doit passer en_consultation à la création")

    def test_creation_avec_rdv_deja_confirme_ne_change_rien(self):
        rdv = _rdv(self.patient, statut='confirme')
        _consultation(self.patient, self.medecin, rendez_vous=rdv)
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'confirme',
                         "Un RDV déjà confirmé ne doit pas être modifié à la création")

    def test_consultation_terminee_termine_le_rdv(self):
        rdv = _rdv(self.patient, statut='en_consultation')
        consultation = _consultation(self.patient, self.medecin, rendez_vous=rdv, statut='en_cours')
        consultation.statut = 'termine'
        consultation.save()
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'termine')

    def test_consultation_annulee_annule_le_rdv(self):
        rdv = _rdv(self.patient, statut='en_consultation')
        consultation = _consultation(self.patient, self.medecin, rendez_vous=rdv, statut='en_cours')
        consultation.statut = 'annule'
        consultation.save()
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'annule')

    def test_ne_downgrade_pas_un_rdv_deja_terminal(self):
        rdv = _rdv(self.patient, statut='termine')
        consultation = _consultation(self.patient, self.medecin, rendez_vous=rdv, statut='en_cours')
        consultation.statut = 'annule'
        consultation.save()
        rdv.refresh_from_db()
        self.assertEqual(rdv.statut, 'termine',
                         "Un RDV déjà dans un statut terminal ne doit pas être écrasé")

    def test_consultation_sans_rendez_vous_ne_leve_pas_erreur(self):
        try:
            consultation = _consultation(self.patient, self.medecin, rendez_vous=None)
            consultation.statut = 'termine'
            consultation.save()
        except Exception as e:
            self.fail(f"Une consultation sans rendez-vous ne devrait pas lever d'erreur : {e}")
