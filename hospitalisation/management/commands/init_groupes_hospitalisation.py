"""
Commande d'amorçage des groupes et permissions du module hospitalisation.

Usage :
    python manage.py init_groupes_hospitalisation
    python manage.py init_groupes_hospitalisation --reset  # repart de zéro

Les noms de groupes définis ici ne servent QU'ICI — ils ne sont jamais
référencés dans les vues ni dans get_actions_disponibles(). L'attribution
des permissions suit la matrice action × statut × permission de services.py.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


# ─── MATRICE : groupe → liste de codenames de permissions ──────────────────
# Seuls les codenames sont utilisés, pas les noms de groupe. Toute modification
# de la matrice est isolée ici et n'impacte pas les vues.
GROUPES_PERMISSIONS = {
    # Rôle Médecins : créer, confirmer, décharger, annuler
    'Médecins': [
        'hospitalisation.add_hospitalisation',
        'hospitalisation.change_hospitalisation',
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_confirmer_demande',
        'hospitalisation.can_decharger_patient',
        'hospitalisation.can_annuler_demande',
        
    ],
    # Rôle Infirmiers : créer, modifier, installer le patient
    'Infirmiers': [
        'hospitalisation.add_hospitalisation',
        'hospitalisation.change_hospitalisation',
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_installer_patient',
    ],
    # Rôle Caisse : facturer, clôturer
    'Caisse': [
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_creer_facture',
        'hospitalisation.can_cloturer_dossier',
    ],
    # Rôle Accueil : créer, modifier, annuler
    'Accueil': [
        'hospitalisation.add_hospitalisation',
        'hospitalisation.change_hospitalisation',
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_annuler_demande',
        'hospitalisation.can_installer_patient',
    ],
    # Rôle Major : confirmer, installer, annuler (supervision soignante)
    'Major': [
        'hospitalisation.add_hospitalisation',
        'hospitalisation.change_hospitalisation',
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_confirmer_demande',
        'hospitalisation.can_installer_patient',
        'hospitalisation.can_annuler_demande',
    ],
    # Rôle Soins (module soins) : peut aussi décharger — demande explicite
    'Soins': [
        'hospitalisation.view_hospitalisation',
        'hospitalisation.can_decharger_patient',
    ],
}


class Command(BaseCommand):
    help = "Crée les groupes métier d'hospitalisation et leur attribue les permissions selon la matrice."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help="Vider les permissions de ces groupes avant de les réassigner."
        )

    def handle(self, *args, **options):
        reset = options['reset']
        errors = []

        for groupe_nom, perm_list in GROUPES_PERMISSIONS.items():
            groupe, created = Group.objects.get_or_create(name=groupe_nom)
            action_str = "créé" if created else "mis à jour"

            if reset:
                groupe.permissions.clear()

            nb_ok = 0
            for perm_str in perm_list:
                try:
                    app_label, codename = perm_str.split('.', 1)
                    perm = Permission.objects.get(
                        codename=codename,
                        content_type__app_label=app_label,
                    )
                    groupe.permissions.add(perm)
                    nb_ok += 1
                except Permission.DoesNotExist:
                    msg = f"  ⚠  Permission introuvable : {perm_str} (appliquez les migrations d'abord)"
                    errors.append(msg)
                    self.stderr.write(msg)

            self.stdout.write(
                self.style.SUCCESS(f"  ✓  Groupe « {groupe_nom} » {action_str} ({nb_ok}/{len(perm_list)} permissions)")
            )

        if errors:
            self.stderr.write(
                self.style.WARNING(
                    f"\n{len(errors)} permission(s) introuvable(s). "
                    "Assurez-vous d'avoir appliqué toutes les migrations :\n"
                    "  python manage.py migrate"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nGroupes configurés. Attribuez-les ensuite aux utilisateurs via l'admin Django."
            ))
