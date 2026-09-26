"""Revenir d'où l'on vient, sans perdre ce qu'on avait commencé à saisir.

Depuis une fiche de rendez-vous, le médecin part créer une demande de labo, un
soin, une ordonnance ou une M.O. Les liens étaient de simples `<a href>` posés
dans le formulaire : le navigateur quittait la page et les 376 champs saisis
disparaissaient, sans un mot.

Le trajet se fait donc en trois temps :

1. le bouton **soumet** la fiche, qui est enregistrée pour de bon ;
2. la vue redirige vers la destination en lui passant `?next=`, l'adresse de
   retour, onglet compris ;
3. la destination, une fois son propre enregistrement fait, y revient.

Une adresse de retour vient du navigateur : on la valide avant de s'y fier,
sinon un lien fabriqué ailleurs renverrait l'utilisateur sur un autre site en
lui faisant croire qu'il est toujours chez lui.
"""
from urllib.parse import urlencode

from django.utils.http import url_has_allowed_host_and_scheme


def url_interne(request, candidate):
    """L'adresse si elle mène bien à ce site, sinon None."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None


def retour_ou(request, defaut):
    """L'adresse de retour demandée, ou `defaut` s'il n'y en a pas de valable.

    Cherche d'abord dans le POST — le formulaire la reconduit dans un champ
    caché pour qu'elle survive à un rechargement après erreur — puis dans
    l'URL.
    """
    return (url_interne(request, request.POST.get('next'))
            or url_interne(request, request.GET.get('next'))
            or defaut)


def vers_avec_retour(destination, retour):
    """`destination` à laquelle on accroche `retour` sous la clé `next`.

    La destination porte déjà ses propres paramètres (le patient, le médecin) :
    on ajoute le nôtre sans écraser les leurs.
    """
    separateur = '&' if '?' in destination else '?'
    return f'{destination}{separateur}{urlencode({"next": retour})}'


#: Onglets de la fiche de rendez-vous, tels que les portent les `data-tab` des
#: deux gabarits. La liste sert de filtre : l'onglet demandé vient du
#: navigateur, et on ne recopie pas tel quel dans une URL ce qu'il nous donne.
ONGLETS_RDV = ('infos', 'clinique', 'cpn', 'accouchement',
               'postnatale', 'curative', 'autres')


def retour_vers_le_rdv(request, chemin):
    """`chemin`, avec l'onglet ouvert au moment du clic."""
    onglet = request.POST.get('_onglet', '')
    if onglet not in ONGLETS_RDV:
        return chemin
    return f'{chemin}?{urlencode({"onglet": onglet})}'


def detour_demande(request, chemin_du_rdv):
    """L'action annexe demandée avant de revenir, ou None si on reste ici.

    Le bouton « Demande de lab » soumet la fiche et donne sa destination dans
    `_apres` : la saisie est enregistrée d'abord, on part ensuite.
    """
    destination = url_interne(request, request.POST.get('_apres'))
    if not destination:
        return None
    return vers_avec_retour(destination, retour_vers_le_rdv(request, chemin_du_rdv))
