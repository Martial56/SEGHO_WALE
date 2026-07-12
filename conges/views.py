import calendar
from datetime import date as _d, timedelta as timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from django.db.models import Q as _Q
from employer.models import Employe, Conge, SoldeConge, HistoriqueConge, NotificationConge, Presence
from conges.utils import (
    compter_jours_ouvres, detecter_conflits, get_or_create_solde,
    jours_feries_ivoire, jours_feries_labels, quota_annuel,
    TYPES_DEDUCTIBLES, DUREES_EXCEPTIONNELLES,
)

RH_MANAGE_GROUPS = {'Médecin Chef', 'Médecin Chef Adjoint', 'Administrateur', 'Directeur', 'RH'}

_MOIS_FR = [
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
]


def can_manage_rh(user):
    return user.is_superuser or user.groups.filter(name__in=RH_MANAGE_GROUPS).exists()


def _employes_eligibles():
    """Retourne les employés actifs ayant droit au congé (exclut vacataires/prestataires)."""
    return Employe.objects.filter(statut='actif').filter(
        _Q(type_contrat__isnull=True) | _Q(type_contrat__droit_au_conge=True)
    ).select_related('type_contrat')


def _rh_users():
    """Retourne les utilisateurs RH/direction pouvant gérer les congés."""
    return User.objects.filter(
        _Q(is_superuser=True) |
        _Q(groups__name__in=list(RH_MANAGE_GROUPS))
    ).distinct()


def _send_notif(destinataires, conge, type_notif, message):
    """Crée des NotificationConge pour chaque destinataire et envoie un email."""
    for user in destinataires:
        NotificationConge.objects.create(
            destinataire=user,
            conge=conge,
            type_notif=type_notif,
            message=message,
        )
    _send_email(destinataires, f"[CMS WALÉ] {message}", message)


def _send_email(destinataires, subject, body):
    """Envoie un email à chaque destinataire ayant une adresse email configurée."""
    from django.core.mail import send_mail
    from django.conf import settings
    emails = [u.email for u in destinataires if getattr(u, 'email', '')]
    if not emails:
        return
    full_body = (
        f"{body}\n\n"
        f"---\n"
        f"Centre Médico-Social WALÉ — Système de gestion des congés\n"
        f"Cet email est généré automatiquement, ne pas répondre."
    )
    try:
        send_mail(
            subject=subject,
            message=full_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=True,
        )
    except Exception:
        pass


def _add_historique(conge, action, user, commentaire=''):
    HistoriqueConge.objects.create(
        conge=conge,
        action=action,
        fait_par=user,
        commentaire=commentaire,
    )


def _create_presence_for_conge(conge):
    """Crée les enregistrements Présence (absent) pour chaque jour ouvré du congé."""
    feries = set()
    for y in range(conge.date_debut.year, conge.date_fin.year + 1):
        feries |= jours_feries_ivoire(y)
    current = conge.date_debut
    motif = f'Congé: {conge.get_type_conge_display()}'
    while current <= conge.date_fin:
        if current.weekday() < 5 and current not in feries:
            Presence.objects.get_or_create(
                employe=conge.employe,
                date=current,
                defaults={'present': False, 'motif_absence': motif},
            )
        current += timedelta(days=1)


def _delete_presence_for_conge(conge):
    """Supprime les enregistrements Présence auto-créés pour ce congé."""
    Presence.objects.filter(
        employe=conge.employe,
        date__gte=conge.date_debut,
        date__lte=conge.date_fin,
        present=False,
        motif_absence__startswith='Congé:',
    ).delete()


SEUIL_CHEVAUCHEMENT = 40  # % du service simultanément en congé


def _auto_approuve_vers_en_cours():
    """Passe en 'en cours' tout congé approuvé dont la date de début est atteinte."""
    today = _d.today()
    for c in Conge.objects.filter(statut='approuve', date_debut__lte=today):
        c.statut = 'en_cours'
        c.save(update_fields=['statut'])
        HistoriqueConge.objects.create(
            conge=c, action='mis_en_cours', fait_par=None,
            commentaire='Passage automatique — date de début atteinte',
        )


def _check_chevauchement(employe, date_debut, date_fin, exclude_pk=None):
    """Retourne un dict d'alerte si ≥SEUIL_CHEVAUCHEMENT% du service est déjà en congé sur la période."""
    if not getattr(employe, 'service_id', None):
        return None
    qs_service = _employes_eligibles().filter(service_id=employe.service_id)
    nb_total = qs_service.count()
    if nb_total <= 1:
        return None
    conges_qs = Conge.objects.filter(
        employe__in=qs_service,
        statut__in=['approuve', 'en_cours', 'valide_service'],
        date_debut__lte=date_fin,
        date_fin__gte=date_debut,
    )
    if exclude_pk:
        conges_qs = conges_qs.exclude(pk=exclude_pk)
    nb_absent = conges_qs.values('employe').distinct().count()
    pct = round(nb_absent * 100 / nb_total)
    if pct >= SEUIL_CHEVAUCHEMENT:
        return {
            'pct': pct,
            'nb_absent': nb_absent,
            'nb_total': nb_total,
            'service': employe.service,
        }
    return None


def _can_validate_service(user, employe):
    """Vérifie si l'utilisateur peut valider au niveau service."""
    if can_manage_rh(user):
        return True
    if not employe.service:
        return False
    service = employe.service
    if not hasattr(service, 'chef_service') or service.chef_service is None:
        return False
    chef = service.chef_service
    if not hasattr(chef, 'user') or chef.user is None:
        return False
    return chef.user_id == user.pk


# ── Liste ─────────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_list(request):
    _auto_approuve_vers_en_cours()
    qs = Conge.objects.select_related('employe', 'approuve_par').order_by('-date_debut')

    today = _d.today()
    f_statut     = request.GET.get('statut', '').strip()
    f_type       = request.GET.get('type_conge', '').strip()
    f_employe    = request.GET.get('employe', '').strip()
    f_annee      = request.GET.get('annee', '').strip()
    f_date_debut = request.GET.get('date_debut', '').strip()
    f_date_fin   = request.GET.get('date_fin', '').strip()
    q            = request.GET.get('q', '').strip()

    if f_statut:
        qs = qs.filter(statut=f_statut)
    if f_type:
        qs = qs.filter(type_conge=f_type)
    if f_employe:
        qs = qs.filter(employe_id=f_employe)
    if f_annee:
        qs = qs.filter(date_debut__year=f_annee)
    if f_date_debut:
        try:
            qs = qs.filter(date_debut__gte=_d.fromisoformat(f_date_debut))
        except ValueError:
            pass
    if f_date_fin:
        try:
            qs = qs.filter(date_fin__lte=_d.fromisoformat(f_date_fin))
        except ValueError:
            pass
    if q:
        qs = qs.filter(
            Q(employe__nom__icontains=q) | Q(employe__prenoms__icontains=q)
        )

    stats = {
        'total':    Conge.objects.count(),
        'demande':  Conge.objects.filter(statut__in=['demande', 'valide_service']).count(),
        'a_venir':  Conge.objects.filter(statut='approuve').count(),
        'en_cours': Conge.objects.filter(statut='en_cours').count(),
        'termine':  Conge.objects.filter(statut='termine').count(),
    }

    # Années disponibles pour le filtre
    annees = list(
        Conge.objects.dates('date_debut', 'year', order='DESC')
        .values_list('date_debut__year', flat=True)
        .distinct()
    )

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'conges/list.html', {
        'nav_active': 'list',
        'page_obj':     page_obj,
        'stats':        stats,
        'employes':     _employes_eligibles().order_by('nom'),
        'types':        Conge.TYPE,
        'statuts':      Conge.STATUT,
        'annees':       annees,
        'f_statut':     f_statut,
        'f_type':       f_type,
        'f_employe':    f_employe,
        'f_annee':      f_annee,
        'f_date_debut': f_date_debut,
        'f_date_fin':   f_date_fin,
        'q':            q,
        'today':        today,
        'can_manage':   can_manage_rh(request.user),
    })


# ── Nouvelle demande ──────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_nouveau(request):
    employe_pk = request.GET.get('employe') or request.POST.get('employe')
    employe_pre = None
    if employe_pk:
        employe_pre = get_object_or_404(Employe, pk=employe_pk)

    conflits = []
    solde = None

    if request.method == 'POST':
        emp_id     = request.POST.get('employe', '').strip()
        type_conge = request.POST.get('type_conge', '').strip()
        date_debut = request.POST.get('date_debut', '').strip()
        date_fin   = request.POST.get('date_fin', '').strip()
        motif      = request.POST.get('motif', '').strip()

        errors = []
        if not emp_id:     errors.append("Veuillez sélectionner un employé.")
        if not type_conge: errors.append("Le type de congé est obligatoire.")
        if not date_debut: errors.append("La date de début est obligatoire.")
        if not date_fin:   errors.append("La date de fin est obligatoire.")

        if not errors:
            d1 = _d.fromisoformat(date_debut)
            d2 = _d.fromisoformat(date_fin)
            if d2 < d1:
                errors.append("La date de fin doit être après la date de début.")

        for e in errors:
            messages.error(request, e)

        if not errors:
            emp = get_object_or_404(Employe, pk=emp_id)
            if emp.type_contrat and not emp.type_contrat.droit_au_conge:
                messages.error(
                    request,
                    f"{emp.nom_complet} ({emp.type_contrat.nom}) n'a pas droit au congé "
                    f"selon le Code du travail ivoirien."
                )
            else:
                # La RH enregistre directement — statut basé sur les dates
                today = _d.today()
                if d2 < today:
                    statut_initial = 'termine'
                elif d1 <= today:
                    statut_initial = 'en_cours'
                else:
                    statut_initial = 'approuve'

                nb_ouvres = compter_jours_ouvres(d1, d2)

                # Alerte solde insuffisant
                if type_conge in TYPES_DEDUCTIBLES:
                    solde_obj = get_or_create_solde(emp, d1.year)
                    if solde_obj.solde < nb_ouvres:
                        messages.warning(
                            request,
                            f"Attention : solde insuffisant pour {emp.nom_complet} "
                            f"({solde_obj.solde}j restants / {nb_ouvres}j demandés)."
                        )

                c = Conge.objects.create(
                    employe=emp, type_conge=type_conge,
                    date_debut=d1, date_fin=d2,
                    motif=motif, statut=statut_initial,
                    nb_jours_ouvres=nb_ouvres,
                    approuve_par=request.user,
                    date_approbation=timezone.now(),
                )
                if c.type_conge in TYPES_DEDUCTIBLES:
                    get_or_create_solde(emp, d1.year)
                _create_presence_for_conge(c)
                _add_historique(c, 'enregistre', request.user,
                                f"Enregistré par RH — {c.get_type_conge_display()}")

                messages.success(
                    request,
                    f"Congé de {emp.nom_complet} enregistré "
                    f"({c.get_type_conge_display()}, {d1:%d/%m/%Y} → {d2:%d/%m/%Y}, "
                    f"{nb_ouvres}j ouvrés)."
                )
                return redirect('conge_detail', pk=c.pk)

    if employe_pre:
        solde = get_or_create_solde(employe_pre, _d.today().year)

    # Calcul solde en temps réel si données POST
    solde_alerte = None
    if request.method == 'POST' and not errors:
        pass  # déjà géré avec messages.warning ci-dessus

    return render(request, 'conges/form.html', {
        'nav_active': 'nouveau',
        'employes':              _employes_eligibles().order_by('nom'),
        'employes_json':         [
            {'pk': e.pk, 'nom': e.nom_complet,
             'mat': e.matricule,
             'svc': e.service.nom if e.service else '',
             'fn':  e.fonction.nom if e.fonction else ''}
            for e in _employes_eligibles().select_related('service','fonction').order_by('nom')
        ],
        'types':                 Conge.TYPE,
        'employe_pre':           employe_pre,
        'can_manage':            can_manage_rh(request.user),
        'conflits':              conflits,
        'solde':                 solde,
        'durees_exceptionnelles': DUREES_EXCEPTIONNELLES,
        'types_deductibles':     list(TYPES_DEDUCTIBLES),
        'post_data': {
            'type_conge': request.POST.get('type_conge', ''),
            'date_debut': request.POST.get('date_debut', ''),
            'date_fin':   request.POST.get('date_fin', ''),
            'motif':      request.POST.get('motif', ''),
        } if request.method == 'POST' else {},
    })


# ── AJAX : infos employé pour le formulaire ────────────────────────────────────
@login_required(login_url='login')
def conge_employe_info(request, emp_pk):
    """Retourne les infos d'un employé en JSON pour le formulaire de congé."""
    if not can_manage_rh(request.user):
        raise PermissionDenied
    emp = get_object_or_404(Employe.objects.select_related('service', 'fonction', 'grade'), pk=emp_pk)
    annee = _d.today().year
    solde = get_or_create_solde(emp, annee)
    # Congés en cours ou à venir
    conges_actifs = Conge.objects.filter(
        employe=emp, statut__in=['approuve', 'en_cours']
    ).order_by('date_debut').values('type_conge', 'date_debut', 'date_fin', 'nb_jours_ouvres')[:5]
    return JsonResponse({
        'pk':            emp.pk,
        'nom':           emp.nom_complet,
        'matricule':     emp.matricule,
        'service':       emp.service.nom if emp.service else '—',
        'fonction':      emp.fonction.nom if emp.fonction else '—',
        'photo':         emp.photo.url if emp.photo else None,
        'initiales':     emp.initiales or emp.nom[0].upper(),
        'solde_restant': float(solde.solde),
        'quota':         float(solde.quota),
        'jours_pris':    float(solde.jours_pris),
        'annee':         annee,
        'conges_actifs': list(conges_actifs),
    })


# ── Détail ────────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_detail(request, pk):
    _auto_approuve_vers_en_cours()
    conge = get_object_or_404(
        Conge.objects.select_related('employe__service', 'employe__fonction',
                                     'employe__grade', 'employe__type_contrat',
                                     'approuve_par', 'valide_par_service'),
        pk=pk
    )
    autres_conges = Conge.objects.filter(
        employe=conge.employe
    ).exclude(pk=pk).order_by('-date_demande')[:5]

    historique = conge.historique.select_related('fait_par').order_by('date')
    peut_valider_service = _can_validate_service(request.user, conge.employe)

    return render(request, 'conges/detail.html', {
        'nav_active': 'list',
        'conge':                conge,
        'autres_conges':        autres_conges,
        'can_manage':           can_manage_rh(request.user),
        'historique':           historique,
        'peut_valider_service': peut_valider_service,
        'today':                _d.today(),
    })








# ── Annuler ───────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_annuler(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(Conge, pk=pk)
    if request.method == 'POST' and conge.statut in ('approuve', 'en_cours'):
        motif_annulation = request.POST.get('motif_annulation', 'Annulé').strip()
        conge.statut = 'refuse'
        conge.commentaire_rh = motif_annulation
        conge.save()

        _add_historique(conge, 'annule', request.user, motif_annulation)
        _delete_presence_for_conge(conge)

        # Notifier l'employé
        emp_user = getattr(conge.employe, 'user', None)
        if emp_user:
            msg = (
                f"Votre congé ({conge.get_type_conge_display()} "
                f"du {conge.date_debut:%d/%m/%Y} au {conge.date_fin:%d/%m/%Y}) a été annulé."
                + (f" Motif : {motif_annulation}" if motif_annulation else "")
            )
            _send_notif([emp_user], conge, 'refuse', msg)

        messages.success(request, "Congé annulé.")
    return redirect('conge_list')


# ── Marquer en cours ──────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_marquer_en_cours(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(Conge, pk=pk)
    if request.method == 'POST' and conge.statut == 'approuve':
        conge.statut = 'en_cours'
        conge.save()
        _add_historique(conge, 'mis_en_cours', request.user)
        messages.success(request, "Congé marqué en cours.")
    return redirect('conge_detail', pk=pk)


# ── Terminer ──────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_terminer(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(Conge, pk=pk)
    if request.method == 'POST' and conge.statut == 'en_cours':
        conge.statut = 'termine'
        conge.save()
        _add_historique(conge, 'termine', request.user)
        messages.success(request, "Congé terminé.")
    return redirect('conge_detail', pk=pk)


# ── Prolongation de congé ─────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_prolonger(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(
        Conge.objects.select_related('employe__service', 'employe__type_contrat'), pk=pk
    )
    if conge.statut != 'en_cours':
        messages.error(request, "Seul un congé en cours peut être prolongé.")
        return redirect('conge_detail', pk=pk)

    if request.method == 'POST':
        nouvelle_fin_str = request.POST.get('nouvelle_date_fin', '').strip()
        motif = request.POST.get('motif', '').strip()
        errors = []
        if not nouvelle_fin_str:
            errors.append("La nouvelle date de fin est obligatoire.")
        if not errors:
            nouvelle_fin = _d.fromisoformat(nouvelle_fin_str)
            if nouvelle_fin <= conge.date_fin:
                errors.append("La nouvelle date de fin doit être postérieure à la date de fin actuelle.")
        for e in errors:
            messages.error(request, e)

        if not errors:
            ancienne_fin = conge.date_fin
            anciens_jours = conge.nb_jours_ouvres or 0
            nouveaux_jours = compter_jours_ouvres(conge.date_debut, nouvelle_fin)
            jours_supplementaires = nouveaux_jours - anciens_jours

            # Créer les présences pour la période supplémentaire
            feries = set()
            for y in range(ancienne_fin.year, nouvelle_fin.year + 1):
                feries |= jours_feries_ivoire(y)
            current = ancienne_fin + timedelta(days=1)
            motif_presence = f'Congé prolongé: {conge.get_type_conge_display()}'
            while current <= nouvelle_fin:
                if current.weekday() < 5 and current not in feries:
                    Presence.objects.get_or_create(
                        employe=conge.employe, date=current,
                        defaults={'present': False, 'motif_absence': motif_presence}
                    )
                current += timedelta(days=1)

            # Mettre à jour le congé
            conge.date_fin = nouvelle_fin
            conge.nb_jours_ouvres = nouveaux_jours
            conge.save(update_fields=['date_fin', 'nb_jours_ouvres'])

            # Mettre à jour le solde si déductible
            if conge.type_conge in TYPES_DEDUCTIBLES:
                solde = get_or_create_solde(conge.employe, conge.date_debut.year)
                from decimal import Decimal
                solde.jours_pris = Decimal(str(float(solde.jours_pris) + jours_supplementaires))
                solde.save(update_fields=['jours_pris'])

            _add_historique(
                conge, 'prolonge', request.user,
                f"Prolongé du {ancienne_fin:%d/%m/%Y} au {nouvelle_fin:%d/%m/%Y} "
                f"(+{jours_supplementaires} j ouvrés). {motif}"
            )
            messages.success(
                request,
                f"Congé prolongé jusqu'au {nouvelle_fin:%d/%m/%Y} "
                f"(+{jours_supplementaires} jour{'s' if jours_supplementaires > 1 else ''} ouvrés)."
            )
            return redirect('conge_detail', pk=pk)

    solde = get_or_create_solde(conge.employe, conge.date_debut.year)
    return render(request, 'conges/prolonger.html', {
        'nav_active': 'list',
        'conge':      conge,
        'solde':      solde,
        'can_manage': True,
    })


# ── Absence non justifiée ──────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_absence_injustifiee(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(
        Conge.objects.select_related('employe__service'), pk=pk
    )
    today = _d.today()
    if conge.statut != 'en_cours':
        messages.error(request, "Action applicable uniquement sur un congé en cours.")
        return redirect('conge_detail', pk=pk)
    if conge.date_fin >= today:
        messages.error(request, "Le congé n'est pas encore échu. Aucun dépassement à constater.")
        return redirect('conge_detail', pk=pk)

    # Jours de dépassement (date_fin exclue car déjà comptée, jusqu'à hier)
    date_retour_prevue = conge.date_fin + timedelta(days=1)
    hier = today - timedelta(days=1)
    jours_depasses = compter_jours_ouvres(date_retour_prevue, hier)

    if request.method == 'POST':
        motif = request.POST.get('motif', '').strip()
        action_choisie = request.POST.get('action', 'injustifiee')  # injustifiee | sans_solde

        # Créer les enregistrements de présence pour chaque jour dépassé
        feries = set()
        for y in (conge.date_fin.year, today.year):
            feries |= jours_feries_ivoire(y)
        current = date_retour_prevue
        libelle_motif = 'Absence non justifiée' if action_choisie == 'injustifiee' else 'Absence — congé sans solde'
        while current <= hier:
            if current.weekday() < 5 and current not in feries:
                Presence.objects.get_or_create(
                    employe=conge.employe, date=current,
                    defaults={'present': False, 'motif_absence': libelle_motif}
                )
            current += timedelta(days=1)

        # Si traitement "sans solde" : créer un congé sans solde pour les jours en trop
        if action_choisie == 'sans_solde' and jours_depasses > 0:
            Conge.objects.create(
                employe=conge.employe,
                type_conge='sans_solde',
                date_debut=date_retour_prevue,
                date_fin=hier,
                motif=f"Dépassement du congé #{conge.pk}. {motif}",
                statut='termine',
                nb_jours_ouvres=jours_depasses,
            )

        _add_historique(
            conge, 'absence_injustifiee', request.user,
            f"{jours_depasses} j ouvré(s) de dépassement "
            f"({date_retour_prevue:%d/%m/%Y}–{hier:%d/%m/%Y}). "
            f"Traitement : {'absence non justifiée' if action_choisie == 'injustifiee' else 'congé sans solde'}. "
            f"{motif}"
        )

        # Terminer le congé original
        conge.statut = 'termine'
        conge.save(update_fields=['statut'])
        _add_historique(conge, 'termine', request.user, 'Clôturé après constat de dépassement.')

        # Notifier l'employé par email
        emp_user = getattr(conge.employe, 'user', None)
        if emp_user:
            label_action = 'absence non justifiée' if action_choisie == 'injustifiee' else 'congé sans solde'
            msg_emp = (
                f"Suite au dépassement de votre congé (retour prévu le {date_retour_prevue:%d/%m/%Y}), "
                f"{jours_depasses} jour(s) ouvré(s) ont été constatés et traités "
                f"en {label_action}."
                + (f"\nMotif indiqué : {motif}" if motif else "")
            )
            _send_notif([emp_user], conge, 'refuse', msg_emp)

        # Notifier les RH
        label_action = 'absence non justifiée' if action_choisie == 'injustifiee' else 'congé sans solde'
        msg_rh = (
            f"Dépassement traité pour {conge.employe.nom_complet} : "
            f"{jours_depasses} j ouvré(s) du {date_retour_prevue:%d/%m/%Y} au {hier:%d/%m/%Y} "
            f"— {label_action}."
        )
        _send_email(_rh_users(), f"[CMS WALÉ] Dépassement congé — {conge.employe.nom_complet}", msg_rh)

        messages.success(
            request,
            f"{jours_depasses} jour(s) de dépassement constaté(s) et traité(s) "
            f"({label_action}). L'employé a été notifié."
        )
        return redirect('conge_detail', pk=pk)

    return render(request, 'conges/absence_injustifiee.html', {
        'nav_active': 'list',
        'conge':              conge,
        'today':              today,
        'date_retour_prevue': date_retour_prevue,
        'hier':               hier,
        'jours_depasses':     jours_depasses,
        'can_manage':         True,
    })


# ── Attestation de congé ──────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_attestation(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(
        Conge.objects.select_related(
            'employe__service', 'employe__fonction', 'employe__type_contrat', 'approuve_par'
        ),
        pk=pk,
    )
    return render(request, 'conges/attestation_conge.html', {
        'conge':    conge,
        'today':    _d.today(),
        'can_manage': True,
    })


# ── Fractionner un congé (Art. 25.7 CODI) ────────────────────────────────────
@login_required(login_url='login')
def conge_fractionner(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    conge = get_object_or_404(
        Conge.objects.select_related('employe__service'), pk=pk
    )
    if conge.type_conge != 'annuel':
        messages.error(request, "Seul le congé annuel peut être fractionné (Art. 25.7 CODI).")
        return redirect('conge_detail', pk=pk)
    if conge.conge_parent_id:
        messages.error(request, "Ce congé est déjà un fragment d'un congé parent.")
        return redirect('conge_detail', pk=pk)
    if conge.statut != 'approuve':
        messages.error(request, "Seul un congé à venir (non encore démarré) peut être fractionné.")
        return redirect('conge_detail', pk=pk)

    fragments_existants = conge.fragments.all()
    if fragments_existants.exists():
        messages.warning(request, "Ce congé est déjà fractionné. Supprimez le fragment existant avant d'en créer un nouveau.")
        return redirect('conge_detail', pk=pk)

    if request.method == 'POST':
        date_debut2 = request.POST.get('date_debut2', '').strip()
        date_fin2   = request.POST.get('date_fin2', '').strip()
        errors = []
        if not date_debut2: errors.append("La date de début de la 2e période est obligatoire.")
        if not date_fin2:   errors.append("La date de fin de la 2e période est obligatoire.")

        if not errors:
            d1 = _d.fromisoformat(date_debut2)
            d2 = _d.fromisoformat(date_fin2)
            if d2 < d1:
                errors.append("La date de fin doit être postérieure à la date de début.")
            # Pas de chevauchement avec la 1ère période
            if not (d2 < conge.date_debut or d1 > conge.date_fin):
                errors.append(
                    f"La 2e période ({d1:%d/%m/%Y}–{d2:%d/%m/%Y}) chevauche "
                    f"la 1ère ({conge.date_debut:%d/%m/%Y}–{conge.date_fin:%d/%m/%Y})."
                )

        for e in errors:
            messages.error(request, e)

        if not errors:
            nb_ouvres = compter_jours_ouvres(d1, d2)
            fragment = Conge.objects.create(
                employe=conge.employe,
                type_conge='annuel',
                date_debut=d1,
                date_fin=d2,
                motif=f"2e période — congé fractionné (réf. #{conge.pk})",
                statut='approuve',
                nb_jours_ouvres=nb_ouvres,
                conge_parent=conge,
                approuve_par=request.user,
                date_approbation=timezone.now(),
            )
            if fragment.type_conge in TYPES_DEDUCTIBLES:
                get_or_create_solde(fragment.employe, d1.year)
            _create_presence_for_conge(fragment)
            _add_historique(fragment, 'approuve', request.user,
                            f"Fragment 2/2 du congé #{conge.pk} (fractionné Art. 25.7 CODI)")
            _add_historique(conge, 'approuve', request.user,
                            f"Congé fractionné en 2 périodes — 2e période : #{fragment.pk}")
            messages.success(
                request,
                f"Congé fractionné. 2e période créée ({nb_ouvres} j ouvrés) du {d1:%d/%m/%Y} au {d2:%d/%m/%Y}."
            )
            return redirect('conge_detail', pk=conge.pk)

    solde = get_or_create_solde(conge.employe, conge.date_debut.year)
    return render(request, 'conges/fractionner.html', {
        'nav_active': 'nouveau',
        'conge':      conge,
        'solde':      solde,
        'can_manage': True,
    })


# ── Alertes anniversaires embauche ───────────────────────────────────────────
def _conges_a_venir(horizon_jours=60):
    """
    Retourne les employés éligibles dont l'anniversaire d'embauche tombe
    dans les `horizon_jours` prochains jours (droit à congé annuel à venir).
    """
    today = _d.today()
    limite = today + timedelta(days=horizon_jours)
    alertes = []

    for emp in _employes_eligibles().select_related('service'):
        if not emp.date_embauche:
            continue
        hire = emp.date_embauche
        if isinstance(hire, str):
            hire = _d.fromisoformat(hire)

        for year in (today.year, today.year + 1):
            try:
                ann = hire.replace(year=year)
            except ValueError:
                ann = hire.replace(year=year, day=28)
            if today <= ann <= limite:
                conge_existant = Conge.objects.filter(
                    employe=emp,
                    type_conge='annuel',
                    statut__in=['approuve', 'en_cours'],
                    date_debut__year=ann.year,
                ).first()
                alertes.append({
                    'employe':           emp,
                    'date_anniversaire': ann,
                    'jours_restants':    (ann - today).days,
                    'quota':             quota_annuel(emp),
                    'annees':            emp.anciennete['annees'] + (1 if ann.year > today.year else 0),
                    'conge_existant':    conge_existant,
                })
                break

    alertes.sort(key=lambda x: x['jours_restants'])
    return alertes


# ── Historique congés d'un employé (RH) ───────────────────────────────────────
@login_required(login_url='login')
def conge_historique_employe(request, emp_pk):
    """Historique complet des congés d'un employé — vue RH."""
    if not can_manage_rh(request.user):
        raise PermissionDenied

    employe = get_object_or_404(
        Employe.objects.select_related('service', 'fonction', 'grade'), pk=emp_pk
    )
    today = _d.today()

    conges = (
        Conge.objects.filter(employe=employe)
        .order_by('-date_debut')
        .select_related('approuve_par')
    )

    # Filtres
    f_annee = request.GET.get('annee', '').strip()
    f_type  = request.GET.get('type_conge', '').strip()
    if f_annee:
        conges = conges.filter(date_debut__year=f_annee)
    if f_type:
        conges = conges.filter(type_conge=f_type)

    # Stats globales
    total_jours = sum(c.nb_jours_ouvres or 0 for c in conges)
    nb_conges   = conges.count()
    solde       = get_or_create_solde(employe, today.year)

    # Années disponibles
    annees = list(
        Conge.objects.filter(employe=employe)
        .dates('date_debut', 'year', order='DESC')
        .values_list('date_debut__year', flat=True)
        .distinct()
    )

    paginator = Paginator(conges, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'conges/historique_employe.html', {
        'nav_active':   'list',
        'employe':      employe,
        'page_obj':     page_obj,
        'total_jours':  total_jours,
        'nb_conges':    nb_conges,
        'solde':        solde,
        'annees':       annees,
        'f_annee':      f_annee,
        'f_type':       f_type,
        'types':        Conge.TYPE,
        'today':        today,
        'can_manage':   True,
    })


# ── Suivi des retours ─────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_suivi_retours(request):
    """Vue RH : suivi des retours de congé — en cours, à venir, en retard."""
    if not can_manage_rh(request.user):
        raise PermissionDenied

    _auto_approuve_vers_en_cours()
    today = _d.today()

    # Congés actuellement en cours
    en_cours = Conge.objects.filter(
        statut='en_cours',
        date_debut__lte=today,
        date_fin__gte=today,
    ).select_related('employe__service', 'employe__fonction').order_by('date_fin')

    # Retours prévus dans les 7 prochains jours
    dans_7j = Conge.objects.filter(
        statut='en_cours',
        date_fin__gt=today,
        date_fin__lte=today + timedelta(days=7),
    ).select_related('employe__service').order_by('date_fin')

    # Retour aujourd'hui
    retour_aujd = Conge.objects.filter(
        statut='en_cours',
        date_fin=today,
    ).select_related('employe__service').order_by('employe__nom')

    # Congés en retard (date_fin dépassée, encore en_cours)
    en_retard = Conge.objects.filter(
        statut='en_cours',
        date_fin__lt=today,
    ).select_related('employe__service').order_by('date_fin')

    # Annotate : jours de retard
    for c in en_retard:
        c.jours_retard = (today - c.date_fin).days

    # Congés qui démarrent dans les 7 prochains jours (à venir)
    a_venir_proche = Conge.objects.filter(
        statut='approuve',
        date_debut__gt=today,
        date_debut__lte=today + timedelta(days=7),
    ).select_related('employe__service').order_by('date_debut')

    return render(request, 'conges/suivi_retours.html', {
        'nav_active':      'retours',
        'today':           today,
        'en_cours':        en_cours,
        'dans_7j':         dans_7j,
        'retour_aujd':     retour_aujd,
        'en_retard':       en_retard,
        'a_venir_proche':  a_venir_proche,
        'nb_retard':       en_retard.count(),
        'can_manage':      True,
    })


# ── Dashboard ─────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_dashboard(request):
    _auto_approuve_vers_en_cours()
    today = _d.today()
    annee = today.year

    a_venir     = Conge.objects.filter(statut='approuve').count()
    en_cours    = Conge.objects.filter(statut='en_cours').count()
    ce_mois     = Conge.objects.filter(
        Q(date_debut__year=today.year, date_debut__month=today.month) |
        Q(date_fin__year=today.year, date_fin__month=today.month)
    ).count()
    total_jours = Conge.objects.filter(
        statut__in=['approuve', 'en_cours', 'termine'],
        date_debut__year=annee,
    ).aggregate(total=Sum('nb_jours_ouvres'))['total'] or 0

    conges_aujourd_hui = Conge.objects.filter(
        date_debut__lte=today,
        date_fin__gte=today,
        statut__in=['approuve', 'en_cours'],
    ).select_related('employe')

    # Congés débutant dans les 7 prochains jours
    dans_7j = Conge.objects.filter(
        statut='approuve',
        date_debut__gt=today,
        date_debut__lte=today + timedelta(days=7),
    ).order_by('date_debut').select_related('employe')

    prochains_conges = Conge.objects.filter(
        statut__in=['approuve', 'en_cours'],
        date_debut__lte=today + timedelta(days=30),
        date_fin__gte=today,
    ).order_by('date_debut').select_related('employe')[:10]

    from collections import Counter
    type_qs = Conge.objects.filter(
        statut__in=['approuve', 'en_cours', 'termine'],
        date_debut__year=annee,
    ).values_list('type_conge', flat=True)
    type_counts = Counter(type_qs)
    total_types = sum(type_counts.values()) or 1
    type_labels = dict(Conge.TYPE)
    repartition = [
        (type_labels.get(code, code), count, round(count * 100 / total_types))
        for code, count in type_counts.most_common()
    ]

    # Retards (en_cours avec date_fin dépassée)
    en_retard_db = Conge.objects.filter(statut='en_cours', date_fin__lt=today).select_related('employe')
    for c in en_retard_db:
        c.jours_retard = (today - c.date_fin).days

    nb_termine = Conge.objects.filter(statut='termine', date_debut__year=annee).count()

    return render(request, 'conges/dashboard.html', {
        'nav_active': 'dashboard',
        'a_venir':             a_venir,
        'en_cours':            en_cours,
        'ce_mois':             ce_mois,
        'total_jours_annee':   total_jours,
        'nb_termine':          nb_termine,
        'conges_aujourd_hui':  conges_aujourd_hui,
        'prochains_conges':    prochains_conges,
        'repartition':         repartition,
        'conges_a_venir':      _conges_a_venir(60),
        'dans_7j':             dans_7j,
        'nb_dans_7j':          dans_7j.count(),
        'en_retard':           en_retard_db,
        'can_manage':          can_manage_rh(request.user),
        'annee':               annee,
        'today':               today,
    })


# ── Calendrier ────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_calendrier(request):
    today = _d.today()
    vue   = request.GET.get('vue', 'mois')  # jour | semaine | mois | annee
    try:
        year = int(request.GET.get('year', today.year))
        mois = int(request.GET.get('mois', today.month))
    except (ValueError, TypeError):
        year, mois = today.year, today.month

    # Date sélectionnée pour vue jour/semaine
    try:
        date_str = request.GET.get('date', today.isoformat())
        date_sel = _d.fromisoformat(date_str)
    except (ValueError, TypeError):
        date_sel = today

    # Semaine de date_sel
    sem_debut = date_sel - timedelta(days=date_sel.weekday())
    sem_fin   = sem_debut + timedelta(days=6)

    first_day = _d(year, mois, 1)
    last_day_num = calendar.monthrange(year, mois)[1]
    last_day = _d(year, mois, last_day_num)

    conges_mois = Conge.objects.filter(
        date_debut__lte=last_day,
        date_fin__gte=first_day,
    ).select_related('employe')

    feries_set  = jours_feries_ivoire(year)
    feries_dict = jours_feries_labels(year)

    type_colors = {
        'annuel':           'green',
        'maladie':          'amber',
        'maternite':        'pink',
        'paternite':        'pink',
        'mariage_employe':  'blue',
        'mariage_enfant':   'blue',
        'deces_conjoint':   'gray',
        'deces_enfant':     'gray',
        'deces_parent':     'gray',
        'deces_frere_soeur':'gray',
        'naissance_enfant': 'blue',
        'exceptionnel':     'blue',
        'sans_solde':       'gray',
    }

    cal_weeks = calendar.monthcalendar(year, mois)
    weeks = []
    for week in cal_weeks:
        week_days = []
        for i, day_num in enumerate(week):
            if day_num == 0:
                week_days.append({
                    'day': 0, 'date': None, 'conges': [],
                    'ferie': None, 'today': False, 'in_month': False,
                    'weekend': i >= 5,
                })
            else:
                d = _d(year, mois, day_num)
                day_conges = []
                for c in conges_mois:
                    if c.date_debut <= d <= c.date_fin:
                        day_conges.append({
                            'conge': c,
                            'color': type_colors.get(c.type_conge, 'blue'),
                        })
                ferie_label = feries_dict.get(d)
                week_days.append({
                    'day':      day_num,
                    'date':     d,
                    'conges':   day_conges,
                    'ferie':    ferie_label,
                    'today':    d == today,
                    'in_month': True,
                    'weekend':  i >= 5,
                })
        weeks.append(week_days)

    if mois == 1:
        prev_year, prev_mois = year - 1, 12
    else:
        prev_year, prev_mois = year, mois - 1
    if mois == 12:
        next_year, next_mois = year + 1, 1
    else:
        next_year, next_mois = year, mois + 1

    # ── Données vue SEMAINE ──
    semaine_days = []
    if vue == 'semaine':
        for i in range(7):
            d = sem_debut + timedelta(days=i)
            day_feries = jours_feries_labels(d.year)
            d_conges = [
                {'conge': c, 'color': type_colors.get(c.type_conge, 'blue')}
                for c in Conge.objects.filter(
                    date_debut__lte=d, date_fin__gte=d,
                    statut__in=['approuve', 'en_cours', 'termine']
                ).select_related('employe')
            ]
            semaine_days.append({
                'date': d, 'conges': d_conges,
                'ferie': day_feries.get(d),
                'today': d == today, 'weekend': i >= 5,
            })

    # ── Données vue JOUR ──
    jour_conges = []
    jour_ferie_label = ''
    if vue == 'jour':
        jour_feries = jours_feries_labels(date_sel.year)
        jour_ferie_label = jour_feries.get(date_sel, '')
        jour_conges = list(Conge.objects.filter(
            date_debut__lte=date_sel, date_fin__gte=date_sel,
            statut__in=['approuve', 'en_cours', 'termine']
        ).select_related('employe__service', 'employe__fonction'))

    # ── Données vue ANNÉE ──
    annee_months = []
    if vue == 'annee':
        feries_annee = jours_feries_ivoire(year)
        all_conges_annee = list(Conge.objects.filter(
            date_debut__year=year,
            statut__in=['approuve', 'en_cours', 'termine']
        ).values_list('date_debut', 'date_fin'))
        # Pour chaque mois : nb de jours avec congés
        for m in range(1, 13):
            ld = calendar.monthrange(year, m)[1]
            nb_jours_conge = 0
            for day in range(1, ld + 1):
                d = _d(year, m, day)
                if any(c[0] <= d <= c[1] for c in all_conges_annee):
                    nb_jours_conge += 1
            annee_months.append({
                'num': m, 'nom': _MOIS_FR[m],
                'nb_jours': nb_jours_conge,
                'total_jours': ld,
            })

    return render(request, 'conges/calendrier.html', {
        'nav_active':          'calendrier',
        'vue':                 vue,
        'year':                year,
        'mois':                mois,
        'nom_mois':            _MOIS_FR[mois],
        'weeks':               weeks,
        'prev_year':           prev_year,
        'prev_mois':           prev_mois,
        'next_year':           next_year,
        'next_mois':           next_mois,
        'jours_feries_labels': feries_dict,
        'feries_set':          feries_set,
        'today':               today,
        'date_sel':            date_sel,
        'sem_debut':           sem_debut,
        'sem_fin':             sem_fin,
        'semaine_days':        semaine_days,
        'jour_conges':         jour_conges,
        'jour_ferie_label':    jour_ferie_label,
        'annee_months':        annee_months,
        'can_manage':          can_manage_rh(request.user),
        'MOIS_FR':             _MOIS_FR,
    })




# ── Soldes ────────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_soldes(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = _d.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    employes = _employes_eligibles().select_related('service').order_by('nom')

    soldes_data = []
    with transaction.atomic():
        for emp in employes:
            s = get_or_create_solde(emp, year)
            # Solde prévisionnel : quota + reportés - total congés planifiés/pris/en cours cette année
            total_planifie = Conge.objects.filter(
                employe=emp,
                statut__in=['demande', 'valide_service', 'approuve', 'en_cours', 'termine'],
                date_debut__year=year,
                type_conge__in=TYPES_DEDUCTIBLES,
            ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
            previsionnel = round(float(s.quota) + float(s.jours_reporter) - float(total_planifie), 1)
            soldes_data.append({'solde': s, 'previsionnel': previsionnel})

    total_quota = sum(float(d['solde'].quota) for d in soldes_data)
    total_pris  = sum(float(d['solde'].jours_pris) for d in soldes_data)
    total_solde = sum(d['solde'].solde for d in soldes_data)

    return render(request, 'conges/soldes.html', {
        'nav_active': 'soldes',
        'soldes_data':  soldes_data,
        'year':         year,
        'annee_prev':   year - 1,
        'annee_next':   year + 1,
        'can_manage':   True,
        'total_quota':  total_quota,
        'total_pris':   total_pris,
        'total_solde':  total_solde,
    })


# ── Recalcul des soldes ───────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_solde_recalc(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        try:
            year = int(request.POST.get('year', _d.today().year))
        except (ValueError, TypeError):
            year = _d.today().year

        employes = _employes_eligibles()
        count = 0
        with transaction.atomic():
            for emp in employes:
                solde, _ = SoldeConge.objects.get_or_create(
                    employe=emp, annee=year,
                    defaults={'quota': quota_annuel(emp)},
                )
                solde.quota = quota_annuel(emp)
                total = Conge.objects.filter(
                    employe=emp,
                    statut__in=['approuve', 'en_cours', 'termine'],
                    date_debut__year=year,
                    type_conge__in=TYPES_DEDUCTIBLES,
                ).aggregate(total=Sum('nb_jours_ouvres'))['total'] or 0
                solde.jours_pris = total
                solde.save()
                count += 1

        messages.success(request, f"Soldes recalculés pour {count} employé(s) — année {year}.")
        from django.urls import reverse
        return redirect(reverse('conge_soldes') + f'?year={year}')
    return redirect('conge_soldes')


# ── Report annuel des soldes ──────────────────────────────────────────────────
@login_required(login_url='login')
def conge_report_solde_annuel(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        try:
            year = int(request.POST.get('year', _d.today().year))
        except (ValueError, TypeError):
            year = _d.today().year
        next_year = year + 1
        employes = _employes_eligibles()
        count = 0
        with transaction.atomic():
            for emp in employes:
                # Récupérer ou créer le solde de l'année N
                solde_n = get_or_create_solde(emp, year)
                restant = solde_n.solde  # quota + reporter - pris
                if restant <= 0:
                    continue
                # Plafonner à 15 jours selon Art. 25.10 CODI
                reportable = min(float(restant), 15.0)
                # Mettre à jour le solde N+1
                solde_n1, _ = SoldeConge.objects.get_or_create(
                    employe=emp, annee=next_year,
                    defaults={'quota': quota_annuel(emp)},
                )
                solde_n1.jours_reporter = float(solde_n1.jours_reporter) + reportable
                solde_n1.save(update_fields=['jours_reporter', 'mis_a_jour_le'])
                count += 1

        messages.success(
            request,
            f"Report effectué pour {count} employé(s) : soldes de {year} → {next_year} "
            f"(max 15 jours/employé selon Art. 25.10 CODI)."
        )
        from django.urls import reverse
        return redirect(reverse('conge_soldes') + f'?year={next_year}')
    return redirect('conge_soldes')


# ── Bon de congé ──────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_bon(request, pk):
    conge = get_object_or_404(
        Conge.objects.select_related('employe', 'approuve_par'), pk=pk
    )
    return render(request, 'conges/bon_conge.html', {
        'conge': conge,
        'today': _d.today(),
    })


# ── Export CSV ────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_export_csv(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    qs = Conge.objects.select_related('employe__service', 'approuve_par')

    f_statut  = request.GET.get('statut', '').strip()
    f_type    = request.GET.get('type_conge', '').strip()
    f_employe = request.GET.get('employe', '').strip()
    q         = request.GET.get('q', '').strip()

    if f_statut:
        qs = qs.filter(statut=f_statut)
    if f_type:
        qs = qs.filter(type_conge=f_type)
    if f_employe:
        qs = qs.filter(employe_id=f_employe)
    if q:
        qs = qs.filter(
            Q(employe__nom__icontains=q) | Q(employe__prenoms__icontains=q)
        )

    from core.utils import csv_response
    headers = [
        'Matricule', 'Nom', 'Prénom', 'Service',
        'Type', 'Date début', 'Date fin',
        'Jours calendaires', 'Jours ouvrés',
        'Statut', 'Demandé le', 'Approuvé par',
    ]
    rows = [
        [
            c.employe.matricule,
            c.employe.nom,
            c.employe.prenoms,
            c.employe.service.nom if c.employe.service else '',
            c.get_type_conge_display(),
            c.date_debut.strftime('%d/%m/%Y'),
            c.date_fin.strftime('%d/%m/%Y'),
            c.duree,
            c.nb_jours_ouvres,
            c.get_statut_display(),
            c.date_demande.strftime('%d/%m/%Y'),
            str(c.approuve_par) if c.approuve_par else '',
        ]
        for c in qs
    ]
    return csv_response('conges_export', headers, rows)


# ── Statistiques par service ──────────────────────────────────────────────────
@login_required(login_url='login')
def conge_stats_service(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = _d.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    from medecins.models import Service

    services = Service.objects.prefetch_related('employes').order_by('nom')

    # Jours ouvrables dans l'année (approximation : 52 semaines * 5 jours - fériés)
    feries_year = jours_feries_ivoire(year)
    total_jours_ouvres_annee = 0
    d = _d(year, 1, 1)
    while d.year == year:
        if d.weekday() < 5 and d not in feries_year:
            total_jours_ouvres_annee += 1
        d += timedelta(days=1)

    stats_services = []
    for service in services:
        employes_service = service.employes.filter(statut='actif')
        nb_employes = employes_service.count()
        if nb_employes == 0:
            continue
        conges_service = Conge.objects.filter(
            employe__service=service,
            statut__in=['approuve', 'en_cours', 'termine'],
            date_debut__year=year,
        )
        nb_conges   = conges_service.count()
        total_jours = conges_service.aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
        # Taux absentéisme = jours_conge / (nb_employes * jours_ouvrables) * 100
        capacite = nb_employes * total_jours_ouvres_annee
        taux = round(float(total_jours) / capacite * 100, 1) if capacite else 0
        stats_services.append({
            'service':       service,
            'nb_employes':   nb_employes,
            'nb_conges':     nb_conges,
            'total_jours':   total_jours,
            'taux':          taux,
        })

    # Répartition mensuelle
    repartition_mensuelle = []
    for m in range(1, 13):
        nb = Conge.objects.filter(
            statut__in=['approuve', 'en_cours', 'termine'],
            date_debut__year=year,
            date_debut__month=m,
        ).count()
        repartition_mensuelle.append({'mois': _MOIS_FR[m], 'nb': nb})

    max_mois = max((r['nb'] for r in repartition_mensuelle), default=1) or 1

    total_conges        = sum(s['nb_conges'] for s in stats_services)
    services_alerte_nb  = sum(1 for s in stats_services if s['taux'] > 15)

    return render(request, 'conges/stats_service.html', {
        'nav_active': 'stats',
        'stats_services':       stats_services,
        'year':                 year,
        'annee_prev':           year - 1,
        'annee_next':           year + 1,
        'repartition_mensuelle': repartition_mensuelle,
        'max_mois':             max_mois,
        'total_conges':         total_conges,
        'services_alerte_nb':   services_alerte_nb,
        'can_manage':           True,
    })


# ── Planning équipe ───────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_planning_equipe(request):
    today = _d.today()
    try:
        year = int(request.GET.get('year', today.year))
        mois = int(request.GET.get('mois', today.month))
    except (ValueError, TypeError):
        year, mois = today.year, today.month

    from medecins.models import Service

    services    = Service.objects.order_by('nom')
    service_id  = request.GET.get('service', '')
    service_sel = None
    if service_id:
        try:
            service_sel = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            pass

    # Employés du service sélectionné (ou tous)
    if service_sel:
        employes_qs = Employe.objects.filter(statut='actif', service=service_sel).order_by('nom')
    else:
        employes_qs = Employe.objects.filter(statut='actif').order_by('nom')[:50]

    last_day_num = calendar.monthrange(year, mois)[1]
    first_day    = _d(year, mois, 1)
    last_day     = _d(year, mois, last_day_num)

    feries = jours_feries_ivoire(year)

    # Jours du mois avec métadonnées
    days = []
    for day_num in range(1, last_day_num + 1):
        d = _d(year, mois, day_num)
        days.append({
            'num':      day_num,
            'date':     d,
            'weekend':  d.weekday() >= 5,
            'ferie':    d in feries,
            'today':    d == today,
        })

    # Congés du mois
    conges_mois = Conge.objects.filter(
        employe__in=employes_qs,
        date_debut__lte=last_day,
        date_fin__gte=first_day,
        statut__in=['approuve', 'en_cours', 'termine'],
    ).select_related('employe')

    # Index: employe_id -> liste de dates en congé
    conge_index = {}
    for c in conges_mois:
        emp_id = c.employe_id
        if emp_id not in conge_index:
            conge_index[emp_id] = {}
        cur = max(c.date_debut, first_day)
        end = min(c.date_fin, last_day)
        while cur <= end:
            conge_index[emp_id][cur.day] = (c.get_type_conge_display(), c.type_conge)
            cur += timedelta(days=1)

    planning_grid = []
    for emp in employes_qs:
        row = {'employe': emp, 'cells': []}
        emp_conges = conge_index.get(emp.pk, {})
        for day in days:
            if day['weekend'] or day['ferie']:
                row['cells'].append({'type': 'non_ouvre', 'label': ''})
            elif day['num'] in emp_conges:
                row['cells'].append({'type': 'conge', 'label': emp_conges[day['num']][0], 'type_code': emp_conges[day['num']][1]})
            else:
                row['cells'].append({'type': 'present', 'label': ''})
        planning_grid.append(row)

    if mois == 1:
        prev_year, prev_mois = year - 1, 12
    else:
        prev_year, prev_mois = year, mois - 1
    if mois == 12:
        next_year, next_mois = year + 1, 1
    else:
        next_year, next_mois = year, mois + 1

    # Totaux par jour (nb employés en congé) — liste indexée sur les jours
    absences_par_jour_list = [0] * len(days)
    for row in planning_grid:
        for i, cell in enumerate(row['cells']):
            if cell['type'] == 'conge':
                absences_par_jour_list[i] += 1

    # Marquer today_col sur chaque cellule
    for row in planning_grid:
        for i, cell in enumerate(row['cells']):
            cell['today'] = days[i]['today']
            cell['weekend'] = days[i]['weekend']
            cell['ferie'] = days[i]['ferie']

    # Totaux par employé (nb jours congé dans le mois)
    for row in planning_grid:
        row['nb_conge'] = sum(1 for c in row['cells'] if c['type'] == 'conge')

    nb_employes = len(planning_grid)

    return render(request, 'conges/planning_equipe.html', {
        'nav_active':         'planning',
        'services':           services,
        'service_sel':        service_sel,
        'planning_grid':      planning_grid,
        'days':               days,
        'year':               year,
        'mois':               mois,
        'nom_mois':           _MOIS_FR[mois],
        'prev_year':          prev_year,
        'prev_mois':          prev_mois,
        'next_year':          next_year,
        'next_mois':          next_mois,
        'absences_par_jour':  absences_par_jour_list,
        'nb_employes':        nb_employes,
        'can_manage':         can_manage_rh(request.user),
    })


# ── Rapport ───────────────────────────────────────────────────────────────────
@login_required(login_url='login')
def conge_rapport(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = _d.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    mois_param = request.GET.get('mois', '')
    mois = None
    if mois_param:
        try:
            mois = int(mois_param)
        except ValueError:
            pass

    service_id = request.GET.get('service', '')

    from medecins.models import Service
    services   = Service.objects.order_by('nom')
    service_sel = None
    if service_id:
        try:
            service_sel = Service.objects.get(pk=service_id)
        except Service.DoesNotExist:
            pass

    qs = Conge.objects.filter(
        statut__in=['approuve', 'en_cours', 'termine'],
        date_debut__year=year,
    ).select_related('employe__service')

    if mois:
        qs = qs.filter(date_debut__month=mois)
    if service_sel:
        qs = qs.filter(employe__service=service_sel)

    # Export CSV du rapport
    if request.GET.get('export') == 'csv':
        from core.utils import csv_response
        headers = ['Employé', 'Matricule', 'Service', 'Type', 'Début', 'Fin', 'Jours ouvrés', 'Statut']
        rows = [
            [
                c.employe.nom_complet,
                c.employe.matricule,
                c.employe.service.nom if c.employe.service else '',
                c.get_type_conge_display(),
                c.date_debut.strftime('%d/%m/%Y'),
                c.date_fin.strftime('%d/%m/%Y'),
                c.nb_jours_ouvres,
                c.get_statut_display(),
            ]
            for c in qs
        ]
        return csv_response(f'rapport_conges_{year}', headers, rows)

    # Statistiques par type
    from collections import defaultdict
    par_type = defaultdict(lambda: {'nb': 0, 'jours': 0})
    for c in qs:
        par_type[c.type_conge]['nb'] += 1
        par_type[c.type_conge]['jours'] += c.nb_jours_ouvres

    type_labels = dict(Conge.TYPE)
    stats_type = [
        {
            'type_code':  code,
            'type_label': type_labels.get(code, code),
            'nb':         vals['nb'],
            'jours':      vals['jours'],
        }
        for code, vals in sorted(par_type.items(), key=lambda x: -x[1]['jours'])
    ]

    # Statistiques par service
    par_service = defaultdict(lambda: {'nb': 0, 'jours': 0, 'employes': set()})
    for c in qs:
        svc = c.employe.service.nom if c.employe.service else '—'
        par_service[svc]['nb'] += 1
        par_service[svc]['jours'] += c.nb_jours_ouvres
        par_service[svc]['employes'].add(c.employe_id)

    stats_service_list = [
        {
            'service':    svc,
            'nb':         vals['nb'],
            'jours':      vals['jours'],
            'nb_employes': len(vals['employes']),
        }
        for svc, vals in sorted(par_service.items(), key=lambda x: -x[1]['jours'])
    ]

    # Top 10 absences
    emp_jours = defaultdict(lambda: {'emp': None, 'jours': 0, 'nb': 0})
    for c in qs:
        emp_jours[c.employe_id]['emp'] = c.employe
        emp_jours[c.employe_id]['jours'] += c.nb_jours_ouvres
        emp_jours[c.employe_id]['nb'] += 1

    top_absences = sorted(emp_jours.values(), key=lambda x: -x['jours'])[:10]

    # Répartition mensuelle
    par_mois = defaultdict(lambda: {'nb': 0, 'jours': 0})
    for c in qs:
        par_mois[c.date_debut.month]['nb'] += 1
        par_mois[c.date_debut.month]['jours'] += c.nb_jours_ouvres

    repartition_mensuelle = []
    for m in range(1, 13):
        repartition_mensuelle.append({
            'mois_num': m,
            'mois':     _MOIS_FR[m],
            'nb':       par_mois[m]['nb'],
            'jours':    par_mois[m]['jours'],
        })

    total_jours = sum(v['jours'] for v in par_type.values())
    total_conges = sum(v['nb'] for v in par_type.values())

    # Données JSON pour les graphes
    chart_type = {
        'labels': [t['type_label'] for t in stats_type],
        'data':   [t['jours'] for t in stats_type],
        'colors': ['#4a7236','#2d99db','#e89a1a','#e84545','#9e9e9e',
                   '#e91e8c','#6c757d','#16a96b','#673ab7','#ff5722'],
    }
    chart_mensuel = {
        'labels': [_MOIS_FR[m] for m in range(1, 13)],
        'data':   [next((rm['jours'] for rm in repartition_mensuelle if rm['mois_num'] == m), 0) for m in range(1, 13)],
    }
    chart_service = {
        'labels': [s['service'] for s in stats_service_list[:8]],
        'data':   [s['jours'] for s in stats_service_list[:8]],
    }

    return render(request, 'conges/rapport.html', {
        'nav_active': 'rapport',
        'year':                  year,
        'mois':                  mois,
        'nom_mois':              _MOIS_FR[mois] if mois else None,
        'service_sel':           service_sel,
        'services':              services,
        'stats_type':            stats_type,
        'stats_service_list':    stats_service_list,
        'top_absences':          top_absences,
        'repartition_mensuelle': repartition_mensuelle,
        'total_jours':           total_jours,
        'total_conges':          total_conges,
        'chart_type':            chart_type,
        'chart_mensuel':         chart_mensuel,
        'chart_service':         chart_service,
        'can_manage':            True,
        'today':                 today,
    })


# ── Tableau de bord Direction ─────────────────────────────────────────────────
@login_required(login_url='login')
def conge_direction(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = _d.today()
    try:
        year = int(request.GET.get('year', today.year))
    except (ValueError, TypeError):
        year = today.year

    from medecins.models import Service
    from collections import defaultdict

    services    = list(Service.objects.order_by('nom'))
    employes_qs = _employes_eligibles()
    nb_employes_total = employes_qs.count()

    # Jours ouvrés théoriques par mois (sans fériés exacts pour simplifier)
    def jours_ouvres_mois(y, m):
        ld = calendar.monthrange(y, m)[1]
        return sum(1 for d in range(1, ld + 1) if _d(y, m, d).weekday() < 5)

    # ── Evolution mensuelle (12 mois) ──
    mois_labels = []
    taux_mensuel = []
    conges_mois_data = []
    maladies_mois_data = []

    for m in range(1, 13):
        jo = jours_ouvres_mois(year, m)
        capacite = nb_employes_total * jo or 1
        jours_conge = Conge.objects.filter(
            date_debut__year=year, date_debut__month=m,
            statut__in=['approuve', 'en_cours', 'termine'],
        ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
        jours_maladie = Conge.objects.filter(
            date_debut__year=year, date_debut__month=m,
            statut__in=['approuve', 'en_cours', 'termine'],
            type_conge='maladie',
        ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
        mois_labels.append(_MOIS_FR[m][:3])
        taux_mensuel.append(round(jours_conge / capacite * 100, 1))
        conges_mois_data.append(int(jours_conge))
        maladies_mois_data.append(int(jours_maladie))

    # ── Par service ──
    services_stats = []
    for svc in services:
        emps = employes_qs.filter(service=svc)
        nb_e = emps.count()
        if not nb_e:
            continue
        jours_total = Conge.objects.filter(
            employe__in=emps,
            date_debut__year=year,
            statut__in=['approuve', 'en_cours', 'termine'],
        ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
        jours_maladie = Conge.objects.filter(
            employe__in=emps,
            date_debut__year=year,
            statut__in=['approuve', 'en_cours', 'termine'],
            type_conge='maladie',
        ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
        capacite = nb_e * sum(jours_ouvres_mois(year, m) for m in range(1, 13)) or 1
        services_stats.append({
            'service':       svc,
            'nb_employes':   nb_e,
            'jours_total':   int(jours_total),
            'jours_maladie': int(jours_maladie),
            'taux':          round(jours_total / capacite * 100, 1),
        })
    services_stats.sort(key=lambda x: -x['taux'])

    # ── Soldes critiques (< 5j) ──
    soldes_critiques = []
    with transaction.atomic():
        for emp in employes_qs.select_related('service'):
            s = get_or_create_solde(emp, year)
            if float(s.solde) < 5:
                soldes_critiques.append({'emp': emp, 'solde': s})
    soldes_critiques.sort(key=lambda x: float(x['solde'].solde))

    # ── KPIs globaux ──
    jo_annee = sum(jours_ouvres_mois(year, m) for m in range(1, 13))
    capacite_annee = nb_employes_total * jo_annee or 1
    total_jours = Conge.objects.filter(
        date_debut__year=year,
        statut__in=['approuve', 'en_cours', 'termine'],
    ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
    total_maladie = Conge.objects.filter(
        date_debut__year=year,
        statut__in=['approuve', 'en_cours', 'termine'],
        type_conge='maladie',
    ).aggregate(t=Sum('nb_jours_ouvres'))['t'] or 0
    taux_global = round(total_jours / capacite_annee * 100, 1)
    taux_maladie = round(total_maladie / capacite_annee * 100, 1)
    pic_mois = mois_labels[taux_mensuel.index(max(taux_mensuel))] if taux_mensuel else '—'

    # ── Données graphes JSON ──
    chart_evolution = {
        'labels':    mois_labels,
        'conges':    conges_mois_data,
        'maladies':  maladies_mois_data,
        'taux':      taux_mensuel,
    }
    chart_services = {
        'labels': [s['service'].nom for s in services_stats[:8]],
        'taux':   [s['taux'] for s in services_stats[:8]],
        'jours':  [s['jours_total'] for s in services_stats[:8]],
    }

    return render(request, 'conges/direction.html', {
        'nav_active':        'direction',
        'year':              year,
        'today':             today,
        'taux_global':       taux_global,
        'taux_maladie':      taux_maladie,
        'total_jours':       int(total_jours),
        'nb_employes':       nb_employes_total,
        'pic_mois':          pic_mois,
        'services_stats':    services_stats,
        'soldes_critiques':  soldes_critiques[:10],
        'chart_evolution':   chart_evolution,
        'chart_services':    chart_services,
        'can_manage':        True,
    })


# ── Notifications : lire toutes ───────────────────────────────────────────────
@login_required(login_url='login')
def conge_notifs_lire(request):
    if request.method == 'POST':
        NotificationConge.objects.filter(
            destinataire=request.user, lue=False
        ).update(lue=True)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True})
        messages.success(request, "Toutes les notifications de congé ont été marquées comme lues.")
        return redirect(request.META.get('HTTP_REFERER', 'conge_dashboard'))
    return redirect('conge_dashboard')


# ── Notifications : lire une ──────────────────────────────────────────────────
@login_required(login_url='login')
def conge_notif_lire_une(request, pk):
    notif = get_object_or_404(NotificationConge, pk=pk, destinataire=request.user)
    if request.method == 'POST':
        notif.lue = True
        notif.save(update_fields=['lue'])
    return redirect('conge_detail', pk=notif.conge_id)
