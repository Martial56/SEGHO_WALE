"""Le cloisonnement du menu Doublons : le centre actif, et lui seul.

Un écran qui rapproche deux fiches les met côte à côte en entier — nom,
naissance, téléphone, assurance. Il n'y a donc pas de petit débordement
possible ici : une seule page vue de travers, et c'est un dossier complet qui
a changé de centre.

D'où la règle, sans exception : ce qui se lit et ce qui se modifie dans ce
menu appartient au centre actif de la requête. Pas de repli sur « le centre
de la première paire venue » — c'est ce repli qui ouvrait Yamoussoukro à
quelqu'un de Toumbokro, au seul motif qu'il n'avait rien choisi. Sans centre
actif, l'écran ne montre rien et le dit. Un super-utilisateur ne fait pas
exception : il choisit son centre comme tout le monde.

La clé d'un groupe (« 12-34 ») voyage dans l'adresse. Elle ne prouve rien :
elle se tape à la main. C'est pourquoi `fiches_du_groupe()`
recharge toujours ses fiches à travers `fiches_du_centre()`, et refuse le lot entier dès qu'une seule
manque — un groupe à moitié d'un autre centre ne se montre pas à moitié.
"""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import render

from .doublons_groupes import membres_depuis_cle
from .models import Patient

#: Ce que l'écran affiche à la place du relevé, et ce que l'API renvoie.
CHOISIR = 'Choisissez un centre.'


def centre_actif(request):
    """Le centre de la requête, ou None — sans aucun repli."""
    return getattr(request, 'centre', None)


def id_du_centre(request):
    centre = centre_actif(request)
    return centre.pk if centre is not None else None


def exige_un_centre(vue):
    """Interdit la vue tant qu'aucun centre n'est actif.

    À poser après `permission_required` : on dit d'abord qu'on n'a pas le
    droit, ensuite qu'il manque un centre.
    """
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if centre_actif(request) is not None:
            return vue(request, *args, **kwargs)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'message': CHOISIR}, status=409)
        if request.method != 'GET':
            # Rien à montrer, rien à écrire : une requête forgée s'arrête ici
            # au lieu de retomber sur le centre de quelqu'un d'autre.
            raise PermissionDenied(CHOISIR)
        return render(request, 'patients/doublons/sans_centre.html',
                      {'titre': 'Doublons', 'message': CHOISIR})
    return enveloppe


def fiches_du_centre(request):
    """Les fiches que ce menu a le droit de lire.

    `all_objects` parce que les masquées et les fusionnées se traitent
    justement ici ; filtrées par centre parce que rien d'autre ne les filtre.
    """
    return Patient.all_objects.filter(centre=centre_actif(request))


def fiche_du_centre(request, pk, **filtres):
    """Une fiche du centre actif, ou 404 — même par son adresse directe.

    Un identifiant qui n'en est pas un (champ de formulaire vide, adresse
    bricolée) vaut une fiche introuvable, pas une erreur serveur.
    """
    try:
        trouvee = fiches_du_centre(request).filter(pk=pk, **filtres).first()
    except (TypeError, ValueError):
        trouvee = None
    if trouvee is None:
        raise Http404("Cette fiche n'existe pas ici.")
    return trouvee


def fiches_du_groupe(request, cle, queryset=None):
    """Les fiches d'une clé de groupe, dans l'ordre de la clé.

    Toutes du centre actif, toutes présentes : il en manque une et la clé est
    refusée en entier. Deux au minimum — en dessous, il n'y a plus de groupe.
    """
    membres = membres_depuis_cle(cle)
    source = fiches_du_centre(request) if queryset is None else queryset
    trouvees = list(source.filter(pk__in=membres))
    if len(trouvees) < 2 or len(trouvees) != len(membres):
        raise Http404("Ce groupe n'existe plus.")
    trouvees.sort(key=lambda p: membres.index(p.pk))
    return trouvees
