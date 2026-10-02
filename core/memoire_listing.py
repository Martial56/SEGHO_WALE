"""Retenir la sélection d'une liste le temps qu'on aille voir une fiche.

On filtre une liste de rendez-vous sur la journée, on ouvre l'un d'eux, on
revient : la liste était de nouveau entière. Tout le travail de tri était à
refaire, et plus la sélection avait demandé de clics, plus la perte était
agaçante.

La sélection vit dans l'URL (`?filter=…&group=…&q=…`). Il suffit donc de la
remettre dans l'URL quand on revient sans elle — et non d'inventer un état
caché : l'adresse affichée reste celle de ce qu'on voit, la page se recharge,
se met en favori et revient par le bouton Précédent sans surprise.

Trois façons de l'oublier, et seulement trois :

* le bouton « Effacer », qui rafraîchit la liste sans aucun paramètre ;
* une nouvelle sélection, qui écrase la précédente ;
* le retour à l'accueil, qui vide toutes les listes d'un coup.

La distinction entre « j'efface » et « je reviens d'une fiche » tient à la
nature de la requête. « Effacer » rafraîchit la liste **en AJAX**, sans quitter
la page ; revenir d'une fiche est un **chargement complet**. Le premier oublie,
le second restaure.
"""
from urllib.parse import urlencode

from django.shortcuts import redirect

#: Paramètres qui composent une sélection. `page` en est volontairement absent :
#: revenir sur une fiche puis retrouver sa liste à la page 7 surprendrait plus
#: que de repartir du début.
PARAMETRES = ('filter', 'group', 'q', 'date_from', 'date_to',
              'tri', 'sens', 'mode_cond')

#: Les conditions personnalisées sont nommées dynamiquement (`cond_champ_0`…).
PREFIXE_CONDITION = 'cond_'

#: Préfixe des clés de session, pour pouvoir toutes les retirer d'un coup.
PREFIXE_CLE = 'listing:'


def _est_parametre(cle):
    return cle in PARAMETRES or cle.startswith(PREFIXE_CONDITION)


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

    Rend une redirection quand la sélection retenue doit être remise dans
    l'URL — la vue n'a alors qu'à la retourner — et None dans tous les autres
    cas, où elle poursuit normalement.
    """
    cle = _cle(request)
    selection = _selection(request)

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


def oublier_tout(request):
    """Vide la mémoire de toutes les listes. Appelée depuis l'accueil."""
    # `.keys()` et non la session elle-même : `SessionBase` expose `__getitem__`
    # sans être itérable, et Python retomberait sur l'indexation par entiers.
    for cle in [c for c in request.session.keys() if c.startswith(PREFIXE_CLE)]:
        del request.session[cle]
