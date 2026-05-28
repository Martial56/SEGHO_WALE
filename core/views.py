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
    from medicament.models import Medicament
    from facturation.models import Facture
    from laboratoire.models import AnalyseLaboratoire
    from employer.models import Employe
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
        'employes_actifs': Employe.objects.filter(statut='actif').count(),
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
    from employer.models import Employe
    from django.core.paginator import Paginator

    medecins = Employe.objects.filter(est_medecin=True).order_by('nom')
    paginator = Paginator(medecins, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {'total': medecins.count(), 'consultations_mois': 0, 'disponibles': medecins.filter(statut='actif').count()}
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Médecins'}]
    return render(request, 'utilisateur/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


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


# ═══════════════════════════════════════════════
#  GYNÉCOLOGIE
# ═══════════════════════════════════════════════

def _rdv_gyn_qs():
    from patients.models import RendezVous
    from django.db.models import Q
    return RendezVous.objects.filter(
        Q(departement='gynecologie_cpn') | Q(medecin__specialite__nom__icontains='gyn')
    ).select_related('patient', 'medecin').order_by('-date_heure')


@login_required(login_url='login')
def gynecologie_list(request):
    from patients.models import Patient
    from django.core.paginator import Paginator
    from django.db.models import Q
    from datetime import date as _date

    q         = request.GET.get('q', '').strip()
    filter_val = request.GET.get('filter', '')
    group_val  = request.GET.get('group', '')

    patients = Patient.objects.filter(
        rendez_vous__departement='gynecologie_cpn'
    ).distinct().order_by('nom', 'prenoms')

    if q:
        patients = patients.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )

    today = _date.today()
    if filter_val == 'femme':
        patients = patients.filter(sexe='F')
    elif filter_val == 'homme':
        patients = patients.filter(sexe='M')
    elif filter_val == 'mineur':
        patients = patients.filter(date_naissance__gt=today.replace(year=today.year - 18))
    elif filter_val == 'adulte':
        patients = patients.filter(
            date_naissance__lte=today.replace(year=today.year - 18),
            date_naissance__gt=today.replace(year=today.year - 60),
        )
    elif filter_val == 'senior':
        patients = patients.filter(date_naissance__lte=today.replace(year=today.year - 60))

    if group_val == 'sexe':
        patients = patients.order_by('sexe', 'nom', 'prenoms')
    elif group_val == 'age':
        patients = patients.order_by('date_naissance')

    paginator = Paginator(patients, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    breadcrumb = [{'title': 'Gynécologie', 'url': '/gynecologie/'}, {'title': 'Patients'}]
    return render(request, 'gynecologie/list.html', {'page_obj': page_obj, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def gynecologie_rdv(request):
    from patients.models import RendezVous
    from django.core.paginator import Paginator
    from django.db.models import Q
    from datetime import date as _date

    q          = request.GET.get('q', '').strip()
    filter_val = request.GET.get('filter', '')
    group_val  = request.GET.get('group', '')
    date_from  = request.GET.get('date_from', '').strip()
    date_to    = request.GET.get('date_to', '').strip()

    rdvs = _rdv_gyn_qs()

    if q:
        rdvs = rdvs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(patient__code_patient__icontains=q)
        )

    if filter_val == 'today' or (not filter_val and not date_from and not date_to):
        rdvs = rdvs.filter(date_heure__date=_date.today())
    elif filter_val == 'mine':
        rdvs = rdvs.filter(medecin__user=request.user)
    elif filter_val == 'urgent':
        rdvs = rdvs.filter(niveau_urgence__in=['urgent', 'tres_urgent'])
    elif filter_val == 'urgence_medicale':
        rdvs = rdvs.filter(type_rdv='urgence')
    elif filter_val == 'consultation':
        rdvs = rdvs.filter(type_rdv='consultation')
    elif filter_val == 'suivi':
        rdvs = rdvs.filter(type_rdv='controle')
    elif filter_val == 'not_done':
        rdvs = rdvs.exclude(statut__in=['termine', 'annule', 'absent'])

    if date_from:
        try:
            rdvs = rdvs.filter(date_heure__date__gte=date_from)
        except (ValueError, TypeError):
            pass
    if date_to:
        try:
            rdvs = rdvs.filter(date_heure__date__lte=date_to)
        except (ValueError, TypeError):
            pass

    if group_val in ('date_jour', 'date_semaine', 'date_mois', 'date_trimestre', 'date_annee'):
        rdvs = rdvs.order_by('date_heure')
    elif group_val == 'statut':
        rdvs = rdvs.order_by('statut', '-date_heure')
    elif group_val in ('medecin', 'referent'):
        rdvs = rdvs.order_by('medecin', '-date_heure')
    elif group_val == 'type_rdv':
        rdvs = rdvs.order_by('type_rdv', '-date_heure')
    elif group_val == 'patient':
        rdvs = rdvs.order_by('patient__nom', 'patient__prenoms')
    elif group_val == 'sexe':
        rdvs = rdvs.order_by('patient__sexe', '-date_heure')
    elif group_val == 'age':
        rdvs = rdvs.order_by('patient__date_naissance')

    paginator = Paginator(rdvs, 80)
    page_obj  = paginator.get_page(request.GET.get('page'))
    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous'},
    ]
    return render(request, 'gynecologie/rdv.html', {'page_obj': page_obj, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def gynecologie_rdv_create(request):
    from patients.forms import RendezVousForm
    from patients.models import Pathologie, TypeVisite
    from employer.models import Employe

    medecins = Employe.objects.filter(est_medecin=True).order_by('nom')

    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            rdv.save()
            action = request.POST.get('_action', '')
            if action == 'annuler':
                return redirect('gynecologie_rdv')
            from django.urls import reverse
            return redirect(reverse('facture_create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
    else:
        form = RendezVousForm(initial={
            'date_heure': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'departement': 'gynecologie_cpn',
        })

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': 'Nouveau'},
    ]
    return render(request, 'gynecologie/rdv_form.html', {
        'form': form,
        'rdv': None,
        'is_new': True,
        'patient_prefill': None,
        'consultation': None,
        'constante': None,
        'facture_payee': False,
        'medecins': medecins,
        'pathologies': Pathologie.objects.filter(actif=True).order_by('nom'),
        'types_visite': TypeVisite.objects.filter(actif=True).order_by('nom'),
        'breadcrumb': breadcrumb,
    })


@login_required(login_url='login')
def gynecologie_rdv_detail(request, pk):
    from patients.forms import RendezVousForm
    from patients.models import RendezVous, Pathologie, TypeVisite
    from employer.models import Employe

    rdv      = get_object_or_404(RendezVous, pk=pk)
    medecins = Employe.objects.filter(est_medecin=True).order_by('nom')

    try:
        from facturation.models import Facture
        facture_payee = Facture.objects.filter(patient=rdv.patient, statut='payee').exists()
    except Exception:
        facture_payee = False

    consultation = None
    constante    = None
    try:
        consultation = rdv.consultation
        try:
            constante = consultation.constantes
        except Exception:
            pass
    except Exception:
        pass

    if request.method == 'POST':
        action = request.POST.get('_action', '')

        if action == 'save_eval':
            _eval_map = {
                'eval_poids': 'poids', 'eval_taille': 'taille',
                'eval_temperature': 'temperature',
                'eval_tension_systolique': 'tension_systolique',
                'eval_tension_diastolique': 'tension_diastolique',
                'eval_tension_systolique_droite': 'tension_systolique_droite',
                'eval_tension_diastolique_droite': 'tension_diastolique_droite',
                'eval_pouls': 'pouls',
                'eval_frequence_respiratoire': 'frequence_respiratoire',
                'eval_saturation_oxygene': 'saturation_oxygene',
                'eval_glycemie': 'glycemie',
                'eval_albumine': 'albumine',
                'eval_perimetre_brachial': 'perimetre_brachial',
                'eval_niveau_douleur': 'niveau_douleur',
            }
            from consultations.models import Consultation as Consult, Constante as Const
            try:
                consult_obj = rdv.consultation
            except Exception:
                consult_obj = None
            if consult_obj is None:
                consult_obj = Consult.objects.create(
                    patient=rdv.patient, medecin=rdv.medecin, rendez_vous=rdv,
                    motif=rdv.motif or 'Évaluation clinique', cree_par=request.user,
                )
            const_obj, _ = Const.objects.get_or_create(consultation=consult_obj)
            for post_key, model_field in _eval_map.items():
                val = request.POST.get(post_key, '').strip()
                if val != '':
                    setattr(const_obj, model_field, val)
            const_obj.save()
            return redirect('gynecologie_rdv_detail', pk=rdv.pk)

        if action == 'confirmer':
            if facture_payee:
                rdv.statut = 'confirme'
                rdv.save(update_fields=['statut'])
            return redirect('gynecologie_rdv')

        if action in ('en_attente', 'en_consultation'):
            rdv.statut = action
            rdv.save(update_fields=['statut'])
            return redirect('gynecologie_rdv_detail', pk=rdv.pk)

        if action == 'terminer':
            rdv.statut = 'termine'
            rdv.save(update_fields=['statut'])
            return redirect('gynecologie_rdv')

        if action == 'annuler':
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])
            return redirect('gynecologie_rdv')

        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            cpn_tv_pk = request.POST.get('cpn_type_visite', '').strip()
            rdv.cpn_mode_entree       = request.POST.get('cpn_mode_entree', '').strip()
            rdv.cpn_mode_entree_autre = request.POST.get('cpn_mode_entree_autre', '').strip()
            rdv.cpn_type_visite = TypeVisite.objects.get(pk=int(cpn_tv_pk)) if cpn_tv_pk else None
            cur_tv_pk = request.POST.get('cur_type_visite', '').strip()
            rdv.cur_mode_entree       = request.POST.get('cur_mode_entree', '').strip()
            rdv.cur_mode_entree_autre = request.POST.get('cur_mode_entree_autre', '').strip()
            rdv.cur_type_visite = TypeVisite.objects.get(pk=int(cur_tv_pk)) if cur_tv_pk else None
            rdv.save()
            if action == 'créer une facture':
                from django.urls import reverse
                return redirect(reverse('facture_create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
            return redirect('gynecologie_rdv')
    else:
        form = RendezVousForm(instance=rdv)

    qs_pks = list(_rdv_gyn_qs().values_list('pk', flat=True))
    total  = len(qs_pks)
    try:
        pos      = qs_pks.index(pk)
        nav_pos  = pos + 1
        nav_prev = qs_pks[pos - 1] if pos > 0 else None
        nav_next = qs_pks[pos + 1] if pos < total - 1 else None
    except ValueError:
        nav_pos = nav_prev = nav_next = None

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': rdv.code_rdv or rdv.patient.code_patient},
    ]
    return render(request, 'gynecologie/rdv_form.html', {
        'form': form,
        'rdv': rdv,
        'is_new': False,
        'patient_prefill': rdv.patient,
        'facture_payee': facture_payee,
        'consultation': consultation,
        'constante': constante,
        'medecins': medecins,
        'pathologies': Pathologie.objects.filter(actif=True).order_by('nom'),
        'types_visite': TypeVisite.objects.filter(actif=True).order_by('nom'),
        'breadcrumb': breadcrumb,
        'nav_total': total,
        'nav_pos': nav_pos,
        'nav_prev': nav_prev,
        'nav_next': nav_next,
    })


@login_required(login_url='login')
@require_POST
def gynecologie_rdv_set_statut(request, pk):
    from patients.models import RendezVous
    rdv = get_object_or_404(RendezVous, pk=pk)
    new_statut = request.POST.get('statut', '')
    valid = [s[0] for s in RendezVous.STATUT]
    if new_statut in valid:
        rdv.statut = new_statut
        rdv.save(update_fields=['statut'])
    return redirect(request.POST.get('next', '/gynecologie/rdv/'))


@login_required(login_url='login')
@require_POST
def gynecologie_rdv_bulk(request):
    from patients.models import RendezVous
    action  = request.POST.get('bulk_action', '')
    pks     = request.POST.getlist('selected_ids')
    valid   = [s[0] for s in RendezVous.STATUT]
    if action in valid and pks:
        RendezVous.objects.filter(pk__in=pks).update(statut=action)
    return redirect(request.POST.get('next', '/gynecologie/rdv/'))


@login_required(login_url='login')
def gynecologie_rdv_calendrier(request):
    import calendar
    from datetime import date as _date
    from collections import defaultdict

    today = _date.today()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    cal = calendar.monthcalendar(year, month)
    month_name = _date(year, month, 1).strftime('%B %Y').capitalize()

    rdvs = _rdv_gyn_qs().filter(date_heure__year=year, date_heure__month=month)
    rdvs_by_day = defaultdict(list)
    for rdv in rdvs:
        rdvs_by_day[rdv.date_heure.day].append(rdv)

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': 'Calendrier'},
    ]
    return render(request, 'gynecologie/rdv_calendrier.html', {
        'year': year, 'month': month,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'month_name': month_name,
        'today': today,
        'cal': cal,
        'rdvs_by_day': dict(rdvs_by_day),
        'breadcrumb': breadcrumb,
    })


@login_required(login_url='login')
def gynecologie_rdv_kanban(request):
    from datetime import date as _date, timedelta
    from django.utils.dateparse import parse_date

    today_dt = _date.today()
    raw_date = request.GET.get('date', '')
    cur_date = parse_date(raw_date) if raw_date else today_dt
    if cur_date is None:
        cur_date = today_dt

    prev_date = cur_date - timedelta(days=1)
    next_date = cur_date + timedelta(days=1)

    rdvs = _rdv_gyn_qs().filter(date_heure__date=cur_date)

    COLS = [
        {'key': 'planifie',        'label': 'Planifié',        'color': '#1565c0', 'bg': '#e3f2fd'},
        {'key': 'confirme',        'label': 'Confirmé',        'color': '#2e7d32', 'bg': '#e8f5e9'},
        {'key': 'en_attente',      'label': 'En attente',      'color': '#f57f17', 'bg': '#fff8e1'},
        {'key': 'en_consultation', 'label': 'En consultation', 'color': '#00838f', 'bg': '#e0f7fa'},
        {'key': 'termine',         'label': 'Terminé',         'color': '#4527a0', 'bg': '#ede7f6'},
        {'key': 'annule',          'label': 'Annulé',          'color': '#b71c1c', 'bg': '#fce4ec'},
        {'key': 'absent',          'label': 'Absent',          'color': '#e65100', 'bg': '#fff3e0'},
    ]
    rdv_list = list(rdvs)
    columns = []
    for col in COLS:
        col_rdvs = [r for r in rdv_list if r.statut == col['key']]
        columns.append({**col, 'rdvs': col_rdvs, 'count': len(col_rdvs)})

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': 'Kanban'},
    ]
    return render(request, 'gynecologie/rdv_kanban.html', {
        'columns': columns,
        'cur_date': cur_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'today': today_dt,
        'total': len(rdv_list),
        'breadcrumb': breadcrumb,
    })


@login_required(login_url='login')
def gynecologie_cpn_suivi(request):
    from patients.models import RendezVous
    from django.db.models import Q
    from datetime import date as _date

    today = _date.today()
    q = request.GET.get('q', '').strip()
    try:
        year  = int(request.GET.get('year',  today.year))
        month = int(request.GET.get('month', today.month))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1
    month_name = _date(year, month, 1).strftime('%B %Y').capitalize()

    # Tous les RDV CPN du mois + RDV CPN hors-mois planifiés pour des patientes actives ce mois
    rdvs_mois = RendezVous.objects.filter(
        departement='gynecologie_cpn',
        date_heure__year=year,
        date_heure__month=month,
    ).select_related('patient', 'cpn_type_visite')

    if q:
        rdvs_mois = rdvs_mois.filter(
            Q(patient__nom__icontains=q) | Q(patient__prenoms__icontains=q) |
            Q(patient__code_patient__icontains=q)
        )

    # Construire un set de patients avec au moins 1 RDV ce mois
    patient_ids = list(rdvs_mois.values_list('patient_id', flat=True).distinct())

    # Tous leurs RDV CPN (tous mois) pour calculer le parcours
    all_rdvs = RendezVous.objects.filter(
        departement='gynecologie_cpn',
        patient_id__in=patient_ids,
    ).select_related('patient', 'cpn_type_visite').order_by('patient_id', 'date_heure')

    # Grouper par patient
    from itertools import groupby as py_groupby
    rdvs_by_patient = {}
    for rdv in all_rdvs:
        rdvs_by_patient.setdefault(rdv.patient_id, []).append(rdv)

    from patients.models import Patient
    patients = Patient.objects.filter(pk__in=patient_ids).order_by('nom', 'prenoms')

    rows = []
    for patient in patients:
        p_rdvs = rdvs_by_patient.get(patient.pk, [])
        done_rdvs    = [r for r in p_rdvs if r.statut == 'termine']
        planned_rdvs = [r for r in p_rdvs if r.statut not in ('termine', 'annule', 'absent')]

        cpn_status = []
        for i in range(5):
            done_rdv    = done_rdvs[i]    if i < len(done_rdvs)    else None
            planned_rdv = planned_rdvs[i] if i < len(planned_rdvs) else None
            rdv_obj     = done_rdv or planned_rdv

            is_at = False
            date_str = ''
            if rdv_obj:
                is_at    = not (rdv_obj.date_heure.year == year and rdv_obj.date_heure.month == month)
                date_str = rdv_obj.date_heure.strftime('%d/%m/%Y')

            cpn_status.append({
                'done':    done_rdv is not None,
                'planned': planned_rdv is not None and done_rdv is None,
                'rdv':     rdv_obj,
                'date':    date_str,
                'is_at':   is_at,
            })

        rows.append({
            'patient':   patient,
            'cpn_status': cpn_status,
            'completed': len(done_rdvs),
        })

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Suivi CPN'},
    ]
    return render(request, 'gynecologie/cpn_suivi.html', {
        'rows': rows,
        'total': len(rows),
        'q': q,
        'year': year, 'month': month,
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'month_name': month_name,
        'breadcrumb': breadcrumb,
    })


@login_required(login_url='login')
def gynecologie_registre_naissance(request):
    from patients.models import Naissance
    from django.core.paginator import Paginator
    from django.db.models import Q

    export       = request.GET.get('export', '')
    q            = request.GET.get('q', '').strip()
    filter_type  = request.GET.get('filter_type', '')
    date_precise = request.GET.get('date_precise', '')
    date_debut   = request.GET.get('date_debut', '')
    date_fin     = request.GET.get('date_fin', '')
    filtre_statut = request.GET.get('filtre_statut', '')
    group_by     = request.GET.get('group_by', '')

    naissances = Naissance.objects.select_related('mere', 'medecin', 'mere__assurance')

    if q:
        naissances = naissances.filter(
            Q(mere__nom__icontains=q) | Q(mere__prenoms__icontains=q) |
            Q(numero__icontains=q) | Q(nom_enfant__icontains=q)
        )

    if filter_type == 'mois':
        now = timezone.now()
        naissances = naissances.filter(date_accouchement__month=now.month, date_accouchement__year=now.year)
    elif filter_type == 'date' and date_precise:
        naissances = naissances.filter(date_accouchement__date=date_precise)
    elif filter_type == 'plage':
        if date_debut:
            naissances = naissances.filter(date_accouchement__date__gte=date_debut)
        if date_fin:
            naissances = naissances.filter(date_accouchement__date__lte=date_fin)

    if filtre_statut in ('vivant', 'mort_ne'):
        naissances = naissances.filter(statut=filtre_statut)

    ORDER_MAP = {
        'annee': 'date_accouchement', 'trimestre': 'date_accouchement',
        'mois': 'date_accouchement', 'semaine': 'date_accouchement',
        'jour': 'date_accouchement', 'mere': 'mere__nom',
        'medecin': 'medecin__nom', 'mode': 'mode_accouchement',
        'statut': 'statut', 'genre': 'sexe_enfant',
        'groupe_sanguin': 'groupe_sanguin_enfant', 'lieu': 'lieu_naissance',
        'parite': 'parite', 'education': 'education_mere', 'cree_le': 'date_creation',
    }
    naissances = naissances.order_by(ORDER_MAP.get(group_by, '-date_accouchement'))
    naissances_list = list(naissances)

    if export == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from django.http import HttpResponse

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Registre des naissances'
        headers = [
            'Numéro', 'Mère', 'Date d\'accouchement', 'Médecin',
            'Mode d\'accouchement', 'Nom de l\'enfant', 'Prénoms de l\'enfant',
            'Sexe', 'Poids (g)', 'Taille (cm)', 'Apgar 1\'', 'Apgar 5\'',
            'Groupe sanguin', 'Lieu de naissance', 'Parité',
            'Garçons', 'Filles', 'Éducation mère', 'Statut', 'Remarques',
        ]
        thin = Side(style='thin', color='DDDDDD')
        border = Border(left=thin, right=thin, bottom=thin)
        header_fill = PatternFill('solid', fgColor='714B67')
        header_font = Font(bold=True, color='FFFFFF', size=10)
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border
        ws.row_dimensions[1].height = 18

        for row_idx, n in enumerate(naissances_list, 2):
            values = [
                n.numero,
                f"{n.mere.nom.upper()} {n.mere.prenoms}",
                n.date_accouchement.strftime('%d/%m/%Y %H:%M'),
                str(n.medecin) if n.medecin else '',
                n.get_mode_accouchement_display(),
                n.nom_enfant, n.prenoms_enfant,
                'Féminin' if n.sexe_enfant == 'F' else 'Masculin',
                float(n.poids_naissance) if n.poids_naissance else '',
                float(n.taille_naissance) if n.taille_naissance else '',
                n.apgar_1min if n.apgar_1min is not None else '',
                n.apgar_5min if n.apgar_5min is not None else '',
                n.groupe_sanguin_enfant, n.lieu_naissance, n.parite,
                n.nombre_garcons, n.nombre_filles,
                n.get_education_mere_display(), n.get_statut_display(), n.remarques,
            ]
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.border = border
                if row_idx % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F9F4FC')

        col_widths = [14, 28, 18, 22, 18, 18, 20, 10, 10, 10, 9, 9, 12, 18, 8, 8, 8, 16, 10, 30]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="naissances_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
        wb.save(response)
        return response

    from itertools import groupby as py_groupby
    grouped_data = None
    if group_by and naissances_list:
        def get_group_key(n):
            if group_by == 'annee':    return str(n.date_accouchement.year)
            if group_by == 'trimestre':
                q = (n.date_accouchement.month - 1) // 3 + 1
                return f"T{q} {n.date_accouchement.year}"
            if group_by == 'mois':    return n.date_accouchement.strftime('%B %Y').capitalize()
            if group_by == 'semaine': return f"Semaine {n.date_accouchement.strftime('%W')} – {n.date_accouchement.year}"
            if group_by == 'jour':    return n.date_accouchement.strftime('%d/%m/%Y')
            if group_by == 'mere':    return f"{n.mere.nom.upper()} {n.mere.prenoms}"
            if group_by == 'medecin': return str(n.medecin) if n.medecin else '— Sans médecin'
            if group_by == 'mode':    return n.get_mode_accouchement_display()
            if group_by == 'statut':  return n.get_statut_display()
            if group_by == 'genre':   return 'Féminin' if n.sexe_enfant == 'F' else 'Masculin'
            if group_by == 'groupe_sanguin': return n.groupe_sanguin_enfant or '—'
            if group_by == 'lieu':    return n.lieu_naissance or '—'
            if group_by == 'parite':  return f"Parité {n.parite}"
            if group_by == 'education': return n.get_education_mere_display() or '—'
            if group_by == 'cree_le': return n.date_creation.strftime('%d/%m/%Y')
            return None
        grouped_data = [(k, list(v)) for k, v in py_groupby(naissances_list, key=get_group_key)]

    paginator = Paginator(naissances_list, 80)
    page_obj  = paginator.get_page(request.GET.get('page'))
    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Registre des naissances'},
    ]
    return render(request, 'gynecologie/registre_naissance.html', {
        'page_obj': page_obj,
        'grouped_data': grouped_data,
        'group_by': group_by,
        'breadcrumb': breadcrumb,
        'filter_type': filter_type,
        'date_precise': date_precise,
        'date_debut': date_debut,
        'date_fin': date_fin,
        'filtre_statut': filtre_statut,
    })


@login_required(login_url='login')
def gynecologie_naissance_create(request):
    from patients.models import Naissance, Patient
    from employer.models import Employe
    from django.utils.dateparse import parse_datetime

    patients = Patient.objects.filter(actif=True).order_by('nom')
    medecins = Employe.objects.filter(est_medecin=True).order_by('nom')
    error    = None

    if request.method == 'POST':
        action = request.POST.get('action', 'brouillon')
        try:
            raw_date = request.POST.get('date_accouchement', '')
            date_acc = parse_datetime(raw_date) if raw_date else timezone.now()
            if date_acc is None:
                date_acc = timezone.now()
            n = Naissance(
                mere_id             = request.POST.get('mere') or None,
                medecin_id          = request.POST.get('medecin') or None,
                date_accouchement   = date_acc,
                lieu_naissance      = request.POST.get('lieu_naissance', ''),
                mode_accouchement   = request.POST.get('mode_accouchement', 'voie_basse'),
                nom_enfant          = request.POST.get('nom_enfant', ''),
                prenoms_enfant      = request.POST.get('prenoms_enfant', ''),
                sexe_enfant         = request.POST.get('sexe_enfant') or 'F',
                poids_naissance     = request.POST.get('poids_naissance') or None,
                groupe_sanguin_enfant = request.POST.get('groupe_sanguin_enfant', ''),
                taux_hemoglobine    = request.POST.get('taux_hemoglobine') or None,
                taille_naissance    = request.POST.get('taille_naissance') or None,
                apgar_1min          = request.POST.get('apgar_1min') or None,
                apgar_5min          = request.POST.get('apgar_5min') or None,
                statut              = request.POST.get('statut', 'vivant'),
                info_parents        = request.POST.get('info_parents', ''),
                education_mere      = request.POST.get('education_mere', ''),
                age_mere            = request.POST.get('age_mere') or None,
                parite              = int(request.POST.get('parite') or 0),
                nombre_garcons      = int(request.POST.get('nombre_garcons') or 0),
                nombre_filles       = int(request.POST.get('nombre_filles') or 0),
                remarques           = request.POST.get('remarques', ''),
                statut_dossier      = 'termine' if action == 'termine' else 'brouillon',
            )
            n.save()
            return redirect('gynecologie_naissances')
        except Exception as e:
            error = str(e)

    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Registre des naissances', 'url': '/gynecologie/naissances/'},
    ]
    return render(request, 'gynecologie/registre_naissance_form.html', {
        'patients': patients,
        'medecins': medecins,
        'breadcrumb': breadcrumb,
        'error': error,
        'post': request.POST if request.method == 'POST' else {},
    })
