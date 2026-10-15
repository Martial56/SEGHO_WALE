"""Règles métier des soins, partagées entre la vue, les filtres et les pastilles.

Un même critère est lu à trois endroits : la vue qui autorise le geste, le
filtre de la liste, et le compteur de la carte d'accueil. Le recopier trois fois
garantit qu'ils finiront par diverger — et une pastille qui annonce 7 soins pour
une liste qui en montre 5 n'est plus jamais regardée. Ils lisent donc tous ici.
"""

from django.db.models import Q
from django.utils import timezone


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


def cloturer_selon_procedures(soin, user=None):
    """Un soin dont plus aucune ligne n'attend se conclut de lui-même.

    Le miroir de `soins_administrer`, qui fait déjà descendre « terminé » du
    soin vers ses procédures. Dans l'autre sens rien ne remontait : un dossier
    de dix lignes toutes terminées restait « en cours » indéfiniment, à moins
    que quelqu'un ne reclique « Administrer » sur le soin — ce qui refermait
    d'un bloc y compris les lignes qui ne l'étaient pas.

    Deux issues, selon ce qui reste une fois le travail fini : au moins une
    ligne terminée conclut le soin à « Terminé », les annulées ne comptant pas ;
    tout annulé l'annule, puisqu'il ne reste alors rien qui ait été fait.

    Les deux issues ne s'ouvrent pas aux mêmes moments. « Terminé » suppose un
    soin payé, donc « en cours » : rien n'est dû au patient qui n'a pas réglé.
    « Annulé » vaut aussi avant le règlement — un dossier dont toutes les lignes
    sont annulées avant d'être payé n'a plus de raison d'attendre sa facture.

    Renvoie le soin conclu, ou None s'il n'y avait rien à faire.
    """
    from core.views import log_event
    from soins.models import ProcedureSoin

    if soin is None or soin.statut not in ('en_cours', 'en_attente_de_paiement', 'brouillon'):
        return None
    # Un dossier d'hospitalisation reçoit ses procédures visite après visite
    # (hospitalisation.views._sync_procedure_soin). Le fermer parce que les
    # premières sont faites gèlerait un séjour encore en cours, et la visite du
    # lendemain viendrait se greffer sur un soin déjà « terminé ».
    if soin.hospitalisation_id:
        return None

    # all_objects : le décompte est borné par le soin, qui porte déjà son
    # centre — voir Soin.demarrer_procedures.
    statuts = set(ProcedureSoin.all_objects.filter(soin=soin)
                  .values_list('statut', flat=True))
    # Un dossier vide n'a rien conclu du tout : ni terminé, ni annulé. Il ne
    # devrait pas exister — un soin se crée avec ses lignes — mais le rencontrer
    # ici ne doit rien déclencher.
    if not statuts:
        return None
    # Il reste du travail : on ne conclut pas.
    if statuts & {'brouillon', 'en_cours'}:
        return None

    if 'termine' in statuts:
        # Une ligne terminée sur un soin non réglé ne le termine pas : le geste
        # a eu lieu, l'encaissement non. Le dossier attend toujours sa caisse.
        if soin.statut != 'en_cours':
            return None
        soin.statut = 'termine'
        soin.termine_par = user if user is not None and user.is_authenticated else None
        soin.date_termine = timezone.now()
        soin.save(update_fields=['statut', 'termine_par', 'date_termine'])
        log_event(soin, user, 'Toutes les lignes terminées — statut : Terminé.', type='statut')
        return soin

    # Plus rien en attente et pas une seule ligne terminée : tout a été annulé.
    return annuler_soin(soin, user,
                        message='Toutes les lignes annulées — statut : Annulé.')


def annuler_soin(soin, user=None, motif='', message='Soin annulé.'):
    """Annule un soin, ses lignes encore ouvertes et sa facturation.

    Point de passage unique des deux chemins qui annulent un dossier : le bouton
    de la fiche (`soins.views.soins_annuler`) et la dernière ligne annulée
    (`cloturer_selon_procedures`). Chacun posait son statut dans son coin, et
    aucun des deux ne touchait aux factures — un soin annulé laissait donc
    derrière lui de quoi encaisser un geste qui n'aurait pas lieu.

    Un soin annulé n'est pas un soin terminé : il ne porte ni `termine_par` ni
    `date_termine`.

    all_objects : le geste suit le soin, qui porte déjà son centre — voir
    `Soin.demarrer_procedures`.

    Renvoie le soin annulé.
    """
    from core.views import log_event
    from soins.models import ProcedureSoin

    soin.statut = 'annule'
    soin.modifie_par = user if user is not None and user.is_authenticated else None
    soin.date_modification = timezone.now()
    soin.save(update_fields=['statut', 'modifie_par', 'date_modification'])
    log_event(soin, user, message, type='statut')
    ProcedureSoin.all_objects.filter(soin=soin).exclude(
        statut__in=('termine', 'annule')).update(statut='annule')
    annuler_facturation_du_soin(soin, user, motif)
    return soin


def annuler_facturation_du_soin(soin, user=None, motif=''):
    """Annule les factures d'un soin annulé : la sienne et celles de ses lignes.

    Le geste de `patients.views.rdv_edit` sur un rendez-vous annulé, porté aux
    soins : la facture suit le dossier qui l'a fait naître, sinon elle reste à
    encaisser pour un acte qui n'aura pas lieu.

    Deux porteurs plutôt qu'un. Le soin a sa facture, et chaque procédure peut
    avoir la sienne (`soins.views._auto_creer_facture`, pour une ligne engagée
    seule). N'annuler que la première laissait les secondes bien vivantes.

    Renvoie le nombre de factures annulées.
    """
    from core.views import log_event
    from facturation.models import Facture
    from soins.models import ProcedureSoin

    ids = {soin.facture_id} if soin.facture_id else set()
    ids.update(ProcedureSoin.all_objects
               .filter(soin=soin, facture__isnull=False)
               .values_list('facture_id', flat=True))
    if not ids:
        return 0

    cause = f'Soin {soin.numero} annulé'
    if motif:
        cause += f' — {motif}'

    annulees = 0
    for facture in Facture.all_objects.filter(pk__in=ids).exclude(statut='annulee'):
        facture.statut = 'annulee'
        facture.save(update_fields=['statut'])
        log_event(facture, user, f'Facture annulée. Cause : {cause}', type='statut')
        annulees += 1
    return annulees
