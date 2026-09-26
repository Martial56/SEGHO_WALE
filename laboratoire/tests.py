from datetime import date

from django.test import TestCase
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
