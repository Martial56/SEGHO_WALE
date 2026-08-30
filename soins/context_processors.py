from .models import Soin
from .regles import condition_a_facturer, condition_administrable


def soins_alertes(request):
    """Alimente la cloche de notifications globale, module Soins.

    Deux alertes, adressées à deux rôles différents — une notification n'a de
    sens que pour qui peut agir dessus :

    * « en attente de paiement » va à la **caisse**. Le geste attaché est de
      créer la facture, réservé à `soins.can_creer_facture`. Un infirmier ne
      peut rien en faire : il ne facture pas, et il ne pourra administrer le
      soin qu'une fois la facture payée. Auparavant elle s'affichait pour tout
      le monde.
    * « prêt à être administré » va aux **soignants**, sur
      `soins.can_administrer_soin`. C'est le pendant : la facture est réglée,
      le geste peut être posé.

    Les deux ne sortent que dans /soins/ (voir core.utils.current_module) et,
    `Soin` étant cloisonné, ne montrent que le centre actif.
    """
    vide = {
        'soins_en_attente': Soin.objects.none(), 'soins_en_attente_count': 0,
        'soins_a_administrer': Soin.objects.none(), 'soins_a_administrer_count': 0,
    }
    if not request.user.is_authenticated:
        return vide

    from core.utils import current_module
    if current_module(request) != 'soins':
        return vide

    contexte = dict(vide)

    if request.user.has_perm('soins.can_creer_facture'):
        qs = (Soin.objects.filter(condition_a_facturer())
              .select_related('patient').order_by('-date_heure'))
        contexte['soins_en_attente'] = qs[:20]
        contexte['soins_en_attente_count'] = qs.count()

    if request.user.has_perm('soins.can_administrer_soin'):
        qs = (Soin.objects.filter(condition_administrable())
              .select_related('patient').order_by('-date_heure'))
        contexte['soins_a_administrer'] = qs[:20]
        contexte['soins_a_administrer_count'] = qs.count()

    return contexte
