# -*- coding: utf-8 -*-
"""
Relève les résultats de laboratoire (messages ORU) déposés par FTP et les
intègre dans la base.

Usage :
    python manage.py relever_resultats_hprim

À planifier via cron, par ex. toutes les 10 minutes :
    */10 * * * * cd /chemin/SEGHO_WALE && python manage.py relever_resultats_hprim
"""

from django.core.management.base import BaseCommand

from laboratoire.hprim.services import relever_resultats


class Command(BaseCommand):
    help = "Relève et intègre les résultats de laboratoire au format HPRIM (ORU)."

    def handle(self, *args, **options):
        try:
            echanges = relever_resultats()
        except RuntimeError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        if not echanges:
            self.stdout.write("Aucun nouveau fichier de résultats.")
            return

        for e in echanges:
            style = self.style.SUCCESS if e.statut == "traite" else self.style.WARNING
            self.stdout.write(style(f"{e.nom_fichier} [{e.statut}] : {e.message_log}"))
