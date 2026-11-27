"""Écrans des bons de sortie de la petite caisse : liste, saisie, validation,
équilibrage. Les règles vivent dans comptabilite/bons_sortie.py."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.views import log_event

from . import bons_sortie as regles
from . import ecritures as moteur
from .forms import BonSortieForm
from .models import BonSortie, Compte, Convention, Tiers
from .vues_compta import lignes_ecriture, lignes_postees


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _mois(valeur, defaut):
    """« 2026-11 » → 1er novembre 2026."""
    try:
        annee, mois = (int(x) for x in (valeur or '').split('-'))
        return date(annee, mois, 1)
    except (TypeError, ValueError):
        return defaut


def _fin_du_mois(debut):
    suivant = date(debut.year + debut.month // 12, debut.month % 12 + 1, 1)
    return date.fromordinal(suivant.toordinal() - 1)


@login_required(login_url='login')
def bons_sortie(request):
    _exiger(request.user, 'comptabilite.view_bonsortie')
    aujourdhui = timezone.localdate()
    debut = _mois(request.GET.get('mois'), aujourdhui.replace(day=1))
    caisses = list(regles.caisses())
    caisse = next((c for c in caisses if str(c.pk) == request.GET.get('caisse')), None)
    etape = request.GET.get('etape', '')
    bons = (BonSortie.objects.filter(date__range=[debut, _fin_du_mois(debut)])
            .select_related('caisse', 'motif', 'cree_par').order_by('-date', '-pk'))
    if caisse:
        bons = bons.filter(caisse=caisse)
    bons = [b for b in bons if not etape or b.etape == etape]
    return render(request, 'comptabilite/bons_sortie.html', {
        'bons': bons, 'mois': debut, 'caisses': [(c, regles.disponible(c, aujourdhui)) for c in caisses],
        'caisse': caisse, 'etape': etape, 'etapes': BonSortie.ETAPES,
        'total': sum((b.montant for b in bons if b.statut != 'annule'), regles.ZERO),
        'a_equilibrer': sum(1 for b in bons if b.etape == 'a_equilibrer'),
    })


@login_required(login_url='login')
def bon_sortie_form(request, pk=None):
    """Saisie ou modification (brouillon) d'un bon. « Valider » l'arrête et
    ouvre l'équilibrage."""
    _exiger(request.user, 'comptabilite.add_bonsortie')
    bon = get_object_or_404(BonSortie, pk=pk) if pk else None
    if bon is not None and bon.statut != 'brouillon':
        messages.info(request, "Ce bon n'est plus modifiable.")
        return redirect('comptabilite:bon_sortie', pk=bon.pk)
    initial = {'date': timezone.localdate()}
    petite = regles.caisses().filter(compte__numero='57100005').first()
    if petite and bon is None:
        initial['caisse'] = petite
    form = BonSortieForm(request.POST or None, request.FILES or None, instance=bon, initial=initial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            bon = regles.enregistrer(request.user, d['caisse'], d['date'], d['motif'], d['libelle'], d['montant'],
                                     d['beneficiaire'], d['justificatif'], d['convention'], bon=bon)
        except regles.ErreurBon as e:
            messages.error(request, str(e))
        else:
            if request.POST.get('action') != 'valider':
                messages.success(request, f"Bon {bon.numero} enregistré en brouillon.")
                return redirect('comptabilite:bon_sortie', pk=bon.pk)
            try:
                regles.valider(bon, request.user)
            except regles.ErreurBon as e:
                messages.error(request, f"Bon {bon.numero} enregistré en brouillon, mais pas validé : {e}")
                return redirect('comptabilite:bon_sortie', pk=bon.pk)
            log_event(bon, request.user, f'Bon de sortie {bon.numero} validé — {bon.montant:,.0f} F'
                      .replace(',', ' '), type='modif', module='comptabilite')
            messages.success(request, f"Bon {bon.numero} validé : vérifiez et passez son écriture.")
            return redirect('comptabilite:bon_sortie_equilibrer', pk=bon.pk)
    caisse = (bon.caisse if bon else initial.get('caisse'))
    return render(request, 'comptabilite/bon_sortie_form.html', {
        'form': form, 'bon': bon,
        'disponibles': [(c, regles.disponible(c, sauf=bon)) for c in regles.caisses()],
        'caisse': caisse,
    })


@login_required(login_url='login')
def bon_sortie(request, pk):
    _exiger(request.user, 'comptabilite.view_bonsortie')
    bon = get_object_or_404(BonSortie.objects.select_related('caisse__compte', 'motif__compte', 'convention',
                                                             'cree_par', 'valide_par'), pk=pk)
    ecriture = bon.ecriture
    return render(request, 'comptabilite/bon_sortie.html', {
        'bon': bon, 'ecriture': ecriture,
        'lignes': ecriture.lignes.select_related('compte') if ecriture else regles.lignes_proposees(bon),
        'peut_saisir': request.user.has_perm('comptabilite.add_bonsortie'),
        'peut_annuler': request.user.has_perm('comptabilite.change_bonsortie'),
    })


@login_required(login_url='login')
@require_POST
def bon_sortie_action(request, pk):
    bon = get_object_or_404(BonSortie, pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'valider':
            _exiger(request.user, 'comptabilite.add_bonsortie')
            regles.valider(bon, request.user)
            log_event(bon, request.user, f'Bon de sortie {bon.numero} validé — {bon.montant:,.0f} F'
                      .replace(',', ' '), type='modif', module='comptabilite')
            messages.success(request, f"Bon {bon.numero} validé : vérifiez et passez son écriture.")
            return redirect('comptabilite:bon_sortie_equilibrer', pk=bon.pk)
        if action == 'annuler':
            _exiger(request.user, 'comptabilite.change_bonsortie')
            regles.annuler(bon)
            log_event(bon, request.user, f'Bon de sortie {bon.numero} annulé.', type='modif', module='comptabilite')
            messages.success(request, f"Bon {bon.numero} annulé.")
    except (regles.ErreurBon, moteur.ErreurCompta) as e:
        messages.error(request, str(e))
    return redirect('comptabilite:bon_sortie', pk=bon.pk)


def _ligne_affichee(compte, libelle, debit, credit, tiers, convention):
    return {'compte': f'{compte.numero} {compte.intitule}', 'libelle': libelle, 'tiers': str(tiers or ''),
            'debit': f'{debit:.0f}' if debit else '', 'credit': f'{credit:.0f}' if credit else '',
            'convention': str(convention.pk) if convention else ''}


@login_required(login_url='login')
def bon_sortie_equilibrer(request, pk):
    """Écriture du bon, préremplie depuis le bon : on contrôle, on peut changer
    de compte de charge ou répartir, et on passe l'écriture."""
    _exiger(request.user, 'comptabilite.add_bonsortie')
    bon = get_object_or_404(BonSortie.objects.select_related('caisse__compte', 'motif__compte', 'convention'), pk=pk)
    if bon.etape != 'a_equilibrer':
        messages.info(request, "Ce bon n'est pas à équilibrer.")
        return redirect('comptabilite:bon_sortie', pk=bon.pk)
    peut_passer = request.user.has_perm('comptabilite.passer_ecritures')
    lignes_saisies = []
    if request.method == 'POST':
        lignes_saisies = lignes_postees(request.POST)
        try:
            lignes = lignes_ecriture(lignes_saisies)
            valider = peut_passer and request.POST.get('action') == 'valider'
            ecriture = regles.equilibrer(bon, lignes, request.user, valider_ecriture=valider)
        except (regles.ErreurBon, moteur.ErreurCompta) as e:
            messages.error(request, str(e))
        else:
            messages.success(request, f"Écriture du bon {bon.numero} passée dans le journal {ecriture.journal.code}"
                                      + (f" et validée : {ecriture.reference}." if valider
                                         else " en brouillon : elle se valide au passage des écritures."))
            return redirect('comptabilite:bon_sortie', pk=bon.pk)
    else:
        lignes_saisies = [_ligne_affichee(*l) for l in regles.lignes_proposees(bon)]
    return render(request, 'comptabilite/bon_sortie_equilibrer.html', {
        'bon': bon, 'lignes': lignes_saisies, 'journal': regles.journal_du_bon(bon),
        'comptes': Compte.objects.imputables(), 'plan_tiers': Tiers.objects.filter(actif=True),
        'conventions': Convention.objects.filter(statut='active'), 'peut_passer': peut_passer,
    })
