from datetime import date, timedelta
import io

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse, HttpResponse

from django.utils import timezone
from .models import (Employe, Fonction, Grade, TypeContrat,
                     DocumentEmploye, InfoSupplementaire, AlerteContrat,
                     AlerteDocument, HistoriqueEmploye, Conge, DOCS_OBLIGATOIRES)
from medecins.models import Service

RH_MANAGE_GROUPS = {'MÃ©decin Chef', 'MÃ©decin Chef Adjoint', 'Administrateur', 'Directeur', 'RH'}

LABELS_DOCS = {'cni': "Carte d'identitÃ©", 'contrat': 'Contrat signÃ©', 'diplome': 'DiplÃ´me'}

_EMPTY_FORM = {
    'nom': '', 'prenoms': '', 'sexe': 'M', 'date_naissance': '',
    'lieu_naissance': '', 'nationalite': 'Ivoirienne', 'situation_matrimoniale': '',
    'nombre_enfants': '0', 'telephone': '', 'telephone2': '', 'email': '',
    'adresse': '', 'service': '', 'fonction': '', 'grade': '', 'type_contrat': '',
    'date_embauche': '', 'date_fin_contrat': '', 'salaire_base': '', 'statut': 'actif',
    'notes': '',
}


def _employe_to_form(e):
    fmt = lambda d: d.strftime('%Y-%m-%d') if d else ''
    return {
        'nom':                    e.nom or '',
        'prenoms':                e.prenoms or '',
        'sexe':                   e.sexe or 'M',
        'date_naissance':         fmt(e.date_naissance),
        'lieu_naissance':         e.lieu_naissance or '',
        'nationalite':            e.nationalite or 'Ivoirienne',
        'situation_matrimoniale': e.situation_matrimoniale or '',
        'nombre_enfants':         str(e.nombre_enfants) if e.nombre_enfants is not None else '0',
        'telephone':              e.telephone or '',
        'telephone2':             e.telephone2 or '',
        'email':                  e.email or '',
        'adresse':                e.adresse or '',
        'service':                str(e.service_id)      if e.service_id      else '',
        'fonction':               str(e.fonction_id)     if e.fonction_id     else '',
        'grade':                  str(e.grade_id)        if e.grade_id        else '',
        'type_contrat':           str(e.type_contrat_id) if e.type_contrat_id else '',
        'date_embauche':          fmt(e.date_embauche),
        'date_fin_contrat':       fmt(e.date_fin_contrat),
        'salaire_base':           str(int(e.salaire_base)) if e.salaire_base else '',
        'statut':                 e.statut or 'actif',
        'notes':                  e.notes or '',
    }


def can_manage_rh(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=RH_MANAGE_GROUPS).exists()


def _rh_selects(user):
    return {
        'fonctions':     Fonction.objects.all(),
        'grades':        Grade.objects.all(),
        'types_contrat': TypeContrat.objects.all(),
        'services':      Service.objects.filter(actif=True).order_by('nom'),
        'can_manage':    can_manage_rh(user),
    }


def _enregistrer_historique(employe, type_changement, ancienne, nouvelle, note, user):
    if ancienne != nouvelle:
        HistoriqueEmploye.objects.create(
            employe=employe,
            type_changement=type_changement,
            ancienne_valeur=str(ancienne),
            nouvelle_valeur=str(nouvelle),
            note=note,
            fait_par=user,
        )


# â”€â”€ Dashboard â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def rh_dashboard(request):
    today = date.today()

    total    = Employe.objects.count()
    actifs   = Employe.objects.filter(statut='actif').count()
    suspendus = Employe.objects.filter(statut='suspendu').count()
    quittes  = Employe.objects.filter(statut='quitte').count()

    # RÃ©partition par type de contrat
    par_contrat = (
        Employe.objects.filter(statut='actif')
        .values('type_contrat__nom')
        .annotate(n=Count('id'))
        .order_by('-n')
    )

    # RÃ©partition par service
    par_service = (
        Employe.objects.filter(statut='actif')
        .values('service__nom')
        .annotate(n=Count('id'))
        .order_by('-n')
    )

    # Contrats expirant dans 90 jours
    fin_90j = (
        Employe.objects.filter(
            statut='actif',
            date_fin_contrat__gte=today,
            date_fin_contrat__lte=today + timedelta(days=90),
        )
        .select_related('service', 'type_contrat')
        .order_by('date_fin_contrat')
    )

    # Pyramide des Ã¢ges (tranches)
    tranches = [
        ('<25 ans',  0,  24),
        ('25-34',   25,  34),
        ('35-44',   35,  44),
        ('45-54',   45,  54),
        ('55+',     55, 200),
    ]
    pyramide = []
    for label, amin, amax in tranches:
        n = sum(
            1 for e in Employe.objects.filter(statut='actif', date_naissance__isnull=False)
            if amin <= e.age <= amax
        )
        pyramide.append({'label': label, 'n': n})

    # Docs manquants
    employes_docs_manquants = [
        e for e in Employe.objects.filter(statut='actif').prefetch_related('documents')
        if e.docs_manquants
    ]

    # ── Turnover ─────────────────────────────────────────────────────────────
    annee = today.year
    entrees_annee = Employe.objects.filter(date_embauche__year=annee).count()
    # Approximation : départs = employés quittés dont la fiche a été modifiée cette année
    departs_annee = Employe.objects.filter(statut='quitte', modifie_le__year=annee).count()
    # Taux de turnover (formule simplifiée BTP/RH) : départs / effectif actif * 100
    taux_turnover = round(departs_annee / actifs * 100, 1) if actifs > 0 else 0
    # Ancienneté moyenne
    anciennete_moy = None
    emp_avec_date = Employe.objects.filter(statut='actif', date_embauche__isnull=False)
    if emp_avec_date.exists():
        total_annees = sum(e.anciennete['annees'] for e in emp_avec_date)
        anciennete_moy = round(total_annees / emp_avec_date.count(), 1)

    return render(request, 'employer/dashboard.html', {
        'total': total, 'actifs': actifs, 'suspendus': suspendus, 'quittes': quittes,
        'par_contrat': list(par_contrat),
        'par_service': list(par_service),
        'fin_90j': fin_90j,
        'pyramide': pyramide,
        'employes_docs_manquants': employes_docs_manquants,
        'annee':          annee,
        'entrees_annee':  entrees_annee,
        'departs_annee':  departs_annee,
        'taux_turnover':  taux_turnover,
        'anciennete_moy': anciennete_moy,
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ Liste â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_list(request):
    qs = Employe.objects.select_related('service', 'fonction', 'grade', 'type_contrat')

    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    f_statut  = request.GET.get('statut', '').strip()

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q)
        )
    if f_service:
        qs = qs.filter(service_id=f_service)
    if f_statut:
        qs = qs.filter(statut=f_statut)

    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))

    stats = {
        'total':     Employe.objects.count(),
        'actifs':    Employe.objects.filter(statut='actif').count(),
        'suspendus': Employe.objects.filter(statut='suspendu').count(),
        'quittes':   Employe.objects.filter(statut='quitte').count(),
    }

    return render(request, 'employer/list.html', {
        'page_obj':  page_obj,
        'stats':     stats,
        'services':  Service.objects.filter(actif=True).order_by('nom'),
        'statuts':   Employe.STATUT_CHOICES,
        'q':         q,
        'f_service': f_service,
        'f_statut':  f_statut,
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ DÃ©tail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_detail(request, pk):
    employe = get_object_or_404(
        Employe.objects.select_related('service', 'fonction', 'grade', 'type_contrat')
                       .prefetch_related('documents', 'historique__fait_par'),
        pk=pk
    )
    from .models import TYPE_DOC_CHOICES
    docs_manquants = [
        {'code': d, 'label': LABELS_DOCS.get(d, d)} for d in employe.docs_manquants
    ]
    conges = Conge.objects.filter(employe=employe).order_by('-date_demande')[:10]
    return render(request, 'employer/detail.html', {
        'employe':          employe,
        'docs':             employe.documents.select_related('ajoute_par').all(),
        'infos_supp':       employe.infos_supp.all(),
        'type_doc_choices': TYPE_DOC_CHOICES,
        'docs_manquants':   docs_manquants,
        'historique':       employe.historique.all()[:30],
        'conges':           conges,
        'can_manage':       can_manage_rh(request.user),
    })


# â”€â”€ CrÃ©er â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_nouveau(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    ctx = _rh_selects(request.user)
    form_data = dict(_EMPTY_FORM)
    if request.method == 'POST':
        employe = _save_employe(request, None)
        if employe:
            HistoriqueEmploye.objects.create(
                employe=employe, type_changement='creation',
                nouvelle_valeur=employe.nom_complet, fait_par=request.user,
            )
            messages.success(request, f'EmployÃ© {employe.nom_complet} crÃ©Ã© avec succÃ¨s.')
            return redirect('rh_detail', pk=employe.pk)
        form_data = request.POST
    return render(request, 'employer/form.html', {
        **ctx, 'employe': None, 'form_data': form_data, 'form_errors': {},
    })


# â”€â”€ Modifier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_modifier(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    employe = get_object_or_404(Employe, pk=pk)
    ctx = _rh_selects(request.user)
    form_data = _employe_to_form(employe)
    if request.method == 'POST':
        # Snapshot avant modif
        old_statut  = employe.statut
        old_salaire = str(int(employe.salaire_base)) if employe.salaire_base else '0'
        old_service = str(employe.service) if employe.service else ''

        updated = _save_employe(request, employe)
        if updated:
            _enregistrer_historique(updated, 'statut', old_statut, updated.statut,
                                    '', request.user)
            new_salaire = str(int(updated.salaire_base)) if updated.salaire_base else '0'
            _enregistrer_historique(updated, 'salaire', old_salaire + ' FCFA',
                                    new_salaire + ' FCFA', '', request.user)
            new_service = str(updated.service) if updated.service else ''
            _enregistrer_historique(updated, 'service', old_service, new_service,
                                    '', request.user)
            messages.success(request, 'Dossier mis Ã  jour avec succÃ¨s.')
            return redirect('rh_detail', pk=employe.pk)
        form_data = request.POST
    return render(request, 'employer/form.html', {
        **ctx, 'employe': employe, 'form_data': form_data, 'form_errors': {},
    })


def _save_employe(request, employe):
    p = request.POST
    nom           = p.get('nom', '').strip()
    prenoms       = p.get('prenoms', '').strip()
    date_embauche = p.get('date_embauche', '').strip()
    if not nom or not prenoms:
        messages.error(request, 'Le nom et les prÃ©noms sont obligatoires.')
        return None
    if not date_embauche:
        messages.error(request, "La date d'embauche est obligatoire.")
        return None

    if employe is None:
        employe = Employe()

    employe.nom     = nom
    employe.prenoms = prenoms
    employe.sexe    = p.get('sexe', '')
    employe.date_naissance         = p.get('date_naissance') or None
    employe.lieu_naissance         = p.get('lieu_naissance', '').strip()
    employe.nationalite            = p.get('nationalite', 'Ivoirienne').strip() or 'Ivoirienne'
    employe.situation_matrimoniale = p.get('situation_matrimoniale', '')
    employe.nombre_enfants         = int(p.get('nombre_enfants') or 0)
    employe.telephone  = p.get('telephone', '').strip()
    employe.telephone2 = p.get('telephone2', '').strip()
    employe.email      = p.get('email', '').strip()
    employe.adresse    = p.get('adresse', '').strip()

    def fk_or_none(model, pk_str):
        try:
            return model.objects.get(pk=int(pk_str)) if pk_str else None
        except (model.DoesNotExist, ValueError, TypeError):
            return None

    employe.service      = fk_or_none(Service, p.get('service'))
    employe.fonction     = fk_or_none(Fonction, p.get('fonction'))
    employe.grade        = fk_or_none(Grade, p.get('grade'))
    employe.type_contrat = fk_or_none(TypeContrat, p.get('type_contrat'))
    employe.date_embauche    = p.get('date_embauche') or None
    employe.date_fin_contrat = p.get('date_fin_contrat') or None
    employe.salaire_base     = p.get('salaire_base') or 0
    employe.statut           = p.get('statut', 'actif')
    employe.notes            = p.get('notes', '').strip()

    if 'photo' in request.FILES:
        if employe.photo:
            employe.photo.delete(save=False)
        employe.photo = request.FILES['photo']

    employe.save()
    return employe


# â”€â”€ Renouvellement de contrat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_renouveler(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        nouvelle_date = request.POST.get('date_fin_contrat', '').strip()
        if not nouvelle_date:
            messages.error(request, 'La nouvelle date de fin de contrat est obligatoire.')
            return redirect('rh_detail', pk=pk)
        ancienne = employe.date_fin_contrat.strftime('%d/%m/%Y') if employe.date_fin_contrat else 'â€”'
        employe.date_fin_contrat = nouvelle_date
        employe.save()
        # RÃ©initialiser les alertes
        AlerteContrat.objects.filter(employe=employe).delete()
        # Historique
        HistoriqueEmploye.objects.create(
            employe=employe,
            type_changement='contrat',
            ancienne_valeur=ancienne,
            nouvelle_valeur=date.fromisoformat(nouvelle_date).strftime('%d/%m/%Y'),
            fait_par=request.user,
        )
        messages.success(request, 'Contrat renouvelÃ© avec succÃ¨s.')
    return redirect('rh_detail', pk=pk)


# â”€â”€ Export Excel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_export_excel(request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    qs = Employe.objects.select_related('service', 'fonction', 'grade', 'type_contrat')
    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    f_statut  = request.GET.get('statut', '').strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q))
    if f_service:
        qs = qs.filter(service_id=f_service)
    if f_statut:
        qs = qs.filter(statut=f_statut)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EmployÃ©s"

    header_fill = PatternFill('solid', fgColor='4A7236')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    thin = Border(
        left=Side(style='thin', color='D0D0D0'), right=Side(style='thin', color='D0D0D0'),
        top=Side(style='thin', color='D0D0D0'),  bottom=Side(style='thin', color='D0D0D0'),
    )

    headers = [
        'Matricule', 'Nom', 'PrÃ©noms', 'Sexe', 'Date naissance', 'NationalitÃ©',
        'TÃ©lÃ©phone', 'Email', 'Service', 'Fonction', 'Grade', 'Type contrat',
        'Date embauche', 'Date fin contrat', 'AnciennetÃ©', 'Salaire base', 'Statut',
    ]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = thin
    ws.row_dimensions[1].height = 20

    alt_fill = PatternFill('solid', fgColor='EDF6E8')
    for row_n, emp in enumerate(qs, 2):
        fill = alt_fill if row_n % 2 == 0 else PatternFill('solid', fgColor='FFFFFF')
        anc = emp.anciennete
        row = [
            emp.matricule, emp.nom, emp.prenoms,
            'M' if emp.sexe == 'M' else 'F',
            emp.date_naissance.strftime('%d/%m/%Y') if emp.date_naissance else '',
            emp.nationalite,
            emp.telephone, emp.email,
            emp.service.nom if emp.service else '',
            emp.fonction.nom if emp.fonction else '',
            emp.grade.nom if emp.grade else '',
            emp.type_contrat.nom if emp.type_contrat else '',
            emp.date_embauche.strftime('%d/%m/%Y') if emp.date_embauche else '',
            emp.date_fin_contrat.strftime('%d/%m/%Y') if emp.date_fin_contrat else '',
            anc['label'],
            int(emp.salaire_base) if emp.salaire_base else 0,
            emp.get_statut_display(),
        ]
        for col, val in enumerate(row, 1):
            cell = ws.cell(row=row_n, column=col, value=val)
            cell.fill = fill
            cell.border = thin
            cell.alignment = Alignment(vertical='center')

    for col in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].auto_size = True
        ws.column_dimensions[get_column_letter(col)].width = max(12, 18)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    resp = HttpResponse(buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="employes.xlsx"'
    return resp


# â”€â”€ Export PDF (fiche individuelle) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_fiche_pdf(request, pk):
    employe = get_object_or_404(
        Employe.objects.select_related('service', 'fonction', 'grade', 'type_contrat')
                       .prefetch_related('documents'),
        pk=pk
    )
    return render(request, 'employer/fiche_print.html', {
        'employe': employe,
        'today': date.today(),
    })


# â”€â”€ Import Excel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_import(request):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        fichier = request.FILES.get('fichier')
        if not fichier:
            messages.error(request, 'Veuillez sÃ©lectionner un fichier Excel.')
            return redirect('rh_import')
        try:
            import openpyxl
            wb = openpyxl.load_workbook(fichier, data_only=True)
            ws = wb.active
            created = 0
            errors = []
            for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not row or not row[0]:
                    continue
                try:
                    nom     = str(row[0]).strip() if row[0] else ''
                    prenoms = str(row[1]).strip() if len(row) > 1 and row[1] else ''
                    if not nom or not prenoms:
                        errors.append(f'Ligne {i} : nom ou prÃ©noms manquants.')
                        continue
                    date_emb_raw = row[2] if len(row) > 2 else None
                    if hasattr(date_emb_raw, 'date'):
                        date_emb = date_emb_raw.date()
                    elif date_emb_raw:
                        date_emb = date.fromisoformat(str(date_emb_raw)[:10])
                    else:
                        errors.append(f'Ligne {i} : date d\'embauche manquante.')
                        continue

                    service_nom = str(row[3]).strip() if len(row) > 3 and row[3] else ''
                    contrat_nom = str(row[4]).strip() if len(row) > 4 and row[4] else ''
                    statut_val  = str(row[5]).strip().lower() if len(row) > 5 and row[5] else 'actif'

                    service = Service.objects.filter(nom__iexact=service_nom).first() if service_nom else None
                    contrat = TypeContrat.objects.filter(nom__iexact=contrat_nom).first() if contrat_nom else None

                    emp = Employe(
                        nom=nom, prenoms=prenoms, date_embauche=date_emb,
                        service=service, type_contrat=contrat,
                        statut=statut_val if statut_val in ('actif', 'suspendu', 'quitte') else 'actif',
                    )
                    emp.save()
                    HistoriqueEmploye.objects.create(
                        employe=emp, type_changement='creation',
                        nouvelle_valeur='Import Excel', fait_par=request.user,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f'Ligne {i} : {e}')

            if created:
                messages.success(request, f'{created} employÃ©(s) importÃ©(s) avec succÃ¨s.')
            for err in errors[:10]:
                messages.warning(request, err)
        except Exception as e:
            messages.error(request, f'Erreur lecture fichier : {e}')
        return redirect('ressources_humaines_list')

    return render(request, 'employer/import.html', {
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ Organigramme â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def rh_organigramme(request):
    employes = (
        Employe.objects.filter(statut='actif')
        .select_related('service', 'fonction', 'grade')
        .order_by('service__nom', 'nom')
    )
    # Grouper par service
    services = {}
    sans_service = []
    for e in employes:
        if e.service:
            key = e.service.nom
            services.setdefault(key, []).append(e)
        else:
            sans_service.append(e)

    return render(request, 'employer/organigramme.html', {
        'services': services,
        'sans_service': sans_service,
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ Documents â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_doc_upload(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        titre   = request.POST.get('titre', '').strip()
        fichier = request.FILES.get('fichier')
        if not titre or not fichier:
            messages.error(request, 'Le titre et le fichier sont obligatoires.')
        else:
            date_exp = request.POST.get('date_expiration', '').strip() or None
            DocumentEmploye.objects.create(
                employe         = employe,
                type_document   = request.POST.get('type_document', 'autre'),
                titre           = titre,
                fichier         = fichier,
                date_expiration = date_exp,
                notes           = request.POST.get('doc_notes', '').strip(),
                ajoute_par      = request.user,
            )
            messages.success(request, f'Document Â« {titre} Â» ajoutÃ©.')
    return redirect('rh_detail', pk=pk)


@login_required(login_url='login')
def employe_doc_delete(request, pk, doc_pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    doc = get_object_or_404(DocumentEmploye, pk=doc_pk, employe_id=pk)
    if request.method == 'POST':
        titre = doc.titre
        if doc.fichier:
            doc.fichier.delete(save=False)
        doc.delete()
        messages.success(request, f'Document Â« {titre} Â» supprimÃ©.')
    return redirect('rh_detail', pk=pk)


# â”€â”€ Informations supplÃ©mentaires â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_info_save(request, pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        cle    = request.POST.get('cle', '').strip()
        valeur = request.POST.get('valeur', '').strip()
        if cle and valeur:
            InfoSupplementaire.objects.create(employe=employe, cle=cle, valeur=valeur)
            messages.success(request, f'Information Â« {cle} Â» ajoutÃ©e.')
        else:
            messages.error(request, 'Le champ et la valeur sont obligatoires.')
    return redirect('rh_detail', pk=pk)


@login_required(login_url='login')
def employe_info_delete(request, pk, info_pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    info = get_object_or_404(InfoSupplementaire, pk=info_pk, employe_id=pk)
    if request.method == 'POST':
        cle = info.cle
        info.delete()
        messages.success(request, f'Information Â« {cle} Â» supprimÃ©e.')
    return redirect('rh_detail', pk=pk)



# â”€â”€ Annuaire â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def rh_annuaire(request):
    qs = Employe.objects.filter(statut='actif').select_related('service', 'fonction')
    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(fonction__nom__icontains=q)
        )
    if f_service:
        qs = qs.filter(service_id=f_service)
    return render(request, 'employer/annuaire.html', {
        'employes':  qs.order_by('service__nom', 'nom'),
        'services':  Service.objects.filter(actif=True).order_by('nom'),
        'q':         q,
        'f_service': f_service,
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ Alertes contrat â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def alerte_marquer_lue(request, alerte_id):
    if request.method == 'POST':
        AlerteContrat.objects.filter(pk=alerte_id).update(lue=True)
    return JsonResponse({'ok': True})


@login_required(login_url='login')
def alertes_tout_lire(request):
    if request.method == 'POST':
        AlerteContrat.objects.filter(lue=False).update(lue=True)
        AlerteDocument.objects.filter(lue=False).update(lue=True)
    return JsonResponse({'ok': True})


# â”€â”€ Alertes document â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def alerte_doc_lue(request, alerte_id):
    if request.method == 'POST':
        AlerteDocument.objects.filter(pk=alerte_id).update(lue=True)
    return JsonResponse({'ok': True})
