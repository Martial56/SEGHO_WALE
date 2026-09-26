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
        """L'écran grise, mais une liste déroulante ne protège de rien.

        La ligne basculait auparavant en texte libre, « à acheter en externe »,
        et l'ordonnance partait quand même — pour se bloquer plus tard à la
        caisse. Une rupture n'est pas prescriptible : rien n'est enregistré.
        """
        avant = LigneOrdonnance.objects.count()
        reponse = self._prescrire(self.sirop.pk, libre='Sirop de test')
        self.assertEqual(LigneOrdonnance.objects.count(), avant)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('rupture' in m for m in refus), refus)
        self.assertTrue(any('Sirop de test' in m for m in refus), refus)

    def test_le_meme_produit_passe_dans_l_autre_centre(self):
        self._centre_actif(self.yamoussoukro)
        self._prescrire(self.sirop.pk, libre='Sirop de test')
        self.assertEqual(LigneOrdonnance.objects.latest('pk').produit_id, self.sirop.pk)

    def test_le_second_formulaire_applique_la_meme_regle(self):
        url = reverse('patients:ordonnance_create', args=[self.patient.pk])
        self._prescrire(self.gants.pk, libre='Gants de test', url=url)
        self.assertEqual(LigneOrdonnance.objects.latest('pk').produit_id, self.gants.pk)

        avant = LigneOrdonnance.objects.count()
        self._prescrire(self.sirop.pk, libre='Sirop de test', url=url)
        self.assertEqual(LigneOrdonnance.objects.count(), avant)

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


class TestUnMessageNeSortQuUneFois(TestCase):
    """Le même message ne s'affiche pas deux fois.

    `base.html` lève déjà un toast pour chaque message Django. Les deux écrans
    d'ordonnance les réaffichaient en plus dans un bandeau : un seul
    `messages.success` arrivait donc en double, le toast qui s'efface et le
    bandeau qui reste. Treize autres gabarits font encore ça ailleurs dans
    l'application — ceux-ci sont réglés.
    """

    def setUp(self):
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_msg', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        patient = Patient.objects.create(
            nom='TestMessage', prenoms='Patient', date_naissance='1979-07-07',
            sexe='M', telephone='0700000007', centre=self.centre)
        self.ordonnance = Ordonnance.objects.create(patient=patient)

    def test_le_message_de_changement_de_statut_n_apparait_qu_une_fois(self):
        page = self.client.post(
            reverse('ordonnance_statut', args=[self.ordonnance.pk]),
            {'statut': 'delivree'}, follow=True).content.decode()
        self.assertEqual(page.count('Statut mis a jour'), 1)

    def test_la_fonction_de_toast_existe_meme_sans_message(self):
        """`window.showToast` n'était défini que s'il y avait un message.

        Sept pages l'appellent derrière un `if (window.showToast)` pour
        signaler une erreur réseau après un rafraîchissement AJAX — c'est-à-dire
        précisément sur des pages sans message Django en attente. L'erreur
        passait donc à la trappe. Le bloc est maintenant rendu partout, seule
        la liste des messages à annoncer se vide.
        """
        page = self.client.get(
            reverse('ordonnance_list')).content.decode()
        self.assertIn('window.showToast = showToast', page)

    def test_le_gabarit_de_detail_ne_reaffiche_plus_les_messages(self):
        from django.template.loader import get_template

        for nom in ('pharmacie/ordonnance/ordonnance_detail.html',
                    'pharmacie/ordonnance/ordonnance_create.html'):
            source = get_template(nom).template.source
            self.assertNotIn('for msg in messages', source, nom)


class TestAucuneOrdonnanceVide(TestCase):
    """Une ordonnance sans médicament n'est pas enregistrée.

    Les trois écrans de prescription créaient l'ordonnance d'abord et
    bouclaient sur les lignes ensuite : un envoi sans médicament laissait une
    coquille en base, dont ni la pharmacie ni la facturation n'ont rien à
    faire. Le cas arrivait tout seul au renouvellement — voir
    [TestRenouvellement] : choisir le prescripteur vidait la grille.
    """

    def setUp(self):
        from employer.models import Employe
        from medecins.models import Medecin
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_vide', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='TestVide', prenoms='Patient', date_naissance='1981-08-08',
            sexe='F', telephone='0700000008', centre=self.centre)
        self.medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTVIDE', prenoms='Prescripteur', date_embauche='2020-01-01'))
        self.produit = Produit.objects.create(
            nom='Sirop du vide', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', self.produit, '30')

    def _post(self, **extra):
        donnees = {
            'patient_id': str(self.patient.pk),
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': '', 'medicament_libre[]': '',
            'posologie[]': '', 'duree[]': '', 'quantite[]': '1',
        }
        donnees.update(extra)
        return self.client.post(
            reverse('ordonnance_create_libre'), donnees, follow=True)

    def test_un_envoi_sans_medicament_ne_cree_rien(self):
        reponse = self._post()
        self.assertEqual(Ordonnance.objects.count(), 0)
        self.assertContains(reponse, "Aucun médicament saisi")

    def test_un_envoi_avec_un_medicament_cree_bien_l_ordonnance(self):
        self._post(**{'medicament[]': str(self.produit.pk),
                      'medicament_libre[]': 'Sirop du vide',
                      'posologie[]': '1 le matin'})
        self.assertEqual(Ordonnance.objects.count(), 1)
        self.assertEqual(Ordonnance.objects.first().lignes.count(), 1)

    def test_un_medicament_sans_posologie_n_est_plus_perdu(self):
        """Deux des trois écrans exigeaient une posologie et jetaient la ligne."""
        self._post(**{'medicament[]': str(self.produit.pk),
                      'medicament_libre[]': 'Sirop du vide'})
        ordonnance = Ordonnance.objects.first()
        self.assertIsNotNone(ordonnance)
        self.assertEqual(ordonnance.lignes.count(), 1)
        self.assertEqual(ordonnance.lignes.first().produit, self.produit)

    def test_la_saisie_survit_a_un_refus(self):
        """Un patient manquant ne doit plus faire perdre les médicaments tapés."""
        reponse = self.client.post(reverse('ordonnance_create_libre'), {
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': str(self.produit.pk),
            'medicament_libre[]': 'Sirop du vide',
            'posologie[]': '1 le matin', 'duree[]': '3 jours', 'quantite[]': '2',
        })
        self.assertContains(reponse, 'Sirop du vide')
        self.assertContains(reponse, '1 le matin')


class TestQuantiteEtDisponibilite(TestCase):
    """On ne valide pas n'importe quoi : la quantité est confrontée au rayon.

    Rien ne rapprochait la quantité demandée du stock. Prescrire 999 d'un
    produit qui en a 50 passait sans un mot, et ne se heurtait à un refus qu'au
    paiement de la facture — patient devant le guichet. La règle vit dans
    `_probleme_de_la_ligne`, partagée par les trois formulaires.
    """

    def setUp(self):
        from employer.models import Employe
        from medecins.models import Medecin
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_qte', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='TestQte', prenoms='Patient', date_naissance='1983-10-10',
            sexe='M', telephone='0700000011', centre=self.centre)
        self.medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTQTE', prenoms='Prescripteur', date_embauche='2020-01-01'))
        self.produit = Produit.objects.create(
            nom='Comprimé compté', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', self.produit, '10')

    def _prescrire(self, quantite, produit_pk=None):
        return self.client.post(reverse('ordonnance_create_libre'), {
            'patient_id': str(self.patient.pk),
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': str(self.produit.pk if produit_pk is None else produit_pk),
            'medicament_libre[]': 'Comprimé compté',
            'posologie[]': '1 le matin', 'duree[]': '', 'quantite[]': str(quantite),
        }, follow=True)

    def test_la_quantite_disponible_passe(self):
        self._prescrire(10)
        self.assertEqual(Ordonnance.objects.count(), 1)
        self.assertEqual(Ordonnance.objects.first().lignes.first().quantite, 10)

    def test_la_quantite_superieure_au_rayon_est_refusee(self):
        reponse = self._prescrire(11)
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('11 demandé(s), 10 en rayon' in m for m in refus), refus)

    def test_le_produit_desactive_est_refuse(self):
        self.produit.actif = False
        self.produit.save(update_fields=['actif'])
        reponse = self._prescrire(1)
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any("n'existe plus au catalogue" in m for m in refus), refus)

    def test_un_produit_inexistant_est_refuse(self):
        reponse = self._prescrire(1, produit_pk=999999)
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any("n'existe plus au catalogue" in m for m in refus), refus)

    def test_une_designation_tapee_sans_selection_est_refusee(self):
        """On sélectionne toujours dans la liste de la pharmacie."""
        reponse = self.client.post(reverse('ordonnance_create_libre'), {
            'patient_id': str(self.patient.pk),
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': '', 'medicament_libre[]': 'Un truc tapé à la main',
            'posologie[]': '1 le matin', 'duree[]': '', 'quantite[]': '1',
        }, follow=True)
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('choisi dans la liste' in m for m in refus), refus)

    def test_la_saisie_revient_apres_le_refus(self):
        reponse = self._prescrire(11)
        self.assertContains(reponse, 'Comprimé compté')
        self.assertContains(reponse, '1 le matin')

    def test_le_refus_montre_quelle_ligne_coince(self):
        """Le message dit quoi, la grille doit dire où.

        Un toast nommant un produit laisse chercher la ligne fautive parmi
        les autres. Elle revient marquée, et l'écran garde le bouton fermé
        tant qu'elle est là.
        """
        reponse = self._prescrire(11)
        self.assertTrue(reponse.context['initial_lignes'][0]['indisponible'])
        # Le nom de classe vit aussi dans le CSS et le JS : c'est la balise
        # de la ligne qu'on regarde, pas l'occurrence du mot dans la page.
        self.assertContains(reponse, '<tr class="line-row line-bloquee">')

    def test_une_ligne_correcte_ne_revient_pas_marquee(self):
        """Refus dû au patient manquant : les lignes, elles, sont bonnes."""
        reponse = self.client.post(reverse('ordonnance_create_libre'), {
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': str(self.produit.pk),
            'medicament_libre[]': 'Comprimé compté',
            'posologie[]': '1 le matin', 'duree[]': '', 'quantite[]': '2',
        })
        self.assertFalse(reponse.context['initial_lignes'][0]['indisponible'])
        self.assertNotContains(reponse, '<tr class="line-row line-bloquee">')


class TestUnProduitUneSeuleLigne(TestCase):
    """Le même produit ne tient que sur une ligne de l'ordonnance.

    Chaque ligne était vérifiée seule : deux lignes de 6 sur un produit qui en
    a 10 passaient toutes les deux, et l'ordonnance en promettait 12. La
    facturation somme bien par produit au paiement — le refus tombait donc
    plus tard, à la caisse.
    """

    def setUp(self):
        from employer.models import Employe
        from medecins.models import Medecin
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_double', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='TestDouble', prenoms='Patient', date_naissance='1984-11-11',
            sexe='F', telephone='0700000012', centre=self.centre)
        self.medecin = Medecin.objects.create(employe=Employe.objects.create(
            nom='TESTDOUBLE', prenoms='Prescripteur', date_embauche='2020-01-01'))
        self.produit = Produit.objects.create(
            nom='Comprimé unique', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        self.autre = Produit.objects.create(
            nom='Sirop voisin', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        _en_rayon('wale_yamoussoukro', self.produit, '10')
        _en_rayon('wale_yamoussoukro', self.autre, '10')

    def _prescrire(self, produits, quantites):
        return self.client.post(reverse('ordonnance_create_libre'), {
            'patient_id': str(self.patient.pk),
            'medecin_id': str(self.medecin.pk),
            'type_ordonnance': 'interne',
            'medicament[]': [str(p.pk) for p in produits],
            'medicament_libre[]': [p.nom for p in produits],
            'posologie[]': ['1 le matin'] * len(produits),
            'duree[]': [''] * len(produits),
            'quantite[]': [str(q) for q in quantites],
        }, follow=True)

    def test_deux_lignes_du_meme_produit_sont_refusees(self):
        reponse = self._prescrire([self.produit, self.produit], [6, 6])
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('est sur 2 lignes' in m for m in refus), refus)
        self.assertTrue(any('12 demandé(s) au total, 10 en rayon' in m
                            for m in refus), refus)

    def test_le_refus_vaut_meme_si_le_total_tient_dans_le_rayon(self):
        """Ce n'est pas une question de stock : c'est une ordonnance à corriger."""
        reponse = self._prescrire([self.produit, self.produit], [2, 3])
        self.assertEqual(Ordonnance.objects.count(), 0)
        refus = [str(m) for m in reponse.context['messages']]
        self.assertTrue(any('regroupez-les' in m for m in refus), refus)

    def test_les_deux_lignes_reviennent_marquees(self):
        reponse = self._prescrire([self.produit, self.produit], [2, 3])
        self.assertEqual(
            [l['indisponible'] for l in reponse.context['initial_lignes']],
            [True, True])

    def test_deux_produits_differents_passent(self):
        self._prescrire([self.produit, self.autre], [2, 3])
        self.assertEqual(Ordonnance.objects.count(), 1)
        self.assertEqual(Ordonnance.objects.first().lignes.count(), 2)


class TestValiditeDeLOrdonnance(TestCase):
    """Une ordonnance naît valable cinq jours, pas le jour même.

    Le formulaire préremplissait la date d'expiration avec la date du jour :
    le bon imprimé annonçait « Validité : jusqu'au [aujourd'hui] », donc périmé
    dès le lendemain. Personne ne s'en plaignait parce que le statut
    « expirée » n'est appliqué nulle part automatiquement — l'écran de
    dispensation ne regarde pas la date.
    """

    def setUp(self):
        from patients.models import Patient

        self.centre = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]
        self.user = User.objects.create_superuser('su_validite', password='x')
        profil = self.user.profile
        profil.centres.add(self.centre)
        profil.centre_actif = self.centre
        profil.save(update_fields=['centre_actif'])
        self.client = Client()
        self.client.force_login(self.user)

        self.patient = Patient.objects.create(
            nom='TestValid', prenoms='Patient', date_naissance='1986-12-12',
            sexe='M', telephone='0700000013', centre=self.centre)

    def test_le_formulaire_propose_cinq_jours(self):
        from consultations.models import (VALIDITE_ORDONNANCE_JOURS,
                                          date_expiration_par_defaut)

        self.assertEqual(VALIDITE_ORDONNANCE_JOURS, 5)
        reponse = self.client.get(reverse('ordonnance_create_libre'))
        attendu = date_expiration_par_defaut().strftime('%Y-%m-%d')
        self.assertContains(
            reponse, f'name="date_expiration" class="ord-input" value="{attendu}"')

    def test_la_date_proposee_est_bien_dans_cinq_jours(self):
        from datetime import date, timedelta

        from consultations.models import date_expiration_par_defaut

        self.assertEqual(date_expiration_par_defaut(),
                         date.today() + timedelta(days=5))

    def test_une_ordonnance_creee_sans_date_prend_la_valeur_par_defaut(self):
        """Le défaut du modèle couvre l'admin et toute création par le code."""
        from consultations.models import date_expiration_par_defaut

        ordonnance = Ordonnance.objects.create(patient=self.patient)
        self.assertEqual(ordonnance.date_expiration, date_expiration_par_defaut())
