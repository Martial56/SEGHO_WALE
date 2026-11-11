"""Clôture des journaux, mois par mois, comme dans Sage 100.

Clôturer le mois d'un journal le fige : plus aucune écriture n'y est créée,
validée ni supprimée (`ecritures.verifier_periode`). Une opération oubliée se
passe alors dans un mois ouvert. Le lettrage reste possible.

Conditions : le mois est commencé, ses écritures sont toutes validées (pas
de brouillon), et l'exercice qui le contient existe. Un mois clôturé se
rouvre (droit de clôturer l'exercice), sauf si son exercice est clos.
"""
from datetime import date

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from .ecritures import ErreurCompta, premier_du_mois
from .models import Ecriture, Exercice, Journal, PeriodeCloturee


def mois_de(exercice):
    """Les premiers jours des mois de l'exercice."""
    mois, fin = premier_du_mois(exercice.date_debut), exercice.date_fin
    resultat = []
    while mois <= fin:
        resultat.append(mois)
        mois = date(mois.year + mois.month // 12, mois.month % 12 + 1, 1)
    return resultat


def _fin_du_mois(mois):
    suivant = date(mois.year + mois.month // 12, mois.month % 12 + 1, 1)
    return date.fromordinal(suivant.toordinal() - 1)


def _ecritures(journal, mois):
    return Ecriture.all_objects.filter(journal=journal, date__range=[mois, _fin_du_mois(mois)])


def cloturer(journal, mois, par):
    mois = premier_du_mois(mois)
    if mois > timezone.localdate():
        raise ErreurCompta(f"{mois:%m/%Y} n'est pas encore commencé : on ne clôture qu'un mois commencé.")
    if PeriodeCloturee.objects.filter(journal=journal, mois=mois).exists():
        raise ErreurCompta(f"Le journal {journal.code} est déjà clôturé pour {mois:%m/%Y}.")
    brouillons = _ecritures(journal, mois).filter(statut='brouillon').count()
    if brouillons:
        raise ErreurCompta(f"{journal.code} {mois:%m/%Y} : {brouillons} écriture(s) en brouillon. Validez-les "
                           "ou supprimez-les avant de clôturer.")
    return PeriodeCloturee.objects.create(journal=journal, mois=mois, cloturee_par=par)


def rouvrir(journal, mois):
    mois = premier_du_mois(mois)
    periode = PeriodeCloturee.objects.filter(journal=journal, mois=mois).first()
    if periode is None:
        raise ErreurCompta(f"Le journal {journal.code} n'est pas clôturé pour {mois:%m/%Y}.")
    if Exercice.objects.filter(date_debut__lte=mois, date_fin__gte=mois, statut='cloture').exists():
        raise ErreurCompta(f"L'exercice de {mois:%m/%Y} est clos : rouvrez d'abord l'exercice.")
    periode.delete()


def cloturer_jusqu_a(mois, par, journaux=None):
    """Clôture tous les journaux, de chaque mois de l'exercice jusqu'à `mois`
    inclus. Rend (nombre de périodes clôturées, [refus])."""
    mois = premier_du_mois(mois)
    exercice = Exercice.objects.filter(date_debut__lte=mois, date_fin__gte=mois).first()
    if exercice is None:
        raise ErreurCompta(f"Aucun exercice ne contient {mois:%m/%Y}.")
    faites, refus = 0, []
    with transaction.atomic():
        for j in journaux or Journal.objects.filter(actif=True):
            for m in mois_de(exercice):
                if m > mois:
                    break
                if PeriodeCloturee.objects.filter(journal=j, mois=m).exists():
                    continue
                try:
                    cloturer(j, m, par)
                    faites += 1
                except ErreurCompta as e:
                    refus.append(str(e))
    return faites, refus


def grille(exercice):
    """[(journal, [cellule par mois])] : chaque cellule dit si le mois est
    clôturé, et combien il porte d'écritures et de brouillons."""
    mois = mois_de(exercice)
    compteurs = {}
    for row in (Ecriture.all_objects.filter(exercice=exercice)
                .values('journal_id', 'date__year', 'date__month')
                .annotate(n=Count('pk'), b=Count('pk', filter=Q(statut='brouillon')))):
        compteurs[(row['journal_id'], date(row['date__year'], row['date__month'], 1))] = (row['n'], row['b'])
    clotures = {(p.journal_id, p.mois): p for p in
                PeriodeCloturee.objects.filter(mois__in=mois).select_related('cloturee_par')}
    actifs = set(Journal.objects.filter(actif=True).values_list('pk', flat=True))
    utilises = {j for j, _ in compteurs} | {j for j, _ in clotures}
    aujourdhui = timezone.localdate()
    lignes = []
    for j in Journal.objects.filter(pk__in=actifs | utilises).order_by('code'):
        cellules = []
        for m in mois:
            n, b = compteurs.get((j.pk, m), (0, 0))
            cellules.append({'mois': m, 'ecritures': n, 'brouillons': b, 'cloture': clotures.get((j.pk, m)),
                             'futur': m > aujourdhui})
        lignes.append((j, cellules))
    return mois, lignes
