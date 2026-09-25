"""La prescription ne propose que ce que la pharmacie du centre peut servir.

Ces écrans lisaient jusqu'ici `pharmacie.Medicament`, la table d'avant les deux
pharmacies — ou, pour celui de l'app `ordonnance`, `stock.Produit` filtré sur la
pharmacie du *médecin prescripteur*, avec retour sur la somme des deux dès que
ce rattachement échouait, c'est-à-dire toujours. Les deux passent désormais par
`pharmacie.disponibilite`, la règle partagée avec la facturation.
"""

import json
import re
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from centres.models import Centre
from consultations.models import LigneOrdonnance, Ordonnance
from pharmacie.models import StockPharmacie
from stock.models import Produit


def _en_rayon(pharmacie, produit, quantite):
    """Un signal pose déjà une ligne à zéro pour chaque pharmacie."""
    sp, _ = StockPharmacie.objects.get_or_create(pharmacie=pharmacie, produit=produit)
    sp.quantite = Decimal(quantite)
    sp.save(update_fields=['quantite'])
    return sp


class TestPrescriptionParCentre(TestCase):

    def setUp(self):
        from patients.models import Patient

        self.toumbokro = Centre.objects.get_or_create(
            code='TOUMBOKRO', defaults={'nom': 'CMS WALE Toumbokro'})[0]
        self.yamoussoukro = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]

        self.user = User.objects.create_superuser('su_ord', password='x')
        profil = self.user.profile
        profil.centres.add(self.toumbokro, self.yamoussoukro)
        profil.centre_actif = self.toumbokro
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        self.sirop = Produit.objects.create(
            nom='Sirop de test', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        self.gants = Produit.objects.create(
            nom='Gants de test', type='consommable',
            prix_achat=Decimal('50'), prix_vente=Decimal('200'))

        # Toumbokro : plus de sirop, mais des gants. Yamoussoukro : du sirop.
        _en_rayon('wale_toumbokro', self.sirop, '0')
        _en_rayon('wale_toumbokro', self.gants, '12')
        _en_rayon('wale_yamoussoukro', self.sirop, '40')
        _en_rayon('wale_yamoussoukro', self.gants, '0')

        # Le patient doit relever du centre actif : les écrans le cherchent avec
        # le gestionnaire cloisonné, et un patient sans centre sort en 404.
        self.patient = Patient.objects.create(
            nom='TestOrd', prenoms='Patient', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000', centre=self.toumbokro)

        from employer.models import Employe
        from medecins.models import Medecin
        self.medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTMED', prenoms='Prescripteur', date_embauche='2020-01-01'))

        # Le formulaire de la fiche patient refuse de créer une ordonnance hors
        # consultation : il lui en faut une pour s'y rattacher.
        from consultations.models import Consultation
        self.consultation = Consultation.objects.create(
            patient=self.patient, medecin=self.medecin, motif='Test')

    # ── Outils ─────────────────────────────────────────────────────────────

    def _centre_actif(self, centre):
        profil = self.user.profile
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])

    def _liste_proposee(self, url):
        """Les produits injectés dans `MEDS`, tels que l'écran les reçoit."""
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200, url)
        brut = re.search(r'let MEDS = (\[.*?\]);',
                         reponse.content.decode(), re.S)
        self.assertIsNotNone(brut, "MEDS introuvable dans le gabarit")
        return {m['designation']: m for m in json.loads(brut.group(1))}

    def _prescrire(self, produit_pk, libre='', url=None):
        return self.client.post(url or reverse('ordonnance_create_libre'), {
            'patient_id': self.patient.pk,
            'medecin_id': self.medecin.pk,
            'medecin': self.medecin.pk,
            'consultation_id': self.consultation.pk,
            'type_ordonnance': 'interne',
            'medicament[]': str(produit_pk or ''),
            'medicament_libre[]': libre,
            'posologie[]': '1 matin et soir',
            'duree[]': '5 jours',
            'quantite[]': '2',
        }, follow=True)

    # ── La liste proposée ──────────────────────────────────────────────────

    def test_la_liste_est_celle_de_la_pharmacie_du_centre_actif(self):
        propose = self._liste_proposee(reverse('ordonnance_create_libre'))
        self.assertEqual(propose['Sirop de test']['stock_actuel'], 0)
        self.assertTrue(propose['Sirop de test']['rupture'])
        self.assertEqual(propose['Gants de test']['stock_actuel'], 12)

        self._centre_actif(self.yamoussoukro)
        propose = self._liste_proposee(reverse('ordonnance_create_libre'))
        self.assertEqual(propose['Sirop de test']['stock_actuel'], 40)
        self.assertFalse(propose['Sirop de test']['rupture'])
        self.assertTrue(propose['Gants de test']['rupture'])

    def test_les_deux_pharmacies_ne_sont_jamais_additionnees(self):
        """Le défaut d'avant : 0 + 40 = 40, et le sirop paraissait disponible."""
        propose = self._liste_proposee(reverse('ordonnance_create_libre'))
        self.assertNotEqual(propose['Sirop de test']['stock_actuel'], 40)

    def test_les_consommables_sont_prescriptibles(self):
        """Ils étaient exclus : `type='medicament'` en dur des deux côtés."""
        propose = self._liste_proposee(reverse('ordonnance_create_libre'))
        self.assertIn('Gants de test', propose)
        self.assertEqual(propose['Gants de test']['type'], 'consommable')

    def test_les_deux_formulaires_proposent_la_meme_liste(self):
        """Ils partagent le gabarit ; ils partagent maintenant la source."""
        libre = self._liste_proposee(reverse('ordonnance_create_libre'))
        fiche = self._liste_proposee(
            reverse('patients:ordonnance_create', args=[self.patient.pk]))
        self.assertEqual(set(libre), set(fiche))
        self.assertEqual(libre['Gants de test']['stock_actuel'],
                         fiche['Gants de test']['stock_actuel'])

    def test_le_gabarit_rend_les_ruptures_non_cliquables(self):
        reponse = self.client.get(reverse('ordonnance_create_libre'))
        page = reponse.content.decode()
        self.assertIn("med-ac-item:not(.med-ac-rupture)", page)
        self.assertIn(".med-ac-rupture { opacity", page)

    # ── L'enregistrement ───────────────────────────────────────────────────

    def test_un_produit_en_rayon_est_rattache_a_la_ligne(self):
        self._prescrire(self.gants.pk, libre='Gants de test')
        ligne = LigneOrdonnance.objects.latest('pk')
        self.assertEqual(ligne.produit_id, self.gants.pk)
        self.assertEqual(ligne.medicament_libre, '')

    def test_un_produit_en_rupture_est_refuse_par_le_serveur(self):
        """L'écran grise, mais une liste déroulante ne protège de rien."""
        reponse = self._prescrire(self.sirop.pk, libre='Sirop de test')
        ligne = LigneOrdonnance.objects.latest('pk')
        self.assertIsNone(ligne.produit_id)
        self.assertEqual(ligne.medicament_libre, 'Sirop de test')
        avertissements = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('externe' in m for m in avertissements), avertissements)

    def test_le_meme_produit_passe_dans_l_autre_centre(self):
        self._centre_actif(self.yamoussoukro)
        self._prescrire(self.sirop.pk, libre='Sirop de test')
        self.assertEqual(LigneOrdonnance.objects.latest('pk').produit_id, self.sirop.pk)

    def test_le_second_formulaire_applique_la_meme_regle(self):
        url = reverse('patients:ordonnance_create', args=[self.patient.pk])
        self._prescrire(self.gants.pk, libre='Gants de test', url=url)
        self.assertEqual(LigneOrdonnance.objects.latest('pk').produit_id, self.gants.pk)

        self._prescrire(self.sirop.pk, libre='Sirop de test', url=url)
        ligne = LigneOrdonnance.objects.latest('pk')
        self.assertIsNone(ligne.produit_id)
        self.assertEqual(ligne.medicament_libre, 'Sirop de test')

    # ── La pastille de l'en-tête ───────────────────────────────────────────

    def test_la_pastille_d_alerte_compte_le_stock_de_la_pharmacie(self):
        """Elle comptait la table morte, donc zéro — rassurant et faux."""
        from core.context_processors import _medicaments_alerte_count
        from core.middleware import set_current_centre

        self.sirop.stock_alerte = Decimal('10')
        self.sirop.save(update_fields=['stock_alerte'])
        self.gants.stock_alerte = Decimal('5')
        self.gants.save(update_fields=['stock_alerte'])

        set_current_centre(self.toumbokro)     # sirop à 0 ≤ 10, gants à 12 > 5
        try:
            self.assertEqual(_medicaments_alerte_count(), 1)
            set_current_centre(self.yamoussoukro)   # gants à 0 ≤ 5, sirop 40 > 10
            self.assertEqual(_medicaments_alerte_count(), 1)
        finally:
            set_current_centre(None)


class TestOrdonnanceSansConsultation(TestCase):
    """On prescrit et on vend aussi à des gens qui ne sortent pas de chez nous.

    Quelqu'un peut se présenter avec une ordonnance faite ailleurs, ou repartir
    avec une ordonnance externe sans avoir été consulté ici. Le chemin existe —
    `ordonnance_create_libre` — et doit tenir jusqu'à l'impression : c'est
    l'écran de détail et le bon à imprimer qui cassaient, l'un et l'autre en
    lisant encore la table supprimée.
    """

    def setUp(self):
        from employer.models import Employe
        from medecins.models import Medecin
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_libre', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='TestLibre', prenoms='Passant', date_naissance='1985-02-02',
            sexe='F', telephone='0700000002', centre=self.centre)
        self.medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTLIB', prenoms='Prescripteur', date_embauche='2020-01-01'))
        self.produit = Produit.objects.create(
            nom='Comprimé de test', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', self.produit, '30')

    def test_une_ordonnance_se_cree_sans_consultation(self):
        reponse = self.client.post(reverse('ordonnance_create_libre'), {
            'patient_id': self.patient.pk,
            'medecin_id': self.medecin.pk,
            'type_ordonnance': 'externe',
            'medicament[]': str(self.produit.pk),
            'medicament_libre[]': self.produit.nom,
            'posologie[]': '1 le matin',
            'duree[]': '3 jours',
            'quantite[]': '1',
        }, follow=True)
        self.assertEqual(reponse.status_code, 200)

        ordonnance = Ordonnance.objects.latest('pk')
        self.assertIsNone(ordonnance.consultation_id)
        self.assertEqual(ordonnance.patient_id, self.patient.pk)
        self.assertEqual(ordonnance.lignes.first().produit_id, self.produit.pk)

    def test_le_detail_et_l_impression_tiennent_sans_consultation(self):
        ordonnance = Ordonnance.objects.create(
            patient=self.patient, medecin=self.medecin, type_ordonnance='externe')
        LigneOrdonnance.objects.create(
            ordonnance=ordonnance, produit=self.produit,
            posologie='1 le matin', duree='3 jours', quantite=1)

        detail = self.client.get(reverse('ordonnance_detail', args=[ordonnance.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Comprimé de test')

        impression = self.client.get(reverse('ordonnance_print', args=[ordonnance.pk]))
        self.assertEqual(impression.status_code, 200)
        # Le bon visait `ligne.medicament.nom`, un champ que la table supprimée
        # n'avait même pas : la désignation sortait vide sur le papier.
        self.assertContains(impression, 'Comprimé de test')

    def test_le_detail_montre_le_stock_de_la_pharmacie(self):
        """Il affichait `produit.stock_actuel`, la réserve centrale."""
        self.produit.stock_actuel = Decimal('999')      # le magasin
        self.produit.save(update_fields=['stock_actuel'])
        _en_rayon('wale_yamoussoukro', self.produit, '7')   # le comptoir

        ordonnance = Ordonnance.objects.create(
            patient=self.patient, medecin=self.medecin, type_ordonnance='interne')
        LigneOrdonnance.objects.create(
            ordonnance=ordonnance, produit=self.produit,
            posologie='1 le matin', quantite=1)

        page = self.client.get(
            reverse('ordonnance_detail', args=[ordonnance.pk])).content.decode()
        self.assertIn('>7<', page)
        self.assertNotIn('>999<', page)

    def test_la_liste_de_l_admin_supporte_une_ordonnance_libre(self):
        """`get_patient` ne lisait que la consultation, et la page tombait en 500."""
        Ordonnance.objects.create(
            patient=self.patient, medecin=self.medecin, type_ordonnance='externe')
        reponse = self.client.get('/admin/consultations/ordonnance/')
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, 'TestLibre')


class TestListeDesOrdonnances(TestCase):
    """La liste `/ordonnances/` s'affiche et nomme les médicaments.

    Elle tombait en `VariableDoesNotExist` : le gabarit terminait sa cascade par
    `|default:l.medicament`, la table d'avant les deux pharmacies. Un argument de
    filtre n'est pas résolu comme une variable ordinaire — l'échec n'est pas
    silencieux, il remonte et la page entière casse, sur *toutes* les
    ordonnances, pas seulement celles restées en texte libre.
    """

    def setUp(self):
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_liste', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        patient = Patient.objects.create(
            nom='TestListe', prenoms='Patient', date_naissance='1980-03-03',
            sexe='M', telephone='0700000003', centre=self.centre)
        produit = Produit.objects.create(
            nom='Sirop répertorié', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', produit, '20')

        # Une ligne rattachée au stock, une restée en texte libre : les deux
        # branches de la cascade du gabarit.
        ordonnance = Ordonnance.objects.create(patient=patient)
        LigneOrdonnance.objects.create(
            ordonnance=ordonnance, produit=produit, posologie='1 le soir', quantite=1)
        LigneOrdonnance.objects.create(
            ordonnance=ordonnance, medicament_libre='Pommade achetée dehors',
            posologie='matin', quantite=1)

    def test_la_page_s_affiche(self):
        reponse = self.client.get(reverse('ordonnance_list'))
        self.assertEqual(reponse.status_code, 200)

    def test_les_deux_origines_sont_nommees(self):
        page = self.client.get(reverse('ordonnance_list')).content.decode()
        self.assertIn('Sirop répertorié', page)
        self.assertIn('Pommade achetée dehors', page)


class TestToutesLesPagesDuModule(TestCase):
    """Chaque écran du module s'ouvre — le filet qui manquait.

    Deux pages ont cassé coup sur coup après le retrait de l'ancienne table,
    l'écran de dispensation puis la liste, chacune découverte en s'en servant
    parce qu'aucun test ne les ouvrait. Ce test les ouvre toutes, sans rien
    vérifier d'autre que « ça répond ». C'est peu, et c'est exactement ce qui
    aurait suffi à les attraper.
    """

    def setUp(self):
        from employer.models import Employe
        from medecins.models import Medecin
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_smoke', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        patient = Patient.objects.create(
            nom='TestSmoke', prenoms='Patient', date_naissance='1975-04-04',
            sexe='F', telephone='0700000004', centre=self.centre)
        medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTSMOKE', prenoms='Prescripteur', date_embauche='2020-01-01'))
        produit = Produit.objects.create(
            nom='Gélule de test', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', produit, '15')

        self.ordonnance = Ordonnance.objects.create(patient=patient, medecin=medecin)
        LigneOrdonnance.objects.create(
            ordonnance=self.ordonnance, produit=produit,
            posologie='2 par jour', quantite=4)

    def test_chaque_url_du_module_repond(self):
        pages = [
            reverse('ordonnance_list'),
            reverse('ordonnance_create_libre'),
            reverse('ordonnance_detail', args=[self.ordonnance.pk]),
            reverse('ordonnance_print', args=[self.ordonnance.pk]),
            reverse('consultation_search') + '?q=test',
            reverse('medicament_search') + '?q=gel',
            reverse('medicaments_dispo_par_medecin'),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_le_changement_de_statut_repond(self):
        reponse = self.client.post(
            reverse('ordonnance_statut', args=[self.ordonnance.pk]),
            {'statut': 'delivree'}, follow=True)
        self.assertEqual(reponse.status_code, 200)
        self.ordonnance.refresh_from_db()
        self.assertEqual(self.ordonnance.statut, 'delivree')
