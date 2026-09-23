"""Tests de la liste des prestations, portée sur core.listing.

Ce qui est vérifié ici est précisément ce que l'ancien mécanisme ne savait pas
faire : cumuler deux valeurs d'un même critère, croiser deux critères
différents, regrouper, et trier sur la totalité du résultat plutôt que sur la
page affichée.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Articleservice, CategorieArticle, CompagniePharma, FamilleArticle


def _article(nom, **kwargs):
    champs = {
        'prix_vente': Decimal('1000'),
        'actif': True,
        'type_produit_hospitalier': 'service',
    }
    champs.update(kwargs)
    return Articleservice.objects.create(nom=nom, **champs)


class BaseListe(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cat_soins = CategorieArticle.objects.create(nom='Soins', code='SOI')
        cls.cat_labo = CategorieArticle.objects.create(nom='Laboratoire', code='LAB')
        cls.fam = FamilleArticle.objects.create(nom='Consommables', code='CONS')
        cls.labo = CompagniePharma.objects.create(nom='Pharma CI', code='PCI')

        cls.pansement = _article(
            'Pansement', categorie=cls.cat_soins, famille=cls.fam,
            type_produit_hospitalier='consommable', prix_vente=Decimal('500'),
            favori=True, quantite_stock=5, quantite_alerte=10,
        )
        cls.injection = _article(
            'Injection interne', categorie=cls.cat_soins,
            type_produit_hospitalier='service', prix_vente=Decimal('0'),
        )
        cls.numeration = _article(
            'Numération formule sanguine', categorie=cls.cat_labo,
            type_produit_hospitalier='examen', prix_vente=Decimal('7000'),
            compagnie_pharmaceutique=cls.labo,
        )
        cls.perime = _article(
            'Sirop retiré', categorie=cls.cat_labo,
            type_produit_hospitalier='medicament', prix_vente=Decimal('2500'),
            actif=False, forme='sirop', voie_administration='orale',
        )

        cls.url = reverse('services:list')

    def setUp(self):
        self.client.force_login(User.objects.create_user('u_liste', password='x'))

    def noms(self, **params):
        """Noms des prestations affichées, dans l'ordre du tableau."""
        reponse = self.client.get(self.url, params)
        self.assertEqual(reponse.status_code, 200)
        contenu = reponse.content.decode()
        ordre = []
        for article in Articleservice.objects.all():
            position = contenu.find('>%s</td>' % article.nom)
            if position != -1:
                ordre.append((position, article.nom))
        return [nom for _, nom in sorted(ordre)]


class TestFiltresCumulables(BaseListe):

    def test_sans_filtre_tout_le_catalogue(self):
        self.assertEqual(len(self.noms()), 4)

    def test_une_valeur(self):
        self.assertEqual(self.noms(filter='archive'), ['Sirop retiré'])

    def test_deux_valeurs_d_une_meme_famille_se_cumulent_en_ou(self):
        """C'est ce que l'ancien `filtre` unique ne pouvait pas faire."""
        noms = self.noms(filter=['tp_examen', 'tp_medicament'])
        self.assertEqual(sorted(noms), ['Numération formule sanguine', 'Sirop retiré'])

    def test_deux_familles_se_croisent_en_et(self):
        noms = self.noms(filter=['actif', 'cat_%s' % self.cat_soins.pk])
        self.assertEqual(sorted(noms), ['Injection interne', 'Pansement'])

    def test_croisement_sans_resultat(self):
        # Archivé (Sirop) ET catégorie Soins : rien en commun.
        self.assertEqual(self.noms(filter=['archive', 'cat_%s' % self.cat_soins.pk]), [])

    def test_gratuit_et_payant(self):
        self.assertEqual(self.noms(filter='gratuit'), ['Injection interne'])
        self.assertEqual(len(self.noms(filter='payant')), 3)

    def test_seuil_d_alerte(self):
        """Un seuil à 0 signifie « pas de seuil » : seul le Pansement est en alerte."""
        self.assertEqual(self.noms(filter='alerte'), ['Pansement'])

    def test_nature_services_et_articles(self):
        self.assertEqual(self.noms(filter='services'), ['Injection interne'])
        self.assertEqual(len(self.noms(filter='articles')), 3)

    def test_famille_dynamique_lue_en_base(self):
        self.assertEqual(self.noms(filter='fam_%s' % self.fam.pk), ['Pansement'])

    def test_compagnie_dynamique_lue_en_base(self):
        self.assertEqual(self.noms(filter='lab_%s' % self.labo.pk),
                         ['Numération formule sanguine'])

    def test_filtre_vide_explicite_ne_retient_rien(self):
        self.assertEqual(len(self.noms(filter='')), 4)

    def test_recherche_et_filtre_se_combinent(self):
        self.assertEqual(self.noms(q='injection', filter='gratuit'), ['Injection interne'])
        self.assertEqual(self.noms(q='injection', filter='payant'), [])


class TestTriServeur(BaseListe):

    def test_tri_par_prix_croissant(self):
        self.assertEqual(
            self.noms(tri='prix', sens='asc'),
            ['Injection interne', 'Pansement', 'Sirop retiré', 'Numération formule sanguine'],
        )

    def test_tri_par_prix_decroissant(self):
        self.assertEqual(
            self.noms(tri='prix', sens='desc'),
            ['Numération formule sanguine', 'Sirop retiré', 'Pansement', 'Injection interne'],
        )

    def test_tri_par_defaut_alphabetique(self):
        self.assertEqual(
            self.noms(),
            ['Injection interne', 'Numération formule sanguine', 'Pansement', 'Sirop retiré'],
        )

    def test_cle_de_tri_inconnue_ignoree(self):
        """Un order_by sur un champ venu de l'URL planterait la page."""
        self.assertEqual(self.noms(tri='__dangereux__', sens='desc'), self.noms())


class TestRegroupement(BaseListe):

    def _reponse(self, **params):
        reponse = self.client.get(self.url, params)
        self.assertEqual(reponse.status_code, 200)
        return reponse.content.decode()

    #: Une bande de groupe dans le tableau. On ne teste pas la seule présence
    #: de « lst-groupe » : la classe figure aussi dans la feuille de styles de
    #: la brique, incluse à chaque rendu, et l'assertion serait toujours vraie.
    BANDE = '<tr class="lst-groupe'

    def test_regroupement_par_categorie(self):
        contenu = self._reponse(group='categorie')
        self.assertIn(self.BANDE, contenu)
        self.assertIn('Soins', contenu)
        self.assertIn('Laboratoire', contenu)

    def test_regroupement_imbrique(self):
        contenu = self._reponse(group=['categorie', 'etat'])
        self.assertIn(self.BANDE + ' lst-groupe-fils', contenu)

    def test_le_compteur_du_titre_reste_celui_des_prestations(self):
        contenu = self._reponse(group='categorie')
        self.assertIn('<span class="o-page-count">4</span>', contenu)

    def test_groupement_inconnu_ignore(self):
        self.assertEqual(self.client.get(self.url, {'group': 'nexiste_pas'}).status_code, 200)

    def test_regroupement_ignore_en_kanban(self):
        """paginer_groupes renvoie des libellés de groupe, pas des articles."""
        contenu = self._reponse(group='categorie', vue='kanban')
        self.assertNotIn(self.BANDE, contenu)
        self.assertIn('class="o-kanban"', contenu)


class TestPeriode(BaseListe):

    def test_aujourd_hui_retient_les_creations_du_jour(self):
        # date_creation est auto_now_add : tout a été créé aujourd'hui.
        self.assertEqual(len(self.noms(filter='today')), 4)

    def test_intervalle_explicite_l_emporte_sur_le_raccourci(self):
        self.assertEqual(self.noms(filter='today', date_from='1990-01-01',
                                   date_to='1990-12-31'), [])

    def test_date_illisible_ignoree(self):
        self.assertEqual(len(self.noms(date_from='pas-une-date')), 4)


class TestVueEtPagination(BaseListe):

    def test_vue_inconnue_repli_sur_liste(self):
        contenu = self.client.get(self.url, {'vue': 'grille'}).content.decode()
        self.assertIn('o-list-table', contenu)

    def test_page_hors_limites_ne_plante_pas(self):
        self.assertEqual(self.client.get(self.url, {'page': '999'}).status_code, 200)
