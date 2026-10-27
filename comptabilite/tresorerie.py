"""
Trésorerie (lot 7) : où est l'argent, et les comptes disent-ils vrai ?

- **Position** : le solde de chaque compte de trésorerie (caisses, banque,
  Mobile Money, chèques à encaisser) selon la comptabilité.
- **Remise en banque** : les espèces d'une caisse déposées en banque passent
  par le compte de virements internes (585) — deux écritures, l'une qui sort
  l'argent de la caisse, l'autre qui le fait entrer en banque.
- **Rapprochement** : chaque ligne du relevé de la banque ou de l'opérateur
  est pointée avec la ligne d'écriture qui lui correspond. Ce qui reste
  non pointé explique l'écart entre le solde du relevé et celui des comptes :
  chèque pas encore encaissé, frais bancaires pas encore comptabilisés…

Les soldes comptables comptent les brouillons : un rapprochement se fait sur
tout ce qui a été saisi, validé ou non.
"""
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q, Sum

from .models import Compte, Ecriture, LigneEcriture, LigneReleve

ZERO = Decimal('0')
FENETRE_RAPPROCHEMENT = 7     # jours d'écart tolérés entre l'écriture et le relevé


class ErreurTresorerie(Exception):
    """Refus d'une opération de trésorerie, avec un message clair."""


def _francs(m):
    return f"{m:,.0f}".replace(',', ' ')


def _lignes(compte, fin=None, debut=None):
    qs = LigneEcriture.objects.filter(compte=compte,
                                      ecriture__in=Ecriture.objects.all().values('pk'))
    if fin:
        qs = qs.filter(ecriture__date__lte=fin)
    if debut:
        qs = qs.filter(ecriture__date__gte=debut)
    return qs


def solde_comptable(compte, fin=None):
    t = _lignes(compte, fin).aggregate(d=Sum('debit'), c=Sum('credit'))
    return (t['d'] or ZERO) - (t['c'] or ZERO)


def position(fin):
    """Solde de chaque compte de trésorerie (classe 5) mouvementé."""
    lignes = []
    for compte in Compte.objects.filter(numero__startswith='5').order_by('numero'):
        if not _lignes(compte, fin).exists():
            continue
        lignes.append({'compte': compte, 'solde': solde_comptable(compte, fin),
                       'tresorerie': getattr(compte, 'compte_tresorerie', None)})
    return lignes


# ─── Remise en banque ──────────────────────────────────────────────────────────

def disponible_en_caisse(caisse, jour):
    """Espèces de la caisse selon les comptes, écritures du jour comprises."""
    from . import ecritures as moteur
    moteur.generer(jour.replace(month=1, day=1), jour)
    return solde_comptable(moteur.compte_de_caisse(caisse), jour)


def creer_remise(caisse, compte_tresorerie, montant, jour, par, reference='', observation=''):
    from .models import RemiseBanque
    from . import ecritures as moteur
    if montant <= 0:
        raise ErreurTresorerie("Le montant déposé doit être positif.")
    disponible = disponible_en_caisse(caisse, jour)
    if montant > disponible:
        raise ErreurTresorerie(f"La caisse {caisse} ne contient que {_francs(disponible)} F selon les comptes.")
    with transaction.atomic():
        remise = RemiseBanque.objects.create(caisse=caisse, compte_tresorerie=compte_tresorerie, montant=montant,
                                             date=jour, reference=reference, observation=observation, cree_par=par)
        ecritures_remise(remise)
    return remise


def ecritures_remise(remise):
    """Sortie de la caisse vers 585, puis entrée en banque depuis 585."""
    from . import ecritures as moteur
    transit = moteur.compte('virement_interne')
    caisse = remise.caisse
    ct = remise.compte_tresorerie
    faites = []
    origine = f'remise_sortie:{remise.pk}'
    if not Ecriture.all_objects.filter(origine=origine).exists():
        faites.append(moteur.creer_ecriture(
            moteur.journal_de_caisse(caisse), remise.date, f'Remise en banque {remise.numero} — {caisse}',
            [(transit, None, remise.montant, ZERO, ct.libelle),
             (moteur.compte_de_caisse(caisse), None, ZERO, remise.montant, ct.libelle)],
            piece=remise.reference or remise.numero, origine=origine, centre=remise.centre))
    origine = f'remise_entree:{remise.pk}'
    if not Ecriture.all_objects.filter(origine=origine).exists():
        journal = moteur.journal('MM' if ct.type == 'mobile_money' else 'BQ')
        faites.append(moteur.creer_ecriture(
            journal, remise.date, f'Dépôt des espèces {remise.numero} — {caisse}',
            [(ct.compte, None, remise.montant, ZERO, str(caisse)),
             (transit, None, ZERO, remise.montant, str(caisse))],
            piece=remise.reference or remise.numero, origine=origine, centre=remise.centre))
    return faites


# ─── Relevé ────────────────────────────────────────────────────────────────────

def _lire_date(texte):
    texte = texte.strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y', '%d.%m.%Y'):
        try:
            return datetime.strptime(texte, fmt).date()
        except ValueError:
            continue
    return None


def _lire_montant(texte):
    texte = (texte or '').strip().replace(' ', '').replace(' ', '')
    if not texte:
        return None
    if ',' in texte and '.' in texte:
        texte = texte.replace('.', '').replace(',', '.')
    else:
        texte = texte.replace(',', '.')
    try:
        return Decimal(texte)
    except InvalidOperation:
        return None


def importer_releve(compte_tresorerie, contenu, par, format_='montant'):
    """Lignes de relevé depuis un fichier CSV exporté par la banque.

    Séparateur « ; » ou « , ». Deux formats, au choix de la personne qui
    importe (le deviner serait risqué : une référence numérique passerait pour
    une colonne de montant) :
    - 'montant' : date ; libellé ; montant (positif = entrée, négatif = sortie) ; [référence]
    - 'debit_credit' : date ; libellé ; débit ; crédit ; [référence]
      (débit = sortie, crédit = entrée, vu du relevé). Les lignes d'en-tête ou
    illisibles sont ignorées et signalées ; une ligne déjà importée (même date,
    libellé et montant) ne l'est pas deux fois.
    """
    texte = contenu.decode('utf-8-sig', errors='replace') if isinstance(contenu, bytes) else contenu
    separateur = ';' if texte.count(';') >= texte.count(',') else ','
    crees, ignorees = 0, []
    for numero, champs in enumerate(csv.reader(io.StringIO(texte), delimiter=separateur), start=1):
        champs = [c.strip() for c in champs]
        if not any(champs):
            continue
        jour = _lire_date(champs[0]) if champs else None
        if jour is None or len(champs) < 3:
            ignorees.append(numero)
            continue
        libelle = champs[1]
        if format_ == 'debit_credit':
            if len(champs) < 4:
                ignorees.append(numero)
                continue
            montant = (_lire_montant(champs[3]) or ZERO) - (_lire_montant(champs[2]) or ZERO)
            reference = champs[4] if len(champs) > 4 else ''
        else:
            montant = _lire_montant(champs[2])
            reference = champs[3] if len(champs) > 3 else ''
        if not montant:
            ignorees.append(numero)
            continue
        if LigneReleve.objects.filter(compte_tresorerie=compte_tresorerie, date=jour, libelle=libelle[:255],
                                      montant=montant).exists():
            continue
        LigneReleve.objects.create(compte_tresorerie=compte_tresorerie, date=jour, libelle=libelle[:255],
                                   montant=montant, reference=reference[:100], cree_par=par)
        crees += 1
    return crees, ignorees


# ─── Rapprochement ─────────────────────────────────────────────────────────────

def _montant_ligne(ligne):
    return ligne.debit - ligne.credit


def ecritures_non_rapprochees(compte_tresorerie, fin=None):
    return (_lignes(compte_tresorerie.compte, fin).filter(ligne_releve__isnull=True)
            .select_related('ecriture__journal').order_by('ecriture__date', 'pk'))


def releve_non_rapproche(compte_tresorerie, fin=None):
    qs = compte_tresorerie.releve.filter(ligne_ecriture__isnull=True)
    return qs.filter(date__lte=fin) if fin else qs


def rapprocher(ligne_releve, ligne_ecriture):
    if ligne_releve.ligne_ecriture_id:
        raise ErreurTresorerie("Cette ligne du relevé est déjà rapprochée.")
    if LigneReleve.objects.filter(ligne_ecriture=ligne_ecriture).exists():
        raise ErreurTresorerie("Cette ligne d'écriture est déjà rapprochée.")
    if ligne_ecriture.compte_id != ligne_releve.compte_tresorerie.compte_id:
        raise ErreurTresorerie("L'écriture ne porte pas sur le compte de ce relevé.")
    if _montant_ligne(ligne_ecriture) != ligne_releve.montant:
        raise ErreurTresorerie(f"Montants différents : relevé {_francs(ligne_releve.montant)} F, "
                               f"écriture {_francs(_montant_ligne(ligne_ecriture))} F.")
    ligne_releve.ligne_ecriture = ligne_ecriture
    ligne_releve.save(update_fields=['ligne_ecriture'])


def defaire(ligne_releve):
    ligne_releve.ligne_ecriture = None
    ligne_releve.save(update_fields=['ligne_ecriture'])


def rapprochement_automatique(compte_tresorerie):
    """Pointe chaque ligne du relevé avec l'écriture de même montant la plus
    proche en date (à ±7 jours), quand il n'y a pas d'ambiguïté."""
    candidates = list(ecritures_non_rapprochees(compte_tresorerie))
    pointees = 0
    for ligne in releve_non_rapproche(compte_tresorerie).order_by('date', 'pk'):
        possibles = [l for l in candidates if _montant_ligne(l) == ligne.montant
                     and abs((l.ecriture.date - ligne.date).days) <= FENETRE_RAPPROCHEMENT]
        if not possibles:
            continue
        possibles.sort(key=lambda l: abs((l.ecriture.date - ligne.date).days))
        if len(possibles) > 1 and abs((possibles[0].ecriture.date - ligne.date).days) == \
                abs((possibles[1].ecriture.date - ligne.date).days):
            continue          # deux candidates aussi proches : au comptable de choisir
        ligne.ligne_ecriture = possibles[0]
        ligne.save(update_fields=['ligne_ecriture'])
        candidates.remove(possibles[0])
        pointees += 1
    return pointees


def comptabiliser_ligne_releve(ligne, contrepartie, par):
    """Une opération vue seulement sur le relevé (frais, agios, intérêts) :
    on la passe en écriture, et elle se rapproche aussitôt."""
    from . import ecritures as moteur
    if ligne.ligne_ecriture_id:
        raise ErreurTresorerie("Cette ligne est déjà rapprochée.")
    ct = ligne.compte_tresorerie
    montant = abs(ligne.montant)
    if ligne.montant < 0:
        lignes = [(contrepartie, None, montant, ZERO, ct.libelle), (ct.compte, None, ZERO, montant, ct.libelle)]
    else:
        lignes = [(ct.compte, None, montant, ZERO, ct.libelle), (contrepartie, None, ZERO, montant, ct.libelle)]
    with transaction.atomic():
        ecriture = moteur.creer_ecriture(moteur.journal('MM' if ct.type == 'mobile_money' else 'BQ'), ligne.date,
                                         ligne.libelle, lignes, piece=ligne.reference, origine=f'releve:{ligne.pk}',
                                         par=par)
        rapprocher(ligne, ecriture.lignes.get(compte=ct.compte))
    return ecriture


def etat_rapprochement(compte_tresorerie, fin):
    """Solde du relevé et solde des comptes à la date, et ce qui explique l'écart."""
    ct = compte_tresorerie
    releve = ct.releve.filter(date__lte=fin)
    if ct.date_solde_initial:
        releve = releve.filter(date__gt=ct.date_solde_initial)
    solde_releve = ct.solde_initial + (releve.aggregate(s=Sum('montant'))['s'] or ZERO)
    solde_compta = solde_comptable(ct.compte, fin)
    ecritures_seules = list(ecritures_non_rapprochees(ct, fin))
    releve_seul = list(releve_non_rapproche(ct, fin))
    total_ecritures = sum((_montant_ligne(l) for l in ecritures_seules), ZERO)
    total_releve = sum((l.montant for l in releve_seul), ZERO)
    explique = solde_compta - total_ecritures + total_releve
    return {
        'solde_releve': solde_releve, 'solde_compta': solde_compta,
        'ecritures_seules': ecritures_seules, 'releve_seul': releve_seul,
        'total_ecritures': total_ecritures, 'total_releve': total_releve,
        'solde_explique': explique, 'ecart_inexplique': solde_releve - explique,
    }
