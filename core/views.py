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
def gynecologie_naissance_create(request):
    from patients.models import Naissance, Patient
    from medecins.models import Medecin

    patients = Patient.objects.filter(actif=True).order_by('nom')
    medecins = Medecin.objects.all().order_by('nom')
    error = None

    if request.method == 'POST':
        from django.utils.dateparse import parse_datetime
        action = request.POST.get('action', 'brouillon')
        try:
            raw_date = request.POST.get('date_accouchement', '')
            date_acc = parse_datetime(raw_date) if raw_date else timezone.now()
            if date_acc is None:
                date_acc = timezone.now()
            n = Naissance(
                mere_id=request.POST.get('mere') or None,
                medecin_id=request.POST.get('medecin') or None,
                date_accouchement=date_acc,
                lieu_naissance=request.POST.get('lieu_naissance', ''),
                mode_accouchement=request.POST.get('mode_accouchement', 'voie_basse'),
                nom_enfant=request.POST.get('nom_enfant', ''),
                prenoms_enfant=request.POST.get('prenoms_enfant', ''),
                sexe_enfant=request.POST.get('sexe_enfant') or 'F',
                poids_naissance=request.POST.get('poids_naissance') or None,
                groupe_sanguin_enfant=request.POST.get('groupe_sanguin_enfant', ''),
                taux_hemoglobine=request.POST.get('taux_hemoglobine') or None,
                taille_naissance=request.POST.get('taille_naissance') or None,
                apgar_1min=request.POST.get('apgar_1min') or None,
                apgar_5min=request.POST.get('apgar_5min') or None,
                statut=request.POST.get('statut', 'vivant'),
                info_parents=request.POST.get('info_parents', ''),
                education_mere=request.POST.get('education_mere', ''),
                age_mere=request.POST.get('age_mere') or None,
                parite=int(request.POST.get('parite') or 0),
                nombre_garcons=int(request.POST.get('nombre_garcons') or 0),
                nombre_filles=int(request.POST.get('nombre_filles') or 0),
                remarques=request.POST.get('remarques', ''),
                statut_dossier='termine' if action == 'termine' else 'brouillon',
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


@login_required(login_url='login')
def gynecologie_registre_naissance(request):
    from patients.models import Naissance
    from django.core.paginator import Paginator
    from django.db.models import Q

    export = request.GET.get('export', '')
    q = request.GET.get('q', '').strip()
    filter_type  = request.GET.get('filter_type', '')
    date_precise = request.GET.get('date_precise', '')
    date_debut   = request.GET.get('date_debut', '')
    date_fin     = request.GET.get('date_fin', '')
    filtre_statut = request.GET.get('filtre_statut', '')

    group_by = request.GET.get('group_by', '')

    naissances = Naissance.objects.select_related('mere', 'medecin', 'mere__assurance')

    if q:
        naissances = naissances.filter(
            Q(mere__nom__icontains=q) |
            Q(mere__prenoms__icontains=q) |
            Q(numero__icontains=q) |
            Q(nom_enfant__icontains=q)
        )

    if filter_type == 'mois':
        now = timezone.now()
        naissances = naissances.filter(
            date_accouchement__month=now.month,
            date_accouchement__year=now.year,
        )
    elif filter_type == 'date' and date_precise:
        naissances = naissances.filter(date_accouchement__date=date_precise)
    elif filter_type == 'plage':
        if date_debut:
            naissances = naissances.filter(date_accouchement__date__gte=date_debut)
        if date_fin:
            naissances = naissances.filter(date_accouchement__date__lte=date_fin)

    if filtre_statut in ('vivant', 'mort_ne'):
        naissances = naissances.filter(statut=filtre_statut)

    # Tri selon le regroupement
    ORDER_MAP = {
        'annee':         'date_accouchement',
        'trimestre':     'date_accouchement',
        'mois':          'date_accouchement',
        'semaine':       'date_accouchement',
        'jour':          'date_accouchement',
        'mere':          'mere__nom',
        'medecin':       'medecin__nom',
        'mode':          'mode_accouchement',
        'statut':        'statut',
        'genre':         'sexe_enfant',
        'groupe_sanguin':'groupe_sanguin_enfant',
        'lieu':          'lieu_naissance',
        'parite':        'parite',
        'education':     'education_mere',
        'cree_le':       'date_creation',
    }
    order_field = ORDER_MAP.get(group_by, '-date_accouchement')
    naissances = naissances.order_by(order_field)

    # Préparer les données groupées
    from itertools import groupby as py_groupby
    from django.utils.formats import date_format

    def get_group_key(n):
        if group_by == 'annee':
            return str(n.date_accouchement.year)
        if group_by == 'trimestre':
            q = (n.date_accouchement.month - 1) // 3 + 1
            return f"T{q} {n.date_accouchement.year}"
        if group_by == 'mois':
            return n.date_accouchement.strftime('%B %Y').capitalize()
        if group_by == 'semaine':
            return f"Semaine {n.date_accouchement.strftime('%W')} – {n.date_accouchement.year}"
        if group_by == 'jour':
            return n.date_accouchement.strftime('%d/%m/%Y')
        if group_by == 'mere':
            return f"{n.mere.nom.upper()} {n.mere.prenoms}"
        if group_by == 'medecin':
            return str(n.medecin) if n.medecin else '— Sans médecin'
        if group_by == 'mode':
            return n.get_mode_accouchement_display()
        if group_by == 'statut':
            return n.get_statut_display()
        if group_by == 'genre':
            return 'Féminin' if n.sexe_enfant == 'F' else 'Masculin'
        if group_by == 'groupe_sanguin':
            return n.groupe_sanguin_enfant or '—'
        if group_by == 'lieu':
            return n.lieu_naissance or '—'
        if group_by == 'parite':
            return f"Parité {n.parite}"
        if group_by == 'education':
            return n.get_education_mere_display() or '—'
        if group_by == 'cree_le':
            return n.date_creation.strftime('%d/%m/%Y')
        return None

    naissances_list = list(naissances)

    # ── EXPORT EXCEL ──
    if export == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from django.http import HttpResponse

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Registre des naissances'

        # En-têtes
        headers = [
            'Numéro', 'Mère', 'Date d\'accouchement', 'Médecin',
            'Mode d\'accouchement', 'Nom de l\'enfant', 'Prénoms de l\'enfant',
            'Sexe', 'Poids (g)', 'Taille (cm)', 'Apgar 1\'', 'Apgar 5\'',
            'Groupe sanguin', 'Lieu de naissance', 'Parité',
            'Garçons', 'Filles', 'Éducation mère', 'Statut', 'Remarques',
        ]
        header_fill = PatternFill('solid', fgColor='714B67')
        header_font = Font(bold=True, color='FFFFFF', size=10)
        thin = Side(style='thin', color='DDDDDD')
        border = Border(left=thin, right=thin, bottom=thin)

        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border
        ws.row_dimensions[1].height = 18

        # Données
        for row_idx, n in enumerate(naissances_list, 2):
            values = [
                n.numero,
                f"{n.mere.nom.upper()} {n.mere.prenoms}",
                n.date_accouchement.strftime('%d/%m/%Y %H:%M'),
                str(n.medecin) if n.medecin else '',
                n.get_mode_accouchement_display(),
                n.nom_enfant,
                n.prenoms_enfant,
                'Féminin' if n.sexe_enfant == 'F' else 'Masculin',
                float(n.poids_naissance) if n.poids_naissance else '',
                float(n.taille_naissance) if n.taille_naissance else '',
                n.apgar_1min if n.apgar_1min is not None else '',
                n.apgar_5min if n.apgar_5min is not None else '',
                n.groupe_sanguin_enfant,
                n.lieu_naissance,
                n.parite,
                n.nombre_garcons,
                n.nombre_filles,
                n.get_education_mere_display(),
                n.get_statut_display(),
                n.remarques,
            ]
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=row_idx, column=col, value=val)
                cell.border = border
                if row_idx % 2 == 0:
                    cell.fill = PatternFill('solid', fgColor='F9F4FC')

        # Largeurs auto
        col_widths = [14,28,18,22,18,18,20,10,10,10,9,9,12,18,8,8,8,16,10,30]
        for i, w in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

        filename = f"naissances_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response

    grouped_data = None
    if group_by and naissances_list:
        grouped_data = [(k, list(v)) for k, v in py_groupby(naissances_list, key=get_group_key)]

    paginator = Paginator(naissances_list, 80)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
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


def _rdv_gyn_qs():
    from patients.models import RendezVous
    from django.db.models import Q
    return RendezVous.objects.filter(
        Q(departement='gynecologie_cpn') | Q(medecin__specialite__nom__icontains='gyn')
    ).select_related('patient', 'medecin').order_by('-date_heure')


def _rdv_form_post(request, rdv):
    from django.utils.dateparse import parse_datetime
    action = request.POST.get('action', '')
    PIPELINE = ('planifie', 'confirme', 'en_attente', 'en_consultation', 'termine')
    if action in PIPELINE:
        rdv.statut = action
        rdv.save(update_fields=['statut'])
        return None, True
    try:
        raw_date = request.POST.get('date_heure', '')
        date_rdv = parse_datetime(raw_date) if raw_date else rdv.date_heure
        if date_rdv is None:
            date_rdv = rdv.date_heure or timezone.now()
        raw_suivi = request.POST.get('date_suivi', '')
        date_suivi = parse_datetime(raw_suivi) if raw_suivi else None
        rdv.patient_id = request.POST.get('patient') or rdv.patient_id
        rdv.medecin_id = request.POST.get('medecin') or None
        rdv.docteur_jr_id = request.POST.get('docteur_jr') or None
        rdv.departement = request.POST.get('departement', rdv.departement)
        rdv.salle_consultation = request.POST.get('salle_consultation', '')
        rdv.date_heure = date_rdv
        rdv.date_suivi = date_suivi
        rdv.duree_minutes = int(request.POST.get('duree_minutes') or 30)
        rdv.type_rdv = request.POST.get('type_rdv', rdv.type_rdv)
        rdv.niveau_urgence = request.POST.get('niveau_urgence', 'normal')
        rdv.motif = request.POST.get('motif', '')
        rdv.notes = request.POST.get('notes', '')
        rdv.maladies = request.POST.get('maladies', '')
        rdv.principales_plaintes = request.POST.get('principales_plaintes', '')
        rdv.antecedents_maladie = request.POST.get('antecedents_maladie', '')
        rdv.historique_passee = request.POST.get('historique_passee', '')
        rdv.rdv_exterieur = bool(request.POST.get('rdv_exterieur'))
        rdv.code_confirmation = request.POST.get('code_confirmation', '')
        rdv.temps_attente_minutes = int(request.POST.get('temps_attente_minutes') or 0)
        rdv.temps_consultation_minutes = int(request.POST.get('temps_consultation_minutes') or 0)
        if action in PIPELINE:
            rdv.statut = action
        rdv.save()
        return None, True
    except Exception as e:
        return str(e), False


@login_required(login_url='login')
def gynecologie_rdv_create(request):
    from patients.models import Patient, RendezVous
    from medecins.models import Medecin

    patients = Patient.objects.filter(actif=True).order_by('nom')
    medecins = Medecin.objects.all().order_by('nom')
    error = None

    if request.method == 'POST':
        rdv = RendezVous()
        err, ok = _rdv_form_post(request, rdv)
        if ok:
            return redirect('gynecologie_rdv_detail', pk=rdv.pk)
        error = err

    total = _rdv_gyn_qs().count()
    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': 'Nouveau'},
    ]
    return render(request, 'gynecologie/rdv_form.html', {
        'patients': patients,
        'medecins': medecins,
        'breadcrumb': breadcrumb,
        'error': error,
        'rdv': None,
        'is_new': True,
        'nav_total': total,
        'nav_pos': None,
        'nav_prev': None,
        'nav_next': None,
    })


@login_required(login_url='login')
def gynecologie_rdv_detail(request, pk):
    from patients.models import Patient, RendezVous
    from medecins.models import Medecin
    from django.shortcuts import get_object_or_404

    rdv = get_object_or_404(RendezVous, pk=pk)
    patients = Patient.objects.filter(actif=True).order_by('nom')
    medecins = Medecin.objects.all().order_by('nom')
    error = None

    if request.method == 'POST':
        err, ok = _rdv_form_post(request, rdv)
        if ok:
            return redirect('gynecologie_rdv_detail', pk=rdv.pk)
        error = err

    # Page navigation within gynécologie RDV queryset
    qs_pks = list(_rdv_gyn_qs().values_list('pk', flat=True))
    total = len(qs_pks)
    try:
        pos = qs_pks.index(pk)
        nav_pos = pos + 1
        nav_prev = qs_pks[pos - 1] if pos > 0 else None
        nav_next = qs_pks[pos + 1] if pos < total - 1 else None
    except ValueError:
        nav_pos, nav_prev, nav_next = None, None, None

    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': rdv.code_rdv or rdv.patient.code_patient},
    ]
    return render(request, 'gynecologie/rdv_form.html', {
        'patients': patients,
        'medecins': medecins,
        'breadcrumb': breadcrumb,
        'error': error,
        'rdv': rdv,
        'is_new': False,
        'nav_total': total,
        'nav_pos': nav_pos,
        'nav_prev': nav_prev,
        'nav_next': nav_next,
    })


@login_required(login_url='login')
def gynecologie_rdv(request):
    from patients.models import RendezVous
    from django.core.paginator import Paginator
    from django.db.models import Q

    q = request.GET.get('q', '').strip()
    rdvs = RendezVous.objects.filter(
        Q(departement='gynecologie_cpn') |
        Q(medecin__specialite__nom__icontains='gyn')
    ).select_related('patient', 'medecin').order_by('-date_heure')

    if q:
        rdvs = rdvs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(patient__code_patient__icontains=q)
        )

    paginator = Paginator(rdvs, 80)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    breadcrumb = [
        {'title': 'Accueil', 'url': '/'},
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous'},
    ]
    return render(request, 'gynecologie/rdv.html', {'page_obj': page_obj, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def gynecologie_list(request):
    from consultations.models import Consultation
    from django.core.paginator import Paginator

    today = timezone.now().date()
    consultations = Consultation.objects.filter(
        medecin__specialite__nom__icontains='gyn'
    ).select_related('patient', 'medecin').order_by('-date_heure')

    paginator = Paginator(consultations, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    stats = {
        'aujourdhui': consultations.filter(date_heure__date=today).count(),
        'ce_mois': consultations.filter(date_heure__month=today.month, date_heure__year=today.year).count(),
        'total': consultations.count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Gynécologie'}]
    return render(request, 'gynecologie/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})
