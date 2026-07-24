from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
import json
import locale

from .models import (
    Fournisseur, BesoinAchat, LigneBesoin,
    Proforma, LigneProforma,
    CommandeAchat, LigneCommandeAchat,
    ReceptionAchat, LigneReceptionAchat,
)
from stock.models import Produit

MOIS_FR = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc']

ACHATS_MANAGE_GROUPS = {'Comptable', 'Directeur', 'Administrateur'}


def can_manage_achats(user):
    return user.is_superuser or user.groups.filter(name__in=ACHATS_MANAGE_GROUPS).exists()


# Transitions de statut valides — un POST direct ne peut pas sauter d'étape
# ni faire "reculer" un besoin/une commande (ex: brouillon -> reçue sans réception).
BESOIN_TRANSITIONS = {
    'brouillon': {'soumis', 'annule'},
    'soumis':    {'en_cours', 'annule'},
    'en_cours':  {'satisfait', 'annule'},
    'satisfait': set(),
    'annule':    set(),
}
COMMANDE_TRANSITIONS = {
    'brouillon':    {'envoyee', 'annulee'},
    'envoyee':      {'en_livraison', 'annulee'},
    'en_livraison': {'annulee'},   # -> 'recue' passe exclusivement par reception_create
    'recue':        set(),
    'annulee':      set(),
}


# ──────────────────────────────────────────────────────────────
# TABLEAU DE BORD
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def achats_dashboard(request):
    today = timezone.now().date()

    # Commandes actives avec flag retard
    commandes_actives_qs = (
        CommandeAchat.objects
        .exclude(statut__in=['recue', 'annulee'])
        .select_related('fournisseur')
        .order_by('date_livraison_prevue')
    )
    commandes_actives = []
    nb_retard = 0
    for c in commandes_actives_qs:
        c.est_en_retard = (
            c.date_livraison_prevue and
            c.date_livraison_prevue < today and
            c.statut not in ('recue', 'annulee')
        )
        if c.est_en_retard:
            nb_retard += 1
        commandes_actives.append(c)

    stats = {
        'fournisseurs':       Fournisseur.objects.filter(actif=True).count(),
        'besoins_ouverts':    BesoinAchat.objects.exclude(statut__in=['satisfait', 'annule']).count(),
        'proformas_attente':  Proforma.objects.filter(statut='en_attente').count(),
        'commandes_en_cours': CommandeAchat.objects.exclude(statut__in=['recue', 'annulee']).count(),
        'receptions_recentes': ReceptionAchat.objects.filter(
            date_reception__gte=today - timezone.timedelta(days=30)
        ).count(),
        'livraisons_en_retard': nb_retard,
    }

    # Graphique : dépenses mensuelles sur 6 mois
    depuis = today.replace(day=1)
    for _ in range(5):
        if depuis.month == 1:
            depuis = depuis.replace(year=depuis.year - 1, month=12)
        else:
            depuis = depuis.replace(month=depuis.month - 1)

    monthly = (
        CommandeAchat.objects
        .filter(date_commande__gte=depuis)
        .annotate(mois=TruncMonth('date_commande'))
        .values('mois')
        .annotate(total=Sum('montant_total'))
        .order_by('mois')
    )
    monthly_map = {r['mois'].strftime('%Y-%m'): float(r['total'] or 0) for r in monthly}

    chart_labels, chart_data = [], []
    cur = depuis
    for _ in range(6):
        key = cur.strftime('%Y-%m')
        chart_labels.append(MOIS_FR[cur.month - 1])
        chart_data.append(monthly_map.get(key, 0))
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)

    # Flux workflow
    workflow_steps = [
        {'label': 'Besoins en brouillon',   'count': BesoinAchat.objects.filter(statut='brouillon').count(),  'color': '#6b7280', 'url': '/achats/besoins/?statut=brouillon'},
        {'label': 'Besoins soumis',          'count': BesoinAchat.objects.filter(statut='soumis').count(),     'color': '#1d4ed8', 'url': '/achats/besoins/?statut=soumis'},
        {'label': 'Proformas en attente',    'count': Proforma.objects.filter(statut='en_attente').count(),    'color': '#92400e', 'url': '/achats/proformas/?statut=en_attente'},
        {'label': 'Commandes envoyées',      'count': CommandeAchat.objects.filter(statut='envoyee').count(),  'color': '#1d4ed8', 'url': '/achats/commandes/?statut=envoyee'},
        {'label': 'En cours de livraison',   'count': CommandeAchat.objects.filter(statut='en_livraison').count(), 'color': '#b45309', 'url': '/achats/commandes/?statut=en_livraison'},
        {'label': 'Reçues ce mois',          'count': ReceptionAchat.objects.filter(date_reception__month=today.month, date_reception__year=today.year).count(), 'color': '#065f46', 'url': '/achats/commandes/?statut=recue'},
    ]

    from stock.models import FicheBesoins
    nb_fiches_stock = FicheBesoins.objects.filter(
        statut__in=('soumis', 'valide'), besoins_achats__isnull=True
    ).count()

    # ── Alertes opérationnelles ──
    seuil_stagnation = today - timezone.timedelta(days=7)
    proformas_stagnantes = Proforma.objects.filter(
        statut='en_attente', date_creation__date__lt=seuil_stagnation
    ).select_related('fournisseur', 'besoin').order_by('date_creation')
    besoins_sans_proforma = BesoinAchat.objects.filter(
        statut='soumis', date_creation__date__lt=seuil_stagnation
    ).order_by('date_creation')
    receptions_non_integrees = ReceptionAchat.objects.filter(
        integre_en_stock=False
    ).select_related('commande__fournisseur').order_by('date_reception')

    alertes = {
        'proformas_stagnantes':     proformas_stagnantes[:5],
        'nb_proformas_stagnantes':  proformas_stagnantes.count(),
        'besoins_sans_proforma':    besoins_sans_proforma[:5],
        'nb_besoins_sans_proforma': besoins_sans_proforma.count(),
        'receptions_non_integrees':    receptions_non_integrees[:5],
        'nb_receptions_non_integrees': receptions_non_integrees.count(),
    }

    # ── Top fournisseurs (commandes non annulées, montant + taux de retard) ──
    fournisseurs_stats = []
    for f in Fournisseur.objects.filter(actif=True):
        commandes_f = list(
            CommandeAchat.objects.filter(fournisseur=f)
            .exclude(statut='annulee')
            .prefetch_related('receptions')
        )
        if not commandes_f:
            continue
        montant = sum(float(c.montant_total) for c in commandes_f)
        nb_retard = 0
        for c in commandes_f:
            if c.statut == 'recue':
                premiere = min((r.date_reception for r in c.receptions.all()), default=None)
                if premiere and c.date_livraison_prevue and premiere > c.date_livraison_prevue:
                    nb_retard += 1
            elif c.date_livraison_prevue and c.date_livraison_prevue < today:
                nb_retard += 1
        fournisseurs_stats.append({
            'fournisseur':   f,
            'nb_commandes':  len(commandes_f),
            'montant_total': montant,
            'nb_retard':     nb_retard,
            'taux_retard':   round(nb_retard / len(commandes_f) * 100, 1),
        })
    fournisseurs_stats.sort(key=lambda x: -x['montant_total'])
    top_fournisseurs = fournisseurs_stats[:5]

    # ── Répartition des dépenses par catégorie de produit (année en cours) ──
    lignes_annee = LigneCommandeAchat.objects.filter(
        commande__date_commande__year=today.year
    ).exclude(commande__statut='annulee').select_related(
        'ligne_proforma__ligne_besoin__produit', 'commande'
    )
    repartition_montants = {}
    for l in lignes_annee:
        produit = None
        if (l.ligne_proforma and l.ligne_proforma.ligne_besoin and l.ligne_proforma.ligne_besoin.produit):
            produit = l.ligne_proforma.ligne_besoin.produit
        label = produit.get_type_display() if produit else 'Hors catalogue'
        repartition_montants[label] = repartition_montants.get(label, 0) + float(l.montant)
    total_repartition = sum(repartition_montants.values()) or 1
    repartition_categories = sorted([
        {'label': label, 'montant': montant, 'pct': round(montant / total_repartition * 100, 1)}
        for label, montant in repartition_montants.items()
    ], key=lambda x: -x['montant'])

    # ── Évolution année sur année ──
    total_annee = CommandeAchat.objects.filter(
        date_commande__year=today.year
    ).exclude(statut='annulee').aggregate(t=Sum('montant_total'))['t'] or 0
    total_annee_prec = CommandeAchat.objects.filter(
        date_commande__year=today.year - 1
    ).exclude(statut='annulee').aggregate(t=Sum('montant_total'))['t'] or 0
    if total_annee_prec:
        evolution_pct = round((float(total_annee) - float(total_annee_prec)) / float(total_annee_prec) * 100, 1)
    else:
        evolution_pct = None

    return render(request, 'achats/dashboard.html', {
        'stats': stats,
        'nb_fiches_stock':    nb_fiches_stock,
        'besoins_recents':    BesoinAchat.objects.select_related('cree_par').order_by('-date_creation')[:6],
        'proformas_attente':  Proforma.objects.filter(statut='en_attente').select_related('fournisseur', 'besoin').order_by('-date_creation')[:6],
        'commandes_actives':  commandes_actives[:8],
        'chart_labels':       json.dumps(chart_labels),
        'chart_data':         json.dumps(chart_data),
        'workflow_steps':     workflow_steps,
        'alertes':            alertes,
        'top_fournisseurs':   top_fournisseurs,
        'repartition_categories': repartition_categories,
        'annee_courante':     today.year,
        'annee_precedente':   today.year - 1,
        'total_annee':        total_annee,
        'total_annee_prec':   total_annee_prec,
        'evolution_pct':      evolution_pct,
    })


# ──────────────────────────────────────────────────────────────
# FOURNISSEURS
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def fournisseurs_list(request):
    qs = Fournisseur.objects.all()
    q = request.GET.get('q', '').strip()
    filtre = request.GET.get('filtre', '')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q) | Q(telephone__icontains=q) | Q(ville__icontains=q))
    if filtre == 'actif':
        qs = qs.filter(actif=True)
    elif filtre == 'inactif':
        qs = qs.filter(actif=False)
    return render(request, 'achats/fournisseurs/list.html', {
        'fournisseurs': qs,
        'q': q,
        'filtre': filtre,
        'total': qs.count(),
        'total_actifs': Fournisseur.objects.filter(actif=True).count(),
    })


@login_required(login_url='login')
def fournisseur_detail(request, pk):
    f = get_object_or_404(Fournisseur, pk=pk)
    proformas = f.proformas.select_related('besoin').order_by('-date_creation')[:10]
    commandes = f.commandes_achats.order_by('-date_creation')[:10]
    return render(request, 'achats/fournisseurs/detail.html', {
        'fournisseur': f,
        'proformas': proformas,
        'commandes': commandes,
    })


@login_required(login_url='login')
def fournisseur_create(request):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        f = Fournisseur()
        _save_fournisseur(f, request.POST)
        messages.success(request, f'Fournisseur « {f.nom} » créé (code : {f.code}).')
        return redirect('achats:fournisseur_detail', pk=f.pk)
    return render(request, 'achats/fournisseurs/form.html', {'action': 'create'})


@login_required(login_url='login')
def fournisseur_edit(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    f = get_object_or_404(Fournisseur, pk=pk)
    if request.method == 'POST':
        _save_fournisseur(f, request.POST)
        messages.success(request, 'Fournisseur mis à jour.')
        return redirect('achats:fournisseur_detail', pk=f.pk)
    return render(request, 'achats/fournisseurs/form.html', {'action': 'edit', 'fournisseur': f})


def _save_fournisseur(obj, data):
    obj.nom = data.get('nom', '').strip()
    obj.telephone = data.get('telephone', '').strip()
    obj.telephone2 = data.get('telephone2', '').strip()
    obj.email = data.get('email', '').strip()
    obj.adresse = data.get('adresse', '').strip()
    obj.ville = data.get('ville', '').strip()
    obj.pays = data.get('pays', "Côte d'Ivoire").strip()
    obj.contact_nom = data.get('contact_nom', '').strip()
    obj.contact_telephone = data.get('contact_telephone', '').strip()
    obj.contact_email = data.get('contact_email', '').strip()
    obj.specialites = data.get('specialites', '').strip()
    obj.conditions_paiement = data.get('conditions_paiement', '').strip()
    delai = data.get('delai_livraison_moyen', '').strip()
    obj.delai_livraison_moyen = int(delai) if delai.isdigit() else None
    obj.actif = data.get('actif') == 'on'
    obj.notes = data.get('notes', '').strip()
    obj.save()


# ──────────────────────────────────────────────────────────────
# BESOINS D'ACHAT
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def besoins_list(request):
    from stock.models import FicheBesoins
    qs = BesoinAchat.objects.select_related('cree_par', 'fiche_besoins').prefetch_related('lignes')
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(titre__icontains=q))
    if statut:
        qs = qs.filter(statut=statut)

    fiches_a_importer = FicheBesoins.objects.filter(
        statut__in=('soumis', 'valide'),
        besoins_achats__isnull=True,
    ).order_by('-date_creation')

    return render(request, 'achats/besoins/list.html', {
        'besoins': qs,
        'q': q,
        'statut': statut,
        'statut_choices': BesoinAchat.STATUT_CHOICES,
        'fiches_a_importer': fiches_a_importer,
        'stats': {
            'total': BesoinAchat.objects.count(),
            'soumis': BesoinAchat.objects.filter(statut='soumis').count(),
            'en_cours': BesoinAchat.objects.filter(statut='en_cours').count(),
            'satisfait': BesoinAchat.objects.filter(statut='satisfait').count(),
        },
    })


@login_required(login_url='login')
def besoin_detail(request, pk):
    besoin = get_object_or_404(BesoinAchat, pk=pk)
    lignes = besoin.lignes.select_related('produit').all()
    proformas = besoin.proformas.select_related('fournisseur').all()
    return render(request, 'achats/besoins/detail.html', {
        'besoin': besoin,
        'lignes': lignes,
        'proformas': proformas,
        'fournisseurs': Fournisseur.objects.filter(actif=True),
    })


@login_required(login_url='login')
def besoin_create(request):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        with transaction.atomic():
            besoin = BesoinAchat(cree_par=request.user)
            _save_besoin(besoin, request.POST)
            _save_lignes_besoin(besoin, request.POST)
        messages.success(request, f'Besoin d\'achat {besoin.numero} créé.')
        return redirect('achats:besoin_detail', pk=besoin.pk)
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    return render(request, 'achats/besoins/form.html', {
        'action': 'create',
        'produits': produits,
    })


@login_required(login_url='login')
def besoin_edit(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    besoin = get_object_or_404(BesoinAchat, pk=pk)
    if besoin.statut not in ('brouillon', 'soumis'):
        messages.error(request, 'Ce besoin ne peut plus être modifié.')
        return redirect('achats:besoin_detail', pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            _save_besoin(besoin, request.POST)
            besoin.lignes.all().delete()
            _save_lignes_besoin(besoin, request.POST)
        messages.success(request, 'Besoin mis à jour.')
        return redirect('achats:besoin_detail', pk=besoin.pk)
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    return render(request, 'achats/besoins/form.html', {
        'action': 'edit',
        'besoin': besoin,
        'lignes': besoin.lignes.select_related('produit').all(),
        'produits': produits,
    })


@login_required(login_url='login')
@require_POST
def besoin_changer_statut(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    besoin = get_object_or_404(BesoinAchat, pk=pk)
    nouveau = request.POST.get('statut')
    if nouveau in BESOIN_TRANSITIONS.get(besoin.statut, set()):
        besoin.statut = nouveau
        besoin.save(update_fields=['statut'])
        messages.success(request, f'Statut mis à jour : {besoin.get_statut_display()}.')
    else:
        messages.error(request, f'Transition de statut invalide ({besoin.get_statut_display()} → {dict(BesoinAchat.STATUT_CHOICES).get(nouveau, nouveau)}).')
    return redirect('achats:besoin_detail', pk=pk)


def _save_besoin(obj, data):
    obj.titre = data.get('titre', '').strip()
    date_str = data.get('date_besoin_souhaite', '').strip()
    obj.date_besoin_souhaite = date_str if date_str else None
    obj.notes = data.get('notes', '').strip()
    obj.save()


def _save_lignes_besoin(besoin, data):
    produit_ids = data.getlist('produit_id')
    designations = data.getlist('designation')
    quantites = data.getlist('quantite')
    unites = data.getlist('unite')
    notes_list = data.getlist('ligne_notes')
    for i, qte in enumerate(quantites):
        if not qte:
            continue
        try:
            q = float(qte.replace(',', '.'))
        except ValueError:
            continue
        if q <= 0:
            continue
        pid = produit_ids[i] if i < len(produit_ids) else ''
        LigneBesoin.objects.create(
            besoin=besoin,
            produit_id=int(pid) if pid else None,
            designation=designations[i] if i < len(designations) else '',
            quantite=q,
            unite=unites[i] if i < len(unites) else 'unité',
            notes=notes_list[i] if i < len(notes_list) else '',
        )


# ──────────────────────────────────────────────────────────────
# PROFORMAS
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def proformas_list(request):
    qs = Proforma.objects.select_related('fournisseur', 'besoin', 'soumis_par')
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(fournisseur__nom__icontains=q) | Q(besoin__titre__icontains=q))
    if statut:
        qs = qs.filter(statut=statut)
    return render(request, 'achats/proformas/list.html', {
        'proformas': qs,
        'q': q,
        'statut': statut,
        'statut_choices': Proforma.STATUT_CHOICES,
        'stats': {
            'total': Proforma.objects.count(),
            'en_attente': Proforma.objects.filter(statut='en_attente').count(),
            'valide': Proforma.objects.filter(statut='valide').count(),
            'rejete': Proforma.objects.filter(statut='rejete').count(),
        },
    })


@login_required(login_url='login')
def proforma_detail(request, pk):
    proforma = get_object_or_404(Proforma, pk=pk)
    lignes = proforma.lignes.select_related('ligne_besoin').all()
    has_commande = hasattr(proforma, 'commande')
    return render(request, 'achats/proformas/detail.html', {
        'proforma': proforma,
        'lignes': lignes,
        'has_commande': has_commande,
        'montant_calc': sum(l.montant for l in lignes),
    })


@login_required(login_url='login')
def proforma_create(request, besoin_pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    besoin = get_object_or_404(BesoinAchat, pk=besoin_pk)
    if besoin.statut in ('satisfait', 'annule'):
        messages.error(request, 'Ce besoin est clos, il ne peut plus recevoir de nouveau proforma.')
        return redirect('achats:besoin_detail', pk=besoin_pk)
    if request.method == 'POST':
        with transaction.atomic():
            pf = Proforma(besoin=besoin, soumis_par=request.user)
            _save_proforma(pf, request.POST, request.FILES)
            _save_lignes_proforma(pf, request.POST, besoin)
            _recalc_proforma_total(pf)
        messages.success(request, f'Proforma {pf.numero} ajouté.')
        return redirect('achats:proforma_detail', pk=pf.pk)
    return render(request, 'achats/proformas/form.html', {
        'action': 'create',
        'besoin': besoin,
        'fournisseurs': Fournisseur.objects.filter(actif=True),
        'lignes_besoin': besoin.lignes.select_related('produit').all(),
    })


@login_required(login_url='login')
def proforma_edit(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    pf = get_object_or_404(Proforma, pk=pk)
    if pf.statut != 'en_attente':
        messages.error(request, 'Ce proforma ne peut plus être modifié.')
        return redirect('achats:proforma_detail', pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            _save_proforma(pf, request.POST, request.FILES)
            pf.lignes.all().delete()
            _save_lignes_proforma(pf, request.POST, pf.besoin)
            _recalc_proforma_total(pf)
        messages.success(request, 'Proforma mis à jour.')
        return redirect('achats:proforma_detail', pk=pk)
    return render(request, 'achats/proformas/form.html', {
        'action': 'edit',
        'proforma': pf,
        'besoin': pf.besoin,
        'fournisseurs': Fournisseur.objects.filter(actif=True),
        'lignes_besoin': pf.besoin.lignes.select_related('produit').all(),
        'lignes': pf.lignes.all(),
    })


@login_required(login_url='login')
@require_POST
def proforma_valider(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    pf = get_object_or_404(Proforma, pk=pk)
    if pf.statut != 'en_attente':
        messages.error(request, 'Ce proforma n\'est pas en attente de validation.')
        return redirect('achats:proforma_detail', pk=pk)
    autre_valide = pf.besoin.proformas.filter(statut='valide').exclude(pk=pf.pk).first()
    if autre_valide:
        messages.error(
            request,
            f'Ce besoin a déjà un proforma validé ({autre_valide.numero} — {autre_valide.fournisseur.nom}). '
            f'Rejetez-le d\'abord si vous voulez en valider un autre.'
        )
        return redirect('achats:proforma_detail', pk=pk)
    with transaction.atomic():
        pf.statut = 'valide'
        pf.valide_par = request.user
        pf.date_validation = timezone.now()
        pf.notes_direction = request.POST.get('notes_direction', '').strip()
        pf.save()
        pf.besoin.statut = 'en_cours'
        pf.besoin.save(update_fields=['statut'])
    messages.success(request, f'Proforma {pf.numero} validé.')
    return redirect('achats:proforma_detail', pk=pk)


@login_required(login_url='login')
@require_POST
def proforma_rejeter(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    pf = get_object_or_404(Proforma, pk=pk)
    pf.statut = 'rejete'
    pf.valide_par = request.user
    pf.date_validation = timezone.now()
    pf.notes_direction = request.POST.get('notes_direction', '').strip()
    pf.save()
    messages.warning(request, f'Proforma {pf.numero} rejeté.')
    return redirect('achats:proforma_detail', pk=pk)


def _save_proforma(obj, data, files=None):
    obj.fournisseur_id = data.get('fournisseur_id')
    obj.date_reception = data.get('date_reception')
    obj.reference_fournisseur = data.get('reference_fournisseur', '').strip()
    obj.notes = data.get('notes', '').strip()
    if files and files.get('fichier'):
        obj.fichier = files['fichier']
    obj.save()


def _save_lignes_proforma(proforma, data, besoin):
    designations = data.getlist('designation')
    quantites = data.getlist('quantite')
    prix = data.getlist('prix_unitaire')
    lb_ids = data.getlist('ligne_besoin_id')
    notes_list = data.getlist('ligne_notes')
    ids_valides = set(besoin.lignes.values_list('pk', flat=True))
    for i, qte in enumerate(quantites):
        if not qte:
            continue
        try:
            q = float(qte.replace(',', '.'))
            pu = float(prix[i].replace(',', '.') if i < len(prix) else '0')
        except ValueError:
            continue
        if q <= 0:
            continue
        if pu < 0:
            pu = 0
        lb_id = lb_ids[i] if i < len(lb_ids) else ''
        # N'accepte le rattachement à une ligne de besoin que si elle appartient
        # bien à CE besoin — évite de croiser la traçabilité avec un autre besoin.
        try:
            lb_id_int = int(lb_id) if lb_id and int(lb_id) in ids_valides else None
        except ValueError:
            lb_id_int = None
        LigneProforma.objects.create(
            proforma=proforma,
            ligne_besoin_id=lb_id_int,
            designation=designations[i] if i < len(designations) else '',
            quantite=q,
            prix_unitaire=pu,
            notes=notes_list[i] if i < len(notes_list) else '',
        )


def _recalc_proforma_total(pf):
    total = sum(l.montant for l in pf.lignes.all())
    pf.montant_total = total
    pf.save(update_fields=['montant_total'])


# ──────────────────────────────────────────────────────────────
# COMMANDES D'ACHAT
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def commandes_list(request):
    today = timezone.now().date()
    qs = CommandeAchat.objects.select_related('fournisseur', 'proforma').order_by('-date_commande')
    q = request.GET.get('q', '').strip()
    statut = request.GET.get('statut', '')
    retard = request.GET.get('retard', '')
    if q:
        qs = qs.filter(Q(numero__icontains=q) | Q(fournisseur__nom__icontains=q))
    if statut == 'en_cours':
        qs = qs.exclude(statut__in=['recue', 'annulee'])
    elif statut:
        qs = qs.filter(statut=statut)
    if retard:
        qs = qs.filter(
            date_livraison_prevue__lt=today
        ).exclude(statut__in=['recue', 'annulee'])

    commandes = []
    for c in qs:
        c.est_en_retard = (
            c.date_livraison_prevue and
            c.date_livraison_prevue < today and
            c.statut not in ('recue', 'annulee')
        )
        commandes.append(c)

    # Toujours global (indépendant du filtre actif), comme les autres compteurs du bandeau —
    # .count() plutôt que de matérialiser les objets juste pour les compter.
    nb_retard = CommandeAchat.objects.filter(
        date_livraison_prevue__lt=today
    ).exclude(statut__in=['recue', 'annulee']).count()

    return render(request, 'achats/commandes/list.html', {
        'commandes': commandes,
        'q': q,
        'statut': statut,
        'statut_choices': CommandeAchat.STATUT_CHOICES,
        'stats': {
            'total':       CommandeAchat.objects.count(),
            'brouillon':   CommandeAchat.objects.filter(statut='brouillon').count(),
            'envoyee':     CommandeAchat.objects.filter(statut='envoyee').count(),
            'en_livraison':CommandeAchat.objects.filter(statut='en_livraison').count(),
            'recue':       CommandeAchat.objects.filter(statut='recue').count(),
            'retard':      nb_retard,
        },
    })


@login_required(login_url='login')
def commande_create(request, proforma_pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    proforma = get_object_or_404(Proforma, pk=proforma_pk, statut='valide')
    if hasattr(proforma, 'commande'):
        messages.warning(request, 'Une commande existe déjà pour ce proforma.')
        return redirect('achats:commande_detail', pk=proforma.commande.pk)
    if request.method == 'POST':
        with transaction.atomic():
            cmd = CommandeAchat(
                proforma=proforma,
                fournisseur=proforma.fournisseur,
                cree_par=request.user,
                montant_total=proforma.montant_total,
            )
            cmd.date_commande = request.POST.get('date_commande') or timezone.now().date()
            date_liv = request.POST.get('date_livraison_prevue', '').strip()
            cmd.date_livraison_prevue = date_liv if date_liv else None
            cmd.notes = request.POST.get('notes', '').strip()
            cmd.save()
            LigneCommandeAchat.objects.bulk_create([
                LigneCommandeAchat(
                    commande=cmd,
                    ligne_proforma=lp,
                    designation=lp.designation,
                    quantite_commandee=lp.quantite,
                    prix_unitaire=lp.prix_unitaire,
                )
                for lp in proforma.lignes.all()
            ])
        messages.success(request, f'Commande {cmd.numero} créée.')
        return redirect('achats:commande_detail', pk=cmd.pk)
    return render(request, 'achats/commandes/form.html', {
        'action': 'create',
        'proforma': proforma,
    })


@login_required(login_url='login')
def commande_edit(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    cmd = get_object_or_404(CommandeAchat, pk=pk)
    if cmd.statut != 'brouillon':
        messages.error(request, 'Seule une commande en brouillon peut être modifiée.')
        return redirect('achats:commande_detail', pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            cmd.date_commande = request.POST.get('date_commande') or cmd.date_commande
            date_liv = request.POST.get('date_livraison_prevue', '').strip()
            cmd.date_livraison_prevue = date_liv if date_liv else None
            cmd.notes = request.POST.get('notes', '').strip()
            cmd.save()

            cmd.lignes.all().delete()
            designations = request.POST.getlist('designation')
            quantites = request.POST.getlist('quantite')
            prix = request.POST.getlist('prix_unitaire')
            nouvelles_lignes = []
            for i, qte in enumerate(quantites):
                if not qte:
                    continue
                try:
                    q = float(qte.replace(',', '.'))
                    pu = float(prix[i].replace(',', '.') if i < len(prix) else '0')
                except ValueError:
                    continue
                if q <= 0:
                    continue
                if pu < 0:
                    pu = 0
                nouvelles_lignes.append(LigneCommandeAchat(
                    commande=cmd,
                    designation=designations[i] if i < len(designations) else '',
                    quantite_commandee=q,
                    prix_unitaire=pu,
                ))
            LigneCommandeAchat.objects.bulk_create(nouvelles_lignes)
            cmd.montant_total = sum(l.montant for l in nouvelles_lignes)
            cmd.save(update_fields=['montant_total'])
        messages.success(request, f'Commande {cmd.numero} mise à jour.')
        return redirect('achats:commande_detail', pk=cmd.pk)
    return render(request, 'achats/commandes/form.html', {
        'action': 'edit',
        'commande': cmd,
        'proforma': cmd.proforma,
        'lignes': cmd.lignes.all(),
    })


@login_required(login_url='login')
def commande_detail(request, pk):
    from datetime import date
    cmd = get_object_or_404(CommandeAchat, pk=pk)
    lignes = cmd.lignes.all()
    receptions = cmd.receptions.select_related('receptionne_par').all()
    est_en_retard = (
        cmd.date_livraison_prevue is not None
        and cmd.statut not in ('recue', 'annulee')
        and cmd.date_livraison_prevue < date.today()
    )
    return render(request, 'achats/commandes/detail.html', {
        'commande': cmd,
        'lignes': lignes,
        'receptions': receptions,
        'montant_calc': sum(l.montant for l in lignes),
        'est_en_retard': est_en_retard,
    })


@login_required(login_url='login')
@require_POST
def commande_changer_statut(request, pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    cmd = get_object_or_404(CommandeAchat, pk=pk)
    nouveau = request.POST.get('statut')
    if nouveau in COMMANDE_TRANSITIONS.get(cmd.statut, set()):
        cmd.statut = nouveau
        cmd.save(update_fields=['statut'])
        messages.success(request, f'Statut mis à jour : {cmd.get_statut_display()}.')
    else:
        messages.error(request, f'Transition de statut invalide ({cmd.get_statut_display()} → {dict(CommandeAchat.STATUT_CHOICES).get(nouveau, nouveau)}).')
    return redirect('achats:commande_detail', pk=pk)


@login_required(login_url='login')
def commande_imprimer(request, pk):
    cmd = get_object_or_404(CommandeAchat, pk=pk)
    lignes = cmd.lignes.all()
    return render(request, 'achats/commandes/imprimer.html', {
        'commande': cmd,
        'lignes': lignes,
    })


# ──────────────────────────────────────────────────────────────
# RÉCEPTIONS
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def reception_create(request, commande_pk):
    if not can_manage_achats(request.user):
        raise PermissionDenied
    commande = get_object_or_404(CommandeAchat, pk=commande_pk)
    if commande.statut not in ('envoyee', 'en_livraison'):
        messages.error(request, 'Cette commande ne peut pas encore être réceptionnée.')
        return redirect('achats:commande_detail', pk=commande_pk)
    lignes = commande.lignes.all()
    if request.method == 'POST':
        # Quantités déjà reçues lors de réceptions précédentes de cette commande —
        # une réception partielle ne doit ni rouvrir le compteur à zéro ni clore
        # la commande/le besoin tant que tout n'est pas effectivement livré.
        deja_recu = {}
        for l in LigneReceptionAchat.objects.filter(ligne_commande__commande=commande):
            deja_recu[l.ligne_commande_id] = deja_recu.get(l.ligne_commande_id, 0.0) + float(l.quantite_recue)

        with transaction.atomic():
            rec = ReceptionAchat(
                commande=commande,
                receptionne_par=request.user,
            )
            date_str = request.POST.get('date_reception', '').strip()
            rec.date_reception = date_str if date_str else timezone.now().date()
            rec.notes = request.POST.get('notes', '').strip()
            rec.save()

            nouvelles_lignes = []
            for ligne in lignes:
                qte_str = request.POST.get(f'qte_{ligne.pk}', '0').replace(',', '.')
                try:
                    qte = float(qte_str)
                except ValueError:
                    qte = 0
                if qte < 0:
                    qte = 0
                conforme = request.POST.get(f'conforme_{ligne.pk}') == 'on'
                dp_str = request.POST.get(f'peremption_{ligne.pk}', '').strip()
                nouvelles_lignes.append(LigneReceptionAchat(
                    reception=rec,
                    ligne_commande=ligne,
                    quantite_recue=qte,
                    conforme=conforme,
                    numero_lot=request.POST.get(f'lot_{ligne.pk}', '').strip(),
                    date_peremption=dp_str if dp_str else None,
                    notes=request.POST.get(f'notes_{ligne.pk}', ''),
                ))
            LigneReceptionAchat.objects.bulk_create(nouvelles_lignes)

            # Solde après CETTE réception, cumulé avec les précédentes
            total_cmd = sum(l.quantite_commandee for l in lignes)
            total_recu_cumule = sum(
                deja_recu.get(l.ligne_commande_id, 0) + float(l.quantite_recue)
                for l in nouvelles_lignes
            )
            # Cette réception seule couvre-t-elle ce qu'il restait à livrer avant elle ?
            restant_avant = float(total_cmd) - sum(deja_recu.values())
            total_recu_cette_fois = sum(float(l.quantite_recue) for l in nouvelles_lignes)
            rec.statut = 'conforme' if total_recu_cette_fois >= restant_avant else 'partielle'
            rec.save(update_fields=['statut'])

            if total_recu_cumule >= float(total_cmd):
                commande.statut = 'recue'
                commande.save(update_fields=['statut'])
                commande.proforma.besoin.statut = 'satisfait'
                commande.proforma.besoin.save(update_fields=['statut'])
            else:
                commande.statut = 'en_livraison'
                commande.save(update_fields=['statut'])

        if commande.statut == 'recue':
            messages.success(request, f'Réception {rec.numero} enregistrée — commande entièrement livrée. Intégrez-la depuis le module Stock (Réceptions à intégrer) pour mettre à jour les quantités.')
        else:
            messages.warning(request, f'Réception {rec.numero} enregistrée — livraison partielle, reliquat en attente.')
        return redirect('achats:reception_detail', pk=rec.pk)
    return render(request, 'achats/receptions/form.html', {
        'commande': commande,
        'lignes': lignes,
    })


@login_required(login_url='login')
def reception_detail(request, pk):
    rec = get_object_or_404(ReceptionAchat, pk=pk)
    lignes = rec.lignes.select_related('ligne_commande').all()
    return render(request, 'achats/receptions/detail.html', {
        'reception': rec,
        'lignes': lignes,
    })


# ──────────────────────────────────────────────────────────────
# AJAX
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def api_produits(request):
    q = request.GET.get('q', '').strip()
    qs = Produit.objects.filter(actif=True).select_related('unite_mesure')
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    data = [{'id': p.pk, 'text': f'{p.nom} ({p.code})', 'unite': p.unite_mesure.nom if p.unite_mesure else ''} for p in qs[:30]]
    return JsonResponse({'results': data})
