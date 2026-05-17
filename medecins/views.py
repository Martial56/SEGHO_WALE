from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import Medecin, Specialite, Diplome, Departement, DocteurReferent
from .forms import (MedecinForm, SpecialiteForm, DiplomeForm, DepartementForm,
                    DocteurReferentForm, ContactAdresseFormSet)


@login_required
def medecin_list(request):
    qs = Medecin.objects.select_related('specialite').all()
    stats = {
        'total': qs.count(),
        'actifs': qs.filter(actif=True).count(),
        'nouveaux_30j': qs.filter(date_creation__gte=timezone.now() - timedelta(days=30)).count(),
    }

    q = request.GET.get('q', '').strip()
    specialite_id = request.GET.get('specialite', '')
    statut = request.GET.get('statut', '')

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

    return render(request, 'medecins/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'specialite_id': specialite_id,
        'statut': statut,
        'specialites': Specialite.objects.all(),
        'total_filtre': qs.count(),
        'active_menu': 'docteurs',
    })


@login_required
def medecin_detail(request, pk):
    medecin = get_object_or_404(Medecin, pk=pk)

    rdv_count = 0
    consultation_count = 0
    ordonnance_count = 0
    hospitalisation_count = 0
    demande_lab_count = 0
    resultat_lab_count = 0
    referent_count = medecin.referents_associes.count()

    try:
        rdv_count = medecin.rendez_vous.count()
    except Exception:
        pass

    try:
        from consultations.models import Consultation, Ordonnance
        consultation_count = Consultation.objects.filter(medecin=medecin).count()
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=medecin).count()
    except Exception:
        pass

    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(medecin_traitant=medecin).count()
    except Exception:
        pass

    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_lab_count = AnalyseLaboratoire.objects.filter(medecin_prescripteur=medecin).count()
        resultat_lab_count = AnalyseLaboratoire.objects.filter(
            medecin_prescripteur=medecin,
            statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    ids = list(Medecin.objects.order_by('nom', 'prenoms').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1

    return render(request, 'medecins/detail.html', {
        'medecin': medecin,
        'rdv_count': rdv_count,
        'consultation_count': consultation_count,
        'ordonnance_count': ordonnance_count,
        'hospitalisation_count': hospitalisation_count,
        'demande_lab_count': demande_lab_count,
        'resultat_lab_count': resultat_lab_count,
        'referent_count': referent_count,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required
def medecin_create(request):
    if request.method == 'POST':
        form = MedecinForm(request.POST, request.FILES)
        if form.is_valid():
            medecin = form.save()
            messages.success(request, f'Dr {medecin.nom} {medecin.prenoms} enregistré ({medecin.code}).')
            return redirect('medecins:detail', pk=medecin.pk)
    else:
        form = MedecinForm()
    return render(request, 'medecins/form.html', {
        'form': form,
        'titre': 'Nouveau médecin',
        'edit': False,
    })


@login_required
def medecin_edit(request, pk):
    medecin = get_object_or_404(Medecin, pk=pk)
    if request.method == 'POST':
        form = MedecinForm(request.POST, request.FILES, instance=medecin)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dossier médecin mis à jour.')
            return redirect('medecins:detail', pk=medecin.pk)
    else:
        form = MedecinForm(instance=medecin)

    rdv_count = 0
    ordonnance_count = 0
    hospitalisation_count = 0
    demande_lab_count = 0
    resultat_lab_count = 0
    try:
        rdv_count = medecin.rendez_vous.count()
    except Exception:
        pass
    try:
        from consultations.models import Ordonnance
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=medecin).count()
    except Exception:
        pass
    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(medecin_traitant=medecin).count()
    except Exception:
        pass
    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_lab_count = AnalyseLaboratoire.objects.filter(medecin_prescripteur=medecin).count()
        resultat_lab_count = AnalyseLaboratoire.objects.filter(
            medecin_prescripteur=medecin,
            statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    return render(request, 'medecins/form.html', {
        'form': form,
        'medecin': medecin,
        'titre': f'Modifier — Dr {medecin.nom} {medecin.prenoms}',
        'edit': True,
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
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/specialites_list.html', {
        'page_obj': page_obj,
        'q': q,
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
            return redirect('medecins:specialites')
    else:
        form = SpecialiteForm()
    return render(request, 'medecins/config/specialite_form.html', {
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
            return redirect('medecins:specialites')
    else:
        form = SpecialiteForm(instance=obj)
    return render(request, 'medecins/config/specialite_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


# ── Configuration : Départements ────────────────────────────────────────────

@login_required
def departement_list(request):
    qs = Departement.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/departements_list.html', {
        'page_obj': page_obj,
        'q': q,
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
            return redirect('medecins:departements')
    else:
        form = DepartementForm()
    return render(request, 'medecins/config/departement_form.html', {
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
            return redirect('medecins:departements')
    else:
        form = DepartementForm(instance=obj)
    return render(request, 'medecins/config/departement_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
        'active_menu': 'config',
    })


# ── Docteurs Référents ─────────────────────────────────────────────────────

@login_required
def referent_list(request):
    qs = DocteurReferent.objects.select_related('specialite').all()
    stats = {
        'total': qs.count(),
        'actifs': qs.filter(actif=True).count(),
    }

    q = request.GET.get('q', '').strip()
    specialite_id = request.GET.get('specialite', '')
    statut = request.GET.get('statut', '')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(code__icontains=q) | Q(etablissement__icontains=q)
        )
    if specialite_id:
        qs = qs.filter(specialite_id=specialite_id)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    paginator = Paginator(qs, 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'medecins/referents/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'specialite_id': specialite_id,
        'statut': statut,
        'specialites': Specialite.objects.all(),
        'total_filtre': qs.count(),
        'active_menu': 'referents',
    })


@login_required
def referent_detail(request, pk):
    referent = get_object_or_404(DocteurReferent, pk=pk)
    patients_count = referent.patients.count()
    contacts_count = referent.contacts_adresses.count()

    ids = list(DocteurReferent.objects.order_by('nom', 'prenoms').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1

    return render(request, 'medecins/referents/detail.html', {
        'referent': referent,
        'patients_count': patients_count,
        'contacts_count': contacts_count,
        'patients': referent.patients.all()[:10],
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
        'active_menu': 'referents',
    })


@login_required
def referent_create(request):
    if request.method == 'POST':
        form = DocteurReferentForm(request.POST, request.FILES)
        contact_fs = ContactAdresseFormSet(request.POST)
        if form.is_valid() and contact_fs.is_valid():
            ref = form.save()
            contact_fs.instance = ref
            contact_fs.save()
            messages.success(request, f'Dr {ref.nom} {ref.prenoms} enregistré ({ref.code}).')
            return redirect('medecins:referent_detail', pk=ref.pk)
    else:
        form = DocteurReferentForm()
        contact_fs = ContactAdresseFormSet()
    return render(request, 'medecins/referents/form.html', {
        'form': form,
        'contact_fs': contact_fs,
        'titre': 'Nouveau docteur référent',
        'edit': False,
        'active_menu': 'referents',
    })


@login_required
def referent_edit(request, pk):
    referent = get_object_or_404(DocteurReferent, pk=pk)
    if request.method == 'POST':
        form = DocteurReferentForm(request.POST, request.FILES, instance=referent)
        contact_fs = ContactAdresseFormSet(request.POST, instance=referent)
        if form.is_valid() and contact_fs.is_valid():
            form.save()
            contact_fs.save()
            messages.success(request, 'Dossier référent mis à jour.')
            return redirect('medecins:referent_detail', pk=referent.pk)
    else:
        form = DocteurReferentForm(instance=referent)
        contact_fs = ContactAdresseFormSet(instance=referent)
    return render(request, 'medecins/referents/form.html', {
        'form': form,
        'contact_fs': contact_fs,
        'referent': referent,
        'titre': f'Modifier — Dr {referent.nom} {referent.prenoms}',
        'edit': True,
        'active_menu': 'referents',
    })


# ── Configuration : Diplômes ────────────────────────────────────────────────

@login_required
def diplome_list(request):
    qs = Diplome.objects.all()
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(titre__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/diplomes_list.html', {
        'page_obj': page_obj,
        'q': q,
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
            return redirect('medecins:diplomes')
    else:
        form = DiplomeForm()
    return render(request, 'medecins/config/diplome_form.html', {
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
            return redirect('medecins:diplomes')
    else:
        form = DiplomeForm(instance=obj)
    return render(request, 'medecins/config/diplome_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.titre}',
        'obj': obj,
        'active_menu': 'config',
    })


# ── Listes liées — Médecin ───────────────────────────────────────────────────

@login_required
def medecin_related_list(request, pk, view_type):
    medecin = get_object_or_404(Medecin, pk=pk)

    TITRES = {
        'rdv':             'Rendez-vous',
        'consultation':    'Consultations',
        'ordonnance':      'Ordonnances',
        'hospitalisation': 'Hospitalisations',
        'demande_examens': "Demandes d'examens",
        'resultat_examens':"Résultats d'examens",
        'referents':       'Référents associés',
    }
    if view_type not in TITRES:
        return redirect('medecins:detail', pk=pk)

    items = []
    if view_type == 'rdv':
        try:
            items = medecin.rendez_vous.select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'consultation':
        try:
            from consultations.models import Consultation
            items = Consultation.objects.filter(medecin=medecin).select_related('patient').order_by('-date_heure')
        except Exception:
            pass
    elif view_type == 'ordonnance':
        try:
            from consultations.models import Ordonnance
            items = Ordonnance.objects.filter(
                consultation__medecin=medecin
            ).select_related('consultation__patient').order_by('-date_emission')
        except Exception:
            pass
    elif view_type == 'hospitalisation':
        try:
            from hospitalisation.models import Hospitalisation
            items = Hospitalisation.objects.filter(
                medecin_traitant=medecin
            ).select_related('patient').order_by('-date_admission')
        except Exception:
            pass
    elif view_type == 'demande_examens':
        try:
            from laboratoire.models import AnalyseLaboratoire
            items = AnalyseLaboratoire.objects.filter(
                medecin_prescripteur=medecin
            ).select_related('patient').order_by('-date_prelevement')
        except Exception:
            pass
    elif view_type == 'resultat_examens':
        try:
            from laboratoire.models import AnalyseLaboratoire
            items = AnalyseLaboratoire.objects.filter(
                medecin_prescripteur=medecin,
                statut__in=['résultat', 'validé', 'envoyé']
            ).select_related('patient').order_by('-date_resultat')
        except Exception:
            pass
    elif view_type == 'referents':
        items = medecin.referents_associes.select_related('specialite').order_by('nom')

    # Compteurs pour les smart buttons
    rdv_count = consultation_count = ordonnance_count = 0
    hospitalisation_count = demande_lab_count = resultat_lab_count = 0
    referent_count = medecin.referents_associes.count()
    try:
        rdv_count = medecin.rendez_vous.count()
    except Exception:
        pass
    try:
        from consultations.models import Consultation, Ordonnance
        consultation_count = Consultation.objects.filter(medecin=medecin).count()
        ordonnance_count = Ordonnance.objects.filter(consultation__medecin=medecin).count()
    except Exception:
        pass
    try:
        from hospitalisation.models import Hospitalisation
        hospitalisation_count = Hospitalisation.objects.filter(medecin_traitant=medecin).count()
    except Exception:
        pass
    try:
        from laboratoire.models import AnalyseLaboratoire
        demande_lab_count = AnalyseLaboratoire.objects.filter(medecin_prescripteur=medecin).count()
        resultat_lab_count = AnalyseLaboratoire.objects.filter(
            medecin_prescripteur=medecin, statut__in=['résultat', 'validé', 'envoyé']
        ).count()
    except Exception:
        pass

    return render(request, 'medecins/related_list.html', {
        'medecin':              medecin,
        'items':                items,
        'titre':                TITRES[view_type],
        'view_type':            view_type,
        'rdv_count':            rdv_count,
        'consultation_count':   consultation_count,
        'ordonnance_count':     ordonnance_count,
        'hospitalisation_count':hospitalisation_count,
        'demande_lab_count':    demande_lab_count,
        'resultat_lab_count':   resultat_lab_count,
        'referent_count':       referent_count,
    })


# ── Listes liées — Docteur Référent ─────────────────────────────────────────

@login_required
def referent_related_list(request, pk, view_type):
    referent = get_object_or_404(DocteurReferent, pk=pk)

    TITRES = {
        'patients': 'Patients référés',
        'contacts': 'Contacts & Adresses',
    }
    if view_type not in TITRES:
        return redirect('medecins:referent_detail', pk=pk)

    items = []
    if view_type == 'patients':
        items = referent.patients.all().order_by('nom', 'prenoms')
    elif view_type == 'contacts':
        items = referent.contacts_adresses.all()

    return render(request, 'medecins/referents/related_list.html', {
        'referent':        referent,
        'items':           items,
        'titre':           TITRES[view_type],
        'view_type':       view_type,
        'patients_count':  referent.patients.count(),
        'contacts_count':  referent.contacts_adresses.count(),
        'active_menu':     'referents',
    })


# ── Suppressions en masse ────────────────────────────────────────────────────

from django.views.decorators.http import require_POST
from django.http import JsonResponse as _JsonResponse

@login_required
@require_POST
def medecin_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Medecin.objects.filter(pk__in=ids).delete()
        return _JsonResponse({'ok': True, 'count': count})
    return _JsonResponse({'ok': False}, status=400)

@login_required
@require_POST
def referent_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = DocteurReferent.objects.filter(pk__in=ids).delete()
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
