"""Règles métier des soins, partagées entre la vue, les filtres et les pastilles.

Un même critère est lu à trois endroits : la vue qui autorise le geste, le
filtre de la liste, et le compteur de la carte d'accueil. Le recopier trois fois
garantit qu'ils finiront par diverger — et une pastille qui annonce 7 soins pour
une liste qui en montre 5 n'est plus jamais regardée. Ils lisent donc tous ici.
"""

from django.db.models import Q


def condition_administrable():
    """Soins qu'un soignant peut effectivement administrer.

    Reprend la règle de `soins.views.soins_administrer` : le paiement doit être
    réglé. Un soin rattaché à une hospitalisation en dépend par un service à
    facturer payé, les autres par leur propre facture.

    La branche « hospitalisation » passe par une sous-requête plutôt que par une
    jointure : traverser une relation multiple dupliquerait la ligne autant de
    fois que le dossier a de services payés, et la brique de listing ne pose pas
    de `distinct()`.
    """
    from hospitalisation.models import ServiceAFacturer

    dossiers_regles = (ServiceAFacturer.objects
                       .filter(source__in=['soin', 'manuel'], facture__statut='payee')
                       .values('hospitalisation_id'))
    return (
        Q(statut='en_cours')
        & (Q(hospitalisation__isnull=True, facture__statut='payee')
           | Q(hospitalisation_id__in=dossiers_regles))
    )


def condition_a_facturer():
    """Soins dont la facture reste à créer — le geste de la caisse."""
    return Q(statut='en_attente_de_paiement', facture__isnull=True)


def demarrer_soin_de_facture(facture):
    """Une facture réglée met en cours le soin qu'elle couvre, et ses procédures.

    Point de passage unique, parce qu'une facture peut devenir « payée » par
    plusieurs chemins : l'encaissement de la caisse, le bouton « Marquer comme
    payée » de la fiche, et la création d'une facture déjà réglée. Seul le
    premier démarrait le soin ; par les autres il restait « en attente de
    paiement » alors que le patient avait payé.

    Renvoie le soin démarré, ou None s'il n'y avait rien à faire.
    """
    from soins.models import Soin

    if facture is None or facture.statut != 'payee':
        return None
    # all_objects : le geste suit la facture, pas le centre actif.
    soin = Soin.all_objects.filter(facture=facture).first()
    if soin is None or soin.statut in ('en_cours', 'termine', 'annule'):
        return None
    soin.statut = 'en_cours'
    soin.save(update_fields=['statut'])
    soin.demarrer_procedures()
    return soin
