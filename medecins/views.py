from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator

from .models import Specialite, Service, Medecin
from .forms import SpecialiteForm, ServiceForm


# ─── SPÉCIALITÉS ────────────────────────────────────────────────────────────

@login_required(login_url='login')
def specialites_list(request):
    qs = Specialite.objects.order_by('nom')
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/specialites_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Specialite.objects.count(),
        'total_filtre': qs.count(),
    })


@login_required(login_url='login')
def specialite_create(request):
    if request.method == 'POST':
        form = SpecialiteForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Spécialité « {obj.nom} » créée.')
            return redirect('medecins_specialites')
    else:
        form = SpecialiteForm()
    return render(request, 'medecins/config/specialite_form.html', {
        'form': form,
        'titre': 'Nouvelle spécialité',
    })


@login_required(login_url='login')
def specialite_edit(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    if request.method == 'POST':
        form = SpecialiteForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Spécialité mise à jour.')
            return redirect('medecins_specialite_detail', pk=pk)
    else:
        form = SpecialiteForm(instance=obj)
    return render(request, 'medecins/config/specialite_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
    })


@login_required(login_url='login')
def specialite_detail(request, pk):
    obj = get_object_or_404(Specialite, pk=pk)
    medecins = Medecin.objects.filter(specialite=obj).order_by('nom', 'prenoms')
    ids = list(Specialite.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'medecins/config/specialite_detail.html', {
        'obj': obj,
        'medecins': medecins,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required(login_url='login')
@require_POST
def specialite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Specialite.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


# ─── SERVICES (DÉPARTEMENTS) ─────────────────────────────────────────────────

@login_required(login_url='login')
def services_list(request):
    qs = Service.objects.select_related('chef_service').order_by('nom')
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    if q:
        qs = qs.filter(nom__icontains=q)
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'medecins/config/departements_list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': Service.objects.count(),
        'total_filtre': qs.count(),
    })


@login_required(login_url='login')
def service_create(request):
    if request.method == 'POST':
        form = ServiceForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Service « {obj.nom} » créé.')
            return redirect('medecins_departements')
    else:
        form = ServiceForm()
    return render(request, 'medecins/config/departement_form.html', {
        'form': form,
        'titre': 'Nouveau service',
    })


@login_required(login_url='login')
def service_edit(request, pk):
    obj = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service mis à jour.')
            return redirect('medecins_departement_detail', pk=pk)
    else:
        form = ServiceForm(instance=obj)
    return render(request, 'medecins/config/departement_form.html', {
        'form': form,
        'titre': f'Modifier — {obj.nom}',
        'obj': obj,
    })


@login_required(login_url='login')
def service_detail(request, pk):
    obj = get_object_or_404(Service.objects.select_related('chef_service'), pk=pk)
    ids = list(Service.objects.order_by('nom').values_list('pk', flat=True))
    try:
        idx = ids.index(pk)
        prev_pk = ids[idx - 1] if idx > 0 else None
        next_pk = ids[idx + 1] if idx < len(ids) - 1 else None
        position = idx + 1
    except ValueError:
        prev_pk = next_pk = None
        position = 1
    return render(request, 'medecins/config/departement_detail.html', {
        'obj': obj,
        'total': len(ids),
        'position': position,
        'prev_pk': prev_pk,
        'next_pk': next_pk,
    })


@login_required(login_url='login')
@require_POST
def service_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Service.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)
