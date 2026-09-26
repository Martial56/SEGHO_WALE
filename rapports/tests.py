"""Tests de la fiche mensuelle de consultations gynécologiques.

Le point sensible est la provenance du « Nombre de consultant » : il se lit sur
le type de consultation du rendez-vous, saisi à la prise du rendez-vous, et non
sur l'onglet Curatif, rempli plus tard — quand il l'est.
"""
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from patients.models import Patient, RegistreCuratif, RendezVous
from services.models import Articleservice

from .gynecologie import calculer_rapport_gynecologie


# ─── Helpers de création ───────────────────────────────────────────────────────

def _article(reference, nom=None):
    return Articleservice.objects.create(
        nom=nom or f'Consultation {reference}',
        reference_interne=reference,
        type_article='prestation',
    )


def _patient(naissance='1990-06-01', sexe='F', suffix=''):
    return Patient.objects.create(
        nom=f'Test{suffix}', prenoms='Patient',
        date_naissance=naissance, sexe=sexe,
        telephone='0700000000',
    )


def _rdv(article, patient=None, jour=15, mois=8, annee=2026, statut='confirme'):
    naive = datetime(annee, mois, jour, 9, 0)
    return RendezVous.objects.create(
        patient=patient or _patient(),
        date_heure=timezone.make_aware(naive),
        type_consultation=article,
        statut=statut,
    )


def _curatif(rdv, **donnees):
    return RegistreCuratif.objects.create(rdv=rdv, donnees=donnees)


def _totaux(annee=2026, mois=8):
    rapport = calculer_rapport_gynecologie(annee, mois)
    return {cle: valeur['total'] for cle, valeur in rapport['activites'].items()}


# ─── Provenance du Nombre de consultant ────────────────────────────────────────

class TestNombreDeConsultant(TestCase):

    def setUp(self):
        self.simple = _article('CS_CSGS', 'Consultation gynécologique simple')
        self.obstetrique = _article('CS_GYNOBS', 'Consultation gynéco-obstétrique')

    def test_les_deux_types_gyneco_font_le_consultant(self):
        _rdv(self.simple)
        _rdv(self.obstetrique)
        self.assertEqual(_totaux()['consultant'], {'F': 2, 'M': 0})

    def test_un_autre_type_de_consultation_ne_compte_pas(self):
        _rdv(_article('CS_CSCARDIO', 'Consultation cardiologique'))
        self.assertEqual(_totaux()['consultant'], {'F': 0, 'M': 0})

    def test_un_rendez_vous_sans_type_de_consultation_ne_compte_pas(self):
        _rdv(None)
        self.assertEqual(_totaux()['consultant'], {'F': 0, 'M': 0})

    def test_le_consultant_compte_meme_sans_onglet_curatif(self):
        """La régression d'origine : aucun registre curatif, donc fiche vide."""
        _rdv(self.simple)
        self.assertFalse(RegistreCuratif.objects.exists())
        self.assertEqual(_totaux()['consultant'], {'F': 1, 'M': 0})

    def test_le_curatif_seul_ne_fait_plus_un_consultant(self):
        """L'ancienne source ne doit plus alimenter la case."""
        rdv = _rdv(_article('CS_CSCARDIO', 'Consultation cardiologique'))
        _curatif(rdv, cur_type_visite='consultant')
        self.assertEqual(_totaux()['consultant'], {'F': 0, 'M': 0})

    def test_le_mois_voisin_est_exclu(self):
        _rdv(self.simple, jour=31, mois=7)
        _rdv(self.simple, jour=1, mois=9)
        self.assertEqual(_totaux(mois=8)['consultant'], {'F': 0, 'M': 0})

    def test_les_bornes_du_mois_sont_incluses(self):
        _rdv(self.simple, jour=1, mois=8)
        _rdv(self.simple, jour=31, mois=8)
        self.assertEqual(_totaux(mois=8)['consultant'], {'F': 2, 'M': 0})


# ─── Ventilation par sexe et par tranche d'âge ─────────────────────────────────

class TestVentilationDuConsultant(TestCase):

    def setUp(self):
        self.simple = _article('CS_CSGS', 'Consultation gynécologique simple')

    def _cellules(self):
        rapport = calculer_rapport_gynecologie(2026, 8)
        return dict(zip(rapport['age_brackets'], rapport['activites']['consultant']['cells']))

    def test_l_age_est_celui_du_jour_du_rendez_vous(self):
        """Née en 1976, elle a 49 ans au rendez-vous et 50 ans deux mois après :
        c'est la tranche du jour du rendez-vous qui compte, pas celle d'aujourd'hui."""
        _rdv(self.simple, patient=_patient(naissance='1976-10-20'), jour=15, mois=8)
        cellules = self._cellules()
        self.assertEqual(cellules['25-49 ans'], {'F': 1, 'M': 0})
        self.assertEqual(cellules['50 et plus'], {'F': 0, 'M': 0})

    def test_le_nourrisson_va_dans_la_premiere_tranche(self):
        _rdv(self.simple, patient=_patient(naissance='2026-03-01'))
        self.assertEqual(self._cellules()['0-11 mois'], {'F': 1, 'M': 0})

    def test_le_sexe_du_patient_choisit_la_colonne(self):
        _rdv(self.simple, patient=_patient(sexe='M', suffix='M'))
        _rdv(self.simple, patient=_patient(sexe='F', suffix='F'))
        self.assertEqual(_totaux()['consultant'], {'F': 1, 'M': 1})


# ─── Cohérence avec la ligne Nombre de consultations ───────────────────────────

class TestNombreDeConsultations(TestCase):

    def setUp(self):
        self.simple = _article('CS_CSGS', 'Consultation gynécologique simple')

    def test_les_consultations_reprennent_les_consultants(self):
        _rdv(self.simple)
        totaux = _totaux()
        self.assertEqual(totaux['consultations'], totaux['consultant'])

    def test_un_controle_s_ajoute_sans_toucher_le_consultant(self):
        rdv = _rdv(_article('CS_CSCARDIO', 'Consultation cardiologique'))
        rdv.departement = _departement_gyneco()
        rdv.save()
        _curatif(rdv, cur_type_visite='controle')
        totaux = _totaux()
        self.assertEqual(totaux['consultant'], {'F': 0, 'M': 0})
        self.assertEqual(totaux['consultations'], {'F': 1, 'M': 0})

    def test_un_consultant_aussi_marque_controle_n_est_compte_qu_une_fois(self):
        rdv = _rdv(self.simple)
        rdv.departement = _departement_gyneco()
        rdv.save()
        _curatif(rdv, cur_type_visite='controle')
        totaux = _totaux()
        self.assertEqual(totaux['consultant'], {'F': 1, 'M': 0})
        self.assertEqual(totaux['consultations'], {'F': 1, 'M': 0})

    def test_les_consultations_ne_sont_jamais_sous_les_consultants(self):
        _rdv(self.simple)
        _rdv(self.simple)
        totaux = _totaux()
        for sexe in ('F', 'M'):
            self.assertGreaterEqual(totaux['consultations'][sexe], totaux['consultant'][sexe])


def _departement_gyneco():
    from medecins.models import Departement
    dept, _ = Departement.objects.get_or_create(code='GYN', defaults={'nom': 'Gynécologie'})
    return dept


# ─── Nom du mois dans l'en-tête des fiches ─────────────────────────────────────

class TestNomDuMois(TestCase):
    """Les fiches sortaient « August 2026 » : `calendar.month_name` lit la locale
    du système, pas celle de Django."""

    def test_les_mois_sont_en_francais(self):
        from .periode import nom_du_mois
        self.assertEqual(nom_du_mois(2026, 1), 'Janvier')
        self.assertEqual(nom_du_mois(2026, 8), 'Août')
        self.assertEqual(nom_du_mois(2026, 12), 'Décembre')

    def test_les_quatre_fiches_titrent_en_francais(self):
        from .gynecologie import calculer_rapport_gynecologie
        from .maternite import calculer_rapport_maternite
        from .med_generale import calculer_rapport_med_generale
        from .soins import calculer_rapport_soins
        for calcul in (calculer_rapport_gynecologie, calculer_rapport_maternite,
                       calculer_rapport_med_generale, calculer_rapport_soins):
            with self.subTest(rapport=calcul.__name__):
                self.assertEqual(calcul(2026, 8)['mois_nom'], 'Août')
