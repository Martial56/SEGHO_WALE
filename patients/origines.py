"""Contexte de retour d'une fiche patient ouverte depuis un autre module.

La fiche patient appartient au module Patients, mais on y entre aussi depuis la
liste d'un autre module — « Les patients » de la gynécologie aujourd'hui,
l'hospitalisation ou le laboratoire demain. Sans indication de provenance, la
fiche renvoie vers la liste des patients et affiche le menu Patients :
l'utilisatrice sort du module où elle travaillait sans l'avoir demandé, et se
retrouve devant une barre de navigation qui n'est pas la sienne.

Le paramètre d'URL `?origine=` porte cette provenance. Ce n'est **pas** un
contrôle d'accès — il suffit de le retirer de l'URL —, c'est le fil qui permet
de revenir d'où l'on vient. Le verrouillage, lui, est assuré par les
permissions Django sur les vues d'écriture (voir patients.views).

Pour brancher un nouveau module, ajouter une entrée ici : rien d'autre à
toucher.
"""


def _cohorte_gynecologie(qs):
    """Les patientes suivies en gynécologie — même jeu que core.views.gynecologie_list."""
    from patients.models import RendezVous
    return qs.filter(
        pk__in=RendezVous.objects.filter(departement__code='GYN').values('patient')
    )


#: code d'origine → où revenir, comment s'appeler, quel menu afficher.
#:
#: * ``url``      : nom d'URL de la liste d'où l'on vient ;
#: * ``libelle``  : ce qu'affiche le fil d'Ariane à la place de « Patients » ;
#: * ``nav``      : la barre de navigation à substituer à celle des patients ;
#: * ``cohorte``  : restreint les flèches ‹ › à la liste d'origine, pour qu'on
#:                  ne déroule pas tout le fichier patients depuis un module
#:                  qui n'en montre qu'une partie.
ORIGINES = {
    'gynecologie': {
        'url':     'gynecologie_list',
        'libelle': 'Gynécologie',
        'nav':     'gynecologie/includes/nav.html',
        'cohorte': _cohorte_gynecologie,
    },
}


def contexte(request):
    """Le contexte de retour d'une requête, prêt à être versé dans un template.

    `origine` décrit d'où l'on vient (None si on vient du module Patients), et
    `origine_qs` est le suffixe à coller aux liens internes — fiche, onglets,
    flèches — pour que la provenance survive à toute la navigation autour du
    patient, et pas seulement au premier écran.
    """
    code = (request.GET.get('origine') or '').strip()
    origine = resoudre(code)
    return {
        'origine': origine,
        'origine_qs': '?origine=%s' % code if origine else '',
    }


def resoudre(code):
    """Retourne le contexte de l'origine demandée, ou None si elle est inconnue.

    Le code venant de l'URL, il est traité comme une donnée quelconque : une
    valeur inattendue ramène simplement à la navigation par défaut.
    """
    return ORIGINES.get((code or '').strip())
