from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import Employe, Specialite, Diplome, Departement
from .forms import EmployeForm, SpecialiteForm, DiplomeForm, DepartementForm, EmployeEducationForm


@login_required
def employe_list(request):
    if not request.user.is_staff:
        try:
            own = Employe.objects.get(user=request.user)
            return redirect('employe:edit', pk=own.pk)
        except Employe.DoesNotExist:
            return render(request, 'employe/list.html', {
                'no_profile': True,
                'page_obj': None,
                'stats': {},
                'active_menu': 'employes',
            })

    qs = Employe.objects.select_related('specialite').all()
    stats = {
        'total': qs.count(),
        'actifs': qs.filter(actif=True).count(),
        'nouveaux_30j': qs.filter(date_creation__gte=timezone.now() - timedelta(days=30)).count(),
    }

    q = request.GET.get('q', '').strip()
    specialite_id = request.GET.get('specialite', '')
    statut = request.GET.get('statut', '')
    vue = request.GET.get('vue', 'kanban')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code__icontains=q) | Q(matricule__icontains=q)
        )
    if specialite_id:
        qs = qs.filter(specialite_id=specialite_id)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'employe/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'specialite_id': specialite_id,
        'statut': statut,
        'specialites': Specialite.objects.all(),
        'total_filtre': qs.count(),
        'active_menu': 'employes',
        'vue': vue,
    })


@login_required
def employe_detail(request, pk):
    employe = get_object_or_404(Employe, pk=pk)

    if not request.user.is_staff:
        try:
            own = Employe.objects.get(user=request.user)
            if own.pk != employe.pk:
                return redirect('employe:detail', pk=own.pk)
        except Employe.DoesNotExist:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

    rdv_count = 0
    consultation_count = 0
    ordonnance_count = 0
    hospitalisation_count = 0
    demande_lab_count = 0
    resultat_lab_count = 0

    try:
        rdv_count = employe.rendez_vous.count()
    except Exception:
        pass

    try:
        from consultations.models import Consultation, Ordonnance
        consultation_count = Consultation.objects.filter(medecin=employe).count()
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=employe).count()
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
            medecin_prescripteur=employe,
            statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    ids = list(Employe.objects.order_by('nom', 'prenoms').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1

    is_own_profile = (employe.user_id is not None and employe.user_id == request.user.pk)

    _is_medecin_det = False
    try:
        _own_det = Employe.objects.get(user=request.user)
        _is_medecin_det = _own_det.est_medecin
    except Employe.DoesNotExist:
        pass
    can_see_medical = request.user.is_staff or _is_medecin_det

    return render(request, 'employe/detail.html', {
        'employe': employe,
        'rdv_count': rdv_count,
        'consultation_count': consultation_count,
        'ordonnance_count': ordonnance_count,
        'hospitalisation_count': hospitalisation_count,
        'demande_lab_count': demande_lab_count,
        'resultat_lab_count': resultat_lab_count,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
        'is_own_profile': is_own_profile,
        'can_see_medical': can_see_medical,
        'education_form': EmployeEducationForm(instance=employe),
    })


@login_required
def employe_create(request):
    if not request.user.is_staff:
        try:
            own = Employe.objects.get(user=request.user)
            return redirect('employe:edit', pk=own.pk)
        except Employe.DoesNotExist:
            pass

    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES)
        if form.is_valid():
            employe = form.save(commit=False)
            username = form.cleaned_data.get('username', '').strip()
            password = form.cleaned_data.get('password', '').strip()
            if username:
                from django.contrib.auth.models import User as AuthUser
                if not AuthUser.objects.filter(username=username).exists():
                    user = AuthUser.objects.create_user(
                        username=username,
                        password=password or None,
                        email=employe.email,
                        first_name=employe.prenoms,
                        last_name=employe.nom,
                    )
                    employe.user = user
                else:
                    form.add_error('username', "Cet identifiant est déjà utilisé.")
                    return render(request, 'employe/form.html', {
                        'form': form, 'titre': 'Nouvel employé', 'edit': False,
                        'is_admin': request.user.is_staff,
                    })
            employe.save()
            form.save_m2m()
            messages.success(request, f'{employe.nom} {employe.prenoms} enregistré ({employe.code}).')
            return redirect('employe:detail', pk=employe.pk)
    else:
        form = EmployeForm()
    return render(request, 'employe/form.html', {
        'form': form,
        'titre': 'Nouvel employé',
        'edit': False,
        'is_admin': request.user.is_staff,
    })


@login_required
def employe_edit(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    is_admin = request.user.is_staff

    if not is_admin:
        try:
            own = Employe.objects.get(user=request.user)
            if own.pk != employe.pk:
                messages.info(request, 'Vous ne pouvez consulter que votre propre profil.')
                return redirect('employe:edit', pk=own.pk)
        except Employe.DoesNotExist:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

    is_own_profile = (employe.user_id is not None and employe.user_id == request.user.pk)

    # Détermination des droits selon le rôle
    is_medecin = False
    if not is_admin:
        try:
            _own_emp = Employe.objects.get(user=request.user)
            is_medecin = _own_emp.est_medecin
        except Employe.DoesNotExist:
            pass
    can_edit_all = is_admin or (is_own_profile and is_medecin)
    can_see_medical = is_admin or is_medecin

    # Champs modifiables par tous (sur son propre profil)
    _ALLOWED_REGULAR = {
        'nom', 'prenoms', 'photo', 'adresse',
        'telephone', 'mobile', 'email',
        'date_naissance', 'lieu_naissance', 'nationalite',
    }
    # Champs réservés à l'admin (même pour un médecin)
    _ADMIN_ONLY = {'est_medecin', 'actif', 'employe_societe', 'matricule'}

    if request.method == 'POST':
        form = EmployeForm(request.POST, request.FILES, instance=employe)
        if form.is_valid():
            updated = form.save(commit=False)

            # Protection serveur : restreindre les champs selon les droits
            if not can_edit_all:
                _orig = Employe.objects.get(pk=employe.pk)
                for _f in Employe._meta.fields:
                    _fn = _f.name
                    if _fn not in _ALLOWED_REGULAR and _fn != 'id':
                        setattr(updated, _fn, getattr(_orig, _fn))
            elif not is_admin:
                _orig = Employe.objects.get(pk=employe.pk)
                for _fn in _ADMIN_ONLY:
                    setattr(updated, _fn, getattr(_orig, _fn))

            username = form.cleaned_data.get('username', '').strip()
            current_password = form.cleaned_data.get('current_password', '').strip()
            new_password = form.cleaned_data.get('new_password', '').strip()
            confirm_password = form.cleaned_data.get('confirm_password', '').strip()

            ctx_err = {
                'form': form, 'employe': employe,
                'titre': f'Modifier — {employe.nom} {employe.prenoms}',
                'edit': True, 'is_admin': is_admin, 'is_own_profile': is_own_profile,
                'is_medecin': is_medecin, 'can_edit_all': can_edit_all,
                'can_see_medical': can_see_medical,
            }

            if new_password:
                if not current_password:
                    form.add_error(None, "Saisissez votre mot de passe actuel pour en définir un nouveau.")
                    return render(request, 'employe/form.html', ctx_err)
                if not updated.user or not updated.user.check_password(current_password):
                    form.add_error(None, "Le mot de passe actuel est incorrect.")
                    return render(request, 'employe/form.html', ctx_err)
                if new_password != confirm_password:
                    form.add_error(None, "Les nouveaux mots de passe ne correspondent pas.")
                    return render(request, 'employe/form.html', ctx_err)

            if username and (is_admin or is_own_profile):
                from django.contrib.auth.models import User as AuthUser
                if updated.user:
                    if updated.user.username != username:
                        if AuthUser.objects.filter(username=username).exclude(pk=updated.user.pk).exists():
                            form.add_error('username', "Cet identifiant est déjà utilisé.")
                            return render(request, 'employe/form.html', ctx_err)
                        updated.user.username = username
                    if new_password:
                        updated.user.set_password(new_password)
                    updated.user.email = updated.email
                    updated.user.first_name = updated.prenoms
                    updated.user.last_name = updated.nom
                    updated.user.save()
                else:
                    if not AuthUser.objects.filter(username=username).exists():
                        user = AuthUser.objects.create_user(
                            username=username,
                            password=new_password or None,
                            email=updated.email,
                            first_name=updated.prenoms,
                            last_name=updated.nom,
                        )
                        updated.user = user
            updated.save()
            if can_edit_all:
                form.save_m2m()
            messages.success(request, 'Profil mis à jour.')
            return redirect('employe:detail', pk=employe.pk)
    else:
        form = EmployeForm(instance=employe)

    rdv_count = 0
    ordonnance_count = 0
    hospitalisation_count = 0
    demande_lab_count = 0
    resultat_lab_count = 0
    try:
        rdv_count = employe.rendez_vous.count()
    except Exception:
        pass
    try:
        from consultations.models import Ordonnance
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=employe).count()
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
            medecin_prescripteur=employe,
            statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    return render(request, 'employe/form.html', {
        'form': form,
        'employe': employe,
        'titre': f'Modifier — {employe.nom} {employe.prenoms}',
        'edit': True,
        'is_admin': is_admin,
        'is_own_profile': is_own_profile,
        'is_medecin': is_medecin,
        'can_edit_all': can_edit_all,
        'can_see_medical': can_see_medical,
        'rdv_count': rdv_count,
        'ordonnance_count': ordonnance_count,
        'hospitalisation_count': hospitalisation_count,
        'demande_lab_count': demande_lab_count,
        'resultat_lab_count': resultat_lab_count,
    })


# ── Configuration : Spécialités ────────────────────────────────────────────

@login_required
def specialite_list(request):
    qs = Specialite.objects.all()
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employe/config/specialites_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Specialite.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def specialite_create(request):
    if request.method == 'POST':
        form = SpecialiteForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Spécialité « {obj.nom} » créée.')
            return redirect('employe:specialites')
    else:
        form = SpecialiteForm()
    return render(request, 'employe/config/specialite_form.html', {
        'form': form,
        'titre': 'Nouvelle spécialité',
        'active_menu': 'config',
    })


@login_required
def specialite_edit(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    if request.method == 'POST':
        form = SpecialiteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Spécialité mise à jour.')
            return redirect('employe:specialites')
    else:
        form = SpecialiteForm(instance=obj)
    return render(request, 'employe/config/specialite_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def specialite_detail(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    employes = Employe.objects.filter(specialite=obj).select_related('specialite').order_by('nom')
    ids = list(Specialite.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employe/config/specialite_detail.html', {
        'obj': obj, 'employes': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
    })


# ── Configuration : Départements ────────────────────────────────────────────

@login_required
def departement_list(request):
    qs = Departement.objects.all()
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employe/config/departements_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Departement.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def departement_create(request):
    if request.method == 'POST':
        form = DepartementForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Département « {obj.nom} » créé.')
            return redirect('employe:departements')
    else:
        form = DepartementForm()
    return render(request, 'employe/config/departement_form.html', {
        'form': form,
        'titre': 'Nouveau département',
        'active_menu': 'config',
    })


@login_required
def departement_edit(request, pk):
    obj = get_object_or_404(Departement, pk=pk)
    if request.method == 'POST':
        form = DepartementForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Département mis à jour.')
            return redirect('employe:departements')
    else:
        form = DepartementForm(instance=obj)
    return render(request, 'employe/config/departement_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def departement_detail(request, pk):
    obj = get_object_or_404(Departement, pk=pk)
    employes = obj.employes.order_by('nom')
    ids = list(Departement.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employe/config/departement_detail.html', {
        'obj': obj, 'employes': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
    })


# ── Configuration : Diplômes ────────────────────────────────────────────────

@login_required
def diplome_list(request):
    qs = Diplome.objects.all()
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(titre__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'employe/config/diplomes_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Diplome.objects.count(),
        'total_filtre': qs.count(),
        'active_menu': 'config',
    })


@login_required
def diplome_create(request):
    if request.method == 'POST':
        form = DiplomeForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Diplôme « {obj.titre} » créé.')
            return redirect('employe:diplomes')
    else:
        form = DiplomeForm()
    return render(request, 'employe/config/diplome_form.html', {
        'form': form,
        'titre': 'Nouveau diplôme',
        'active_menu': 'config',
    })


@login_required
def diplome_edit(request, pk):
    obj = get_object_or_404(Diplome, pk=pk)
    if request.method == 'POST':
        form = DiplomeForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Diplôme mis à jour.')
            return redirect('employe:diplomes')
    else:
        form = DiplomeForm(instance=obj)
    return render(request, 'employe/config/diplome_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.titre}',
        'obj': obj,
        'active_menu': 'config',
    })


@login_required
def diplome_detail(request, pk):
    obj = get_object_or_404(Diplome, pk=pk)
    employes = Employe.objects.filter(diplome=obj).order_by('nom')
    ids = list(Diplome.objects.order_by('titre').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'employe/config/diplome_detail.html', {
        'obj': obj, 'employes': employes,
        'total': len(ids), 'position': position,
        'prev_pk': prev_pk, 'next_pk': next_pk,
        'active_menu': 'config',
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
        return redirect('employe:detail', pk=pk)

    items = []
    if view_type == 'rdv':
        try:
            items = employe.rendez_vous.select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'consultation':
        try:
            from consultations.models import Consultation
            items = Consultation.objects.filter(medecin=employe).select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'ordonnance':
        try:
            from consultations.models import Ordonnance
            items = Ordonnance.objects.filter(
                consultation__medecin=employe
            ).select_related('consultation__patient').order_by('-date_emission')
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
                statut__in=['résultat', 'validé', 'envoyé']
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
        from consultations.models import Consultation, Ordonnance
        consultation_count = Consultation.objects.filter(medecin=employe).count()
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=employe).count()
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
            medecin_prescripteur=employe, statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    return render(request, 'employe/related_list.html', {
        'employe':              employe,
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
def employe_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Employe.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)

@login_required
@require_POST
def specialite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Specialite.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)

@login_required
@require_POST
def departement_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Departement.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)

@login_required
@require_POST
def diplome_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Diplome.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)


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
    return redirect('employe:detail', pk=pk)
