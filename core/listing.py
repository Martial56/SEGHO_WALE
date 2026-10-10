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

from django.core.paginator import Page, Paginator
from django.db.models import Count, Q

#: Paramètre d'URL par lequel le navigateur réclame les lignes d'un groupe
#: qu'il vient de déplier. Préfixé d'un tiret bas : ce n'est pas un filtre,
#: et la mémoire des listes doit l'ignorer (voir core.memoire_listing).
PARAM_GROUPE = '_groupe'

#: Paramètre d'URL portant les groupes à rendre déjà dépliés, sous la forme
#: `<page>:<chemin>,<chemin>`. Il voyage avec les filtres et le regroupement, et
#: la mémoire des listes le retient comme eux (voir core.memoire_listing) : la
#: page revient donc dépliée comme on l'avait laissée, sans rien à rattraper
#: après l'affichage.
#:
#: Le numéro de page fait partie de la valeur parce qu'un chemin est positionnel
#: — « 0 » désigne le premier groupe *de la page affichée*. Sans lui, passer à la
#: page suivante aurait déplié un groupe sans rapport, en silence.
PARAM_OUVERTS = 'ouverts'

#: Valeur de `PARAM_GROUPE` réclamant les lignes de **tous** les groupes de la
#: page, en une seule requête. C'est ce que le navigateur demande en tâche de
#: fond une fois la page affichée, pour que déplier ne fasse plus attendre.
TOUS_LES_GROUPES = '*'

#: Paramètre d'URL portant le rang de la première ligne réclamée dans un groupe.
#: Un gros groupe ne sort pas d'un bloc : « Charger plus » redemande le même
#: groupe à partir de là où le lot précédent s'est arrêté.
PARAM_DECALAGE = '_decalage'

#: Nombre de lignes rendues d'un coup pour un groupe déplié.
#:
#: Sans ce plafond, déplier un groupe de trente mille lignes les rendait toutes :
#: la réponse pesait des dizaines de méga-octets et la page se figeait le temps
#: de les poser. On n'en montre donc qu'un lot, suivi d'une entrée « Charger
#: plus » tant qu'il en reste — c'est la pagination des groupes, à l'intérieur
#: d'un groupe.
#:
#: Le préchargement, lui, ne passe pas par ici : il a son propre garde-fou
#: côté navigateur (MAX_LIGNES_PRECHARGEES dans listing_groupes.js), qui renonce
#: à précharger une page trop lourde plutôt que de la tronquer.
TAILLE_LOT_GROUPE = 80


# ── Déclarations ────────────────────────────────────────────────────────────

def condition_recherche(champs, q, mots_max=6):
    """Condition de recherche libre sur plusieurs champs.

    Le texte saisi est découpé en mots : chaque mot doit se retrouver dans au
    moins un des champs — ET entre les mots, OU entre les champs. Sans ce
    découpage, « anoh josiane » était cherché tel quel dans `nom`, puis tel
    quel dans `prenoms`, et ne trouvait rien : le nom et les prénoms vivent
    dans deux colonnes distinctes. L'ordre de saisie n'a plus d'importance,
    « josiane anoh » trouve la même fiche.

    Le nombre de mots est borné : une saisie collée par erreur ne doit pas
    fabriquer une requête à cinquante conditions.
    """
    condition = Q()
    for mot in (q or '').split()[:mots_max]:
        par_champ = Q()
        for champ in champs:
            par_champ |= Q(**{f'{champ}__icontains': mot})
        condition &= par_champ
    return condition


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
                 par_page=25, filtres_defaut=(), tri_defaut=(), tris=None):
        self.recherche = tuple(recherche)
        self.familles = list(familles)
        self.dimensions = OrderedDict((d.cle, d) for d in dimensions)
        self.par_page = par_page
        self.filtres_defaut = tuple(filtres_defaut)
        self.tri_defaut = tuple(tri_defaut)
        #: Colonnes triables : clé lisible dans l'URL -> champs du modèle.
        #: Le tri se fait en base, sur la totalité du résultat filtré. Trier en
        #: JavaScript ne réordonnait que les 25 lignes de la page affichée : on
        #: croyait voir le plus ancien, on voyait le plus ancien *de la page*.
        self.tris = dict(tris or {})

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
        return qs.filter(condition_recherche(self.recherche, q))

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

    def tri_demande(self, request):
        """Colonne de tri demandée, ou ('', 'asc') si aucune n'est valable.

        Une clé inconnue est ignorée plutôt que refusée : `order_by` sur un
        champ arbitraire venu de l'URL planterait la page.
        """
        cle = (request.GET.get('tri') or '').strip()
        sens = 'desc' if request.GET.get('sens') == 'desc' else 'asc'
        return (cle if cle in self.tris else ''), sens

    def trier(self, qs, groupes, tri='', sens='asc'):
        """Ordonne le résultat.

        L'ordre est celui-ci, et il compte : d'abord les champs des dimensions
        de regroupement — sans quoi les groupes se mélangeraient —, puis le tri
        demandé par l'utilisateur, qui joue donc *à l'intérieur* de chaque
        groupe, et enfin le tri par défaut de la liste.
        """
        dims = self.dimensions_retenues(groupes)
        ordre = []

        def ajouter(champ):
            if champ and champ not in ordre:
                ordre.append(champ)

        for dim in dims:
            for champ in dim.order:
                ajouter(champ)
        for champ in self.tris.get(tri, ()):
            ajouter(f'-{champ}' if sens == 'desc' else champ)
        for champ in self.tri_defaut:
            ajouter(champ)
        return qs.order_by(*ordre) if ordre else qs

    # ── Sélection ───────────────────────────────────────────────────────────

    def selection(self, request, base_qs, champs=(), contexte=None, dimensions=None,
                  trier=None):
        """Jeu filtré tel que la liste l'affiche, et dimensions retenues.

        Rassemble les cinq gestes que chaque vue de liste répétait — recherche,
        filtres, conditions personnalisées, tri, dimensions — pour que l'export
        puisse emprunter le même chemin que la page.

        `trier(qs, groupes)` remplace le tri par défaut pour les listes qui en
        ont un à elles : celle des rendez-vous ordonne la journée en cours à
        l'endroit et les jours passés à l'envers, ce que `trier` ne sait pas
        exprimer.
        """
        q = (request.GET.get('q') or '').strip()
        groupes = request.GET.getlist('group')
        filtres = self.filtres_demandes(request)

        qs = self.appliquer_recherche(base_qs, q)
        qs = self.appliquer_filtres(qs, filtres, contexte or {})
        conditions = conditions_demandees(request, champs) if champs else []
        mode = 'ou' if request.GET.get('cm') == 'ou' else 'et'
        qs = appliquer_conditions(qs, conditions, mode)
        tri, sens = self.tri_demande(request)
        qs = trier(qs, groupes) if trier else self.trier(qs, groupes, tri, sens)

        table = self.dimensions if dimensions is None else dimensions
        dims = [table[g] for g in groupes if g in table]
        return Selection(qs=qs, dims=dims, filtres=filtres, groupes=groupes,
                         q=q, conditions=conditions, mode_conditions=mode,
                         tri=tri, sens=sens)


#: Paramètres d'URL qui ne décrivent pas la sélection mais la façon de la
#: parcourir à l'écran. Les emporter dans un lien d'export n'aurait aucun effet
#: et donnerait à croire qu'on ne télécharge que la page affichée.
_PARAMS_DE_PAGE = ('page', 'format', PARAM_GROUPE, PARAM_OUVERTS, PARAM_DECALAGE)


def parametres_export(request):
    """Query string à recopier dans les liens d'export : la sélection, sans la
    pagination ni le dépliage."""
    params = request.GET.copy()
    for cle in _PARAMS_DE_PAGE:
        params.pop(cle, None)
    return params.urlencode()


class Selection:
    """Ce que la liste montre : le jeu filtré, et le découpage demandé.

    Rendue par `Listing.selection`, elle sert la page comme son export. Les
    deux lisent donc le même objet, ce qui est la seule façon de garantir qu'un
    fichier téléchargé porte exactement les lignes affichées — auparavant
    l'export refaisait sa propre requête, sans filtre, et sortait la table
    entière.
    """

    def __init__(self, qs, dims, filtres, groupes, q, conditions,
                 mode_conditions, tri='', sens='asc'):
        self.qs = qs
        self.dims = dims
        self.filtres = filtres
        self.groupes = groupes
        self.q = q
        self.conditions = conditions
        self.mode_conditions = mode_conditions
        self.tri = tri
        self.sens = sens

    @property
    def active(self):
        """Une sélection est-elle posée, ou regarde-t-on le jeu entier ?"""
        return bool(self.filtres or self.groupes or self.q or self.conditions)


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
    # Valeurs brutes de **chaque** niveau, par chemin complet : c'est ce qui
    # permet de ne charger qu'un groupe précis quand on le déplie.
    brutes_chemin = defaultdict(lambda: [set() for _ in dims])
    for ligne in lignes:
        chemin = tuple(dim.label(ligne) for dim in dims)
        totaux[chemin] = totaux.get(chemin, 0) + ligne['_n']
        # Valeurs brutes du premier niveau, sous forme de tuple : elles servent à
        # ne recharger que les lignes des groupes affichés.
        brutes[chemin[0]].add(tuple(ligne[champ] for champ in racine.values))
        for niveau, dim in enumerate(dims):
            brutes_chemin[chemin][niveau].add(
                tuple(ligne[champ] for champ in dim.values))
    return totaux, dict(brutes), dict(brutes_chemin)


def _totaux_feuilles_python(qs, dims):
    """Compte en parcourant la sélection : nécessaire dès qu'une dimension n'est
    pas agrégeable en SQL (valeur dans un JSONField, appartenance multiple).

    L'ordre d'insertion suit celui de la requête, déjà triée selon les
    dimensions : les en-têtes sortent donc dans le même ordre qu'en SQL.
    """
    totaux, brutes = {}, defaultdict(set)
    brutes_chemin = defaultdict(lambda: [set() for _ in dims])
    for objet in qs:
        for chemin in _chemins(objet, dims):
            totaux[chemin] = totaux.get(chemin, 0) + 1
            # Pas de valeur brute en base ici : on transmet le libellé lui-même,
            # que le `filtre` de la dimension saura retraduire.
            brutes[chemin[0]].add((chemin[0],))
            for niveau, libelle in enumerate(chemin):
                brutes_chemin[chemin][niveau].add((libelle,))
    return totaux, dict(brutes), dict(brutes_chemin)


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


class _PageDeGroupes(Page):
    """Une page de groupes, dont l'étendue dépend des pages qui la précèdent.

    `Page` déduit ses bornes d'une taille de page constante ; ici elle varie,
    et les deux numéros se lisent donc sur le découpage réel.
    """

    def start_index(self):
        return self.paginator.debut(self.number)

    def end_index(self):
        return self.paginator.debut(self.number) + len(self.object_list) - 1


class _PaginateurDeGroupes(Paginator):
    """Pagine les groupes en visant un nombre d'**en-têtes** par page.

    En mode groupé, seuls les en-têtes racines sont visibles : les lignes de
    données et les sous-groupes partent repliés (`display:none` dans
    includes/listing/groupes.html). Ce qu'on lit à l'écran, ce sont donc des
    en-têtes, et une page doit en porter autant qu'une page à plat porte de
    lignes. Huit, le réglage d'origine, remplissait le quart d'un écran.

    Le plafond ne sert que d'amortisseur : les lignes des groupes affichés
    partent toutes dans le HTML même repliées, et une page de groupes énormes
    pèserait lourd pour rien. Il ne peut jamais réduire une page en dessous de
    `MINIMUM_GROUPES_PAR_PAGE` — mieux vaut une page lourde qu'une page qui
    n'affiche qu'un seul groupe.

    `per_page` ne sert qu'à satisfaire `Paginator` : le découpage ne passe pas
    par lui, `page()` et `num_pages` sont redéfinis.
    """

    #: Au-delà, on coupe la page : personne ne dépliera dix mille lignes.
    PLAFOND_LIGNES_CHARGEES = 1000
    #: En dessous, la page n'a plus de sens, le plafond cède.
    MINIMUM_GROUPES_PAR_PAGE = 5

    def __init__(self, libelles, tailles, groupes_par_page):
        super().__init__(libelles, per_page=max(1, groupes_par_page))
        self._pages = self._decouper(libelles, tailles, max(1, groupes_par_page))

    @classmethod
    def _decouper(cls, libelles, tailles, par_page):
        pages, courante, lignes = [], [], 0
        for libelle in libelles:
            taille = tailles.get(libelle, 1)
            trop_de_groupes = len(courante) >= par_page
            trop_de_lignes = (lignes + taille > cls.PLAFOND_LIGNES_CHARGEES
                              and len(courante) >= cls.MINIMUM_GROUPES_PAR_PAGE)
            if courante and (trop_de_groupes or trop_de_lignes):
                pages.append(courante)
                courante, lignes = [], 0
            courante.append(libelle)
            lignes += taille
        if courante:
            pages.append(courante)
        # Jamais zéro page : une sélection vide en garde une, vide.
        return pages or [[]]

    @property
    def num_pages(self):
        return len(self._pages)

    def debut(self, numero):
        """Rang du premier groupe de cette page, à partir de 1."""
        return sum(len(p) for p in self._pages[:numero - 1]) + 1

    def page(self, numero):
        numero = self.validate_number(numero)
        return _PageDeGroupes(self._pages[numero - 1], numero, self)


def paginer_groupes(qs_filtre, dims, numero_page, groupes_par_page=25,
                    chemin_demande=None, ouverts='', decalage=0):
    """Pagine les **groupes** plutôt que les lignes, à la manière d'Odoo.

    Avec un regroupement actif, paginer les lignes conduit à afficher des groupes
    dont les lignes sont sur une autre page : on les déplie et rien n'apparaît.
    On pagine donc les groupes racines, et un groupe visible contient toujours
    tout ce qu'il annonce.

    `groupes_par_page` est le `par_page` de la liste appelante : une page
    regroupée porte autant d'en-têtes qu'une page à plat porte de lignes, les
    lignes de données étant repliées. Une page peut en porter moins quand ses
    groupes sont énormes (voir `_PaginateurDeGroupes`).

    Les lignes de données ne sont chargées **que** pour le groupe nommé par
    `chemin_demande`, celui qu'on vient de déplier. Les charger toutes d'avance
    mettait dans le HTML, repliées et souvent jamais lues, toutes les lignes de
    tous les groupes affichés : une ligne pèse plus d'un kilo-octet, et un
    regroupement à gros groupes produisait une page de plusieurs dizaines de
    méga-octets.

    Le navigateur redemande donc la page avec `_groupe=<chemin>` et n'y prend
    que les lignes du groupe (static/js/listing_groupes.js), exactement comme
    `rafraichir()` ne prend que les zones qui l'intéressent. Un dépliage déjà
    chargé ne rappelle plus le serveur.

    `chemin_demande = TOUS_LES_GROUPES` réclame d'un coup les lignes de tous les
    groupes de la page. C'est ce que le navigateur demande en tâche de fond
    aussitôt la page affichée : l'affichage reste aussi rapide qu'avec les
    en-têtes seuls, et quand on déplie, les lignes sont déjà là. On retrouve
    ainsi le dépliage instantané d'avant le chargement différé, sans retrouver
    sa page de plusieurs méga-octets — c'est le même volume, mais après coup et
    sans bloquer.

    `decalage` dit à partir de quelle ligne servir le groupe demandé : c'est le
    « Charger plus » d'un gros groupe (voir TAILLE_LOT_GROUPE). Il vient de
    l'URL, donc de n'importe où : tout ce qui n'est pas un rang positif vaut
    zéro, et on repart du début plutôt que de refuser la page.

    Retourne (arbre, page_de_groupes, nombre_total_de_groupes).
    """
    try:
        decalage = max(0, int(decalage or 0))
    except (TypeError, ValueError):
        decalage = 0
    arbre, page, nombre, totaux_page, brutes_chemin, brutes = _page_de_groupes(
        qs_filtre, dims, numero_page, groupes_par_page)
    if chemin_demande == TOUS_LES_GROUPES:
        retenus = set(page.object_list)
        arbre = _arbre(totaux_page,
                       _lignes_des_groupes(qs_filtre, dims, brutes, retenus),
                       dims, retenus)
    elif chemin_demande:
        noeud = _noeud_par_chemin(arbre, chemin_demande)
        # Un nœud qui a des enfants n'a pas de lignes à lui : ses sous-groupes
        # sont déjà dans la page, et ce sont eux qui en demanderont.
        if noeud is not None and not noeud['enfants']:
            _poser_lot(noeud, _lignes_du_groupe(
                qs_filtre, dims, brutes_chemin, noeud['cle'], decalage), decalage)

    # En dernier : l'arbre a pu être rebâti juste au-dessus par le
    # préchargement, et les marques posées avant auraient été perdues.
    _ouvrir(arbre, chemins_ouverts(ouverts, numero_page),
            lambda n: _poser_lot(n, _lignes_du_groupe(
                qs_filtre, dims, brutes_chemin, n['cle'])))
    return arbre, page, nombre


def chemins_ouverts(valeur, numero_page):
    """Les chemins à déplier, s'ils concernent bien la page affichée.

    `valeur` est ce que porte `PARAM_OUVERTS` : « 2:0,1-3 ». Le numéro en tête
    dit de quelle page ces chemins parlent. Il ne s'agit pas de prudence
    gratuite : un chemin est positionnel, « 0 » désigne le premier groupe de la
    page affichée. Les liens de pagination recopient les paramètres courants,
    donc sans cette vérification, passer à la page suivante aurait déplié un
    groupe sans rapport — et rien ne l'aurait signalé.
    """
    if not valeur:
        return ()
    page, _, chemins = str(valeur).partition(':')
    if not chemins:
        return ()
    if (page or '1') != (str(numero_page) if numero_page else '1'):
        return ()
    return tuple(c for c in chemins.split(',') if c)


def _ouvrir(arbre, chemins, charger_lignes):
    """Marque les groupes dépliés et leur donne leur premier lot de lignes.

    `charger_lignes` reçoit le nœud et s'occupe d'y ranger ce qu'il faut — le
    lot comme ce qu'il en reste (voir `_poser_lot`). Un groupe restauré ouvert
    revient donc sur son premier lot, avec son « Charger plus » s'il est gros :
    on ne retient pas jusqu'où on avait déroulé, seulement qu'il était ouvert.

    Les ancêtres s'ouvrent avec eux : la bande d'un sous-groupe est masquée tant
    que son parent est fermé, un chemin « 0-1 » déplié seul ne se verrait donc
    pas. Le navigateur les note déjà tous, mais le serveur ne doit pas dépendre
    de cette politesse.
    """
    for chemin in chemins:
        morceaux = chemin.split('-')
        for profondeur in range(1, len(morceaux) + 1):
            noeud = _noeud_par_chemin(arbre, '-'.join(morceaux[:profondeur]))
            if noeud is None:
                break
            noeud['ouvert'] = True
            for enfant in noeud['enfants']:
                enfant['visible'] = True
            # Un nœud à enfants n'a pas de lignes à lui, et celles d'un groupe
            # déjà servi par `_groupe` ou par le préchargement sont là.
            if not noeud['enfants'] and not noeud['lignes']:
                charger_lignes(noeud)


def _page_de_groupes(qs_filtre, dims, numero_page, groupes_par_page):
    """Le découpage en pages et l'arbre d'en-têtes, sans aucune ligne.

    Séparé du chargement des lignes parce que les deux n'ont rien à voir : ceci
    ne dépend que de l'agrégation, cela d'un chemin réclamé par le navigateur.
    La séparation rend aussi les en-têtes testables sans toucher aux lignes.

    Retourne (arbre, page, nombre_de_groupes, totaux,
    valeurs_brutes_par_chemin, valeurs_brutes_par_racine).
    """
    totaux, brutes, brutes_chemin = (
        _totaux_feuilles_sql(qs_filtre, dims)
        if all(d.agregeable for d in dims)
        else _totaux_feuilles_python(qs_filtre, dims))

    # Nombre de lignes de chaque groupe racine : l'agrégation l'a déjà compté au
    # niveau le plus fin, il n'y a qu'à replier les sous-groupes dessus.
    tailles = defaultdict(int)
    for chemin, n in totaux.items():
        tailles[chemin[0]] += n

    # Groupes racines dans l'ordre de l'agrégation, sans doublon.
    racines_libelles = list(dict.fromkeys(chemin[0] for chemin in totaux))
    page = _PaginateurDeGroupes(
        racines_libelles, tailles, groupes_par_page).get_page(numero_page)
    retenus = set(page.object_list)

    totaux_page = {c: n for c, n in totaux.items() if c[0] in retenus}
    arbre = _arbre(totaux_page, [], dims, retenus)
    return (arbre, page, len(racines_libelles), totaux_page, brutes_chemin,
            brutes)


def _noeud_par_chemin(noeuds, chemin):
    """Le nœud dont le chemin positionnel est donné ('0', '2-1'…), ou None."""
    for n in noeuds:
        if n['chemin'] == chemin:
            return n
        if chemin.startswith(n['chemin'] + '-'):
            trouve = _noeud_par_chemin(n['enfants'], chemin)
            if trouve is not None:
                return trouve
    return None


def _condition_du_chemin(dims, brutes_chemin, cle):
    """Condition retenant exactement les lignes d'un groupe feuille, ou None.

    None dès qu'une dimension ne sait pas se traduire en filtre (valeur dans un
    JSONField, appartenance multiple) : l'appelant retombe alors sur un tri en
    Python, plus lent mais exact.
    """
    par_niveau = brutes_chemin.get(cle)
    if par_niveau is None or not all(d.filtrable for d in dims):
        return None
    condition = Q()
    for dim, valeurs in zip(dims, par_niveau):
        condition &= dim.filtre(valeurs)
    return condition


def _lignes_des_groupes(qs_filtre, dims, brutes, retenus):
    """Les lignes de tous les groupes racines affichés, en une seule requête.

    Le dépliage groupe par groupe fait attendre à chaque ouverture, et refait
    l'agrégation complète pour n'en tirer que quelques lignes. Le navigateur
    demande donc tout d'un coup une fois la page à l'écran : il paie un
    aller-retour pendant qu'on lit les en-têtes, et chaque dépliage devient
    instantané ensuite.

    Une seule condition suffit : la page retient des groupes **racines
    entiers**, jamais une partie d'un groupe. Filtrer sur la première dimension
    ramène donc exactement les lignes de la page, et `_arbre` les range ensuite
    dans leurs feuilles.
    """
    racine = dims[0]
    annotations = {}
    for dim in dims:
        annotations.update(dim.annotate)
    base = qs_filtre.annotate(**annotations) if annotations else qs_filtre
    if not racine.filtrable:
        # La dimension ne s'exprime pas en base : `_arbre` fera le tri lui-même.
        return list(base)
    valeurs = set()
    for libelle in retenus:
        valeurs |= brutes.get(libelle, set())
    if not valeurs:
        return []
    return list(base.filter(racine.filtre(valeurs)))


def _lignes_du_groupe(qs_filtre, dims, brutes_chemin, cle, decalage=0,
                      limite=TAILLE_LOT_GROUPE):
    """Un lot des lignes d'un groupe feuille, désigné par son chemin en libellés.

    Le lot va de `decalage` à `decalage + limite` : voir TAILLE_LOT_GROUPE pour
    la raison de ce découpage. La tranche est posée sur le queryset, donc la base
    ne renvoie que ces lignes-là — sauf pour le repli en Python, où une dimension
    qui ne s'exprime pas en filtre oblige de toute façon à tout parcourir ; le
    plafond n'y protège que le rendu.
    """
    annotations = {}
    for dim in dims:
        annotations.update(dim.annotate)
    base = qs_filtre.annotate(**annotations) if annotations else qs_filtre

    condition = _condition_du_chemin(dims, brutes_chemin, cle)
    if condition is not None:
        return list(base.filter(condition)[decalage:decalage + limite])
    # Repli : la dimension ne s'exprime pas en base, on trie en Python.
    retenues = [o for o in qs_filtre if cle in _chemins(o, dims)]
    return retenues[decalage:decalage + limite]


def _poser_lot(noeud, lignes, decalage=0):
    """Range un lot dans son nœud et calcule ce qu'il reste à charger.

    Le compte ne vient pas des lignes mais de `total`, qui sort de l'agrégation :
    on sait donc ce qui manque sans l'avoir lu, et « Charger plus » peut annoncer
    combien de lignes il reste avant qu'on ait touché à la base.
    """
    noeud['lignes'] = lignes
    reste = max(0, noeud['total'] - decalage - len(lignes))
    noeud['suite'] = decalage + len(lignes) if reste and lignes else None
    noeud['reste'] = reste
    noeud['prochain'] = min(reste, TAILLE_LOT_GROUPE)


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
            # Chemin en libellés, celui de `totaux` : le chargement différé s'en
            # sert pour retrouver les lignes du groupe (`lignes_du_groupe`).
            'cle':      cle_complete,
            'niveau':   niveau,
            # Retrait calculé ici pour éviter toute arithmétique dans le gabarit.
            'indent':   14 + niveau * 20,
            'libelle':  libelle,
            'total':    sommes.get(cle_complete, 0),
            'sur_page': 0,
            'partiel':  False,
            # Rang du lot suivant, et ce qu'il restera après celui-ci : de quoi
            # écrire l'entrée « Charger plus ». `suite` est None quand le groupe
            # est entier — il n'y a alors rien à proposer.
            'suite':    None,
            'reste':    0,
            'prochain': 0,
            # Déplié dès le rendu : la page arrive ouverte, sans que rien n'ait
            # à la rouvrir après coup (voir `chemins_ouverts`).
            'ouvert':   False,
            # Une bande de sous-groupe ne se montre que si son parent est
            # déplié — c'est l'état du parent qui décide, jamais le sien.
            'visible':  niveau == 0,
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
            # Le préchargement passe par ici plutôt que par `_poser_lot` : il
            # range les lignes de tous les groupes d'un coup. Il les prend
            # entières, donc `suite` reste nul — mais on le calcule quand même,
            # pour que l'arbre dise la même chose par les deux chemins.
            if n['partiel'] and n['sur_page']:
                n['suite'] = n['sur_page']
                n['reste'] = n['total'] - n['sur_page']
                n['prochain'] = min(n['reste'], TAILLE_LOT_GROUPE)
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
    return lambda o: libelles.get(str(_attribut(o, chemin)), 'Indéfini') if _attribut(o, chemin) not in (None, '') else 'Indéfini'


def _label_choix(chemin, libelles):
    return lambda r: libelles.get(str(r[chemin]), 'Indéfini') if r[chemin] not in (None, '') else 'Indéfini'


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
            #
            # `order_by()` efface le tri par défaut du modèle, et ce n'est pas
            # un détail : toutes ces tables en ont un, si bien que prendre 201
            # lignes obligeait la base à trier la table entière d'abord. Sur un
            # millier de factures c'est invisible, sur cent mille beaucoup
            # moins — et ce tri ne servait à rien, puisqu'on ne cherche ici
            # qu'à savoir si la table est petite et, si oui, ce qu'elle
            # contient.
            objets = list(modele.objects.all().order_by()[:MAX_CHOIX_LIEN + 1])
            if len(objets) <= MAX_CHOIX_LIEN:
                # Rangés par libellé : on vient y choisir une valeur, et une
                # liste alphabétique se parcourt mieux que l'ordre où la base
                # les a rendus.
                choix = sorted(((str(o.pk), str(o)) for o in objets),
                               key=lambda c: _sans_accent(c[1]))
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
