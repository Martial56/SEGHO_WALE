"""Écrans des achats (lot 8) : factures fournisseurs, leurs règlements, et
l'entrée en stock des dons en nature. Les règles vivent dans
comptabilite/fournisseurs.py."""
from datetime import date
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.views import log_event

from . import ecritures as moteur
from . import fournisseurs as regles
from .forms import _Champs
from .models import CompteTresorerie, Convention, Don, Ecriture, FactureFournisseur, ReglementFournisseur

ZERO = Decimal('0')
NB_LIGNES_VIDES = 3


def _exiger(user, perm):
    if not user.has_perm(perm):
        raise PermissionDenied


def _montant(valeur):
    try:
        return Decimal(str(valeur or '').replace(' ', '').replace(' ', '').replace(',', '.') or '0')
    except InvalidOperation:
        return None


def _date(valeur, defaut=None):
    try:
        return date.fromisoformat(valeur)
    except (TypeError, ValueError):
        return defaut


# ─── Factures fournisseurs ─────────────────────────────────────────────────────

@login_required(login_url='login')
def factures_fournisseurs(request):
    _exiger(request.user, 'comptabilite.view_facturefournisseur')
    filtre = request.GET.get('filtre', 'a_regler')
    qs = FactureFournisseur.objects.prefetch_related('reglements')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(fournisseur__icontains=q) | qs.filter(reference__icontains=q) | qs.filter(numero__icontains=q)
    factures = list(qs[:500])
    if filtre == 'a_regler':
        factures = [f for f in factures if f.reste > 0]
    return render(request, 'comptabilite/factures_fournisseurs.html', {
        'factures': factures, 'filtre': filtre, 'q': q,
        'total_reste': sum((f.reste for f in factures), ZERO),
    })


class FactureFournisseurForm(_Champs, forms.ModelForm):
    class Meta:
        model = FactureFournisseur
        fields = ['fournisseur', 'reference', 'date', 'date_echeance', 'objet', 'convention', 'justificatif']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'date_echeance': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'fournisseur': forms.TextInput(attrs={'list': 'liste-fournisseurs', 'autocomplete': 'off'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['convention'].queryset = Convention.objects.filter(statut='active')
        self.fields['convention'].empty_label = '— Fonds propres du centre —'


def _lignes_postees(post):
    """[(compte, libellé, montant)] lues du formulaire, et les valeurs brutes pour le réafficher."""
    comptes = {str(c.pk): c for c in regles.comptes_d_achat()}
    lignes, brutes, erreurs = [], [], []
    for i in range(int(post.get('nb_lignes') or 0)):
        cid, lib, m = post.get(f'compte_{i}', ''), post.get(f'libelle_{i}', '').strip(), post.get(f'montant_{i}', '').strip()
        if not (cid or lib or m):
            continue
        brutes.append({'compte': cid, 'libelle': lib, 'montant': m})
        montant = _montant(m)
        if cid not in comptes:
            erreurs.append(f"Ligne {i + 1} : choisissez un compte.")
        elif montant is None:
            erreurs.append(f"Ligne {i + 1} : montant illisible.")
        else:
            lignes.append((comptes[cid], lib, montant))
    return lignes, brutes, erreurs


@login_required(login_url='login')
def facture_fournisseur_form(request, pk=None):
    objet = get_object_or_404(FactureFournisseur, pk=pk) if pk else None
    _exiger(request.user, 'comptabilite.change_facturefournisseur' if objet else 'comptabilite.add_facturefournisseur')
    initial = {'date': timezone.localdate()}
    lignes_initiales = []
    if objet:
        lignes_initiales = [{'compte': str(l.compte_id), 'libelle': l.libelle, 'montant': f'{l.montant:.0f}'}
                            for l in objet.lignes.all()]
    else:
        # Reprise de la valeur reçue d'une commande (Stock ou Achats).
        from achats.models import CommandeAchat
        from stock.models import CommandeStock
        commande_stock = CommandeStock.objects.filter(pk=request.GET.get('commande_stock') or None).first()
        commande_achat = CommandeAchat.objects.filter(pk=request.GET.get('commande_achat') or None).first()
        commande = commande_stock or commande_achat
        if commande:
            initial.update({'fournisseur': str(commande.fournisseur or ''), 'objet': f'Commande {commande.numero}',
                            'commande_stock': commande_stock, 'commande_achat': commande_achat})
            lignes = (regles.lignes_commande_stock(commande_stock) if commande_stock
                      else regles.lignes_commande_achat(commande_achat))
            lignes_initiales = [{'compte': str(c.pk), 'libelle': lib, 'montant': f'{m:.0f}'} for c, lib, m in lignes]
    form = FactureFournisseurForm(request.POST or None, request.FILES or None, instance=objet, initial=initial)
    lignes_affichees = lignes_initiales
    if request.method == 'POST':
        lignes, lignes_affichees, erreurs = _lignes_postees(request.POST)
        if form.is_valid() and not erreurs:
            facture = form.save(commit=False)
            if not objet:
                facture.commande_stock_id = request.POST.get('commande_stock') or None
                facture.commande_achat_id = request.POST.get('commande_achat') or None
            try:
                regles.enregistrer_facture(facture, lignes, request.user)
            except (regles.ErreurAchat, moteur.ErreurCompta) as e:
                erreurs.append(str(e))
            else:
                log_event(facture, request.user, f'Facture fournisseur {facture} enregistrée.',
                          type='modif', module='comptabilite')
                messages.success(request, f"Facture {facture.numero} enregistrée ; son écriture d'achat est "
                                          "prête en brouillon.")
                return redirect('comptabilite:facture_fournisseur', pk=facture.pk)
        for e in erreurs:
            messages.error(request, e)
    lignes_affichees = list(lignes_affichees) + [{}] * NB_LIGNES_VIDES
    return render(request, 'comptabilite/facture_fournisseur_form.html', {
        'form': form, 'objet': objet, 'lignes': lignes_affichees, 'comptes': regles.comptes_d_achat(),
        'fournisseurs': regles.noms_fournisseurs(),
        'commande_stock': initial.get('commande_stock'), 'commande_achat': initial.get('commande_achat'),
    })


@login_required(login_url='login')
def facture_fournisseur(request, pk):
    _exiger(request.user, 'comptabilite.view_facturefournisseur')
    facture = get_object_or_404(
        FactureFournisseur.objects.select_related('convention', 'commande_stock', 'commande_achat')
        .prefetch_related('lignes__compte',
                          Prefetch('reglements', queryset=ReglementFournisseur.objects.select_related('compte_tresorerie'))),
        pk=pk)
    if request.method == 'POST':
        _exiger(request.user, 'comptabilite.add_reglementfournisseur')
        ct = CompteTresorerie.objects.filter(pk=request.POST.get('compte_tresorerie') or None).first()
        mode = request.POST.get('mode', 'virement')
        if mode not in dict(ReglementFournisseur.MODE):
            mode = 'virement'
        try:
            reglement = regles.regler(facture, _montant(request.POST.get('montant')),
                                      _date(request.POST.get('date'), timezone.localdate()), mode, request.user,
                                      compte_tresorerie=ct, reference=request.POST.get('reference', '').strip())
        except (regles.ErreurAchat, moteur.ErreurCompta) as e:
            messages.error(request, str(e))
        else:
            log_event(facture, request.user, f'Règlement {reglement.numero} enregistré.', type='modif',
                      module='comptabilite')
            messages.success(request, f"Règlement {reglement.numero} enregistré.")
        return redirect('comptabilite:facture_fournisseur', pk=facture.pk)
    ecritures = Ecriture.objects.filter(
        origine__in=[f'facture_fournisseur:{facture.pk}']
        + [f'reglement_fournisseur:{r.pk}' for r in facture.reglements.all()]).select_related('journal')
    return render(request, 'comptabilite/facture_fournisseur.html', {
        'facture': facture, 'ecritures': ecritures, 'aujourdhui': timezone.localdate(),
        'comptes_tresorerie': CompteTresorerie.objects.filter(actif=True).select_related('compte'),
        'modes': ReglementFournisseur.MODE,
        'peut_regler': request.user.has_perm('comptabilite.add_reglementfournisseur') and facture.reste > 0,
        'peut_modifier': request.user.has_perm('comptabilite.change_facturefournisseur')
                         and not any(e.statut == 'validee' and e.origine.startswith('facture_') for e in ecritures),
    })


# ─── Don en nature : entrée en stock ───────────────────────────────────────────

@login_required(login_url='login')
def don_stock(request, pk):
    _exiger(request.user, 'comptabilite.change_don')
    _exiger(request.user, 'stock.add_mouvementstock')
    from stock.models import Produit
    don = get_object_or_404(Don, pk=pk)
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    if request.method == 'POST':
        lignes, illisibles = [], 0
        for p in produits:
            quantite = _montant(request.POST.get(f'qte_{p.pk}'))
            if not quantite:
                continue
            valeur = _montant(request.POST.get(f'valeur_{p.pk}'))
            if quantite is None or valeur is None:
                illisibles += 1
                continue
            lignes.append((p, quantite, valeur, request.POST.get(f'lot_{p.pk}', '').strip(),
                           _date(request.POST.get(f'peremption_{p.pk}'))))
        try:
            if illisibles:
                raise regles.ErreurAchat(f"{illisibles} ligne(s) illisible(s) : vérifiez quantités et valeurs.")
            regles.entrer_don_en_stock(don, lignes, request.user)
        except (regles.ErreurAchat, moteur.ErreurCompta) as e:
            messages.error(request, str(e))
        else:
            log_event(don, request.user, f'Produits du don {don.numero} entrés en stock.', type='modif',
                      module='comptabilite')
            messages.success(request, f"{len(lignes)} produit(s) entré(s) en stock ; le don vaut maintenant "
                                      f"{don.montant:,.0f} F.".replace(',', ' '))
            return redirect('comptabilite:dons')
    return render(request, 'comptabilite/don_stock.html', {
        'don': don, 'produits': produits, 'lignes': don.lignes.select_related('produit'),
    })
