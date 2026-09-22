"""Où mène la ligne d'un rendez-vous.

Un rendez-vous de gynécologie et un rendez-vous de médecine générale ne
s'ouvrent pas sur la même page : le premier a des registres — prénatal,
accouchement, postnatal — que le formulaire du module Rendez-vous n'affiche
pas. Mais tout le monde ne travaille pas en gynécologie, et envoyer un médecin
généraliste dans un module qui n'est pas le sien serait aussi gênant que de
priver la sage-femme de ses registres.

La destination croise donc les deux : le département du rendez-vous **et**
l'accès de la personne au module Gynécologie.

    rendez-vous GYN  + accès gynéco  → la fiche du module Gynécologie
    rendez-vous GYN  sans accès      → la fiche du module Rendez-vous
    tout autre département           → la fiche du module Rendez-vous

Écrit ici plutôt que dans un gabarit : les lignes de rendez-vous sont rendues à
plusieurs endroits, et la règle recopiée finirait par diverger.

Ce n'est pas un contrôle d'accès — celui-ci est posé par `module_requis` sur les
vues du module Gynécologie. C'est l'aiguillage qui évite d'y envoyer quelqu'un
pour rien.
"""

from django.urls import reverse

from modules_permissions.decorateurs import utilisateur_a_module

#: Département dont les rendez-vous relèvent du module Gynécologie.
DEPARTEMENT_GYNECO = 'GYN'


def url_fiche_rdv(user, rdv, suffixe=''):
    """L'adresse de la fiche de ce rendez-vous pour cet utilisateur.

    `suffixe` reçoit le paramètre de provenance (`?origine=…`) pour que le
    retour ramène là où l'on était, quel que soit le module d'arrivée.
    """
    departement = getattr(rdv, 'departement', None)
    est_gyneco = departement is not None and departement.code == DEPARTEMENT_GYNECO

    if est_gyneco and utilisateur_a_module(user, 'gynecologie'):
        base = reverse('gynecologie_rdv_detail', args=[rdv.pk])
    else:
        base = reverse('patients:rdv_edit', args=[rdv.pk])
    return base + suffixe
