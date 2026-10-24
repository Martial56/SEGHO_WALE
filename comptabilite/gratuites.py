"""
Remises et gratuités : toute remise porte un motif.

La facture garde le prix plein de chaque acte ; la remise (en %, par ligne)
dit ce que le patient ne paie pas, et le motif de la facture dit pourquoi. Le
centre connaît ainsi l'effort social qu'il consent — ce que les bailleurs et
le conseil d'administration demandent — au lieu de remises muettes.
"""
from decimal import Decimal, InvalidOperation

ZERO = Decimal('0')


def remises_postees(donnees):
    """Remises (%) des lignes non vides d'un formulaire de facture."""
    remises = []
    for cle, valeur in donnees.items():
        if not cle.startswith('ligne_remise_'):
            continue
        indice = cle[len('ligne_remise_'):]
        if not (donnees.get(f'ligne_libelle_{indice}') or '').strip():
            continue
        try:
            remise = Decimal(str(valeur or '0').replace(',', '.'))
        except InvalidOperation:
            continue
        if remise > 0:
            remises.append(remise)
    return remises


def controler_remises(donnees, motif, user):
    """Message d'erreur si les remises saisies ne sont pas couvertes, sinon None.

    Une remise sans motif est refusée ; une remise au-delà du plafond du motif
    n'est permise qu'à qui en a reçu le droit.
    """
    remises = remises_postees(donnees)
    if not remises:
        return None
    if motif is None:
        return "Une remise est saisie : indiquez le motif de la remise ou de la gratuité."
    plus_forte = max(remises)
    if plus_forte > motif.remise_max and not user.has_perm('comptabilite.accorder_remise_hors_plafond'):
        return (f"Le motif « {motif} » autorise au plus {motif.remise_max:g} % de remise "
                f"(saisi : {plus_forte:g} %). Seule une personne autorisée peut aller au-delà.")
    return None


def montant_gratuite(lignes):
    """Ce que les remises ont retiré du prix plein, en francs."""
    total = ZERO
    for ligne in lignes:
        if ligne.remise:
            total += ligne.quantite * ligne.prix_unitaire * ligne.remise / 100
    return total.quantize(Decimal('1'))


def etat_gratuites(debut, fin):
    """Gratuités accordées entre deux dates : par motif, et la liste des factures.

    Les factures annulées n'en font pas partie : la remise n'a finalement
    profité à personne.
    """
    from facturation.models import Facture
    factures = (Facture.objects
                .filter(date_emission__date__range=[debut, fin], lignes__remise__gt=0)
                .exclude(statut__in=['annulee', 'brouillon'])
                .select_related('patient', 'motif_remise', 'cree_par')
                .prefetch_related('lignes').distinct().order_by('date_emission'))
    lignes, par_motif = [], {}
    total = ZERO
    for facture in factures:
        montant = montant_gratuite(facture.lignes.all())
        if not montant:
            continue
        motif = str(facture.motif_remise) if facture.motif_remise_id else 'Sans motif (avant le contrôle)'
        brut = facture.montant_total + montant
        lignes.append({'facture': facture, 'motif': motif, 'montant': montant, 'prix_plein': brut})
        groupe = par_motif.setdefault(motif, {'motif': motif, 'nb': 0, 'montant': ZERO})
        groupe['nb'] += 1
        groupe['montant'] += montant
        total += montant
    return {
        'lignes': lignes,
        'par_motif': sorted(par_motif.values(), key=lambda g: -g['montant']),
        'total': total,
    }
