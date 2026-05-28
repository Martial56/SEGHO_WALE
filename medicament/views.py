import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, F
from django.core.paginator import Paginator

from .models import (
    Medicament, CategorieMedicament, GroupeMedicament, LigneMedicamentGroupe,
    CompagniePharma, EffetTherapeutique, DosageMedicament,
    RouteMedicament, FormulaireType,
)
from .forms import (
    MedicamentForm, MouvementStockForm, GroupeMedicamentForm,
    CompagniePharmaForm, EffetTherapeutiqueForm,
    DosageMedicamentForm, RouteMedicamentForm, FormulaireTypeForm,
)
from pharmacie.models import MouvementStock


def _login(view_func):
    return login_required(view_func, login_url='login')


# ─── CATALOGUE ────────────────────────────────────────────────────────────────

@_login
def medicament_list(request):
    q      = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    cat_id = request.GET.get('categorie', '')

    qs = Medicament.objects.select_related('categorie').order_by('designation')
    if q:
        qs = qs.filter(Q(designation__icontains=q) | Q(code__icontains=q) | Q(dci__icontains=q))
    if statut == 'ok':
        qs = qs.filter(stock_actuel__gt=F('stock_alerte'))
    elif statut == 'alerte':
        qs = qs.filter(stock_actuel__lte=F('stock_alerte'), stock_actuel__gt=F('stock_minimum'))
    elif statut == 'rupture':
        qs = qs.filter(stock_actuel__lte=F('stock_minimum'))
    if cat_id:
        qs = qs.filter(categorie_id=cat_id)

    paginator  = Paginator(qs, 30)
    page_obj   = paginator.get_page(request.GET.get('page'))
    categories = CategorieMedicament.objects.order_by('nom')

    return render(request, 'medicament/list.html', {
        'page_obj':   page_obj,
        'total':      paginator.count,
        'q':          q,
        'statut':     statut,
        'cat_id':     cat_id,
        'categories': categories,
        'stats': {
            'total':   Medicament.objects.count(),
            'ok':      Medicament.objects.filter(stock_actuel__gt=F('stock_alerte')).count(),
            'alerte':  Medicament.objects.filter(stock_actuel__lte=F('stock_alerte'), stock_actuel__gt=F('stock_minimum')).count(),
            'rupture': Medicament.objects.filter(stock_actuel__lte=F('stock_minimum')).count(),
        },
    })


@_login
def medicament_detail(request, pk):
    medicament = get_object_or_404(
        Medicament.objects.select_related('categorie', 'compagnie_pharma', 'effet_therapeutique'), pk=pk
    )
    lots       = medicament.lots.order_by('date_peremption')
    mouvements = medicament.mouvements.select_related('cree_par').order_by('-date_mouvement')[:20]
    return render(request, 'medicament/detail.html', {
        'medicament': medicament,
        'lots':       lots,
        'mouvements': mouvements,
    })


@_login
def medicament_create(request):
    if request.method == 'POST':
        form = MedicamentForm(request.POST)
        if form.is_valid():
            med = form.save()
            messages.success(request, f"Médicament {med.designation} créé.")
            return redirect('medicament:detail', pk=med.pk)
    else:
        form = MedicamentForm()
    return render(request, 'medicament/form.html', {'form': form, 'title': 'Nouveau médicament'})


@_login
def medicament_edit(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    next_url   = request.GET.get('next', '')
    if request.method == 'POST':
        form = MedicamentForm(request.POST, instance=medicament)
        if form.is_valid():
            form.save()
            messages.success(request, "Médicament mis à jour.")
            return redirect(next_url or f'/medicaments/{pk}/')
    else:
        form = MedicamentForm(instance=medicament)
    return render(request, 'medicament/form.html', {
        'form': form, 'medicament': medicament,
        'title': f'Modifier — {medicament.designation}',
        'next_url': next_url,
    })


@_login
def mouvement_add(request, pk):
    medicament = get_object_or_404(Medicament, pk=pk)
    next_url   = request.GET.get('next', '')
    if request.method == 'POST':
        form = MouvementStockForm(request.POST, medicament=medicament)
        if form.is_valid():
            mv             = form.save(commit=False)
            mv.medicament  = medicament
            mv.cree_par    = request.user
            mv.stock_avant = medicament.stock_actuel
            if mv.type_mouvement == 'entree':
                medicament.stock_actuel += mv.quantite
            elif mv.type_mouvement in ('sortie', 'peremption'):
                medicament.stock_actuel = max(0, medicament.stock_actuel - mv.quantite)
            elif mv.type_mouvement == 'ajustement':
                medicament.stock_actuel = mv.quantite
            mv.stock_apres = medicament.stock_actuel
            mv.save()
            medicament.save(update_fields=['stock_actuel'])
            messages.success(request, "Mouvement enregistré.")
            return redirect(next_url or f'/medicaments/{pk}/')
    else:
        form = MouvementStockForm(medicament=medicament)
    return render(request, 'medicament/mouvement_form.html', {
        'form': form, 'medicament': medicament, 'next_url': next_url,
    })


# ─── GROUPES ──────────────────────────────────────────────────────────────────

@_login
def groupe_list(request):
    q  = request.GET.get('q', '').strip()
    qs = GroupeMedicament.objects.select_related('medecin').order_by('nom')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(maladies__icontains=q))
    paginator = Paginator(qs, 25)
    return render(request, 'medicament/groupe/list.html', {
        'page_obj': paginator.get_page(request.GET.get('page')),
        'total': paginator.count, 'q': q,
    })


@_login
def groupe_create(request):
    if request.method == 'POST':
        form = GroupeMedicamentForm(request.POST)
        if form.is_valid():
            groupe = form.save()
            _save_lignes(request, groupe)
            messages.success(request, f"Groupe « {groupe.nom} » créé.")
            return redirect('medicament:groupe_detail', pk=groupe.pk)
    else:
        form = GroupeMedicamentForm()
    return render(request, 'medicament/groupe/form.html', {
        'form': form, 'title': 'Nouveau groupe',
        'medicaments_json': _medicaments_json(),
    })


@_login
def groupe_detail(request, pk):
    groupe = get_object_or_404(
        GroupeMedicament.objects.select_related('medecin').prefetch_related('lignes__medicament'), pk=pk
    )
    return render(request, 'medicament/groupe/detail.html', {'groupe': groupe})


@_login
def groupe_edit(request, pk):
    groupe   = get_object_or_404(GroupeMedicament, pk=pk)
    next_url = request.GET.get('next', '')
    if request.method == 'POST':
        form = GroupeMedicamentForm(request.POST, instance=groupe)
        if form.is_valid():
            form.save()
            groupe.lignes.all().delete()
            _save_lignes(request, groupe)
            messages.success(request, "Groupe mis à jour.")
            return redirect(next_url or 'medicament:groupe_detail', pk=pk)
    else:
        form = GroupeMedicamentForm(instance=groupe)

    existing = [
        {
            'medicament_id':       l.medicament_id,
            'medicament_nom':      str(l.medicament),
            'autorise':            l.autorise,
            'frequence_posologique': l.frequence_posologique,
            'dosage':              l.dosage,
            'unite_dosage':        l.unite_dosage,
            'qte_par_jour':        str(l.qte_par_jour),
            'jours':               l.jours,
            'commentaire':         l.commentaire,
        }
        for l in groupe.lignes.select_related('medicament').all()
    ]
    return render(request, 'medicament/groupe/form.html', {
        'form': form, 'groupe': groupe,
        'title': f'Modifier — {groupe.nom}',
        'next_url': next_url,
        'existing_lignes_json': json.dumps(existing),
        'medicaments_json': _medicaments_json(),
    })


def _save_lignes(request, groupe):
    i = 0
    while f'ligne_med_{i}' in request.POST:
        med_id = request.POST.get(f'ligne_med_{i}')
        if med_id:
            LigneMedicamentGroupe.objects.create(
                groupe=groupe, medicament_id=med_id,
                autorise=request.POST.get(f'ligne_autorise_{i}') == 'on',
                frequence_posologique=request.POST.get(f'ligne_freq_{i}', ''),
                dosage=request.POST.get(f'ligne_dosage_{i}', ''),
                unite_dosage=request.POST.get(f'ligne_unite_{i}', ''),
                qte_par_jour=request.POST.get(f'ligne_qte_{i}', 1) or 1,
                jours=request.POST.get(f'ligne_jours_{i}', 1) or 1,
                commentaire=request.POST.get(f'ligne_comment_{i}', ''),
            )
        i += 1


def _medicaments_json():
    return json.dumps([
        {'id': m.pk, 'nom': str(m), 'dosage': m.dosage}
        for m in Medicament.objects.filter(actif=True).order_by('designation')
    ])


# ─── CONFIGURATION ────────────────────────────────────────────────────────────

def _config_view(request, model_class, form_class, template, list_url_name, pk=None):
    instance = get_object_or_404(model_class, pk=pk) if pk else None
    if request.method == 'POST':
        form = form_class(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Enregistré.")
            return redirect(list_url_name)
    else:
        form = form_class(instance=instance)
    return render(request, template, {
        'form': form, 'instance': instance,
        'objects': model_class.objects.all(),
    })


@_login
def config_compagnie(request, pk=None):
    return _config_view(request, CompagniePharma, CompagniePharmaForm,
        'medicament/config/compagnie.html', 'medicament:config_compagnie', pk)

@_login
def config_effet(request, pk=None):
    return _config_view(request, EffetTherapeutique, EffetTherapeutiqueForm,
        'medicament/config/effet.html', 'medicament:config_effet', pk)

@_login
def config_dosage(request, pk=None):
    return _config_view(request, DosageMedicament, DosageMedicamentForm,
        'medicament/config/dosage.html', 'medicament:config_dosage', pk)

@_login
def config_route(request, pk=None):
    return _config_view(request, RouteMedicament, RouteMedicamentForm,
        'medicament/config/route.html', 'medicament:config_route', pk)

@_login
def config_formulaire(request, pk=None):
    return _config_view(request, FormulaireType, FormulaireTypeForm,
        'medicament/config/formulaire.html', 'medicament:config_formulaire', pk)
