from decimal import Decimal

from django.contrib.auth.models import Group, User
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
    user = User.objects.create_user(username, password='x')
    groupe, _ = Group.objects.get_or_create(name=groupe_nom)
    user.groups.add(groupe)
    return user


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

    def test_groupes_autorises_ok(self):
        for i, groupe in enumerate(['Caisse', 'Pharmacien', 'Administrateur', 'Directeur']):
            user = _groupe_user(f'u_cvrf_{i}', groupe)
            self.assertTrue(can_view_rapport_financier(user), f"{groupe} devrait être autorisé")

    def test_groupe_non_autorise_refuse(self):
        user = _groupe_user('u_cvrf_accueil', 'Accueil')
        self.assertFalse(can_view_rapport_financier(user))


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

    def test_rapports_autorises_pour_groupe_caisse(self):
        _groupe_user('u_vrp_caisse', 'Caisse')
        client = Client()
        client.login(username='u_vrp_caisse', password='x')
        for name in RAPPORT_URLS:
            resp = client.get(reverse(name, kwargs={'pharmacie': 'wale_toumbokro'}))
            self.assertEqual(resp.status_code, 200,
                             f"{name} devrait être accessible au groupe Caisse")


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
        User.objects.create_user('u_vte', password='x')
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
        User.objects.create_user('u_liv', password='x')
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
