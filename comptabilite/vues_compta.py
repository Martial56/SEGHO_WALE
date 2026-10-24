"""Écrans de comptabilité générale : écritures, passage, OD, plan comptable,
correspondances (lot 3). Les règles vivent dans comptabilite/ecritures.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ecritures as moteur
from .models import Compte, Correspondance, Ecriture, Journal

ZERO = Decimal('0')


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _date(valeur, defaut):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


@login_required(login_url='login')
def ecritures(request):
    """Liste des écritures, génération et passage (validation)."""
    _exiger(request.user, 'comptabilite.view_ecriture')
    peut_passer = request.user.has_perm('comptabilite.passer_ecritures')
    aujourdhui = timezone.localdate()

    if request.method == 'POST':
        if not peut_passer:
            raise PermissionDenied
        action = request.POST.get('action')
        if action == 'generer':
            debut = _date(request.POST.get('debut'), aujourdhui.replace(month=1, day=1))
            fin = _date(request.POST.get('fin'), aujourdhui)
            resultat = moteur.generer(debut, fin)
            messages.success(request, f"{resultat['crees']} écriture(s) générée(s) en brouillon "
                                      f"du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}.")
            for erreur in resultat['erreurs'][:10]:
                messages.warning(request, erreur)
            if len(resultat['erreurs']) > 10:
                messages.warning(request, f"… et {len(resultat['erreurs']) - 10} autre(s) pièce(s) en erreur.")
        elif action == 'valider':
            ids = request.POST.getlist('ecriture')
            choisies = list(Ecriture.objects.filter(pk__in=ids, statut='brouillon')
                            .select_related('journal', 'exercice'))
            try:
                n = moteur.valider(choisies, request.user)
            except moteur.ErreurCompta as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"{n} écriture(s) validée(s).")
        return redirect(request.get_full_path())

    debut = _date(request.GET.get('debut'), aujourdhui.replace(day=1))
    fin = _date(request.GET.get('fin'), aujourdhui)
    statut = request.GET.get('statut', 'brouillon')
    code_journal = request.GET.get('journal', '')
    qs = (Ecriture.objects.filter(date__range=[debut, fin])
          .select_related('journal', 'exercice').prefetch_related('lignes__compte')
          .annotate(total=Sum('lignes__debit')).order_by('date', 'journal__code', 'pk'))
    if statut in ('brouillon', 'validee'):
        qs = qs.filter(statut=statut)
    if code_journal:
        qs = qs.filter(journal__code=code_journal)
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'comptabilite/ecritures.html', {
        'page': page, 'debut': debut, 'fin': fin, 'statut': statut, 'code_journal': code_journal,
        'journaux': Journal.objects.filter(actif=True), 'peut_passer': peut_passer,
        'nb_brouillons': Ecriture.objects.filter(statut='brouillon').count(),
        'debut_exercice': aujourdhui.replace(month=1, day=1), 'aujourdhui': aujourdhui,
    })


@login_required(login_url='login')
def ecriture_detail(request, pk):
    _exiger(request.user, 'comptabilite.view_ecriture')
    ecriture = get_object_or_404(Ecriture.objects.select_related(
        'journal', 'exercice', 'cree_par', 'validee_par', 'contre_passation_de'), pk=pk)
    debit, credit = ecriture.totaux()
    return render(request, 'comptabilite/ecriture_detail.html', {
        'ecriture': ecriture, 'lignes': ecriture.lignes.select_related('compte'),
        'debit': debit, 'credit': credit,
        'contre_passee_par': getattr(ecriture, 'contre_passee_par', None),
        'peut_passer': request.user.has_perm('comptabilite.passer_ecritures'),
    })


@login_required(login_url='login')
@require_POST
def ecriture_action(request, pk):
    _exiger(request.user, 'comptabilite.passer_ecritures')
    ecriture = get_object_or_404(Ecriture, pk=pk)
    action = request.POST.get('action')
    try:
        if action == 'valider':
            moteur.valider([ecriture], request.user)
            messages.success(request, f"Écriture validée : {ecriture.reference}.")
        elif action == 'contre_passer':
            inverse = moteur.contre_passer(ecriture, request.user)
            messages.success(request, "Contre-passation préparée en brouillon : validez-la au passage des écritures.")
            return redirect('comptabilite:ecriture', pk=inverse.pk)
        elif action == 'supprimer':
            moteur.supprimer_brouillon(ecriture)
            messages.success(request, "Brouillon supprimé. S'il venait de la facturation, il sera "
                                      "recréé à la prochaine génération.")
            return redirect('comptabilite:ecritures')
    except moteur.ErreurCompta as e:
        messages.error(request, str(e))
    return redirect('comptabilite:ecriture', pk=ecriture.pk)


def _montant(valeur):
    try:
        m = Decimal(str(valeur or '0').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        raise moteur.ErreurCompta(f"Montant illisible : « {valeur} ».")
    if m < 0:
        raise moteur.ErreurCompta("Les montants sont positifs : choisissez la colonne débit ou crédit.")
    return m


@login_required(login_url='login')
def od_saisie(request):
    """Saisie d'une opération diverse (salaires, loyers, régularisations…)."""
    _exiger(request.user, 'comptabilite.add_ecriture')
    aujourdhui = timezone.localdate()
    lignes_saisies = []
    if request.method == 'POST':
        n = 0
        while f'compte_{n}' in request.POST:
            lignes_saisies.append({k: request.POST.get(f'{k}_{n}', '') for k in
                                   ('compte', 'libelle', 'tiers', 'debit', 'credit')})
            n += 1
        try:
            jour = _date(request.POST.get('date'), None)
            if jour is None:
                raise moteur.ErreurCompta("Indiquez la date de l'opération.")
            libelle = request.POST.get('libelle', '').strip()
            if not libelle:
                raise moteur.ErreurCompta("Indiquez le libellé de l'opération.")
            journal_ = get_object_or_404(Journal, pk=request.POST.get('journal'))
            lignes = []
            for l in lignes_saisies:
                if not l['compte'] and not l['debit'] and not l['credit']:
                    continue
                c = Compte.objects.filter(numero=l['compte'].split(' ')[0].strip(), actif=True).first()
                if c is None:
                    raise moteur.ErreurCompta(f"Compte inconnu : « {l['compte']} ».")
                d, cr = _montant(l['debit']), _montant(l['credit'])
                if d and cr:
                    raise moteur.ErreurCompta(f"Compte {c.numero} : une ligne est au débit ou au crédit, pas les deux.")
                lignes.append((c, l['libelle'], d, cr, l['tiers']))
            ecriture = moteur.creer_ecriture(journal_, jour, libelle, lignes,
                                             piece=request.POST.get('piece', '').strip(), par=request.user)
        except moteur.ErreurCompta as e:
            messages.error(request, str(e))
        else:
            messages.success(request, "Opération enregistrée en brouillon : validez-la au passage des écritures.")
            return redirect('comptabilite:ecriture', pk=ecriture.pk)
    while len(lignes_saisies) < 4:
        lignes_saisies.append({'compte': '', 'libelle': '', 'tiers': '', 'debit': '', 'credit': ''})
    return render(request, 'comptabilite/od_saisie.html', {
        'journaux': Journal.objects.filter(actif=True).order_by('code'),
        'journal_defaut': Journal.objects.filter(code='OD').first(),
        'comptes': Compte.objects.filter(actif=True),
        'lignes': lignes_saisies, 'aujourdhui': aujourdhui, 'post': request.POST,
    })


@login_required(login_url='login')
def plan_comptable(request, pk=None):
    from django import forms

    _exiger(request.user, 'comptabilite.view_compte')
    peut_modifier = request.user.has_perm('comptabilite.change_compte')

    class CompteForm(forms.ModelForm):
        class Meta:
            model = Compte
            fields = ['numero', 'intitule', 'actif', 'a_valider']

        def clean_numero(self):
            numero = self.cleaned_data['numero'].strip()
            if not numero.isdigit() or numero[0] not in '12345678':
                raise forms.ValidationError("Un numéro de compte est fait de chiffres et commence par une classe de 1 à 8.")
            if self.instance.pk and self.instance.numero != numero and self.instance.lignes.exists():
                raise forms.ValidationError("Ce compte porte déjà des écritures : son numéro ne change plus.")
            return numero

    objet = get_object_or_404(Compte, pk=pk) if pk else None
    form = CompteForm(request.POST or None, instance=objet)
    for champ in ('numero', 'intitule'):
        form.fields[champ].widget.attrs['class'] = 'cpt-input'
    if request.method == 'POST':
        if not peut_modifier:
            raise PermissionDenied
        if form.is_valid():
            c = form.save()
            messages.success(request, f"Compte {c} enregistré.")
            return redirect('comptabilite:plan_comptable')
    q = request.GET.get('q', '').strip()
    comptes = Compte.objects.all()
    if q:
        comptes = comptes.filter(Q(numero__startswith=q) | Q(intitule__icontains=q))
    return render(request, 'comptabilite/plan_comptable.html', {
        'comptes': comptes, 'form': form, 'objet': objet, 'q': q, 'peut_modifier': peut_modifier,
        'nb_a_valider': Compte.objects.filter(a_valider=True).count(),
    })


@login_required(login_url='login')
def correspondances(request):
    _exiger(request.user, 'comptabilite.view_correspondance')
    peut_modifier = request.user.has_perm('comptabilite.change_correspondance')
    lignes = list(Correspondance.objects.select_related('compte').order_by('cle'))
    if request.method == 'POST':
        if not peut_modifier:
            raise PermissionDenied
        comptes = {c.pk: c for c in Compte.objects.filter(actif=True)}
        changes = 0
        for corr in lignes:
            choix = request.POST.get(f'corr_{corr.pk}')
            if choix and choix.isdigit() and int(choix) in comptes and int(choix) != corr.compte_id:
                corr.compte = comptes[int(choix)]
                corr.save(update_fields=['compte'])
                changes += 1
        messages.success(request, f"{changes} correspondance(s) modifiée(s).")
        return redirect('comptabilite:correspondances')
    return render(request, 'comptabilite/correspondances.html', {
        'lignes': lignes, 'comptes': Compte.objects.filter(actif=True), 'peut_modifier': peut_modifier,
    })
