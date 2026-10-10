"""Déclaration de la liste des caisses — une carte par caisse, bornée à une période.

Le total par caisse était le cumul depuis l'ouverture du centre : un chiffre qui
ne se rapportait à aucune journée de travail et qu'aucun caissier ne pouvait
rapprocher de son fond de tiroir. Il porte désormais sur la période retenue, par
défaut la journée en cours, comme la liste des factures.

La période se déclare ici comme une famille `core.listing`, pour que le menu
« Filtres » du module la génère tout seul et que le pilotage JavaScript commun
(setPeriode, applyDateFilter) la mène sans une ligne de script en plus.
"""

from datetime import date, datetime as dt, timedelta

from django.db.models import Q

from core.listing import Famille


#: Codes de la famille « Période », qui s'excluent mutuellement.
CODES_PERIODE = ('today', 'semaine', 'mois', 'annee')

#: La caisse travaille sur la journée en cours : c'est ce qu'on vient vérifier.
FILTRES_DEFAUT = ('today',)


def bornes_periode(codes, aujourdhui=None, date_from='', date_to=''):
    """(début, fin) de la période retenue, bornes incluses, `None` quand ouverte.

    Un intervalle explicite l'emporte sur les raccourcis, comme sur la liste des
    factures — les deux se contrediraient sinon. Une date illisible est ignorée
    plutôt que remontée : une URL recopiée de travers doit afficher la liste, pas
    une erreur.
    """
    aujourdhui = aujourdhui or date.today()
    date_from = (date_from or '').strip()
    date_to = (date_to or '').strip()

    if date_from or date_to:
        debut = fin = None
        try:
            if date_from:
                debut = dt.strptime(date_from, '%Y-%m-%d').date()
            if date_to:
                fin = dt.strptime(date_to, '%Y-%m-%d').date()
        except ValueError:
            return None, None
        return debut, fin

    codes = set(codes or ())
    if 'today' in codes:
        return aujourdhui, aujourdhui
    if 'semaine' in codes:
        return aujourdhui - timedelta(days=7), aujourdhui
    if 'mois' in codes:
        return aujourdhui.replace(day=1), aujourdhui
    if 'annee' in codes:
        return aujourdhui.replace(month=1, day=1), aujourdhui
    return None, None


def condition_periode(codes, aujourdhui=None, date_from='', date_to=''):
    """Condition de période à poser **dans** l'annotation, pas sur le queryset.

    Filtrer les caisses sur la date de leurs paiements ferait disparaître celles
    qui n'ont rien encaissé sur la période, au lieu de les afficher à 0 F : on
    croirait la caisse supprimée alors qu'elle n'a simplement pas servi ce
    jour-là. Placée dans le `filter=` de l'agrégat, elle ne retire aucune ligne.
    """
    debut, fin = bornes_periode(codes, aujourdhui, date_from, date_to)
    condition = Q()
    if debut:
        condition &= Q(paiements__date_paiement__date__gte=debut)
    if fin:
        condition &= Q(paiements__date_paiement__date__lte=fin)
    return condition


def _periode_sans_effet(qs, codes, contexte):
    """La période ne filtre pas les caisses : voir `condition_periode`."""
    return qs


def familles_caisses():
    """Familles de filtres de la liste des caisses."""
    return [
        Famille('periode', "Période d'encaissement", exclusive=True, dates=True,
                applique=_periode_sans_effet, valeurs=[
                    ('today',   "Aujourd'hui",      Q()),
                    ('semaine', '7 derniers jours', Q()),
                    ('mois',    'Mois en cours',    Q()),
                    ('annee',   'Année en cours',   Q()),
                ]),
        Famille('etat', 'État', valeurs=[
            ('etat_actif',   'Active',   Q(actif=True)),
            ('etat_inactif', 'Inactive', Q(actif=False)),
        ]),
    ]


def listing_caisses():
    """Déclaration de la liste des caisses, partagée par la page et son export."""
    from core.listing import Listing

    return Listing(
        recherche=('nom', 'code'),
        familles=familles_caisses(),
        par_page=100,
        filtres_defaut=FILTRES_DEFAUT,
        tri_defaut=('nom',),
    )


def caisses_de_la_periode(filtres, aujourdhui, date_from, date_to):
    """Caisses annotées de ce qu'elles ont encaissé sur la période retenue.

    La période borne l'agrégat, pas le jeu : une caisse qui n'a rien encaissé
    s'affiche à 0 F au lieu de disparaître. Une facture annulée a été
    remboursée, son encaissement ne pèse plus dans la caisse.
    """
    from django.db.models import Count, Q, Sum

    from .models import Caisse

    encaisse = (condition_periode(filtres, aujourdhui, date_from, date_to)
                & ~Q(paiements__facture__statut='annulee'))
    return Caisse.objects.annotate(
        total=Sum('paiements__montant', filter=encaisse),
        nb_paiements=Count('paiements', filter=encaisse),
    ).order_by('nom')
