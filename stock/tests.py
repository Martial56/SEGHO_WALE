from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from achats.models import Fournisseur
from core.middleware import _locals

from .models import (
    Produit, LotProduit, CommandeStock, LigneCommande, Inventaire,
    LigneInventaire, DemandePharmacie, LigneDemande, FicheBesoins,
    LigneFicheBesoins,
)


# ─── Helpers de création ───────────────────────────────────────────────────────

def _produit(type_='medicament', suffix='', **kwargs):
    defaults = dict(
        nom=f'Produit{suffix}', type=type_,
        stock_actuel=Decimal('0'), stock_alerte=Decimal('10'), stock_minimum=Decimal('5'),
        prix_achat=Decimal('100'), prix_vente=Decimal('200'),
    )
    defaults.update(kwargs)
    return Produit.objects.create(**defaults)


def _fournisseur(suffix=''):
    return Fournisseur.objects.create(nom=f'Fournisseur{suffix}', telephone='0700000000')


def _commande(fournisseur=None, statut='brouillon'):
    return CommandeStock.objects.create(fournisseur=fournisseur or _fournisseur(), statut=statut)


def _fiche():
    today = timezone.now().date()
    return FicheBesoins.objects.create(periode_debut=today, periode_fin=today)


def _reset_current_user():
    _locals.current_user = None


# ─── Tests génération de numéros/codes uniques ─────────────────────────────────

class TestNumerosUniques(TestCase):

    def test_produit_code_prefixes_par_type(self):
        annee = timezone.now().year
        for type_, prefix in [('medicament', 'MED'), ('consommable', 'CONS'), ('equipement', 'EQP')]:
            p = _produit(type_=type_, suffix=type_)
            self.assertTrue(p.code.startswith(f'{prefix}{annee}'),
                            f"Code '{p.code}' devrait commencer par '{prefix}{annee}'")

    def test_deux_produits_meme_type_codes_distincts(self):
        p1 = _produit(suffix='A')
        p2 = _produit(suffix='B')
        self.assertNotEqual(p1.code, p2.code)

    def test_formats_numeros_commande_demande_fiche_inventaire(self):
        annee = timezone.now().year
        commande = _commande()
        self.assertTrue(commande.numero.startswith(f'CMD{annee}'),
                        f"Attendu préfixe CMD{annee}, obtenu {commande.numero}")
        demande = DemandePharmacie.objects.create(pharmacie='wale_toumbokro')
        self.assertTrue(demande.numero.startswith(f'DEM{annee}'),
                        f"Attendu préfixe DEM{annee}, obtenu {demande.numero}")
        fiche = _fiche()
        self.assertTrue(fiche.numero.startswith(f'FB{annee}'),
                        f"Attendu préfixe FB{annee}, obtenu {fiche.numero}")
        inv = Inventaire.objects.create()
        self.assertTrue(inv.numero.startswith(f'INV{annee}'),
                        f"Attendu préfixe INV{annee}, obtenu {inv.numero}")


# ─── Tests logique Produit (états de stock, validations) ──────────────────────

class TestProduitLogique(TestCase):

    def test_en_rupture_et_en_alerte(self):
        rupture = _produit(suffix='R', stock_actuel=Decimal('0'), stock_alerte=Decimal('10'))
        self.assertTrue(rupture.en_rupture)
        self.assertFalse(rupture.en_alerte)

        alerte = _produit(suffix='AL', stock_actuel=Decimal('5'), stock_alerte=Decimal('10'))
        self.assertFalse(alerte.en_rupture)
        self.assertTrue(alerte.en_alerte)

        ok = _produit(suffix='OK', stock_actuel=Decimal('50'), stock_alerte=Decimal('10'))
        self.assertFalse(ok.en_rupture)
        self.assertFalse(ok.en_alerte)

    def test_clean_stock_minimum_doit_etre_inferieur_alerte(self):
        p = Produit(nom='Test', type='medicament',
                    stock_minimum=Decimal('10'), stock_alerte=Decimal('10'))
        with self.assertRaises(ValidationError):
            p.clean()

    def test_clean_prix_vente_ne_peut_pas_etre_inferieur_achat(self):
        p = Produit(nom='Test', type='medicament',
                    prix_achat=Decimal('1000'), prix_vente=Decimal('500'))
        with self.assertRaises(ValidationError):
            p.clean()


# ─── Tests calculs (LigneCommande.montant, LigneInventaire.ecart) ─────────────

class TestLigneCommandeEtInventaire(TestCase):

    def test_montant_ligne_commande(self):
        commande = _commande()
        produit = _produit(suffix='LC')
        ligne = LigneCommande.objects.create(
            commande=commande, produit=produit,
            quantite_commandee=Decimal('3'), prix_unitaire=Decimal('1500'),
        )
        self.assertEqual(ligne.montant, Decimal('4500'))

    def test_ecart_ligne_inventaire_calcule_automatiquement(self):
        inv = Inventaire.objects.create()
        excedent = LigneInventaire.objects.create(
            inventaire=inv, produit=_produit(suffix='LI1'),
            stock_theorique=Decimal('10'), stock_reel=Decimal('15'),
        )
        self.assertEqual(excedent.ecart, Decimal('5'))

        manque = LigneInventaire.objects.create(
            inventaire=inv, produit=_produit(suffix='LI2'),
            stock_theorique=Decimal('10'), stock_reel=Decimal('4'),
        )
        self.assertEqual(manque.ecart, Decimal('-6'))


# ─── Tests LigneFicheBesoins (stock_disponible, validation) ───────────────────

class TestLigneFicheBesoins(TestCase):

    def test_stock_disponible(self):
        fiche = _fiche()
        ligne = LigneFicheBesoins.objects.create(
            fiche=fiche, produit=_produit(suffix='FB1'),
            stock_initial=Decimal('20'), qte_recue=Decimal('5'), qte_dispensee=Decimal('8'),
        )
        self.assertEqual(ligne.stock_disponible, Decimal('17'))

    def test_clean_qte_accordee_superieure_a_commander_refuse(self):
        fiche = _fiche()
        ligne = LigneFicheBesoins(
            fiche=fiche, produit=_produit(suffix='FB2'),
            qte_commander=Decimal('10'), qte_accordee=Decimal('15'),
        )
        with self.assertRaises(ValidationError):
            ligne.clean()


# ─── Tests vue mouvement_create (mouvements de stock) ──────────────────────────

class TestMouvementStockView(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('u_mvt', password='x')
        self.client = Client()
        self.client.login(username='u_mvt', password='x')

    def tearDown(self):
        _reset_current_user()

    def test_entree_augmente_le_stock(self):
        produit = _produit(suffix='ME', stock_actuel=Decimal('10'))
        resp = self.client.post(reverse('stock_mouvement_create'), {
            'produit': produit.pk, 'type': 'entree', 'motif': 'achat', 'quantite': '5',
        })
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('15'))

    def test_sortie_ne_descend_pas_sous_zero(self):
        produit = _produit(suffix='MS', stock_actuel=Decimal('5'))
        resp = self.client.post(reverse('stock_mouvement_create'), {
            'produit': produit.pk, 'type': 'peremption', 'motif': 'peremption', 'quantite': '20',
        })
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('0'))

    def test_ajustement_definit_stock_exact(self):
        produit = _produit(suffix='MA', stock_actuel=Decimal('10'))
        resp = self.client.post(reverse('stock_mouvement_create'), {
            'produit': produit.pk, 'type': 'ajustement', 'motif': 'inventaire', 'quantite': '7',
        })
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('7'))


# ─── Tests vue commande_receptionner (réception commande → lot + stock) ───────

class TestCommandeReceptionnerView(TestCase):

    def tearDown(self):
        _reset_current_user()

    def test_reception_cree_lot_augmente_stock_et_passe_statut_recu(self):
        produit = _produit(suffix='CR', stock_actuel=Decimal('0'))
        commande = _commande(statut='envoye')
        ligne = LigneCommande.objects.create(
            commande=commande, produit=produit,
            quantite_commandee=Decimal('10'), prix_unitaire=Decimal('500'),
        )
        user = User.objects.create_user('u_cr', password='x')
        client = Client()
        client.login(username='u_cr', password='x')
        resp = client.post(
            reverse('stock_commande_receptionner', kwargs={'pk': commande.pk}),
            {f'recu_{ligne.pk}': '10'},
        )
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        commande.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('10'))
        self.assertEqual(commande.statut, 'recu')
        self.assertTrue(LotProduit.objects.filter(produit=produit).exists())


# ─── Tests vue dotation_valider (approbation/refus des demandes pharmacie) ────

class TestDotationValiderView(TestCase):

    def setUp(self):
        self.user = User.objects.create_user('u_dv', password='x')
        self.client = Client()
        self.client.login(username='u_dv', password='x')

    def tearDown(self):
        _reset_current_user()

    def test_approuver_deduit_stock_et_passe_en_livraison(self):
        produit = _produit(suffix='DVA', stock_actuel=Decimal('20'))
        demande = DemandePharmacie.objects.create(pharmacie='wale_toumbokro')
        ligne = LigneDemande.objects.create(demande=demande, produit=produit, quantite_demandee=Decimal('5'))
        resp = self.client.post(
            reverse('stock_dotation_valider', kwargs={'pk': demande.pk}),
            {'action': 'approuver', f'approuve_{ligne.pk}': '5'},
        )
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        demande.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('15'))
        self.assertEqual(demande.statut, 'en_livraison')

    def test_refuser_demande_change_statut_sans_toucher_stock(self):
        produit = _produit(suffix='DVR', stock_actuel=Decimal('20'))
        demande = DemandePharmacie.objects.create(pharmacie='wale_toumbokro')
        LigneDemande.objects.create(demande=demande, produit=produit, quantite_demandee=Decimal('5'))
        resp = self.client.post(
            reverse('stock_dotation_valider', kwargs={'pk': demande.pk}),
            {'action': 'refuser'},
        )
        self.assertEqual(resp.status_code, 302)
        produit.refresh_from_db()
        demande.refresh_from_db()
        self.assertEqual(produit.stock_actuel, Decimal('20'))
        self.assertEqual(demande.statut, 'refusee')
