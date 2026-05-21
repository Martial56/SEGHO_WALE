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
from utilisateur.models import Departement as Service
from .forms import FonctionForm, GradeForm, TypeContratForm

RH_MANAGE_GROUPS = {'Médecin Chef', 'Médecin Chef Adjoint', 'Administrateur', 'Directeur', 'RH'}

LABELS_DOCS = {'cni': "Carte d'identité", 'contrat': 'Contrat signé', 'diplome': 'Diplôme'}

_EMPTY_FORM = {
    'nom': '', 'prenoms': '', 'sexe': 'M', 'date_naissance': '',
    'lieu_naissance': '', 'nationalite': 'Ivoirienne', 'situation_matrimoniale': '',
    'nombre_enfants': '0', 'telephone': '', 'telephone2': '', 'email': '',
    'adresse': '', 'services': [], 'fonction': '', 'grade': '', 'type_contrat': '',
    'date_embauche': '', 'date_fin_contrat': '', 'salaire_base': '', 'statut': 'actif',
    'notes': '', 'numero_ordre': '',
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
        'services':               list(e.services.values_list('pk', flat=True)),
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

    # Répartition par type de contrat
    par_contrat = (
        Employe.objects.filter(statut='actif')
        .values('type_contrat__nom')
        .annotate(n=Count('id'))
        .order_by('-n')
    )

    # Répartition par service
    par_service = (
        Employe.objects.filter(statut='actif')
        .values('services__nom')
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
        .prefetch_related('services')
        .select_related('type_contrat')
        .order_by('date_fin_contrat')
    )

    # Pyramide des âges (tranches)
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
    qs = Employe.objects.prefetch_related('services').select_related('fonction', 'grade', 'type_contrat')

    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    f_statut  = request.GET.get('statut', '').strip()

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q)
        )
    if f_service:
        qs = qs.filter(services__pk=f_service)
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


# â”€â”€ Détail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_detail(request, pk):
    employe = get_object_or_404(
        Employe.objects.prefetch_related('services', 'documents', 'historique__fait_par')
                       .select_related('fonction', 'grade', 'type_contrat'),
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


# â”€â”€ Créer â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            messages.success(request, f'Employé {employe.nom_complet} créé avec succès.')
            return redirect('employer:rh_detail', pk=employe.pk)
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
        old_service = ', '.join(s.nom for s in employe.services.all())

        updated = _save_employe(request, employe)
        if updated:
            _enregistrer_historique(updated, 'statut', old_statut, updated.statut,
                                    '', request.user)
            new_salaire = str(int(updated.salaire_base)) if updated.salaire_base else '0'
            _enregistrer_historique(updated, 'salaire', old_salaire + ' FCFA',
                                    new_salaire + ' FCFA', '', request.user)
            new_service = ', '.join(s.nom for s in updated.services.all())
            _enregistrer_historique(updated, 'service', old_service, new_service,
                                    '', request.user)
            messages.success(request, 'Dossier mis à jour avec succès.')
            return redirect('employer:rh_detail', pk=employe.pk)
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
        messages.error(request, 'Le nom et les prénoms sont obligatoires.')
        return None
    if not date_embauche:
        messages.error(request, "La date d'embauche est obligatoire.")
        return None

    date_naissance_raw = p.get('date_naissance', '').strip()
    if date_naissance_raw:
        try:
            from datetime import date as _date
            dn = _date.fromisoformat(date_naissance_raw)
            annee_courante = _date.today().year
            if dn.year < 1900 or dn.year > annee_courante:
                messages.error(request, f"La date de naissance doit être comprise entre 1900 et {annee_courante}.")
                return None
        except ValueError:
            messages.error(request, "Date de naissance invalide.")
            return None

    if employe is None:
        employe = Employe()
        numero_ordre_raw = p.get('numero_ordre', '').strip()
        if numero_ordre_raw:
            try:
                employe.numero_ordre = int(numero_ordre_raw)
            except ValueError:
                pass

    employe.nom     = nom
    employe.prenoms = prenoms
    employe.sexe    = p.get('sexe', '')
    employe.date_naissance         = date_naissance_raw or None
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

    # M2M : doit être assigné après save()
    service_pks = [pk for pk in p.getlist('services') if pk]
    employe.services.set(Service.objects.filter(pk__in=service_pks))

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
            return redirect('employer:rh_detail', pk=pk)
        ancienne = employe.date_fin_contrat.strftime('%d/%m/%Y') if employe.date_fin_contrat else 'â€”'
        employe.date_fin_contrat = nouvelle_date
        employe.save()
        # Réinitialiser les alertes
        AlerteContrat.objects.filter(employe=employe).delete()
        # Historique
        HistoriqueEmploye.objects.create(
            employe=employe,
            type_changement='contrat',
            ancienne_valeur=ancienne,
            nouvelle_valeur=date.fromisoformat(nouvelle_date).strftime('%d/%m/%Y'),
            fait_par=request.user,
        )
        messages.success(request, 'Contrat renouvelé avec succès.')
    return redirect('employer:rh_detail', pk=pk)


# â”€â”€ Export Excel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def employe_export_excel(request):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    qs = Employe.objects.prefetch_related('services').select_related('fonction', 'grade', 'type_contrat')
    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    f_statut  = request.GET.get('statut', '').strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(prenoms__icontains=q) | Q(matricule__icontains=q))
    if f_service:
        qs = qs.filter(services__pk=f_service)
    if f_statut:
        qs = qs.filter(statut=f_statut)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Employés"

    header_fill = PatternFill('solid', fgColor='4A7236')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    thin = Border(
        left=Side(style='thin', color='D0D0D0'), right=Side(style='thin', color='D0D0D0'),
        top=Side(style='thin', color='D0D0D0'),  bottom=Side(style='thin', color='D0D0D0'),
    )

    headers = [
        'Matricule', 'Nom', 'Prénoms', 'Sexe', 'Date naissance', 'Nationalité',
        'Téléphone', 'Email', 'Service', 'Fonction', 'Grade', 'Type contrat',
        'Date embauche', 'Date fin contrat', 'Ancienneté', 'Salaire base', 'Statut',
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
            ', '.join(s.nom for s in emp.services.all()),
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
        Employe.objects.prefetch_related('services', 'documents')
                       .select_related('fonction', 'grade', 'type_contrat'),
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
            messages.error(request, 'Veuillez sélectionner un fichier Excel.')
            return redirect('employer:rh_import')
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
                        errors.append(f'Ligne {i} : nom ou prénoms manquants.')
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
                        type_contrat=contrat,
                        statut=statut_val if statut_val in ('actif', 'suspendu', 'quitte') else 'actif',
                    )
                    emp.save()
                    if service:
                        emp.services.add(service)
                    HistoriqueEmploye.objects.create(
                        employe=emp, type_changement='creation',
                        nouvelle_valeur='Import Excel', fait_par=request.user,
                    )
                    created += 1
                except Exception as e:
                    errors.append(f'Ligne {i} : {e}')

            if created:
                messages.success(request, f'{created} employé(s) importé(s) avec succès.')
            for err in errors[:10]:
                messages.warning(request, err)
        except Exception as e:
            messages.error(request, f'Erreur lecture fichier : {e}')
        return redirect('employer:ressources_humaines_list')

    return render(request, 'employer/import.html', {
        'can_manage': can_manage_rh(request.user),
    })


# â”€â”€ Organigramme â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def rh_organigramme(request):
    employes = (
        Employe.objects.filter(statut='actif')
        .prefetch_related('services')
        .select_related('fonction', 'grade')
        .order_by('nom')
    )
    # Grouper par service (un employé peut apparaître dans plusieurs services)
    services = {}
    sans_service = []
    for e in employes:
        svc_list = list(e.services.all())
        if svc_list:
            for svc in svc_list:
                services.setdefault(svc.nom, []).append(e)
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
            messages.success(request, f'Document « {titre} » ajouté.')
    return redirect('employer:rh_detail', pk=pk)


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
        messages.success(request, f'Document « {titre} » supprimé.')
    return redirect('employer:rh_detail', pk=pk)


# â”€â”€ Informations supplémentaires â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            messages.success(request, f'Information « {cle} » ajoutée.')
        else:
            messages.error(request, 'Le champ et la valeur sont obligatoires.')
    return redirect('employer:rh_detail', pk=pk)


@login_required(login_url='login')
def employe_info_delete(request, pk, info_pk):
    if not can_manage_rh(request.user):
        raise PermissionDenied
    info = get_object_or_404(InfoSupplementaire, pk=info_pk, employe_id=pk)
    if request.method == 'POST':
        cle = info.cle
        info.delete()
        messages.success(request, f'Information « {cle} » supprimée.')
    return redirect('employer:rh_detail', pk=pk)



# â”€â”€ Annuaire â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@login_required(login_url='login')
def rh_annuaire(request):
    qs = Employe.objects.filter(statut='actif').prefetch_related('services').select_related('fonction')
    q         = request.GET.get('q', '').strip()
    f_service = request.GET.get('service', '').strip()
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(fonction__nom__icontains=q)
        )
    if f_service:
        qs = qs.filter(services__pk=f_service)
    return render(request, 'employer/annuaire.html', {
        'employes':  qs.order_by('nom'),
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


# ── Configuration : Spécialités, Départements, Diplômes ─────────────────────

from django.views.decorators.http import require_POST
from django.http import JsonResponse as _JsonResponse
from utilisateur.models import Specialite, Diplome
from utilisateur.models import Employe as UtilisateurEmploye
from utilisateur.forms import SpecialiteForm, DiplomeForm, DepartementForm


@login_required
def specialite_list(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    qs = Specialite.objects.all()
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employer/config/specialites_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Specialite.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def specialite_create(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    if request.method == 'POST':
        form = SpecialiteForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Spécialité « {obj.nom} » créée.')
            return redirect('employer:specialites')
    else:
        form = SpecialiteForm()
    return render(request, 'employer/config/specialite_form.html', {
        'form': form,
        'titre': 'Nouvelle spécialité',
        'active_menu': 'config',
    })


@login_required
def specialite_edit(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Specialite, pk=pk)
    if request.method == 'POST':
        form = SpecialiteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Spécialité mise à jour.')
            return redirect('employer:specialites')
    else:
        form = SpecialiteForm(instance=obj)
    return render(request, 'employer/config/specialite_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def specialite_detail(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Specialite, pk=pk)
    employes = UtilisateurEmploye.objects.filter(specialite=obj).select_related('specialite').order_by('nom')
    ids = list(Specialite.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employer/config/specialite_detail.html', {
        'obj': obj, 'utilisateurs': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
    })


@login_required
@require_POST
def specialite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Specialite.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)


@login_required
def departement_list_config(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    qs = Service.objects.annotate(nb_employes=Count('employes_rh'))
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employer/config/departements_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Service.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def departement_create(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    if request.method == 'POST':
        form = DepartementForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Département « {obj.nom} » créé.')
            return redirect('employer:departements')
    else:
        form = DepartementForm()
    return render(request, 'employer/config/departement_form.html', {
        'form': form,
        'titre': 'Nouveau département',
        'active_menu': 'config',
    })


@login_required
def departement_edit(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        form = DepartementForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Département mis à jour.')
            return redirect('employer:departements')
    else:
        form = DepartementForm(instance=obj)
    return render(request, 'employer/config/departement_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def departement_detail_config(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Service, pk=pk)
    employes = obj.employes_rh.order_by('nom')
    ids = list(Service.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employer/config/departement_detail.html', {
        'obj': obj, 'utilisateurs': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
    })


@login_required
@require_POST
def departement_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Service.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)


@login_required
def diplome_list(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    qs = Diplome.objects.all()
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(titre__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employer/config/diplomes_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Diplome.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def diplome_create(request):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    if request.method == 'POST':
        form = DiplomeForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Diplôme « {obj.titre} » créé.')
            return redirect('employer:diplomes')
    else:
        form = DiplomeForm()
    return render(request, 'employer/config/diplome_form.html', {
        'form': form,
        'titre': 'Nouveau diplôme',
        'active_menu': 'config',
    })


@login_required
def diplome_edit(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Diplome, pk=pk)
    if request.method == 'POST':
        form = DiplomeForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Diplôme mis à jour.')
            return redirect('employer:diplomes')
    else:
        form = DiplomeForm(instance=obj)
    return render(request, 'employer/config/diplome_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.titre}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def diplome_detail(request, pk):
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    obj = get_object_or_404(Diplome, pk=pk)
    employes = UtilisateurEmploye.objects.filter(diplome=obj).order_by('nom')
    ids = list(Diplome.objects.order_by('titre').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employer/config/diplome_detail.html', {
        'obj': obj, 'utilisateurs': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
    })


@login_required
@require_POST
def diplome_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Diplome.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)


# ── Configuration RH : Fonction / Grade / TypeContrat ────────────────────────

def _config_rh_list(request, model, form_class, template, list_url, label):
    from urllib.parse import urlencode
    if not request.user.is_staff:
        return redirect('employer:ressources_humaines_list')
    qs = model.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(nom__icontains=q)
    edit_pk = request.GET.get('edit')
    edit_obj = None
    if edit_pk:
        try:
            edit_obj = model.objects.get(pk=int(edit_pk))
        except (model.DoesNotExist, ValueError):
            pass
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'delete':
            pk = request.POST.get('pk')
            try:
                obj = model.objects.get(pk=int(pk))
                nom = obj.nom
                obj.delete()
                messages.success(request, f'« {nom} » supprimé.')
            except (model.DoesNotExist, ValueError):
                messages.error(request, 'Élément introuvable.')
            return redirect(list_url)
        pk = request.POST.get('pk')
        instance = None
        if pk:
            try:
                instance = model.objects.get(pk=int(pk))
            except (model.DoesNotExist, ValueError):
                pass
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'« {obj.nom} » {"modifié" if instance else "créé"}.')
            next_url      = request.POST.get('next', '').strip()
            created_field = request.POST.get('created_field', '').strip()
            if next_url:
                if created_field:
                    sep = '&' if '?' in next_url else '?'
                    next_url += sep + urlencode({'restored_field': created_field, 'restored_pk': obj.pk})
                return redirect(next_url)
            return redirect(list_url)
        return render(request, template, {
            'items': model.objects.all(),
            'form': form, 'edit_obj': instance,
            'q': q, 'label': label,
        })
    nom_initial = request.GET.get('nom', '')
    form = form_class(instance=edit_obj) if edit_obj else form_class(
        initial={'nom': nom_initial} if nom_initial else {}
    )
    return render(request, template, {
        'items': qs,
        'form': form, 'edit_obj': edit_obj,
        'q': q, 'label': label,
        'from_form': bool(request.GET.get('next')),
    })


@login_required(login_url='login')
def config_fonctions(request):
    return _config_rh_list(
        request, Fonction, FonctionForm,
        'employer/config/rh_config_list.html',
        'employer:config_fonctions', 'Fonction',
    )


@login_required(login_url='login')
def config_grades(request):
    return _config_rh_list(
        request, Grade, GradeForm,
        'employer/config/rh_config_list.html',
        'employer:config_grades', 'Grade',
    )


@login_required(login_url='login')
def config_types_contrat(request):
    return _config_rh_list(
        request, TypeContrat, TypeContratForm,
        'employer/config/rh_config_list.html',
        'employer:config_types_contrat', 'Type de contrat',
    )


@login_required(login_url='login')
@require_POST
def config_item_create_ajax(request):
    """Création rapide depuis le formulaire employé (appel AJAX)."""
    if not request.user.is_staff:
        return _JsonResponse({'ok': False, 'error': 'Non autorisé'}, status=403)
    model_name = request.POST.get('model')
    nom = request.POST.get('nom', '').strip()
    if not nom:
        return _JsonResponse({'ok': False, 'error': 'Nom requis'}, status=400)
    MODEL_MAP = {'fonction': Fonction, 'grade': Grade, 'type_contrat': TypeContrat}
    model = MODEL_MAP.get(model_name)
    if not model:
        return _JsonResponse({'ok': False, 'error': 'Modèle inconnu'}, status=400)
    obj, created = model.objects.get_or_create(nom=nom)
    return _JsonResponse({'ok': True, 'pk': obj.pk, 'nom': obj.nom, 'created': created})
