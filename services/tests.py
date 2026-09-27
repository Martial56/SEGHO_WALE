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
            actif=False,
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


class TestFicheArticleMontreCeQuiEstSaisi(TestCase):
    """La fiche d'un article affiche les champs que le formulaire remplit.

    Elle en montrait 15 sur les 60 du modèle. La plupart des absents ne sont
    remplis par aucun écran — les afficher n'aurait montré que des valeurs par
    défaut. Mais trois l'étaient bel et bien par le formulaire et restaient
    invisibles : le type de produit hospitalier, le type de test et le **code
    HPRIM**, celui-là même qui part au laboratoire partenaire. Un examen
    enregistré avec son code s'affichait comme n'en ayant aucun.
    """

    def setUp(self):
        from decimal import Decimal

        from django.contrib.auth.models import User
        from django.test import Client

        self.user = User.objects.create_superuser('su_fiche', password='x')
        self.client = Client()
        self.client.force_login(self.user)

        self.examen = Articleservice.objects.create(
            nom='NFS fiche', prix_vente=Decimal('4000'),
            type_produit_hospitalier='examen',
            type_test_labo='hematologie', code_hprim='NFS01')
        self.acte = Articleservice.objects.create(
            nom='Consultation fiche', prix_vente=Decimal('3000'),
            type_produit_hospitalier='service')

    def _page(self, article):
        return self.client.get(
            reverse('services:detail', args=[article.pk])).content.decode()

    def test_le_code_hprim_s_affiche(self):
        self.assertIn('NFS01', self._page(self.examen))

    def test_le_type_de_test_s_affiche(self):
        self.assertIn('Hématologie', self._page(self.examen))

    def test_le_type_de_produit_hospitalier_s_affiche(self):
        self.assertIn('Type de produit hospitalier', self._page(self.examen))
        self.assertIn('Examen', self._page(self.examen))

    def test_le_bloc_laboratoire_reste_muet_sur_un_acte(self):
        """Une consultation n'a rien à dire du laboratoire."""
        page = self._page(self.acte)
        self.assertNotIn('>Laboratoire<', page)
        self.assertNotIn('Code HPRIM', page)


# ─── Catégories : l'export ne porte plus que ce qui existe ─────────────────────

class TestExportDesCategories(TestCase):
    """La catégorie portait neuf champs de gestion de stock hérités d'un ERP —
    stratégie FIFO/LIFO, méthode de coût, routes, comptes comptables. Vides sur
    toutes les catégories, lus par personne, et sans objet pour une prestation :
    on ne stocke pas une consultation. Retirés du modèle.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from services.models import CategorieArticle
        self.client.force_login(User.objects.create_superuser('exp_cat', password='x'))
        self.mere, _ = CategorieArticle.objects.get_or_create(
            code='EXA', defaults={'nom': 'Examens'})
        CategorieArticle.objects.update_or_create(
            code='ECHO', defaults={'nom': 'Échographies',
                                   'description': 'Imagerie', 'parent': self.mere})

    def test_l_export_ne_porte_que_quatre_colonnes(self):
        from services.views import _CAT_HDR
        self.assertEqual(_CAT_HDR, ['code', 'nom', 'description', 'parent'])

    def test_le_csv_sort_avec_le_bon_entete(self):
        reponse = self.client.get('/services/export/categories/', {'format': 'csv'})
        self.assertEqual(reponse.status_code, 200)
        entete = reponse.content.decode('utf-8-sig').splitlines()[0].strip()
        self.assertEqual(entete, 'code,nom,description,parent')

    def test_la_categorie_parente_sort_toujours(self):
        """La seule colonne vide qu'on a gardée : elle est remplissable."""
        import json
        reponse = self.client.get('/services/export/categories/', {'format': 'json'})
        lignes = {l['code']: l for l in json.loads(reponse.content)}
        self.assertEqual(lignes['ECHO']['parent'], 'EXA')

    def test_les_champs_de_stock_ont_disparu_du_modele(self):
        from services.models import CategorieArticle
        champs = {f.name for f in CategorieArticle._meta.get_fields()}
        for parti in ('methode_cout', 'valorisation_inventaire', 'routes',
                      'strategie_enlevement', 'reservation_conditionnement',
                      'bloquer_serie_lot', 'sequence_code_barres',
                      'compte_revenus', 'compte_charges'):
            with self.subTest(champ=parti):
                self.assertNotIn(parti, champs)

    def test_l_article_garde_ses_propres_champs(self):
        """Garde-fou : retirer un champ de la catégorie ne touche pas l'article."""
        from services.models import Articleservice
        champs = {f.name for f in Articleservice._meta.get_fields()}
        self.assertIn('reference_interne', champs)
        self.assertIn('prix_vente', champs)

    def test_un_ancien_fichier_a_treize_colonnes_passe_encore(self):
        """Les colonnes disparues sont ignorées, la ligne est quand même créée."""
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        from services.models import CategorieArticle
        ancien = json.dumps([{
            'code': 'ZZT', 'nom': 'Ancienne', 'description': 'essai', 'parent': '',
            'methode_cout': 'fifo', 'valorisation_inventaire': 'automatique',
            'reservation_conditionnement': 'entiers', 'bloquer_serie_lot': 1,
            'routes': 'Achats', 'strategie_enlevement': 'lifo',
            'sequence_code_barres': 'SEQ1',
            'compte_revenus': '70110000', 'compte_charges': '60110000',
        }]).encode()
        self.client.post('/services/importer/categories/', {
            'fichier': SimpleUploadedFile('anciennes.json', ancien,
                                          content_type='application/json')})
        cree = CategorieArticle.objects.filter(code='ZZT').first()
        self.assertIsNotNone(cree)
        self.assertEqual(cree.nom, 'Ancienne')
        self.assertEqual(cree.description, 'essai')

    def test_le_formulaire_propose_exactement_les_champs_restants(self):
        from services.forms import CategorieArticleForm
        self.assertEqual(list(CategorieArticleForm().fields),
                         ['nom', 'code', 'parent', 'description'])


# ─── Prestations : l'export ne porte plus que ce qui sert ──────────────────────

class TestExportDesPrestations(TestCase):
    """L'export sortait 33 colonnes pour 7 qui portaient une information, et
    oubliait la seule qui manquait vraiment : le département.

    Les 26 autres décrivaient un médicament (forme, voie, dosage, composant
    actif, avertissements) ou une comptabilité que rien ne renseigne. Le
    catalogue ne contient que des prestations — examens, consultations, soins —
    et les médicaments vivent dans Pharmacie et Stock.
    """

    def setUp(self):
        from decimal import Decimal
        from django.contrib.auth.models import User
        from medecins.models import Departement
        from services.models import Articleservice, CategorieArticle
        self.client.force_login(User.objects.create_superuser('exp_art', password='x'))
        # Des migrations de seed créent déjà certains codes : on les réutilise
        # plutôt que de heurter la contrainte d'unicité.
        self.cat, _ = CategorieArticle.objects.get_or_create(
            code='CS', defaults={'nom': 'Consultations'})
        self.dept, _ = Departement.objects.get_or_create(
            code='GYN', defaults={'nom': 'Gynécologie'})
        Articleservice.objects.create(
            reference_interne='CS_GYNOBS', nom='Consultation gynéco-obstétrique',
            categorie=self.cat, departement=self.dept, prix_vente=Decimal('3350'))
        Articleservice.objects.create(
            reference_interne='CS_SANS', nom='Consultation sans département',
            categorie=self.cat, prix_vente=Decimal('1000'))

    def test_l_export_porte_quatorze_colonnes(self):
        from services.views import _ART_HDR
        self.assertEqual(_ART_HDR, [
            'reference_interne', 'nom', 'prix_vente', 'cout',
            'type_article', 'type_produit_hospitalier',
            'actif', 'peut_etre_vendu', 'peut_etre_achete',
            'categorie', 'departement',
            'type_test_labo', 'code_hprim', 'unite_mesure',
        ])

    def test_le_departement_sort_par_son_code(self):
        """Pas l'identifiant — un « 6 » ne veut rien dire d'une base à l'autre —
        ni le libellé, qui se renomme. Le code est celui sur lequel l'import des
        départements déduplique."""
        import json
        reponse = self.client.get('/services/export/articles/', {'format': 'json'})
        lignes = {l['reference_interne']: l for l in json.loads(reponse.content)}
        self.assertEqual(lignes['CS_GYNOBS']['departement'], 'GYN')
        self.assertEqual(lignes['CS_SANS']['departement'], '')

    def test_le_csv_sort_avec_le_bon_entete(self):
        reponse = self.client.get('/services/export/articles/', {'format': 'csv'})
        entete = reponse.content.decode('utf-8-sig').splitlines()[0].strip()
        self.assertTrue(entete.startswith('reference_interne,nom,prix_vente'))
        self.assertIn('departement', entete.split(','))

    def test_les_champs_de_medicament_ont_disparu_du_modele(self):
        from services.models import Articleservice
        champs = {f.name for f in Articleservice._meta.get_fields()}
        for parti in ('forme', 'voie_administration', 'dosage', 'dosage_unite',
                      'composant_actif', 'effet_therapeutique', 'indications',
                      'avertissement_grossesse', 'avertissement_lactation',
                      'notes_internes', 'code_barres', 'unite_achat',
                      'compte_revenus', 'compte_charges', 'compte_ecart_prix'):
            with self.subTest(champ=parti):
                self.assertNotIn(parti, champs)

    def test_la_categorie_garde_ses_champs_restants(self):
        """Garde-fou contre une suppression trop large."""
        from services.models import Articleservice
        champs = {f.name for f in Articleservice._meta.get_fields()}
        for garde in ('reference_interne', 'nom', 'prix_vente', 'cout',
                      'categorie', 'departement', 'type_test_labo',
                      'code_hprim', 'unite_mesure', 'quantite_stock'):
            with self.subTest(champ=garde):
                self.assertIn(garde, champs)


class TestImportDesPrestations(TestCase):

    def setUp(self):
        from django.contrib.auth.models import User
        from medecins.models import Departement
        from services.models import CategorieArticle
        self.client.force_login(User.objects.create_superuser('imp_art', password='x'))
        CategorieArticle.objects.get_or_create(code='CS', defaults={'nom': 'Consultations'})
        Departement.objects.get_or_create(code='GYN', defaults={'nom': 'Gynécologie'})

    def _importer(self, lignes):
        import json
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post('/services/importer/articles/', {
            'fichier': SimpleUploadedFile(
                'a.json', json.dumps(lignes).encode(),
                content_type='application/json')})

    def test_le_departement_est_rattache_par_son_code(self):
        from services.models import Articleservice
        self._importer([{'reference_interne': 'ZZ1', 'nom': 'Test',
                         'categorie': 'CS', 'departement': 'GYN'}])
        article = Articleservice.objects.get(reference_interne='ZZ1')
        self.assertEqual(article.departement.code, 'GYN')

    def test_un_departement_inconnu_est_signale_sans_bloquer(self):
        """L'article passe, on complète après : c'est le choix retenu, plutôt
        que de refuser tout le fichier."""
        from django.contrib.messages import get_messages
        from services.models import Articleservice
        reponse = self._importer([{'reference_interne': 'ZZ2', 'nom': 'Test',
                                   'categorie': 'CS', 'departement': 'INCONNU'}])
        article = Articleservice.objects.get(reference_interne='ZZ2')
        self.assertIsNone(article.departement)
        messages = ' '.join(str(m) for m in get_messages(reponse.wsgi_request))
        self.assertIn('Département(s) introuvable(s)', messages)
        self.assertIn('INCONNU', messages)

    def test_un_ancien_fichier_a_trente_trois_colonnes_passe_encore(self):
        from services.models import Articleservice
        self._importer([{
            'reference_interne': 'ZZ3', 'nom': 'Ancien format', 'categorie': 'CS',
            'forme': 'sirop', 'voie_administration': 'orale', 'code_barres': '123',
            'dosage': '500', 'composant_actif': 'paracétamol',
            'compte_revenus': '70110000', 'notes_internes': 'bla', 'unite_achat': 'U',
        }])
        article = Articleservice.objects.get(reference_interne='ZZ3')
        self.assertEqual(article.nom, 'Ancien format')


# ─── Modèles vierges à télécharger avant d'importer ────────────────────────────

class TestModelesDImport(TestCase):
    """Un import rate presque toujours pour deux raisons : les colonnes sont
    inventées, ou on a tapé « Gynécologie » là où le fichier attend `GYN`. Le
    modèle répond aux deux — mêmes colonnes que l'import, et les codes réels de
    la base proposés en liste déroulante.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from medecins.models import Departement
        from services.models import CategorieArticle
        self.client.force_login(User.objects.create_superuser('modele', password='x'))
        CategorieArticle.objects.get_or_create(code='CS', defaults={'nom': 'Consultations'})
        Departement.objects.get_or_create(code='GYN', defaults={'nom': 'Gynécologie'})

    def _classeur(self, url):
        import io
        import openpyxl
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        return reponse, openpyxl.load_workbook(io.BytesIO(reponse.content))

    def test_le_modele_des_prestations_se_telecharge(self):
        reponse, _ = self._classeur('/services/export/articles/modele/')
        self.assertIn('modele_import_prestations.xlsx', reponse['Content-Disposition'])

    def test_le_modele_des_categories_se_telecharge(self):
        reponse, _ = self._classeur('/services/export/categories/modele/')
        self.assertIn('modele_import_categories.xlsx', reponse['Content-Disposition'])

    def test_les_colonnes_du_modele_sont_celles_de_l_export(self):
        """Le seul point qui compte : si les deux divergent, le modèle induit
        en erreur au lieu d'aider."""
        from services.views import _ART_HDR, _CAT_HDR
        for url, entetes in (('/services/export/articles/modele/', _ART_HDR),
                             ('/services/export/categories/modele/', _CAT_HDR)):
            with self.subTest(url=url):
                _, wb = self._classeur(url)
                lues = [c.value for c in wb.active[1]]
                self.assertEqual(lues, entetes)

    def test_les_listes_proposent_les_codes_reels_de_la_base(self):
        _, wb = self._classeur('/services/export/articles/modele/')
        valeurs = {c.value for ligne in wb['Listes'].iter_rows() for c in ligne if c.value}
        self.assertIn('CS', valeurs)        # une catégorie existante
        self.assertIn('GYN', valeurs)       # un département existant
        self.assertIn('prestation', valeurs)

    def test_la_feuille_des_listes_est_cachee(self):
        """Elle n'est qu'un support technique : la montrer inviterait à la remplir."""
        _, wb = self._classeur('/services/export/articles/modele/')
        self.assertEqual(wb['Listes'].sheet_state, 'hidden')

    def test_un_modele_rempli_s_importe(self):
        """Le bout du bout : télécharger, remplir, importer."""
        import io
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile
        from services.models import Articleservice

        _, wb = self._classeur('/services/export/articles/modele/')
        ws = wb.active
        ws.delete_rows(2)   # la ligne d'exemple
        ws.append(['ZZ_MOD', 'Prestation par modèle', '2500', '0',
                   'prestation', 'service', '1', '1', '0', 'CS', 'GYN', '', '', ''])
        tampon = io.BytesIO()
        wb.save(tampon)
        tampon.seek(0)
        self.client.post('/services/importer/articles/', {
            'fichier': SimpleUploadedFile(
                'm.xlsx', tampon.read(),
                content_type='application/vnd.openxmlformats-officedocument.'
                             'spreadsheetml.sheet')})

        article = Articleservice.objects.get(reference_interne='ZZ_MOD')
        self.assertEqual(article.nom, 'Prestation par modèle')
        self.assertEqual(article.categorie.code, 'CS')
        self.assertEqual(article.departement.code, 'GYN')

    def test_la_ligne_d_exemple_se_distingue_de_la_saisie(self):
        """En gris italique : elle se supprime sans hésiter et ne passe pas
        pour une donnée."""
        _, wb = self._classeur('/services/export/articles/modele/')
        cellule = wb.active.cell(row=2, column=1)
        self.assertTrue(cellule.font.italic)
