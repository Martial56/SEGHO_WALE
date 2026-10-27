"""Écrans des financements (lot 5) : bailleurs, conventions, versements, dons,
budget annuel, fonds dédiés. Les calculs vivent dans comptabilite/financements.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.views import log_event

from . import ecritures as moteur
from . import financements as fin
from .forms import BailleurForm, ConventionForm, DonForm, LigneBudgetaireFormSet, VersementForm
from .models import Bailleur, Compte, Convention, Don, Exercice, LigneBudget, LigneEcriture


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _exercice(request):
    """Exercice choisi, ou celui de l'année en cours (créé s'il manque)."""
    choisi = Exercice.objects.filter(pk=request.GET.get('exercice') or request.POST.get('exercice')).first()
    if choisi:
        return choisi
    jour = timezone.localdate()
    existant = Exercice.objects.filter(date_debut__lte=jour, date_fin__gte=jour).first()
    return existant or Exercice.objects.create(libelle=str(jour.year), date_debut=date(jour.year, 1, 1),
                                               date_fin=date(jour.year, 12, 31))


# ─── Bailleurs ─────────────────────────────────────────────────────────────────

@login_required(login_url='login')
def bailleurs(request, pk=None):
    _exiger(request.user, 'comptabilite.view_bailleur')
    objet = get_object_or_404(Bailleur, pk=pk) if pk else None
    form = BailleurForm(request.POST or None, instance=objet)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.change_bailleur' if objet else 'comptabilite.add_bailleur')
        if form.is_valid():
            b = form.save()
            messages.success(request, f"Partenaire « {b} » enregistré.")
            return redirect('comptabilite:bailleurs')
    return render(request, 'comptabilite/bailleurs.html', {
        'form': form, 'objet': objet, 'bailleurs': Bailleur.objects.all(),
        'peut_modifier': request.user.has_perm('comptabilite.change_bailleur')
                         or request.user.has_perm('comptabilite.add_bailleur'),
    })


# ─── Conventions ───────────────────────────────────────────────────────────────

@login_required(login_url='login')
def conventions(request):
    _exiger(request.user, 'comptabilite.view_convention')
    statut = request.GET.get('statut', 'active')
    qs = Convention.objects.select_related('bailleur')
    if statut in dict(Convention.STATUT):
        qs = qs.filter(statut=statut)
    return render(request, 'comptabilite/conventions.html', {
        'suivis': [fin.suivi(c) for c in qs], 'statut': statut, 'statuts': Convention.STATUT,
    })


@login_required(login_url='login')
def convention_form(request, pk=None):
    objet = get_object_or_404(Convention, pk=pk) if pk else None
    _exiger(request.user, 'comptabilite.change_convention' if objet else 'comptabilite.add_convention')
    form = ConventionForm(request.POST or None, instance=objet)
    budget = LigneBudgetaireFormSet(request.POST or None, instance=objet or Convention(), prefix='budget')
    if request.method == 'POST' and form.is_valid() and budget.is_valid():
        with transaction.atomic():
            convention = form.save()
            budget.instance = convention
            budget.save()
        messages.success(request, f"Convention {convention.code} enregistrée.")
        return redirect('comptabilite:convention', pk=convention.pk)
    return render(request, 'comptabilite/convention_form.html', {'form': form, 'budget': budget, 'objet': objet})


@login_required(login_url='login')
def convention_detail(request, pk):
    _exiger(request.user, 'comptabilite.view_convention')
    convention = get_object_or_404(Convention.objects.select_related('bailleur', 'compte_ressource'), pk=pk)
    form = VersementForm(request.POST or None, initial={'date': timezone.localdate()})
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.add_versement')
        if form.is_valid():
            versement = form.save(commit=False)
            versement.convention = convention
            versement.cree_par = request.user
            versement.centre = convention.centre
            versement.save()
            log_event(convention, request.user, f'Versement {versement} reçu.', type='modif',
                      module='comptabilite')
            try:
                moteur.ecriture_versement(versement)
            except moteur.ErreurCompta as e:
                messages.warning(request, f"Versement enregistré, écriture non préparée : {e}")
            messages.success(request, f"Versement {versement.numero} enregistré.")
            return redirect('comptabilite:convention', pk=convention.pk)
    depenses = (LigneEcriture.objects.filter(convention=convention, compte__numero__startswith='6')
                .select_related('ecriture__journal', 'compte').order_by('-ecriture__date'))
    return render(request, 'comptabilite/convention_detail.html', {
        'convention': convention, 'suivi': fin.suivi(convention), 'form': form,
        'versements': convention.versements.order_by('-date'), 'dons': convention.dons.order_by('-date'),
        'depenses': depenses[:200],
        'peut_recevoir': request.user.has_perm('comptabilite.add_versement'),
        'peut_modifier': request.user.has_perm('comptabilite.change_convention'),
    })


# ─── Dons ──────────────────────────────────────────────────────────────────────

@login_required(login_url='login')
def dons(request):
    _exiger(request.user, 'comptabilite.view_don')
    jour = timezone.localdate()
    annee = int(request.GET.get('annee') or jour.year)
    qs = Don.objects.filter(date__year=annee).select_related('donateur', 'convention')
    return render(request, 'comptabilite/dons.html', {
        'dons': qs, 'annee': annee, 'total': sum((d.montant for d in qs), Decimal('0')),
        'annees': range(jour.year, jour.year - 6, -1),
    })


@login_required(login_url='login')
def don_form(request, pk=None):
    objet = get_object_or_404(Don, pk=pk) if pk else None
    _exiger(request.user, 'comptabilite.change_don' if objet else 'comptabilite.add_don')
    if objet and LigneEcriture.objects.filter(ecriture__origine=f'don:{objet.pk}',
                                              ecriture__statut='validee').exists():
        messages.error(request, "Ce don est déjà comptabilisé et validé : il ne se modifie plus.")
        return redirect('comptabilite:dons')
    if objet and objet.lignes.exists():
        messages.error(request, "Les produits de ce don sont entrés en stock : sa valeur est la leur, "
                                "il ne se modifie plus.")
        return redirect('comptabilite:dons')
    form = DonForm(request.POST or None, instance=objet, initial={'date': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            don = form.save(commit=False)
            if not objet:
                don.cree_par = request.user
            don.save()
            # Un don modifié avant validation : son brouillon est refait.
            from .models import Ecriture
            Ecriture.all_objects.filter(origine=f'don:{don.pk}', statut='brouillon').delete()
        try:
            moteur.ecriture_don(don)
        except moteur.ErreurCompta as e:
            messages.warning(request, f"Don enregistré, écriture non préparée : {e}")
        messages.success(request, f"Don {don.numero} enregistré.")
        return redirect('comptabilite:dons')
    return render(request, 'comptabilite/don_form.html', {'form': form, 'objet': objet})


@login_required(login_url='login')
def don_recu(request, pk):
    _exiger(request.user, 'comptabilite.view_don')
    don = get_object_or_404(Don.objects.select_related('donateur', 'convention'), pk=pk)
    return render(request, 'comptabilite/don_recu.html', {'don': don, 'imprime_le': timezone.now()})


# ─── Budget annuel ─────────────────────────────────────────────────────────────

def _montant(valeur):
    try:
        m = Decimal(str(valeur or '').replace(' ', '').replace(',', '.') or '0')
    except InvalidOperation:
        return None
    return m if m >= 0 else None


@login_required(login_url='login')
def budget(request):
    _exiger(request.user, 'comptabilite.view_lignebudget')
    exercice = _exercice(request)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.change_lignebudget')
        erreurs = 0
        with transaction.atomic():
            for compte in Compte.objects.filter(numero__regex=r'^[67]'):
                cle = f'budget_{compte.pk}'
                if cle not in request.POST:
                    continue
                montant = _montant(request.POST[cle])
                if montant is None:
                    erreurs += 1
                elif montant:
                    LigneBudget.objects.update_or_create(exercice=exercice, compte=compte,
                                                         defaults={'montant': montant})
                else:
                    LigneBudget.objects.filter(exercice=exercice, compte=compte).delete()
        if erreurs:
            messages.warning(request, f"{erreurs} montant(s) illisible(s) ignoré(s).")
        messages.success(request, f"Budget {exercice} enregistré.")
        return redirect(f"{request.path}?exercice={exercice.pk}")
    prevus = {lb.compte_id: lb.montant for lb in LigneBudget.objects.filter(exercice=exercice)}
    comptes = [(c, prevus.get(c.pk)) for c in Compte.objects.filter(actif=True, numero__regex=r'^[67]')]
    return render(request, 'comptabilite/budget.html', {
        'exercice': exercice, 'exercices': Exercice.objects.all(), 'comptes': comptes,
        'total_charges': sum((m for c, m in comptes if m and c.classe == '6'), Decimal('0')),
        'total_ressources': sum((m for c, m in comptes if m and c.classe == '7'), Decimal('0')),
        'peut_modifier': request.user.has_perm('comptabilite.change_lignebudget'),
    })


# ─── Fonds dédiés ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def fonds_dedies(request):
    _exiger(request.user, 'comptabilite.view_convention')
    exercice = _exercice(request)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.passer_ecritures')
        try:
            constitution, reprise = fin.ecritures_fonds_dedies(exercice, request.user)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
        else:
            if constitution or reprise:
                messages.success(request, "Écritures de fonds dédiés préparées en brouillon : "
                                          "validez-les au passage des écritures.")
            else:
                messages.info(request, "Rien à constater, ou écritures déjà préparées.")
        return redirect(f"{request.path}?exercice={exercice.pk}")
    from .models import Ecriture
    return render(request, 'comptabilite/fonds_dedies.html', {
        'exercice': exercice, 'exercices': Exercice.objects.all(),
        'resultats': fin.calcul_fonds_dedies(exercice),
        'ecritures': Ecriture.objects.filter(origine__in=[f'fonds_dedies:{exercice.pk}',
                                                          f'reprise_fonds_dedies:{exercice.pk}']),
        'peut_passer': request.user.has_perm('comptabilite.passer_ecritures'),
    })
