from datetime import date, time, timedelta, datetime
import calendar
import json

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from employer.models import Employe, Presence, JourFerie, Conge
from employer.views import can_manage_rh

_MOIS_FR = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre',
}
_JOURS_FR = {0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi',
             4: 'Vendredi', 5: 'Samedi', 6: 'Dimanche'}


def _employes_actifs():
    return (Employe.objects.filter(statut='actif')
            .select_related('service', 'fonction')
            .order_by('nom', 'prenoms'))


def _parse_time(val):
    if not val or not val.strip():
        return None
    try:
        from datetime import time
        h, m = val.strip().split(':')
        return time(int(h), int(m))
    except (ValueError, IndexError):
        return None


def _nav_month(year, month):
    if month == 1:
        py, pm = year - 1, 12
    else:
        py, pm = year, month - 1
    if month == 12:
        ny, nm = year + 1, 1
    else:
        ny, nm = year, month + 1
    return py, pm, ny, nm


# ── Registre quotidien ────────────────────────────────────────────────────────

@login_required(login_url='login')
def presence_registre(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    date_str = request.GET.get('date', '')
    try:
        selected_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        selected_date = date.today()

    # Filtre service
    from medecins.models import Service
    services   = Service.objects.order_by('nom')
    service_id = request.GET.get('service', '')
    service_sel = None
    employes = _employes_actifs()
    if service_id:
        try:
            service_sel = Service.objects.get(pk=service_id)
            employes = employes.filter(service=service_sel)
        except Service.DoesNotExist:
            pass

    if request.method == 'POST':
        for emp in _employes_actifs():
            present = (request.POST.get(f'present_{emp.pk}', '0') == '1')
            obj, _ = Presence.objects.get_or_create(
                employe=emp, date=selected_date,
                defaults={'present': present},
            )
            obj.present             = present
            obj.heure_arrivee_matin = _parse_time(request.POST.get(f'h_am_{emp.pk}'))
            obj.heure_depart_matin  = _parse_time(request.POST.get(f'h_dm_{emp.pk}'))
            obj.heure_arrivee_soir  = _parse_time(request.POST.get(f'h_as_{emp.pk}'))
            obj.heure_depart_soir   = _parse_time(request.POST.get(f'h_ds_{emp.pk}'))
            obj.remarques           = request.POST.get(f'rem_{emp.pk}', '').strip()
            if not present:
                motif = request.POST.get(f'motif_{emp.pk}', '').strip()
                obj.motif_absence = motif
            else:
                obj.motif_absence = ''
            obj.save()
        messages.success(request, f"Registre du {selected_date:%d/%m/%Y} enregistré.")
        url = f"{request.path}?date={selected_date.isoformat()}"
        if service_id:
            url += f"&service={service_id}"
        return redirect(url)

    employes = list(employes)
    emp_ids  = [e.pk for e in employes]
    presences_map = {p.employe_id: p for p in
                     Presence.objects.filter(date=selected_date, employe_id__in=emp_ids)}
    conges_map = {c.employe_id: c for c in Conge.objects.filter(
        employe_id__in=emp_ids,
        date_debut__lte=selected_date,
        date_fin__gte=selected_date,
        statut__in=['approuve', 'en_cours'],
    )}

    lignes = []
    for i, emp in enumerate(employes, 1):
        p     = presences_map.get(emp.pk)
        conge = conges_map.get(emp.pk)
        if p:
            present = p.present
        elif conge:
            present = False
        else:
            present = True
        lignes.append({'num': i, 'emp': emp, 'p': p, 'present': present, 'conge': conge})

    # Navigation jours ouvrés
    prev_d = selected_date - timedelta(days=1)
    next_d = selected_date + timedelta(days=1)
    while prev_d.weekday() >= 5:
        prev_d -= timedelta(days=1)
    while next_d.weekday() >= 5:
        next_d += timedelta(days=1)

    nb_presents = sum(1 for l in lignes if l['present'])

    return render(request, 'presence/registre.html', {
        'selected_date':     selected_date,
        'selected_date_iso': selected_date.isoformat(),
        'jour_fr':           _JOURS_FR[selected_date.weekday()],
        'mois_fr':           _MOIS_FR[selected_date.month],
        'prev_date':         prev_d,
        'next_date':         next_d,
        'lignes':            lignes,
        'services':          services,
        'service_sel':       service_sel,
        'nb_presents':       nb_presents,
        'nb_absents':        len(lignes) - nb_presents,
        'today':             date.today(),
        'can_manage':        True,
    })


# ── Récapitulatif mensuel (tableau des jours) ─────────────────────────────────

@login_required(login_url='login')
def presence_recap_mensuel(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    last_day = calendar.monthrange(year, month)[1]
    emp_count = Employe.objects.filter(statut='actif').count()

    jours = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        if d.weekday() >= 5:
            continue
        nb_p = Presence.objects.filter(date=d, present=True).count()
        nb_a = Presence.objects.filter(date=d, present=False).count()
        jours.append({
            'date':    d,
            'jour_fr': _JOURS_FR[d.weekday()],
            'nb_p':    nb_p,
            'nb_a':    nb_a,
            'nb_ns':   max(0, emp_count - nb_p - nb_a),
            'taux':    round(nb_p / emp_count * 100) if emp_count else 0,
            'futur':   d > today,
        })

    py, pm, ny, nm = _nav_month(year, month)
    return render(request, 'presence/recap_mensuel.html', {
        'jours': jours, 'year': year, 'month': month, 'mois_fr': _MOIS_FR[month],
        'emp_count': emp_count, 'today': today,
        'prev_year': py, 'prev_month': pm, 'next_year': ny, 'next_month': nm,
        'can_manage': True,
    })


# ── Historique d'un employé ───────────────────────────────────────────────────

@login_required(login_url='login')
def presence_employe(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    employe = get_object_or_404(Employe.objects.select_related('service', 'fonction'), pk=pk)
    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    last_day = calendar.monthrange(year, month)[1]
    presences_map = {p.date: p for p in
                     Presence.objects.filter(employe=employe, date__year=year, date__month=month)}

    # Fetch all approved/en_cours congés overlapping this month in one query
    conges_mois = list(Conge.objects.filter(
        employe=employe,
        statut__in=['approuve', 'en_cours'],
        date_debut__lte=date(year, month, last_day),
        date_fin__gte=date(year, month, 1),
    ))

    def _conge_pour(d):
        for c in conges_mois:
            if c.date_debut <= d <= c.date_fin:
                return c
        return None

    jours = []
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        jours.append({
            'date':    d,
            'jour_fr': _JOURS_FR[d.weekday()],
            'weekend': d.weekday() >= 5,
            'p':       presences_map.get(d),
            'conge':   _conge_pour(d) if d.weekday() < 5 else None,
        })

    jouvres  = sum(1 for j in jours if not j['weekend'])
    nb_p     = sum(1 for j in jours if j['p'] and j['p'].present and not j['weekend'])
    nb_a     = sum(1 for j in jours if j['p'] and not j['p'].present and not j['weekend'])
    nb_retards = sum(
        1 for j in jours
        if j['p'] and j['p'].present and not j['weekend']
        and (j['p'].retard_matin_min > 0 or j['p'].retard_soir_min > 0)
    )

    py, pm, ny, nm = _nav_month(year, month)
    return render(request, 'presence/employe.html', {
        'employe': employe, 'jours': jours,
        'year': year, 'month': month, 'mois_fr': _MOIS_FR[month],
        'jouvres': jouvres, 'nb_p': nb_p, 'nb_a': nb_a,
        'nb_ns':    max(0, jouvres - nb_p - nb_a),
        'nb_retards': nb_retards,
        'taux': round(nb_p / jouvres * 100, 1) if jouvres else 0,
        'prev_year': py, 'prev_month': pm, 'next_year': ny, 'next_month': nm,
        'can_manage': True,
    })


# ── Statistiques ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def presence_stats(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    last_day  = calendar.monthrange(year, month)[1]
    jouvres   = sum(1 for d in range(1, last_day + 1)
                    if date(year, month, d).weekday() < 5)

    from medecins.models import Service
    services   = Service.objects.order_by('nom')
    service_id = request.GET.get('service', '')
    service_sel = None
    employes = _employes_actifs()
    if service_id:
        try:
            service_sel = Service.objects.get(pk=service_id)
            employes = employes.filter(service=service_sel)
        except Service.DoesNotExist:
            pass

    stats = []
    for emp in employes:
        nb_p = Presence.objects.filter(employe=emp, date__year=year, date__month=month, present=True).count()
        nb_a = Presence.objects.filter(employe=emp, date__year=year, date__month=month, present=False).count()
        stats.append({
            'emp': emp,
            'nb_p': nb_p,
            'nb_a': nb_a,
            'nb_ns': max(0, jouvres - nb_p - nb_a),
            'taux': round(nb_p / jouvres * 100, 1) if jouvres else 0,
        })
    stats.sort(key=lambda x: x['taux'])

    # Par service
    stats_svc = []
    for svc in Service.objects.order_by('nom'):
        emps = _employes_actifs().filter(service=svc)
        n = emps.count()
        if not n:
            continue
        total_poss = n * jouvres
        total_p = Presence.objects.filter(
            employe__in=emps, date__year=year, date__month=month, present=True
        ).count()
        stats_svc.append({
            'service': svc,
            'nb_emps': n,
            'taux': round(total_p / total_poss * 100, 1) if total_poss else 0,
        })

    py, pm, ny, nm = _nav_month(year, month)
    return render(request, 'presence/stats.html', {
        'stats': stats, 'stats_svc': stats_svc,
        'year': year, 'month': month, 'mois_fr': _MOIS_FR[month],
        'jouvres': jouvres, 'services': services, 'service_sel': service_sel,
        'prev_year': py, 'prev_month': pm, 'next_year': ny, 'next_month': nm,
        'can_manage': True,
    })


# ── Rapport de présence ──────────────────────────────────────────────────────

@login_required(login_url='login')
def presence_rapport(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied

    today = date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    last_day = calendar.monthrange(year, month)[1]
    jouvres_list = [date(year, month, d) for d in range(1, last_day + 1)
                    if date(year, month, d).weekday() < 5]
    nb_jouvres = len(jouvres_list)

    from medecins.models import Service
    services   = Service.objects.order_by('nom')
    service_id = request.GET.get('service', '')
    service_sel = None
    employes = _employes_actifs()
    if service_id:
        try:
            service_sel = Service.objects.get(pk=service_id)
            employes = employes.filter(service=service_sel)
        except Service.DoesNotExist:
            pass

    stats = []
    retards_all = []

    for emp in employes:
        presences = {p.date: p for p in
                     Presence.objects.filter(employe=emp, date__year=year, date__month=month)}
        nb_p = sum(1 for p in presences.values() if p.present)
        nb_a = sum(1 for p in presences.values() if not p.present)

        nb_retards = 0
        min_retards = 0
        for p in presences.values():
            if not p.present:
                continue
            rm = p.retard_matin_min
            rs = p.retard_soir_min
            if rm > 0:
                nb_retards += 1
                min_retards += rm
                retards_all.append({
                    'emp':          emp,
                    'date':         p.date,
                    'jour_fr':      _JOURS_FR[p.date.weekday()],
                    'type':         'Matin',
                    'heure_arrivee': p.heure_arrivee_matin,
                    'minutes':      rm,
                    'ref':          '08:00',
                })
            if rs > 0:
                nb_retards += 1
                min_retards += rs
                retards_all.append({
                    'emp':          emp,
                    'date':         p.date,
                    'jour_fr':      _JOURS_FR[p.date.weekday()],
                    'type':         'Soir',
                    'heure_arrivee': p.heure_arrivee_soir,
                    'minutes':      rs,
                    'ref':          '15:00',
                })

        stats.append({
            'emp':         emp,
            'nb_p':        nb_p,
            'nb_a':        nb_a,
            'nb_ns':       max(0, nb_jouvres - nb_p - nb_a),
            'nb_retards':  nb_retards,
            'min_retards': min_retards,
            'taux':        round(nb_p / nb_jouvres * 100, 1) if nb_jouvres else 0,
        })

    retards_all.sort(key=lambda x: (x['date'], x['emp'].nom))

    py, pm, ny, nm = _nav_month(year, month)
    return render(request, 'presence/rapport.html', {
        'stats':       stats,
        'retards_all': retards_all,
        'year':        year,
        'month':       month,
        'mois_fr':     _MOIS_FR[month],
        'nb_jouvres':  nb_jouvres,
        'services':    services,
        'service_sel': service_sel,
        'prev_year':   py,
        'prev_month':  pm,
        'next_year':   ny,
        'next_month':  nm,
        'today':       today,
        'can_manage':  True,
    })


# ── Kiosque de pointage ───────────────────────────────────────────────────────

_LABELS_ACTION = {
    'arrivee_matin': 'Arrivée matin',
    'depart_matin':  'Départ matin',
    'arrivee_soir':  'Arrivée soir',
    'depart_soir':   'Départ soir',
}


def _conge_du_jour(emp, d):
    """Retourne le congé approuvé/en cours de l'employé pour la date d, ou None."""
    return Conge.objects.filter(
        employe=emp,
        date_debut__lte=d,
        date_fin__gte=d,
        statut__in=['approuve', 'en_cours'],
    ).first()


def _est_jour_ouvre(d):
    """Retourne (True, None) si ouvré, (False, raison) sinon."""
    if d.weekday() == 6:
        return False, 'Dimanche — repos'
    ferie = JourFerie.objects.filter(date=d).first()
    if ferie:
        return False, f'Jour férié — {ferie.description}'
    return True, None


_MIDI = time(12, 0)


def _detecter_action(emp, d):
    """Détermine la prochaine action à enregistrer selon ce qui est déjà saisi.

    Après 12h00 : si le matin n'est pas encore enregistré, on saute directement
    à l'arrivée soir (l'employé est absent le matin). Sur Samedi (weekday 5),
    il n'y a pas de session soir donc c'est 'complet'.
    """
    apres_midi = datetime.now().time() >= _MIDI
    a_soir = d.weekday() < 5  # session soir uniquement Lun–Ven

    try:
        p = Presence.objects.get(employe=emp, date=d)
    except Presence.DoesNotExist:
        if apres_midi and a_soir:
            return 'arrivee_soir'
        if apres_midi and not a_soir:
            return 'complet'  # Samedi après 12h → journée terminée
        return 'arrivee_matin'

    if not p.heure_arrivee_matin:
        if apres_midi and a_soir:
            return 'arrivee_soir'
        if apres_midi and not a_soir:
            return 'complet'
        return 'arrivee_matin'
    if not p.heure_depart_matin:
        return 'depart_matin'
    if a_soir:
        if not p.heure_arrivee_soir:
            return 'arrivee_soir'
        if not p.heure_depart_soir:
            return 'depart_soir'
    return 'complet'


def presence_pointage(request):
    """Page kiosque publique — l'employé pointe lui-même."""
    today = date.today()
    now   = datetime.now()
    ouvre, raison_ferme = _est_jour_ouvre(today)
    return render(request, 'presence/pointage.html', {
        'today':        today,
        'ouvre':        ouvre,
        'raison_ferme': raison_ferme,
        'jour_fr':      _JOURS_FR[today.weekday()],
        'mois_fr':      _MOIS_FR[today.month],
        'heure_init':   now.strftime('%H:%M'),
    })


@require_POST
def presence_chercher(request):
    """AJAX — recherche d'un employé par matricule."""
    try:
        data = json.loads(request.body)
        matricule = data.get('matricule', '').strip().upper()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'ok': False, 'erreur': 'Données invalides'})

    if not matricule:
        return JsonResponse({'ok': False, 'erreur': 'Matricule requis'})

    try:
        emp = Employe.objects.select_related('service', 'fonction').get(
            matricule=matricule, statut='actif'
        )
    except Employe.DoesNotExist:
        return JsonResponse({'ok': False, 'erreur': 'Matricule introuvable ou employé inactif'})

    today = date.today()
    conge = _conge_du_jour(emp, today)
    if conge:
        return JsonResponse({
            'ok':    False,
            'conge': True,
            'erreur': f"En congé — {conge.get_type_conge_display()} (jusqu'au {conge.date_fin:%d/%m/%Y})",
        })

    action = _detecter_action(emp, today)

    return JsonResponse({
        'ok': True,
        'emp': {
            'pk':         emp.pk,
            'nom':        emp.nom_complet,
            'matricule':  emp.matricule,
            'service':    emp.service.nom if emp.service else '—',
            'fonction':   emp.fonction.nom if emp.fonction else '',
            'photo':      emp.photo.url if emp.photo else None,
        },
        'action':       action,
        'action_label': _LABELS_ACTION.get(action, ''),
        'complet':      action == 'complet',
    })


@require_POST
def presence_pointer(request):
    """AJAX — enregistre le pointage avec l'heure courante."""
    try:
        data   = json.loads(request.body)
        emp_pk = int(data.get('emp_pk'))
        action = data.get('action', '').strip()
    except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
        return JsonResponse({'ok': False, 'erreur': 'Données invalides'})

    if action not in _LABELS_ACTION:
        return JsonResponse({'ok': False, 'erreur': 'Action inconnue'})

    try:
        emp = Employe.objects.get(pk=emp_pk, statut='actif')
    except Employe.DoesNotExist:
        return JsonResponse({'ok': False, 'erreur': 'Employé introuvable'})

    today = date.today()
    ouvre, raison = _est_jour_ouvre(today)
    if not ouvre:
        return JsonResponse({'ok': False, 'erreur': raison})

    # Vérification cohérence
    current = _detecter_action(emp, today)
    if current == 'complet':
        return JsonResponse({'ok': False, 'erreur': 'Journée déjà complète'})
    if current != action:
        return JsonResponse({'ok': False, 'erreur': 'Veuillez actualiser et recommencer'})

    now = datetime.now().time().replace(second=0, microsecond=0)
    p, _ = Presence.objects.get_or_create(employe=emp, date=today, defaults={'present': True})
    p.present = True

    if action == 'arrivee_matin':
        p.heure_arrivee_matin = now
    elif action == 'depart_matin':
        p.heure_depart_matin = now
    elif action == 'arrivee_soir':
        p.heure_arrivee_soir = now
    elif action == 'depart_soir':
        p.heure_depart_soir = now

    p.save()

    # Prochaine action
    next_action = _detecter_action(emp, today)
    return JsonResponse({
        'ok':          True,
        'heure':       now.strftime('%H:%M'),
        'action':      action,
        'label':       _LABELS_ACTION[action],
        'next_action': next_action,
        'complet':     next_action == 'complet',
    })
