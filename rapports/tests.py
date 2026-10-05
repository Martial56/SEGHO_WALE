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

def _nombre_de_la_ligne(libelle, annee=2026, mois=10, configuration=None):
    """Le nombre affiché par une ligne de la fiche, désignée par son libellé.

    Les lignes ne sont plus deux listes côte à côte mais des blocs : on les
    traverse tous plutôt que de viser une position, qui ne veut plus rien dire
    dès qu'on en intercale une.
    """
    from .soins import calculer_rapport_soins
    rapport = calculer_rapport_soins(annee, mois, configuration=configuration)
    for bloc in rapport['blocs']:
        for ligne in bloc['lignes']:
            if ligne['libelle'] == libelle:
                return ligne['valeurs'][0]
    raise AssertionError(f"aucune ligne « {libelle} » dans la fiche")



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
        return _nombre_de_la_ligne('PERFUSION')

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
        return _nombre_de_la_ligne(label)

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
        condamnait la ligne à zéro. On le vérifie maintenant sur le format
        officiel semé en base, puisque c'est lui qui porte la composition."""
        from .models import ConfigurationFicheSoins
        noms = {a.nom
                for bloc in ConfigurationFicheSoins.officielle().blocs.all()
                for ligne in bloc.lignes.all()
                for a in ligne.articles.all()}
        self.assertNotIn('MISE EN OBSERVATION (VENTE)', noms)


class TestLaFicheSeLitDepuisLaConfiguration(TestCase):
    """La composition des deux colonnes de soins a quitté le code pour la base.

    Elle vivait dans deux constantes qui désignaient les prestations **par leur
    nom**. Deux pannes en sont nées, et toutes deux ont mis des mois à se voir :
    une ligne qui visait un article jamais utilisé affichait zéro pour
    l'éternité, et un soin posé pendant une mise en observation n'était compté
    nulle part. Les prestations sont désormais désignées par clé étrangère, et
    chaque ligne dit où chercher.
    """

    def setUp(self):
        from facturation.models import Facture
        from hospitalisation.models import Hospitalisation, ServiceAFacturer
        from .models import (BlocFicheSoins, ColonneFicheSoins,
                             ConfigurationFicheSoins, LigneFicheSoins)

        self.Facture = Facture
        self.Hospitalisation = Hospitalisation
        self.ServiceAFacturer = ServiceAFacturer
        self.Configuration = ConfigurationFicheSoins
        self.Bloc = BlocFicheSoins
        self.Colonne = ColonneFicheSoins
        self.Ligne = LigneFicheSoins

        self.patient = Patient.objects.create(
            nom='Config', prenoms='Patient', date_naissance='1990-06-01',
            sexe='F', telephone='0700000000')
        self.article = Articleservice.objects.create(
            nom='PRESTATION DE TEST', prix_vente=2000, actif=True)

    # ── fabrication d'une configuration minimale ────────────────────────────

    def _configuration(self, *blocs):
        """`blocs` : des couples (titre, [lignes]), une ligne étant un dict
        d'attributs passés tels quels au modèle."""
        configuration = self.Configuration.objects.create(nom='Essai')
        for rang_bloc, (titre, lignes) in enumerate(blocs):
            bloc = self.Bloc.objects.create(
                configuration=configuration, titre=titre, ordre=rang_bloc)
            self.Colonne.objects.create(bloc=bloc, titre='Nombre', ordre=0)
            for rang, attributs in enumerate(lignes):
                articles = attributs.pop('articles', [])
                ligne = self.Ligne.objects.create(
                    bloc=bloc, ordre=rang, **attributs)
                if articles:
                    ligne.articles.set(articles)
        return configuration

    def _rapport(self, configuration):
        from .soins import calculer_rapport_soins
        return calculer_rapport_soins(2026, 10, configuration=configuration)

    def _valeur(self, configuration, libelle):
        return _nombre_de_la_ligne(libelle, configuration=configuration)

    # ── données ─────────────────────────────────────────────────────────────

    def _procedure(self, article=None, statut_facture='payee'):
        from soins.models import ProcedureSoin
        facture = self.Facture.objects.create(
            patient=self.patient, type_facture='soins',
            statut=statut_facture, montant_total=2000)
        return ProcedureSoin.objects.create(
            patient=self.patient, soin_type=article or self.article,
            facture=facture, prix=2000,
            date=timezone.make_aware(datetime(2026, 10, 8, 9, 0)))

    def _service_en_observation(self, article=None, statut_facture='payee'):
        hosp = self.Hospitalisation.objects.create(
            patient=self.patient,
            date_admission=timezone.make_aware(datetime(2026, 10, 8, 9, 0)),
            statut='hospitalise')
        facture = self.Facture.objects.create(
            patient=self.patient, type_facture='hospitalisation',
            statut=statut_facture, montant_total=2000)
        return self.ServiceAFacturer.objects.create(
            hospitalisation=hosp, service=article or self.article,
            source='visite_infirmiere', facture=facture,
            date=datetime(2026, 10, 8).date())

    # ── le semis ────────────────────────────────────────────────────────────

    def test_le_format_officiel_est_seme(self):
        officielle = self.Configuration.officielle()
        self.assertIsNotNone(officielle)
        blocs = list(officielle.blocs.all())
        self.assertEqual([b.titre for b in blocs],
                         ['Soins', 'Autres soins à préciser'])
        self.assertEqual([b.lignes.count() for b in blocs], [8, 7])

    def test_une_base_sans_catalogue_garde_quand_meme_ses_lignes(self):
        """Le semis accroche les prestations qu'il trouve par leur nom. Dans
        une base où le catalogue n'a pas encore été saisi — celle des tests, et
        celle d'un collègue qui démarre — il n'en trouve aucune.

        La ligne doit alors exister sans prestation et compter zéro, pas
        disparaître ni faire tomber la fiche. La différence avec l'ancien
        fonctionnement est qu'on peut désormais le **voir** et cocher la bonne
        prestation, au lieu d'un zéro que rien n'explique.
        """
        pansement = self.Configuration.officielle().blocs.get(
            titre='Soins').lignes.get(libelle='PANSEMENT')
        self.assertEqual(pansement.articles.count(), 0)
        self.assertEqual(_nombre_de_la_ligne('PANSEMENT'), 0)

    def test_sans_configuration_donnee_c_est_le_format_officiel(self):
        from .soins import calculer_rapport_soins
        rapport = calculer_rapport_soins(2026, 10)
        self.assertEqual(rapport['configuration'],
                         self.Configuration.officielle())

    # ── le renommage, qui est tout l'enjeu ──────────────────────────────────

    def test_renommer_une_prestation_ne_casse_plus_la_ligne(self):
        """Avant, la ligne visait la chaîne : la renommer la rendait muette.
        Elle vise la clé étrangère, qui survit au renommage."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Essai', 'source': 'articles',
                        'origines': 'procedure', 'articles': [self.article]}]))
        self._procedure()
        self.assertEqual(self._valeur(configuration, 'Essai'), 1)

        self.article.nom = 'TOUT AUTRE NOM'
        self.article.save(update_fields=['nom'])
        self.assertEqual(self._valeur(configuration, 'Essai'), 1)

    # ── les deux axes d'une ligne ───────────────────────────────────────────

    def test_l_origine_par_defaut_ignore_l_observation(self):
        """C'est le comportement d'avant, et il reste le défaut : une ligne
        branchée sur le module Soins ne compte pas les mises en observation."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Essai', 'source': 'articles',
                        'origines': 'procedure', 'articles': [self.article]}]))
        self._service_en_observation()
        self.assertEqual(self._valeur(configuration, 'Essai'), 0)

    def test_une_prestation_posee_en_observation_compte_si_on_le_demande(self):
        """L'axe qui manquait : c'est par là que la nébulisation d'octobre
        passait, facturée, payée, et comptée nulle part."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Essai', 'source': 'articles',
                        'origines': 'mo', 'articles': [self.article]}]))
        self._service_en_observation()
        self.assertEqual(self._valeur(configuration, 'Essai'), 1)

    def test_les_deux_origines_s_additionnent(self):
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Essai', 'source': 'articles',
                        'origines': 'les_deux', 'articles': [self.article]}]))
        self._procedure()
        self._service_en_observation()
        self.assertEqual(self._valeur(configuration, 'Essai'), 2)

    def test_une_prestation_non_payee_ne_compte_dans_aucune_origine(self):
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Essai', 'source': 'articles',
                        'origines': 'les_deux', 'articles': [self.article]}]))
        self._procedure(statut_facture='emise')
        self._service_en_observation(statut_facture='emise')
        self.assertEqual(self._valeur(configuration, 'Essai'), 0)

    # ── zéro et blanc ne sont pas la même chose ─────────────────────────────

    def test_une_ligne_sans_prestation_compte_zero(self):
        """Zéro, pas un blanc : la question a été posée, la réponse est aucune."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Vide', 'source': 'articles',
                        'origines': 'procedure'}]))
        self.assertEqual(self._valeur(configuration, 'Vide'), 0)

    def test_une_ligne_manuelle_laisse_la_case_blanche(self):
        """Et là un blanc, pas un zéro : personne n'a compté, c'est à remplir
        à la main. Afficher zéro affirmerait quelque chose de faux."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'À la main', 'source': 'manuelle'}]))
        self.assertIsNone(self._valeur(configuration, 'À la main'))

    # ── la mise en page ─────────────────────────────────────────────────────

    def test_les_blocs_s_impriment_deux_par_tableau(self):
        configuration = self._configuration(
            ('Un', [{'libelle': 'a', 'source': 'manuelle'}]),
            ('Deux', [{'libelle': 'b', 'source': 'manuelle'}]),
            ('Trois', [{'libelle': 'c', 'source': 'manuelle'}]))
        tableaux = self._rapport(configuration)['tableaux']
        self.assertEqual(len(tableaux), 2)
        self.assertEqual([e['texte'] for e in tableaux[0]['entetes']],
                         ['Un', 'Nombre', 'Deux', 'Nombre'])
        self.assertEqual([e['texte'] for e in tableaux[1]['entetes']],
                         ['Trois', 'Nombre'])

    def test_la_case_du_bloc_le_plus_court_est_absente_pas_nulle(self):
        """Les deux blocs d'origine n'ont pas le même nombre de lignes : le
        dernier rang de droite doit rester vide. Un zéro y affirmerait qu'on a
        compté quelque chose qui n'existe pas."""
        configuration = self._configuration(
            ('Long', [{'libelle': 'a', 'source': 'manuelle'},
                      {'libelle': 'b', 'source': 'manuelle'}]),
            ('Court', [{'libelle': 'c', 'source': 'manuelle'}]))
        rangees = self._rapport(configuration)['tableaux'][0]['rangees']
        premiere_a_droite = rangees[0][3]
        derniere_a_droite = rangees[1][3]
        self.assertTrue(premiere_a_droite['presente'])
        self.assertFalse(derniere_a_droite['presente'])

    # ── le texte entre parenthèses ──────────────────────────────────────────

    def test_une_ligne_a_plusieurs_prestations_les_enumere(self):
        autre = Articleservice.objects.create(
            nom='AUTRE PRESTATION', prix_vente=1000, actif=True)
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Groupée', 'source': 'articles',
                        'articles': [self.article, autre]}]))
        ligne = self._rapport(configuration)['blocs'][0]['lignes'][0]
        self.assertEqual(ligne['detail'],
                         'Autre Prestation, Prestation De Test')

    def test_une_ligne_a_une_seule_prestation_se_tait(self):
        """Répéter « Transfusion » sous « TRANSFUSION » n'apprendrait rien."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Seule', 'source': 'articles',
                        'articles': [self.article]}]))
        ligne = self._rapport(configuration)['blocs'][0]['lignes'][0]
        self.assertIsNone(ligne['detail'])

    def test_les_deux_lignes_d_observation_disent_leur_regle(self):
        """Elles ne comptent aucune prestation : leur règle ne se lit nulle
        part ailleurs que dans ce texte."""
        configuration = self._configuration(
            ('Soins', [{'libelle': 'Avec', 'source': 'mo_avec_soin'},
                       {'libelle': 'Sans', 'source': 'mo_sans_soin'}]))
        lignes = self._rapport(configuration)['blocs'][0]['lignes']
        self.assertIn('au moins un soin', lignes[0]['detail'])
        self.assertIn('sans aucun soin', lignes[1]['detail'])


class TestLEcranDeConfiguration(TestCase):
    """Régler la fiche sans toucher à celle des autres.

    Tout le dispositif tient sur une idée : un utilisateur ordinaire qui part
    du format par défaut n'en modifie pas une ligne, il en reçoit une **copie**.
    Sans cette copie, le premier réglage de n'importe qui changerait la fiche
    de tout le monde, et « revenir au format par défaut » ne renverrait nulle
    part. Les superutilisateurs, eux, ajustent bien le format par défaut : ils
    sont les seuls.
    """

    URL = '/rapports/soins/configuration/'

    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client
        from .models import ConfigurationFicheSoins

        self.User = User
        self.Configuration = ConfigurationFicheSoins
        self.officielle = ConfigurationFicheSoins.officielle()
        self.article = Articleservice.objects.create(
            nom='PRESTATION D ESSAI', prix_vente=1000, actif=True)

        self.simple = User.objects.create_user('agent_cfg', password='x')
        self.admin = User.objects.create_superuser('admin_cfg', password='x')
        self.client = Client()

    # ── outillage ───────────────────────────────────────────────────────────

    def _connecter(self, utilisateur):
        self.client.force_login(utilisateur)

    def _composition(self, *blocs):
        import json
        return json.dumps({'blocs': list(blocs)})

    def _bloc(self, titre='Soins', lignes=(), colonne='Nombre'):
        return {'titre': titre, 'colonne': colonne, 'lignes': list(lignes)}

    def _ligne(self, libelle='Essai', source='articles',
               origines='procedure', articles=None):
        return {'libelle': libelle, 'source': source, 'origines': origines,
                'articles': articles if articles is not None else []}

    def _enregistrer(self, composition):
        return self.client.post(self.URL, {'composition': composition})

    def _lignes_de(self, configuration):
        return [(bloc.titre, [l.libelle for l in bloc.lignes.all()])
                for bloc in configuration.blocs.all()]

    # ── accès ───────────────────────────────────────────────────────────────

    def test_l_ecran_demande_une_session(self):
        reponse = self.client.get(self.URL)
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('/login', reponse['Location'])

    def test_l_ecran_s_ouvre_sur_la_fiche_en_cours(self):
        self._connecter(self.simple)
        reponse = self.client.get(self.URL)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.context['configuration'], self.officielle)
        self.assertTrue(reponse.context['partira_en_copie'])

    def test_un_superutilisateur_est_prevenu_qu_il_touche_au_defaut(self):
        self._connecter(self.admin)
        reponse = self.client.get(self.URL)
        self.assertTrue(reponse.context['modifie_le_defaut'])
        self.assertFalse(reponse.context['partira_en_copie'])

    # ── la copie, qui est tout le dispositif ────────────────────────────────

    def test_enregistrer_donne_sa_propre_copie_a_un_utilisateur(self):
        self._connecter(self.simple)
        avant = self._lignes_de(self.officielle)

        reponse = self._enregistrer(self._composition(
            self._bloc('Mes soins', [self._ligne('Ma ligne')])))
        self.assertEqual(reponse.status_code, 302)

        sienne = self.Configuration.objects.get(utilisateur=self.simple)
        self.assertTrue(sienne.est_active)
        self.assertEqual(self._lignes_de(sienne), [('Mes soins', ['Ma ligne'])])
        self.assertEqual(self._lignes_de(self.officielle), avant,
                         'le format par défaut a bougé')

    def test_un_second_enregistrement_ne_recree_pas_une_copie(self):
        """Sinon chaque clic sur Enregistrer laisserait une configuration morte
        derrière lui, et `pour()` finirait par en tirer une au hasard."""
        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('Mes soins', [self._ligne('Une')])))
        self._enregistrer(self._composition(
            self._bloc('Mes soins', [self._ligne('Deux')])))

        siennes = self.Configuration.objects.filter(utilisateur=self.simple)
        self.assertEqual(siennes.count(), 1)
        self.assertEqual(self._lignes_de(siennes.first()),
                         [('Mes soins', ['Deux'])])

    def test_un_superutilisateur_modifie_le_format_par_defaut(self):
        self._connecter(self.admin)
        self._enregistrer(self._composition(
            self._bloc('Soins', [self._ligne('Ligne officielle')])))

        self.officielle.refresh_from_db()
        self.assertEqual(self._lignes_de(self.officielle),
                         [('Soins', ['Ligne officielle'])])
        self.assertFalse(
            self.Configuration.objects.filter(utilisateur=self.admin).exists())

    def test_la_fiche_d_un_utilisateur_ne_regarde_pas_celle_d_un_autre(self):
        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('À moi', [self._ligne('Ma ligne')])))

        autre = self.User.objects.create_user('autre_cfg', password='x')
        self.assertEqual(self.Configuration.pour(autre), self.officielle)

    # ── revenir au format par défaut ────────────────────────────────────────

    def test_revenir_au_defaut_abandonne_sa_fiche(self):
        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('À moi', [self._ligne('Ma ligne')])))
        self.assertTrue(
            self.Configuration.objects.filter(utilisateur=self.simple).exists())

        reponse = self.client.post(self.URL, {'action': 'defaut'})
        self.assertEqual(reponse.status_code, 302)
        self.assertFalse(
            self.Configuration.objects.filter(utilisateur=self.simple).exists())
        self.assertEqual(self.Configuration.pour(self.simple), self.officielle)

    def test_revenir_au_defaut_ne_touche_pas_au_defaut(self):
        """C'est une renonciation, pas une remise à zéro : ce que les
        superutilisateurs ont ajusté reste."""
        self._connecter(self.admin)
        self._enregistrer(self._composition(
            self._bloc('Soins', [self._ligne('Ajustée par un admin')])))

        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('À moi', [self._ligne('Ma ligne')])))
        self.client.post(self.URL, {'action': 'defaut'})

        self.assertEqual(self._lignes_de(self.Configuration.officielle()),
                         [('Soins', ['Ajustée par un admin'])])

    # ── composer ────────────────────────────────────────────────────────────

    def test_l_ordre_des_lignes_est_celui_de_l_envoi(self):
        """Intercaler une ligne, c'est la poser où l'on veut dans la liste :
        l'écran ne transporte aucun numéro de rang, c'est la position qui fait
        foi."""
        self._connecter(self.admin)
        self._enregistrer(self._composition(self._bloc('Soins', [
            self._ligne('Première'), self._ligne('Intercalée'),
            self._ligne('Dernière')])))
        bloc = self.Configuration.officielle().blocs.first()
        self.assertEqual([(l.ordre, l.libelle) for l in bloc.lignes.all()],
                         [(0, 'Première'), (1, 'Intercalée'), (2, 'Dernière')])

    def test_on_peut_ajouter_un_bloc(self):
        self._connecter(self.admin)
        self._enregistrer(self._composition(
            self._bloc('Soins', [self._ligne('a')]),
            self._bloc('Autres soins à préciser', [self._ligne('b')]),
            self._bloc('Mon bloc', [self._ligne('c')])))
        self.assertEqual(
            [t for t, _ in self._lignes_de(self.Configuration.officielle())],
            ['Soins', 'Autres soins à préciser', 'Mon bloc'])

    def test_le_titre_de_la_colonne_se_change(self):
        self._connecter(self.admin)
        self._enregistrer(self._composition(
            self._bloc('Soins', [self._ligne('a')], colonne='Effectif')))
        bloc = self.Configuration.officielle().blocs.first()
        self.assertEqual(bloc.colonnes.first().titre, 'Effectif')

    def test_les_prestations_cochees_sont_enregistrees(self):
        self._connecter(self.admin)
        self._enregistrer(self._composition(self._bloc('Soins', [
            self._ligne('Groupée', articles=[self.article.pk])])))
        ligne = self.Configuration.officielle().blocs.first().lignes.first()
        self.assertEqual([a.pk for a in ligne.articles.all()],
                         [self.article.pk])

    def test_une_ligne_d_observation_ne_garde_aucune_prestation(self):
        """Sa règle les ignore : les laisser attachées ferait croire, à la
        relecture de l'écran, qu'elles entrent dans le chiffre."""
        self._connecter(self.admin)
        self._enregistrer(self._composition(self._bloc('Soins', [
            self._ligne('PERFUSION', source='mo_avec_soin',
                        articles=[self.article.pk])])))
        ligne = self.Configuration.officielle().blocs.first().lignes.first()
        self.assertEqual(ligne.articles.count(), 0)

    # ── refus ───────────────────────────────────────────────────────────────

    def _refus(self, composition):
        avant = self._lignes_de(self.Configuration.officielle())
        reponse = self._enregistrer(composition)
        self.assertEqual(reponse.status_code, 200, 'la page aurait dû rester')
        self.assertEqual(self._lignes_de(self.Configuration.officielle()), avant,
                         'une composition refusée a quand même effacé la fiche')
        return reponse

    def test_un_libelle_vide_est_refuse_sans_rien_effacer(self):
        """La validation passe **avant** l'effacement : une fiche refusée ne
        doit pas laisser l'ancienne détruite et la nouvelle non écrite."""
        self._connecter(self.admin)
        self._refus(self._composition(
            self._bloc('Soins', [self._ligne(''), self._ligne('Valide')])))

    def test_une_prestation_inconnue_est_refusee(self):
        """Un identifiant qui n'existe plus veut dire que l'écran travaille sur
        un catalogue périmé. Vider la ligne en silence se paierait des mois
        plus tard."""
        self._connecter(self.admin)
        self._refus(self._composition(
            self._bloc('Soins', [self._ligne('Essai', articles=[999999])])))

    def test_une_source_inventee_est_refusee(self):
        self._connecter(self.admin)
        self._refus(self._composition(
            self._bloc('Soins', [self._ligne('Essai', source='n_importe_quoi')])))

    def test_une_fiche_sans_bloc_est_refusee(self):
        self._connecter(self.admin)
        self._refus(self._composition())

    def test_une_composition_illisible_est_refusee(self):
        self._connecter(self.admin)
        self._refus('ceci n\'est pas du json')

    # ── le lien avec la fiche ───────────────────────────────────────────────

    def _tableau_des_soins(self):
        """Le seul tableau composable de la fiche, isolé du reste de la page.

        Viser la page entière ferait passer un test pour la mauvaise raison :
        la légende et la barre d'outils portent elles aussi des mots qu'on
        cherche.
        """
        html = self.client.get(
            '/rapports/soins/?annee=2026&mois=10').content.decode()
        debut = html.index('Activités de soins infirmiers')
        return html[debut:html.index('rm-legende', debut)]

    def test_la_fiche_suit_la_configuration_de_celui_qui_la_regarde(self):
        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('À moi', [self._ligne('Ma ligne', source='manuelle')])))

        tableau = self._tableau_des_soins()
        self.assertIn('Ma ligne', tableau)
        self.assertNotIn('PERFUSION', tableau)

    def test_la_fiche_d_un_autre_reste_le_format_par_defaut(self):
        self._connecter(self.simple)
        self._enregistrer(self._composition(
            self._bloc('À moi', [self._ligne('Ma ligne', source='manuelle')])))

        autre = self.User.objects.create_user('temoin_cfg', password='x')
        self._connecter(autre)
        tableau = self._tableau_des_soins()
        self.assertIn('PERFUSION', tableau)
        self.assertNotIn('Ma ligne', tableau)


class TestLaDuplicationEmporteTout(TestCase):
    """Copier une configuration, c'est en copier le contenu — pas y pointer.

    C'est l'opération sur laquelle repose tout le reste : la copie qu'un
    utilisateur reçoit du format par défaut, et, demain, celle qu'il prendra
    d'un collègue. Une copie qui perdrait les prestations cochées rendrait
    toutes ses lignes muettes, et le dirait d'autant moins qu'elles
    afficheraient zéro, un chiffre parfaitement crédible.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from .models import ConfigurationFicheSoins
        self.Configuration = ConfigurationFicheSoins
        self.source = ConfigurationFicheSoins.officielle()
        self.article = Articleservice.objects.create(
            nom='PRESTATION A COPIER', prix_vente=1000, actif=True)
        ligne = self.source.blocs.first().lignes.get(libelle='TRANSFUSION')
        ligne.articles.set([self.article])
        self.destinataire = User.objects.create_user('copie_cfg', password='x')

    def test_la_copie_a_les_memes_blocs_et_les_memes_lignes(self):
        copie = self.source.dupliquer(self.destinataire)
        self.assertEqual(
            [(b.titre, [l.libelle for l in b.lignes.all()])
             for b in copie.blocs.all()],
            [(b.titre, [l.libelle for l in b.lignes.all()])
             for b in self.source.blocs.all()])

    def test_la_copie_emporte_les_prestations_cochees(self):
        copie = self.source.dupliquer(self.destinataire)
        ligne = copie.blocs.first().lignes.get(libelle='TRANSFUSION')
        self.assertEqual([a.pk for a in ligne.articles.all()],
                         [self.article.pk])

    def test_la_copie_emporte_les_colonnes(self):
        bloc = self.source.blocs.first()
        bloc.colonnes.update(titre='Effectif')
        copie = self.source.dupliquer(self.destinataire)
        self.assertEqual(copie.blocs.first().colonnes.first().titre, 'Effectif')

    def test_la_copie_appartient_a_son_destinataire_et_n_est_pas_le_defaut(self):
        copie = self.source.dupliquer(self.destinataire)
        self.assertEqual(copie.utilisateur, self.destinataire)
        self.assertFalse(copie.est_defaut)

    def test_modifier_la_copie_ne_touche_pas_l_original(self):
        """Sans cela, retoucher le format par défaut changerait la fiche de
        ceux qui en étaient partis, sans qu'ils aient rien fait."""
        copie = self.source.dupliquer(self.destinataire)
        copie.blocs.first().lignes.filter(libelle='TRANSFUSION').delete()
        self.assertTrue(
            self.source.blocs.first().lignes.filter(
                libelle='TRANSFUSION').exists())


class TestLEcranRendBienSaComposition(TestCase):
    """L'écran se construit en JavaScript depuis un JSON déposé dans la page.

    Ce test existe parce que ce lien s'est cassé en silence : la vue a renvoyé
    un moment une **chaîne** JSON là où le gabarit attendait un objet, et
    `JSON.parse` rendait alors une chaîne dont `.blocs` vaut `undefined`.
    L'écran s'ouvrait vide, sans la moindre erreur, et vingt-six tests restaient
    verts — aucun ne regardait la page rendue.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client
        self.client = Client()
        self.client.force_login(
            User.objects.create_superuser('rendu_cfg', password='x'))

    def _json_de(self, identifiant):
        import json
        import re
        html = self.client.get(
            '/rapports/soins/configuration/').content.decode()
        trouve = re.search(
            r'<script id="%s" type="application/json">(.*?)</script>'
            % identifiant, html, re.S)
        self.assertIsNotNone(trouve, f"le bloc {identifiant} manque")
        return json.loads(trouve.group(1))

    def test_la_composition_arrive_dans_la_page_sous_forme_d_objet(self):
        donnees = self._json_de('cfg-donnees')
        self.assertIsInstance(donnees, dict,
                              "le JavaScript recevrait une chaîne, pas la fiche")
        self.assertEqual([b['titre'] for b in donnees['blocs']],
                         ['Soins', 'Autres soins à préciser'])

    def test_une_ligne_porte_tout_ce_qu_il_faut_pour_la_redessiner(self):
        bloc = self._json_de('cfg-donnees')['blocs'][0]
        self.assertEqual(
            sorted(bloc['lignes'][0]),
            ['articles', 'libelle', 'origines', 'source'])

    def test_le_catalogue_arrive_sous_forme_de_liste(self):
        from services.models import Articleservice
        Articleservice.objects.create(nom='AU CATALOGUE', prix_vente=10,
                                      actif=True)
        prestations = self._json_de('cfg-prestations')
        self.assertIsInstance(prestations, list)
        self.assertIn('AU CATALOGUE', [p['nom'] for p in prestations])


class TestMettreDeCoteEtPartager(TestCase):
    """Garder une composition sous un nom, la reprendre, la proposer.

    C'est ce qui permet de rouvrir un mois passé tel qu'on l'avait rendu : on
    met la composition de côté quand on produit la fiche, et on la repasse plus
    tard. Et c'est par là qu'une fiche circule entre collègues — **par copie**,
    jamais par lien : une fiche partagée qui resterait liée à son original
    changerait dans le dos de ceux qui l'ont prise.
    """

    URL = '/rapports/soins/configuration/'

    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client
        from .models import ConfigurationFicheSoins

        self.User = User
        self.Configuration = ConfigurationFicheSoins
        self.officielle = ConfigurationFicheSoins.officielle()
        self.moi = User.objects.create_user('moi_cfg', password='x')
        self.autre = User.objects.create_user('autre_p3', password='x')
        self.client = Client()
        self.client.force_login(self.moi)

    # ── outillage ───────────────────────────────────────────────────────────

    def _composition(self, *libelles):
        import json
        return json.dumps({'blocs': [{
            'titre': 'Soins', 'colonne': 'Nombre',
            'lignes': [{'libelle': l, 'source': 'manuelle',
                        'origines': 'procedure', 'articles': []}
                       for l in libelles]}]})

    def _mettre_de_cote(self, nom, *libelles):
        return self.client.post(self.URL, {
            'action': 'enregistrer_sous', 'nom': nom,
            'composition': self._composition(*libelles)})

    def _libelles(self, configuration):
        return [l.libelle for b in configuration.blocs.all()
                for l in b.lignes.all()]

    def _fiche_de(self, utilisateur):
        return self.Configuration.objects.get(utilisateur=utilisateur,
                                              est_active=True)

    # ── mettre de côté ──────────────────────────────────────────────────────

    def test_mettre_de_cote_cree_une_fiche_nommee_qui_n_est_pas_la_courante(self):
        self._mettre_de_cote('Fiche de juin', 'Une ligne de juin')
        mise = self.Configuration.objects.get(nom='Fiche de juin')
        self.assertEqual(mise.utilisateur, self.moi)
        self.assertFalse(mise.est_active)
        self.assertEqual(self._libelles(mise), ['Une ligne de juin'])
        self.assertEqual(self.Configuration.pour(self.moi), self.officielle,
                         "mettre de côté a changé la fiche de travail")

    def test_mettre_de_cote_sans_nom_est_refuse(self):
        self.client.post(self.URL, {
            'action': 'enregistrer_sous', 'nom': '   ',
            'composition': self._composition('Une ligne')})
        self.assertFalse(self.Configuration.objects.filter(
            utilisateur=self.moi).exists())

    def test_une_composition_bancale_ne_laisse_pas_une_fiche_vide(self):
        """La fiche est créée avant d'être remplie : si le remplissage échoue,
        elle doit disparaître, sinon la liste se peuple de coquilles."""
        self.client.post(self.URL, {
            'action': 'enregistrer_sous', 'nom': 'Bancale',
            'composition': 'pas du json'})
        self.assertFalse(
            self.Configuration.objects.filter(nom='Bancale').exists())

    def test_elle_apparait_dans_mes_fiches(self):
        self._mettre_de_cote('Fiche de juin', 'Une ligne')
        reponse = self.client.get(self.URL)
        self.assertEqual([f.nom for f in reponse.context['mes_fiches']],
                         ['Fiche de juin'])

    # ── reprendre ───────────────────────────────────────────────────────────

    def test_reprendre_une_fiche_remplace_la_courante(self):
        self._mettre_de_cote('Fiche de juin', 'Ligne de juin')
        mise = self.Configuration.objects.get(nom='Fiche de juin')

        self.client.post(self.URL, {'action': 'reprendre', 'config': mise.pk})
        self.assertEqual(self._libelles(self._fiche_de(self.moi)),
                         ['Ligne de juin'])

    def test_reprendre_ne_touche_pas_la_fiche_mise_de_cote(self):
        """Elle doit rester disponible : on la reprend pour un mois, puis on
        revient à la sienne."""
        self._mettre_de_cote('Fiche de juin', 'Ligne de juin')
        mise = self.Configuration.objects.get(nom='Fiche de juin')
        self.client.post(self.URL, {'action': 'reprendre', 'config': mise.pk})

        mise.refresh_from_db()
        self.assertFalse(mise.est_active)
        self.assertEqual(self._libelles(mise), ['Ligne de juin'])

    def test_reprendre_n_ecrase_jamais_le_format_par_defaut(self):
        """Même pour un superutilisateur, qui modifie pourtant le défaut quand
        il enregistre : « Appliquer » est un geste personnel, personne
        n'attend qu'il change la fiche de tout le centre."""
        admin = self.User.objects.create_superuser('admin_p3', password='x')
        self.client.force_login(admin)
        avant = self._libelles(self.officielle)

        self._mettre_de_cote('La mienne', 'Ma ligne')
        mise = self.Configuration.objects.get(nom='La mienne')
        self.client.post(self.URL, {'action': 'reprendre', 'config': mise.pk})

        self.officielle.refresh_from_db()
        self.assertEqual(self._libelles(self.officielle), avant)
        self.assertEqual(self._libelles(self._fiche_de(admin)), ['Ma ligne'])

    # ── proposer aux autres ─────────────────────────────────────────────────

    def _proposer(self, nom='Fiche partagée', *libelles):
        self._mettre_de_cote(nom, *(libelles or ('Ligne partagée',)))
        fiche = self.Configuration.objects.get(nom=nom)
        self.client.post(self.URL, {'action': 'partager', 'config': fiche.pk})
        fiche.refresh_from_db()
        return fiche

    def test_proposer_puis_retirer(self):
        fiche = self._proposer()
        self.assertTrue(fiche.partagee)
        self.client.post(self.URL,
                         {'action': 'ne_plus_partager', 'config': fiche.pk})
        fiche.refresh_from_db()
        self.assertFalse(fiche.partagee)

    def test_une_fiche_proposee_est_visible_par_les_autres(self):
        fiche = self._proposer()
        self.client.force_login(self.autre)
        reponse = self.client.get(self.URL)
        self.assertEqual([f.pk for f in reponse.context['fiches_partagees']],
                         [fiche.pk])

    def test_une_fiche_non_proposee_reste_invisible(self):
        self._mettre_de_cote('Secrète', 'Ma ligne')
        self.client.force_login(self.autre)
        reponse = self.client.get(self.URL)
        self.assertEqual(list(reponse.context['fiches_partagees']), [])

    def test_appliquer_la_fiche_d_un_autre_en_fait_une_copie(self):
        fiche = self._proposer('Fiche partagée', 'Ligne de départ')

        self.client.force_login(self.autre)
        self.client.post(self.URL, {'action': 'reprendre', 'config': fiche.pk})
        self.assertEqual(self._libelles(self._fiche_de(self.autre)),
                         ['Ligne de départ'])

        # L'auteur la modifie : la copie ne doit pas bouger.
        self.client.force_login(self.moi)
        self.client.post(self.URL, {'action': 'reprendre', 'config': fiche.pk})
        for bloc in fiche.blocs.all():
            bloc.lignes.update(libelle='Ligne changée après coup')
        self.assertEqual(self._libelles(self._fiche_de(self.autre)),
                         ['Ligne de départ'])

    # ── droits ──────────────────────────────────────────────────────────────

    def test_on_ne_supprime_pas_la_fiche_d_un_autre(self):
        fiche = self._proposer()
        self.client.force_login(self.autre)
        self.client.post(self.URL, {'action': 'supprimer', 'config': fiche.pk})
        self.assertTrue(self.Configuration.objects.filter(pk=fiche.pk).exists())

    def test_on_ne_retire_pas_du_partage_la_fiche_d_un_autre(self):
        fiche = self._proposer()
        self.client.force_login(self.autre)
        self.client.post(self.URL,
                         {'action': 'ne_plus_partager', 'config': fiche.pk})
        fiche.refresh_from_db()
        self.assertTrue(fiche.partagee)

    def test_on_ne_reprend_pas_une_fiche_qu_on_n_a_pas_le_droit_de_lire(self):
        self._mettre_de_cote('Secrète', 'Ma ligne')
        secrete = self.Configuration.objects.get(nom='Secrète')

        self.client.force_login(self.autre)
        self.client.post(self.URL,
                         {'action': 'reprendre', 'config': secrete.pk})
        self.assertFalse(self.Configuration.objects.filter(
            utilisateur=self.autre).exists())

    def test_un_numero_de_fiche_absurde_ne_casse_rien(self):
        reponse = self.client.post(self.URL,
                                   {'action': 'reprendre', 'config': 'abc'})
        self.assertEqual(reponse.status_code, 302)

    def test_supprimer_sa_propre_fiche(self):
        self._mettre_de_cote('À jeter', 'Ma ligne')
        fiche = self.Configuration.objects.get(nom='À jeter')
        self.client.post(self.URL, {'action': 'supprimer', 'config': fiche.pk})
        self.assertFalse(self.Configuration.objects.filter(pk=fiche.pk).exists())

    # ── rouvrir un mois dans une autre composition ──────────────────────────

    def _fiche_affichee(self, parametres=''):
        reponse = self.client.get(
            '/rapports/soins/?annee=2026&mois=10' + parametres)
        self.assertEqual(reponse.status_code, 200)
        html = reponse.content.decode()
        debut = html.index('Activités de soins infirmiers')
        return html[debut:html.index('rm-legende', debut)]

    def test_on_rouvre_un_mois_dans_une_composition_mise_de_cote(self):
        self._mettre_de_cote('Fiche de juin', 'Ligne de juin')
        mise = self.Configuration.objects.get(nom='Fiche de juin')

        self.assertIn('PERFUSION', self._fiche_affichee())
        tableau = self._fiche_affichee(f'&config={mise.pk}')
        self.assertIn('Ligne de juin', tableau)
        self.assertNotIn('PERFUSION', tableau)

    def test_la_regarder_ainsi_ne_change_pas_sa_propre_fiche(self):
        self._mettre_de_cote('Fiche de juin', 'Ligne de juin')
        mise = self.Configuration.objects.get(nom='Fiche de juin')
        self._fiche_affichee(f'&config={mise.pk}')
        self.assertIn('PERFUSION', self._fiche_affichee())

    def test_une_composition_inaccessible_est_refusee(self):
        """Sinon il suffirait d'incrémenter un chiffre dans l'adresse pour
        lire la fiche de n'importe qui."""
        self._mettre_de_cote('Secrète', 'Ma ligne')
        secrete = self.Configuration.objects.get(nom='Secrète')
        self.client.force_login(self.autre)
        reponse = self.client.get(
            f'/rapports/soins/?annee=2026&mois=10&config={secrete.pk}')
        self.assertEqual(reponse.status_code, 404)

    def test_la_feuille_dit_de_quelle_composition_elle_sort(self):
        """Deux personnes qui impriment le même mois peuvent en sortir deux
        feuilles différentes : sans cette mention, elles seraient
        indiscernables sur un bureau."""
        html = self.client.get(
            '/rapports/soins/?annee=2026&mois=10').content.decode()
        self.assertIn('Composition : <strong>Format officiel</strong>', html)
