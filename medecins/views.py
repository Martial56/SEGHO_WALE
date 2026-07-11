from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from .models import Medecin


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
def medecins_export_csv(request):
    import csv
    from django.http import HttpResponse

    qs = Medecin.objects.select_related('specialite', 'departement').order_by('nom')
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

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="medecins.csv"'
    response.write('﻿')  # BOM pour Excel
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Matricule', 'Nom', 'Prénoms', 'Spécialité', 'Département', 'Téléphone', 'Email', 'Honoraire (FCFA)', 'Statut'])
    for med in qs:
        writer.writerow([
            med.matricule,
            med.nom,
            med.prenoms,
            str(med.specialite) if med.specialite else '',
            str(med.departement) if med.departement else '',
            med.telephone or '',
            med.email or '',
            med.taux_honoraire or 0,
            'Actif' if med.actif else 'Inactif',
        ])
    return response


@login_required(login_url='login')
def medecin_dashboard(request):
    import json
    from consultations.models import Consultation
    from patients.models import RendezVous
    from django.db.models.functions import TruncMonth
    from datetime import date

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
