"""Retenir la sélection d'une liste le temps qu'on aille voir une fiche.

On filtre une liste de rendez-vous sur la journée, on ouvre l'un d'eux, on
revient : la liste était de nouveau entière. Tout le travail de tri était à
refaire, et plus la sélection avait demandé de clics, plus la perte était
agaçante.

La sélection vit dans l'URL (`?filter=…&group=…&q=…`). Il suffit donc de la
remettre dans l'URL quand on revient sans elle — et non d'inventer un état
caché : l'adresse affichée reste celle de ce qu'on voit, la page se recharge,
se met en favori et revient par le bouton Précédent sans surprise.

Quatre façons de l'oublier, et seulement quatre :

* le bouton « Effacer », qui rafraîchit la liste sans aucun paramètre ;
* une nouvelle sélection, qui écrase la précédente ;
* le retour à l'accueil, qui vide toutes les listes d'un coup ;
* sortir du module, qui emporte les sélections des listes qu'on y laisse.

La dernière est la plus large, et les deux premières restent utiles à
l'intérieur d'un module. Retenir une sélection sert le temps d'un aller-retour —
ouvrir une fiche, passer d'une liste sœur à l'autre — et cesse de servir dès
qu'on travaille ailleurs : retrouver la facturation filtrée sur un mois choisi
la veille, en venant de l'hospitalisation, ne rend service à personne. Le retour
à l'accueil en est le cas particulier, l'accueil ne relevant d'aucun module.

La distinction entre « j'efface » et « je reviens d'une fiche » tient à la
nature de la requête. « Effacer » rafraîchit la liste **en AJAX**, sans quitter
la page ; revenir d'une fiche est un **chargement complet**. Le premier oublie,
le second restaure.

Une sélection se pose en rechargeant la liste, et la mémoire n'a donc qu'à lire
l'URL qu'on lui demande. L'état déplié, lui, ne recharge rien : déplier un
groupe se fait dans la page, et l'adresse n'est réécrite que pour le navigateur
(`history.replaceState`). Il n'arrivait jamais jusqu'ici — revenir d'une fiche
par le bouton « Retour » ramenait bien le filtre et le regroupement, mais la
liste repliée. D'où `PARAM_MEMO` : une requête de fond, que le navigateur envoie
à chaque dépliage et qui ne sert qu'à faire retenir.
"""
from urllib.parse import urlencode

from django.http import HttpResponse
from django.shortcuts import redirect

# Importé plutôt que recopié : c'est la brique des listes qui définit ce nom.
from core.listing import PARAM_GROUPE

#: Paramètres qui composent une sélection. `page` en est volontairement absent :
#: revenir sur une fiche puis retrouver sa liste à la page 7 surprendrait plus
#: que de repartir du début.
#:
#: `cf`, `co`, `cv` et `cm` sont les conditions personnalisées — champ,
#: opérateur, valeur, et le mode qui les combine. Elles manquaient : la liste
#: retenait `cond_…` et `mode_cond`, deux noms que rien n'a jamais écrits.
#: Poser un filtre personnalisé, ouvrir une fiche et revenir le faisait donc
#: disparaître sans un mot, sur les six listes qui offrent la fonction.
PARAMETRES = ('filter', 'group', 'q', 'date_from', 'date_to',
              'tri', 'sens', 'cf', 'co', 'cv', 'cm', 'ouverts')

#: Préfixe des clés de session, pour pouvoir toutes les retirer d'un coup.
PREFIXE_CLE = 'listing:'

#: Marque une requête qui ne vient que faire retenir la sélection : elle porte
#: l'URL de la liste telle qu'elle est à l'écran et n'attend aucune page en
#: retour. C'est ainsi que l'état déplié rejoint la mémoire sans rien recharger
#: (voir la docstring du module, et `noterOuverts` dans listing_groupes.js).
PARAM_MEMO = '_memo'


def _est_parametre(cle):
    return cle in PARAMETRES


def _selection(request):
    """Les paramètres de sélection de cette URL, en paires (clé, valeur).

    Des paires et non un dictionnaire : `filter` et `group` se répètent, et un
    dictionnaire n'en garderait qu'une valeur.
    """
    return [(cle, valeur)
            for cle in request.GET
            if _est_parametre(cle)
            for valeur in request.GET.getlist(cle)]


def _cle(request):
    """Une mémoire par liste : le chemin les distingue.

    Les trois listes de rendez-vous partagent la même vue mais pas la même
    adresse ; chacune garde donc sa propre sélection.
    """
    return PREFIXE_CLE + request.path


def _est_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def selection_memorisee(request):
    """À appeler en tête d'une vue de liste.

    Rend une réponse que la vue n'a qu'à retourner — la redirection qui remet la
    sélection retenue dans l'URL, ou le 204 d'une requête de mémorisation — et
    None dans tous les autres cas, où la vue poursuit normalement.
    """
    # Déplier un groupe redemande la page avec `_groupe` : ce n'est ni une
    # sélection ni un effacement, et il ne doit donc ni être retenu ni effacer
    # ce qui l'est. Sans ce garde-fou, ouvrir un groupe sur une liste filtrée
    # perdrait le filtre retenu.
    if PARAM_GROUPE in request.GET:
        return None

    cle = _cle(request)
    selection = _selection(request)

    # Requête de mémorisation : on retient, et c'est tout. Pas de page à rendre,
    # et surtout rien à oublier — sans ce retour anticipé, une liste dépliée
    # alors qu'aucun critère n'est posé passerait plus bas pour un « Effacer »,
    # que personne n'a demandé.
    if PARAM_MEMO in request.GET:
        if selection:
            request.session[cle] = selection
        return HttpResponse(status=204)

    if selection:
        request.session[cle] = selection
        return None

    if _est_ajax(request):
        # Aucun paramètre et pas de rechargement : c'est « Effacer ».
        request.session.pop(cle, None)
        return None

    retenue = request.session.get(cle)
    if not retenue:
        return None
    # `retenue` revient de la session sous forme de listes, pas de tuples.
    return redirect(f'{request.path}?{urlencode([tuple(p) for p in retenue])}')


def _module(chemin):
    """Module dont relève une adresse : son premier segment.

    « /patients/ », « /patients/rendez-vous/ » et « /patients/252/ » relèvent du
    même module — c'est ce qui laisse une sélection survivre à l'ouverture d'une
    fiche et au passage d'une liste à sa voisine. « / », le tableau de bord, n'en
    relève d'aucun.

    Le premier segment et non le namespace de l'URL : les clés en mémoire sont
    des chemins, pas des requêtes, et il faut mesurer les deux côtés avec la même
    règle. Chaque module de ce projet préfixe ses routes par son propre nom.
    """
    segments = [s for s in chemin.split('/') if s]
    return segments[0] if segments else ''


def _cles_retenues(session):
    """Clés de sélection présentes en session.

    `.keys()` et non la session elle-même : `SessionBase` expose `__getitem__`
    sans être itérable, et Python retomberait sur l'indexation par entiers. La
    liste est matérialisée avant toute suppression — on ne retire pas d'un
    dictionnaire qu'on parcourt.
    """
    return [c for c in session.keys() if c.startswith(PREFIXE_CLE)]


def oublier_tout(request):
    """Vide la mémoire de toutes les listes. Appelée depuis l'accueil."""
    for cle in _cles_retenues(request.session):
        del request.session[cle]


def oublier_les_autres_modules(request):
    """Oublie les listes qui ne relèvent pas du module de la page demandée.

    Appelée à chaque navigation par core.middleware.MemoireListingMiddleware, et
    non depuis les vues de liste : une sélection doit tomber quand on ouvre une
    page d'un autre module, c'est-à-dire précisément là où aucune vue de liste ne
    s'exécute.
    """
    courant = _module(request.path)
    for cle in _cles_retenues(request.session):
        if _module(cle[len(PREFIXE_CLE):]) != courant:
            del request.session[cle]
