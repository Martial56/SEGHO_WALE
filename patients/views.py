from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta

from .models import Patient, RendezVous
from .forms import PatientForm, RendezVousForm


@login_required
def patient_list(request):
    qs = Patient.objects.all()
    stats = {
        'total': qs.count(),
        'actifs': qs.filter(actif=True).count(),
        'nouveaux_30j': qs.filter(date_creation__gte=timezone.now() - timedelta(days=30)).count(),
    }

    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    sexe = request.GET.get('sexe', '')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)
    if sexe in ('M', 'F'):
        qs = qs.filter(sexe=sexe)

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'patients/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'statut': statut,
        'sexe': sexe,
        'total_filtre': qs.count(),
        'breadcrumb': [{'title': 'Patients'}],
    })


@login_required
def patient_detail(request, pk):
    patient = get_object_or_404(Patient, pk=pk)

    rdv_count = patient.rendez_vous.count()
    consultation_count = patient.consultations.count()
    facture_count = patient.factures.count()

    try:
        from consultations.models import Ordonnance
        ordonnance_count = Ordonnance.objects.filter(consultation__patient=patient).count()
    except Exception:
        ordonnance_count = 0

    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(patient=patient).count()
    except Exception:
        hospitalisation_count = 0

    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_examens_count = AnalyseLaboratoire.objects.filter(patient=patient).count()
        resultat_examens_count = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        demande_examens_count = 0
        resultat_examens_count = 0

    # Navigation précédent/suivant dans la liste ordonnée
    ids = list(Patient.objects.order_by('-date_creation').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1

    return render(request, 'patients/detail.html', {
        'patient': patient,
        'rdv_count': rdv_count,
        'consultation_count': consultation_count,
        'facture_count': facture_count,
        'ordonnance_count': ordonnance_count,
        'hospitalisation_count': hospitalisation_count,
        'demande_examens_count': demande_examens_count,
        'resultat_examens_count': resultat_examens_count,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required
def patient_create(request):
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES)
        if form.is_valid():
            patient = form.save()
            messages.success(request, f'Patient {patient.nom} {patient.prenoms} enregistré avec le code {patient.code_patient}.')
            return redirect('patients:list')
    else:
        form = PatientForm()
    return render(request, 'patients/form.html', {'form': form, 'titre': 'Nouveau patient', 'edit': False})


@login_required
def patient_edit(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    if request.method == 'POST':
        form = PatientForm(request.POST, request.FILES, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dossier patient mis à jour.')
            return redirect('patients:detail', pk=patient.pk)
    else:
        form = PatientForm(instance=patient)
    return render(request, 'patients/form.html', {
        'form': form,
        'patient': patient,
        'titre': f'Modifier — {patient.nom} {patient.prenoms}',
        'edit': True,
    })


@login_required
def rdv_global_list(request):
    from datetime import date, datetime as dt

    today = date.today()
    date_debut_str = request.GET.get('date_debut', today.isoformat())
    date_fin_str   = request.GET.get('date_fin',   today.isoformat())
    statut_filter  = request.GET.get('statut', '')
    pas_fini       = request.GET.get('pas_fini', '')

    try:
        d1 = dt.strptime(date_debut_str, '%Y-%m-%d').date()
        d2 = dt.strptime(date_fin_str,   '%Y-%m-%d').date()
    except ValueError:
        d1 = d2 = today

    qs = RendezVous.objects.select_related('patient', 'medecin').filter(
        date_heure__date__gte=d1,
        date_heure__date__lte=d2,
    ).order_by('date_heure')

    if pas_fini:
        qs = qs.filter(statut__in=['planifie', 'confirme'])
    elif statut_filter:
        qs = qs.filter(statut=statut_filter)

    base_qs = RendezVous.objects.filter(date_heure__date__gte=d1, date_heure__date__lte=d2)
    stats = {
        'total':     base_qs.count(),
        'planifies': base_qs.filter(statut='planifie').count(),
        'confirmes': base_qs.filter(statut='confirme').count(),
        'termines':  base_qs.filter(statut='termine').count(),
        'absents':   base_qs.filter(statut__in=['annule', 'absent']).count(),
    }

    return render(request, 'patients/rendez_vous.html', {
        'rdv_list':      qs,
        'stats':         stats,
        'date_debut':    d1.isoformat(),
        'date_fin':      d2.isoformat(),
        'statut_filter': statut_filter,
        'pas_fini':      pas_fini,
        'today':         today.isoformat(),
        'is_today':      d1 == today and d2 == today,
    })


@login_required
def patient_info_json(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    return JsonResponse({'age': patient.age, 'telephone': patient.telephone})


@login_required
def rdv_create(request):
    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        if form.is_valid():
            rdv = form.save()
            messages.success(
                request,
                f'Rendez-vous créé pour {rdv.patient.nom} {rdv.patient.prenoms} '
                f'le {rdv.date_heure.strftime("%d/%m/%Y à %H:%M")}.'
            )
            return redirect('patients:rdv_global')
    else:
        form = RendezVousForm(initial={'date_heure': timezone.now().strftime('%Y-%m-%dT%H:%M')})
    return render(request, 'patients/rendez_vous_form.html', {
        'form':  form,
        'titre': 'Nouveau rendez-vous',
    })


@login_required
def patient_rdv_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    items = patient.rendez_vous.select_related('medecin').order_by('-date_heure')
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'rdv',
        'titre': 'Rendez-vous',
        'items': items,
    })


@login_required
def patient_consultation_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from consultations.models import Consultation
        items = Consultation.objects.filter(patient=patient).select_related('medecin').order_by('-date_heure')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'consultation',
        'titre': 'Consultations',
        'items': items,
    })


@login_required
def patient_ordonnance_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from consultations.models import Ordonnance
        items = Ordonnance.objects.filter(
            consultation__patient=patient
        ).select_related('consultation').order_by('-date_emission')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'ordonnance',
        'titre': 'Ordonnances',
        'items': items,
    })


@login_required
def patient_hospitalisation_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from hospitalisation.models import Hospitalisation
        items = Hospitalisation.objects.filter(patient=patient).select_related(
            'medecin_traitant', 'chambre'
        ).order_by('-date_admission')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'hospitalisation',
        'titre': 'Hospitalisations',
        'items': items,
    })


@login_required
def patient_demande_examens_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from laboratoire.models import AnalyseLaboratoire
        items = AnalyseLaboratoire.objects.filter(patient=patient).order_by('-date_prelevement')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'demande_examens',
        'titre': "Demandes d'examens de laboratoire",
        'items': items,
    })


@login_required
def patient_resultat_examens_list(request, pk):
    patient = get_object_or_404(Patient, pk=pk)
    try:
        from laboratoire.models import AnalyseLaboratoire
        items = AnalyseLaboratoire.objects.filter(
            patient=patient, statut__in=['résultat', 'validé', 'envoyé']
        ).order_by('-date_resultat')
    except Exception:
        items = []
    return render(request, 'patients/related_list.html', {
        'patient': patient,
        'view_type': 'resultat_examens',
        'titre': "Résultats d'examens de laboratoire",
        'items': items,
    })
