from django.core.management.base import BaseCommand
from datetime import date, timedelta
from django.db.models import Q

from employer.models import Conge, HistoriqueConge, NotificationConge
from django.contrib.auth.models import User

RH_GROUPS = ['RH', 'Directeur', 'Administrateur', 'Médecin Chef', 'Médecin Chef Adjoint']


class Command(BaseCommand):
    help = (
        "Passage automatique des congés : approuvé→en cours, en cours→terminé. "
        "Envoie aussi des rappels de retour la veille."
    )

    def handle(self, *args, **options):
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # ── 1. Approuvé → En cours ────────────────────────────────────────────
        to_start = Conge.objects.filter(statut='approuve', date_debut__lte=today)
        count_start = 0
        for c in to_start:
            c.statut = 'en_cours'
            c.save(update_fields=['statut'])
            HistoriqueConge.objects.create(
                conge=c, action='mis_en_cours', fait_par=None,
                commentaire='Passage automatique système',
            )
            count_start += 1
        self.stdout.write(f'{count_start} congé(s) passé(s) en cours.')

        # ── 2. En cours → Terminé ─────────────────────────────────────────────
        to_end = Conge.objects.filter(statut='en_cours', date_fin__lt=today)
        count_end = 0
        for c in to_end:
            c.statut = 'termine'
            c.save(update_fields=['statut'])
            HistoriqueConge.objects.create(
                conge=c, action='termine', fait_par=None,
                commentaire='Passage automatique système',
            )
            count_end += 1
        self.stdout.write(f'{count_end} congé(s) terminé(s).')

        # ── 3. Rappels de retour (congés finissant demain) ────────────────────
        retours = Conge.objects.filter(
            statut='en_cours', date_fin=tomorrow,
        ).select_related('employe__user')

        rh_users = User.objects.filter(
            Q(is_superuser=True) | Q(groups__name__in=RH_GROUPS)
        ).distinct()

        count_rappels = 0
        for c in retours:
            msg_rh = (
                f"Rappel retour : {c.employe.nom_complet} reprend son service "
                f"demain {tomorrow:%d/%m/%Y} "
                f"(congé {c.get_type_conge_display()} "
                f"du {c.date_debut:%d/%m/%Y} au {c.date_fin:%d/%m/%Y})."
            )
            for rh in rh_users:
                NotificationConge.objects.get_or_create(
                    destinataire=rh,
                    conge=c,
                    type_notif='approuve',
                    defaults={'message': msg_rh},
                )
            emp_user = getattr(c.employe, 'user', None)
            if emp_user:
                msg_emp = (
                    f"Rappel : vous reprenez votre poste demain {tomorrow:%d/%m/%Y} "
                    f"après votre {c.get_type_conge_display()}."
                )
                NotificationConge.objects.get_or_create(
                    destinataire=emp_user,
                    conge=c,
                    type_notif='approuve',
                    defaults={'message': msg_emp},
                )
            count_rappels += 1
        self.stdout.write(f'{count_rappels} rappel(s) de retour envoyé(s).')
        self.stdout.write(self.style.SUCCESS('auto_conge_statut terminé.'))
