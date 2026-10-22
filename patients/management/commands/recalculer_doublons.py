"""Relève les doublons de la base et les range dans `DoublonPaire`.

Le relevé précédent reste lisible pendant tout le calcul : les paires ne sont
remplacées qu'à la fin, en une seule transaction. Sans cela, l'écran des
doublons montrerait une liste vide ou à moitié remplie pendant les minutes que
dure le passage.

Prévue pour tourner chaque nuit. Sur la VM de production, une ligne de
crontab suffit — le projet n'a pas d'ordonnanceur, et n'en a pas besoin pour
un travail par jour :

    30 2 * * * cd /chemin/vers/SEGHO_WALE && .venv/bin/python manage.py \
               recalculer_doublons >> /var/log/segho-doublons.log 2>&1

2 h 30 du matin : le centre est fermé, et c'est aussi le filet du recalcul
ciblé, celui qui part après chaque enregistrement et qu'un worker recyclé peut
emporter.

Un bouton dans l'écran des doublons la lancera aussi à la demande, par
`core.taches.lancer`, pour que l'utilisateur voie la jauge comme pour un
import.
"""

import time

from django.core.management.base import BaseCommand, CommandError

from centres.models import Centre
from patients.cles_phonetiques import rafraichir
from patients.doublons_recalcul import (RecalculDejaEnCours, calculer_paires,
                                        recalculer_centre)
from patients.models import Patient


class Command(BaseCommand):
    help = "Recalcule les doublons détectés, centre par centre."

    def add_arguments(self, parser):
        parser.add_argument('--centre', type=int, default=None,
                            help="N'en traiter qu'un (par son identifiant).")
        parser.add_argument('--cles', action='store_true',
                            help='Régénérer aussi les clés phonétiques.')
        parser.add_argument('--simulation', action='store_true',
                            help='Compter sans rien écrire.')

    def handle(self, *args, **options):
        centres = self._centres(options['centre'])
        if not centres:
            raise CommandError('Aucun centre à traiter.')

        for centre_id, nom in centres:
            if options['cles']:
                self._cles(centre_id, nom)
            self._paires(centre_id, nom, options['simulation'])

    def _centres(self, centre_id):
        qs = Centre.objects.all() if centre_id is None else Centre.objects.filter(pk=centre_id)
        connus = list(qs.values_list('pk', 'nom'))
        # Une base montée avant les centres porte des fiches sans centre : les
        # ignorer les laisserait hors de tout relevé.
        if centre_id is None and Patient.all_objects.filter(centre__isnull=True).exists():
            connus.append((None, 'sans centre'))
        return connus

    def _cles(self, centre_id, nom):
        depart = time.monotonic()
        fiches = Patient.all_objects.filter(centre_id=centre_id).only(
            'pk', 'nom', 'prenoms', 'date_naissance', 'centre_id')
        ecrites = total = 0
        lot = []
        for fiche in fiches.iterator(chunk_size=2000):
            lot.append(fiche)
            if len(lot) >= 2000:
                ecrites += rafraichir(lot)
                total += len(lot)
                lot = []
        if lot:
            ecrites += rafraichir(lot)
            total += len(lot)
        self.stdout.write(
            f'{nom} — clés phonétiques : {ecrites} lignes pour {total} fiches '
            f'en {time.monotonic() - depart:.0f} s')

    def _paires(self, centre_id, nom, simulation):
        depart = time.monotonic()
        try:
            if simulation:
                nombre = len(calculer_paires(centre_id))
                suffixe = ' (simulation, rien écrit)'
            else:
                nombre = recalculer_centre(centre_id)
                suffixe = ''
        except RecalculDejaEnCours as erreur:
            raise CommandError(str(erreur))
        self.stdout.write(self.style.SUCCESS(
            f'{nom} — {nombre} paire(s) en {time.monotonic() - depart:.0f} s{suffixe}'))
