"""Les deux traces que l'écran des doublons relit.

Elles sont posées à la saisie : l'une quand on poursuit malgré une fiche
proche, l'autre quand on crée un dossier malgré un doublon signalé. Toutes
deux portent sur la **fiche existante**, parce qu'au moment où elles
s'écrivent la seconde n'existe pas encore, et peut ne jamais exister.

Les codes sont le seul repère sur lequel l'écran s'appuie. Chercher dans le
texte des messages marcherait aujourd'hui et plus demain : un message est
écrit pour être lu, il se reformule.
"""

#: « Continuer la saisie » dans la fenêtre des dossiers ressemblants.
CONFIRMATION = 'doublon.confirmation'

#: Dossier créé malgré un doublon bloquant, par qui détient la permission.
FORCAGE = 'doublon.forcage'

CODES = (FORCAGE, CONFIRMATION)

LIBELLES = {
    FORCAGE: 'Création forcée',
    CONFIRMATION: 'Saisie poursuivie',
}


def traces(centre=None):
    """Les deux familles, les plus récentes d'abord.

    Filtrées par centre à travers la fiche visée : `LogActivite` n'est pas
    cloisonné — il porte des événements de toute l'application —, c'est donc
    le patient qui donne le centre.
    """
    from django.contrib.contenttypes.models import ContentType
    from core.models import LogActivite
    from .models import Patient

    qs = (LogActivite.objects
          .filter(code__in=CODES,
                  content_type=ContentType.objects.get_for_model(Patient))
          .select_related('user')
          .order_by('-date'))
    if centre is not None:
        qs = qs.filter(object_id__in=Patient.all_objects.filter(centre=centre)
                       .values('pk'))
    return qs
