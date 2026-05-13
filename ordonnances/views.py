from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from .models import GroupeMedicaments, Maladie, Ordonnance
from .forms import GroupeMedicamentsForm, LigneGroupeMedicamentsFormSet, MaladieForm, OrdonnanceForm, LigneOrdonnanceFormSet


@login_required(login_url='login')
def ordonnance_list(request):
    qs = Ordonnance.objects.select_related('patient', 'medecin').order_by('-date_ordonnance')

    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(
            Q(patient__nom__icontains=q) |
            Q(patient__prenoms__icontains=q) |
            Q(medecin__nom__icontains=q) |
            Q(numero__icontains=q)
        )

    statut = request.GET.get('statut', '')
    if statut:
        qs = qs.filter(statut=statut)

    type_ord = request.GET.get('type', '')
    if type_ord:
        qs = qs.filter(type_ordonnance=type_ord)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    today = timezone.now().date()
    stats = {
        'total': Ordonnance.objects.count(),
        'brouillons': Ordonnance.objects.filter(statut='brouillon').count(),
        'prescrits': Ordonnance.objects.filter(statut='prescrit').count(),
        'du_jour': Ordonnance.objects.filter(date_ordonnance__date=today).count(),
    }

    return render(request, 'ordonnances/list.html', {
        'page_obj': page_obj,
        'stats': stats,
        'q': q,
        'statut_filtre': statut,
        'type_filtre': type_ord,
        'breadcrumb': [{'title': 'Accueil', 'url': '/'}, {'title': 'Ordonnances'}],
    })


@login_required(login_url='login')
def ordonnance_create(request):
    if request.method == 'POST':
        form = OrdonnanceForm(request.POST)
        formset = LigneOrdonnanceFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            ordonnance = form.save()
            formset.instance = ordonnance
            formset.save()
            messages.success(request, f"Ordonnance {ordonnance.numero} créée avec succès.")
            return redirect('ordonnance_detail', pk=ordonnance.pk)
    else:
        form = OrdonnanceForm(initial={'date_ordonnance': timezone.now()})
        formset = LigneOrdonnanceFormSet()

    return render(request, 'ordonnances/form.html', {
        'form': form,
        'formset': formset,
        'titre': 'Nouvelle ordonnance',
        'is_create': True,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Nouvelle'},
        ],
    })


@login_required(login_url='login')
def ordonnance_edit(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)

    if ordonnance.statut == 'prescrit' and not request.user.is_staff:
        messages.error(request, "Impossible de modifier une ordonnance déjà prescrite.")
        return redirect('ordonnance_detail', pk=pk)

    if request.method == 'POST':
        form = OrdonnanceForm(request.POST, instance=ordonnance)
        formset = LigneOrdonnanceFormSet(request.POST, instance=ordonnance)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Ordonnance {ordonnance.numero} mise à jour.")
            return redirect('ordonnance_detail', pk=ordonnance.pk)
    else:
        form = OrdonnanceForm(instance=ordonnance)
        formset = LigneOrdonnanceFormSet(instance=ordonnance)

    return render(request, 'ordonnances/form.html', {
        'form': form,
        'formset': formset,
        'ordonnance': ordonnance,
        'titre': f'Modifier {ordonnance.numero}',
        'is_create': False,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': ordonnance.numero},
        ],
    })


@login_required(login_url='login')
def ordonnance_detail(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    return render(request, 'ordonnances/detail.html', {
        'ordonnance': ordonnance,
        'lignes': ordonnance.lignes.select_related('medicament').all(),
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': ordonnance.numero},
        ],
    })


@login_required(login_url='login')
@require_POST
def ordonnance_prescrire(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if ordonnance.statut == 'brouillon':
        ordonnance.statut = 'prescrit'
        ordonnance.save()
        messages.success(request, f"Ordonnance {ordonnance.numero} passée à l'état Prescrit.")
    return redirect('ordonnance_detail', pk=pk)


# ── Groupes de médicaments ──────────────────────────────────────────────────

@login_required(login_url='login')
def groupe_medicaments_list(request):
    qs = GroupeMedicaments.objects.select_related('medecin').order_by('nom')
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(maladie__nom__icontains=q))
    return render(request, 'ordonnances/groupes/list.html', {
        'groupes': qs,
        'q': q,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Groupes de médicaments'},
        ],
    })


@login_required(login_url='login')
def groupe_medicaments_create(request):
    if request.method == 'POST':
        form = GroupeMedicamentsForm(request.POST)
        formset = LigneGroupeMedicamentsFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            groupe = form.save()
            formset.instance = groupe
            formset.save()
            messages.success(request, f"Groupe « {groupe.nom} » créé avec succès.")
            return redirect('groupe_medicaments_list')
    else:
        form = GroupeMedicamentsForm()
        formset = LigneGroupeMedicamentsFormSet()
    return render(request, 'ordonnances/groupes/form.html', {
        'form': form,
        'formset': formset,
        'titre': 'Nouveau groupe de médicaments',
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Groupes', 'url': '/ordonnances/groupes/'},
            {'title': 'Nouveau'},
        ],
    })


@login_required(login_url='login')
def groupe_medicaments_edit(request, pk):
    groupe = get_object_or_404(GroupeMedicaments, pk=pk)
    if request.method == 'POST':
        form = GroupeMedicamentsForm(request.POST, instance=groupe)
        formset = LigneGroupeMedicamentsFormSet(request.POST, instance=groupe)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Groupe « {groupe.nom} » mis à jour.")
            return redirect('groupe_medicaments_list')
    else:
        form = GroupeMedicamentsForm(instance=groupe)
        formset = LigneGroupeMedicamentsFormSet(instance=groupe)
    return render(request, 'ordonnances/groupes/form.html', {
        'form': form,
        'formset': formset,
        'groupe': groupe,
        'titre': f'Modifier — {groupe.nom}',
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Groupes', 'url': '/ordonnances/groupes/'},
            {'title': groupe.nom},
        ],
    })


@login_required(login_url='login')
@require_POST
def groupe_medicaments_delete(request, pk):
    groupe = get_object_or_404(GroupeMedicaments, pk=pk)
    nom = groupe.nom
    groupe.delete()
    messages.success(request, f"Groupe « {nom} » supprimé.")
    return redirect('groupe_medicaments_list')


# ── Maladies ────────────────────────────────────────────────────────────────

@login_required(login_url='login')
def maladie_list(request):
    qs = Maladie.objects.order_by('nom')
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    return render(request, 'ordonnances/maladies/list.html', {
        'maladies': qs,
        'q': q,
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Maladies'},
        ],
    })


@login_required(login_url='login')
def maladie_create(request):
    if request.method == 'POST':
        form = MaladieForm(request.POST)
        if form.is_valid():
            maladie = form.save()
            messages.success(request, f"Maladie « {maladie.nom} » créée.")
            return redirect('maladie_list')
    else:
        form = MaladieForm()
    return render(request, 'ordonnances/maladies/form.html', {
        'form': form,
        'titre': 'Nouvelle maladie',
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Maladies', 'url': '/ordonnances/maladies/'},
            {'title': 'Nouveau'},
        ],
    })


@login_required(login_url='login')
def maladie_edit(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    if request.method == 'POST':
        form = MaladieForm(request.POST, instance=maladie)
        if form.is_valid():
            form.save()
            messages.success(request, f"Maladie « {maladie.nom} » mise à jour.")
            return redirect('maladie_list')
    else:
        form = MaladieForm(instance=maladie)
    return render(request, 'ordonnances/maladies/form.html', {
        'form': form,
        'maladie': maladie,
        'titre': f'Modifier — {maladie.nom}',
        'breadcrumb': [
            {'title': 'Accueil', 'url': '/'},
            {'title': 'Ordonnances', 'url': '/ordonnances/'},
            {'title': 'Maladies', 'url': '/ordonnances/maladies/'},
            {'title': maladie.nom},
        ],
    })


@login_required(login_url='login')
@require_POST
def maladie_delete(request, pk):
    maladie = get_object_or_404(Maladie, pk=pk)
    nom = maladie.nom
    maladie.delete()
    messages.success(request, f"Maladie « {nom} » supprimée.")
    return redirect('maladie_list')
