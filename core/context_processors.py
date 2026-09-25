from datetime import date

from django.db.models import F


#: Curseur de luminosité mis en sommeil le 2026-09-23, à la demande — la
#: fonctionnalité est conservée pour une mise à jour ultérieure, quand les
#: utilisateurs la réclameront. Repasser à True suffit à tout rallumer : rien
#: n'a été supprimé, ni le champ `UserProfile.luminosite`, ni la route
#: `luminosite_set`, ni les réglages déjà enregistrés par chacun.
LUMINOSITE_ACTIVE = False


def user_profile(request):
    from core.utils import LUMINOSITE_DEFAUT
    eteint = {'user_profile': None, 'accent_css': None,
              'luminosite': LUMINOSITE_DEFAUT, 'luminosite_active': LUMINOSITE_ACTIVE}
    if not request.user.is_authenticated:
        return eteint
    try:
        from core.models import UserProfile
        from core.utils import build_accent_css, is_valid_hex_color, normaliser_luminosite
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        accent_css = build_accent_css(profile.accent_color) if is_valid_hex_color(profile.accent_color) else None
        # Re-bornage défensif : le champ a des validateurs, mais ils ne sont pas
        # joués par un UPDATE en shell ni par un import de données. Le gabarit ne
        # doit jamais pouvoir écrire une luminosité illisible, quelle que soit la
        # valeur réellement en base.
        return {
            'user_profile': profile,
            'accent_css': accent_css,
            # En sommeil, on renvoie 100 % sans lire le profil : le filtre ne
            # s'applique plus, et la valeur enregistrée par l'utilisateur reste
            # intacte en base pour le jour où on rallume.
            'luminosite': (normaliser_luminosite(profile.luminosite)
                           if LUMINOSITE_ACTIVE else LUMINOSITE_DEFAUT),
            'luminosite_active': LUMINOSITE_ACTIVE,
        }
    except Exception:
        return eteint


def header_stats(request):
    empty = {'header_stats': {'medicaments_alerte': 0, 'factures_impayees': 0, 'analyses_pending': 0}}
    if not request.user.is_authenticated:
        return empty
    from core.utils import current_module
    module = current_module(request)
    try:
        return {
            'header_stats': {
                'medicaments_alerte': _medicaments_alerte_count() if module == 'pharmacie' else 0,
                'factures_impayees': _factures_impayees_count() if module == 'facturation' else 0,
                'analyses_pending': _analyses_pending_count() if module == 'laboratoire' else 0,
            }
        }
    except Exception:
        return empty


def _medicaments_alerte_count():
    """Produits sous le seuil d'alerte dans la pharmacie du centre actif.

    Comptait `pharmacie.Medicament`, la table d'avant les deux pharmacies : un
    seul `stock_actuel` pour tout le déploiement, jamais réapprovisionné. Elle
    est vide depuis, et l'alerte affichait donc zéro — rassurant et faux. Le
    compte porte maintenant sur ce que la pharmacie du centre a réellement en
    rayon, seuil d'alerte du produit à l'appui.
    """
    from pharmacie.disponibilite import pharmacie_active, produits_de_la_pharmacie

    return (produits_de_la_pharmacie(pharmacie_active())
            .filter(stock_pharma__lte=F('stock_alerte')).count())


def _factures_impayees_count():
    from facturation.models import Facture
    return Facture.objects.filter(statut__in=['emise', 'partielle']).count()


def _analyses_pending_count():
    from laboratoire.models import AnalyseLaboratoire
    return AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count()


def logo_saison(request):
    """Logo avec bonnet de Noël du 1er au 30 décembre (même fenêtre que le
    thème du kiosque de pointage) — header de l'appli, kiosque de pointage et
    page de bienvenue. Logo normal le reste de l'année."""
    today = date.today()
    if today.month == 12 and today.day <= 30:
        return {'logo_static': 'img/logo_noel.png'}
    return {'logo_static': 'img/logo.png'}
