from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q

from .models import Employe, Poste, Conge
from .forms import EmployeForm, PosteForm, CongeForm


# ── Employés ─────────────────────────────────────────────────────────────────

@login_required
def employe_list(request):
    qs = Employe.objects.select_related('poste').all()

    q      = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    vue    = request.GET.get('vue', 'liste')

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(prenoms__icontains=q) |
            Q(matricule__icontains=q) | Q(telephone__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)

    total = Employe.objects.count()
    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'ressources_humaines/list.html', {
        'page_obj': page_obj,
        'total':    total,
        'q':        q,
        'statut':   statut,
        'vue':      vue,
        'statut_choices': Employe.STATUT,
    })


@login_required
def employe_create(request):
    if request.method == 'POST':
        form = EmployeForm(request.POST)
        if form.is_valid():
            emp = form.save()
            messages.success(request, f'{emp.nom} {emp.prenoms} enregistré ({emp.matricule}).')
            return redirect('rh:list')
    else:
        form = EmployeForm()
    return render(request, 'ressources_humaines/form.html', {
        'form':   form,
        'is_new': True,
    })


@login_required
def employe_edit(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    if request.method == 'POST':
        form = EmployeForm(request.POST, instance=employe)
        if form.is_valid():
            form.save()
            messages.success(request, 'Dossier mis à jour.')
            return redirect('rh:list')
    else:
        form = EmployeForm(instance=employe)
    return render(request, 'ressources_humaines/form.html', {
        'form':    form,
        'employe': employe,
        'is_new':  False,
    })


# ── Postes ────────────────────────────────────────────────────────────────────

@login_required
def poste_list(request):
    qs = Poste.objects.select_related('service').all()
    q  = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))

    total     = Poste.objects.count()
    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'ressources_humaines/postes/list.html', {
        'page_obj': page_obj,
        'total':    total,
        'q':        q,
    })


@login_required
def poste_create(request):
    if request.method == 'POST':
        form = PosteForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Poste « {obj.nom} » créé.')
            return redirect('rh:postes')
    else:
        form = PosteForm()
    return render(request, 'ressources_humaines/postes/form.html', {
        'form':   form,
        'is_new': True,
    })


@login_required
def poste_edit(request, pk):
    poste = get_object_or_404(Poste, pk=pk)
    if request.method == 'POST':
        form = PosteForm(request.POST, instance=poste)
        if form.is_valid():
            form.save()
            messages.success(request, 'Poste mis à jour.')
            return redirect('rh:postes')
    else:
        form = PosteForm(instance=poste)
    return render(request, 'ressources_humaines/postes/form.html', {
        'form':   form,
        'poste':  poste,
        'is_new': False,
    })


# ── Congés ────────────────────────────────────────────────────────────────────

@login_required
def conge_list(request):
    qs = Conge.objects.select_related('employe').all()

    q        = request.GET.get('q', '').strip()
    statut   = request.GET.get('statut', '')
    type_c   = request.GET.get('type_conge', '')

    if q:
        qs = qs.filter(
            Q(employe__nom__icontains=q) | Q(employe__prenoms__icontains=q)
        )
    if statut:
        qs = qs.filter(statut=statut)
    if type_c:
        qs = qs.filter(type_conge=type_c)

    qs = qs.order_by('-date_demande')
    total     = Conge.objects.count()
    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'ressources_humaines/conges/list.html', {
        'page_obj':      page_obj,
        'total':         total,
        'q':             q,
        'statut':        statut,
        'type_conge':    type_c,
        'statut_choices':   Conge.STATUT,
        'type_choices':     Conge.TYPE,
    })


@login_required
def conge_create(request):
    if request.method == 'POST':
        form = CongeForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Congé de {obj.employe} enregistré.')
            return redirect('rh:conges')
    else:
        form = CongeForm()
    return render(request, 'ressources_humaines/conges/form.html', {
        'form':   form,
        'is_new': True,
    })


@login_required
def conge_edit(request, pk):
    conge = get_object_or_404(Conge, pk=pk)
    if request.method == 'POST':
        form = CongeForm(request.POST, instance=conge)
        if form.is_valid():
            form.save()
            messages.success(request, 'Congé mis à jour.')
            return redirect('rh:conges')
    else:
        form = CongeForm(instance=conge)
    return render(request, 'ressources_humaines/conges/form.html', {
        'form':   form,
        'conge':  conge,
        'is_new': False,
    })
