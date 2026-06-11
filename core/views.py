from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from django.db.models import F, Q
from django.contrib.contenttypes.models import ContentType
from datetime import timedelta
from .models import LogActivite


@login_required(login_url='login')
@require_POST
def post_note(request):
    """Vue générique pour poster une note sur n'importe quel objet."""
    app_label  = request.POST.get('app_label')
    model_name = request.POST.get('model_name')
    object_id  = request.POST.get('object_id')
    note       = request.POST.get('note_text', '').strip()
    next_url   = request.POST.get('next', '/')

    if note and app_label and model_name and object_id:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model_name)
            LogActivite.objects.create(
                content_type=ct,
                object_id=int(object_id),
                user=request.user,
                type='note',
                message=note,
            )
        except ContentType.DoesNotExist:
            pass

    return redirect(next_url)


def log_event(obj, user, message, type='system'):
    """Helper à appeler depuis n'importe quelle vue pour logger un événement."""
    ct = ContentType.objects.get_for_model(obj)
    LogActivite.objects.create(
        content_type=ct,
        object_id=obj.pk,
        user=user,
        type=type,
        message=message,
    )


def get_logs(obj, limit=30):
    """Retourne les logs d'un objet."""
    ct = ContentType.objects.get_for_model(obj)
    return LogActivite.objects.filter(
        content_type=ct, object_id=obj.pk
    ).select_related('user')[:limit]


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
    from hospitalisation.models import Hospitalisation
    from pharmacie.models import Medicament
    from laboratoire.models import AnalyseLaboratoire
    from employer.models import Employe
    from soins.models import Soin

    today = timezone.now().date()

    stats = {
        'patients_total': Patient.objects.filter(actif=True).count(),
        'rdv_today': RendezVous.objects.filter(date_heure__date=today).count(),
        'hospitalisations': Hospitalisation.objects.filter(statut='hospitalise').count(),
        'analyses_pending': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'medicaments_alerte': Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count(),
        'employes_actifs': Employe.objects.filter(statut='actif').count(),
        'soins_aujourd_hui': Soin.objects.filter(date_creation__date=today).count(),
    }

    try:
        from modules_permissions.models import get_user_modules
        user_modules = get_user_modules(request.user)
        accessible_codes = set(user_modules.values_list('code', flat=True))
    except Exception:
        user_modules = []
        accessible_codes = set()

    return render(request, 'core/dashboard.html', {
        'stats': stats,
        'today': today,
        'user': request.user,
        'user_modules': user_modules,
        'accessible_codes': accessible_codes,
    })


@login_required(login_url='login')
def kpi_dashboard(request):
    import json as _json
    from patients.models import Patient, RendezVous
    from consultations.models import Consultation
    from hospitalisation.models import Hospitalisation
    from pharmacie.models import Medicament
    from laboratoire.models import AnalyseLaboratoire
    from employer.models import Employe
    from soins.models import Soin
    from medecins.models import Medecin

    today = timezone.now().date()

    stats = {
        'patients_total': Patient.objects.filter(actif=True).count(),
        'patients_today': Patient.objects.filter(date_creation__date=today).count(),
        'consultations_today': Consultation.objects.filter(date_heure__date=today).count(),
        'rdv_today': RendezVous.objects.filter(date_heure__date=today).count(),
        'hospitalisations': Hospitalisation.objects.filter(statut='hospitalise').count(),
        'analyses_pending': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'medicaments_alerte': Medicament.objects.filter(stock_actuel__lte=F('stock_alerte')).count(),
        'employes_actifs': Employe.objects.filter(statut='actif').count(),
        'soins_aujourd_hui': Soin.objects.filter(date_creation__date=today).count(),
        'medecins_actifs': Medecin.objects.filter(actif=True).count(),
        'medecins_total': Medecin.objects.count(),
    }

    try:
        from facturation.models import Facture
        from django.db.models import Sum
        fq = Facture.objects.filter(statut__in=['brouillon', 'emise'])
        stats['factures_impayees_count'] = fq.count()
        m = fq.aggregate(t=Sum('montant_total'))['t'] or 0
        if m >= 1_000_000:
            stats['factures_montant_fmt'] = f"{m/1_000_000:.1f}M F"
        elif m >= 1_000:
            stats['factures_montant_fmt'] = f"{int(m/1_000)}k F"
        else:
            stats['factures_montant_fmt'] = f"{int(m)} F"
    except Exception:
        stats['factures_impayees_count'] = 0
        stats['factures_montant_fmt'] = "0 F"

    stats['patients_anniversaires'] = Patient.objects.filter(
        date_naissance__month=today.month, date_naissance__day=today.day, actif=True
    ).count()
    stats['employes_anniversaires'] = Employe.objects.filter(
        date_naissance__month=today.month, date_naissance__day=today.day
    ).count()

    chart_labels, chart_patients, chart_rdv = [], [], []
    current_monday = today - timedelta(days=today.weekday())
    for i in range(7, -1, -1):
        w_start = current_monday - timedelta(weeks=i)
        w_end = w_start + timedelta(days=6)
        chart_labels.append(w_start.strftime('%d/%m'))
        chart_patients.append(Patient.objects.filter(date_creation__date__range=[w_start, w_end]).count())
        chart_rdv.append(RendezVous.objects.filter(date_heure__date__range=[w_start, w_end]).count())

    chart_data = _json.dumps({'labels': chart_labels, 'patients': chart_patients, 'rdv': chart_rdv})

    rdv_auj = RendezVous.objects.filter(
        date_heure__date=today,
        statut__in=['planifie', 'confirme', 'en_attente', 'en_consultation']
    ).select_related('patient', 'medecin').order_by('date_heure')[:10]

    last_cons = Consultation.objects.select_related('patient', 'medecin').order_by('-date_heure')[:6]

    try:
        from modules_permissions.models import get_user_modules
        user_modules = get_user_modules(request.user)
        accessible_codes = set(user_modules.values_list('code', flat=True))
    except Exception:
        user_modules = []
        accessible_codes = set()

    return render(request, 'core/kpi_dashboard.html', {
        'stats': stats,
        'rdv_auj': rdv_auj,
        'last_cons': last_cons,
        'today': today,
        'user': request.user,
        'user_modules': user_modules,
        'accessible_codes': accessible_codes,
        'chart_data': chart_data,
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
        'nouveaux_30j': Patient.objects.filter(date_creation__date__gte=today - timedelta(days=30)).count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Patients'}]
    return render(request, 'patients/list.html', {'page_obj': page_obj, 'stats': stats, 'breadcrumb': breadcrumb})


@login_required(login_url='login')
def medecins_list(request):
    from medecins.models import Medecin, Specialite
    from django.core.paginator import Paginator

    qs         = Medecin.objects.select_related('specialite').order_by('nom')
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

    return render(request, 'medecins/list.html', {
        'page_obj':          page_obj,
        'specialites':       specialites,
        'kanban_colonnes':   kanban_colonnes,
        'stats': {
            'total':       Medecin.objects.count(),
            'actifs':      Medecin.objects.filter(actif=True).count(),
            'specialites': specialites.count(),
        },
        'q':                 q,
        'specialite_filtre': specialite,
        'statut_filtre':     statut,
        'vue_active':        vue,
    })


@login_required(login_url='login')
def medecin_create(request):
    from medecins.models import Medecin, Specialite, Service
    from django.contrib.auth.models import User
    from django.utils import timezone as tz

    specialites       = Specialite.objects.order_by('nom')
    services          = Service.objects.filter(actif=True).order_by('nom')
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

        if not nom:      errors['nom']      = 'Le nom est obligatoire.'
        if not prenoms:  errors['prenoms']  = 'Les prénoms sont obligatoires.'
        if not telephone: errors['telephone'] = 'Le téléphone est obligatoire.'

        if not errors:
            annee  = tz.now().year
            dernier = Medecin.objects.filter(matricule__startswith=f'MED{annee}').order_by('-matricule').first()
            seq     = (int(dernier.matricule[-4:]) + 1) if dernier else 1
            matricule = f'MED{annee}{seq:04d}'

            dernier_ord = Medecin.objects.filter(ordre_medecin__startswith=f'ORD{annee}').order_by('-ordre_medecin').first()
            seq_ord     = (int(dernier_ord.ordre_medecin[-4:]) + 1) if dernier_ord else 1
            ordre_medecin = f'ORD{annee}{seq_ord:04d}'

            med = Medecin(matricule=matricule, nom=nom, prenoms=prenoms,
                          telephone=telephone, email=email,
                          ordre_medecin=ordre_medecin, actif=actif)
            try: med.taux_honoraire = float(taux_honoraire)
            except ValueError: med.taux_honoraire = 0

            if specialite_pk:
                med.specialite = Specialite.objects.filter(pk=specialite_pk).first()
            if service_pk:
                med.service = Service.objects.filter(pk=service_pk).first()
            if user_pk:
                med.user = User.objects.filter(pk=user_pk).first()
            if request.FILES.get('photo'):
                med.photo = request.FILES['photo']

            med.save()
            messages.success(request, f'Médecin {med} enregistré avec succès (matricule : {med.matricule}).')
            return redirect('medecins_list')

        post_data = request.POST
    else:
        post_data = None

    return render(request, 'medecins/form.html', {
        'mode': 'create',
        'specialites': specialites,
        'services': services,
        'users_disponibles': users_disponibles,
        'errors': errors,
        'post': post_data,
    })


@login_required(login_url='login')
def medecin_edit(request, pk):
    from medecins.models import Medecin, Specialite, Service
    from django.contrib.auth.models import User

    med               = get_object_or_404(Medecin, pk=pk)
    specialites       = Specialite.objects.order_by('nom')
    services          = Service.objects.filter(actif=True).order_by('nom')
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

        if not nom:      errors['nom']      = 'Le nom est obligatoire.'
        if not prenoms:  errors['prenoms']  = 'Les prénoms sont obligatoires.'
        if not telephone: errors['telephone'] = 'Le téléphone est obligatoire.'

        if not errors:
            med.nom = nom; med.prenoms = prenoms
            med.telephone = telephone; med.email = email; med.actif = actif
            try: med.taux_honoraire = float(taux_honoraire)
            except ValueError: med.taux_honoraire = 0

            med.specialite = Specialite.objects.filter(pk=specialite_pk).first() if specialite_pk else None
            med.service    = Service.objects.filter(pk=service_pk).first() if service_pk else None
            med.user       = User.objects.filter(pk=user_pk).first() if user_pk else None

            if request.FILES.get('photo'):
                if med.photo: med.photo.delete(save=False)
                med.photo = request.FILES['photo']
            elif request.POST.get('photo_supprimer') == '1' and med.photo:
                med.photo.delete(save=False)
                med.photo = None

            med.save()
            messages.success(request, f'Médecin {med} mis à jour avec succès.')
            return redirect('medecins_list')

    return render(request, 'medecins/form.html', {
        'mode': 'edit',
        'med': med,
        'specialites': specialites,
        'services': services,
        'users_disponibles': users_disponibles,
        'errors': errors,
    })


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
    from pharmacie.models import Medicament, CommandePharmacies
    from django.core.paginator import Paginator

    # Journalisation des actions POST (create/edit/statut sur CommandePharmacies)
    if request.method == 'POST':
        action = request.POST.get('_action', '')
        commande_pk = request.POST.get('commande_pk', '')
        if action == 'create_commande' and commande_pk:
            try:
                commande = CommandePharmacies.objects.get(pk=int(commande_pk))
                log_event(commande, request.user, 'Commande créée.', 'system')
            except (CommandePharmacies.DoesNotExist, ValueError):
                pass
        elif action == 'edit_commande' and commande_pk:
            try:
                commande = CommandePharmacies.objects.get(pk=int(commande_pk))
                log_event(commande, request.user, 'Commande modifiée.', 'modif')
            except (CommandePharmacies.DoesNotExist, ValueError):
                pass
        elif action == 'statut_commande' and commande_pk:
            try:
                commande = CommandePharmacies.objects.get(pk=int(commande_pk))
                log_event(commande, request.user, f'Statut changé : {commande.get_statut_display()}', 'statut')
            except (CommandePharmacies.DoesNotExist, ValueError):
                pass

    medicaments = Medicament.objects.all().order_by('designation')
    paginator = Paginator(medicaments, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Dernière commande pour le chatter
    derniere_commande = CommandePharmacies.objects.order_by('-date_commande').first()
    logs = get_logs(derniere_commande) if derniere_commande else []

    stats = {
        'total_medicaments': Medicament.objects.count(),
        'valeur_stock': 0,
        'ruptures': 0,
        'commandes_attente': CommandePharmacies.objects.filter(statut__in=['brouillon', 'envoye']).count(),
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Pharmacie'}]
    return render(request, 'pharmacie/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'breadcrumb': breadcrumb,
        'obj': derniere_commande,
        'logs': logs,
    })


@login_required(login_url='login')
def ordonnances_list(request):
    from consultations.models import Ordonnance
    from django.core.paginator import Paginator
    from django.db.models import Q as DbQ

    qs = Ordonnance.objects.select_related(
        'consultation__patient', 'consultation__medecin'
    ).prefetch_related('lignes').order_by('-date_emission')

    q = request.GET.get('q', '').strip()
    statut_filtre = request.GET.get('statut', '')
    type_filtre = request.GET.get('type', '')

    if q:
        qs = qs.filter(
            DbQ(numero__icontains=q) |
            DbQ(consultation__patient__nom__icontains=q) |
            DbQ(consultation__patient__prenoms__icontains=q)
        )
    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
    if type_filtre:
        qs = qs.filter(type_ordonnance=type_filtre)

    stats = {
        'total':     Ordonnance.objects.count(),
        'emises':    Ordonnance.objects.filter(statut='emise').count(),
        'delivrees': Ordonnance.objects.filter(statut='delivree').count(),
        'expirees':  Ordonnance.objects.filter(statut='expiree').count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'pharmacie/ordonnance_list.html', {
        'page_obj': page_obj,
        'q': q,
        'statut_filtre': statut_filtre,
        'type_filtre': type_filtre,
        'stats': stats,
    })


@login_required(login_url='login')
def laboratoire_list(request):
    from laboratoire.models import AnalyseLaboratoire
    from django.core.paginator import Paginator

    analyses = AnalyseLaboratoire.objects.select_related(
        'patient', 'type_examen'
    ).order_by('-date_prelevement')
    paginator = Paginator(analyses, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    stats = {
        'en_cours': AnalyseLaboratoire.objects.filter(statut__in=['recu', 'en_analyse']).count(),
        'resultats_prets': AnalyseLaboratoire.objects.filter(statut__in=['resultat', 'valide']).count(),
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
    from employer.models import Employe, Conge
    from django.core.paginator import Paginator

    # Journalisation des actions POST (create/edit/statut sur Conge ou Employe)
    if request.method == 'POST':
        action = request.POST.get('_action', '')
        conge_pk = request.POST.get('conge_pk', '')
        employe_pk = request.POST.get('employe_pk', '')
        if action == 'create_conge' and conge_pk:
            try:
                conge = Conge.objects.get(pk=int(conge_pk))
                log_event(conge, request.user, 'Congé créé.', 'system')
            except (Conge.DoesNotExist, ValueError):
                pass
        elif action == 'edit_conge' and conge_pk:
            try:
                conge = Conge.objects.get(pk=int(conge_pk))
                log_event(conge, request.user, 'Congé modifié.', 'modif')
            except (Conge.DoesNotExist, ValueError):
                pass
        elif action == 'statut_conge' and conge_pk:
            try:
                conge = Conge.objects.get(pk=int(conge_pk))
                log_event(conge, request.user, f'Statut changé : {conge.get_statut_display()}', 'statut')
            except (Conge.DoesNotExist, ValueError):
                pass
        elif action == 'create_employe' and employe_pk:
            try:
                employe = Employe.objects.get(pk=int(employe_pk))
                log_event(employe, request.user, 'Employé créé.', 'system')
            except (Employe.DoesNotExist, ValueError):
                pass
        elif action == 'edit_employe' and employe_pk:
            try:
                employe = Employe.objects.get(pk=int(employe_pk))
                log_event(employe, request.user, 'Employé modifié.', 'modif')
            except (Employe.DoesNotExist, ValueError):
                pass

    employes = Employe.objects.all().order_by('nom')
    paginator = Paginator(employes, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Dernier congé pour le chatter
    dernier_conge = Conge.objects.select_related('employe').order_by('-date_demande').first()
    logs = get_logs(dernier_conge) if dernier_conge else []

    stats = {
        'total_employes': Employe.objects.count(),
        'employes_actifs': Employe.objects.filter(statut='actif').count(),
        'conges_attente': Conge.objects.filter(statut='demande').count(),
        'taux_presence': 0,
    }
    breadcrumb = [{'title': 'Accueil', 'url': '/'}, {'title': 'Ressources Humaines'}]
    return render(request, 'ressources_humaines/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'breadcrumb': breadcrumb,
        'obj': dernier_conge,
        'logs': logs,
    })


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
def laboratoire_create(request):
    from laboratoire.models import DemandeExamen, LigneDemandeExamen, TypeExamen
    from patients.models import Patient
    from django.contrib.auth.models import User
    from django.utils.dateparse import parse_datetime

    patient_pk = request.GET.get('patient') or request.POST.get('patient_id')
    patient = get_object_or_404(Patient, pk=patient_pk) if patient_pk else None
    types_examens = TypeExamen.objects.order_by('categorie', 'nom')
    techniciens = User.objects.filter(is_active=True).order_by('last_name', 'first_name')

    if request.method == 'POST':
        if not patient:
            messages.error(request, 'Patient requis.')
            return redirect('laboratoire_list')

        action = request.POST.get('action', 'brouillon')
        demande = DemandeExamen(
            patient=patient,
            type_test=request.POST.get('type_test', ''),
            urgent=request.POST.get('urgent') == 'on',
            commentaire=request.POST.get('commentaire', '').strip(),
            statut='demande' if action == 'envoyer' else 'brouillon',
            cree_par=request.user,
        )
        tech_id = request.POST.get('technicien')
        if tech_id:
            try:
                demande.technicien_id = int(tech_id)
            except ValueError:
                pass
        raw_date = request.POST.get('date_prelevement', '').strip()
        if raw_date:
            demande.date_prelevement = parse_datetime(raw_date)
        demande.save()

        total = 0
        i = 0
        while True:
            examen_id = request.POST.get(f'ligne_examen_{i}')
            if examen_id is None:
                break
            if examen_id.strip():
                try:
                    te = TypeExamen.objects.get(pk=int(examen_id))
                    prix = float(request.POST.get(f'ligne_prix_{i}', te.prix) or te.prix)
                    LigneDemandeExamen.objects.create(
                        demande=demande,
                        type_examen=te,
                        libelle=te.nom,
                        prix=prix,
                        instructions=request.POST.get(f'ligne_instructions_{i}', '').strip(),
                    )
                    total += prix
                except (ValueError, TypeExamen.DoesNotExist):
                    pass
            i += 1

        demande.montant_total = total
        demande.save()
        log_event(demande, request.user, 'Demande d\'examen créée.', type='system')
        messages.success(request, f'Demande {demande.numero} créée avec succès.')
        return redirect('laboratoire_list')

    return render(request, 'laboratoire/create_analyse.html', {
        'patient': patient,
        'types_examens': types_examens,
        'techniciens': techniciens,
        'type_test_choices': DemandeExamen.TYPE_TEST,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Laboratoire', 'url': '/laboratoire/'},
            {'title': 'Nouvelle demande'},
        ],
    })


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
            log_event(n, request.user, 'Naissance enregistrée.', 'system')
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
    from patients.forms import RendezVousForm
    from medecins.models import Medecin

    medecins = Medecin.objects.all().order_by('nom')

    if request.method == 'POST':
        form = RendezVousForm(request.POST)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            rdv.save()
            log_event(rdv, request.user, 'Rendez-vous créé.', 'system')
            from patients.utils import save_registres
            save_registres(request, rdv)
            action = request.POST.get('_action', '')
            if action == 'annuler':
                return redirect('gynecologie_rdv')
            from django.urls import reverse
            return redirect(reverse('facturation:create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
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
    from patients.models import Pathologie, TypeVisite
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
        'registre_cpn': None,
        'registre_accouchement': None,
        'registre_postnatale': None,
        'registre_curatif': None,
    })


@login_required(login_url='login')
def gynecologie_rdv_detail(request, pk):
    from patients.forms import RendezVousForm
    from patients.models import RendezVous
    from medecins.models import Medecin
    from django.shortcuts import get_object_or_404

    rdv = get_object_or_404(RendezVous, pk=pk)
    medecins = Medecin.objects.all().order_by('nom')

    try:
        from facturation.models import Facture
        facture_payee = Facture.objects.filter(patient=rdv.patient, statut='payee').exists()
    except Exception:
        facture_payee = False

    consultation = None
    constante = None
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
                'eval_pouls': 'pouls', 'eval_frequence_respiratoire': 'frequence_respiratoire',
                'eval_saturation_oxygene': 'saturation_oxygene', 'eval_glycemie': 'glycemie',
                'eval_albumine': 'albumine', 'eval_perimetre_brachial': 'perimetre_brachial',
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
                log_event(consult_obj, request.user, 'Consultation créée.', type='system')
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
                log_event(rdv, request.user, 'Statut changé : Confirmé', 'statut')
            return redirect('gynecologie_rdv')

        if action in ('en_attente', 'en_consultation'):
            rdv.statut = action
            rdv.save(update_fields=['statut'])
            log_event(rdv, request.user, f'Statut changé : {rdv.get_statut_display()}', 'statut')
            return redirect('gynecologie_rdv_detail', pk=rdv.pk)

        if action == 'terminer':
            rdv.statut = 'termine'
            rdv.save(update_fields=['statut'])
            log_event(rdv, request.user, 'Statut changé : Terminé', 'statut')
            return redirect('gynecologie_rdv')

        if action == 'annuler':
            rdv.statut = 'annule'
            rdv.save(update_fields=['statut'])
            log_event(rdv, request.user, 'Statut changé : Annulé', 'statut')
            return redirect('gynecologie_rdv')

        form = RendezVousForm(request.POST, instance=rdv)
        if form.is_valid():
            rdv = form.save(commit=False)
            code = request.POST.get('code_confirmation', '').strip()
            if code:
                rdv.code_confirmation = code
            from patients.models import TypeVisite
            rdv.cpn_mode_entree = request.POST.get('cpn_mode_entree', '').strip()
            rdv.cpn_mode_entree_autre = request.POST.get('cpn_mode_entree_autre', '').strip()
            cpn_tv_pk = request.POST.get('cpn_type_visite', '').strip()
            if cpn_tv_pk:
                try:
                    rdv.cpn_type_visite = TypeVisite.objects.get(pk=int(cpn_tv_pk))
                except (ValueError, TypeVisite.DoesNotExist):
                    rdv.cpn_type_visite = None
            else:
                rdv.cpn_type_visite = None
            rdv.cur_mode_entree = request.POST.get('cur_mode_entree', '').strip()
            rdv.cur_mode_entree_autre = request.POST.get('cur_mode_entree_autre', '').strip()
            cur_tv_pk = request.POST.get('cur_type_visite', '').strip()
            if cur_tv_pk:
                try:
                    rdv.cur_type_visite = TypeVisite.objects.get(pk=int(cur_tv_pk))
                except (ValueError, TypeVisite.DoesNotExist):
                    rdv.cur_type_visite = None
            else:
                rdv.cur_type_visite = None
            rdv.save()
            log_event(rdv, request.user, 'Rendez-vous modifié.', 'modif')
            from patients.utils import save_registres
            save_registres(request, rdv)
            if action == 'créer une facture':
                from django.urls import reverse
                return redirect(reverse('facturation:create') + f'?patient={rdv.patient.pk}&rdv={rdv.pk}')
            return redirect('gynecologie_rdv')
    else:
        form = RendezVousForm(instance=rdv)

    # Navigation précédent/suivant dans la liste gynécologie
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
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Rendez-vous', 'url': '/gynecologie/rdv/'},
        {'title': rdv.code_rdv or rdv.patient.code_patient},
    ]
    from patients.models import Pathologie, TypeVisite, RegistreCPN, RegistreAccouchement, RegistrePostnatale, RegistreCuratif
    def _get_reg(Model):
        try:
            return Model.objects.get(rdv=rdv)
        except Model.DoesNotExist:
            return None

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
        'registre_cpn':          _get_reg(RegistreCPN),
        'registre_accouchement': _get_reg(RegistreAccouchement),
        'registre_postnatale':   _get_reg(RegistrePostnatale),
        'registre_curatif':      _get_reg(RegistreCuratif),
        'obj': rdv,
        'logs': get_logs(rdv),
    })


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

    # --- Filtre rapide (today par défaut si aucun filtre ni plage de dates) ---
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

    # --- Plage de dates ---
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

    # --- Tri selon regroupement ---
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
    from patients.models import Patient
    from django.core.paginator import Paginator
    from datetime import date as _date

    q          = request.GET.get('q', '').strip()
    filter_val = request.GET.get('filter', '')
    group_val  = request.GET.get('group', '')

    patients = Patient.objects.filter(
        rendez_vous__departement='gynecologie_cpn'
    ).distinct().order_by('nom', 'prenoms')

    if q:
        patients = patients.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(code_patient__icontains=q) | Q(telephone__icontains=q)
        )

    # --- Filtres patients ---
    today = _date.today()
    if filter_val == 'femme':
        patients = patients.filter(sexe='F')
    elif filter_val == 'homme':
        patients = patients.filter(sexe='M')
    elif filter_val == 'mineur':
        cutoff = today.replace(year=today.year - 18)
        patients = patients.filter(date_naissance__gt=cutoff)
    elif filter_val == 'adulte':
        cutoff_18 = today.replace(year=today.year - 18)
        cutoff_60 = today.replace(year=today.year - 60)
        patients = patients.filter(date_naissance__lte=cutoff_18, date_naissance__gt=cutoff_60)
    elif filter_val == 'senior':
        cutoff = today.replace(year=today.year - 60)
        patients = patients.filter(date_naissance__lte=cutoff)

    # --- Tri selon regroupement ---
    if group_val == 'sexe':
        patients = patients.order_by('sexe', 'nom', 'prenoms')
    elif group_val == 'age':
        patients = patients.order_by('date_naissance')

    paginator = Paginator(patients, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    breadcrumb = [
        {'title': 'Gynécologie', 'url': '/gynecologie/'},
        {'title': 'Patients'},
    ]
    return render(request, 'gynecologie/list.html', {'page_obj': page_obj, 'breadcrumb': breadcrumb})
