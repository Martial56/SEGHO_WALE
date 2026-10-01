from django.core.management.base import BaseCommand
from django.db import transaction

from hospitalisation.models import Hospitalisation
from patients.models import Pathologie, RegistreCuratif
from soins.models import ProcedureSoin


def _pks_du_registre(donnees):
    """Identifiants de pathologies stockés dans `cur_diagnostic` (liste ou chaîne)."""
    brut = (donnees or {}).get('cur_diagnostic', [])
    if isinstance(brut, str):
        brut = [brut] if brut else []
    return {int(v) for v in brut if str(v).strip().isdigit()}


class Command(BaseCommand):
    help = (
        "Vide le catalogue des pathologies. Par défaut ne fait qu'un état des lieux ; "
        "--confirmer supprime les pathologies jamais utilisées."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirmer', action='store_true',
            help="Supprime réellement (sans cette option, rien n'est modifié).",
        )
        parser.add_argument(
            '--inclure-utilisees', action='store_true',
            help="Supprime aussi les pathologies déjà utilisées : leurs diagnostics "
                 "deviennent « Sans diagnostic » dans les listes et les rapports.",
        )

    def handle(self, *args, **options):
        # Le gestionnaire de base ignore le filtre par centre : on vide tout le catalogue.
        toutes = set(Pathologie._base_manager.values_list('pk', flat=True))

        utilisees = set()
        for donnees in RegistreCuratif._base_manager.values_list('donnees', flat=True):
            utilisees |= _pks_du_registre(donnees)
        utilisees |= set(Hospitalisation._base_manager.exclude(maladie=None)
                         .values_list('maladie_id', flat=True))
        utilisees |= set(ProcedureSoin._base_manager.exclude(maladie=None)
                         .values_list('maladie_id', flat=True))
        utilisees &= toutes

        a_supprimer = toutes if options['inclure_utilisees'] else toutes - utilisees

        self.stdout.write(f"Pathologies en base          : {len(toutes)}")
        self.stdout.write(f"  dont utilisées             : {len(utilisees)}")
        self.stdout.write(f"  à supprimer                : {len(a_supprimer)}")
        conservees = sorted(Pathologie._base_manager.filter(pk__in=utilisees - a_supprimer)
                            .values_list('nom', flat=True))
        if conservees:
            self.stdout.write("Conservées car utilisées (relancer avec --inclure-utilisees pour les supprimer) :")
            for nom in conservees:
                self.stdout.write(f"  - {nom}")

        if not options['confirmer']:
            self.stdout.write(self.style.WARNING(
                "Simulation : rien n'a été modifié. Relancer avec --confirmer pour supprimer."))
            return

        with transaction.atomic():
            supprimees, _ = Pathologie._base_manager.filter(pk__in=a_supprimer).delete()
        self.stdout.write(self.style.SUCCESS(f"{supprimees} pathologie(s) supprimée(s)."))
