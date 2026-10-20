"""Reprise des ancrages blockchain restés en erreur.

Un ancrage en erreur (passerelle injoignable, réseau Fabric indisponible…)
n'est retenté automatiquement que si le même signal se redéclenche. Pour les
entités ancrées une seule fois (patient à sa création, paiement…), cette
commande, lancée périodiquement, assure la reprise.

L'empreinte est recalculée à partir de l'état courant de l'entité : si
celle-ci a été modifiée entre l'échec et la reprise, c'est l'état courant qui
est ancré.

Usage : python manage.py reessayer_ancrages [--limite 100]
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from blockchain_bridge import hashing
from blockchain_bridge.models import AncrageBlockchain
from blockchain_bridge.services import ancrer_evenement


def _metadonnees(ancrage):
    """Reconstitue les métadonnées techniques envoyées lors de l'ancrage
    initial (voir signals.py)."""
    if ancrage.type_entite == 'patient':
        return None
    if ancrage.type_entite == 'echange_hprim':
        from laboratoire.models import EchangeHPRIM

        from blockchain_bridge.signals import _metadonnees_hprim

        echange = EchangeHPRIM.objects.filter(pk=ancrage.id_entite).first()
        return _metadonnees_hprim(echange) if echange else None
    return {'type_document': ancrage.type_entite}


class Command(BaseCommand):
    help = "Retente l'ancrage blockchain des événements restés en erreur."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limite', type=int, default=100,
            help="Nombre maximal d'ancrages traités par exécution (100 par défaut).",
        )

    def handle(self, *args, **options):
        if not getattr(settings, 'BLOCKCHAIN_ENABLED', False):
            self.stdout.write('BLOCKCHAIN_ENABLED est désactivé : aucune reprise effectuée.')
            return

        ancrages = list(AncrageBlockchain.objects.filter(statut='erreur').order_by('pk')[:options['limite']])
        confirmes, echecs, introuvables = 0, 0, 0

        for ancrage in ancrages:
            empreinte = hashing.recalculer_empreinte(ancrage.type_entite, ancrage.id_entite)
            if empreinte is None:
                ancrage.erreur_message = "entité introuvable (supprimée depuis l'ancrage ?) : reprise impossible"
                ancrage.save(update_fields=['erreur_message'])
                introuvables += 1
                continue

            ancrer_evenement(
                ancrage.type_entite, ancrage.id_entite, empreinte,
                code_patient=ancrage.code_patient,
                code_centre=ancrage.code_centre,
                metadonnees=_metadonnees(ancrage),
            )
            ancrage.refresh_from_db()
            if ancrage.statut == 'confirme':
                confirmes += 1
            else:
                echecs += 1
                self.stderr.write(f'{ancrage.id_evenement} : {ancrage.erreur_message}')

        self.stdout.write(
            f'{len(ancrages)} ancrage(s) en erreur traité(s) : {confirmes} confirmé(s), '
            f'{echecs} toujours en erreur, {introuvables} entité(s) introuvable(s).'
        )
