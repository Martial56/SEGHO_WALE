from datetime import date, timedelta
from .models import Employe, AlerteContrat, DocumentEmploye, AlerteDocument, NotificationConge


def alertes_contrat(request):
    if not request.user.is_authenticated:
        return {}

    from core.utils import current_module
    module = current_module(request)

    today     = date.today()
    limite_2m = today + timedelta(days=60)

    alertes_c = AlerteContrat.objects.none()
    alertes_d = AlerteDocument.objects.none()

    # La génération/mise à jour des alertes est coûteuse (une requête par
    # employé/document concerné) : on ne la fait que dans le module concerné,
    # comme les autres context processors de la cloche de notifications.
    if module == 'employer':
        # ── Alertes fin de contrat ─────────────────────────────────────────
        employes = Employe.objects.filter(
            statut='actif',
            date_fin_contrat__isnull=False,
            date_fin_contrat__gte=today,
            date_fin_contrat__lte=limite_2m,
        )
        for emp in employes:
            jours = (emp.date_fin_contrat - today).days
            if jours <= 30:
                alerte, _ = AlerteContrat.objects.get_or_create(
                    employe=emp, echeance='1_mois',
                    defaults={'date_fin_contrat': emp.date_fin_contrat},
                )
                if alerte.date_fin_contrat != emp.date_fin_contrat:
                    alerte.date_fin_contrat = emp.date_fin_contrat
                    alerte.lue = False
                    alerte.save(update_fields=['date_fin_contrat', 'lue'])
                AlerteContrat.objects.filter(employe=emp, echeance='2_mois', lue=False).update(lue=True)
            else:
                alerte, _ = AlerteContrat.objects.get_or_create(
                    employe=emp, echeance='2_mois',
                    defaults={'date_fin_contrat': emp.date_fin_contrat},
                )
                if alerte.date_fin_contrat != emp.date_fin_contrat:
                    alerte.date_fin_contrat = emp.date_fin_contrat
                    alerte.lue = False
                    alerte.save(update_fields=['date_fin_contrat', 'lue'])

        alertes_c = (
            AlerteContrat.objects.filter(lue=False)
            .select_related('employe')
            .order_by('date_fin_contrat')[:30]
        )

        # ── Alertes documents expirés ──────────────────────────────────────
        docs = DocumentEmploye.objects.filter(
            date_expiration__isnull=False,
            date_expiration__gte=today,
            date_expiration__lte=limite_2m,
        ).select_related('employe')

        for doc in docs:
            jours = (doc.date_expiration - today).days
            if jours <= 30:
                alerte, _ = AlerteDocument.objects.get_or_create(
                    document=doc, echeance='1_mois',
                    defaults={'date_expiration': doc.date_expiration},
                )
                if alerte.date_expiration != doc.date_expiration:
                    alerte.date_expiration = doc.date_expiration
                    alerte.lue = False
                    alerte.save(update_fields=['date_expiration', 'lue'])
                AlerteDocument.objects.filter(document=doc, echeance='2_mois', lue=False).update(lue=True)
            else:
                alerte, _ = AlerteDocument.objects.get_or_create(
                    document=doc, echeance='2_mois',
                    defaults={'date_expiration': doc.date_expiration},
                )
                if alerte.date_expiration != doc.date_expiration:
                    alerte.date_expiration = doc.date_expiration
                    alerte.lue = False
                    alerte.save(update_fields=['date_expiration', 'lue'])

        alertes_d = (
            AlerteDocument.objects.filter(lue=False)
            .select_related('document__employe')
            .order_by('date_expiration')[:30]
        )

    # ── Notifications congés (pour l'utilisateur courant) ─────────────────────
    # Module distinct de "Employés" (/conges/ a sa propre icône) : n'afficher
    # ces notifications que lorsqu'on est effectivement dans le module congés.
    if module == 'conges':
        notifs_conge = (
            NotificationConge.objects.filter(destinataire=request.user, lue=False)
            .select_related('conge__employe')
            .order_by('-cree_le')[:20]
        )
        notifs_conge_count = NotificationConge.objects.filter(
            destinataire=request.user, lue=False
        ).count()
    else:
        notifs_conge = NotificationConge.objects.none()
        notifs_conge_count = 0

    alertes_contrat_count = AlerteContrat.objects.filter(lue=False).count() if module == 'employer' else 0
    alertes_document_count = AlerteDocument.objects.filter(lue=False).count() if module == 'employer' else 0
    total = alertes_contrat_count + alertes_document_count + notifs_conge_count

    return {
        'alertes_contrat':    alertes_c,
        'alertes_document':   alertes_d,
        'alertes_count':      total,
        'notifs_conge':       notifs_conge,
        'notifs_conge_count': notifs_conge_count,
        'show_rh_alerts':     True,
    }
