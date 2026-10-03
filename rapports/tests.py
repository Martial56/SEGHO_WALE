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


# ─── Fiche d'activité de soins : la ligne PERFUSION ───────────────────────────

class TestPerfusionCompteLesDeuxSources(TestCase):
    """Un soin posé pendant une mise en observation compte, quel que soit le
    chemin de saisie emprunté.

    L'application en offre deux — le bouton « Ajouter un soin », qui écrit
    `source='soin'`, et l'onglet des visites infirmières, qui écrit
    `source='visite_infirmiere'` — et la fiche ne lisait que le premier. Or il
    n'avait jamais servi une seule fois : la ligne valait zéro depuis toujours,
    pendant que de vrais soins facturés passaient par le second.
    """

    def setUp(self):
        from facturation.models import Facture
        from hospitalisation.models import Hospitalisation, ServiceAFacturer

        self.Facture = Facture
        self.ServiceAFacturer = ServiceAFacturer
        self.patient = Patient.objects.create(
            nom='Perf', prenoms='Patient', date_naissance='1990-06-01',
            sexe='F', telephone='0700000000')
        self.article = Articleservice.objects.create(
            nom='NEBULISATION DE TEST', prix_vente=2000, actif=True)
        self.hosp = Hospitalisation.objects.create(
            patient=self.patient,
            date_admission=timezone.make_aware(datetime(2026, 10, 8, 9, 0)),
            statut='hospitalise')

    def _soin(self, source, statut_facture='payee'):
        facture = self.Facture.objects.create(
            patient=self.patient, type_facture='hospitalisation',
            statut=statut_facture, montant_total=2000)
        return self.ServiceAFacturer.objects.create(
            hospitalisation=self.hosp, service=self.article,
            source=source, facture=facture)

    def _perfusion(self):
        from .soins import calculer_rapport_soins
        lignes = calculer_rapport_soins(2026, 10)['lignes_soins']
        # La ligne PERFUSION est la première de la colonne de gauche.
        return lignes[0][0]['nombre']

    def test_un_soin_apporte_compte(self):
        self._soin('soin')
        self.assertEqual(self._perfusion(), 1)

    def test_une_visite_infirmiere_compte_aussi(self):
        """C'est le cas qui ne comptait pas, et c'est le seul qu'on utilise."""
        self._soin('visite_infirmiere')
        self.assertEqual(self._perfusion(), 1)

    def test_une_mo_a_deux_soins_ne_compte_qu_une_fois(self):
        self._soin('soin')
        self._soin('visite_infirmiere')
        self.assertEqual(self._perfusion(), 1)

    def test_une_facture_impayee_ne_compte_pas(self):
        self._soin('visite_infirmiere', statut_facture='emise')
        self.assertEqual(self._perfusion(), 0)

    def test_la_mise_en_observation_seule_ne_compte_pas(self):
        """`meo` est la prestation d'observation elle-même, pas un soin."""
        self._soin('meo')
        self.assertEqual(self._perfusion(), 0)

    def test_une_visite_docteur_ne_compte_pas(self):
        """Seules les deux origines retenues comptent, pas toute ligne facturée."""
        self._soin('visite_docteur')
        self.assertEqual(self._perfusion(), 0)

    def test_un_soin_paye_et_un_impaye_sur_la_meme_mo_comptent_une_fois(self):
        """Les deux conditions doivent porter sur la **même** ligne liée : en
        deux `filter`, une MO passerait avec un soin non facturé d'un côté et
        une tout autre ligne payée de l'autre."""
        self._soin('meo')                                   # payé, mais pas un soin
        self._soin('visite_infirmiere', statut_facture='emise')
        self.assertEqual(self._perfusion(), 0)

    def test_une_mo_d_un_autre_mois_ne_compte_pas(self):
        self.hosp.date_admission = timezone.make_aware(datetime(2026, 9, 8, 9, 0))
        self.hosp.save(update_fields=['date_admission'])
        self._soin('visite_infirmiere')
        self.assertEqual(self._perfusion(), 0)


class TestMiseEnObservationSimple(TestCase):
    """« Simple » veut dire : aucun soin n'a été posé pendant l'observation.

    La ligne visait l'article « MISE EN OBSERVATION (VENTE) », qui n'a jamais
    servi — les mises en observation réelles portent « MISE EN OBSERVATION ».
    Elle affichait donc zéro quoi qu'il arrive. Elle compte désormais les MO
    elles-mêmes, moins celles qui ont reçu un soin : c'est le complément exact
    de la ligne PERFUSION.
    """

    def setUp(self):
        from facturation.models import Facture
        from hospitalisation.models import Hospitalisation, ServiceAFacturer

        self.Facture = Facture
        self.Hospitalisation = Hospitalisation
        self.ServiceAFacturer = ServiceAFacturer
        self.patient = Patient.objects.create(
            nom='Simple', prenoms='Patient', date_naissance='1990-06-01',
            sexe='F', telephone='0700000000')
        self.article = Articleservice.objects.create(
            nom='MISE EN OBSERVATION DE TEST', prix_vente=5000, actif=True)

    def _mo(self, payee=True):
        """Une MO avec sa facture d'observation, comme en produit l'application."""
        hosp = self.Hospitalisation.objects.create(
            patient=self.patient,
            date_admission=timezone.make_aware(datetime(2026, 10, 8, 9, 0)),
            statut='hospitalise')
        facture = self.Facture.objects.create(
            patient=self.patient, hospitalisation=hosp,
            type_facture='hospitalisation',
            statut='payee' if payee else 'emise', montant_total=5000)
        self.ServiceAFacturer.objects.create(
            hospitalisation=hosp, service=self.article, source='meo', facture=facture)
        return hosp, facture

    def _ajouter_soin(self, hosp, facture, source='visite_infirmiere'):
        return self.ServiceAFacturer.objects.create(
            hospitalisation=hosp, service=self.article, source=source, facture=facture)

    def _ligne(self, label):
        from .soins import calculer_rapport_soins
        gauche = [g for g, _ in calculer_rapport_soins(2026, 10)['lignes_soins'] if g]
        return next(x['nombre'] for x in gauche if x['label'] == label)

    def _simple(self):
        return self._ligne('Mise en Observation simple')

    def test_une_mo_payee_sans_soin_compte(self):
        self._mo()
        self.assertEqual(self._simple(), 1)

    def test_une_mo_avec_une_visite_infirmiere_ne_compte_pas(self):
        hosp, facture = self._mo()
        self._ajouter_soin(hosp, facture)
        self.assertEqual(self._simple(), 0)

    def test_une_mo_avec_un_soin_apporte_ne_compte_pas(self):
        hosp, facture = self._mo()
        self._ajouter_soin(hosp, facture, source='soin')
        self.assertEqual(self._simple(), 0)

    def test_la_prestation_d_observation_elle_meme_n_est_pas_un_soin(self):
        """Sinon aucune MO ne serait jamais « simple » : elles portent toutes
        une ligne `meo`."""
        self._mo()
        self.assertEqual(self._simple(), 1)

    def test_une_mo_non_payee_ne_compte_pas(self):
        self._mo(payee=False)
        self.assertEqual(self._simple(), 0)

    def test_une_mo_d_un_autre_mois_ne_compte_pas(self):
        hosp, _ = self._mo()
        hosp.date_admission = timezone.make_aware(datetime(2026, 9, 8, 9, 0))
        hosp.save(update_fields=['date_admission'])
        self.assertEqual(self._simple(), 0)

    def test_les_deux_lignes_se_partagent_les_mo(self):
        """PERFUSION et « simple » doivent couvrir toutes les MO payées, sans
        qu'aucune tombe dans les deux ni dans aucune."""
        self._mo()                                   # sans soin
        self._mo()                                   # sans soin
        hosp, facture = self._mo()
        self._ajouter_soin(hosp, facture)            # avec soin
        self.assertEqual(self._simple(), 2)
        self.assertEqual(self._ligne('PERFUSION'), 1)

    def test_l_ancien_article_vente_ne_sert_plus(self):
        """Il existe au catalogue mais n'a jamais servi : s'appuyer dessus
        condamnait la ligne à zéro."""
        from .soins import SOINS
        self.assertNotIn(
            'MISE EN OBSERVATION (VENTE)',
            [n for _, noms in SOINS if isinstance(noms, list) for n in noms])
