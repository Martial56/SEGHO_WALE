"""Le mois d'un rapport, écrit en français.

`calendar.month_name` lit la locale du système d'exploitation, pas celle de
Django : sur un serveur en locale C — le cas par défaut — les fiches sortaient
« August 2026 » au lieu de « Août 2026 ». `date_format` passe par la langue
active de Django (`LANGUAGE_CODE = 'fr-fr'`), qui elle est garantie.
"""
from datetime import date

from django.utils.formats import date_format


def nom_du_mois(annee, mois):
    """« Août », « Septembre »… — la casse d'un titre, pas celle d'une phrase."""
    return date_format(date(annee, mois, 1), 'F').capitalize()
