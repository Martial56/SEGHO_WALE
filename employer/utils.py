from decimal import Decimal


# Droit légal ivoirien : 2,2 jours ouvrables par mois de service (Code du travail art. 25.6)
QUOTA_ANNUEL_DEFAUT = Decimal('26.0')


def quota_annuel(employe):
    """Retourne le quota de jours de congé annuel pour un employé.

    Retourne 0 si le type de contrat n'ouvre pas droit au congé (vacataires,
    prestataires, etc.), sinon le quota légal standard ivoirien.
    """
    try:
        if employe.type_contrat and not employe.type_contrat.droit_au_conge:
            return Decimal('0.0')
    except Exception:
        pass
    return QUOTA_ANNUEL_DEFAUT
