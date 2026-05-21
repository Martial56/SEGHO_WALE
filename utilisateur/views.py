from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import Employe, DiplomePersonnel
from .forms import EmployeForm, EmployeEducationForm, DiplomePersonnelForm


@login_required
def employe_list(request):
    from employer.models import Employe as EmpRH
    from django.contrib.auth.models import User

    if not request.user.is_staff:
        try:
            emp = EmpRH.objects.get(user=request.user)
            return redirect('utilisateur:detail', pk=emp.pk)
        except EmpRH.DoesNotExist:
            return render(request, 'utilisateur/list.html', {'no_profile': True})

    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')

    employes_avec_compte = EmpRH.objects.filter(
        user__isnull=False
    ).select_related('user', 'fonction').order_by('nom', 'prenoms')

    utilisateurs_sans_employe = User.objects.filter(
        employe_profile__isnull=True
    ).order_by('last_name', 'username')

    employes_sans_compte = EmpRH.objects.filter(
        user__isnull=True
    ).select_related('fonction').order_by('nom', 'prenoms')

    return render(request, 'utilisateur/list.html', {
        'employes_avec_compte': employes_avec_compte,
        'utilisateurs_sans_employe': utilisateurs_sans_employe,
        'employes_sans_compte': employes_sans_compte,
        'q': q,
        'vue': vue,
        'total_associes': EmpRH.objects.filter(user__isnull=False).count(),
        'total_sans_employe': User.objects.filter(employe_profile__isnull=True).count(),
        'total_sans_compte': EmpRH.objects.filter(user__isnull=True).count(),
        'is_admin_view': True,
    })


@login_required
def employe_detail(request, pk):
    from employer.models import Employe as EmpRH, DocumentEmploye, TYPE_DOC_CHOICES
    emp = get_object_or_404(EmpRH, pk=pk)

    # Sécurité : non-staff ne peut voir que son propre profil
    if not request.user.is_staff:
        own_emp = EmpRH.objects.filter(user=request.user).first()
        if not own_emp:
            return render(request, 'utilisateur/list.html', {'no_profile': True})
        if own_emp.pk != emp.pk:
            return redirect('utilisateur:detail', pk=own_emp.pk)

    is_own_profile = (emp.user_id is not None and emp.user_id == request.user.pk)

    # Profil clinique lié (utilisateur.Employe) s'il existe
    profil_clinique = None
    if emp.user_id:
        try:
            profil_clinique = emp.user.utilisateur_profile
        except Exception:
            pass

    documents = DocumentEmploye.objects.filter(employe=emp).order_by('-date_ajout')
    docs_manquants_keys = emp.docs_manquants
    doc_labels = dict(TYPE_DOC_CHOICES)
    docs_manquants = [{'key': k, 'label': doc_labels.get(k, k)} for k in docs_manquants_keys]

    from .forms import DocumentUploadForm
    doc_form = DocumentUploadForm()

    return render(request, 'utilisateur/detail.html', {
        'utilisateur': emp,
        'profil_clinique': profil_clinique,
        'documents': documents,
        'docs_manquants': docs_manquants,
        'doc_form': doc_form,
        'is_own_profile': is_own_profile,
        'is_staff': request.user.is_staff,
    })


@login_required
def employe_create(request):
    # La création des employés se fait depuis le module employer.
    # Rediriger les non-staff vers leur profil.
    from employer.models import Employe as EmpRH
    try:
        own = EmpRH.objects.get(user=request.user)
        return redirect('utilisateur:detail', pk=own.pk)
    except EmpRH.DoesNotExist:
        return render(request, 'utilisateur/list.html', {'no_profile': True})


@login_required
def employe_edit(request, pk):
    from employer.models import Employe as EmpRH
    emp = get_object_or_404(EmpRH, pk=pk)
    is_admin = request.user.is_staff
    is_own_profile = (emp.user_id is not None and emp.user_id == request.user.pk)

    if not is_admin and not is_own_profile:
        own_emp = EmpRH.objects.filter(user=request.user).first()
        if own_emp:
            return redirect('utilisateur:edit', pk=own_emp.pk)
        return render(request, 'utilisateur/list.html', {'no_profile': True})

    from .forms import EmployeProfilForm, EmployeProfilAdminForm, PasswordChangeFormCustom
    from django.contrib.auth import update_session_auth_hash

    FormClass = EmployeProfilAdminForm if is_admin else EmployeProfilForm
    admin_mode_pwd = is_admin and not is_own_profile

    if request.method == 'POST':
        action = request.POST.get('action', 'profil')

        if action == 'profil':
            form = FormClass(request.POST, request.FILES, instance=emp)
            pwd_form = PasswordChangeFormCustom(admin_mode=admin_mode_pwd)
            if form.is_valid():
                form.save()
                if emp.user:
                    emp.user.first_name = emp.prenoms
                    emp.user.last_name = emp.nom
                    emp.user.email = emp.email
                    emp.user.save()
                messages.success(request, 'Profil mis à jour.')
                return redirect('utilisateur:detail', pk=emp.pk)
            onglet_actif = 'profil'

        elif action == 'password':
            form = FormClass(instance=emp)
            pwd_form = PasswordChangeFormCustom(request.POST, admin_mode=admin_mode_pwd)
            if pwd_form.is_valid():
                new_pwd = pwd_form.cleaned_data['new_password']
                if admin_mode_pwd:
                    emp.user.set_password(new_pwd)
                    emp.user.save()
                    messages.success(request, f'Mot de passe de {emp.nom} mis à jour.')
                    return redirect('utilisateur:detail', pk=emp.pk)
                else:
                    current = pwd_form.cleaned_data.get('current_password', '')
                    if not emp.user or not emp.user.check_password(current):
                        pwd_form.add_error('current_password', 'Mot de passe actuel incorrect.')
                    else:
                        emp.user.set_password(new_pwd)
                        emp.user.save()
                        update_session_auth_hash(request, emp.user)
                        messages.success(request, 'Mot de passe mis à jour.')
                        return redirect('utilisateur:detail', pk=emp.pk)
            onglet_actif = 'compte'
        else:
            form = FormClass(instance=emp)
            pwd_form = PasswordChangeFormCustom(admin_mode=admin_mode_pwd)
            onglet_actif = 'profil'
    else:
        form = FormClass(instance=emp)
        pwd_form = PasswordChangeFormCustom(admin_mode=admin_mode_pwd)
        onglet_actif = request.GET.get('onglet', 'profil')

    return render(request, 'utilisateur/form.html', {
        'utilisateur': emp,
        'form': form,
        'pwd_form': pwd_form,
        'edit': True,
        'is_admin': is_admin,
        'is_own_profile': is_own_profile,
        'admin_edit': is_admin and not is_own_profile,
        'onglet_actif': onglet_actif,
    })


# ── Listes liées — Employé ───────────────────────────────────────────────────

@login_required
def employe_related_list(request, pk, view_type):
    employe = get_object_or_404(Employe, pk=pk)

    TITRES = {
        'rdv':             'Rendez-vous',
        'consultation':    'Consultations',
        'ordonnance':      'Ordonnances',
        'hospitalisation': 'Hospitalisations',
        'demande_examens': "Demandes d'examens",
        'resultat_examens':"Résultats d'examens",
    }
    if view_type not in TITRES:
        return redirect('utilisateur:detail', pk=pk)

    items = []
    if view_type == 'rdv':
        try:
            items = employe.rendez_vous.select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'consultation':
        try:
            from soins.models import Soin
            items = Soin.objects.filter(infirmier=employe).select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'ordonnance':
        try:
            from ordonnances.models import Ordonnance
            items = Ordonnance.objects.filter(
                medecin=employe
            ).select_related('patient').order_by('-date_ordonnance')
        except Exception:
            pass
    elif view_type == 'hospitalisation':
        try:
            from hospitalisation.models import Hospitalisation
            items = Hospitalisation.objects.filter(
                medecin_traitant=employe
            ).select_related('patient').order_by('-date_admission')
        except Exception:
            pass
    elif view_type == 'demande_examens':
        try:
            from laboratoire.models import AnalyseLaboratoire
            items = AnalyseLaboratoire.objects.filter(
                medecin_prescripteur=employe
            ).select_related('patient').order_by('-date_prelevement')
        except Exception:
            pass
    elif view_type == 'resultat_examens':
        try:
            from laboratoire.models import AnalyseLaboratoire
            items = AnalyseLaboratoire.objects.filter(
                medecin_prescripteur=employe,
                statut__in=['resultat', 'valide', 'envoye']
            ).select_related('patient').order_by('-date_resultat')
        except Exception:
            pass

    rdv_count = consultation_count = ordonnance_count = 0
    hospitalisation_count = demande_lab_count = resultat_lab_count = 0
    try:
        rdv_count = employe.rendez_vous.count()
    except Exception:
        pass
    try:
        from soins.models import Soin
        from ordonnances.models import Ordonnance
        consultation_count = Soin.objects.filter(infirmier=employe).count()
        ordonnance_count = Ordonnance.objects.filter(medecin=employe).count()
    except Exception:
        pass
    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(medecin_traitant=employe).count()
    except Exception:
        pass
    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_lab_count = AnalyseLaboratoire.objects.filter(medecin_prescripteur=employe).count()
        resultat_lab_count = AnalyseLaboratoire.objects.filter(
            medecin_prescripteur=employe, statut__in=['resultat', 'valide', 'envoye']
        ).count()
    except Exception:
        pass

    return render(request, 'utilisateur/related_list.html', {
        'utilisateur':          employe,
        'items':                items,
        'titre':                TITRES[view_type],
        'view_type':            view_type,
        'rdv_count':            rdv_count,
        'consultation_count':   consultation_count,
        'ordonnance_count':     ordonnance_count,
        'hospitalisation_count':hospitalisation_count,
        'demande_lab_count':    demande_lab_count,
        'resultat_lab_count':   resultat_lab_count,
    })


# ── Suppressions en masse ────────────────────────────────────────────────────

from django.views.decorators.http import require_POST
from django.http import JsonResponse as _JsonResponse

@login_required
@require_POST
def employe_upload_document(request, pk):
    from employer.models import Employe as EmpRH
    emp = get_object_or_404(EmpRH, pk=pk)
    is_own = emp.user_id == request.user.pk
    if not request.user.is_staff and not is_own:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    from .forms import DocumentUploadForm
    form = DocumentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        doc = form.save(commit=False)
        doc.employe = emp
        doc.ajoute_par = request.user
        doc.save()
        messages.success(request, 'Document ajouté avec succès.')
    else:
        messages.error(request, 'Erreur lors de l\'ajout du document. Vérifiez les champs.')
    return redirect('utilisateur:detail', pk=pk)


@login_required
@require_POST
def employe_delete_document(request, pk, doc_pk):
    from employer.models import Employe as EmpRH, DocumentEmploye
    emp = get_object_or_404(EmpRH, pk=pk)
    is_own = emp.user_id == request.user.pk
    if not request.user.is_staff and not is_own:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    doc = get_object_or_404(DocumentEmploye, pk=doc_pk, employe=emp)
    doc.delete()
    messages.success(request, 'Document supprimé.')
    return redirect('utilisateur:detail', pk=pk)


@login_required
@require_POST
def employe_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Employe.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)


# ── Diplômes personnels ──────────────────────────────────────────────────────

@login_required
def mes_diplomes_list(request):
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        return redirect('utilisateur:list')
    qs = DiplomePersonnel.objects.filter(employe=employe)
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(titre__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'utilisateur/config/mes_diplomes_list.html', {
        'page_obj': page_obj,
        'utilisateur': employe,
        'q': q,
        'total': DiplomePersonnel.objects.filter(employe=employe).count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def mes_diplome_create(request):
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        return redirect('utilisateur:list')
    if request.method == 'POST':
        form = DiplomePersonnelForm(request.POST)
        if form.is_valid():
            dp = form.save(commit=False)
            dp.employe = employe
            dp.save()
            messages.success(request, f'Diplôme « {dp.titre} » ajouté.')
            next_url = request.GET.get('next', '')
            if next_url:
                return redirect(next_url)
            return redirect('utilisateur:mes_diplomes')
    else:
        form = DiplomePersonnelForm()
    return render(request, 'utilisateur/config/mes_diplome_form.html', {
        'form': form,
        'utilisateur': employe,
        'active_menu': 'config',
    })


@login_required
@require_POST
def mes_diplome_delete(request, pk):
    try:
        employe = Employe.objects.get(user=request.user)
    except Employe.DoesNotExist:
        return redirect('utilisateur:list')
    dp = get_object_or_404(DiplomePersonnel, pk=pk, employe=employe)
    dp.delete()
    messages.success(request, 'Diplôme supprimé.')
    next_url = request.POST.get('next', '')
    if next_url:
        return redirect(next_url)
    return redirect('utilisateur:mes_diplomes')


@login_required
@require_POST
def employe_save_diplomes(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    if not request.user.is_staff:
        if not (employe.user and employe.user == request.user):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
    from django.utils import timezone as _tz
    current_year = _tz.now().year
    titres = request.POST.getlist('titre')
    etablissements = request.POST.getlist('etablissement')
    annees = request.POST.getlist('annee')
    count = 0
    skipped = 0
    for i, titre in enumerate(titres):
        titre = titre.strip()
        if not titre:
            continue
        etab = etablissements[i].strip() if i < len(etablissements) else ''
        annee_raw = annees[i].strip() if i < len(annees) else ''
        if annee_raw.isdigit():
            annee = int(annee_raw)
            if annee > current_year:
                skipped += 1
                continue
        else:
            annee = None
        DiplomePersonnel.objects.create(employe=employe, titre=titre, etablissement=etab, annee=annee)
        count += 1
    if count:
        messages.success(request, f'{count} diplôme(s) ajouté(s).')
    if skipped:
        messages.error(request, f'{skipped} ligne(s) ignorée(s) : l\'année ne peut pas dépasser {current_year}.')
    return redirect('utilisateur:detail', pk=pk)


@login_required
@require_POST
def employe_update_education(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    if not request.user.is_staff:
        if not (employe.user and employe.user == request.user):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
    form = EmployeEducationForm(request.POST, instance=employe)
    if form.is_valid():
        form.save()
        messages.success(request, 'Éducation et diplôme mis à jour.')
    else:
        messages.error(request, 'Erreur lors de la mise à jour.')
    return redirect('utilisateur:detail', pk=pk)

