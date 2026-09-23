"""Déclaration de la liste des prestations pour la brique core.listing.

Même rôle que soin_listing ou chambre_listing : décrire *quoi* filtrer,
regrouper et trier — le comment vient de core.listing (cumul des valeurs d'une
famille en OU, croisement des familles en ET, comptages calculés en base,
regroupement imbriqué, tri porté par le serveur).

Ce que remplace ce fichier : un paramètre `filtre` à valeur unique parcouru par
une chaîne de `elif`, si bien que « Services » et « Favoris » ne pouvaient pas
être demandés ensemble — le second effaçait le premier. `statut=inactif` et
`filtre=archive` faisaient de surcroît exactement la même chose, par deux
chemins différents, et aucun regroupement ni tri serveur n'existait.
"""

from datetime import date, timedelta

from django.db.models import F, Q
from django.db.models.functions import (TruncDay, TruncMonth, TruncQuarter,
                                        TruncWeek, TruncYear)

from patients.rdv_listing import (_debut_semaine, _lib_jour, _lib_mois,
                                  _lib_semaine, _lib_trimestre, _local)


#: Champs interrogés par la barre de recherche.
CHAMPS_RECHERCHE = ('nom', 'reference_interne', 'code_barres', 'composant_actif',
                    'nom_produit_fabricant', 'code_produit',
                    'categorie__nom', 'categorie__code', 'famille__nom')

#: Aucun filtre à l'arrivée : un catalogue s'ouvre entier, on n'y cherche pas
#: que les articles du jour. « Effacer » y ramène.
FILTRES_DEFAUT = ()

#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')


# ── Filtres ─────────────────────────────────────────────────────────────────

def _appliquer_periode(qs, codes, contexte):
    """Période de création : un intervalle explicite l'emporte sur les raccourcis."""
    aujourdhui = contexte.get('aujourdhui') or date.today()
    date_from = (contexte.get('date_from') or '').strip()
    date_to = (contexte.get('date_to') or '').strip()

    if date_from or date_to:
        from datetime import datetime as dt
        try:
            if date_from:
                qs = qs.filter(date_creation__date__gte=dt.strptime(date_from, '%Y-%m-%d').date())
            if date_to:
                qs = qs.filter(date_creation__date__lte=dt.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass                       # date illisible : la période est ignorée
        return qs

    if 'today' in codes:
        return qs.filter(date_creation__date=aujourdhui)
    if 'semaine' in codes:
        return qs.filter(date_creation__date__gte=aujourdhui - timedelta(days=7),
                         date_creation__date__lte=aujourdhui)
    if 'mois' in codes:
        return qs.filter(date_creation__year=aujourdhui.year,
                         date_creation__month=aujourdhui.month)
    if 'annee' in codes:
        return qs.filter(date_creation__year=aujourdhui.year)
    return qs


def libelle_periode(filtres, date_from='', date_to=''):
    """Mention discrète de la période affichée, à côté du titre."""
    if date_from and date_to:
        return f'créées du {date_from} au {date_to}'
    if date_from:
        return f'créées à partir du {date_from}'
    if date_to:
        return f"créées jusqu'au {date_to}"
    for code, libelle in (('today', "créées aujourd'hui"),
                          ('semaine', 'créées ces 7 derniers jours'),
                          ('mois', 'créées ce mois-ci'),
                          ('annee', "créées cette année")):
        if code in filtres:
            return libelle
    return 'tout le catalogue'


def _categories():
    """Catégories réellement portées par un article, lues en base."""
    from .models import Articleservice
    lignes = (Articleservice.objects.exclude(categorie=None)
              .values_list('categorie_id', 'categorie__nom', 'categorie__code')
              .order_by('categorie__nom').distinct())
    return [(f'cat_{pk}', f'{code} — {nom}' if code else nom, Q(categorie_id=pk))
            for pk, nom, code in lignes]


def _familles():
    from .models import Articleservice
    lignes = (Articleservice.objects.exclude(famille=None)
              .values_list('famille_id', 'famille__nom')
              .order_by('famille__nom').distinct())
    return [(f'fam_{pk}', nom, Q(famille_id=pk)) for pk, nom in lignes]


def _compagnies():
    from .models import Articleservice
    lignes = (Articleservice.objects.exclude(compagnie_pharmaceutique=None)
              .values_list('compagnie_pharmaceutique_id', 'compagnie_pharmaceutique__nom')
              .order_by('compagnie_pharmaceutique__nom').distinct())
    return [(f'lab_{pk}', nom, Q(compagnie_pharmaceutique_id=pk)) for pk, nom in lignes]


def familles_articles():
    """Familles de filtres de la liste des prestations."""
    from core.listing import Famille
    from .models import Articleservice

    return [
        Famille('periode', 'Période de création', exclusive=True, dates=True,
                applique=_appliquer_periode, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        # « Archivé » et « Inactif » désignaient la même chose par deux chemins
        # différents (filtre=archive et statut=inactif) : une seule famille.
        Famille('etat', 'État', valeurs=[
            ('actif',    'Actif',    Q(actif=True)),
            ('archive',  'Archivé',  Q(actif=False)),
        ]),
        Famille('nature', 'Nature', valeurs=[
            ('services', 'Services médicaux', Q(type_produit_hospitalier='service')),
            ('articles', 'Articles',          ~Q(type_produit_hospitalier='service')),
        ]),
        Famille('type_produit', 'Type de produit', valeurs=(
            [(f'tp_{code}', libelle, Q(type_produit_hospitalier=code))
             for code, libelle in Articleservice.TYPE_PRODUIT_CHOICES]
            + [('tp_vide', 'Non précisé', Q(type_produit_hospitalier=''))]
        )),
        Famille('type_article', "Type d'article", valeurs=[
            (f'ta_{code}', libelle, Q(type_article=code))
            for code, libelle in Articleservice.TYPE_ARTICLE_CHOICES
        ]),
        Famille('categorie', 'Catégorie', source=_categories),
        Famille('famille', 'Famille', source=_familles),
        Famille('usage', 'Usage', valeurs=[
            ('vendu',   'Peut être vendu',   Q(peut_etre_vendu=True)),
            ('achete',  'Peut être acheté',  Q(peut_etre_achete=True)),
            ('ni_ni',   'Ni vendu ni acheté', Q(peut_etre_vendu=False, peut_etre_achete=False)),
        ]),
        Famille('mise_en_avant', 'Mise en avant', valeurs=[
            ('favori',     'Favori',     Q(favori=True)),
            ('non_favori', 'Non favori', Q(favori=False)),
        ]),
        Famille('tarif', 'Tarif', valeurs=[
            ('gratuit', 'Gratuit (0 F)',   Q(prix_vente=0)),
            ('payant',  'Payant',          Q(prix_vente__gt=0)),
            ('sans_cout', "Sans coût d'achat renseigné", Q(cout=0)),
        ]),
        # Le seuil d'alerte à 0 signifie « pas de seuil » : sans cette borne,
        # tout article à zéro en stock serait signalé en alerte.
        Famille('stock', 'Stock', valeurs=[
            ('en_stock', 'En stock',            Q(quantite_stock__gt=0)),
            ('rupture',  'En rupture',          Q(quantite_stock__lte=0)),
            ('alerte',   "Sous le seuil d'alerte",
             Q(quantite_alerte__gt=0, quantite_stock__lte=F('quantite_alerte'))),
        ]),
        Famille('forme', 'Forme', valeurs=[
            (f'forme_{code}', libelle, Q(forme=code))
            for code, libelle in Articleservice.FORME_CHOICES
        ]),
        Famille('voie', "Voie d'administration", valeurs=[
            (f'voie_{code}', libelle, Q(voie_administration=code))
            for code, libelle in Articleservice.VOIE_CHOICES
        ]),
        Famille('avertissement', 'Avertissement', valeurs=[
            ('av_grossesse', 'Grossesse', Q(avertissement_grossesse=True)),
            ('av_lactation', 'Lactation', Q(avertissement_lactation=True)),
        ]),
        Famille('laboratoire', 'Compagnie pharmaceutique', source=_compagnies),
    ]


# ── Regroupements ───────────────────────────────────────────────────────────

def _vide(valeur, defaut):
    return valeur if valeur else defaut


#: Dimensions rassemblées sous une entrée dépliable du menu.
SOUS_MENU_DATE = 'Date de création'


def construire_dimensions():
    """Dimensions déclarées, dans l'ordre où le menu les propose."""
    from core.listing import Dimension
    from .models import Articleservice

    lib_type_produit = dict(Articleservice.TYPE_PRODUIT_CHOICES)
    lib_type_article = dict(Articleservice.TYPE_ARTICLE_CHOICES)
    lib_forme = dict(Articleservice.FORME_CHOICES)
    lib_voie = dict(Articleservice.VOIE_CHOICES)

    def booleen(champ, oui, non):
        """Dimension d'un champ oui/non : le libellé doit être identique des deux
        côtés, sinon l'en-tête de groupe ne retrouve pas ses lignes."""
        return {
            'values': (champ,),
            'label':  lambda r: oui if r[champ] else non,
            'valeur': lambda o: oui if getattr(o, champ) else non,
            'order':  (champ,),
        }

    brut = [
        ('categorie', 'Catégorie', None, {
            'values': ('categorie__nom',),
            'label':  lambda r: _vide(r['categorie__nom'], 'Sans catégorie'),
            'valeur': lambda o: _vide(o.categorie.nom if o.categorie_id else '', 'Sans catégorie'),
            'order':  ('categorie__nom',),
        }),
        ('famille', 'Famille', None, {
            'values': ('famille__nom',),
            'label':  lambda r: _vide(r['famille__nom'], 'Sans famille'),
            'valeur': lambda o: _vide(o.famille.nom if o.famille_id else '', 'Sans famille'),
            'order':  ('famille__nom',),
        }),
        ('type_produit', 'Type de produit', None, {
            'values': ('type_produit_hospitalier',),
            'label':  lambda r: lib_type_produit.get(r['type_produit_hospitalier']) or 'Non précisé',
            'valeur': lambda o: lib_type_produit.get(o.type_produit_hospitalier) or 'Non précisé',
            'order':  ('type_produit_hospitalier',),
        }),
        ('type_article', "Type d'article", None, {
            'values': ('type_article',),
            'label':  lambda r: lib_type_article.get(r['type_article']) or 'Non précisé',
            'valeur': lambda o: lib_type_article.get(o.type_article) or 'Non précisé',
            'order':  ('type_article',),
        }),
        ('etat', 'État', None, booleen('actif', 'Actif', 'Archivé')),
        ('tarif', 'Tarif', None, {
            'values': ('prix_vente',),
            'label':  lambda r: 'Gratuit' if not r['prix_vente'] else 'Payant',
            'valeur': lambda o: 'Gratuit' if not o.prix_vente else 'Payant',
            'order':  ('prix_vente',),
        }),
        ('forme', 'Forme', None, {
            'values': ('forme',),
            'label':  lambda r: lib_forme.get(r['forme']) or 'Non précisée',
            'valeur': lambda o: lib_forme.get(o.forme) or 'Non précisée',
            'order':  ('forme',),
        }),
        ('voie', "Voie d'administration", None, {
            'values': ('voie_administration',),
            'label':  lambda r: lib_voie.get(r['voie_administration']) or 'Non précisée',
            'valeur': lambda o: lib_voie.get(o.voie_administration) or 'Non précisée',
            'order':  ('voie_administration',),
        }),
        ('laboratoire', 'Compagnie pharmaceutique', None, {
            'values': ('compagnie_pharmaceutique__nom',),
            'label':  lambda r: _vide(r['compagnie_pharmaceutique__nom'], 'Sans compagnie'),
            'valeur': lambda o: _vide(o.compagnie_pharmaceutique.nom
                                      if o.compagnie_pharmaceutique_id else '', 'Sans compagnie'),
            'order':  ('compagnie_pharmaceutique__nom',),
        }),
        ('unite_mesure', 'Unité de mesure', None, {
            'values': ('unite_mesure__nom',),
            'label':  lambda r: _vide(r['unite_mesure__nom'], 'Sans unité'),
            'valeur': lambda o: _vide(o.unite_mesure.nom if o.unite_mesure_id else '', 'Sans unité'),
            'order':  ('unite_mesure__nom',),
        }),
        ('departement', 'Département', None, {
            'values': ('departement__nom',),
            'label':  lambda r: _vide(r['departement__nom'], 'Sans département'),
            'valeur': lambda o: _vide(o.departement.nom if o.departement_id else '', 'Sans département'),
            'order':  ('departement__nom',),
        }),
        ('favori', 'Mise en avant', None, booleen('favori', 'Favori', 'Non favori')),
        ('vendu', 'Vente', None, booleen('peut_etre_vendu', 'Peut être vendu', 'Non vendu')),
        ('achete', 'Achat', None, booleen('peut_etre_achete', 'Peut être acheté', 'Non acheté')),
        ('date_annee', 'Année', SOUS_MENU_DATE, {
            'annotate': {'g_annee': TruncYear('date_creation')},
            'values': ('g_annee',),
            'label':  lambda r: str(_local(r['g_annee']).year) if r['g_annee'] else 'Sans date',
            'valeur': lambda o: str(_local(o.date_creation).year) if o.date_creation else 'Sans date',
            'order':  ('-date_creation',),
        }),
        ('date_trimestre', 'Trimestre', SOUS_MENU_DATE, {
            'annotate': {'g_trim': TruncQuarter('date_creation')},
            'values': ('g_trim',),
            'label':  lambda r: _lib_trimestre(_local(r['g_trim'])),
            'valeur': lambda o: _lib_trimestre(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('date_mois', 'Mois', SOUS_MENU_DATE, {
            'annotate': {'g_mois': TruncMonth('date_creation')},
            'values': ('g_mois',),
            'label':  lambda r: _lib_mois(_local(r['g_mois'])),
            'valeur': lambda o: _lib_mois(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
        ('date_semaine', 'Semaine', SOUS_MENU_DATE, {
            'annotate': {'g_sem': TruncWeek('date_creation')},
            'values': ('g_sem',),
            'label':  lambda r: _lib_semaine(_local(r['g_sem'])),
            # TruncWeek ramène au lundi : le calcul depuis l'objet doit en faire
            # autant, sinon les deux chemins ne donnent pas le même libellé.
            'valeur': lambda o: _lib_semaine(_debut_semaine(_local(o.date_creation))),
            'order':  ('-date_creation',),
        }),
        ('date_jour', 'Jour', SOUS_MENU_DATE, {
            'annotate': {'g_jour': TruncDay('date_creation')},
            'values': ('g_jour',),
            'label':  lambda r: _lib_jour(_local(r['g_jour'])),
            'valeur': lambda o: _lib_jour(_local(o.date_creation)),
            'order':  ('-date_creation',),
        }),
    ]

    return {cle: Dimension(cle=cle, libelle=libelle, sous_menu=sous_menu, **d)
            for cle, libelle, sous_menu, d in brut}


#: Colonnes triables de la liste : clé lue dans l'URL -> champs du modèle.
#: Le tri porte sur la totalité du résultat filtré, pas sur la page affichée :
#: l'ancien tri s'exécutait en JavaScript et ne réordonnait que les 40 lignes
#: visibles, on croyait voir le moins cher et on voyait le moins cher *de la page*.
TRIS = {
    'nom':       ('nom',),
    'reference': ('reference_interne',),
    'categorie': ('categorie__nom',),
    'type':      ('type_produit_hospitalier',),
    'prix':      ('prix_vente',),
    'statut':    ('actif',),
}
