"""Amorçage déclaratif des groupes métier : permissions et modules visibles.

    python manage.py init_groupes            # applique la matrice
    python manage.py init_groupes --dry-run  # montre ce qui changerait

La matrice ci-dessous est la seule source de vérité. La commande est
*déclarative* et rejouable : ce qui n'y figure pas est retiré du groupe. C'est
volontaire — c'est ce qui permet de corriger un groupe qui a dérivé, comme
« Infirmier » qui avait fini par détenir les huit permissions d'hospitalisation,
facturation et clôture comprises.

Deux mécanismes coexistent dans l'application et ne font pas la même chose :

* les **permissions** Django décident de ce qu'un utilisateur a le droit de
  faire — ce sont elles que les vues interrogent (`user.has_perm`) ;
* les **modules** (modules_permissions.Module) décident de ce qui s'affiche
  dans le menu et le lanceur. Ils ne verrouillent aucune URL.

Un groupe est donc décrit par les deux : ce qu'il voit, et ce qu'il peut.

Les noms ci-dessous ne sont qu'une proposition de départ, pas un contrat : plus
aucun contrôle d'accès ne compare un nom de groupe. Un groupe créé à la main
dans /admin/, nommé comme on veut, fait le même travail dès qu'il détient les
permissions. La commande reste là pour monter un jeu de groupes d'un coup.

Le rattachement d'un utilisateur à un centre ne se règle pas ici : il vit sur sa
fiche (bloc « Centres d'affectation »). Sans centre, un compte ne voit aucune
donnée, ce qui se confond facilement avec un défaut de permission.
"""

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from modules_permissions.models import GroupModule, Module


#: groupe -> permissions (app.codename) et modules visibles (Module.code).
MATRICE = {
    # Soigne : saisit les fiches, administre les soins, installe et décharge les
    # patients, clôture et annule les dossiers. Ne facture pas.
    'Infirmier': {
        'permissions': [
            'soins.view_soin', 'soins.add_soin', 'soins.change_soin',
            'soins.view_proceduresoin', 'soins.add_proceduresoin', 'soins.change_proceduresoin',
            'soins.can_administrer_soin',
            'hospitalisation.view_hospitalisation',
            'hospitalisation.add_hospitalisation',
            'hospitalisation.change_hospitalisation',
            'hospitalisation.can_confirmer_demande',
            'hospitalisation.can_installer_patient',
            'hospitalisation.can_decharger_patient',
            'hospitalisation.can_cloturer_dossier',
            'hospitalisation.can_annuler_demande',
            'hospitalisation.can_ajouter_soin',
            'patients.view_patient',
            'patients.view_rendezvous',
        ],
        'modules': ['patients', 'rendezvous', 'consultations', 'hospitalisation', 'gynecologie'],
    },
    # Encaisse : crée et valide les factures, enregistre les paiements, tient la
    # caisse. Consulte les dossiers qu'elle facture sans pouvoir les modifier.
    'Caisse': {
        'permissions': [
            'facturation.view_facture', 'facturation.add_facture', 'facturation.change_facture',
            'facturation.can_valider_facture',
            'facturation.view_lignefacture', 'facturation.add_lignefacture',
            'facturation.change_lignefacture',
            'facturation.view_paiement', 'facturation.add_paiement',
            # La caisse facture des soins et des hospitalisations : il lui faut
            # les voir pour les facturer. Sans le droit de lecture ni le module
            # correspondant, `can_creer_facture` ne sert à rien — un soin en
            # attente de paiement reste inatteignable depuis son menu, et il
            # n'apparaît pas dans la liste des factures puisqu'il n'en a pas
            # encore.
            'soins.view_soin', 'soins.view_proceduresoin',
            'soins.can_creer_facture',
            'hospitalisation.view_hospitalisation',
            'hospitalisation.can_creer_facture',
            'hospitalisation.can_confirmer_demande',
            'hospitalisation.can_cloturer_dossier',
            'caisse.view_sessioncaisse', 'caisse.add_sessioncaisse', 'caisse.change_sessioncaisse',
            'caisse.view_transactioncaisse', 'caisse.add_transactioncaisse',
            'patients.view_patient', 'patients.view_rendezvous',
        ],
        'modules': ['facturation', 'caisse', 'patients', 'rendezvous',
                    'consultations', 'hospitalisation'],
    },
    # Confirme la demande et décharge le patient — la décision médicale, à
    # l'entrée comme à la sortie du séjour.
    # Entrée volontairement réduite à ce que la décharge exige : lire le
    # dossier, le patient, et prononcer la sortie. Le reste du rôle Médecin
    # reste à définir ; tant qu'il n'est pas arbitré, mieux vaut un groupe
    # étroit qu'un groupe deviné.
    'Médecin': {
        'permissions': [
            'hospitalisation.view_hospitalisation',
            'hospitalisation.can_confirmer_demande',
            'hospitalisation.can_decharger_patient',
            'patients.view_patient',
            'patients.view_rendezvous',
        ],
        'modules': ['patients', 'rendezvous', 'consultations', 'hospitalisation'],
    },
}


def _permission(chemin):
    """Résout « app.codename » en objet Permission, ou None si inconnue."""
    app, _, codename = chemin.partition('.')
    return Permission.objects.filter(
        content_type__app_label=app, codename=codename
    ).first()


class Command(BaseCommand):
    help = "Applique la matrice des groupes métier : permissions et modules."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Affiche les changements sans rien écrire.",
        )

    def handle(self, *args, **options):
        # L'essai à blanc écrit puis annule, au lieu de sauter les écritures :
        # le compte rendu doit décrire ce qui se passerait vraiment.
        essai = options['dry_run']
        with transaction.atomic():
            for nom, regles in MATRICE.items():
                self._appliquer(nom, regles)
            if essai:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\nEssai à blanc : rien enregistré.'))

    # ── Étapes ──────────────────────────────────────────────────────────────

    def _appliquer(self, nom, regles):
        groupe, cree = Group.objects.get_or_create(name=nom)
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n{nom}{" (créé)" if cree else ""}'))

        voulues, inconnues = [], []
        for chemin in regles['permissions']:
            p = _permission(chemin)
            (voulues if p else inconnues).append(p or chemin)
        for chemin in inconnues:
            self.stdout.write(self.style.ERROR(f'  permission inconnue : {chemin}'))

        actuelles = set(groupe.permissions.all())
        cible = set(voulues)
        for p in sorted(cible - actuelles, key=lambda x: x.codename):
            self.stdout.write(self.style.SUCCESS(
                f'  + {p.content_type.app_label}.{p.codename}'))
        for p in sorted(actuelles - cible, key=lambda x: x.codename):
            self.stdout.write(self.style.WARNING(
                f'  − {p.content_type.app_label}.{p.codename}'))
        if not (cible ^ actuelles):
            self.stdout.write('  permissions déjà conformes')
        groupe.permissions.set(voulues)
        self._modules(groupe, regles['modules'])

    def _modules(self, groupe, codes):
        modules = {m.code: m for m in Module.objects.filter(code__in=codes)}
        for code in codes:
            if code not in modules:
                self.stdout.write(self.style.ERROR(f'  module inconnu : {code}'))

        actuels = set(GroupModule.objects.filter(group=groupe)
                      .values_list('module__code', flat=True))
        cible = set(modules)
        for code in sorted(cible - actuels):
            self.stdout.write(self.style.SUCCESS(f'  + module {code}'))
            GroupModule.objects.get_or_create(group=groupe, module=modules[code])
        for code in sorted(actuels - cible):
            self.stdout.write(self.style.WARNING(f'  − module {code}'))
            GroupModule.objects.filter(group=groupe, module__code=code).delete()
        if not (cible ^ actuels):
            self.stdout.write('  modules déjà conformes')
