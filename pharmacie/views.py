from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, F
from django.utils import timezone
from django.core.paginator import Paginator
import datetime

from .models import (
    StockPharmacie, MouvementPharmacie,
    DispensationOrdonnance, LigneDispensation, PHARMACIES_WALE,
    VentePharmacie, LigneVente,
    InventairePharmacie, LigneInventairePharmacie,
)
from stock.models import Produit, DemandePharmacie, LigneDemande

PHARMACIES_DICT = dict(PHARMACIES_WALE)


def get_pharmacie_or_404(pharmacie):
    if pharmacie not in PHARMACIES_DICT:
        from django.http import Http404
        raise Http404
    return pharmacie


@login_required(login_url='login')
def pharmacie_accueil(request):
    from consultations.models import Ordonnance
    attente = Ordonnance.objects.filter(statut='emise').count()
    pharmacies_data = []
    for code, label in PHARMACIES_WALE:
        ruptures = StockPharmacie.objects.filter(pharmacie=code, quantite__lte=0).count()
        alertes  = StockPharmacie.objects.filter(
            pharmacie=code, quantite__gt=0, quantite__lte=F('produit__stock_alerte')
        ).count()
        total = StockPharmacie.objects.filter(pharmacie=code).count()
        pharmacies_data.append({
            'code':     code,
            'label':    label,
            'total':    total,
            'ruptures': ruptures,
            'alertes':  alertes,
            'attente':  attente,
        })
    return render(request, 'pharmacie/accueil.html', {
        'pharmacies_data': pharmacies_data,
    })


@login_required(login_url='login')
def pharmacie_dashboard(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    stock_items = StockPharmacie.objects.filter(pharmacie=pharmacie).select_related('produit')

    ruptures = stock_items.filter(quantite__lte=0).count()
    alertes  = stock_items.filter(quantite__gt=0, quantite__lte=F('produit__stock_alerte')).count()

    stats = {
        'total_refs': stock_items.count(),
        'ruptures':   ruptures,
        'alertes':    alertes,
    }

    from consultations.models import Ordonnance
    ordonnances_attente = Ordonnance.objects.filter(
        statut='emise'
    ).select_related('consultation__patient', 'consultation__medecin').order_by('-date_emission')[:8]

    derniers_mvts = MouvementPharmacie.objects.filter(
        pharmacie=pharmacie
    ).select_related('produit').order_by('-date')[:8]

    stock_critique = stock_items.filter(
        quantite__lte=F('produit__stock_alerte')
    ).order_by('quantite')[:8]

    demandes_en_attente = DemandePharmacie.objects.filter(
        pharmacie=pharmacie, statut='en_attente'
    ).count()

    return render(request, 'pharmacie/dashboard.html', {
        'pharmacie':           pharmacie,
        'label':               label,
        'stats':               stats,
        'ordonnances_attente': ordonnances_attente,
        'derniers_mvts':       derniers_mvts,
        'stock_critique':      stock_critique,
        'demandes_en_attente': demandes_en_attente,
        'today':               today,
    })


@login_required(login_url='login')
def pharmacie_stock(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    qs          = StockPharmacie.objects.filter(pharmacie=pharmacie).select_related('produit', 'produit__categorie')
    q           = request.GET.get('q', '').strip()
    statut      = request.GET.get('statut', '')
    type_filtre = request.GET.get('type', '')

    if q:
        qs = qs.filter(Q(produit__nom__icontains=q) | Q(produit__code__icontains=q))
    if statut == 'rupture':
        qs = qs.filter(quantite__lte=0)
    elif statut == 'alerte':
        qs = qs.filter(quantite__gt=0, quantite__lte=F('produit__stock_alerte'))
    elif statut == 'ok':
        qs = qs.filter(quantite__gt=F('produit__stock_alerte'))
    if type_filtre:
        qs = qs.filter(produit__type=type_filtre)

    qs = qs.order_by('produit__type', 'produit__nom')
    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    stats = {
        'total':    StockPharmacie.objects.filter(pharmacie=pharmacie).count(),
        'ruptures': StockPharmacie.objects.filter(pharmacie=pharmacie, quantite__lte=0).count(),
        'alertes':  StockPharmacie.objects.filter(pharmacie=pharmacie, quantite__gt=0, quantite__lte=F('produit__stock_alerte')).count(),
    }

    return render(request, 'pharmacie/stock.html', {
        'pharmacie': pharmacie, 'label': label,
        'page_obj':  page_obj, 'stats': stats,
        'q': q, 'statut': statut, 'type_filtre': type_filtre,
    })


@login_required(login_url='login')
def pharmacie_ordonnances(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    from consultations.models import Ordonnance
    statut_filtre = request.GET.get('statut', 'emise')
    q             = request.GET.get('q', '').strip()

    qs = Ordonnance.objects.select_related(
        'consultation__patient', 'consultation__medecin'
    ).prefetch_related('lignes__medicament').order_by('-date_emission')

    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
    if q:
        qs = qs.filter(
            Q(consultation__patient__nom__icontains=q) |
            Q(consultation__patient__prenoms__icontains=q) |
            Q(numero__icontains=q)
        )

    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'pharmacie/ordonnances.html', {
        'pharmacie':     pharmacie, 'label': label,
        'page_obj':      page_obj,
        'statut_filtre': statut_filtre,
        'q':             q,
    })


@login_required(login_url='login')
def pharmacie_dispenser(request, pharmacie, pk):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    from consultations.models import Ordonnance
    ordonnance = get_object_or_404(Ordonnance, pk=pk)

    if hasattr(ordonnance, 'dispensation'):
        messages.info(request, 'Cette ordonnance a déjà été dispensée.')
        return redirect('pharmacie_ordonnances', pharmacie=pharmacie)

    lignes = ordonnance.lignes.select_related('medicament').all()

    lignes_enrichies = []
    for ligne in lignes:
        produit    = None
        stock_item = None
        nom_med    = ''
        if ligne.medicament:
            nom_med = ligne.medicament.designation
            produit = Produit.objects.filter(
                nom__icontains=nom_med[:20], type='medicament', actif=True
            ).first()
        elif ligne.medicament_libre:
            nom_med = ligne.medicament_libre
            produit = Produit.objects.filter(
                nom__icontains=nom_med[:20], type='medicament', actif=True
            ).first()

        if produit:
            stock_item = StockPharmacie.objects.filter(pharmacie=pharmacie, produit=produit).first()

        lignes_enrichies.append({
            'ligne':       ligne,
            'nom_med':     nom_med,
            'produit':     produit,
            'stock_item':  stock_item,
            'stock_dispo': float(stock_item.quantite) if stock_item else 0,
            'suffisant':   bool(stock_item and float(stock_item.quantite) >= ligne.quantite),
            'qte_defaut':  min(float(ligne.quantite), float(stock_item.quantite)) if stock_item else 0,
        })

    nb_complets     = sum(1 for l in lignes_enrichies if l['suffisant'])
    nb_partiels     = sum(1 for l in lignes_enrichies if not l['suffisant'] and l['produit'] and l['stock_dispo'] > 0)
    nb_rupture      = sum(1 for l in lignes_enrichies if l['produit'] and l['stock_dispo'] == 0)
    nb_non_trouves  = sum(1 for l in lignes_enrichies if not l['produit'])
    total_lignes    = len(lignes_enrichies)

    for item in lignes_enrichies:
        item['substituts'] = []
        if not item['suffisant'] and item['produit'] and item['produit'].dci:
            subs = StockPharmacie.objects.filter(
                pharmacie=pharmacie, quantite__gt=0,
                produit__dci__iexact=item['produit'].dci,
            ).exclude(produit=item['produit']).select_related('produit')[:3]
            item['substituts'] = list(subs)

    try:
        patient_obj = ordonnance.consultation.patient
    except Exception:
        patient_obj = None
    historique_patient = []
    if patient_obj:
        historique_patient = list(
            DispensationOrdonnance.objects.filter(
                pharmacie=pharmacie,
                ordonnance__consultation__patient=patient_obj,
            ).exclude(ordonnance=ordonnance).select_related(
                'ordonnance'
            ).prefetch_related('lignes__produit').order_by('-date')[:5]
        )

    if request.method == 'POST':
        dispensation = DispensationOrdonnance.objects.create(
            pharmacie=pharmacie, ordonnance=ordonnance,
            notes=request.POST.get('notes', '').strip(),
            dispense_par=request.user,
        )
        statut_global = 'complete'
        for item in lignes_enrichies:
            ligne = item['ligne']
            try:
                qte = int(request.POST.get(f'qte_{ligne.pk}', 0) or 0)
            except ValueError:
                qte = 0
            qte = max(0, min(qte, ligne.quantite))
            if qte < ligne.quantite:
                statut_global = 'partielle'

            LigneDispensation.objects.create(
                dispensation=dispensation,
                produit=item['produit'],
                medicament_libre=item['nom_med'],
                quantite_prescrite=ligne.quantite,
                quantite_dispensee=qte,
            )
            if item['stock_item'] and qte > 0:
                sp    = item['stock_item']
                avant = float(sp.quantite)
                apres = max(0, avant - qte)
                MouvementPharmacie.objects.create(
                    pharmacie=pharmacie, produit=sp.produit,
                    type='dispensation', quantite=qte,
                    stock_avant=avant, stock_apres=apres,
                    reference=ordonnance.numero,
                    cree_par=request.user,
                )
                sp.quantite = apres
                sp.save(update_fields=['quantite'])

        dispensation.statut = statut_global
        dispensation.save(update_fields=['statut'])
        ordonnance.statut = 'delivree' if statut_global == 'complete' else 'partielle'
        ordonnance.save(update_fields=['statut'])

        messages.success(request, f'Ordonnance {ordonnance.numero} dispensée ({statut_global}).')
        return redirect('pharmacie_ordonnances', pharmacie=pharmacie)

    return render(request, 'pharmacie/dispenser.html', {
        'pharmacie':        pharmacie, 'label': label,
        'ordonnance':       ordonnance,
        'lignes_enrichies': lignes_enrichies,
        'nb_complets':    nb_complets,
        'nb_partiels':    nb_partiels,
        'nb_rupture':     nb_rupture,
        'nb_non_trouves': nb_non_trouves,
        'total_lignes':   total_lignes,
        'historique_patient': historique_patient,
    })


@login_required(login_url='login')
def pharmacie_demande(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label    = PHARMACIES_DICT[pharmacie]
    from .models import StockPharmacie
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    # Récupérer le stock de cette pharmacie pour chaque produit
    stock_pharmacie = {sp.produit_id: sp for sp in StockPharmacie.objects.filter(pharmacie=pharmacie)}
    produits_data = []
    for p in produits:
        sp = stock_pharmacie.get(p.pk)
        produits_data.append({
            'produit': p,
            'stock_pharmacie': float(sp.quantite) if sp else 0,
            'en_rupture': (sp.quantite <= 0) if sp else True,
            'en_alerte': (sp and 0 < sp.quantite <= p.stock_alerte),
        })
    errors   = {}

    if request.method == 'POST':
        notes   = request.POST.get('notes', '').strip()
        demande = DemandePharmacie.objects.create(
            pharmacie=pharmacie, notes=notes, cree_par=request.user,
        )
        nb = 0
        for p in produits:
            val = request.POST.get(f'qte_{p.pk}', '').strip()
            if val:
                try:
                    qte = float(val)
                    if qte > 0:
                        LigneDemande.objects.create(demande=demande, produit=p, quantite_demandee=qte)
                        nb += 1
                except ValueError:
                    pass
        if nb > 0:
            messages.success(request, f'Demande {demande.numero} envoyée au stock central ({nb} produit{"s" if nb > 1 else ""}).')
            return redirect('pharmacie_dashboard', pharmacie=pharmacie)
        demande.delete()
        errors['lignes'] = 'Ajoutez au moins un produit avec une quantité.'

    return render(request, 'pharmacie/demande.html', {
        'pharmacie': pharmacie, 'label': label,
        'produits': produits_data, 'errors': errors,
    })


@login_required(login_url='login')
def pharmacie_journal(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    qs    = MouvementPharmacie.objects.filter(pharmacie=pharmacie).select_related('produit').order_by('-date')
    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'pharmacie/journal.html', {
        'pharmacie': pharmacie, 'label': label, 'page_obj': page_obj,
    })


@login_required(login_url='login')
def pharmacie_livraisons(request, pharmacie):
    """Liste des livraisons en attente de confirmation par la pharmacie."""
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    en_attente  = DemandePharmacie.objects.filter(pharmacie=pharmacie, statut='en_livraison').order_by('-date_traitement')
    historique  = DemandePharmacie.objects.filter(pharmacie=pharmacie, statut__in=['approuvee', 'partielle']).order_by('-date_traitement')[:10]

    return render(request, 'pharmacie/livraisons.html', {
        'pharmacie':    pharmacie,
        'label':        label,
        'en_attente':   en_attente,
        'historique':   historique,
    })


@login_required(login_url='login')
def pharmacie_confirmer_livraison(request, pharmacie, pk):
    """La pharmacie confirme la réception d'une livraison → met à jour son stock."""
    from django.views.decorators.http import require_POST as _rp
    get_pharmacie_or_404(pharmacie)
    label   = PHARMACIES_DICT[pharmacie]
    demande = get_object_or_404(DemandePharmacie, pk=pk, pharmacie=pharmacie)

    if demande.statut != 'en_livraison':
        messages.info(request, 'Cette livraison a déjà été traitée.')
        return redirect('pharmacie_livraisons', pharmacie=pharmacie)

    lignes = demande.lignes.select_related('produit').all()

    if request.method == 'POST':
        tout_recu = True
        for ligne in lignes:
            if not ligne.produit or ligne.quantite_approuvee <= 0:
                continue
            try:
                qte_recue = float(request.POST.get(f'recu_{ligne.pk}', ligne.quantite_approuvee) or ligne.quantite_approuvee)
            except ValueError:
                qte_recue = float(ligne.quantite_approuvee)
            qte_recue = max(0, min(qte_recue, float(ligne.quantite_approuvee)))

            if qte_recue < float(ligne.quantite_approuvee):
                tout_recu = False

            if qte_recue > 0:
                # Mettre à jour ou créer le StockPharmacie
                sp, _ = StockPharmacie.objects.get_or_create(
                    pharmacie=pharmacie, produit=ligne.produit,
                    defaults={'quantite': 0}
                )
                avant = float(sp.quantite)
                apres = avant + qte_recue
                MouvementPharmacie.objects.create(
                    pharmacie=pharmacie, produit=ligne.produit,
                    type='entree', quantite=qte_recue,
                    stock_avant=avant, stock_apres=apres,
                    reference=demande.numero,
                    notes=f'Livraison dotation {demande.numero}',
                    cree_par=request.user,
                )
                sp.quantite = apres
                sp.save(update_fields=['quantite'])

        demande.statut = 'approuvee' if tout_recu else 'partielle'
        demande.save(update_fields=['statut'])
        messages.success(request, f'Livraison {demande.numero} confirmée — stock mis à jour.')
        return redirect('pharmacie_livraisons', pharmacie=pharmacie)

    # Enrichir les lignes pour affichage
    lignes_enrichies = []
    for ligne in lignes:
        if not ligne.produit:
            continue
        sp = StockPharmacie.objects.filter(pharmacie=pharmacie, produit=ligne.produit).first()
        lignes_enrichies.append({
            'ligne':       ligne,
            'produit':     ligne.produit,
            'stock_actuel': float(sp.quantite) if sp else 0,
        })

    return render(request, 'pharmacie/confirmer_livraison.html', {
        'pharmacie':        pharmacie,
        'label':            label,
        'demande':          demande,
        'lignes_enrichies': lignes_enrichies,
    })


@login_required(login_url='login')
def pharmacie_caisse(request, pharmacie):
    from decimal import Decimal
    from django.db.models import Sum, Count
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    stats_jour = VentePharmacie.objects.filter(
        pharmacie=pharmacie, date_vente__date=today, statut='payee'
    ).aggregate(nb=Count('id'), total=Sum('montant_net'))
    if not stats_jour['nb']:
        stats_jour['nb'] = 0
    if not stats_jour['total']:
        stats_jour['total'] = Decimal('0')

    type_filtre = request.GET.get('type', '')
    q = request.GET.get('q', '').strip()

    qs = StockPharmacie.objects.filter(
        pharmacie=pharmacie, quantite__gt=0
    ).select_related('produit', 'produit__categorie').order_by('produit__type', 'produit__nom')

    if type_filtre:
        qs = qs.filter(produit__type=type_filtre)
    if q:
        qs = qs.filter(Q(produit__nom__icontains=q) | Q(produit__code__icontains=q))

    if request.method == 'POST':
        mode_paiement = request.POST.get('mode_paiement', 'especes')
        notes = request.POST.get('notes', '').strip()
        try:
            remise = Decimal(str(request.POST.get('remise', '0') or '0'))
        except Exception:
            remise = Decimal('0')

        all_stock = StockPharmacie.objects.filter(
            pharmacie=pharmacie, quantite__gt=0
        ).select_related('produit')

        lignes_data = []
        for sp in all_stock:
            val = request.POST.get(f'qte_{sp.produit.pk}', '').strip()
            if val:
                try:
                    qte = Decimal(str(val))
                    if qte > 0:
                        lignes_data.append((sp, qte))
                except Exception:
                    pass

        if not lignes_data:
            messages.error(request, 'Saisissez au moins une quantité.')
        else:
            montant_total = sum(sp.produit.prix_vente * qte for sp, qte in lignes_data)
            vente = VentePharmacie.objects.create(
                pharmacie=pharmacie,
                mode_paiement=mode_paiement,
                montant_total=montant_total,
                remise=remise,
                notes=notes,
                cree_par=request.user,
            )
            for sp, qte in lignes_data:
                LigneVente.objects.create(
                    vente=vente,
                    produit=sp.produit,
                    quantite=qte,
                    prix_unitaire=sp.produit.prix_vente,
                )
                avant = float(sp.quantite)
                apres = max(0.0, avant - float(qte))
                MouvementPharmacie.objects.create(
                    pharmacie=pharmacie,
                    produit=sp.produit,
                    type='vente',
                    quantite=qte,
                    stock_avant=avant,
                    stock_apres=apres,
                    reference=vente.numero,
                    cree_par=request.user,
                )
                sp.quantite = Decimal(str(apres))
                sp.save(update_fields=['quantite'])
            messages.success(request, f'Vente {vente.numero} enregistrée — {vente.montant_net} F CFA.')
            return redirect('pharmacie_ticket', pharmacie=pharmacie, pk=vente.pk)

    return render(request, 'pharmacie/caisse.html', {
        'pharmacie': pharmacie, 'label': label,
        'stock_items': qs,
        'stats_jour': stats_jour,
        'type_filtre': type_filtre, 'q': q,
        'today': today,
    })


@login_required(login_url='login')
def pharmacie_ticket(request, pharmacie, pk):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    vente = get_object_or_404(VentePharmacie, pk=pk, pharmacie=pharmacie)
    return render(request, 'pharmacie/ticket.html', {
        'pharmacie': pharmacie, 'label': label,
        'vente': vente,
    })


@login_required(login_url='login')
def pharmacie_recette(request, pharmacie):
    from decimal import Decimal
    from django.db.models import Sum, Count
    from datetime import datetime
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    date_str = request.GET.get('date', str(today))
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = today

    ventes = VentePharmacie.objects.filter(
        pharmacie=pharmacie, date_vente__date=selected_date
    ).prefetch_related('lignes__produit').order_by('-date_vente')

    payees = ventes.filter(statut='payee')
    stats = payees.aggregate(
        total=Sum('montant_net'),
        nb=Count('id'),
        especes=Sum('montant_net', filter=Q(mode_paiement='especes')),
        mobile=Sum('montant_net', filter=Q(mode_paiement='mobile_money')),
        assurance=Sum('montant_net', filter=Q(mode_paiement='assurance')),
    )
    for k in ['total', 'especes', 'mobile', 'assurance']:
        if stats[k] is None:
            stats[k] = Decimal('0')
    if stats['nb'] is None:
        stats['nb'] = 0

    return render(request, 'pharmacie/recette.html', {
        'pharmacie': pharmacie, 'label': label,
        'ventes': ventes, 'stats': stats,
        'selected_date': selected_date, 'today': today,
    })


@login_required(login_url='login')
def pharmacie_rapport_journalier(request, pharmacie):
    from decimal import Decimal
    from django.db.models import Sum, Count
    from datetime import datetime
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    date_str = request.GET.get('date', str(today))
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = today

    ventes = VentePharmacie.objects.filter(
        pharmacie=pharmacie, date_vente__date=selected_date
    ).prefetch_related(
        'lignes__produit', 'lignes__produit__categorie'
    ).select_related('patient', 'cree_par').order_by('date_vente')

    payees = ventes.filter(statut='payee')
    stats = payees.aggregate(
        total=Sum('montant_net'),
        nb=Count('id'),
        especes=Sum('montant_net', filter=Q(mode_paiement='especes')),
        mobile=Sum('montant_net', filter=Q(mode_paiement='mobile_money')),
        assurance=Sum('montant_net', filter=Q(mode_paiement='assurance')),
    )
    for k in ['total', 'especes', 'mobile', 'assurance']:
        if stats[k] is None:
            stats[k] = Decimal('0')
    if stats['nb'] is None:
        stats['nb'] = 0

    recap_produits = {}
    for vente in payees:
        for ligne in vente.lignes.all():
            pid = ligne.produit_id
            if pid not in recap_produits:
                recap_produits[pid] = {
                    'produit': ligne.produit,
                    'qte_totale': Decimal('0'),
                    'montant_total': Decimal('0'),
                }
            recap_produits[pid]['qte_totale']   += ligne.quantite
            recap_produits[pid]['montant_total'] += ligne.montant

    recap_list = sorted(recap_produits.values(), key=lambda x: x['montant_total'], reverse=True)

    return render(request, 'pharmacie/rapport_journalier.html', {
        'pharmacie':     pharmacie,
        'label':         label,
        'ventes':        ventes,
        'stats':         stats,
        'recap_list':    recap_list,
        'selected_date': selected_date,
        'today':         today,
        'generated_at':  timezone.now(),
        'generated_by':  request.user,
    })


@login_required(login_url='login')
def pharmacie_fiche_dispensation(request, pharmacie, pk):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    dispensation = get_object_or_404(DispensationOrdonnance, pk=pk, pharmacie=pharmacie)
    return render(request, 'pharmacie/fiche_dispensation.html', {
        'pharmacie': pharmacie, 'label': label,
        'dispensation': dispensation,
        'ordonnance': dispensation.ordonnance,
        'now': timezone.now(),
    })


@login_required(login_url='login')
def pharmacie_alertes_reappro(request, pharmacie):
    from decimal import Decimal
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    ruptures = StockPharmacie.objects.filter(
        pharmacie=pharmacie, quantite__lte=0
    ).select_related('produit').order_by('produit__nom')

    alertes = StockPharmacie.objects.filter(
        pharmacie=pharmacie, quantite__gt=0,
        quantite__lte=F('produit__stock_alerte')
    ).select_related('produit').order_by('quantite')

    if request.method == 'POST':
        notes = request.POST.get('notes', 'Demande générée depuis alertes réapprovisionnement')
        produit_ids = request.POST.getlist('produits')
        if produit_ids:
            demande = DemandePharmacie.objects.create(
                pharmacie=pharmacie, notes=notes, cree_par=request.user,
            )
            nb = 0
            for pid in produit_ids:
                try:
                    produit = Produit.objects.get(pk=int(pid))
                    qte_str = request.POST.get(f'qte_{pid}', '1')
                    qte = Decimal(str(qte_str or '1'))
                    if qte > 0:
                        LigneDemande.objects.create(demande=demande, produit=produit, quantite_demandee=qte)
                        nb += 1
                except Exception:
                    pass
            if nb > 0:
                messages.success(request, f'Demande {demande.numero} créée ({nb} produit{"s" if nb>1 else ""}).')
                return redirect('pharmacie_dashboard', pharmacie=pharmacie)
            demande.delete()
        messages.error(request, 'Sélectionnez au moins un produit.')

    return render(request, 'pharmacie/alertes_reappro.html', {
        'pharmacie': pharmacie, 'label': label,
        'ruptures': ruptures, 'alertes': alertes,
    })


@login_required(login_url='login')
def pharmacie_peremptions(request, pharmacie):
    from datetime import timedelta
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    produits_ids = StockPharmacie.objects.filter(
        pharmacie=pharmacie, quantite__gt=0
    ).values_list('produit_id', flat=True)

    q = request.GET.get('q', '').strip()
    produit_id = request.GET.get('produit_id', '').strip()

    from stock.models import LotProduit
    lots = LotProduit.objects.filter(
        produit_id__in=produits_ids,
        date_peremption__lte=today + timedelta(days=90),
        quantite_actuelle__gt=0,
    ).select_related('produit').order_by('date_peremption')

    produits = LotProduit.objects.filter(
        produit_id__in=produits_ids,
        quantite_actuelle__gt=0
    ).select_related('produit').order_by('produit__nom').values_list('produit_id', 'produit__nom').distinct()

    if produit_id:
        try:
            lots = lots.filter(produit_id=int(produit_id))
        except ValueError:
            pass
    elif q:
        lots = lots.filter(produit__nom__icontains=q)

    lots_enrichis = []
    for lot in lots:
        jours = (lot.date_peremption - today).days
        niveau = 'perime' if jours < 0 else 'critique' if jours <= 30 else 'alerte' if jours <= 60 else 'attention'
        lots_enrichis.append({'lot': lot, 'jours': jours, 'niveau': niveau})

    return render(request, 'pharmacie/peremptions.html', {
        'pharmacie': pharmacie, 'label': label,
        'lots_enrichis': lots_enrichis, 'today': today,
        'produits': produits, 'q': q, 'produit_id': produit_id,
    })


@login_required(login_url='login')
def pharmacie_retours(request, pharmacie):
    from decimal import Decimal
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    stock_items = StockPharmacie.objects.filter(
        pharmacie=pharmacie
    ).select_related('produit').order_by('produit__nom')

    q = request.GET.get('q', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    historique = MouvementPharmacie.objects.filter(
        pharmacie=pharmacie, type='retour'
    ).select_related('produit', 'cree_par').order_by('-date')

    if q:
        historique = historique.filter(
            Q(produit__nom__icontains=q) |
            Q(reference__icontains=q) |
            Q(notes__icontains=q)
        )

    if start_date:
        try:
            start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
            historique = historique.filter(date__date__gte=start)
        except ValueError:
            pass

    if end_date:
        try:
            end = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
            historique = historique.filter(date__date__lte=end)
        except ValueError:
            pass

    historique = historique[:20]

    if request.method == 'POST':
        try:
            produit_id = int(request.POST.get('produit_id', 0))
            qte = Decimal(str(request.POST.get('quantite', '0') or '0'))
            if qte <= 0: raise ValueError
        except Exception:
            messages.error(request, 'Quantité invalide.')
            return redirect('pharmacie_retours', pharmacie=pharmacie)

        motif = request.POST.get('motif', '').strip()
        sp = StockPharmacie.objects.filter(pharmacie=pharmacie, produit_id=produit_id).first()
        if not sp:
            messages.error(request, 'Produit introuvable.')
            return redirect('pharmacie_retours', pharmacie=pharmacie)

        avant = float(sp.quantite)
        apres = avant + float(qte)
        MouvementPharmacie.objects.create(
            pharmacie=pharmacie, produit=sp.produit,
            type='retour', quantite=qte,
            stock_avant=avant, stock_apres=apres,
            reference=motif, notes=motif, cree_par=request.user,
        )
        sp.quantite = Decimal(str(apres))
        sp.save(update_fields=['quantite'])
        messages.success(request, f'Retour de {qte} {sp.produit.unite_mesure} de « {sp.produit.nom} » enregistré.')
        return redirect('pharmacie_retours', pharmacie=pharmacie)

    return render(request, 'pharmacie/retours.html', {
        'pharmacie': pharmacie, 'label': label,
        'stock_items': stock_items, 'historique': historique,
    })


@login_required(login_url='login')
def pharmacie_inventaire_list(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    inventaires = InventairePharmacie.objects.filter(
        pharmacie=pharmacie
    ).select_related('cree_par', 'valide_par').order_by('-date_inventaire')
    return render(request, 'pharmacie/inventaire_list.html', {
        'pharmacie': pharmacie, 'label': label, 'inventaires': inventaires,
    })


@login_required(login_url='login')
def pharmacie_inventaire_nouveau(request, pharmacie):
    from decimal import Decimal
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    stock_items = StockPharmacie.objects.filter(
        pharmacie=pharmacie
    ).select_related('produit').order_by('produit__type', 'produit__nom')

    if request.method == 'POST':
        date_str = request.POST.get('date_inventaire', str(timezone.now().date()))
        notes = request.POST.get('notes', '').strip()
        try:
            from datetime import datetime as _dt
            date_inv = _dt.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            date_inv = timezone.now().date()

        inv = InventairePharmacie.objects.create(
            pharmacie=pharmacie, date_inventaire=date_inv,
            notes=notes, cree_par=request.user,
        )
        for sp in stock_items:
            val = request.POST.get(f'reel_{sp.produit.pk}', '').strip()
            try:
                reel = Decimal(str(val)) if val != '' else sp.quantite
            except Exception:
                reel = sp.quantite
            LigneInventairePharmacie.objects.create(
                inventaire=inv, produit=sp.produit,
                stock_theorique=sp.quantite, stock_reel=reel,
            )
        messages.success(request, f'Inventaire {inv.numero} créé.')
        return redirect('pharmacie_inventaire_detail', pharmacie=pharmacie, pk=inv.pk)

    return render(request, 'pharmacie/inventaire_form.html', {
        'pharmacie': pharmacie, 'label': label,
        'stock_items': stock_items, 'today': timezone.now().date(),
    })


@login_required(login_url='login')
def pharmacie_inventaire_detail(request, pharmacie, pk):
    from decimal import Decimal
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    inv = get_object_or_404(InventairePharmacie, pk=pk, pharmacie=pharmacie)
    lignes = list(inv.lignes.select_related('produit').order_by('produit__type', 'produit__nom'))

    if request.method == 'POST' and inv.statut == 'brouillon':
        for ligne in lignes:
            val = request.POST.get(f'reel_{ligne.produit.pk}', '').strip()
            if val:
                try:
                    ligne.stock_reel = Decimal(str(val))
                    ligne.save(update_fields=['stock_reel'])
                except Exception:
                    pass

        if request.POST.get('action') == 'valider':
            for ligne in inv.lignes.select_related('produit').all():
                ecart = ligne.stock_reel - ligne.stock_theorique
                if ecart != 0:
                    sp = StockPharmacie.objects.filter(pharmacie=pharmacie, produit=ligne.produit).first()
                    if sp:
                        avant = float(sp.quantite)
                        apres = float(ligne.stock_reel)
                        MouvementPharmacie.objects.create(
                            pharmacie=pharmacie, produit=ligne.produit,
                            type='ajustement', quantite=ecart,
                            stock_avant=avant, stock_apres=apres,
                            reference=inv.numero,
                            notes=f'Ajustement inventaire {inv.numero}',
                            cree_par=request.user,
                        )
                        sp.quantite = Decimal(str(apres))
                        sp.save(update_fields=['quantite'])
            inv.statut = 'valide'
            inv.valide_par = request.user
            inv.date_validation = timezone.now()
            inv.save(update_fields=['statut', 'valide_par', 'date_validation'])
            messages.success(request, f'Inventaire {inv.numero} validé. Stock ajusté.')
            return redirect('pharmacie_inventaire_detail', pharmacie=pharmacie, pk=inv.pk)
        else:
            messages.success(request, 'Quantités enregistrées.')
        lignes = list(inv.lignes.select_related('produit').order_by('produit__type', 'produit__nom'))

    stats = {
        'total': len(lignes),
        'avec_ecart': sum(1 for l in lignes if l.ecart != 0),
        'manquants': sum(1 for l in lignes if l.ecart < 0),
        'excedents': sum(1 for l in lignes if l.ecart > 0),
    }

    return render(request, 'pharmacie/inventaire_detail.html', {
        'pharmacie': pharmacie, 'label': label,
        'inv': inv, 'lignes': lignes, 'stats': stats,
    })


@login_required(login_url='login')
def pharmacie_rapport_mensuel(request, pharmacie):
    from decimal import Decimal
    from django.db.models import Sum, Count
    from datetime import date as date_type
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    y, m = today.year, today.month
    mois_list = []
    for _ in range(12):
        mois_list.insert(0, date_type(y, m, 1))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    ventes_mois = []
    for mo in mois_list:
        agg = VentePharmacie.objects.filter(
            pharmacie=pharmacie,
            date_vente__year=mo.year, date_vente__month=mo.month,
            statut='payee',
        ).aggregate(total=Sum('montant_net'), nb=Count('id'))
        ventes_mois.append({
            'label': mo.strftime('%b %Y'),
            'total': float(agg['total'] or 0),
            'nb': agg['nb'] or 0,
        })

    disp_mois = []
    for mo in mois_list:
        nb = DispensationOrdonnance.objects.filter(
            pharmacie=pharmacie,
            date__year=mo.year, date__month=mo.month,
        ).count()
        disp_mois.append({'label': mo.strftime('%b %Y'), 'nb': nb})

    from .models import LigneVente
    mois_actuel = date_type(today.year, today.month, 1)
    top_produits = LigneVente.objects.filter(
        vente__pharmacie=pharmacie,
        vente__date_vente__year=mois_actuel.year,
        vente__date_vente__month=mois_actuel.month,
        vente__statut='payee',
    ).values('produit__nom').annotate(
        qte=Sum('quantite'), montant=Sum('montant')
    ).order_by('-montant')[:10]

    return render(request, 'pharmacie/rapport_mensuel.html', {
        'pharmacie': pharmacie, 'label': label, 'today': today,
        'ventes_mois': ventes_mois, 'disp_mois': disp_mois,
        'top_produits': top_produits,
        'total_annee': sum(m['total'] for m in ventes_mois),
        'total_disp': sum(m['nb'] for m in disp_mois),
        'chart_labels': [m['label'] for m in ventes_mois],
        'chart_ventes': [m['total'] for m in ventes_mois],
        'chart_disp':   [m['nb'] for m in disp_mois],
    })


@login_required(login_url='login')
def pharmacie_rapport_dispensation(request, pharmacie):
    from django.db.models import Count
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]
    today = timezone.now().date()

    mois_str = request.GET.get('mois', today.strftime('%Y-%m'))
    try:
        annee, mois = int(mois_str[:4]), int(mois_str[5:7])
    except Exception:
        annee, mois = today.year, today.month

    dispensations = DispensationOrdonnance.objects.filter(
        pharmacie=pharmacie, date__year=annee, date__month=mois,
    ).select_related(
        'ordonnance__consultation__patient',
        'ordonnance__consultation__medecin',
        'dispense_par',
    ).prefetch_related('lignes__produit').order_by('-date')

    stats = dispensations.aggregate(
        total=Count('id'),
        completes=Count('id', filter=Q(statut='complete')),
        partielles=Count('id', filter=Q(statut='partielle')),
    )

    return render(request, 'pharmacie/rapport_dispensation.html', {
        'pharmacie': pharmacie, 'label': label,
        'dispensations': dispensations, 'stats': stats,
        'mois_str': mois_str, 'today': today,
    })


@login_required(login_url='login')
def pharmacie_comparaison(request, pharmacie):
    get_pharmacie_or_404(pharmacie)
    label = PHARMACIES_DICT[pharmacie]

    all_produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    ph1_code = PHARMACIES_WALE[0][0]; ph1_label = PHARMACIES_WALE[0][1]
    ph2_code = PHARMACIES_WALE[1][0]; ph2_label = PHARMACIES_WALE[1][1]

    stocks = {}
    for sp in StockPharmacie.objects.filter(
        pharmacie__in=[ph1_code, ph2_code]
    ).select_related('produit'):
        stocks.setdefault(sp.produit_id, {})[sp.pharmacie] = float(sp.quantite)

    produits_data = []
    for p in all_produits:
        s = stocks.get(p.pk, {})
        q1 = s.get(ph1_code, 0); q2 = s.get(ph2_code, 0)
        if q1 > 0 or q2 > 0:
            produits_data.append({
                'produit': p, 'qte1': q1, 'qte2': q2, 'total': q1 + q2,
            })

    return render(request, 'pharmacie/comparaison.html', {
        'pharmacie': pharmacie, 'label': label,
        'produits_data': produits_data,
        'ph1_code': ph1_code, 'ph1_label': ph1_label,
        'ph2_code': ph2_code, 'ph2_label': ph2_label,
    })
