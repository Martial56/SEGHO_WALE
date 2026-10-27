"""Écrans de trésorerie (lot 7) : position, comptes, remises en banque,
relevés, rapprochement ; et le refus d'un assureur. Les règles vivent dans
comptabilite/tresorerie.py et comptabilite/assurances.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import assurances as tiers
from . import ecritures as moteur
from . import tresorerie as regles
from .models import Compte, CompteTresorerie, LigneEcriture, LigneReleve, RemiseBanque


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _date(valeur, defaut=None):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


def _montant(valeur):
    try:
        return Decimal(str(valeur or '').replace(' ', '').replace(',', '.'))
    except InvalidOperation:
        return None


@login_required(login_url='login')
def tresorerie(request):
    """Où est l'argent : solde de chaque compte de trésorerie."""
    _exiger(request.user, 'comptabilite.view_comptetresorerie')
    fin = _date(request.GET.get('date'), timezone.localdate())
    lignes = regles.position(fin)
    return render(request, 'comptabilite/tresorerie.html', {
        'fin': fin, 'lignes': lignes, 'total': sum((l['solde'] for l in lignes), Decimal('0')),
        'comptes': CompteTresorerie.objects.filter(actif=True).select_related('compte'),
    })


class CompteTresorerieForm(forms.ModelForm):
    class Meta:
        model = CompteTresorerie
        fields = ['libelle', 'type', 'compte', 'etablissement', 'numero', 'solde_initial', 'date_solde_initial', 'actif']
        widgets = {'date_solde_initial': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['compte'].queryset = Compte.objects.filter(actif=True, numero__startswith='5')
        self.fields['compte'].help_text = "Compte de classe 5 (créez un sous-compte 5211, 5212… par banque si besoin)."
        for nom, champ in self.fields.items():
            if not isinstance(champ.widget, forms.CheckboxInput):
                champ.widget.attrs.setdefault('class', 'cpt-input')


@login_required(login_url='login')
def comptes_tresorerie(request, pk=None):
    _exiger(request.user, 'comptabilite.view_comptetresorerie')
    objet = get_object_or_404(CompteTresorerie, pk=pk) if pk else None
    form = CompteTresorerieForm(request.POST or None, instance=objet)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.change_comptetresorerie' if objet else 'comptabilite.add_comptetresorerie')
        if form.is_valid():
            ct = form.save()
            messages.success(request, f"Compte de trésorerie « {ct} » enregistré.")
            return redirect('comptabilite:comptes_tresorerie')
    return render(request, 'comptabilite/comptes_tresorerie.html', {
        'form': form, 'objet': objet, 'comptes': CompteTresorerie.objects.select_related('compte'),
        'peut_modifier': request.user.has_perm('comptabilite.change_comptetresorerie'),
    })


@login_required(login_url='login')
def remises(request):
    """Espèces des caisses déposées en banque."""
    from facturation.models import Caisse
    _exiger(request.user, 'comptabilite.view_remisebanque')
    aujourdhui = timezone.localdate()
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.add_remisebanque')
        caisse = Caisse.objects.filter(pk=request.POST.get('caisse')).first()
        ct = CompteTresorerie.objects.filter(pk=request.POST.get('compte_tresorerie')).first()
        montant = _montant(request.POST.get('montant'))
        jour = _date(request.POST.get('date'), aujourdhui)
        if caisse is None or ct is None or montant is None:
            messages.error(request, "Caisse, compte de dépôt et montant sont obligatoires.")
        else:
            try:
                remise = regles.creer_remise(caisse, ct, montant, jour, request.user,
                                             request.POST.get('reference', '').strip(),
                                             request.POST.get('observation', ''))
            except (regles.ErreurTresorerie, moteur.ErreurCompta) as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"Remise {remise.numero} enregistrée ; ses deux écritures sont préparées.")
                return redirect('comptabilite:remises')
    caisses = list(Caisse.objects.filter(actif=True).order_by('nom'))
    soldes = {}
    for c in caisses:
        try:
            soldes[c.pk] = regles.solde_comptable(moteur.compte_de_caisse(c), aujourdhui)
        except moteur.ErreurCompta:
            soldes[c.pk] = None
    return render(request, 'comptabilite/remises.html', {
        'remises': RemiseBanque.objects.select_related('caisse', 'compte_tresorerie')[:200],
        'caisses': [(c, soldes[c.pk]) for c in caisses],
        'comptes': CompteTresorerie.objects.filter(actif=True, type='banque') or CompteTresorerie.objects.filter(actif=True),
        'aujourdhui': aujourdhui, 'post': request.POST,
    })


@login_required(login_url='login')
def rapprochement(request, pk):
    """Relevé et écritures d'un compte de trésorerie, côte à côte, à pointer."""
    _exiger(request.user, 'comptabilite.view_lignereleve')
    ct = get_object_or_404(CompteTresorerie.objects.select_related('compte'), pk=pk)
    fin = _date(request.GET.get('date') or request.POST.get('date'), timezone.localdate())
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.change_lignereleve')
        action = request.POST.get('action')
        try:
            if action == 'importer':
                _exiger(request.user, 'comptabilite.add_lignereleve')
                fichier = request.FILES.get('fichier')
                if not fichier:
                    raise regles.ErreurTresorerie("Choisissez le fichier du relevé (CSV).")
                crees, ignorees = regles.importer_releve(ct, fichier.read(), request.user,
                                                         request.POST.get('format', 'montant'))
                messages.success(request, f"{crees} ligne(s) de relevé importée(s).")
                if ignorees:
                    messages.warning(request, f"Lignes ignorées (en-tête ou illisibles) : "
                                              f"{', '.join(str(n) for n in ignorees[:15])}.")
            elif action == 'ajouter':
                _exiger(request.user, 'comptabilite.add_lignereleve')
                jour, montant = _date(request.POST.get('ligne_date')), _montant(request.POST.get('ligne_montant'))
                libelle = request.POST.get('ligne_libelle', '').strip()
                if jour is None or not montant or not libelle:
                    raise regles.ErreurTresorerie("Date, libellé et montant (non nul) sont obligatoires.")
                LigneReleve.objects.create(compte_tresorerie=ct, date=jour, libelle=libelle[:255], montant=montant,
                                           reference=request.POST.get('ligne_reference', '')[:100],
                                           cree_par=request.user)
                messages.success(request, "Ligne de relevé ajoutée.")
            elif action == 'auto':
                n = regles.rapprochement_automatique(ct)
                messages.success(request, f"{n} ligne(s) rapprochée(s) automatiquement.")
            elif action == 'pointer':
                releve = get_object_or_404(LigneReleve, pk=request.POST.get('releve'), compte_tresorerie=ct)
                ligne = get_object_or_404(LigneEcriture, pk=request.POST.get('ecriture'))
                regles.rapprocher(releve, ligne)
                messages.success(request, "Lignes rapprochées.")
            elif action == 'defaire':
                regles.defaire(get_object_or_404(LigneReleve, pk=request.POST.get('releve'), compte_tresorerie=ct))
                messages.success(request, "Rapprochement défait.")
            elif action == 'comptabiliser':
                _exiger(request.user, 'comptabilite.add_ecriture')
                releve = get_object_or_404(LigneReleve, pk=request.POST.get('releve'), compte_tresorerie=ct)
                contrepartie = get_object_or_404(Compte, pk=request.POST.get('contrepartie'))
                regles.comptabiliser_ligne_releve(releve, contrepartie, request.user)
                messages.success(request, "Opération passée en écriture (brouillon) et rapprochée.")
        except (regles.ErreurTresorerie, moteur.ErreurCompta) as e:
            messages.error(request, str(e))
        return redirect(f"{request.path}?date={fin.isoformat()}")

    etat = regles.etat_rapprochement(ct, fin)
    try:
        frais = moteur.compte('frais_bancaires').pk
    except moteur.ErreurCompta:
        frais = None
    return render(request, 'comptabilite/rapprochement.html', {
        'ct': ct, 'fin': fin, 'etat': etat,
        'rapprochees': ct.releve.filter(ligne_ecriture__isnull=False, date__lte=fin)
                       .select_related('ligne_ecriture__ecriture').order_by('-date')[:100],
        'comptes': Compte.objects.filter(actif=True).exclude(pk=ct.compte_id), 'frais': frais,
        'peut_modifier': request.user.has_perm('comptabilite.change_lignereleve'),
    })


@login_required(login_url='login')
def rejet_assurance(request, pk):
    """Refus par l'assureur de tout ou partie de sa part sur une facture."""
    from facturation.models import Facture
    _exiger(request.user, 'comptabilite.add_rejetassurance')
    facture = get_object_or_404(Facture.objects.select_related('patient', 'assurance'), pk=pk)
    if not facture.assurance_id:
        messages.error(request, "Cette facture n'a pas de part assurance.")
        return redirect('facturation:detail', pk=facture.pk)
    if request.method == 'POST':
        try:
            rejet = tiers.rejeter(facture, _montant(request.POST.get('montant')) or Decimal('0'),
                                  request.POST.get('decision'), request.POST.get('motif', ''),
                                  _date(request.POST.get('date'), timezone.localdate()), request.user)
        except tiers.ErreurAssurance as e:
            messages.error(request, str(e))
        else:
            try:
                moteur.ecriture_rejet(rejet)
            except moteur.ErreurCompta as e:
                messages.warning(request, f"Refus enregistré, écriture non préparée : {e}")
            messages.success(request, f"Refus {rejet.numero} enregistré ({rejet.get_decision_display().lower()}).")
            return redirect('comptabilite:creances_assureur', pk=facture.assurance_id)
    return render(request, 'comptabilite/rejet_form.html', {
        'facture': facture, 'aujourdhui': timezone.localdate(),
        'rejets': facture.rejets_assurance.order_by('-date'),
    })
