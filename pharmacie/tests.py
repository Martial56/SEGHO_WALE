from decimal import Decimal

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from core.middleware import _locals
from stock.models import Produit, DemandePharmacie, LigneDemande

from .models import (
    StockPharmacie, MouvementPharmacie, VentePharmacie, LigneVente,
    InventairePharmacie, LigneInventairePharmacie,
)
from .views import can_view_rapport_financier


# ─── Helpers de création ───────────────────────────────────────────────────────

def _produit(suffix=''):
    return Produit.objects.create(
        nom=f'Médoc{suffix}', type='medicament',
        prix_achat=Decimal('100'), prix_vente=Decimal('500'),
    )


def _stock_pharmacie(pharmacie='wale_toumbokro', produit=None, quantite=Decimal('10')):
    # Un signal (pharmacie.signals) crée déjà une ligne StockPharmacie à quantité 0
    # pour chaque pharmacie dès qu'un Produit est créé — on la met simplement à jour.
    sp, _ = StockPharmacie.objects.get_or_create(pharmacie=pharmacie, produit=produit or _produit())
    sp.quantite = quantite
    sp.save(update_fields=['quantite'])
    return sp


def _groupe_user(username, groupe_nom):
    """Utilisateur membre d'un groupe — qui ne lui accorde aucun droit en soi.

    Le module s'appuyait sur des noms de groupes attendus en dur ; depuis la
    migration 0009 il lit des permissions Django. Appartenir à un groupe nommé
    « Caisse » ne suffit donc plus : c'est la permission qui ouvre la porte.
    """
    user = User.objects.create_user(username, password='x')
    groupe, _ = Group.objects.get_or_create(name=groupe_nom)
    user.groups.add(groupe)
    return user


def _user_avec_permissions(username, *codes, centre_code='TOUMBOKRO'):
    """Utilisateur portant les permissions nommées, rattaché à un centre.

    Les écrans de pharmacie posent deux verrous, et il faut les deux : la
    permission Django, et le fait que le centre actif de la personne soit celui
    dont dépend la pharmacie ouverte (`peut_acceder_pharmacie`). Un utilisateur
    sans centre actif se voit refuser Toumbokro comme Yamoussoukro.
    """
    from centres.models import Centre

    user = User.objects.create_user(username, password='x')
    for code in codes:
        user.user_permissions.add(Permission.objects.get(
            codename=code, content_type__app_label='pharmacie'))
    if centre_code:
        centre = Centre.objects.get(code=centre_code)
        profil = user.profile
        profil.centres.add(centre)
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])
    # `has_perm` mémorise ses résultats sur l'instance : sans cette relecture,
    # un utilisateur interrogé avant l'ajout resterait refusé.
    return User.objects.get(pk=user.pk)


def _reset_current_user():
    _locals.current_user = None


RAPPORT_URLS = ['pharmacie_rapport_journalier', 'pharmacie_rapport_mensuel', 'pharmacie_rapport_dispensation']


# ─── Tests can_view_rapport_financier ───────────────────────────────────────────

class TestCanViewRapportFinancier(TestCase):

    def test_superuser_autorise(self):
        su = User.objects.create_superuser('su_cvrf', password='x')
        self.assertTrue(can_view_rapport_financier(su))

    def test_user_sans_groupe_refuse(self):
        user = User.objects.create_user('u_cvrf', password='x')
        self.assertFalse(can_view_rapport_financier(user))

    def test_la_permission_ouvre_le_rapport(self):
        user = _user_avec_permissions('u_cvrf_perm', 'voir_rapport_financier_pharmacie')
        self.assertTrue(can_view_rapport_financier(user))

    def test_le_nom_du_groupe_ne_suffit_pas(self):
        """Le test attendait l'inverse, et décrivait la règle d'avant 0009.

        Le module exigeait l'appartenance à un groupe nommé « Caisse »,
        « Pharmacien », « Administrateur » ou « Directeur » — quatre noms écrits
        en dur, qu'il fallait créer à l'identique pour ouvrir quoi que ce soit.
        Une permission Django se coche sur l'utilisateur ou sur le groupe de son
        choix, et le nom du groupe n'a plus d'importance.
        """
        for i, groupe in enumerate(['Caisse', 'Pharmacien', 'Administrateur', 'Accueil']):
            user = _groupe_user(f'u_cvrf_{i}', groupe)
            self.assertFalse(can_view_rapport_financier(user),
                             f"{groupe} ne devrait rien ouvrir sans la permission")


# ─── Tests des vues de rapports : autorisations HTTP ───────────────────────────

class TestVuesRapportsPermissions(TestCase):

    def tearDown(self):
        _reset_current_user()

    def test_rapports_refuses_sans_groupe_autorise(self):
        User.objects.create_user('u_vrp_plain', password='x')
        client = Client()
        client.login(username='u_vrp_plain', password='x')
        for name in RAPPORT_URLS:
            resp = client.get(reverse(name, kwargs={'pharmacie': 'wale_toumbokro'}))
            self.assertEqual(resp.status_code, 403,
                             f"{name} devrait refuser un utilisateur sans groupe autorisé")

    def test_rapports_autorises_par_la_permission(self):
        _user_avec_permissions('u_vrp_perm', 'voir_rapport_financier_pharmacie')
        client = Client()
        client.login(username='u_vrp_perm', password='x')
        for name in RAPPORT_URLS:
            resp = client.get(reverse(name, kwargs={'pharmacie': 'wale_toumbokro'}))
            self.assertEqual(resp.status_code, 200,
                             f"{name} devrait s'ouvrir avec la permission")


# ─── Tests calculs (montant_net, montant ligne, ecart) ─────────────────────────

class TestCalculsPharmacie(TestCase):

    def test_vente_montant_net_calcule_a_la_sauvegarde(self):
        vente = VentePharmacie.objects.create(
            pharmacie='wale_toumbokro', montant_total=Decimal('10000'), remise=Decimal('1000'),
        )
        self.assertEqual(vente.montant_net, Decimal('9000'))

    def test_ligne_vente_montant_calcule_a_la_sauvegarde(self):
        vente = VentePharmacie.objects.create(pharmacie='wale_toumbokro', montant_total=Decimal('0'))
        ligne = LigneVente.objects.create(
            vente=vente, produit=_produit('LV'), quantite=Decimal('3'), prix_unitaire=Decimal('500'),
        )
        self.assertEqual(ligne.montant, Decimal('1500'))

    def test_ligne_inventaire_pharmacie_ecart(self):
        inv = InventairePharmacie.objects.create(pharmacie='wale_toumbokro', date_inventaire=timezone.now().date())
        ligne = LigneInventairePharmacie.objects.create(
            inventaire=inv, produit=_produit('LIP'),
            stock_theorique=Decimal('10'), stock_reel=Decimal('7'),
        )
        self.assertEqual(ligne.ecart, Decimal('-3'))


# ─── Tests génération de numéros uniques ───────────────────────────────────────

class TestNumerosUniques(TestCase):

    def test_format_numero_vente(self):
        annee = timezone.now().year
        vente = VentePharmacie.objects.create(pharmacie='wale_toumbokro', montant_total=Decimal('1000'))
        self.assertTrue(vente.numero.startswith(f'VNT{annee}'),
                        f"Attendu préfixe VNT{annee}, obtenu {vente.numero}")

    def test_deux_ventes_numeros_distincts(self):
        v1 = VentePharmacie.objects.create(pharmacie='wale_toumbokro', montant_total=Decimal('1000'))
        v2 = VentePharmacie.objects.create(pharmacie='wale_toumbokro', montant_total=Decimal('1000'))
        self.assertNotEqual(v1.numero, v2.numero)

    def test_format_numero_inventaire_pharmacie(self):
        annee = timezone.now().year
        inv = InventairePharmacie.objects.create(pharmacie='wale_toumbokro', date_inventaire=timezone.now().date())
        self.assertTrue(inv.numero.startswith(f'INV-PH{annee}'),
                        f"Attendu préfixe INV-PH{annee}, obtenu {inv.numero}")


# ─── Tests mouvements de stock pharmacie via les vues ──────────────────────────

class TestStockMovementViews(TestCase):

    def tearDown(self):
        _reset_current_user()

    def test_vente_diminue_stock_pharmacie_et_cree_mouvement(self):
        produit = _produit('VTE')
        sp = _stock_pharmacie('wale_toumbokro', produit, Decimal('10'))
        _user_avec_permissions('u_vte', 'gerer_stock_pharmacie',
                               'valider_vente_pharmacie')
        client = Client()
        client.login(username='u_vte', password='x')
        resp = client.post(reverse('pharmacie_caisse', kwargs={'pharmacie': 'wale_toumbokro'}), {
            'mode_paiement': 'especes', f'qte_{produit.pk}': '4',
        })
        self.assertEqual(resp.status_code, 302)
        sp.refresh_from_db()
        self.assertEqual(sp.quantite, Decimal('6'))
        self.assertTrue(MouvementPharmacie.objects.filter(produit=produit, type='vente').exists())

    def test_confirmation_livraison_augmente_stock_pharmacie(self):
        produit = _produit('LIV')
        demande = DemandePharmacie.objects.create(pharmacie='wale_toumbokro', statut='en_livraison')
        ligne = LigneDemande.objects.create(
            demande=demande, produit=produit,
            quantite_demandee=Decimal('10'), quantite_approuvee=Decimal('8'),
        )
        _user_avec_permissions('u_liv', 'gerer_stock_pharmacie')
        client = Client()
        client.login(username='u_liv', password='x')
        resp = client.post(
            reverse('pharmacie_confirmer_livraison', kwargs={'pharmacie': 'wale_toumbokro', 'pk': demande.pk}),
            {f'recu_{ligne.pk}': '8'},
        )
        self.assertEqual(resp.status_code, 302)
        sp = StockPharmacie.objects.get(pharmacie='wale_toumbokro', produit=produit)
        self.assertEqual(sp.quantite, Decimal('8'))
        demande.refresh_from_db()
        self.assertEqual(demande.statut, 'approuvee')


# ─── La règle partagée : ce que la pharmacie du centre actif a en rayon ────────

class TestDisponibiliteParCentre(TestCase):
    """Un produit ne se propose que là où il y en a.

    La prescription additionnait jusqu'ici le stock des deux pharmacies dès
    qu'elle n'arrivait pas à rattacher le médecin à un centre — c'est-à-dire
    toujours, aucun des 59 médecins n'ayant de compte utilisateur. Un
    prescripteur de Toumbokro se voyait donc proposer ce qui dort à
    Yamoussoukro, à quarante kilomètres.
    """

    def setUp(self):
        from centres.models import Centre

        self.toumbokro = Centre.objects.get_or_create(
            code='TOUMBOKRO', defaults={'nom': 'CMS WALE Toumbokro'})[0]
        self.yamoussoukro = Centre.objects.get_or_create(
            code='WALE', defaults={'nom': 'CMS WALE Yamoussoukro'})[0]

        self.sirop = Produit.objects.create(
            nom='Sirop de test', type='medicament',
            prix_achat=Decimal('100'), prix_vente=Decimal('500'))
        self.gants = Produit.objects.create(
            nom='Gants de test', type='consommable',
            prix_achat=Decimal('50'), prix_vente=Decimal('200'))
        self.tensiometre = Produit.objects.create(
            nom='Tensiomètre de test', type='equipement',
            prix_achat=Decimal('9000'), prix_vente=Decimal('15000'))

        # Toumbokro a des gants mais plus de sirop ; Yamoussoukro a les deux.
        _stock_pharmacie('wale_toumbokro', self.sirop, Decimal('0'))
        _stock_pharmacie('wale_toumbokro', self.gants, Decimal('12'))
        _stock_pharmacie('wale_yamoussoukro', self.sirop, Decimal('40'))
        _stock_pharmacie('wale_yamoussoukro', self.gants, Decimal('5'))

    # ── Rattachement ───────────────────────────────────────────────────────

    def test_chaque_centre_a_sa_pharmacie(self):
        from .disponibilite import pharmacie_du_centre

        self.assertEqual(pharmacie_du_centre(self.toumbokro), 'wale_toumbokro')
        self.assertEqual(pharmacie_du_centre(self.yamoussoukro), 'wale_yamoussoukro')

    def test_un_centre_sans_pharmacie_ne_propose_rien(self):
        """Mieux vaut une liste vide que celle d'un autre centre."""
        from centres.models import Centre

        from .disponibilite import pharmacie_du_centre, produits_de_la_pharmacie

        ailleurs = Centre.objects.create(nom='CMS Ailleurs', code='AILLEURS')
        self.assertIsNone(pharmacie_du_centre(ailleurs))
        self.assertEqual(produits_de_la_pharmacie(None).count(), 0)

    # ── Le stock proposé est celui de la pharmacie, pas du magasin ──────────

    def test_le_stock_affiche_est_celui_de_la_pharmacie(self):
        from .disponibilite import produits_de_la_pharmacie

        par_nom = {p.nom: p.stock_pharma
                   for p in produits_de_la_pharmacie('wale_toumbokro')}
        self.assertEqual(par_nom['Sirop de test'], Decimal('0'))
        self.assertEqual(par_nom['Gants de test'], Decimal('12'))

        par_nom = {p.nom: p.stock_pharma
                   for p in produits_de_la_pharmacie('wale_yamoussoukro')}
        self.assertEqual(par_nom['Sirop de test'], Decimal('40'))
        self.assertEqual(par_nom['Gants de test'], Decimal('5'))

    def test_les_deux_pharmacies_ne_sont_jamais_additionnees(self):
        """Le défaut d'avant : 0 + 40 donnait 40, et le sirop paraissait dispo."""
        from .disponibilite import produits_de_la_pharmacie

        toumbokro = {p.nom: p.stock_pharma
                     for p in produits_de_la_pharmacie('wale_toumbokro')}
        self.assertNotEqual(toumbokro['Sirop de test'], Decimal('40'))
        self.assertEqual(toumbokro['Sirop de test'], Decimal('0'))

    # ── Ce qui est proposé, et ce qui est grisé ─────────────────────────────

    def test_les_consommables_sont_proposes_avec_les_medicaments(self):
        """C'est leur absence qui a lancé ce chantier — les gants d'un examen."""
        from .disponibilite import produits_de_la_pharmacie

        noms = {p.nom for p in produits_de_la_pharmacie('wale_toumbokro')}
        self.assertIn('Sirop de test', noms)
        self.assertIn('Gants de test', noms)

    def test_les_equipements_ne_sont_pas_proposes(self):
        from .disponibilite import produits_de_la_pharmacie

        noms = {p.nom for p in produits_de_la_pharmacie('wale_toumbokro')}
        self.assertNotIn('Tensiomètre de test', noms)

    def test_une_rupture_reste_visible_mais_sort_des_disponibles(self):
        """Grisé et non effacé : cacher le produit ferait croire qu'il n'existe pas."""
        from .disponibilite import produits_de_la_pharmacie

        visibles = {p.nom for p in produits_de_la_pharmacie('wale_toumbokro')}
        servables = {p.nom for p in produits_de_la_pharmacie(
            'wale_toumbokro', disponibles_seulement=True)}

        self.assertIn('Sirop de test', visibles)
        self.assertNotIn('Sirop de test', servables)
        self.assertIn('Gants de test', servables)

    def test_un_produit_jamais_recu_se_presente_comme_une_rupture(self):
        """Pour le patient, « jamais reçu » et « épuisé » veulent dire pareil."""
        from .disponibilite import produits_de_la_pharmacie

        inedit = Produit.objects.create(
            nom='Produit jamais livré', type='medicament',
            prix_achat=Decimal('10'), prix_vente=Decimal('30'))
        StockPharmacie.objects.filter(produit=inedit).delete()

        par_nom = {p.nom: p.stock_pharma
                   for p in produits_de_la_pharmacie('wale_toumbokro')}
        self.assertIn('Produit jamais livré', par_nom)
        self.assertEqual(par_nom['Produit jamais livré'], Decimal('0'))

    # ── Le garde-fou du serveur ─────────────────────────────────────────────

    def test_le_serveur_refuse_ce_que_la_pharmacie_n_a_pas(self):
        """L'écran grise, mais une liste déroulante ne protège de rien."""
        from .disponibilite import est_disponible

        self.assertFalse(est_disponible(self.sirop.pk, 'wale_toumbokro'))
        self.assertTrue(est_disponible(self.sirop.pk, 'wale_yamoussoukro'))

    def test_le_serveur_refuse_plus_que_le_rayon_ne_contient(self):
        from .disponibilite import est_disponible

        self.assertTrue(est_disponible(self.gants.pk, 'wale_toumbokro', 12))
        self.assertFalse(est_disponible(self.gants.pk, 'wale_toumbokro', 13))

    def test_le_serveur_refuse_les_demandes_absurdes(self):
        from .disponibilite import est_disponible

        self.assertFalse(est_disponible(self.gants.pk, 'wale_toumbokro', 0))
        self.assertFalse(est_disponible(self.gants.pk, 'wale_toumbokro', -3))
        self.assertFalse(est_disponible(self.gants.pk, 'wale_toumbokro', 'beaucoup'))
        self.assertFalse(est_disponible(None, 'wale_toumbokro'))
        self.assertFalse(est_disponible(self.gants.pk, None))


class TestAncienneChaineSupprimee(TestCase):
    """La chaîne du 9 mai 2026 n'existe plus.

    `CategorieMedicament`, `Medicament`, `LotMedicament` et un `MouvementStock`
    homonyme de celui de l'app `stock` avaient été écrits quand le déploiement
    n'avait qu'une pharmacie : un seul `stock_actuel` par médicament, sans
    notion de centre. La réécriture du 30 mai leur a substitué `stock.Produit`
    et `StockPharmacie`, mais l'ancienne est restée branchée quatre mois sur les
    ordonnances, avec des prix qui avaient divergé.
    """

    MODELES_SUPPRIMES = ('medicament', 'lotmedicament', 'mouvementstock',
                         'categoriemedicament')

    def test_les_modeles_n_existent_plus(self):
        from django.apps import apps

        restants = {m.__name__ for m in apps.get_app_config('pharmacie').get_models()}
        for nom in ('Medicament', 'LotMedicament', 'CategorieMedicament'):
            self.assertNotIn(nom, restants)

    def test_le_doublon_de_nom_mouvementstock_est_leve(self):
        """Deux classes portaient ce nom, une par app. Il n'en reste qu'une."""
        from django.apps import apps

        porteurs = [m._meta.label for m in apps.get_models()
                    if m.__name__ == 'MouvementStock']
        self.assertEqual(porteurs, ['stock.MouvementStock'])

    def test_les_lignes_ne_pointent_plus_vers_la_table_morte(self):
        from consultations.models import LigneOrdonnance

        from facturation.models import LigneFacture

        for modele in (LigneOrdonnance, LigneFacture):
            champs = {f.name for f in modele._meta.get_fields()}
            self.assertNotIn('medicament', champs, modele.__name__)

        # La ligne d'ordonnance garde bien son lien vers le catalogue vivant.
        self.assertIn('produit', {f.name for f in LigneOrdonnance._meta.get_fields()})

    def test_les_permissions_orphelines_sont_parties(self):
        """Sans ce nettoyage, deux « mouvement de stock » cohabiteraient dans l'admin."""
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        self.assertEqual(ContentType.objects.filter(
            app_label='pharmacie', model__in=self.MODELES_SUPPRIMES).count(), 0)
        self.assertEqual(Permission.objects.filter(
            content_type__app_label='pharmacie',
            content_type__model__in=self.MODELES_SUPPRIMES).count(), 0)
        # Celles de l'app stock, elles, sont intactes.
        self.assertTrue(ContentType.objects.filter(
            app_label='stock', model='mouvementstock').exists())


class TestEcranDeDispensation(TestCase):
    """L'écran « Dispenser » d'une ordonnance s'ouvre.

    Il ne s'ouvrait plus : la vue demandait encore `select_related('medicament')`
    sur les lignes d'ordonnance, un champ retiré en même temps que l'ancienne
    table `pharmacie.Medicament`. Django lève alors un `FieldError` et la page
    répond 500 — sans qu'aucun test ne s'en aperçoive, l'écran n'étant couvert
    par rien. C'est ce que ce test garde désormais.
    """

    def setUp(self):
        from centres.models import Centre
        from consultations.models import LigneOrdonnance, Ordonnance
        from patients.models import Patient

        _reset_current_user()
        centre = Centre.objects.get(code='TOUMBOKRO')
        patient = Patient.objects.create(
            nom='Dispense', prenoms='Patient', date_naissance='1990-06-01',
            sexe='M', telephone='0700000000', centre=centre,
        )
        self.produit = _produit('_disp')
        _stock_pharmacie('wale_toumbokro', self.produit, Decimal('10'))
        self.ordonnance = Ordonnance.objects.create(patient=patient, statut='emise')
        LigneOrdonnance.objects.create(
            ordonnance=self.ordonnance, produit=self.produit,
            posologie='1 matin et soir', quantite=2,
        )
        self.user = _user_avec_permissions(
            'u_dispense', 'gerer_stock_pharmacie', centre_code='TOUMBOKRO')
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        _reset_current_user()

    def _url(self):
        return reverse('pharmacie_dispenser',
                       args=['wale_toumbokro', self.ordonnance.pk])

    def test_la_page_s_ouvre(self):
        reponse = self.client.get(self._url())
        self.assertEqual(reponse.status_code, 200)

    def test_la_ligne_et_son_stock_sont_affiches(self):
        reponse = self.client.get(self._url())
        self.assertContains(reponse, self.produit.nom)
        # Le stock de la pharmacie couvre les 2 unités prescrites.
        self.assertEqual(
            [l['suffisant'] for l in reponse.context['lignes_enrichies']], [True])

    def test_la_validation_sort_le_stock_et_marque_l_ordonnance(self):
        self.client.post(self._url(), {f'qte_{self.ordonnance.lignes.first().pk}': '2'})
        self.ordonnance.refresh_from_db()
        self.assertEqual(self.ordonnance.statut, 'delivree')
        self.assertEqual(
            StockPharmacie.objects.get(
                pharmacie='wale_toumbokro', produit=self.produit).quantite,
            Decimal('8'))


class TestToutesLesPagesDeLaPharmacie(TestCase):
    """Chaque écran de la pharmacie s'ouvre.

    Trois pages ont cassé coup sur coup après le retrait de l'ancienne table —
    la dispensation, la liste des ordonnances, puis la liste du jour — toutes
    découvertes en s'en servant, faute d'un test qui les ouvre. Celui-ci ne
    vérifie rien d'autre que « ça répond » : c'est peu, mais c'est ce qui
    manquait.
    """

    PHARMACIE = 'wale_yamoussoukro'

    def setUp(self):
        from centres.models import Centre
        from consultations.models import LigneOrdonnance, Ordonnance
        from patients.models import Patient

        _reset_current_user()
        centre = Centre.objects.get(code='WALE')
        self.user = User.objects.create_superuser('su_pharma_smoke', password='x')
        profil = self.user.profile
        profil.centres.add(centre)
        profil.centre_actif = centre
        profil.save(update_fields=['centre_actif'])

        self.client = Client()
        self.client.force_login(self.user)

        patient = Patient.objects.create(
            nom='TestPharma', prenoms='Patient', date_naissance='1988-05-05',
            sexe='M', telephone='0700000005', centre=centre)
        produit = _produit('_smoke')
        _stock_pharmacie(self.PHARMACIE, produit, Decimal('20'))
        self.ordonnance = Ordonnance.objects.create(patient=patient, statut='emise')
        LigneOrdonnance.objects.create(
            ordonnance=self.ordonnance, produit=produit,
            posologie='1 par jour', quantite=3)

    def tearDown(self):
        _reset_current_user()

    def test_chaque_ecran_repond(self):
        sans_argument = ['pharmacie_accueil']
        par_pharmacie = [
            'pharmacie_dashboard', 'pharmacie_stock', 'pharmacie_ordonnances',
            'pharmacie_demande', 'pharmacie_journal', 'pharmacie_caisse',
            'pharmacie_recette', 'pharmacie_rapport_journalier',
            'pharmacie_livraisons', 'pharmacie_alertes_reappro',
            'pharmacie_peremptions', 'pharmacie_retours',
            'pharmacie_inventaire_list', 'pharmacie_rapport_mensuel',
            'pharmacie_rapport_dispensation', 'pharmacie_comparaison',
            'pharmacie_import_stock_initial',
        ]
        urls = [reverse(nom) for nom in sans_argument]
        urls += [reverse(nom, args=[self.PHARMACIE]) for nom in par_pharmacie]
        urls.append(reverse('pharmacie_dispenser',
                            args=[self.PHARMACIE, self.ordonnance.pk]))

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
