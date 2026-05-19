from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import F


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(request.GET.get('next', 'dashboard'))
        else:
            error = "Identifiant ou mot de passe incorrect."
    return render(request, 'registration/login.html', {'error': error})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard(request):
    from patients.models import Patient, RendezVous
    from soins.models import Soin
    from hospitalisation.models import Hospitalisation
    from pharmacie.models import Medicament
    from facturation.models import Facture
    from laboratoire.models import AnalyseLaboratoire
    from employe.models import Employe
    from modules_permissions.models import get_user_modules

    today = timezone.now().date()

    stats = {
        'patients_total': Patient.objects.count(),
        'patients_today': Patient.objects.filter(date_creation__date=today).count(),
        'soins_today': Soin.objects.filter(date_heure__date=today).count(),
        'rdv_today': RendezVous.objects.filter(date_heure__date=today).count(),
        'hospitalisations': Hospitalisation.objects.filter(statut__in=['admis', 'en_soins']).count(),
        'analyses_pending': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        # 'factures_impayees': Facture.objects.filter(statut__in=['emise', 'partielle']).count(),
        'factures_impayees': 0,
        'medicaments_alerte': Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count(),
        'employes_actifs': Employe.objects.filter(actif=True).count(),
    }

    rdv_auj = RendezVous.objects.filter(
        date_heure__date=today,
        statut__in=['planifie', 'confirme']
    ).select_related('patient', 'medecin').order_by('date_heure')[:8]

    last_soins = Soin.objects.select_related(
        'patient', 'infirmier'
    ).order_by('-date_heure')[:6]

    user_modules = get_user_modules(request.user)
    accessible_codes = set(user_modules.values_list('code', flat=True))

    return render(request, 'core/dashboard.html', {
        'stats': stats,
        'rdv_auj': rdv_auj,
        'last_soins': last_soins,
        'today': today,
        'user': request.user,
        'user_modules': user_modules,
        'accessible_codes': accessible_codes,
    })


@login_required(login_url='login')
def patients_list(request):
    from patients.models import Patient
    from django.core.paginator import Paginator

    patients = Patient.objects.filter(actif=True).order_by('-date_creation')
    paginator = Paginator(patients, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    today = timezone.now().date()
    stats = {
        'total': Patient.objects.filter(actif=True).count(),
        'actifs': Patient.objects.filter(actif=True).count(),
        'nouveaux_30j': Patient.objects.filter(date_creation__date__gte=today - timezone.timedelta(days=30)).count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Patients'}]
    return render(request, 'patients/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def medecins_list(request):
    from employe.models import Employe
    from django.core.paginator import Paginator

    medecins = Employe.objects.filter(est_medecin=True).order_by('nom')
    paginator = Paginator(medecins, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'total': medecins.count(), 'consultations_mois': 0, 'disponibles': medecins.filter(actif=True).count()}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Médecins'}]
    return render(request, 'employe/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def soins_list(request):
    from soins.models import Soin
    from django.core.paginator import Paginator

    soins = Soin.objects.select_related('patient', 'infirmier').order_by('-date_heure')
    paginator = Paginator(soins, 25)
    page_obj = paginator.get_page(request.GET.get('page'))
    today = timezone.now().date()
    stats = {
        'aujourdhui': Soin.objects.filter(date_heure__date=today).count(),
        'ce_mois': Soin.objects.filter(date_heure__month=today.month, date_heure__year=today.year).count(),
        'en_cours': Soin.objects.filter(statut='courant').count(),
        'termines': Soin.objects.filter(statut='complete').count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Soins'}]
    return render(request, 'soins/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def pharmacie_list(request):
    from pharmacie.models import Medicament
    from django.core.paginator import Paginator

    medicaments = Medicament.objects.all().order_by('nom')
    paginator = Paginator(medicaments, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'total_medicaments': Medicament.objects.count(), 'valeur_stock': 0, 'ruptures': 0, 'commandes_attente': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Pharmacie'}]
    return render(request, 'pharmacie/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def laboratoire_list(request):
    from laboratoire.models import AnalyseLaboratoire
    from django.core.paginator import Paginator

    analyses = AnalyseLaboratoire.objects.all().order_by('-date_prelevement')
    paginator = Paginator(analyses, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {
        'en_cours': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'resultats_prets': AnalyseLaboratoire.objects.filter(statut='resultat').count(),
        'analyses_mois': AnalyseLaboratoire.objects.filter(date_prelevement__month=timezone.now().month).count(),
        'delai_moyen': 0,
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Laboratoire'}]
    return render(request, 'laboratoire/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def hospitalisation_list(request):
    from hospitalisation.models import Hospitalisation
    from django.core.paginator import Paginator

    hospitalisations = Hospitalisation.objects.all().order_by('-date_admission')
    paginator = Paginator(hospitalisations, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'patients_hospitalises': Hospitalisation.objects.filter(statut__in=['admis', 'en_soins']).count(), 'taux_occupation': 0, 'chambres_disponibles': 0, 'duree_moyenne': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Hospitalisation'}]
    return render(request, 'hospitalisation/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def facturation_list(request):
    from facturation.models import Facture
    from django.core.paginator import Paginator

    factures = Facture.objects.all().order_by('-date_emission')
    paginator = Paginator(factures, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'montant_total': 0, 'montant_recu': 0, 'montant_attente': 0, 'taux_recouvrement': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Facturation'}]
    return render(request, 'facturation/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def caisse_list(request):
    from caisse.models import SessionCaisse
    from django.core.paginator import Paginator

    sessions = SessionCaisse.objects.all().order_by('-date_ouverture')
    paginator = Paginator(sessions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'solde_actuel': 0, 'entrees_jour': 0, 'sorties_jour': 0, 'transactions': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Caisse'}]
    return render(request, 'caisse/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})



@login_required(login_url='login')
def rapports_list(request):
    from rapports.models import RapportMedical
    from django.core.paginator import Paginator

    rapports = RapportMedical.objects.all().order_by('-date_creation')
    paginator = Paginator(rapports, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {
        'total_rapports': RapportMedical.objects.count(),
        'rapports_mois': RapportMedical.objects.filter(date_creation__month=timezone.now().month).count(),
        'rapports_attente': RapportMedical.objects.filter(valide=False).count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Rapports'}]
    return render(request, 'rapports/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})
