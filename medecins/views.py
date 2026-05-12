from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import Medecin, Specialite, Departement, Service


@login_required(login_url='login')
def medecin_list(request):
    qs = Medecin.objects.select_related('specialite').prefetch_related('departements')

    q = request.GET.get('q', '').strip()
    specialite_id = request.GET.get('specialite', '')
    service_id = request.GET.get('service', '')
    chirurgien = request.GET.get('chirurgien', '')
    statut = request.GET.get('statut', 'actif')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code__icontains=q) | Q(fonction__icontains=q)
        )
    if specialite_id:
        qs = qs.filter(specialite_id=specialite_id)
    if service_id:
        qs = qs.filter(departements__id=service_id)
    if chirurgien == '1':
        qs = qs.filter(chirurgien_principal=True)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'archive':
        qs = qs.filter(actif=False)

    qs = qs.order_by('nom', 'prenoms')

    paginator = Paginator(qs, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    stats = {
        'total': Medecin.objects.count(),
        'actifs': Medecin.objects.filter(actif=True).count(),
        'chirurgiens': Medecin.objects.filter(chirurgien_principal=True, actif=True).count(),
        'specialites': Specialite.objects.count(),
    }

    return render(request, 'medecins/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'specialites': Specialite.objects.order_by('nom'),
        'departements': Departement.objects.filter(actif=True).order_by('nom'),
        'q': q,
        'specialite_id': specialite_id,
        'service_id': service_id,
        'chirurgien': chirurgien,
        'statut': statut,
        'breadcrumb': [{'title': 'Accueil', 'url': '/'}, {'title': 'Médecins'}],
    })


@login_required(login_url='login')
def medecin_detail(request, pk):
    medecin = get_object_or_404(
        Medecin.objects.select_related('specialite', 'service_consultation', 'service_suivi')
                       .prefetch_related('departements', 'diplomes__diplome'),
        pk=pk
    )

    from consultations.models import Ordonnance, ExamenDemande
    from laboratoire.models import AnalyseLaboratoire
    stats = {
        'rdv': medecin.rendez_vous.count(),
        'consultations': medecin.consultations.count(),
        'ordonnances': Ordonnance.objects.filter(consultation__medecin=medecin).count(),
        'hospitalisations': medecin.hospitalisation_set.count(),
        'traitements': medecin.protocolehospitalisation_set.count(),
        'chirurgie': 0,
        'demandes_lab': ExamenDemande.objects.filter(consultation__medecin=medecin).count(),
        'resultats_lab': AnalyseLaboratoire.objects.filter(examen_demande__consultation__medecin=medecin).count(),
    }

    return render(request, 'medecins/detail.html', {
        'medecin': medecin,
        'stats': stats,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Médecins', 'url': '/medecins/'},
            {'title': f'Dr {medecin.nom} {medecin.prenoms}'},
        ],
    })
