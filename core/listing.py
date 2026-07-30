"""Brique commune aux listes : recherche, filtres cumulables, regroupement imbriqué.

Pensée pour être réutilisée par n'importe quel module. Chaque liste se contente
de **déclarer** ses familles de filtres et ses dimensions de regroupement ; la
mécanique (combinaison des filtres, comptage réel, construction de l'arbre de
groupes, pagination, fragment AJAX, génération des menus) vit ici.

Trois principes, hérités de la liste des patients puis des rendez-vous :

* **Filtres cumulables** : à l'intérieur d'une même famille les valeurs se
  combinent en OU, entre familles différentes en ET. Une famille peut être
  déclarée `exclusive` pour se comporter comme un bouton radio (les périodes).
* **Compteurs réels** : le nombre affiché sur un en-tête de groupe est calculé en
  base sur toute la sélection, pas seulement sur la page courante. Quand un
  groupe déborde de la page, on affiche « sur cette page / total ».
* **Regroupement imbriqué** : regrouper par Genre puis État produit des lignes
  Genre dépliables révélant des sous-lignes État, elles-mêmes dépliables.

Les valeurs d'une famille peuvent être **dynamiques** (lues en base) : une entrée
ajoutée en configuration devient filtrable sans toucher au code.
"""

from collections import OrderedDict, defaultdict

from django.db.models import Count, Q


# ── Déclarations ────────────────────────────────────────────────────────────

class Famille:
    """Une famille de filtres. Ses valeurs se combinent en OU.

    `valeurs` est une liste de triplets (code, libellé, Q) pour les familles
    figées. Pour une famille alimentée par la configuration, passer plutôt
    `source` : un appelable sans argument renvoyant ces triplets, évalué à chaque
    requête pour refléter la base.
    """

    def __init__(self, cle, libelle, valeurs=None, source=None,
                 exclusive=False, applique=None, dates=False):
        self.cle = cle
        self.libelle = libelle
        self._valeurs = list(valeurs or [])
        self.source = source
        self._cache = None
        self.exclusive = exclusive
        # Une famille peut porter un intervalle de dates (la période).
        self.dates = dates
        # Certaines familles ne s'expriment pas par un simple OU de Q (la période,
        # qui doit céder devant un intervalle de dates) : elles fournissent alors
        # leur propre fonction (qs, codes_retenus, contexte) -> qs.
        self.applique = applique

    def valeurs(self):
        """Valeurs de la famille, lues une seule fois par instance.

        `source` interroge la base : sans cette mémorisation elle serait rappelée
        à chaque usage (application des filtres, puis génération du menu). Les
        instances étant construites à chaque requête, une valeur ajoutée en
        configuration reste visible immédiatement.
        """
        if self.source is None:
            return self._valeurs
        if self._cache is None:
            self._cache = list(self.source())
        return self._cache

    def codes(self):
        return [code for code, _, _ in self.valeurs()]

    def codes_retenus(self, filtres):
        retenus = set(filtres)
        return [code for code in self.codes() if code in retenus]

    def est_active(self, filtres):
        return bool(self.codes_retenus(filtres))


class Dimension:
    """Une dimension de regroupement.

    `values` liste les champs à passer à `.values()` pour agréger les compteurs
    en base. Une dimension qui ne peut pas être agrégée en SQL (valeur dans un
    JSONField, appartenance multiple) laisse `values` vide : les compteurs sont
    alors calculés en Python, plus lentement mais sur la même source que les
    en-têtes — sans quoi les deux ne concorderaient pas.

    `valeur(objet)` renvoie le libellé du groupe pour un objet. Elle peut
    renvoyer une **liste** de libellés : l'objet apparaît alors dans plusieurs
    groupes (cas d'un rendez-vous portant plusieurs pathologies).
    """

    def __init__(self, cle, libelle, valeur, values=(), annotate=None,
                 label=None, order=(), sous_menu=None, filtre=None, perso=False):
        self.cle = cle
        self.libelle = libelle
        self.valeur = valeur
        self.values = tuple(values)
        self.annotate = dict(annotate or {})
        self.label = label
        self.order = tuple(order)
        # Une dimension déclarée se replie dans le sous-menu latéral qu'elle
        # nomme ; une dimension `perso` (générée depuis les champs du
        # formulaire) rejoint la liste déroulante « Ajouter un groupement
        # personnalisé », où `sous_menu` sert alors de titre de groupe.
        self.sous_menu = sous_menu
        self.perso = perso
        # `filtre(valeurs_brutes)` -> Q, pour ne charger que les lignes des
        # groupes affichés. Dérivable seule quand la dimension tient dans un seul
        # champ ; à fournir sinon (plusieurs champs, valeur dans un JSONField).
        self._filtre = filtre

    @property
    def agregeable(self):
        return bool(self.values)

    @property
    def filtrable(self):
        """Peut-on restreindre la requête aux lignes de certains groupes ?

        Oui dès que la dimension s'exprime en base, y compris sur plusieurs
        champs ou sur une annotation — on filtre alors sur l'annotation, ce que
        Django sait faire. Seules les dimensions non agrégeables (valeur dans un
        JSONField, appartenance multiple) doivent fournir leur propre filtre.
        """
        return bool(self._filtre) or self.agregeable

    def filtre(self, valeurs_brutes):
        """Condition retenant les lignes des groupes dont on donne les valeurs.

        `valeurs_brutes` est un ensemble de tuples, un par champ de `values`.
        Un seul champ donne un `__in` ; plusieurs champs donnent un OU de ET,
        chaque tuple décrivant une combinaison exacte.
        """
        if self._filtre:
            return self._filtre(valeurs_brutes)
        if len(self.values) == 1:
            champ = self.values[0]
            valeurs = [t[0] for t in valeurs_brutes]
            concretes = [v for v in valeurs if v is not None]
            # `IN (NULL)` ne correspond à rien en SQL : le groupe des valeurs
            # absentes (« Sans type de consultation »…) doit être visé par
            # `isnull`, sans quoi il s'afficherait sans jamais charger ses lignes.
            condition = Q(**{f'{champ}__in': concretes}) if concretes else Q(pk__in=[])
            if len(concretes) < len(valeurs):
                condition |= Q(**{f'{champ}__isnull': True})
            return condition
        condition = Q()
        for tuple_valeurs in valeurs_brutes:
            condition |= Q(**dict(zip(self.values, tuple_valeurs)))
        return condition


class Listing:
    """Déclaration complète d'une liste."""

    def __init__(self, recherche=(), familles=(), dimensions=(),
                 par_page=25, filtres_defaut=(), tri_defaut=()):
        self.recherche = tuple(recherche)
        self.familles = list(familles)
        self.dimensions = OrderedDict((d.cle, d) for d in dimensions)
        self.par_page = par_page
        self.filtres_defaut = tuple(filtres_defaut)
        self.tri_defaut = tuple(tri_defaut)

    # ── Filtres ─────────────────────────────────────────────────────────────

    def filtres_demandes(self, request):
        """Filtres retenus, en appliquant le défaut sur une URL sans paramètre."""
        if 'filter' not in request.GET:
            return list(self.filtres_defaut)
        return request.GET.getlist('filter')

    def est_selection_par_defaut(self, filtres):
        return set(filtres) == set(self.filtres_defaut)

    def appliquer_recherche(self, qs, q):
        if not q or not self.recherche:
            return qs
        condition = Q()
        for champ in self.recherche:
            condition |= Q(**{f'{champ}__icontains': q})
        return qs.filter(condition)

    def appliquer_filtres(self, qs, filtres, contexte=None):
        """Applique chaque famille en ET ; les valeurs d'une famille en OU."""
        contexte = contexte or {}
        for famille in self.familles:
            codes = famille.codes_retenus(filtres)
            if famille.applique:
                qs = famille.applique(qs, codes, contexte)
                continue
            if not codes:
                continue
            table = {code: condition for code, _, condition in famille.valeurs()}
            combine = Q()
            for code in codes:
                combine |= table[code]
            qs = qs.filter(combine)
        return qs

    def familles_actives(self, filtres, contexte=None):
        """Familles contenant une valeur retenue.

        Le menu replie chaque famille dans un sous-menu : sans cet indicateur,
        une valeur active y serait invisible tant qu'on ne survole pas la ligne.
        """
        actives = {f.cle: f.est_active(filtres) for f in self.familles}
        for famille in self.familles:
            if famille.applique and famille.cle in (contexte or {}):
                actives[famille.cle] = bool(contexte[famille.cle])
        return actives

    # ── Regroupement ────────────────────────────────────────────────────────

    def dimensions_retenues(self, groupes):
        """Dimensions demandées, dans l'ordre où l'utilisateur les a choisies."""
        return [self.dimensions[g] for g in groupes if g in self.dimensions]

    def trier(self, qs, groupes):
        """Trie pour que les groupes soient cohérents avec leur imbrication."""
        dims = self.dimensions_retenues(groupes)
        tri = []
        for dim in dims:
            for champ in dim.order:
                if champ not in tri:
                    tri.append(champ)
        for champ in self.tri_defaut:
            if champ not in tri:
                tri.append(champ)
        return qs.order_by(*tri) if tri else qs


# ── Comptage ────────────────────────────────────────────────────────────────

def _totaux_feuilles_sql(qs, dims):
    """Compte en base les combinaisons de valeurs, au niveau le plus fin.

    Les groupes sont ordonnés par leurs valeurs : l'ordre des en-têtes est ainsi
    naturel (chronologique pour une date, alphabétique pour un nom) et stable.
    Retourne aussi, pour chaque groupe racine, les valeurs brutes de la base —
    nécessaires pour ne recharger que les lignes des groupes affichés.
    """
    annotations, champs = {}, []
    for dim in dims:
        annotations.update(dim.annotate)
        champs.extend(dim.values)
    lignes = (qs.annotate(**annotations).order_by(*champs)
                .values(*champs).annotate(_n=Count('id')))
    racine = dims[0]
    totaux, brutes = {}, defaultdict(set)
    for ligne in lignes:
        chemin = tuple(dim.label(ligne) for dim in dims)
        totaux[chemin] = totaux.get(chemin, 0) + ligne['_n']
        # Valeurs brutes du premier niveau, sous forme de tuple : elles servent à
        # ne recharger que les lignes des groupes affichés.
        brutes[chemin[0]].add(tuple(ligne[champ] for champ in racine.values))
    return totaux, dict(brutes)


def _totaux_feuilles_python(qs, dims):
    """Compte en parcourant la sélection : nécessaire dès qu'une dimension n'est
    pas agrégeable en SQL (valeur dans un JSONField, appartenance multiple).

    L'ordre d'insertion suit celui de la requête, déjà triée selon les
    dimensions : les en-têtes sortent donc dans le même ordre qu'en SQL.
    """
    totaux, brutes = {}, defaultdict(set)
    for objet in qs:
        for chemin in _chemins(objet, dims):
            totaux[chemin] = totaux.get(chemin, 0) + 1
            # Pas de valeur brute en base ici : on transmet le libellé lui-même,
            # que le `filtre` de la dimension saura retraduire.
            brutes[chemin[0]].add((chemin[0],))
    return totaux, dict(brutes)


def _chemins(objet, dims):
    """Chemins de groupe d'un objet : plusieurs si une dimension est multivaluée."""
    chemins = [()]
    for dim in dims:
        valeurs = dim.valeur(objet)
        if not isinstance(valeurs, (list, tuple, set)):
            valeurs = [valeurs]
        valeurs = list(valeurs) or ['—']
        chemins = [chemin + (valeur,) for chemin in chemins for valeur in valeurs]
    return chemins


def _sommes_par_prefixe(totaux):
    """Total de chaque nœud de l'arbre, obtenu en cumulant ses feuilles."""
    sommes = defaultdict(int)
    for chemin, n in totaux.items():
        for i in range(1, len(chemin) + 1):
            sommes[chemin[:i]] += n
    return sommes


def paginer_groupes(qs_filtre, dims, numero_page, groupes_par_page=8):
    """Pagine les **groupes** plutôt que les lignes, à la manière d'Odoo.

    Avec un regroupement actif, paginer les lignes conduit à afficher des groupes
    dont les lignes sont sur une autre page : on les déplie et rien n'apparaît.
    Ici on pagine les groupes racines, puis on charge **toutes** les lignes de
    ceux affichés — un groupe visible s'ouvre donc toujours.

    Retourne (arbre, page_de_groupes, nombre_total_de_groupes).
    """
    from django.core.paginator import Paginator

    totaux, brutes = (_totaux_feuilles_sql(qs_filtre, dims)
                      if all(d.agregeable for d in dims)
                      else _totaux_feuilles_python(qs_filtre, dims))

    # Groupes racines dans l'ordre de l'agrégation, sans doublon.
    racines_libelles = list(dict.fromkeys(chemin[0] for chemin in totaux))
    page = Paginator(racines_libelles, groupes_par_page).get_page(numero_page)
    retenus = set(page.object_list)

    # Ne recharger que les lignes des groupes affichés, quand la dimension
    # racine sait se traduire en filtre ; sinon on parcourt toute la sélection
    # (cas d'une valeur en JSONField ou d'une appartenance multiple).
    racine = dims[0]
    if racine.filtrable and brutes:
        valeurs = set()
        for libelle in retenus:
            valeurs |= brutes.get(libelle, set())
        if valeurs:
            # L'annotation doit précéder le filtre : une dimension calculée
            # (tranche d'âge, mois) se filtre sur son annotation.
            base = qs_filtre.annotate(**racine.annotate) if racine.annotate else qs_filtre
            lignes = list(base.filter(racine.filtre(valeurs)))
        else:
            lignes = []
    else:
        lignes = list(qs_filtre)

    totaux_page = {c: n for c, n in totaux.items() if c[0] in retenus}
    arbre = _arbre(totaux_page, lignes, dims, retenus)
    return arbre, page, len(racines_libelles)


def _arbre(totaux, lignes, dims, retenus=None):
    """Construit l'arbre de groupes et y range les lignes fournies.

    Chaque nœud porte :
      chemin    identifiant hiérarchique ('0-2-1'), utilisé pour replier
      niveau    profondeur, pour l'indentation
      libelle   valeur du groupe
      total     nombre réel dans la sélection entière
      sur_page  nombre de lignes effectivement chargées
      partiel   vrai si toutes les lignes du groupe ne sont pas chargées
      enfants / lignes selon qu'on est ou non sur la dernière dimension

    L'arbre vient de l'agrégation et non des lignes : tous les groupes de la
    sélection apparaissent avec leur compte réel, et le total d'un parent est
    exactement la somme de ses enfants.
    """
    sommes = _sommes_par_prefixe(totaux)
    racines, index = [], {}

    def noeud(cle_complete, libelle, niveau, parent):
        existant = index.get(cle_complete)
        if existant:
            return existant
        freres = parent['enfants'] if parent else racines
        cree = {
            'chemin':   (parent['chemin'] + '-' if parent else '') + str(len(freres)),
            'parent':   parent['chemin'] if parent else '',
            'niveau':   niveau,
            # Retrait calculé ici pour éviter toute arithmétique dans le gabarit.
            'indent':   14 + niveau * 20,
            'libelle':  libelle,
            'total':    sommes.get(cle_complete, 0),
            'sur_page': 0,
            'partiel':  False,
            'enfants':  [],
            'lignes':   [],
        }
        freres.append(cree)
        index[cle_complete] = cree
        return cree

    for chemin in totaux:
        parent = None
        for niveau, libelle in enumerate(chemin):
            parent = noeud(chemin[:niveau + 1], libelle, niveau, parent)

    for objet in lignes:
        for chemin in _chemins(objet, dims):
            if retenus is not None and chemin[0] not in retenus:
                continue
            feuille = index.get(chemin)
            if feuille is None:          # groupe hors page : garde-fou
                continue
            feuille['lignes'].append(objet)
            for niveau in range(1, len(chemin) + 1):
                index[chemin[:niveau]]['sur_page'] += 1

    def marquer(noeuds):
        for n in noeuds:
            n['partiel'] = n['sur_page'] < n['total']
            marquer(n['enfants'])
    marquer(racines)
    return racines


# ── Construction des menus ──────────────────────────────────────────────────
# Les gabarits ne peuvent pas appeler de méthode avec argument : on prépare ici
# des structures directement affichables, ce qui évite d'écrire un menu à la main
# dans chaque module.

def menu_filtres(familles, filtres, date_from='', date_to=''):
    """Décrit le menu « Filtres » : une entrée par famille.

    Une famille à valeur unique devient une simple ligne à cocher ; les autres
    se replient dans un sous-menu latéral. `active` sert à marquer la ligne
    parente, sans quoi une valeur retenue serait invisible tant qu'on ne survole
    pas la ligne.
    """
    entrees = []
    for famille in familles:
        valeurs = famille.valeurs()
        retenus = set(famille.codes_retenus(filtres))
        active = bool(retenus)
        if famille.dates and (date_from or date_to):
            active = True
        entrees.append({
            'cle':       famille.cle,
            'libelle':   famille.libelle,
            'exclusive': famille.exclusive,
            'dates':     famille.dates,
            'active':    active,
            'unique':    len(valeurs) == 1,
            'valeurs':   [{'code': code, 'libelle': libelle, 'active': code in retenus}
                          for code, libelle, _ in valeurs],
        })
    return entrees


#: Intitulé de l'entrée qui donne accès aux champs non déclarés.
LIBELLE_GROUPEMENT_PERSO = 'Ajouter un groupement personnalisé'


def menu_groupes(dimensions, groupes):
    """Décrit le menu « Regrouper par ».

    Les dimensions déclarant un `sous_menu` (les découpages de date, par exemple)
    sont rassemblées sous une entrée dépliable, insérée à la place de la première
    d'entre elles pour respecter l'ordre de déclaration.

    Les dimensions `perso` — un champ de formulaire par dimension, il y en a
    plusieurs centaines — ne peuvent pas devenir autant de lignes de menu : le
    sous-menu déborderait de l'écran sans qu'on puisse le parcourir. Elles
    partent donc dans une liste déroulante, groupée par onglet de formulaire, où
    le navigateur assure défilement et recherche au clavier. Celles déjà
    retenues en sortent pour devenir des lignes cochées, seul moyen de les
    retirer.
    """
    retenus = set(groupes)
    entrees, sous_menus = [], {}
    # Pas d'indicateur « actif » sur cette entrée : c'est une action, pas un
    # état. Les groupements retenus sont listés juste au-dessus, cochés.
    perso = {'perso': True, 'libelle': LIBELLE_GROUPEMENT_PERSO,
             'actives': [], 'groupes': []}
    groupes_perso = {}

    for dim in dimensions:
        item = {'cle': dim.cle, 'libelle': dim.libelle, 'active': dim.cle in retenus}

        if dim.perso:
            if item['active']:
                # Le groupe accompagne le libellé : deux onglets du formulaire
                # peuvent porter le même intitulé (« Statut VAT »), et une ligne
                # cochée sans son groupe ne dirait pas de laquelle il s'agit.
                item['groupe'] = dim.sous_menu or ''
                perso['actives'].append(item)
                continue
            titre = dim.sous_menu or ''
            if titre not in groupes_perso:
                groupes_perso[titre] = {'libelle': titre, 'valeurs': []}
                perso['groupes'].append(groupes_perso[titre])
            groupes_perso[titre]['valeurs'].append(item)
            continue

        if not dim.sous_menu:
            entrees.append(item)
            continue
        if dim.sous_menu not in sous_menus:
            sous_menus[dim.sous_menu] = {'libelle': dim.sous_menu, 'valeurs': [], 'active': False}
            entrees.append(sous_menus[dim.sous_menu])
        sous_menus[dim.sous_menu]['valeurs'].append(item)
        if item['active']:
            sous_menus[dim.sous_menu]['active'] = True

    if perso['actives'] or perso['groupes']:
        entrees.append(perso)
    return entrees


# ── Filtres et regroupements personnalisés ──────────────────────────────────
# L'utilisateur peut filtrer ou regrouper sur n'importe quel champ, sans qu'il
# ait été déclaré. Les champs sont découverts sur le modèle, ce qui donne aussi
# une liste blanche : une condition portant sur autre chose est ignorée, une URL
# forgée ne peut donc pas atteindre une relation arbitraire.

#: Opérateurs proposés selon le type de champ, et traduction en lookup Django.
#: `None` en valeur de lookup signale un traitement particulier (vide / non vide).
OPERATEURS = {
    'texte': [
        ('contient',     'contient',        'icontains'),
        ('ne_contient',  'ne contient pas', 'icontains'),
        ('egal',         'est égal à',      'iexact'),
        ('vide',         'est vide',        None),
        ('non_vide',     "n'est pas vide",  None),
    ],
    'nombre': [
        ('egal',      'est égal à',       'exact'),
        ('different', 'est différent de', 'exact'),
        ('sup',       'est supérieur à',  'gt'),
        ('inf',       'est inférieur à',  'lt'),
        ('vide',      'est vide',         None),
        ('non_vide',  "n'est pas vide",   None),
    ],
    'date': [
        ('egal',     'est le',         'date'),
        ('apres',    'est après le',   'date__gt'),
        ('avant',    'est avant le',   'date__lt'),
        ('vide',     'est vide',       None),
        ('non_vide', "n'est pas vide", None),
    ],
    'booleen': [
        ('vrai', 'est vrai', 'exact'),
        ('faux', 'est faux', 'exact'),
    ],
    'choix': [
        ('egal',      'est',          'exact'),
        ('different', "n'est pas",    'exact'),
        ('vide',      'est vide',     None),
        ('non_vide',  "n'est pas vide", None),
    ],
    # ── Champs vivant dans un JSONField ──
    # Une valeur JSON est toujours du texte. Les dates au format ISO se
    # comparent donc correctement lettre par lettre (2026-03 vient bien après
    # 2026-02), mais pas les nombres : « 9 » passerait pour plus grand que
    # « 12 ». D'où deux catégories à part, qui n'offrent que les opérateurs
    # justes — mieux vaut ne pas proposer « est supérieur à » que de le
    # proposer faux.
    'date_json': [
        ('egal',     'est le',         'exact'),
        ('apres',    'est après le',   'gt'),
        ('avant',    'est avant le',   'lt'),
        ('vide',     'est vide',       None),
        ('non_vide', "n'est pas vide", None),
    ],
    'nombre_json': [
        ('egal',      'est égal à',       'exact'),
        ('different', 'est différent de', 'exact'),
        ('vide',      'est vide',         None),
        ('non_vide',  "n'est pas vide",   None),
    ],
    'lien': [
        ('egal',      'est',            'exact'),
        ('different', "n'est pas",      'exact'),
        ('vide',      'est vide',       None),
        ('non_vide',  "n'est pas vide", None),
    ],
}

#: Opérateurs qui nient la condition plutôt que de l'appliquer.
_NEGATIFS = {'ne_contient', 'different'}


def _type_champ(champ):
    """Catégorie d'un champ de modèle, pour choisir opérateurs et saisie."""
    from django.db import models
    if getattr(champ, 'choices', None):
        return 'choix'
    if isinstance(champ, models.BooleanField):
        return 'booleen'
    if isinstance(champ, (models.DateField, models.DateTimeField)):
        return 'date'
    if isinstance(champ, (models.IntegerField, models.FloatField, models.DecimalField)):
        return 'nombre'
    if isinstance(champ, (models.ForeignKey, models.OneToOneField)):
        return 'lien'
    if isinstance(champ, (models.CharField, models.TextField, models.EmailField)):
        return 'texte'
    return None


def champs_filtrables(modele, extra=(), exclure=(), groupe=''):
    """Champs sur lesquels filtrer ou regrouper, découverts sur le modèle.

    `extra` permet d'ajouter des chemins traversant une relation
    (« patient__nom »), utiles mais non découvrables automatiquement sans risquer
    d'exposer tout le schéma. Chaque entrée y est soit un chemin, soit un couple
    (chemin, groupe) pour la ranger ailleurs que les champs du modèle.

    `groupe` nomme la famille sous laquelle les champs sont présentés, quand la
    liste en compte assez pour mériter des intertitres.
    """
    from django.db import models
    trouves = []
    for champ in modele._meta.fields:
        if champ.primary_key or champ.name in exclure:
            continue
        categorie = _type_champ(champ)
        if not categorie:
            continue
        entree = {
            'chemin':  champ.name,
            'libelle': str(champ.verbose_name).capitalize(),
            'type':    categorie,
            'choix':   [(str(v), str(l)) for v, l in (champ.choices or [])],
            'groupe':  groupe,
        }
        if categorie == 'lien':
            entree['modele_lie'] = champ.related_model
        trouves.append(entree)

    for entree_extra in extra:
        chemin, groupe_extra = (entree_extra if isinstance(entree_extra, (tuple, list))
                                else (entree_extra, groupe))
        try:
            champ = modele._meta.get_field(chemin.split('__')[0])
        except Exception:
            continue
        cible = champ.related_model if getattr(champ, 'related_model', None) else None
        for partie in chemin.split('__')[1:]:
            if cible is None:
                break
            try:
                champ = cible._meta.get_field(partie)
            except Exception:
                champ = None
                break
            cible = getattr(champ, 'related_model', None)
        categorie = _type_champ(champ) if champ else None
        if not categorie:
            continue
        entree = {
            'chemin':  chemin,
            'libelle': str(champ.verbose_name).capitalize(),
            'type':    categorie,
            'choix':   [(str(v), str(l)) for v, l in (champ.choices or [])],
            'groupe':  groupe_extra,
        }
        # Comme pour les champs du modèle : sans le modèle visé, l'agrégation
        # d'un lien reste une clé primaire nue (« 2 ») là où le libellé calculé
        # depuis l'objet donne son nom — le groupe s'affiche alors avec son
        # compte mais ne charge jamais ses lignes. Le constructeur de conditions
        # en a besoin pour la même raison, afin de proposer des noms.
        if categorie == 'lien':
            entree['modele_lie'] = champ.related_model
        trouves.append(entree)
    return trouves


def _lookup(categorie, operateur):
    for code, _, lookup in OPERATEURS.get(categorie, []):
        if code == operateur:
            return lookup, code
    return None, None


def conditions_demandees(request, champs):
    """Conditions personnalisées lues dans l'URL, validées contre la liste blanche.

    Les trois listes parallèles `cf` (champ), `co` (opérateur) et `cv` (valeur)
    évitent d'avoir à inventer un séparateur, donc à gérer son échappement.
    """
    par_chemin = {c['chemin']: c for c in champs}
    chemins = request.GET.getlist('cf')
    operateurs = request.GET.getlist('co')
    valeurs = request.GET.getlist('cv')

    conditions = []
    for i, chemin in enumerate(chemins):
        champ = par_chemin.get(chemin)
        if not champ:
            continue                      # champ inconnu : condition ignorée
        operateur = operateurs[i] if i < len(operateurs) else ''
        lookup, code = _lookup(champ['type'], operateur)
        if code is None:
            continue                      # opérateur invalide pour ce type
        conditions.append({
            'champ':     champ,
            'operateur': code,
            'valeur':    valeurs[i] if i < len(valeurs) else '',
        })
    return conditions


def appliquer_conditions(qs, conditions, mode='et'):
    """Applique les conditions personnalisées, combinées en ET ou en OU."""
    if not conditions:
        return qs
    combine = None
    for cond in conditions:
        q = _condition_en_q(cond)
        if q is None:
            continue
        if combine is None:
            combine = q
        elif mode == 'ou':
            combine |= q
        else:
            combine &= q
    return qs.filter(combine) if combine is not None else qs


def _condition_en_q(cond):
    champ, operateur, valeur = cond['champ'], cond['operateur'], cond['valeur']
    chemin, categorie = champ['chemin'], champ['type']
    lookup, _ = _lookup(categorie, operateur)

    # Un champ de formulaire laissé vide est enregistré comme chaîne vide, pas
    # comme valeur absente : c'est vrai des champs texte du modèle comme de
    # toutes les valeurs de registre, dates et nombres compris.
    aussi_chaine_vide = categorie in ('texte', 'choix', 'date_json', 'nombre_json')
    if operateur == 'vide':
        vide = Q(**{f'{chemin}__isnull': True})
        if aussi_chaine_vide:
            vide |= Q(**{chemin: ''})
        return vide
    if operateur == 'non_vide':
        plein = Q(**{f'{chemin}__isnull': False})
        if aussi_chaine_vide:
            plein &= ~Q(**{chemin: ''})
        return plein
    if categorie == 'booleen':
        return Q(**{chemin: operateur == 'vrai'})
    if valeur == '':
        return None

    q = Q(**{f'{chemin}__{lookup}': valeur})
    return ~q if operateur in _NEGATIFS else q


def dimensions_auto(champs, exclure=()):
    """Dimensions de regroupement générées depuis les champs découverts.

    Alimente l'entrée « Ajouter un groupement personnalisé » : l'utilisateur peut
    regrouper sur n'importe quel champ, sans qu'il ait fallu le déclarer. Les
    dates sont écartées, les dimensions dédiées (année, mois, semaine…) étant plus
    parlantes qu'un regroupement sur l'horodatage exact.

    `sous_menu` reçoit le groupe du champ : c'est le titre sous lequel la liste
    déroulante le rangera.
    """
    from django.db.models import TextField
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast

    dims = []
    for champ in champs:
        chemin, categorie = champ['chemin'], champ['type']
        if categorie in ('date', 'date_json') or chemin in exclure:
            continue

        # `cle_ligne` est la clé sous laquelle la valeur ressort de l'agrégation ;
        # `chemin` reste la voie d'accès depuis l'objet. Les deux se confondent
        # pour un champ de modèle, mais pas pour une valeur de JSONField : lue
        # par le chemin ordinaire, elle est reconvertie au passage (SQLite relit
        # « "0.00" » comme le nombre 0.0) et ne correspond alors plus ni au
        # libellé calculé depuis l'objet, ni à ce que contient la base — le
        # groupe s'afficherait avec son compte mais resterait vide au dépliage.
        # KeyTextTransform rend le texte tel qu'il est stocké ; le Cast en dit le
        # type, sans quoi la valeur serait de nouveau prise pour du JSON au
        # moment de filtrer (« malformed JSON » sur les textes libres).
        cle_ligne, annotate = chemin, None
        if champ.get('json'):
            prefixe, cle_json = chemin.rsplit('__', 1)
            cle_ligne = 'j_' + chemin.replace('__', '_')
            annotate = {cle_ligne: Cast(KeyTextTransform(cle_json, prefixe), TextField())}

        commun = {'cle': f'auto_{chemin}', 'libelle': champ['libelle'],
                  'values': (cle_ligne,), 'order': (cle_ligne,), 'annotate': annotate,
                  'sous_menu': champ.get('groupe', ''), 'perso': True}

        if categorie == 'choix':
            libelles = dict(champ['choix'])
            dims.append(Dimension(valeur=_valeur_choix(chemin, libelles),
                                  label=_label_choix(cle_ligne, libelles), **commun))
        elif categorie == 'booleen':
            dims.append(Dimension(valeur=_valeur_booleen(chemin),
                                  label=_label_booleen(cle_ligne), **commun))
        elif categorie == 'lien':
            dims.append(Dimension(valeur=_valeur_lien(chemin),
                                  label=_label_lien(cle_ligne, champ.get('modele_lie')), **commun))
        else:                                   # texte, nombre, nombre_json
            dims.append(Dimension(valeur=_valeur_brute(chemin),
                                  label=_label_brut(cle_ligne), **commun))
    return dims


# Fabriques de fonctions : une closure par champ, pour que chaque dimension
# garde son propre chemin sans capturer la variable de boucle.

def _attribut(objet, chemin):
    """Valeur d'un chemin de champ sur un objet, relations et JSON comprises.

    Le passage par un dictionnaire est indispensable aux champs de registre :
    leur chemin traverse un JSONField (`registre_cpn__donnees__cpn_statut_vat`),
    dont les clés ne sont pas des attributs. Sans cela le libellé calculé depuis
    l'objet ne correspondrait pas à celui calculé en base, et les lignes ne
    retrouveraient pas leur groupe.
    """
    for partie in chemin.split('__'):
        if isinstance(objet, dict):
            objet = objet.get(partie)
        else:
            # Une relation inverse absente lève une exception qui hérite
            # d'AttributeError : getattr avec défaut la rattrape.
            objet = getattr(objet, partie, None)
        if objet is None:
            return None
    return objet


def _valeur_choix(chemin, libelles):
    return lambda o: libelles.get(str(_attribut(o, chemin)), 'Non précisé') if _attribut(o, chemin) not in (None, '') else 'Non précisé'


def _label_choix(chemin, libelles):
    return lambda r: libelles.get(str(r[chemin]), 'Non précisé') if r[chemin] not in (None, '') else 'Non précisé'


def _valeur_booleen(chemin):
    return lambda o: 'Oui' if _attribut(o, chemin) else 'Non'


def _label_booleen(chemin):
    return lambda r: 'Oui' if r[chemin] else 'Non'


def _valeur_lien(chemin):
    return lambda o: str(_attribut(o, chemin)) if _attribut(o, chemin) is not None else 'Non renseigné'


def _label_lien(chemin, modele_lie):
    """Libellé d'un lien : la valeur agrégée est une clé, il faut la résoudre.

    Le dictionnaire est construit à la première demande puis conservé, pour ne pas
    interroger la base une fois par groupe.
    """
    cache = {}

    def libelle(ligne):
        pk = ligne[chemin]
        if pk is None:
            return 'Non renseigné'
        if not cache and modele_lie is not None:
            cache.update({o.pk: str(o) for o in modele_lie.objects.all()})
        return cache.get(pk, str(pk))
    return libelle


def _valeur_brute(chemin):
    return lambda o: str(_attribut(o, chemin)) if _attribut(o, chemin) not in (None, '') else 'Non renseigné'


def _label_brut(chemin):
    return lambda r: str(r[chemin]) if r[chemin] not in (None, '') else 'Non renseigné'


#: Au-delà de ce nombre d'enregistrements, un champ de lien n'est plus proposé
#: sous forme de liste déroulante : la charger entière serait déraisonnable.
MAX_CHOIX_LIEN = 200


def _sans_accent(texte):
    """Clé de tri : « Œdèmes » doit se ranger avec les O, pas après les Z."""
    import unicodedata
    decompose = unicodedata.normalize('NFD', texte.lower())
    return ''.join(c for c in decompose if unicodedata.category(c) != 'Mn')


def champs_pour_navigateur(champs):
    """Description des champs destinée au constructeur de conditions.

    Renvoie une structure sérialisable en JSON. Les opérateurs sont donnés une
    fois par catégorie et non par champ : avec plusieurs centaines de champs, les
    répéter à chaque entrée pesait l'essentiel du poids de la page.

    Les liens ne sont déroulés en liste de valeurs que si la table visée reste
    petite.
    """
    sortie, ordre_groupes = [], []
    for champ in champs:
        categorie = champ['type']
        choix = list(champ['choix'])
        if categorie == 'lien' and champ.get('modele_lie') is not None:
            modele = champ['modele_lie']
            # Un enregistrement de plus que la limite suffit à savoir si la table
            # est trop grande : un COUNT séparé doublerait le nombre de requêtes,
            # et il y a autant de tables à interroger que de champs de lien.
            objets = list(modele.objects.all()[:MAX_CHOIX_LIEN + 1])
            if len(objets) <= MAX_CHOIX_LIEN:
                choix = [(str(o.pk), str(o)) for o in objets]
            else:
                categorie = 'nombre'      # repli : saisie de l'identifiant
        groupe = champ.get('groupe', '')
        if groupe not in ordre_groupes:
            ordre_groupes.append(groupe)
        sortie.append({
            'chemin':  champ['chemin'],
            'libelle': champ['libelle'],
            'type':    categorie,
            'choix':   choix,
            'groupe':  groupe,
        })

    # Groupes dans l'ordre de déclaration, champs par ordre alphabétique à
    # l'intérieur de chacun : la liste déroulante se parcourt ainsi comme le
    # formulaire, onglet par onglet.
    sortie.sort(key=lambda c: (ordre_groupes.index(c['groupe']), _sans_accent(c['libelle'])))
    return {
        'champs': sortie,
        'operateurs': {categorie: [{'code': c, 'libelle': l} for c, l, _ in liste]
                       for categorie, liste in OPERATEURS.items()},
        # Transmis plutôt que redéfini dans le script : une seule source.
        'sans_valeur': list(OPERATEURS_SANS_VALEUR),
    }


#: Opérateurs n'attendant aucune valeur : la saisie doit alors être masquée.
OPERATEURS_SANS_VALEUR = ('vide', 'non_vide', 'vrai', 'faux')
