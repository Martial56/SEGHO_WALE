from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
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
    from consultations.models import Consultation
    from hospitalisation.models import Hospitalisation
    from pharmacie.models import Medicament
    from facturation.models import Facture
    from laboratoire.models import AnalyseLaboratoire
    from ressources_humaines.models import Employe
    from modules_permissions.models import get_user_modules

    today = timezone.now().date()

    stats = {
        'patients_total': Patient.objects.filter(actif=True).count(),
        'patients_today': Patient.objects.filter(date_creation__date=today).count(),
        'consultations_today': Consultation.objects.filter(date_heure__date=today).count(),
        'rdv_today': RendezVous.objects.filter(date_heure__date=today).count(),
        'hospitalisations': Hospitalisation.objects.filter(statut__in=['admis', 'en_soins']).count(),
        'analyses_pending': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'factures_impayees': Facture.objects.filter(statut__in=['emise', 'partielle']).count(),
        'medicaments_alerte': Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count(),
        'employes_actifs': Employe.objects.filter(statut='actif').count(),
    }

    rdv_auj = RendezVous.objects.filter(
        date_heure__date=today,
        statut__in=['planifie', 'confirme']
    ).select_related('patient', 'medecin').order_by('date_heure')[:8]

    last_cons = Consultation.objects.select_related(
        'patient', 'medecin'
    ).order_by('-date_heure')[:6]

    # Modules accessibles pour cet utilisateur
    user_modules = get_user_modules(request.user)
    accessible_codes = set(user_modules.values_list('code', flat=True))

    return render(request, 'core/dashboard.html', {
        'stats': stats,
        'rdv_auj': rdv_auj,
        'last_cons': last_cons,
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
    from medecins.models import Medecin
    from django.core.paginator import Paginator

    medecins = Medecin.objects.all().order_by('nom')
    paginator = Paginator(medecins, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'total': Medecin.objects.count(), 'consultations_mois': 0, 'disponibles': Medecin.objects.count()}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Médecins'}]
    return render(request, 'medecins/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def consultations_list(request):
    from consultations.models import Consultation
    from django.core.paginator import Paginator

    consultations = Consultation.objects.all().order_by('-date_heure')
    paginator = Paginator(consultations, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    today = timezone.now().date()
    stats = {
        'aujourdhui': Consultation.objects.filter(date_heure__date=today).count(),
        'ce_mois': Consultation.objects.filter(date_heure__month=today.month, date_heure__year=today.year).count(),
        'rdv_venir': 0,
        'diagnostic_rate': 0,
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Consultations'}]
    return render(request, 'consultations/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


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

    analyses = AnalyseLaboratoire.objects.all().order_by('-date_reception')
    paginator = Paginator(analyses, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {
        'en_cours': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'resultats_prets': AnalyseLaboratoire.objects.filter(statut='resultats_prets').count(),
        'analyses_mois': AnalyseLaboratoire.objects.filter(date_reception__month=timezone.now().month).count(),
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
    from caisse.models import Session
    from django.core.paginator import Paginator

    sessions = Session.objects.all().order_by('-date_ouverture')
    paginator = Paginator(sessions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'solde_actuel': 0, 'entrees_jour': 0, 'sorties_jour': 0, 'transactions': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Caisse'}]
    return render(request, 'caisse/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def ressources_humaines_list(request):
    from ressources_humaines.models import Employe
    from django.core.paginator import Paginator

    employes = Employe.objects.all().order_by('nom')
    paginator = Paginator(employes, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'total_employes': Employe.objects.count(), 'employes_actifs': Employe.objects.filter(actif=True).count(), 'conges_attente': 0, 'taux_presence': 0}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Ressources Humaines'}]
    return render(request, 'ressources_humaines/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def rapports_list(request):
    from rapports.models import Rapport
    from django.core.paginator import Paginator

    rapports = Rapport.objects.all().order_by('-date_creation')
    paginator = Paginator(rapports, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {
        'total_rapports': Rapport.objects.count(),
        'rapports_mois': Rapport.objects.filter(date_creation__month=timezone.now().month).count(),
        'rapports_attente': Rapport.objects.filter(statut='en_attente').count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Rapports'}]
    return render(request, 'rapports/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def facture_create(request):
    from facturation.models import Facture, LigneFacture, Acte, Paiement
    from facturation.forms import FactureForm
    from patients.models import Patient, RendezVous
    from caisse.models import Caisse
    from django.urls import reverse

    patient_pk = request.GET.get('patient') or request.POST.get('patient_id')
    patient = get_object_or_404(Patient, pk=patient_pk) if patient_pk else None
    actes = Acte.objects.filter(actif=True).order_by('categorie', 'libelle')
    caisses = Caisse.objects.filter(actif=True).order_by('nom')

    # Pré-remplissage depuis le RDV
    rdv_obj = None
    rdv_pk = request.GET.get('rdv') or request.POST.get('rdv_id')
    if rdv_pk:
        try:
            rdv_obj = RendezVous.objects.get(pk=rdv_pk)
        except RendezVous.DoesNotExist:
            pass

    initial_type_facture = 'consultation' if rdv_obj else ''
    initial_ligne_libelle = rdv_obj.service.nom if (rdv_obj and rdv_obj.service) else ''

    if request.method == 'POST':
        form = FactureForm(request.POST)
        if not patient:
            messages.error(request, 'Patient introuvable.')
            return redirect('facturation_list')
        if form.is_valid():
            facture = form.save(commit=False)
            facture.patient = patient
            facture.cree_par = request.user
            facture.save()

            total = 0
            i = 0
            while True:
                libelle = request.POST.get(f'ligne_libelle_{i}')
                if libelle is None:
                    break
                if libelle.strip():
                    try:
                        qte = float(request.POST.get(f'ligne_qte_{i}', 1) or 1)
                        prix = float(request.POST.get(f'ligne_prix_{i}', 0) or 0)
                        remise = float(request.POST.get(f'ligne_remise_{i}', 0) or 0)
                    except ValueError:
                        qte, prix, remise = 1, 0, 0
                    ligne = LigneFacture(
                        facture=facture,
                        libelle=libelle.strip(),
                        quantite=qte,
                        prix_unitaire=prix,
                        remise=remise,
                    )
                    acte_id = request.POST.get(f'ligne_acte_{i}')
                    if acte_id:
                        try:
                            ligne.acte_id = int(acte_id)
                        except ValueError:
                            pass
                    ligne.save()
                    total += qte * prix * (1 - remise / 100)
                i += 1

            facture.montant_total = total
            facture.save()

            # Enregistrement du paiement si soumis via la modale
            pay_montant_raw = request.POST.get('pay_montant', '').strip()
            if pay_montant_raw:
                try:
                    pay_montant = float(pay_montant_raw)
                except ValueError:
                    pay_montant = 0
                if pay_montant > 0:
                    mode = request.POST.get('pay_mode', 'especes')
                    memo = request.POST.get('pay_memo', '')
                    compte = request.POST.get('pay_compte', '')
                    reference = compte if compte else memo
                    paiement = Paiement(
                        facture=facture,
                        montant=pay_montant,
                        mode_paiement=mode,
                        reference=reference,
                        notes=memo,
                        recu_par=request.user,
                    )
                    paiement.save()
                    facture.montant_paye = pay_montant
                    facture.statut = 'payee' if pay_montant >= total else 'partielle'
                    facture.save()

            messages.success(request, f'Facture {facture.numero} créée avec succès.')
            if rdv_pk:
                return redirect(reverse('patients:rdv_edit', kwargs={'pk': rdv_pk}))
            return redirect('facturation_list')
    else:
        initial = {'type_facture': initial_type_facture} if initial_type_facture else {}
        form = FactureForm(initial=initial)

    return render(request, 'facturation/create_facture.html', {
        'form': form,
        'patient': patient,
        'actes': actes,
        'caisses': caisses,
        'rdv': rdv_obj,
        'initial_ligne_libelle': initial_ligne_libelle,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Facturation', 'url': '/facturation/'},
            {'title': 'Nouvelle facture'},
        ],
    })
