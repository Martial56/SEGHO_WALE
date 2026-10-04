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


# ─── Disposition de la fiche de médecine générale ──────────────────────────────

class TestDispositionMedGenerale(TestCase):
    """La fiche reprend la disposition papier ; une pathologie ajoutée au
    catalogue vient après la dernière ligne de sa catégorie."""

    def setUp(self):
        from medecins.models import Departement
        from patients.models import Pathologie
        self.Pathologie = Pathologie
        self.dept, _ = Departement.objects.get_or_create(code='medg', defaults={'nom': 'Médecine Générale'})

    def _patho(self, nom, categorie):
        return self.Pathologie.objects.create(nom=nom, categorie=categorie, departement=self.dept)

    def _rapport(self):
        from .med_generale import calculer_rapport_med_generale
        return calculer_rapport_med_generale(2026, 8)

    def test_les_lignes_de_la_fiche_restent_dans_leur_ordre(self):
        self._patho('Zona', 'infectieuse')
        self._patho('Angine (IRA haute)', 'infectieuse')
        labels = [l['label'] for l in self._rapport()['a_page2']]
        self.assertLess(labels.index('Angine (IRA haute)'), labels.index('Zona'))
        self.assertEqual(labels[0], 'Broncho-pneumonie (IRA basse)')

    def test_une_nouvelle_pathologie_suit_la_derniere_ligne_de_sa_categorie(self):
        self._patho('Mpox', 'infectieuse')
        self._patho('Lupus', 'non_infectieuse')
        self._patho('Syphilis', 'ist')
        rapport = self._rapport()
        self.assertEqual([l['label'] for l in rapport['a_page3'][-2:]],
                         ["Nombre d'enfants de moins de 5 ans atteints de la diarrhée et ayant reçu une prescription de SRO + Zinc",
                          'Mpox'])
        self.assertEqual([l['label'] for l in rapport['b_page4'][-2:]],
                         ['Autres Maladies non infectieuses', 'Lupus'])
        self.assertEqual(rapport['ist'][-1]['label'], 'Syphilis')

    def test_les_doublons_du_catalogue_alimentent_la_meme_ligne(self):
        p1 = self._patho('Cas de Paludisme simple', 'infectieuse')
        p2 = self._patho('Cas dePaludisme simple', 'infectieuse')
        patient = _patient(naissance='1990-01-01', sexe='M')
        for p in (p1, p2):
            rdv = _rdv(None, patient=patient)
            rdv.departement = self.dept
            rdv.save()
            _curatif(rdv, cur_diagnostic=[str(p.pk)])
        rapport = self._rapport()
        ligne = next(l for l in rapport['a_page1'] if l['label'] == 'Cas de paludisme simple')
        # Cellules : (0-11 mois, F), (0-11 mois, M), (1-4 ans, F)… ; 25-49 ans M = 14e.
        self.assertEqual(ligne['cellules'][13]['val'], 2)
        # Puis Total F/M (cellules 17 et 18), avant les Cas référés.
        self.assertEqual([c['val'] for c in ligne['cellules'][16:18]], [0, 2])
        self.assertNotIn('Cas dePaludisme simple', [l['label'] for l in rapport['a_page3']])


# ─── Disposition de la fiche de gynécologie ────────────────────────────────────

class TestDispositionGynecologie(TestCase):
    """La fiche reprend la disposition papier ; une pathologie ajoutée au
    catalogue vient après la dernière ligne de sa catégorie."""

    def setUp(self):
        from patients.models import Pathologie
        self.Pathologie = Pathologie
        self.dept = _departement_gyneco()

    def _patho(self, nom, categorie):
        return self.Pathologie.objects.create(nom=nom, categorie=categorie, departement=self.dept)

    def test_les_lignes_de_la_fiche_restent_dans_leur_ordre(self):
        self._patho('Violence sexuelle', 'autre_gyneco')
        self._patho('Prolapsus génitaux', 'autre_gyneco')
        rapport = calculer_rapport_gynecologie(2026, 8)
        labels = [l['label'] for l in rapport['autre_page3']]
        self.assertEqual(labels[0], "Tumeurs bénignes de l'utérus")
        self.assertLess(labels.index('Prolapsus génitaux'), labels.index('Violence sexuelle'))
        self.assertEqual([l['label'] for l in rapport['grossesse_page2']],
                         ['Grossesse gemellaire', "Complication de l'allaitement", 'Autres maladies infectieuses'])
        self.assertTrue(rapport['grossesse_ligne_vierge'])

    def test_une_nouvelle_pathologie_suit_la_derniere_ligne_de_sa_categorie(self):
        self._patho('Métrorragies', 'grossesse')
        self._patho('Vaginose', 'infectieuse')
        self._patho("Désir d'IVG", 'autre_gyneco')
        rapport = calculer_rapport_gynecologie(2026, 8)
        # « Autres maladies infectieuses » reste la dernière ligne du tableau A.
        self.assertEqual([l['label'] for l in rapport['grossesse_page2'][-3:]],
                         ["Complication de l'allaitement", 'Métrorragies', 'Autres maladies infectieuses'])
        self.assertFalse(rapport['grossesse_ligne_vierge'])
        self.assertEqual([l['label'] for l in rapport['infectieuse'][-2:]], ['Condylomes', 'Vaginose'])
        self.assertEqual([l['label'] for l in rapport['autre_page3'][-2:]], ['Violence sexuelle', "Désir d'IVG"])

    def test_une_variante_de_nom_alimente_la_ligne_de_la_fiche(self):
        patho = self._patho('Fibrome utérien', 'autre_gyneco')
        rdv = _rdv(_article('CS_CSGS'), patient=_patient(naissance='1990-01-01'))
        rdv.departement = self.dept
        rdv.save()
        _curatif(rdv, cur_diagnostic=[str(patho.pk)])
        rapport = calculer_rapport_gynecologie(2026, 8)
        ligne = next(l for l in rapport['autre_page3'] if l['label'] == 'Fibrome utérin')
        # 25-49 ans F = 13e cellule, puis Total F/M (17e et 18e).
        self.assertEqual(ligne['cellules'][12]['val'], 1)
        self.assertEqual([c['val'] for c in ligne['cellules'][16:18]], [1, 0])
        self.assertNotIn('Fibrome utérien', [l['label'] for l in rapport['autre_page3']])
