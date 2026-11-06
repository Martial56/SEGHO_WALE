from datetime import date

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

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


def _sync(facture):
    """`_sync_lignes_demande_examen`, sous un nom court.

    Elle passe par `facture.demandes_examens`, dont le manager filtre sur le
    centre actif : hors requête il faut le poser (cf. `centre_actif`), sans
    quoi elle ne trouve aucune demande et ne fait rien — en silence.
    """
    from facturation.views import _sync_lignes_demande_examen

    return _sync_lignes_demande_examen(facture)


class TestLaDemandeDitCeQuiAEtePaye(TestCase):
    """La caisse ne réécrit plus la demande du médecin, elle l'annote.

    `_sync_lignes_demande_examen` effaçait toutes les lignes de la demande et
    les recréait depuis la facture. Un examen retiré à la caisse disparaissait
    sans trace — personne ne pouvait plus dire ce que le médecin avait demandé,
    ni pourquoi l'examen n'avait pas été fait. Et la recréation perdait
    `article_service`, c'est-à-dire le **code HPRIM** envoyé au laboratoire
    partenaire : la demande partait sans code dès qu'elle était facturée.
    """

    def setUp(self):
        from decimal import Decimal

        from django.contrib.auth.models import User
        from django.test import Client
        from centres.models import Centre
        from facturation.models import Facture, LigneFacture
        from laboratoire.models import DemandeExamen, LigneDemandeExamen
        from patients.models import Patient
        from services.models import Articleservice

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_labo_paye', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])
        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='LaboPaye', prenoms='Patient', date_naissance='1980-01-01',
            sexe='M', telephone='0700000040', centre=self.centre)

        from services.models import CategorieArticle

        self.categorie_examens = CategorieArticle.objects.create(
            nom='Examens biologiques', code='EX')
        self.article = Articleservice.objects.create(
            nom='NFS', prix_vente=Decimal('4000'), code_hprim='NFS01',
            categorie=self.categorie_examens)

        self.facture = Facture.objects.create(
            patient=self.patient, type_facture='laboratoire', statut='payee',
            montant_total=Decimal('4000'), centre=self.centre)
        self.demande = DemandeExamen.objects.create(
            patient=self.patient, facture=self.facture, centre=self.centre)
        self.garde = LigneDemandeExamen.objects.create(
            demande=self.demande, libelle='NFS', prix=Decimal('4000'),
            article_service=self.article)
        self.retire = LigneDemandeExamen.objects.create(
            demande=self.demande, libelle='Cholestérol', prix=Decimal('2500'))

        # La facture ne porte que le premier : le second a été retiré.
        LigneFacture.objects.create(
            facture=self.facture, libelle='NFS', quantite=1,
            prix_unitaire=Decimal('4000'), article=self.article,
            ligne_demande_examen=self.garde)

    def test_l_examen_retire_reste_sur_la_demande(self):
        with centre_actif(self.centre):
            _sync(self.facture)
        self.assertEqual(self.demande.lignes.count(), 2)

    def test_l_examen_retire_est_marque_non_paye(self):
        from facturation.views import _examens_non_payes

        with centre_actif(self.centre):
            _sync(self.facture)
            self.assertEqual(_examens_non_payes(self.demande), {self.retire.pk})

    def test_le_code_hprim_survit_a_la_facturation(self):
        """`article_service` était perdu à chaque enregistrement de facture."""
        with centre_actif(self.centre):
            _sync(self.facture)
        self.garde.refresh_from_db()
        self.assertEqual(self.garde.article_service_id, self.article.pk)
        self.assertEqual(self.garde.article_service.code_hprim, 'NFS01')

    def test_le_total_ne_compte_que_ce_qui_est_paye(self):
        from decimal import Decimal

        with centre_actif(self.centre):
            _sync(self.facture)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.montant_total, Decimal('4000'))

    def test_un_examen_ajoute_a_la_caisse_rejoint_la_demande(self):
        from decimal import Decimal

        from facturation.models import LigneFacture
        from services.models import Articleservice

        glycemie = Articleservice.objects.create(
            nom='Glycémie', prix_vente=Decimal('1500'),
            categorie=self.categorie_examens)
        LigneFacture.objects.create(
            facture=self.facture, libelle='Glycémie', quantite=1,
            prix_unitaire=Decimal('1500'), article=glycemie)
        with centre_actif(self.centre):
            _sync(self.facture)

        ajoutee = self.demande.lignes.get(libelle='Glycémie')
        self.assertEqual(ajoutee.origine, 'caisse')
        # Le laboratoire doit le faire : il est payé, donc pas « non payé ».
        from facturation.views import _examens_non_payes
        self.assertNotIn(ajoutee.pk, _examens_non_payes(self.demande))

    def test_les_deux_mentions_s_affichent(self):
        from decimal import Decimal

        from facturation.models import LigneFacture
        from services.models import Articleservice

        glycemie = Articleservice.objects.create(
            nom='Glycémie', prix_vente=Decimal('1500'),
            categorie=self.categorie_examens)
        LigneFacture.objects.create(
            facture=self.facture, libelle='Glycémie', quantite=1,
            prix_unitaire=Decimal('1500'), article=glycemie)
        with centre_actif(self.centre):
            _sync(self.facture)

        page = self.client.get(
            reverse('laboratoire_detail', args=[self.demande.pk])).content.decode()
        self.assertIn('>Non payé<', page)
        self.assertIn('>Ajouté à la caisse<', page)

    def test_un_consommable_ajoute_a_la_caisse_ne_part_pas_au_labo(self):
        """Une facture d'examens n'est pas faite que d'examens.

        La caisse y ajoute volontiers une boîte de gants. Sans tri, elle
        arrivait sur la demande et le laboratoire se voyait réclamer
        d'« exécuter » un consommable.
        """
        from decimal import Decimal

        from facturation.models import LigneFacture
        from services.models import Articleservice
        from stock.models import Produit

        gants = Produit.objects.create(
            nom='Gants', type='consommable',
            prix_achat=Decimal('50'), prix_vente=Decimal('200'))
        LigneFacture.objects.create(
            facture=self.facture, libelle='Gants', quantite=1,
            prix_unitaire=Decimal('200'), produit=gants)
        # Et une ligne tapée à la main, sans catégorie : dans le doute, non.
        LigneFacture.objects.create(
            facture=self.facture, libelle='Divers', quantite=1,
            prix_unitaire=Decimal('500'))

        with centre_actif(self.centre):
            _sync(self.facture)

        libelles = set(self.demande.lignes.values_list('libelle', flat=True))
        self.assertEqual(libelles, {'NFS', 'Cholestérol'})

    def test_une_ligne_du_medecin_ne_porte_aucune_mention(self):
        with centre_actif(self.centre):
            _sync(self.facture)
        self.garde.refresh_from_db()
        self.assertEqual(self.garde.origine, 'medecin')


class TestLaNumerotationSurvitAUneSuppression(TestCase):
    """Les trois numérotations du laboratoire partageaient le défaut de `Patient`.

    Elles comptaient les lignes de l'année : effacer une analyse faisait
    retomber le compteur sur un numéro déjà porté, et l'enregistrement suivant
    butait sur la contrainte d'unicité.
    """

    def setUp(self):
        self.patient = Patient.objects.create(
            nom='Labo', prenoms='Test', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000')

    def _demande(self):
        return DemandeExamen.objects.create(patient=self.patient)

    def test_une_demande_apres_une_suppression_ne_leve_plus(self):
        a, b, c = (self._demande() for _ in range(3))
        dernier = c.numero
        b.delete()
        suivante = self._demande()
        self.assertGreater(suivante.numero, dernier)
        self.assertEqual(
            DemandeExamen.all_objects.filter(numero=suivante.numero).count(), 1)

    def test_une_analyse_apres_une_suppression_ne_leve_plus(self):
        from .models import AnalyseLaboratoire
        faits = [AnalyseLaboratoire.objects.create(patient=self.patient)
                 for _ in range(3)]
        dernier = faits[-1].numero
        faits[1].delete()
        suivante = AnalyseLaboratoire.objects.create(patient=self.patient)
        self.assertGreater(suivante.numero, dernier)

    def test_une_imagerie_apres_une_suppression_ne_leve_plus(self):
        from .models import ExamenImagerie
        faits = [ExamenImagerie.objects.create(
            patient=self.patient, type_imagerie='radiographie',
            zone_examinee='Thorax') for _ in range(3)]
        dernier = faits[-1].numero
        faits[1].delete()
        suivante = ExamenImagerie.objects.create(
            patient=self.patient, type_imagerie='radiographie',
            zone_examinee='Thorax')
        self.assertGreater(suivante.numero, dernier)


class FormatOrmSyslamTests(SimpleTestCase):
    """Le fichier ORM doit être exactement celui attendu par le laboratoire
    (SYSLAM) : identités du segment H, version H2.2, identifiants numériques
    en 9.3, codes HPRIM seuls en 9.5, segment L sans nom de fichier."""

    ATTENDU = (
        "H|~^\\&|WALE0020.HPR||ACCWAL~WALE Accueil Auto||ORM|||WALE~CMS WALE|||H2.2~L|202608070608\r\n"
        "P|1|PAT202600013|||Adepo~Jean||19570720|M||||080605\r\n"
        "OBR|1|2026000027~2026000027||NFS^VS|||||||N\r\n"
        "L|1||1|4\r\n"
    )

    def test_fichier_identique_a_l_exemple_du_laboratoire(self):
        from datetime import datetime
        from .hprim.core import (AnalyseData, DemandeData, Entite, HprimMessage,
                                 PatientData)
        from .hprim.integration import identifiant_hprim

        msg = HprimMessage(
            contexte="ORM",
            emetteur=Entite("ACCWAL", "WALE Accueil Auto"),
            recepteur=Entite("WALE", "CMS WALE"),
            nom_fichier="WALE0020.HPR",
            date_message=datetime(2026, 8, 7, 6, 8),
        )
        identifiant = identifiant_hprim("DEM2026000027")
        msg.ajouter_patient(
            PatientData(rang=1, id_demandeur="PAT202600013", nom="Adepo", prenom="Jean",
                        date_naissance=datetime(1957, 7, 20), sexe="M", telephone="080605"),
            [DemandeData(rang=1, id_echantillon=identifiant, id_demande=identifiant,
                         analyses=[AnalyseData("NFS", "Numération formule sanguine"),
                                   AnalyseData("VS", "Vitesse de sédimentation")])],
        )
        self.assertEqual(msg.render(), self.ATTENDU)


class OrmDepuisLaBaseTests(TestCase):
    """Bout en bout : une demande enregistrée part avec les identités et les
    identifiants attendus par le laboratoire, et le résultat qui revient avec
    l'identifiant numérique retrouve bien sa demande."""

    def setUp(self):
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-ORM')
        with centre_actif(self.centre):
            self.config = ConfigurationHPRIM.objects.create(nom='Config WALE', actif=True)
            patient = Patient.objects.create(
                nom='Adepo', prenoms='Jean', date_naissance=date(1957, 7, 20),
                sexe='M', telephone='080605',
            )
            self.demande = DemandeExamen.objects.create(patient=patient, statut='brouillon')
            LigneDemandeExamen.objects.create(demande=self.demande, libelle='NFS', prix=5000)

    def test_segments_h_et_obr(self):
        from .hprim.integration import construire_orm
        _nom, contenu, _msg = construire_orm(self.demande, self.config, 20)
        segments = contenu.split("\r\n")
        identifiant = self.demande.numero.replace("DEM", "")
        self.assertIn("|ACCWAL~WALE Accueil Auto||ORM|||WALE~CMS WALE|||H2.2~L|", segments[0])
        self.assertTrue(segments[2].startswith(f"OBR|1|{identifiant}~{identifiant}||"))
        self.assertTrue(identifiant.isdigit())
        self.assertEqual(segments[3], "L|1||1|4")

    def test_le_retour_oru_numerique_retrouve_la_demande(self):
        from .hprim.integration import integrer_oru
        identifiant = self.demande.numero.replace("DEM", "")
        oru = (
            "H|~^\\&|LAB00001.HPR||WALE~CMS WALE||ORU|||ACCWAL~WALE Accueil Auto|||H2.2~L|202608071000\r\n"
            f"P|1|{self.demande.patient.code_patient}|||Adepo~Jean\r\n"
            f"OBR|1|{identifiant}~{identifiant}||NFS\r\n"
            "OBX|1|NM|HB~Hémoglobine~L||13.5|g/dl|12-16|N\r\n"
            "L|1||1|5\r\n"
        ).encode("iso-8859-1")
        with centre_actif(self.centre):
            _parsed, synthese = integrer_oru(oru, centre=self.centre)
        self.assertEqual(synthese["resultats"], 1)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, "termine")

    def test_le_medecin_ouvre_la_fiche_du_resultat(self):
        from django.contrib.auth.models import User
        from django.urls import reverse
        from .hprim.integration import integrer_oru
        identifiant = self.demande.numero.replace("DEM", "")
        patient = self.demande.patient
        oru = (
            "H|~^\\&|LAB00002.HPR||WALE~CMS WALE||ORU|||ACCWAL~WALE Accueil Auto|||H2.2~L|202608071000\r\n"
            f"P|1|{patient.code_patient}|||Adepo~Jean\r\n"
            f"OBR|1|{identifiant}~{identifiant}||NFS\r\n"
            "OBX|1|NM|HB~Hémoglobine~L||8.1|g/dl|12-16|L\r\n"
            "OBX|2|NM|GB~Leucocytes~L||6500|/mm3|4000-10000|N\r\n"
            "L|1||1|6\r\n"
        ).encode("iso-8859-1")
        with centre_actif(self.centre):
            integrer_oru(oru, centre=self.centre)
            self.client.force_login(User.objects.create_superuser('medecin_res', password='x'))
            analyse = self.demande.analyses.get()
            liste = self.client.get(reverse('patients:resultat_examens_list', args=[patient.pk]))
            fiche = self.client.get(reverse('patients:resultat_examen_detail', args=[patient.pk, analyse.pk]))

        url_fiche = reverse('patients:resultat_examen_detail', args=[patient.pk, analyse.pk])
        self.assertContains(liste, f'data-url="{url_fiche}')
        self.assertContains(liste, 'NFS')                 # libellé de la demande, plus « None »
        self.assertContains(fiche, 'Hémoglobine')
        self.assertContains(fiche, '12 – 16')
        self.assertContains(fiche, '<tr class="re-anormal">', count=1)
        self.assertContains(fiche, '1 valeur hors normes')


class OngletResultatsDeLaConsultationTests(TestCase):
    """Une demande faite depuis une consultation garde le lien avec elle, et
    le résultat reçu s'affiche dans l'onglet « Résultats d'examens » des deux
    fiches de consultation (médecine générale et gynécologie)."""

    def setUp(self):
        from django.contrib.auth.models import User
        from django.utils import timezone
        from patients.models import RendezVous
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-ONG')
        self.user = User.objects.create_superuser('medecin_onglet', password='x')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Kone', prenoms='Mariam', date_naissance=date(1992, 3, 3),
                sexe='F', telephone='0700000001')
            self.rdv = RendezVous.objects.create(
                patient=self.patient, date_heure=timezone.now(),
                statut='en_consultation', motif='Consultation')
            self.autre_rdv = RendezVous.objects.create(
                patient=self.patient, date_heure=timezone.now(),
                statut='en_consultation', motif='Autre consultation')
        self.client.force_login(self.user)

    def _demande_depuis_la_consultation(self):
        from django.urls import reverse
        with centre_actif(self.centre):
            self.client.post(reverse('laboratoire_create'), {
                'patient_id': self.patient.pk, 'rdv_id': self.rdv.pk,
                'ligne_examen_0': 'Hémogramme', 'ligne_prix_0': '4000',
            })
        return DemandeExamen.all_objects.get(patient=self.patient)

    def test_la_demande_garde_sa_consultation(self):
        self.assertEqual(self._demande_depuis_la_consultation().rendez_vous, self.rdv)

    def test_le_resultat_s_affiche_dans_l_onglet(self):
        from django.urls import reverse
        from .hprim.integration import integrer_oru
        demande = self._demande_depuis_la_consultation()
        identifiant = demande.numero.replace("DEM", "")
        oru = (
            "H|~^\\&|LAB00003.HPR||WALE~CMS WALE||ORU|||ACCWAL~WALE Accueil Auto|||H2.2~L|202608071000\r\n"
            f"P|1|{self.patient.code_patient}|||Kone~Mariam\r\n"
            f"OBR|1|{identifiant}~{identifiant}||NFS\r\n"
            "OBX|1|NM|HB~Hémoglobine~L||7.9|g/dl|12-16|L\r\n"
            "OBX|2|NM|PLQ~Plaquettes~L||250000|/mm3|150000-400000|N\r\n"
            "L|1||1|6\r\n"
        ).encode("iso-8859-1")
        with centre_actif(self.centre):
            integrer_oru(oru, centre=self.centre)
            pages = [
                self.client.get(reverse('patients:rdv_edit', args=[self.rdv.pk])),
                self.client.get(reverse('gynecologie_rdv_detail', args=[self.rdv.pk])),
            ]
            autre = self.client.get(reverse('patients:rdv_edit', args=[self.autre_rdv.pk]))

        for page in pages:
            self.assertContains(page, 'data-tab="resultats"')
            self.assertContains(page, 'id="tab-resultats"')
            self.assertContains(page, 'Hémoglobine')
            self.assertContains(page, '<tr class="rex-anormal">', count=1)
            self.assertContains(page, '1 valeur hors normes')
        # L'autre consultation du même jour ne montre pas ce résultat.
        self.assertNotContains(autre, 'Hémoglobine')
        self.assertContains(autre, "Aucun examen de laboratoire n'a été demandé depuis cette consultation.")


class BulletinDeResultatsTests(TestCase):
    """Le bulletin imprimable reprend la fiche papier du laboratoire : une
    rubrique par type de test, l'examen en titre, les valeurs de référence,
    l'antériorité et le commentaire du biologiste (segment C)."""

    def setUp(self):
        from django.contrib.auth.models import User
        from services.models import Articleservice, CategorieArticle
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-BUL')
        categorie = CategorieArticle.objects.create(nom='Examens biologiques', code='EX')
        nfs = Articleservice.objects.create(nom='Hémogramme', code_hprim='NFS', categorie=categorie,
                                            type_test_labo='hematologie')
        ge = Articleservice.objects.create(nom='Goutte épaisse', code_hprim='GE', categorie=categorie,
                                           type_test_labo='parasitologie')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Kouassi', prenoms='Adjoua Adeline', date_naissance=date(1988, 1, 1),
                sexe='F', telephone='0799125679')
            self.ancienne = DemandeExamen.objects.create(patient=self.patient)
            LigneDemandeExamen.objects.create(demande=self.ancienne, libelle='Hémogramme', prix=0,
                                              article_service=nfs)
            self.demande = DemandeExamen.objects.create(patient=self.patient)
            LigneDemandeExamen.objects.create(demande=self.demande, libelle='Hémogramme', prix=0,
                                              article_service=nfs)
            LigneDemandeExamen.objects.create(demande=self.demande, libelle='Goutte épaisse', prix=0,
                                              article_service=ge)
        self.client.force_login(User.objects.create_superuser('medecin_bul', password='x'))

    def _oru(self, demande, date_msg, corps):
        ident = demande.numero.replace("DEM", "")
        return (
            "H|~^\\&|LAB00009.HPR||WALE~CMS WALE||ORU|||ACCWAL~WALE Accueil Auto|||H2.2~L|" + date_msg + "\r\n"
            f"P|1|{self.patient.code_patient}|||Kouassi~Adjoua Adeline\r\n"
            + corps.replace("ID", f"{ident}~{ident}") + "L|1||1|9\r\n"
        ).encode("iso-8859-1")

    def test_bulletin(self):
        from django.urls import reverse
        from .hprim.integration import integrer_oru
        with centre_actif(self.centre):
            integrer_oru(self._oru(self.ancienne, "202610010800",
                                   "OBR|1|ID||NFS\r\nOBX|1|NM|HB~Hémoglobine~L||10.1|g/dl|11.5-16.0|L\r\n"),
                         centre=self.centre)
            integrer_oru(self._oru(self.demande, "202611060830",
                                   "OBR|1|ID||NFS\r\n"
                                   "OBX|1|NM|HB~Hémoglobine~L||8.8|g/dl|11.5-16.0|L\r\n"
                                   "OBX|2|NM|GB~Leucocytes~L||8700|/mm3|4000-10000|N\r\n"
                                   "C|1|L|Anémie, Hypochrome, Microcytaire\r\n"
                                   "OBR|2|ID||GE\r\n"
                                   "OBX|1|TX|GE~Recherche de parasites sanguins~L||POSITIVE|||A\r\n"),
                         centre=self.centre)
            analyses = list(self.demande.analyses.order_by('code_examen'))
            self.assertEqual([a.code_examen for a in analyses], ['GE', 'NFS'])
            nfs = analyses[1]
            self.assertEqual(nfs.conclusion, 'Anémie, Hypochrome, Microcytaire')
            page = self.client.get(reverse('patients:resultat_examen_bulletin',
                                           args=[self.patient.pk, nfs.pk]))

        html = page.content.decode()
        # Les deux examens de la demande, chacun dans sa rubrique, dans l'ordre de la fiche.
        self.assertLess(html.index('HEMATOLOGIE GENERALE'), html.index('PARASITOLOGIE'))
        self.assertContains(page, 'Hémogramme')
        self.assertContains(page, 'Recherche de parasites sanguins')
        self.assertContains(page, '(11.5 – 16.0)')
        self.assertContains(page, 'Anémie, Hypochrome, Microcytaire')
        self.assertContains(page, '10.1 g/dl<br>(01/10/26)')      # antériorité
        self.assertContains(page, 'Née le 01.01.1988')
        self.assertRegex(html, r'Madame\s+<strong>KOUASSI Adjoua Adeline</strong>')


class NotificationResultatTests(TestCase):
    """Un résultat arrivé est signalé au médecin prescripteur — dans sa cloche
    et en rouge sur l'onglet de la consultation — jusqu'à ce que lui l'ouvre.
    Un autre utilisateur qui consulte le dossier n'éteint pas l'alerte."""

    def setUp(self):
        from django.contrib.auth.models import User
        from django.utils import timezone
        from employer.models import Employe
        from medecins.models import Medecin, Specialite
        from patients.models import RendezVous
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-NOT')
        self.docteur = User.objects.create_superuser('dr_notif', password='x')
        self.infirmiere = User.objects.create_superuser('inf_notif', password='x')
        specialite, _ = Specialite.objects.get_or_create(nom='Généraliste', code='GEN')
        medecin = Medecin.objects.create(
            user=self.docteur, specialite=specialite,
            employe=Employe.objects.create(nom='Docteur', prenoms='Notif', telephone='0700000009',
                                           date_embauche='2020-01-01'))
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Traore', prenoms='Awa', date_naissance=date(1990, 5, 5),
                sexe='F', telephone='0700000010')
            self.rdv = RendezVous.objects.create(
                patient=self.patient, medecin=medecin, date_heure=timezone.now(),
                statut='en_consultation', motif='Consultation')
            self.demande = DemandeExamen.objects.create(
                patient=self.patient, rendez_vous=self.rdv, medecin_prescripteur=medecin)
            LigneDemandeExamen.objects.create(demande=self.demande, libelle='Hémogramme', prix=0)

    def _recevoir_resultat(self):
        from .hprim.integration import integrer_oru
        ident = self.demande.numero.replace("DEM", "")
        oru = (
            "H|~^\&|LAB00010.HPR||WALE~CMS WALE||ORU|||ACCWAL~WALE Accueil Auto|||H2.2~L|202611060900\r\n"
            f"P|1|{self.patient.code_patient}|||Traore~Awa\r\n"
            f"OBR|1|{ident}~{ident}||NFS\r\n"
            "OBX|1|NM|HB~Hémoglobine~L||12.4|g/dl|11.5-16.0|N\r\n"
            "L|1||1|5\r\n"
        ).encode("iso-8859-1")
        with centre_actif(self.centre):
            integrer_oru(oru, centre=self.centre)
        return self.demande.analyses.get()

    def _get(self, user, url):
        self.client.force_login(user)
        with centre_actif(self.centre):
            return self.client.get(url)

    def _post(self, user, url):
        self.client.force_login(user)
        with centre_actif(self.centre):
            return self.client.post(url)

    def test_parcours(self):
        from django.urls import reverse
        analyse = self._recevoir_resultat()
        self.assertEqual(analyse.destinataire, self.docteur)
        self.assertIsNone(analyse.vu_le)
        fiche_rdv = reverse('patients:rdv_edit', args=[self.rdv.pk])
        vus = reverse('patients:rdv_resultats_vus', args=[self.rdv.pk])

        # Le médecin est prévenu, l'infirmière non ; l'onglet est rouge.
        page = self._get(self.docteur, fiche_rdv)
        self.assertContains(page, "Résultats d'examens à lire")
        self.assertContains(page, 'class="f-tab f-tab-resultats-nouveaux"')
        self.assertContains(page, 'NOUVEAU')
        self.assertNotContains(self._get(self.infirmiere, fiche_rdv), "Résultats d'examens à lire")

        # L'infirmière ouvre l'onglet : l'alerte du médecin reste.
        self.assertEqual(self._post(self.infirmiere, vus).json(), {'marques': 0, 'restants': 1})
        self.assertContains(self._get(self.infirmiere, fiche_rdv), 'class="f-tab f-tab-resultats-nouveaux"')

        # Le médecin l'ouvre : plus de rouge, plus de notification.
        self.assertEqual(self._post(self.docteur, vus).json(), {'marques': 1, 'restants': 0})
        page = self._get(self.docteur, fiche_rdv)
        self.assertNotContains(page, 'class="f-tab f-tab-resultats-nouveaux"')
        self.assertNotContains(page, "Résultats d'examens à lire")

    def test_ouvrir_la_fiche_du_resultat_eteint_l_alerte(self):
        from django.urls import reverse
        analyse = self._recevoir_resultat()
        self._get(self.docteur, reverse('patients:resultat_examen_detail', args=[self.patient.pk, analyse.pk]))
        analyse.refresh_from_db()
        self.assertIsNotNone(analyse.vu_le)

    def test_sans_destinataire_le_premier_lecteur_eteint_l_alerte(self):
        """Prescripteur sans compte : personne ne peut être prévenu, mais
        l'onglet ne doit pas rester rouge une fois le résultat lu."""
        from django.urls import reverse
        self.demande.medecin_prescripteur = None
        self.demande.save()
        self.rdv.medecin = None
        self.rdv.save()
        analyse = self._recevoir_resultat()
        self.assertIsNone(analyse.destinataire)
        vus = reverse('patients:rdv_resultats_vus', args=[self.rdv.pk])
        self.assertEqual(self._post(self.infirmiere, vus).json(), {'marques': 1, 'restants': 0})
        self.assertNotContains(self._get(self.infirmiere, reverse('patients:rdv_edit', args=[self.rdv.pk])),
                               'class="f-tab f-tab-resultats-nouveaux"')


class StatutFactureeDemandeTests(TestCase):
    """Brouillon → Facturée quand la caisse rattache la facture ; retour en
    brouillon si elle est annulée ; l'envoi au laboratoire reste possible."""

    def setUp(self):
        from decimal import Decimal
        from django.contrib.auth.models import User
        from facturation.models import Facture
        self.centre = Centre.objects.create(nom='CMS WALE Yamoussoukro', code='WALE-FACT-DEM')
        with centre_actif(self.centre):
            self.patient = Patient.objects.create(
                nom='Koffi', prenoms='Ama', date_naissance=date(1991, 2, 2),
                sexe='F', telephone='0700000077')
            self.demande = DemandeExamen.objects.create(patient=self.patient)
            LigneDemandeExamen.objects.create(demande=self.demande, libelle='NFS', prix=4000)
            self.facture = Facture.objects.create(
                patient=self.patient, type_facture='laboratoire', statut='emise',
                montant_total=Decimal('4000'))
        self.client.force_login(User.objects.create_superuser('caisse_dem', password='x'))

    def _facturer(self):
        # Ce que fait la caisse (facturation.views) : demande.facture = facture.
        self.demande.facture = self.facture
        self.demande.save(update_fields=['facture'])
        self.demande.refresh_from_db()

    def test_la_facture_passe_la_demande_facturee(self):
        self._facturer()
        self.assertEqual(self.demande.statut, 'facturee')
        self.assertEqual(self.demande.get_statut_display(), 'Facturée')

    def test_annuler_la_facture_la_remet_en_brouillon(self):
        self._facturer()
        self.facture.statut = 'annulee'
        self.facture.save()
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, 'brouillon')

    def test_une_demande_deja_envoyee_ne_bouge_pas(self):
        DemandeExamen.all_objects.filter(pk=self.demande.pk).update(statut='demande')
        self._facturer()
        self.assertEqual(self.demande.statut, 'demande')

    def test_le_bouton_envoyer_au_labo_reste_propose(self):
        from django.urls import reverse
        self._facturer()
        with centre_actif(self.centre):
            page = self.client.get(reverse('laboratoire_detail', args=[self.demande.pk]))
        self.assertContains(page, 'value="envoyer_labo"')
        self.assertContains(page, 'Facturé</div>')
