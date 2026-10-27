"""Écrans des tiers payants (lot 6) : créances, bordereaux, règlements.
Les règles vivent dans comptabilite/assurances.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import assurances as regles
from . import ecritures as moteur
from .models import BordereauAssurance, ReglementAssurance


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _date(valeur, defaut=None):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


def _assurance(pk):
    from patients.models import Assurance
    return get_object_or_404(Assurance, pk=pk)


@login_required(login_url='login')
def assurances(request):
    """Ce que doit chaque assureur, et ce qui n'est pas encore envoyé."""
    _exiger(request.user, 'comptabilite.view_bordereauassurance')
    return render(request, 'comptabilite/assurances.html', {'lignes': regles.synthese_par_assureur()})


@login_required(login_url='login')
def creances_assureur(request, pk):
    _exiger(request.user, 'comptabilite.view_bordereauassurance')
    assurance = _assurance(pk)
    aujourdhui = timezone.localdate()
    debut = _date(request.GET.get('debut') or request.POST.get('debut'), aujourdhui.replace(day=1))
    fin = _date(request.GET.get('fin') or request.POST.get('fin'), aujourdhui)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.add_bordereauassurance')
        try:
            bordereau = regles.preparer_bordereau(assurance, debut, fin, request.user)
        except regles.ErreurAssurance as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"Bordereau {bordereau.numero} préparé.")
            return redirect('comptabilite:bordereau', pk=bordereau.pk)
    creances = regles.creances(assurance)
    return render(request, 'comptabilite/creances_assureur.html', {
        'assurance': assurance, 'creances': creances, 'total': sum((r for _, r in creances), Decimal('0')),
        'a_envoyer': regles.a_bordereauter(assurance, debut, fin), 'debut': debut, 'fin': fin,
        'bordereaux': assurance.bordereaux.order_by('-cree_le')[:20],
    })


@login_required(login_url='login')
def bordereaux(request):
    _exiger(request.user, 'comptabilite.view_bordereauassurance')
    qs = BordereauAssurance.objects.select_related('assurance').order_by('-cree_le')
    statut = request.GET.get('statut', '')
    if statut in dict(BordereauAssurance.STATUT):
        qs = qs.filter(statut=statut)
    lignes = [(b, regles.contenu_bordereau(b)) for b in qs[:200]]
    return render(request, 'comptabilite/bordereaux.html', {
        'lignes': lignes, 'statut': statut, 'statuts': BordereauAssurance.STATUT})


@login_required(login_url='login')
def bordereau(request, pk):
    _exiger(request.user, 'comptabilite.view_bordereauassurance')
    b = get_object_or_404(BordereauAssurance.objects.select_related('assurance'), pk=pk)
    return render(request, 'comptabilite/bordereau.html', {
        'b': b, 'contenu': regles.contenu_bordereau(b), 'reglements': b.reglements.order_by('date'),
        'peut_modifier': request.user.has_perm('comptabilite.change_bordereauassurance'),
        'peut_regler': request.user.has_perm('comptabilite.add_reglementassurance'),
    })


@login_required(login_url='login')
def bordereau_imprimer(request, pk):
    _exiger(request.user, 'comptabilite.view_bordereauassurance')
    b = get_object_or_404(BordereauAssurance.objects.select_related('assurance'), pk=pk)
    return render(request, 'comptabilite/bordereau_print.html', {
        'b': b, 'contenu': regles.contenu_bordereau(b), 'imprime_le': timezone.now()})


@login_required(login_url='login')
@require_POST
def bordereau_action(request, pk):
    _exiger(request.user, 'comptabilite.change_bordereauassurance')
    b = get_object_or_404(BordereauAssurance, pk=pk)
    try:
        if request.POST.get('action') == 'envoyer':
            regles.marquer_envoye(b, _date(request.POST.get('date_envoi')))
            messages.success(request, f"Bordereau {b.numero} marqué comme envoyé.")
        elif request.POST.get('action') == 'retirer':
            from facturation.models import Facture
            facture = get_object_or_404(Facture, pk=request.POST.get('facture'))
            regles.retirer_du_bordereau(b, facture)
            messages.success(request, f"Facture {facture.numero} retirée du bordereau.")
    except regles.ErreurAssurance as e:
        messages.error(request, str(e))
    return redirect('comptabilite:bordereau', pk=b.pk)


@login_required(login_url='login')
def reglements(request):
    _exiger(request.user, 'comptabilite.view_reglementassurance')
    return render(request, 'comptabilite/reglements.html', {
        'reglements': ReglementAssurance.objects.select_related('assurance', 'bordereau').order_by('-date', '-pk')[:300]})


@login_required(login_url='login')
def reglement_nouveau(request):
    """Règlement d'un assureur, réparti sur ses factures."""
    from patients.models import Assurance
    _exiger(request.user, 'comptabilite.add_reglementassurance')
    saisie = request.POST if request.method == 'POST' else request.GET
    assurance = Assurance.objects.filter(pk=saisie.get('assurance')).first()
    bordereau_ = BordereauAssurance.objects.filter(pk=saisie.get('bordereau')).first()
    if bordereau_ and assurance is None:
        assurance = bordereau_.assurance
    if request.method == 'POST':
        try:
            montant = Decimal(str(request.POST.get('montant', '')).replace(' ', '').replace(',', '.'))
        except InvalidOperation:
            montant = None
        jour = _date(request.POST.get('date'))
        if assurance is None or montant is None or jour is None:
            messages.error(request, "Assureur, date et montant sont obligatoires.")
        else:
            try:
                reglement, affectations = regles.enregistrer_reglement(
                    assurance, montant, jour, request.POST.get('mode', 'virement'), request.user,
                    request.POST.get('reference', '').strip(), bordereau_, request.POST.get('observation', ''))
            except regles.ErreurAssurance as e:
                messages.error(request, str(e))
            else:
                try:
                    moteur.ecriture_reglement(reglement)
                except moteur.ErreurCompta as e:
                    messages.warning(request, f"Règlement enregistré, écriture non préparée : {e}")
                messages.success(request, f"Règlement {reglement.numero} enregistré et réparti sur "
                                          f"{len(affectations)} facture(s).")
                return redirect('comptabilite:reglements')
    return render(request, 'comptabilite/reglement_form.html', {
        'assurances': Assurance.objects.filter(actif=True).order_by('nom'), 'assurance': assurance,
        'bordereaux': (BordereauAssurance.objects.filter(assurance=assurance).exclude(statut='regle')
                       if assurance else []),
        'bordereau': bordereau_,
        'du': (regles.contenu_bordereau(bordereau_)['reste'] if bordereau_ else
               sum((r for _, r in regles.creances(assurance)), Decimal('0')) if assurance else None),
        'modes': ReglementAssurance.MODE, 'saisie': saisie, 'aujourdhui': timezone.localdate(),
    })
