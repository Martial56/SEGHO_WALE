"""Compteurs « tu as quelque chose à faire ici » des cartes de la page d'accueil.

Une pastille n'est pas une statistique : elle annonce un **travail en attente
pour la personne qui regarde**. D'où deux règles qui gouvernent tout ce module :

* elle est conditionnée à la **permission** qui autorise le geste, jamais à un
  nom de groupe — un groupe se renomme (« Caissier » l'a été), une permission
  non ;
* elle mène à la **liste déjà filtrée** sur ce qu'elle a compté. Une pastille
  qui annonce 7 et ouvre une liste où il faut les chercher ne sera plus jamais
  regardée.

Les compteurs sont cloisonnés par centre sans effort : les modèles interrogés
sont des ModeleCentre, leur manager filtre déjà sur le centre actif.
"""

from django.db.models import Q
from django.urls import reverse


def pastilles(user):
    """Compteurs par code de module, pour l'utilisateur donné.

    Retourne `{code_module: {'total': int, 'url': str, 'libelle': str}}`, en
    n'incluant que les modules où quelque chose attend réellement. Une carte
    sans entrée reste muette — c'est le silence qui donne son sens au chiffre.
    """
    if not (user and user.is_authenticated):
        return {}

    resultat = {}
    for code, calcul in (('consultations', _soins),
                         ('hospitalisation', _hospitalisation),
                         ('facturation', _facturation)):
        entree = calcul(user)
        if entree and entree['total']:
            resultat[code] = entree
    return resultat


def compteurs(user):
    """Vue réduite `{code_module: total}`, pour le rafraîchissement AJAX.

    Les URL ne changent pas d'un rafraîchissement à l'autre : inutile de les
    renvoyer toutes les 30 secondes.
    """
    return {code: e['total'] for code, e in pastilles(user).items()}


# ── Un calcul par carte ─────────────────────────────────────────────────────

def _soins(user):
    """Soins à facturer (caisse) et soins prêts à administrer (soignants).

    Les deux se cumulent pour qui a les deux droits : la carte répond à « ai-je
    du travail ici ? », pas à « lequel ».
    """
    from soins.models import Soin
    from soins.regles import condition_a_facturer, condition_administrable

    conditions, filtres, libelles = [], [], []
    if user.has_perm('soins.can_creer_facture'):
        conditions.append(condition_a_facturer())
        filtres.append('a_facturer')
        libelles.append('à facturer')
    if user.has_perm('soins.can_administrer_soin'):
        conditions.append(condition_administrable())
        filtres.append('a_administrer')
        libelles.append('à administrer')
    if not conditions:
        return None

    combine = conditions[0]
    for c in conditions[1:]:
        combine |= c
    total = Soin.objects.filter(combine).count()
    return {
        'total': total,
        'url': reverse('soins:list') + '?' + '&'.join(f'filter={f}' for f in filtres),
        'libelle': ' et '.join(libelles),
    }


def _hospitalisation(user):
    """Dossiers à installer (soignants) et services à facturer (caisse)."""
    from hospitalisation.models import Hospitalisation
    from hospitalisation.hospitalisation_listing import _condition_a_facturer

    conditions, filtres, libelles = [], [], []
    if user.has_perm('hospitalisation.can_installer_patient'):
        conditions.append(Q(statut='confirme'))
        filtres.append('a_installer')
        libelles.append('à installer')
    if user.has_perm('hospitalisation.can_creer_facture'):
        conditions.append(_condition_a_facturer())
        filtres.append('a_facturer')
        libelles.append('à facturer')
    if not conditions:
        return None

    combine = conditions[0]
    for c in conditions[1:]:
        combine |= c
    total = Hospitalisation.objects.filter(combine).count()
    return {
        'total': total,
        # `filter=` vide en tête : sans lui la vue réapplique sa période par
        # défaut (la journée) et la liste serait plus courte que la pastille.
        'url': (reverse('hospitalisation:list') + '?filter=&'
                + '&'.join(f'filter={f}' for f in filtres)),
        'libelle': ' et '.join(libelles),
    }


def _facturation(user):
    """Factures émises non réglées : des patients qui attendent de payer.

    Le droit de lecture suffit — encaisser passe ensuite par
    `can_manage_paiement`, mais voir qu'il y a la queue n'a pas à être plus
    restreint que la liste elle-même.
    """
    from facturation.models import Facture

    if not user.has_perm('facturation.view_facture'):
        return None
    total = Facture.objects.filter(statut='emise').count()
    return {
        'total': total,
        # `date_from=` vide : la liste se limite sinon aux factures du jour.
        'url': reverse('facturation:list') + '?filter=statut:emise&date_from=',
        'libelle': 'à encaisser',
    }
