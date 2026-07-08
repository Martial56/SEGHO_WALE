from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.contrib.auth.models import User

from .models import Specialite, Service, Medecin
from .forms import SpecialiteForm, ServiceForm


# ─── SPÉCIALITÉS ────────────────────────────────────────────────────────────

@login_required(login_url='login')
def specialites_list(request):
    qs = Specialite.objects.order_by('nom')
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/specialites_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Specialite.objects.count(),
        'total_filtre': qs.count(),
    })


@login_required(login_url='login')
def specialite_create(request):
    if request.method == 'POST':
        form = SpecialiteForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Spécialité « {obj.nom} » créée.')
            return redirect('medecins_specialites')
    else:
        form = SpecialiteForm()
    return render(request, 'medecins/config/specialite_form.html', {
        'form': form,
        'titre': 'Nouvelle spécialité',
    })


@login_required(login_url='login')
def specialite_edit(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    if request.method == 'POST':
        form = SpecialiteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Spécialité mise à jour.')
            return redirect('medecins_specialite_detail', pk=pk)
    else:
        form = SpecialiteForm(instance=obj)
    return render(request, 'medecins/config/specialite_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
    })


@login_required(login_url='login')
def specialite_detail(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    medecins = Medecin.objects.filter(specialite=obj).order_by('nom', 'prenoms')
    ids = list(Specialite.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'medecins/config/specialite_detail.html', {
        'obj': obj,
        'medecins': medecins,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required(login_url='login')
@require_POST
def specialite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Specialite.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


# ─── SERVICES (DÉPARTEMENTS) ─────────────────────────────────────────────────

@login_required(login_url='login')
def services_list(request):
    qs = Service.objects.select_related('chef_service').order_by('nom')
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/departements_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Service.objects.count(),
        'total_filtre': qs.count(),
    })


@login_required(login_url='login')
def service_create(request):
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Service « {obj.nom} » créé.')
            return redirect('medecins_departements')
    else:
        form = ServiceForm()
    return render(request, 'medecins/config/departement_form.html', {
        'form': form,
        'titre': 'Nouveau service',
    })


@login_required(login_url='login')
def service_edit(request, pk):
    obj = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service mis à jour.')
            return redirect('medecins_departement_detail', pk=pk)
    else:
        form = ServiceForm(instance=obj)
    return render(request, 'medecins/config/departement_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
    })


@login_required(login_url='login')
def service_detail(request, pk):
    obj = get_object_or_404(Service.objects.select_related('chef_service'), pk=pk)
    ids = list(Service.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    medecins = Medecin.objects.filter(service=obj).order_by('nom', 'prenoms')
    return render(request, 'medecins/config/departement_detail.html', {
        'obj': obj,
        'medecins': medecins,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required(login_url='login')
@require_POST
def service_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Service.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


# ─── MÉDECINS CRUD ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def medecins_list(request):
    qs = Medecin.objects.select_related('specialite', 'service').order_by('nom')
    q          = request.GET.get('q', '').strip()
    specialite = request.GET.get('specialite', '')
    statut     = request.GET.get('statut', '')
    vue        = request.GET.get('vue', '')

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q))
    if specialite:
        qs = qs.filter(specialite__pk=specialite)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    total       = Medecin.objects.count()
    actifs      = Medecin.objects.filter(actif=True).count()
    specialites = Specialite.objects.all().order_by('nom')
    paginator   = Paginator(qs, 20)
    page_obj    = paginator.get_page(request.GET.get('page'))

    kanban_colonnes = []
    for sp in specialites:
        medecins_sp = [m for m in qs if m.specialite_id == sp.pk]
        if medecins_sp:
            kanban_colonnes.append({'titre': sp.nom, 'medecins': medecins_sp})
    sans_spec = [m for m in qs if m.specialite_id is None]
    if sans_spec:
        kanban_colonnes.append({'titre': 'Sans spécialité', 'medecins': sans_spec})

    # Médecins en service aujourd'hui (via planning hebdomadaire)
    en_service_pks = set()
    try:
        from planning.models import PlanningHebdomadaire, Affectation
        from datetime import timedelta
        today_date = timezone.now().date()
        lundi      = today_date - timedelta(days=today_date.weekday())
        jour_num   = today_date.weekday()
        planning   = PlanningHebdomadaire.objects.filter(semaine_debut=lundi, publie=True).first()
        if planning:
            noms_service = [a.personnel.lower() for a in
                            Affectation.objects.filter(planning=planning, jour=jour_num)]
            for med_obj in qs:
                nom_lower = med_obj.nom.lower()
                if any(nom_lower in p or p in nom_lower for p in noms_service):
                    en_service_pks.add(med_obj.pk)
    except Exception:
        pass

    return render(request, 'medecins/list.html', {
        'page_obj':          page_obj,
        'specialites':       specialites,
        'kanban_colonnes':   kanban_colonnes,
        'stats': {'total': total, 'actifs': actifs, 'specialites': specialites.count()},
        'q':                 q,
        'specialite_filtre': specialite,
        'statut_filtre':     statut,
        'vue_active':        vue,
        'can_manage':        request.user.is_staff or request.user.is_superuser,
        'en_service_pks':    en_service_pks,
    })


@login_required(login_url='login')
def medecin_create(request):
    specialites = Specialite.objects.order_by('nom')
    services    = Service.objects.filter(actif=True).order_by('nom')
    users_disponibles = User.objects.filter(medecin__isnull=True).order_by('last_name', 'first_name')
    errors = {}

    if request.method == 'POST':
        nom            = request.POST.get('nom', '').strip()
        prenoms        = request.POST.get('prenoms', '').strip()
        specialite_pk  = request.POST.get('specialite', '')
        service_pk     = request.POST.get('service', '')
        telephone      = request.POST.get('telephone', '').strip()
        email          = request.POST.get('email', '').strip()
        taux_honoraire = request.POST.get('taux_honoraire', '0').strip() or '0'
        actif          = request.POST.get('actif') == 'on'
        user_pk        = request.POST.get('user', '')

        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not prenoms:
            errors['prenoms'] = 'Les prénoms sont obligatoires.'
        if not telephone:
            errors['telephone'] = 'Le téléphone est obligatoire.'

        if not errors:
            annee   = timezone.now().year
            dernier = Medecin.objects.filter(matricule__startswith=f'MED{annee}').order_by('-matricule').first()
            seq     = (int(dernier.matricule[-4:]) + 1 if dernier and dernier.matricule[-4:].isdigit() else 1)
            matricule = f'MED{annee}{seq:04d}'

            dernier_ord = Medecin.objects.filter(ordre_medecin__startswith=f'ORD{annee}').order_by('-ordre_medecin').first()
            seq_ord     = (int(dernier_ord.ordre_medecin[-4:]) + 1 if dernier_ord and dernier_ord.ordre_medecin[-4:].isdigit() else 1)
            ordre_medecin = f'ORD{annee}{seq_ord:04d}'

            med = Medecin(matricule=matricule, nom=nom, prenoms=prenoms,
                          telephone=telephone, email=email, ordre_medecin=ordre_medecin, actif=actif)
            try:
                med.taux_honoraire = float(taux_honoraire)
            except ValueError:
                med.taux_honoraire = 0

            med.specialite = Specialite.objects.filter(pk=specialite_pk).first() if specialite_pk else None
            med.service    = Service.objects.filter(pk=service_pk).first() if service_pk else None

            if user_pk:
                try:
                    med.user = User.objects.get(pk=user_pk)
                except User.DoesNotExist:
                    pass
            if request.FILES.get('photo'):
                med.photo = request.FILES['photo']
            med.save()
            messages.success(request, f'Médecin {med} enregistré (matricule : {med.matricule}).')
            return redirect('medecins_list')
        post_data = request.POST
    else:
        post_data = None

    return render(request, 'medecins/form.html', {
        'mode': 'create', 'specialites': specialites, 'services': services,
        'users_disponibles': users_disponibles, 'errors': errors, 'post': post_data,
    })


@login_required(login_url='login')
def medecin_edit(request, pk):
    med         = get_object_or_404(Medecin, pk=pk)
    specialites = Specialite.objects.order_by('nom')
    services    = Service.objects.filter(actif=True).order_by('nom')
    users_disponibles = User.objects.filter(
        Q(medecin__isnull=True) | Q(medecin=med)
    ).order_by('last_name', 'first_name')
    errors = {}

    if request.method == 'POST':
        nom            = request.POST.get('nom', '').strip()
        prenoms        = request.POST.get('prenoms', '').strip()
        specialite_pk  = request.POST.get('specialite', '')
        service_pk     = request.POST.get('service', '')
        telephone      = request.POST.get('telephone', '').strip()
        email          = request.POST.get('email', '').strip()
        taux_honoraire = request.POST.get('taux_honoraire', '0').strip() or '0'
        actif          = request.POST.get('actif') == 'on'
        user_pk        = request.POST.get('user', '')

        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not prenoms:
            errors['prenoms'] = 'Les prénoms sont obligatoires.'
        if not telephone:
            errors['telephone'] = 'Le téléphone est obligatoire.'

        if not errors:
            med.nom = nom; med.prenoms = prenoms
            med.telephone = telephone; med.email = email; med.actif = actif
            try:
                med.taux_honoraire = float(taux_honoraire)
            except ValueError:
                med.taux_honoraire = 0
            med.specialite = Specialite.objects.filter(pk=specialite_pk).first() if specialite_pk else None
            med.service    = Service.objects.filter(pk=service_pk).first() if service_pk else None
            if user_pk:
                try:
                    med.user = User.objects.get(pk=user_pk)
                except User.DoesNotExist:
                    med.user = None
            else:
                med.user = None
            if request.FILES.get('photo'):
                if med.photo:
                    med.photo.delete(save=False)
                med.photo = request.FILES['photo']
            elif request.POST.get('photo_supprimer') == '1' and med.photo:
                med.photo.delete(save=False)
                med.photo = None
            med.save()
            messages.success(request, f'Médecin {med} mis à jour.')
            return redirect('medecin_detail', pk=med.pk)

    return render(request, 'medecins/form.html', {
        'mode': 'edit', 'med': med, 'specialites': specialites, 'services': services,
        'users_disponibles': users_disponibles, 'errors': errors,
    })


@login_required(login_url='login')
@require_POST
def medecin_supprimer(request, pk):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied
    med = get_object_or_404(Medecin, pk=pk)
    nom = str(med)
    med.delete()
    messages.success(request, f'{nom} a été supprimé.')
    return redirect('medecins_list')


@login_required(login_url='login')
def medecin_detail(request, pk):
    from consultations.models import Consultation
    from patients.models import RendezVous
    from planning.models import PlanningHebdomadaire, Affectation, JOURS
    from datetime import timedelta

    med   = get_object_or_404(Medecin, pk=pk)
    today = timezone.now().date()

    cons_qs = Consultation.objects.filter(medecin=med).select_related('patient').order_by('-date_heure')
    cons_paginator = Paginator(cons_qs, 10)
    consultations_recentes = cons_paginator.get_page(request.GET.get('cons_page'))
    rdv_a_venir = (
        RendezVous.objects.filter(
            medecin=med, date_heure__date__gte=today,
            statut__in=['planifie', 'confirme', 'en_attente'],
        ).select_related('patient').order_by('date_heure')[:5]
    )
    rdv_total        = RendezVous.objects.filter(medecin=med).count()
    rdv_honores      = RendezVous.objects.filter(medecin=med, statut__in=['termine', 'en_consultation']).count()
    rdv_pour_taux    = RendezVous.objects.filter(medecin=med, statut__in=['termine', 'en_consultation', 'absent']).count()
    taux_presence    = round(rdv_honores / rdv_pour_taux * 100) if rdv_pour_taux > 0 else None
    stats = {
        'total_consultations': Consultation.objects.filter(medecin=med).count(),
        'consultations_mois':  Consultation.objects.filter(
            medecin=med, date_heure__month=today.month, date_heure__year=today.year).count(),
        'rdv_total':      rdv_total,
        'rdv_a_venir':    RendezVous.objects.filter(
            medecin=med, date_heure__date__gte=today,
            statut__in=['planifie', 'confirme', 'en_attente']).count(),
        'taux_presence':  taux_presence,
    }

    # Planning semaine courante pour ce médecin
    lundi = today - timedelta(days=today.weekday())
    planning_semaine = PlanningHebdomadaire.objects.filter(semaine_debut=lundi).first()
    planning_grid = None
    if planning_semaine:
        aff_qs = list(
            Affectation.objects.filter(
                planning=planning_semaine,
                personnel__icontains=med.nom,
            ).select_related('plage', 'plage__bureau').order_by('plage__bureau__ordre', 'plage__ordre', 'jour')
        )
        if aff_qs:
            plages = sorted({a.plage for a in aff_qs}, key=lambda p: (p.bureau.ordre, p.ordre))
            grid = []
            for plage in plages:
                row = {'plage': plage, 'jours': []}
                for j_num, j_lbl in JOURS:
                    aff = next((a for a in aff_qs if a.plage_id == plage.pk and a.jour == j_num), None)
                    row['jours'].append({'label': j_lbl, 'aff': aff})
                grid.append(row)
            planning_grid = {
                'semaine': planning_semaine,
                'jours': [j[1] for j in JOURS],
                'grid': grid,
            }

    return render(request, 'medecins/detail.html', {
        'med':                   med,
        'consultations_recentes': consultations_recentes,
        'rdv_a_venir':           rdv_a_venir,
        'stats':                 stats,
        'today':                 today,
        'planning_grid':         planning_grid,
    })


@login_required(login_url='login')
def medecins_export_csv(request):
    from core.utils import csv_response

    qs = Medecin.objects.select_related('specialite', 'service').order_by('nom')
    q          = request.GET.get('q', '').strip()
    specialite = request.GET.get('specialite', '')
    statut     = request.GET.get('statut', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q))
    if specialite:
        qs = qs.filter(specialite__pk=specialite)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    headers = ['Matricule', 'Nom', 'Prénoms', 'Spécialité', 'Département', 'Téléphone', 'Email', 'Honoraire (FCFA)', 'Statut']
    rows = [
        [
            med.matricule,
            med.nom,
            med.prenoms,
            str(med.specialite) if med.specialite else '',
            str(med.service) if med.service else '',
            med.telephone or '',
            med.email or '',
            med.taux_honoraire or 0,
            'Actif' if med.actif else 'Inactif',
        ]
        for med in qs
    ]
    return csv_response('medecins', headers, rows)


@login_required(login_url='login')
def medecin_dashboard(request):
    import json
    from consultations.models import Consultation
    from patients.models import RendezVous
    from django.db.models.functions import TruncMonth
    from datetime import date, timedelta

    today = timezone.now().date()
    total  = Medecin.objects.count()
    actifs = Medecin.objects.filter(actif=True).count()

    # 6 months ago (safe arithmetic)
    m = today.month - 6
    y = today.year
    if m <= 0:
        m += 12
        y -= 1
    six_mois_ago = date(y, m, 1)

    cons_today = Consultation.objects.filter(date_heure__date=today).count()
    rdv_today  = RendezVous.objects.filter(date_heure__date=today).count()

    # RDV par statut
    statut_labels_map = {
        'planifie': 'Planifié', 'confirme': 'Confirmé', 'en_attente': 'En attente',
        'annule': 'Annulé', 'termine': 'Terminé', 'no_show': 'Non présenté',
    }
    rdv_par_statut = [
        {'statut': statut_labels_map.get(r['statut'], r['statut']), 'n': r['n']}
        for r in RendezVous.objects.values('statut').annotate(n=Count('id')).order_by('-n')
    ]

    # Consultations par mois (6 derniers mois)
    monthly_raw = list(
        Consultation.objects.filter(date_heure__date__gte=six_mois_ago)
        .annotate(mois=TruncMonth('date_heure'))
        .values('mois').annotate(n=Count('id'))
        .order_by('mois')
    )
    chart_labels = [m['mois'].strftime('%b %Y') for m in monthly_raw]
    chart_data   = [m['n'] for m in monthly_raw]

    # Top 8 médecins par consultations (6 derniers mois)
    top_medecins = list(
        Consultation.objects.filter(date_heure__date__gte=six_mois_ago, medecin__isnull=False)
        .values('medecin__pk', 'medecin__nom', 'medecin__prenoms')
        .annotate(n=Count('id'))
        .order_by('-n')[:8]
    )

    # Répartition par spécialité
    par_specialite = list(
        Medecin.objects.filter(actif=True, specialite__isnull=False)
        .values('specialite__nom').annotate(n=Count('id')).order_by('-n')[:8]
    )

    rdv_chart_labels = json.dumps([r['statut'] for r in rdv_par_statut])
    rdv_chart_data   = json.dumps([r['n'] for r in rdv_par_statut])

    return render(request, 'medecins/dashboard.html', {
        'total':             total,
        'actifs':            actifs,
        'inactifs':          total - actifs,
        'cons_today':        cons_today,
        'rdv_today':         rdv_today,
        'rdv_par_statut':    rdv_par_statut,
        'top_medecins':      top_medecins,
        'par_specialite':    par_specialite,
        'chart_labels':      json.dumps(chart_labels),
        'chart_data':        json.dumps(chart_data),
        'chart_has_data':    bool(chart_labels),
        'rdv_chart_labels':  rdv_chart_labels,
        'rdv_chart_data':    rdv_chart_data,
        'today':             today,
    })
