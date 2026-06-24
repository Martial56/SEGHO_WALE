from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Produit, CategorieStock, LotProduit, MouvementStock, CommandeStock, LigneCommande, Inventaire, LigneInventaire, DemandePharmacie, LigneDemande, PHARMACIES, FicheBesoins, LigneFicheBesoins, UniteMesure
from achats.models import Fournisseur


@login_required(login_url='login')
def stock_dashboard(request):
    import json as _json
    today = timezone.now().date()

    ok      = Produit.objects.filter(actif=True, stock_actuel__gt=F('stock_alerte')).count()
    alertes = Produit.objects.filter(actif=True, stock_actuel__gt=0, stock_actuel__lte=F('stock_alerte')).count()
    ruptures = Produit.objects.filter(actif=True, stock_actuel__lte=0).count()

    stats = {
        'total_produits':     Produit.objects.filter(actif=True).count(),
        'medicaments':        Produit.objects.filter(type='medicament', actif=True).count(),
        'consommables':       Produit.objects.filter(type='consommable', actif=True).count(),
        'equipements':        Produit.objects.filter(type='equipement', actif=True).count(),
        'ruptures':           ruptures,
        'alertes':            alertes,
        'commandes_en_cours': CommandeStock.objects.filter(statut__in=['brouillon', 'envoye', 'partiel']).count(),
        'lots_perimes':       LotProduit.objects.filter(date_peremption__lt=today, quantite_actuelle__gt=0).count(),
    }

    # ── Graphe 1 : Répartition statut stock (donut) ──
    chart_statut = {
        'labels': ['Stock OK', 'En alerte', 'Rupture'],
        'data':   [ok, alertes, ruptures],
        'colors': ['#1a237e', '#f57c00', '#d32f2f'],
    }

    # ── Graphe 2 : Entrées vs Livraisons sur 7 jours (ligne) ──
    jours_labels, entrees_data, sorties_data = [], [], []
    for i in range(6, -1, -1):
        d = today - timezone.timedelta(days=i)
        jours_labels.append(d.strftime('%d/%m'))
        entrees_data.append(
            int(MouvementStock.objects.filter(type='entree', date__date=d).aggregate(
                t=Sum('quantite'))['t'] or 0)
        )
        sorties_data.append(
            int(MouvementStock.objects.filter(type='livraison', date__date=d).aggregate(
                t=Sum('quantite'))['t'] or 0)
        )
    chart_mouvements = {
        'labels':  jours_labels,
        'entrees': entrees_data,
        'sorties': sorties_data,
    }

    # ── Graphe 3 : Top 6 produits livrés (30 jours) ──
    from collections import defaultdict
    debut_mois = today - timezone.timedelta(days=30)
    mvts = MouvementStock.objects.filter(
        type='livraison', date__date__gte=debut_mois
    ).select_related('produit')
    conso = defaultdict(float)
    for mv in mvts:
        conso[mv.produit.nom[:20]] += float(mv.quantite)
    top_items = sorted(conso.items(), key=lambda x: x[1], reverse=True)[:6]
    chart_top = {
        'labels': [t[0] for t in top_items],
        'data':   [t[1] for t in top_items],
    }

    # ── Graphe 4 : Répartition par type (bar) ──
    chart_types = {
        'labels': ['Médicaments', 'Consommables', 'Équipements'],
        'data':   [
            Produit.objects.filter(type='medicament', actif=True).count(),
            Produit.objects.filter(type='consommable', actif=True).count(),
            Produit.objects.filter(type='equipement', actif=True).count(),
        ],
        'colors': ['#4a6741', '#1a237e', '#4527a0'],
    }

    produits_alerte = Produit.objects.filter(
        actif=True, stock_actuel__lte=F('stock_alerte')
    ).order_by('stock_actuel')[:10]

    lots_a_surveiller = LotProduit.objects.filter(
        quantite_actuelle__gt=0,
        date_peremption__lte=today + timezone.timedelta(days=90)
    ).select_related('produit').order_by('date_peremption')[:10]

    derniers_mouvements = MouvementStock.objects.select_related('produit').order_by('-date')[:10]

    commandes_recentes = CommandeStock.objects.select_related('fournisseur').exclude(
        statut='annule'
    ).order_by('-date_creation')[:5]

    # Point 1 — Alertes critiques (ruptures, sous seuil minimum, lots périmant dans 30j)
    produits_rupture      = Produit.objects.filter(actif=True, stock_actuel__lte=0).order_by('nom')[:5]
    produits_sous_minimum = Produit.objects.filter(
        actif=True, stock_actuel__gt=0, stock_actuel__lte=F('stock_minimum')
    ).order_by('stock_actuel')[:5]
    lots_expiration_30 = LotProduit.objects.filter(
        quantite_actuelle__gt=0,
        date_peremption__gt=today,
        date_peremption__lte=today + timezone.timedelta(days=30),
    ).select_related('produit').order_by('date_peremption')[:5]

    # Points 3 & 6 — À commander + KPIs (une seule requête produits partagée)
    produits_all = list(Produit.objects.filter(actif=True))
    a_commander_dash = sorted(
        [{'produit': p, 'qte': p.qte_a_commander, 'stock': p.stock_actuel, 'minimum': p.stock_minimum}
         for p in produits_all if p.qte_a_commander > 0],
        key=lambda x: x['qte'], reverse=True
    )[:8]
    kpi_valeur_stock     = round(sum(float(p.stock_actuel) * float(p.prix_achat) for p in produits_all))
    total_livr_kpi       = float(MouvementStock.objects.filter(type='livraison').aggregate(t=Sum('quantite'))['t'] or 0)
    stock_total_kpi      = sum(float(p.stock_actuel) for p in produits_all)
    kpi_taux_rotation    = round(total_livr_kpi / stock_total_kpi, 2) if stock_total_kpi > 0 else 0
    _td = float(LigneDemande.objects.aggregate(t=Sum('quantite_demandee'))['t'] or 0)
    _ta = float(LigneDemande.objects.aggregate(t=Sum('quantite_approuvee'))['t'] or 0)
    kpi_taux_service     = round(_ta / _td * 100, 1) if _td > 0 else 0
    lots_obsoletes_count = LotProduit.objects.filter(
        quantite_actuelle__gt=0,
        date_reception__lt=today - timezone.timedelta(days=180),
    ).count()

    return render(request, 'stock/dashboard.html', {
        'stats':               stats,
        'produits_alerte':     produits_alerte,
        'lots_a_surveiller':   lots_a_surveiller,
        'derniers_mouvements': derniers_mouvements,
        'commandes_recentes':  commandes_recentes,
        'today':               today,
        'chart_statut':        chart_statut,
        'chart_mouvements':    chart_mouvements,
        'chart_top':           chart_top,
        'chart_types':         chart_types,
        # Point 1
        'produits_rupture':      produits_rupture,
        'produits_sous_minimum': produits_sous_minimum,
        'lots_expiration_30':    lots_expiration_30,
        # Point 3
        'a_commander_dash':      a_commander_dash,
        # Point 6
        'kpi_valeur_stock':      kpi_valeur_stock,
        'kpi_taux_rotation':     kpi_taux_rotation,
        'kpi_taux_service':      kpi_taux_service,
        'lots_obsoletes_count':  lots_obsoletes_count,
    })


@login_required(login_url='login')
def produits_list(request):
    qs = Produit.objects.select_related('categorie').prefetch_related('lots').filter(actif=True)
    type_filtre      = request.GET.get('type', '')
    statut_filtre    = request.GET.get('statut', '')
    categorie_filtre = request.GET.get('categorie', '')
    q = request.GET.get('q', '').strip()

    if type_filtre:
        qs = qs.filter(type=type_filtre)
    if categorie_filtre:
        qs = qs.filter(categorie__pk=categorie_filtre)
    if statut_filtre == 'rupture':
        qs = qs.filter(stock_actuel__lte=0)
    elif statut_filtre == 'alerte':
        qs = qs.filter(stock_actuel__gt=0, stock_actuel__lte=F('stock_alerte'))
    elif statut_filtre == 'ok':
        qs = qs.filter(stock_actuel__gt=F('stock_alerte'))
    if q:
        qs = qs.filter(
            Q(nom__icontains=q) | Q(code__icontains=q) |
            Q(dci__icontains=q) | Q(lots__numero_lot__icontains=q)
        ).distinct()

    qs = qs.order_by('type', 'nom')
    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    categories = CategorieStock.objects.filter(actif=True).order_by('nom')
    stats = {
        'total':      Produit.objects.filter(actif=True).count(),
        'ruptures':   Produit.objects.filter(actif=True, stock_actuel__lte=0).count(),
        'alertes':    Produit.objects.filter(actif=True, stock_actuel__gt=0, stock_actuel__lte=F('stock_alerte')).count(),
    }

    return render(request, 'stock/produits/list.html', {
        'page_obj':      page_obj,
        'categories':    categories,
        'type_filtre':      type_filtre,
        'statut_filtre':    statut_filtre,
        'categorie_filtre': categorie_filtre,
        'q':                q,
        'stats':         stats,
    })


@login_required(login_url='login')
def produit_detail(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    lots = produit.lots.order_by('date_peremption')
    mouvements = produit.mouvements.order_by('-date')[:20]
    return render(request, 'stock/produits/detail.html', {
        'produit':    produit,
        'lots':       lots,
        'mouvements': mouvements,
        'today':      timezone.now().date(),
    })


@login_required(login_url='login')
def produit_create(request):
    categories  = CategorieStock.objects.filter(actif=True).order_by('nom')
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    unites      = UniteMesure.objects.filter(actif=True).order_by('categorie', 'nom')
    errors = {}

    if request.method == 'POST':
        nom  = request.POST.get('nom', '').strip()
        type_ = request.POST.get('type', 'medicament')
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not errors:
            um_pk = request.POST.get('unite_mesure', '')
            p = Produit(
                nom=nom, type=type_,
                dci=request.POST.get('dci', '').strip(),
                dosage=request.POST.get('dosage', '').strip(),
                forme=request.POST.get('forme', ''),
                unite_mesure_id=int(um_pk) if um_pk.isdigit() else None,
                description=request.POST.get('description', '').strip(),
                prescription_obligatoire=request.POST.get('prescription_obligatoire') == 'on',
            )
            try: p.stock_alerte  = float(request.POST.get('stock_alerte',  10) or 10)
            except ValueError: p.stock_alerte = 10
            try: p.stock_minimum = float(request.POST.get('stock_minimum', 5) or 5)
            except ValueError: p.stock_minimum = 5
            try: p.prix_achat    = float(request.POST.get('prix_achat', 0) or 0)
            except ValueError: p.prix_achat = 0
            try: p.prix_vente    = float(request.POST.get('prix_vente', 0) or 0)
            except ValueError: p.prix_vente = 0
            cat_pk = request.POST.get('categorie', '')
            if cat_pk:
                p.categorie = CategorieStock.objects.filter(pk=cat_pk).first()
            frn_pk = request.POST.get('fournisseur_principal', '')
            if frn_pk:
                p.fournisseur_principal = Fournisseur.objects.filter(pk=frn_pk).first()
            p.save()
            messages.success(request, f'Produit « {p.nom} » créé (code : {p.code}).')
            return redirect('stock_produit_detail', pk=p.pk)

    return render(request, 'stock/produits/form.html', {
        'mode':         'create',
        'categories':   categories,
        'fournisseurs': fournisseurs,
        'unites':       unites,
        'errors':       errors,
        'post':         request.POST if request.method == 'POST' else None,
    })


@login_required(login_url='login')
def produit_edit(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    categories   = CategorieStock.objects.filter(actif=True).order_by('nom')
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    unites       = UniteMesure.objects.filter(actif=True).order_by('categorie', 'nom')
    errors = {}

    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not errors:
            um_pk = request.POST.get('unite_mesure', '')
            produit.nom   = nom
            produit.type  = request.POST.get('type', produit.type)
            produit.dci   = request.POST.get('dci', '').strip()
            produit.dosage = request.POST.get('dosage', '').strip()
            produit.forme  = request.POST.get('forme', '')
            produit.unite_mesure_id = int(um_pk) if um_pk.isdigit() else None
            produit.description  = request.POST.get('description', '').strip()
            produit.prescription_obligatoire = request.POST.get('prescription_obligatoire') == 'on'
            produit.actif = request.POST.get('actif') != 'off'
            try: produit.stock_alerte  = float(request.POST.get('stock_alerte',  produit.stock_alerte) or 10)
            except ValueError: pass
            try: produit.stock_minimum = float(request.POST.get('stock_minimum', produit.stock_minimum) or 5)
            except ValueError: pass
            try: produit.prix_achat    = float(request.POST.get('prix_achat', produit.prix_achat) or 0)
            except ValueError: pass
            try: produit.prix_vente    = float(request.POST.get('prix_vente', produit.prix_vente) or 0)
            except ValueError: pass
            cat_pk = request.POST.get('categorie', '')
            produit.categorie = CategorieStock.objects.filter(pk=cat_pk).first() if cat_pk else None
            frn_pk = request.POST.get('fournisseur_principal', '')
            produit.fournisseur_principal = Fournisseur.objects.filter(pk=frn_pk).first() if frn_pk else None
            produit.save()
            messages.success(request, f'Produit « {produit.nom} » mis à jour.')
            return redirect('stock_produit_detail', pk=produit.pk)

    return render(request, 'stock/produits/form.html', {
        'mode':         'edit',
        'produit':      produit,
        'categories':   categories,
        'fournisseurs': fournisseurs,
        'unites':       unites,
        'errors':       errors,
    })


@login_required(login_url='login')
def mouvements_list(request):
    qs = MouvementStock.objects.select_related('produit').order_by('-date')
    type_filtre = request.GET.get('type', '')
    periode     = request.GET.get('periode', '')
    q           = request.GET.get('q', '').strip()

    if type_filtre:
        qs = qs.filter(type=type_filtre)
    if q:
        qs = qs.filter(Q(produit__nom__icontains=q) | Q(reference__icontains=q))

    today = timezone.now().date()
    if periode == 'today':
        qs = qs.filter(date__date=today)
    elif periode == 'week':
        debut_semaine = today - timezone.timedelta(days=today.weekday())
        qs = qs.filter(date__date__gte=debut_semaine)
    elif periode == 'month':
        qs = qs.filter(date__month=today.month, date__year=today.year)

    try:
        per_page = int(request.GET.get('per_page', 20))
        if per_page not in (10, 20, 40, 50, 100):
            per_page = 20
    except ValueError:
        per_page = 20

    paginator = Paginator(qs, per_page)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/mouvements/list.html', {
        'page_obj':    page_obj,
        'per_page':    per_page,
        'total':       qs.count(),
        'type_filtre': type_filtre,
        'periode':     periode,
        'q':           q,
    })


@login_required(login_url='login')
def mouvement_create(request):
    produits = Produit.objects.filter(actif=True).order_by('nom')
    if request.method == 'POST':
        produit_pk = request.POST.get('produit', '')
        type_      = request.POST.get('type', '')
        motif      = request.POST.get('motif', '')
        try:
            quantite = float(request.POST.get('quantite', 0) or 0)
        except ValueError:
            quantite = 0
        notes    = request.POST.get('notes', '').strip()
        reference = request.POST.get('reference', '').strip()

        produit = Produit.objects.filter(pk=produit_pk).first()
        if produit and quantite > 0 and type_:
            stock_avant = float(produit.stock_actuel)
            if type_ == 'entree':
                stock_apres = stock_avant + quantite
            elif type_ in ('sortie', 'peremption', 'retour'):
                stock_apres = max(0, stock_avant - quantite)
            else:
                stock_apres = quantite  # ajustement

            MouvementStock.objects.create(
                produit=produit, type=type_, motif=motif,
                quantite=quantite, stock_avant=stock_avant,
                stock_apres=stock_apres, notes=notes, reference=reference,
                cree_par=request.user,
            )
            produit.stock_actuel = stock_apres
            produit.save(update_fields=['stock_actuel'])
            messages.success(request, f'Mouvement enregistré pour « {produit.nom} ».')
            return redirect('stock_mouvements')

    return render(request, 'stock/mouvements/form.html', {'produits': produits})


@login_required(login_url='login')
def commandes_list(request):
    qs = CommandeStock.objects.select_related('fournisseur').order_by('-date_creation')
    statut_filtre = request.GET.get('statut', '')
    if statut_filtre:
        qs = qs.filter(statut=statut_filtre)
    paginator = Paginator(qs, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/commandes/list.html', {
        'page_obj':     page_obj,
        'statut_filtre': statut_filtre,
    })


@login_required(login_url='login')
def commande_create(request):
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    produits     = Produit.objects.filter(actif=True).order_by('nom')
    if request.method == 'POST':
        frn_pk = request.POST.get('fournisseur', '')
        fournisseur = Fournisseur.objects.filter(pk=frn_pk).first()
        if fournisseur:
            cmd = CommandeStock.objects.create(
                fournisseur=fournisseur,
                notes=request.POST.get('notes', '').strip(),
                cree_par=request.user,
            )
            messages.success(request, f'Commande {cmd.numero} créée.')
            return redirect('stock_commande_detail', pk=cmd.pk)
    return render(request, 'stock/commandes/form.html', {
        'fournisseurs': fournisseurs,
        'produits':     produits,
    })


@login_required(login_url='login')
@require_POST
def commande_ajouter_ligne(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut != 'brouillon':
        return JsonResponse({'error': 'La commande n\'est plus modifiable.'}, status=400)

    produit_pk  = request.POST.get('produit', '')
    try:
        quantite    = float(request.POST.get('quantite', 0) or 0)
        prix        = float(request.POST.get('prix_unitaire', 0) or 0)
    except ValueError:
        return JsonResponse({'error': 'Quantité ou prix invalide.'}, status=400)
    notes = request.POST.get('notes', '').strip()

    produit = Produit.objects.filter(pk=produit_pk).first()
    if not produit:
        return JsonResponse({'error': 'Produit introuvable.'}, status=400)
    if quantite <= 0:
        return JsonResponse({'error': 'La quantité doit être supérieure à 0.'}, status=400)

    ligne = LigneCommande.objects.create(
        commande=commande, produit=produit,
        quantite_commandee=quantite, prix_unitaire=prix, notes=notes,
    )

    # Recalculer le montant total
    total = sum(float(l.quantite_commandee) * float(l.prix_unitaire)
                for l in commande.lignes.all())
    commande.montant_total = total
    commande.save(update_fields=['montant_total'])

    return JsonResponse({
        'id':           ligne.pk,
        'produit_nom':  produit.nom,
        'produit_code': produit.code,
        'produit_pk':   produit.pk,
        'quantite':     float(ligne.quantite_commandee),
        'prix':         float(ligne.prix_unitaire),
        'montant':      float(ligne.montant),
        'total':        float(commande.montant_total),
        'nb_lignes':    commande.lignes.count(),
    })


@login_required(login_url='login')
@require_POST
def commande_ajouter_lot(request, pk):
    """Ajoute plusieurs produits à la commande en une seule soumission."""
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut != 'brouillon':
        return JsonResponse({'error': 'Non modifiable.'}, status=400)

    produits = Produit.objects.filter(actif=True)
    ajouts = []
    deja_presents = []
    for p in produits:
        qte_str = request.POST.get(f'qte_{p.pk}', '').strip()
        prix_str = request.POST.get(f'prix_{p.pk}', '').strip()
        if not qte_str:
            continue
        try:
            qte = float(qte_str)
        except ValueError:
            continue
        if qte <= 0:
            continue
        try:
            prix = float(prix_str) if prix_str else float(p.prix_achat)
        except ValueError:
            prix = float(p.prix_achat)

        # Un produit ne peut apparaître qu'une seule fois par commande
        if LigneCommande.objects.filter(commande=commande, produit=p).exists():
            deja_presents.append(p.nom)
            continue
        LigneCommande.objects.create(
            commande=commande, produit=p,
            quantite_commandee=qte, prix_unitaire=prix,
        )
        ajouts.append(p.nom)

    total = sum(float(l.quantite_commandee) * float(l.prix_unitaire) for l in commande.lignes.all())
    commande.montant_total = total
    commande.save(update_fields=['montant_total'])

    if ajouts:
        messages.success(request, f'{len(ajouts)} produit(s) ajouté(s) à la commande.')
    if deja_presents:
        noms = ', '.join(deja_presents)
        messages.warning(request, f'Déjà dans la commande (ignoré) : {noms}.')
    return redirect('stock_commande_detail', pk=pk)


@login_required(login_url='login')
@require_POST
def commande_supprimer_ligne(request, pk, ligne_pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut != 'brouillon':
        return JsonResponse({'error': 'Non modifiable.'}, status=400)
    ligne = get_object_or_404(LigneCommande, pk=ligne_pk, commande=commande)
    ligne.delete()
    total = sum(float(l.quantite_commandee) * float(l.prix_unitaire)
                for l in commande.lignes.all())
    commande.montant_total = total
    commande.save(update_fields=['montant_total'])
    return JsonResponse({'total': float(total), 'nb_lignes': commande.lignes.count()})


@login_required(login_url='login')
def commande_print(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    lignes   = commande.lignes.select_related('produit').all()
    return render(request, 'stock/commandes/print.html', {
        'commande': commande,
        'lignes':   lignes,
        'today':    timezone.now().date(),
    })


@login_required(login_url='login')
def commande_detail(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    lignes   = commande.lignes.select_related('produit').all()
    produits = Produit.objects.filter(actif=True).order_by('nom')
    return render(request, 'stock/commandes/detail.html', {
        'commande': commande,
        'lignes':   lignes,
        'produits': produits,
    })


@login_required(login_url='login')
@require_POST
def categorie_create_ajax(request):
    nom  = request.POST.get('nom', '').strip()
    type_ = request.POST.get('type', 'medicament')
    if not nom:
        return JsonResponse({'error': 'Le nom est obligatoire.'}, status=400)
    cat, created = CategorieStock.objects.get_or_create(nom=nom, type=type_)
    return JsonResponse({'id': cat.pk, 'nom': cat.nom, 'type': cat.type, 'created': created})


@login_required(login_url='login')
def fournisseur_create(request):
    errors = {}
    if request.method == 'POST':
        nom       = request.POST.get('nom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        email     = request.POST.get('email', '').strip()
        adresse   = request.POST.get('adresse', '').strip()
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not telephone:
            errors['telephone'] = 'Le téléphone est obligatoire.'
        if not errors:
            f = Fournisseur.objects.create(
                nom=nom, telephone=telephone, email=email, adresse=adresse
            )
            messages.success(request, f'Fournisseur « {f.nom} » créé (code : {f.code}).')
            return redirect('stock_fournisseurs')
    return render(request, 'stock/fournisseurs/form.html', {
        'mode': 'create', 'errors': errors,
        'post': request.POST if request.method == 'POST' else None,
    })


@login_required(login_url='login')
def fournisseur_edit(request, pk):
    fournisseur = get_object_or_404(Fournisseur, pk=pk)
    errors = {}
    if request.method == 'POST':
        nom       = request.POST.get('nom', '').strip()
        telephone = request.POST.get('telephone', '').strip()
        email     = request.POST.get('email', '').strip()
        adresse   = request.POST.get('adresse', '').strip()
        actif     = request.POST.get('actif') == 'on'
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not telephone:
            errors['telephone'] = 'Le téléphone est obligatoire.'
        if not errors:
            fournisseur.nom       = nom
            fournisseur.telephone = telephone
            fournisseur.email     = email
            fournisseur.adresse   = adresse
            fournisseur.actif     = actif
            fournisseur.save()
            messages.success(request, f'Fournisseur « {fournisseur.nom} » mis à jour.')
            return redirect('stock_fournisseurs')
    return render(request, 'stock/fournisseurs/form.html', {
        'mode': 'edit', 'fournisseur': fournisseur, 'errors': errors,
    })


@login_required(login_url='login')
def fournisseurs_list(request):
    qs = Fournisseur.objects.filter(actif=True).order_by('nom')
    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/fournisseurs/list.html', {
        'fournisseurs': page_obj,
        'page_obj':     page_obj,
        'q':            q,
    })


# ---------------------------------------------------------------------------
# Réception commande
# ---------------------------------------------------------------------------

@login_required(login_url='login')
@require_POST
def commande_envoyer(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut != 'brouillon':
        messages.error(request, 'Seule une commande en brouillon peut être envoyée.')
        return redirect('stock_commande_detail', pk=pk)
    if not commande.lignes.exists():
        messages.error(request, 'Ajoutez au moins un produit avant d\'envoyer la commande.')
        return redirect('stock_commande_detail', pk=pk)
    commande.statut = 'envoye'
    commande.save(update_fields=['statut'])
    messages.success(request, f'Commande {commande.numero} envoyée au fournisseur {commande.fournisseur.nom}.')
    return redirect('stock_commande_detail', pk=pk)


@login_required(login_url='login')
def commande_modifier(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut != 'brouillon':
        messages.error(request, 'Seule une commande en brouillon peut être modifiée.')
        return redirect('stock_commande_detail', pk=pk)
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    errors = {}
    if request.method == 'POST':
        frn_pk = request.POST.get('fournisseur', '')
        fournisseur = Fournisseur.objects.filter(pk=frn_pk).first()
        if not fournisseur:
            errors['fournisseur'] = 'Sélectionnez un fournisseur.'
        if not errors:
            commande.fournisseur = fournisseur
            commande.notes = request.POST.get('notes', '').strip()
            date_liv = request.POST.get('date_livraison_prevue', '')
            commande.date_livraison_prevue = date_liv if date_liv else None
            commande.save(update_fields=['fournisseur', 'notes', 'date_livraison_prevue'])
            messages.success(request, f'Commande {commande.numero} mise à jour.')
            return redirect('stock_commande_detail', pk=pk)
    return render(request, 'stock/commandes/modifier.html', {
        'commande':    commande,
        'fournisseurs': fournisseurs,
        'errors':      errors,
    })


@login_required(login_url='login')
@require_POST
def commande_receptionner(request, pk):
    commande = get_object_or_404(CommandeStock, pk=pk)
    if commande.statut not in ('envoye', 'partiel'):
        messages.error(request, 'Cette commande ne peut pas être réceptionnée.')
        return redirect('stock_commande_detail', pk=pk)

    lignes = commande.lignes.select_related('produit').all()
    tout_recu = True

    for ligne in lignes:
        key = f'recu_{ligne.pk}'
        try:
            qte_recue = float(request.POST.get(key, 0) or 0)
        except ValueError:
            qte_recue = 0
        if qte_recue <= 0:
            continue

        # Mettre à jour la ligne
        from decimal import Decimal
        ligne.quantite_recue = min(ligne.quantite_recue + Decimal(str(qte_recue)), ligne.quantite_commandee)
        ligne.save(update_fields=['quantite_recue'])

        # Créer un lot
        num_lot = request.POST.get(f'lot_{ligne.pk}', '').strip() or f'LOT-{commande.numero}'
        date_peremption = request.POST.get(f'peremption_{ligne.pk}', '') or None
        lot = LotProduit.objects.create(
            produit=ligne.produit, numero_lot=num_lot,
            quantite_initiale=qte_recue, quantite_actuelle=qte_recue,
            fournisseur=commande.fournisseur, date_reception=timezone.now().date(),
            prix_achat_lot=ligne.prix_unitaire,
            date_peremption=date_peremption if date_peremption else None,
        )

        # Mouvement de stock
        stock_avant = float(ligne.produit.stock_actuel)
        stock_apres = stock_avant + qte_recue
        MouvementStock.objects.create(
            produit=ligne.produit, lot=lot, type='entree', motif='achat',
            quantite=qte_recue, stock_avant=stock_avant, stock_apres=stock_apres,
            reference=commande.numero, cree_par=request.user,
        )
        ligne.produit.stock_actuel = stock_apres
        ligne.produit.save(update_fields=['stock_actuel'])

        if ligne.quantite_recue < ligne.quantite_commandee:
            tout_recu = False

    # Mettre à jour le statut commande
    commande.statut = 'recu' if tout_recu else 'partiel'
    commande.date_reception = timezone.now().date()
    commande.save(update_fields=['statut', 'date_reception'])

    messages.success(request, f'Réception enregistrée pour la commande {commande.numero}.')
    return redirect('stock_commande_detail', pk=pk)


# ---------------------------------------------------------------------------
# Inventaire
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def inventaire_list(request):
    qs = Inventaire.objects.order_by('-date_creation')
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/inventaire/list.html', {
        'inventaires': page_obj,
        'page_obj':    page_obj,
    })


@login_required(login_url='login')
def inventaire_create(request):
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    if request.method == 'POST':
        inv = Inventaire.objects.create(
            notes=request.POST.get('notes', '').strip(),
            cree_par=request.user,
        )
        for p in produits:
            val = request.POST.get(f'reel_{p.pk}', '')
            if val != '':
                try:
                    stock_reel = float(val)
                except ValueError:
                    stock_reel = float(p.stock_actuel)
                peremption = request.POST.get(f'peremption_{p.pk}', '').strip() or None
                LigneInventaire.objects.create(
                    inventaire=inv, produit=p,
                    stock_theorique=p.stock_actuel,
                    stock_reel=stock_reel,
                    date_peremption=peremption,
                )
        messages.success(request, f'Inventaire {inv.numero} créé.')
        return redirect('stock_inventaire_detail', pk=inv.pk)
    return render(request, 'stock/inventaire/form.html', {'produits': produits})


@login_required(login_url='login')
def inventaire_detail(request, pk):
    inv = get_object_or_404(Inventaire, pk=pk)
    lignes = inv.lignes.select_related('produit').all()

    if request.method == 'POST' and request.POST.get('action') == 'valider' and inv.statut == 'brouillon':
        for ligne in lignes:
            if ligne.ecart != 0:
                type_mvt = 'entree' if ligne.ecart > 0 else 'ajustement'
                stock_avant = float(ligne.produit.stock_actuel)
                stock_apres = float(ligne.stock_reel)
                MouvementStock.objects.create(
                    produit=ligne.produit, type=type_mvt, motif='inventaire',
                    quantite=abs(float(ligne.ecart)),
                    stock_avant=stock_avant, stock_apres=stock_apres,
                    reference=inv.numero, cree_par=request.user,
                )
                ligne.produit.stock_actuel = stock_apres
                ligne.produit.save(update_fields=['stock_actuel'])

            # Mettre à jour la date de péremption sur le lot principal si renseignée
            if ligne.date_peremption:
                lot = ligne.produit.lots.order_by('-date_reception').first()
                if lot:
                    lot.date_peremption = ligne.date_peremption
                    lot.save(update_fields=['date_peremption'])
        inv.statut = 'valide'
        inv.date_validation = timezone.now()
        inv.save(update_fields=['statut', 'date_validation'])
        messages.success(request, f'Inventaire {inv.numero} validé. Les stocks ont été mis à jour.')
        return redirect('stock_inventaire_detail', pk=pk)

    lignes_list = list(lignes)
    stats_ecarts = {
        'excedents': sum(1 for l in lignes_list if float(l.ecart) > 0),
        'manques':   sum(1 for l in lignes_list if float(l.ecart) < 0),
        'neutres':   sum(1 for l in lignes_list if float(l.ecart) == 0),
        'total':     len(lignes_list),
    }

    return render(request, 'stock/inventaire/detail.html', {
        'inv':          inv,
        'lignes':       lignes_list,
        'stats_ecarts': stats_ecarts,
    })


# ---------------------------------------------------------------------------
# Péremptions
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def peremptions_list(request):
    today = timezone.now().date()
    filtre = request.GET.get('filtre', '90j')

    if filtre == 'expires':
        lots = LotProduit.objects.filter(date_peremption__lt=today, quantite_actuelle__gt=0)
    elif filtre == '30j':
        lots = LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=30), date_peremption__gte=today, quantite_actuelle__gt=0)
    elif filtre == '60j':
        lots = LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=60), date_peremption__gte=today, quantite_actuelle__gt=0)
    else:
        lots = LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=90), quantite_actuelle__gt=0)

    lots = lots.select_related('produit', 'fournisseur').order_by('date_peremption')
    stats = {
        'expires': LotProduit.objects.filter(date_peremption__lt=today, quantite_actuelle__gt=0).count(),
        'j30':     LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=30), date_peremption__gte=today, quantite_actuelle__gt=0).count(),
        'j60':     LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=60), date_peremption__gte=today, quantite_actuelle__gt=0).count(),
        'j90':     LotProduit.objects.filter(date_peremption__lte=today + timezone.timedelta(days=90), quantite_actuelle__gt=0).count(),
    }
    paginator = Paginator(lots, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/peremptions/list.html', {
        'lots': page_obj, 'page_obj': page_obj,
        'stats': stats, 'filtre': filtre, 'today': today,
    })


# ---------------------------------------------------------------------------
# Valorisation
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def valorisation(request):
    produits = Produit.objects.filter(actif=True, stock_actuel__gt=0).select_related('categorie')

    valeur_totale = sum(float(p.stock_actuel) * float(p.prix_achat) for p in produits)

    par_type = {
        'medicament':  {'valeur': 0, 'nb': 0},
        'consommable': {'valeur': 0, 'nb': 0},
        'equipement':  {'valeur': 0, 'nb': 0},
    }
    for p in produits:
        par_type[p.type]['valeur'] += float(p.stock_actuel) * float(p.prix_achat)
        par_type[p.type]['nb'] += 1

    paginator = Paginator(produits.order_by('-stock_actuel'), 30)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/valorisation.html', {
        'produits':     page_obj,
        'page_obj':     page_obj,
        'valeur_totale': valeur_totale,
        'par_type':     par_type,
    })


# ---------------------------------------------------------------------------
# Rapports consommation
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rapports_consommation(request):
    import datetime
    from collections import defaultdict
    today = timezone.now().date()
    mois  = int(request.GET.get('mois', today.month))
    annee = int(request.GET.get('annee', today.year))
    type_filtre = request.GET.get('type', '')

    # Livraisons = sorties vers pharmacies (type livraison)
    mouvements = MouvementStock.objects.filter(
        type='livraison',
        date__month=mois, date__year=annee,
    ).select_related('produit', 'lot')

    if type_filtre:
        mouvements = mouvements.filter(produit__type=type_filtre)

    # Agréger par produit (quantité + valorisation)
    consommation = defaultdict(lambda: {'produit': None, 'total': 0.0, 'nb_livraisons': 0, 'valeur': 0.0})
    for mv in mouvements:
        k = mv.produit.pk
        consommation[k]['produit']       = mv.produit
        consommation[k]['total']         += float(mv.quantite)
        consommation[k]['nb_livraisons'] += 1
        prix = float(mv.lot.prix_achat_lot) if mv.lot_id else float(mv.produit.prix_achat)
        consommation[k]['valeur']        += float(mv.quantite) * prix

    lignes = sorted(consommation.values(), key=lambda x: x['total'], reverse=True)

    total_quantite = sum(l['total'] for l in lignes)
    total_valeur   = sum(l['valeur'] for l in lignes)

    # Mois nav
    d_courante = datetime.date(annee, mois, 1)
    if mois == 1:
        prev_mois, prev_annee = 12, annee - 1
    else:
        prev_mois, prev_annee = mois - 1, annee
    if mois == 12:
        next_mois, next_annee = 1, annee + 1
    else:
        next_mois, next_annee = mois + 1, annee

    MOIS_NOMS = ['', 'Janvier','Février','Mars','Avril','Mai','Juin',
                 'Juillet','Août','Septembre','Octobre','Novembre','Décembre']
    annees_dispo = list(range(today.year, today.year - 3, -1))

    return render(request, 'stock/rapports/consommation.html', {
        'lignes':         lignes,
        'mois':           mois,
        'annee':          annee,
        'mois_nom':       MOIS_NOMS[mois],
        'mois_noms':      MOIS_NOMS,
        'annees_dispo':   annees_dispo,
        'type_filtre':    type_filtre,
        'total_quantite': total_quantite,
        'total_valeur':   total_valeur,
        'prev_mois':      prev_mois,
        'prev_annee':     prev_annee,
        'next_mois':      next_mois,
        'next_annee':     next_annee,
        'today':          today,
    })


@login_required(login_url='login')
def rapports_dotations(request):
    import json as _json, datetime
    from collections import defaultdict
    today   = timezone.now().date()
    annee   = int(request.GET.get('annee', today.year))
    pharmacie_filtre = request.GET.get('pharmacie', '')

    MOIS_NOMS = ['','Janv','Févr','Mars','Avr','Mai','Juin','Juil','Août','Sept','Oct','Nov','Déc']
    PHARMACIES_LABELS = {'wale_toumbokro': 'Walé Toumbokro', 'wale_yamoussoukro': 'Walé Yamoussoukro'}

    # ── 1. Tendance mensuelle des demandes par pharmacie ──
    tendance = {}
    for code, label in PHARMACIES_LABELS.items():
        tendance[code] = {'label': label, 'data': [0]*12}
    demandes = DemandePharmacie.objects.filter(date_demande__year=annee)
    if pharmacie_filtre:
        demandes = demandes.filter(pharmacie=pharmacie_filtre)
    for d in demandes:
        m = d.date_demande.month - 1
        if d.pharmacie in tendance:
            tendance[d.pharmacie]['data'][m] += 1

    chart_tendance = {
        'labels': MOIS_NOMS[1:],
        'datasets': [
            {'label': v['label'], 'data': v['data'],
             'borderColor': '#1a237e' if k == 'wale_yamoussoukro' else '#ef6c00',
             'backgroundColor': 'rgba(26,35,126,.1)' if k == 'wale_yamoussoukro' else 'rgba(239,108,0,.08)',
             'tension': 0.3, 'fill': True}
            for k, v in tendance.items()
        ]
    }

    # ── 2. Taux approbation par pharmacie ──
    taux = {}
    for code, label in PHARMACIES_LABELS.items():
        qs = DemandePharmacie.objects.filter(pharmacie=code, date_demande__year=annee)
        total     = qs.count()
        approuvee = qs.filter(statut__in=['approuvee', 'partielle', 'en_livraison']).count()
        taux[code] = {
            'label':     label,
            'total':     total,
            'approuvee': approuvee,
            'taux':      round(approuvee / total * 100) if total else 0,
        }

    # ── 3. Top 10 produits les plus demandés ──
    qs_lignes = LigneDemande.objects.filter(
        demande__date_demande__year=annee
    ).select_related('produit', 'demande')
    if pharmacie_filtre:
        qs_lignes = qs_lignes.filter(demande__pharmacie=pharmacie_filtre)

    prod_stats = defaultdict(lambda: {'produit': None, 'qte_demandee': 0.0, 'qte_approuvee': 0.0, 'nb': 0})
    for ligne in qs_lignes:
        if not ligne.produit:
            continue
        k = ligne.produit.pk
        prod_stats[k]['produit']      = ligne.produit
        prod_stats[k]['qte_demandee'] += float(ligne.quantite_demandee)
        prod_stats[k]['qte_approuvee'] += float(ligne.quantite_approuvee)
        prod_stats[k]['nb']           += 1

    top_produits = sorted(prod_stats.values(), key=lambda x: x['qte_demandee'], reverse=True)[:10]

    chart_top = {
        'labels':    [t['produit'].nom[:20] for t in top_produits],
        'demandee':  [t['qte_demandee']     for t in top_produits],
        'approuvee': [t['qte_approuvee']    for t in top_produits],
    }

    # ── 4. Comparaison volumes entre pharmacies ──
    comp = {}
    for code, label in PHARMACIES_LABELS.items():
        qte = sum(
            float(l.quantite_demandee)
            for l in LigneDemande.objects.filter(
                demande__pharmacie=code, demande__date_demande__year=annee
            )
        )
        comp[code] = {'label': label, 'qte': qte}

    chart_comp = {
        'labels': [v['label'] for v in comp.values()],
        'data':   [v['qte']   for v in comp.values()],
        'colors': ['#1a237e', '#ef6c00'],
    }

    # ── 5. Stats globales ──
    stats = {
        'total_demandes': DemandePharmacie.objects.filter(date_demande__year=annee).count(),
        'en_attente':     DemandePharmacie.objects.filter(date_demande__year=annee, statut='en_attente').count(),
        'approuvees':     DemandePharmacie.objects.filter(date_demande__year=annee, statut__in=['approuvee','en_livraison']).count(),
        'refusees':       DemandePharmacie.objects.filter(date_demande__year=annee, statut='refusee').count(),
    }

    annees_dispo = list(range(today.year, today.year - 3, -1))

    return render(request, 'stock/rapports/dotations.html', {
        'annee':           annee,
        'annees_dispo':    annees_dispo,
        'pharmacie_filtre': pharmacie_filtre,
        'pharmacies':      PHARMACIES_LABELS,
        'stats':           stats,
        'taux':            taux,
        'top_produits':    top_produits,
        'chart_tendance':  chart_tendance,
        'chart_top':       chart_top,
        'chart_comp':      chart_comp,
        'today':           today,
    })


# ---------------------------------------------------------------------------
@login_required(login_url='login')
def rapports_besoins(request):
    """Rapport besoins mensuels — style fiche commande pharmacie."""
    type_filtre = request.GET.get('type', '')
    today = timezone.now().date()

    qs = Produit.objects.filter(actif=True).order_by('type', 'nom')
    if type_filtre:
        qs = qs.filter(type=type_filtre)

    # Calcul des indicateurs pour chaque produit
    produits_data = []
    for p in qs:
        cmm = p.cmm
        stock = float(p.stock_actuel)
        couverture = p.couverture_jours
        qte_cmd = p.qte_a_commander
        produits_data.append({
            'produit':    p,
            'cmm':        cmm,
            'stock':      stock,
            'couverture': couverture,
            'qte_cmd':    qte_cmd,
            'en_besoin':  qte_cmd > 0,
        })

    # Stats globales
    nb_rupture  = sum(1 for d in produits_data if d['stock'] <= 0)
    nb_critique = sum(1 for d in produits_data if 0 < d['stock'] <= float(d['produit'].stock_alerte))
    nb_besoin   = sum(1 for d in produits_data if d['qte_cmd'] > 0)

    ctx = {
        'produits_data': produits_data,
        'type_filtre':   type_filtre,
        'today':         today,
        'stats': {'rupture': nb_rupture, 'critique': nb_critique, 'besoin': nb_besoin, 'total': len(produits_data)},
    }
    return render(request, 'stock/rapports/besoins.html', ctx)


@login_required(login_url='login')
def rapports_besoins_print(request):
    """Version imprimable / PDF de la fiche de besoins."""
    type_filtre = request.GET.get('type', '')
    today = timezone.now().date()
    qs = Produit.objects.filter(actif=True).order_by('type', 'nom')
    if type_filtre:
        qs = qs.filter(type=type_filtre)
    produits_data = []
    for p in qs:
        produits_data.append({
            'produit':    p,
            'cmm':        p.cmm,
            'stock':      float(p.stock_actuel),
            'couverture': p.couverture_jours,
            'qte_cmd':    p.qte_a_commander,
        })
    return render(request, 'stock/rapports/besoins_print.html', {
        'produits_data': produits_data,
        'type_filtre':   type_filtre,
        'today':         today,
        'type_label': {'medicament': 'Médicaments', 'consommable': 'Consommables', 'equipement': 'Équipements'}.get(type_filtre, 'Tous les produits'),
    })


@login_required(login_url='login')
def rapports_indicateurs(request):
    """Tableau de bord des indicateurs de performance du stock."""
    import json as _json
    today = timezone.now().date()

    produits = list(Produit.objects.filter(actif=True))

    # Taux de service = demandes satisfaites / demandes totales
    total_demandee  = sum(float(l.quantite_demandee)  for l in LigneDemande.objects.all())
    total_approuvee = sum(float(l.quantite_approuvee) for l in LigneDemande.objects.all())
    taux_service  = round(total_approuvee / total_demandee * 100, 1) if total_demandee > 0 else 0
    taux_rupture  = round((total_demandee - total_approuvee) / total_demandee * 100, 1) if total_demandee > 0 else 0

    # Valeur du stock
    valeur_stock = sum(float(p.stock_actuel) * float(p.prix_achat) for p in produits)

    # Taux de rotation = livraisons / stock moyen
    from django.db.models import Sum
    total_livraisons = float(MouvementStock.objects.filter(type='livraison').aggregate(
        t=Sum('quantite'))['t'] or 0)
    stock_total = sum(float(p.stock_actuel) for p in produits)
    taux_rotation = round(total_livraisons / stock_total, 2) if stock_total > 0 else 0

    # Couverture moyenne
    couvertures = [p.couverture_jours for p in produits if p.couverture_jours is not None]
    couverture_moy = round(sum(couvertures) / len(couvertures)) if couvertures else 0

    # Top 5 produits avec couverture critique (< 30 jours)
    critiques = sorted(
        [{'produit': p, 'couverture': p.couverture_jours, 'cmm': p.cmm}
         for p in produits if p.couverture_jours is not None and p.couverture_jours < 30],
        key=lambda x: x['couverture']
    )[:10]

    # Top 5 produits à commander
    a_commander = sorted(
        [{'produit': p, 'qte': p.qte_a_commander, 'cmm': p.cmm}
         for p in produits if p.qte_a_commander > 0],
        key=lambda x: x['qte'], reverse=True
    )[:10]

    # Prévision 3 mois (Feature 3)
    previsions = []
    for item in a_commander:
        p   = item['produit']
        cmm = item['cmm'] or 0
        s0  = float(p.stock_actuel)
        previsions.append({
            'produit':         p,
            'cmm':             cmm,
            'stock_actuel':    s0,
            'stock_m1':        max(0, s0 - cmm),
            'stock_m2':        max(0, s0 - 2 * cmm),
            'stock_m3':        max(0, s0 - 3 * cmm),
            'qte_a_commander': item['qte'],
        })

    chart_service_data = {
        'labels': ['Taux de service', 'Taux de rupture'],
        'data': [float(taux_service), float(taux_rupture)],
        'colors': ['#0d7a4c', '#e84545'],
    }
    chart_critiques_data = {
        'labels': [c['produit'].nom[:22] for c in critiques],
        'data': [int(c['couverture']) for c in critiques],
    }
    chart_commander_data = {
        'labels': [c['produit'].nom[:22] for c in a_commander],
        'data': [int(c['qte']) for c in a_commander],
    }

    return render(request, 'stock/rapports/indicateurs.html', {
        'today':           today,
        'taux_service':    taux_service,
        'taux_rupture':    taux_rupture,
        'taux_rotation':   taux_rotation,
        'couverture_moy':  couverture_moy,
        'valeur_stock':    valeur_stock,
        'critiques':       critiques,
        'a_commander':     a_commander,
        'previsions':      previsions,
        'total_produits':  len(produits),
        'chart_service':   chart_service_data,
        'chart_critiques': chart_critiques_data,
        'chart_commander': chart_commander_data,
    })


# ---------------------------------------------------------------------------
# Rapport de péremptions (Feature 1)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rapports_peremptions(request):
    from collections import defaultdict
    today = timezone.now().date()
    mois  = int(request.GET.get('mois', today.month))
    annee = int(request.GET.get('annee', today.year))

    mouvements = MouvementStock.objects.filter(
        type='peremption',
        date__month=mois, date__year=annee,
    ).select_related('produit', 'lot', 'cree_par').order_by('-date')

    total_quantite = sum(float(mv.quantite) for mv in mouvements)
    total_valeur   = sum(
        float(mv.quantite) * float(mv.lot.prix_achat_lot if mv.lot_id else mv.produit.prix_achat)
        for mv in mouvements
    )

    MOIS_NOMS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    annees_dispo = list(range(today.year, today.year - 3, -1))
    prev_mois, prev_annee = (12, annee - 1) if mois == 1 else (mois - 1, annee)
    next_mois, next_annee = (1, annee + 1) if mois == 12 else (mois + 1, annee)

    return render(request, 'stock/rapports/peremptions.html', {
        'mouvements':     mouvements,
        'mois':           mois, 'annee': annee, 'mois_nom': MOIS_NOMS[mois],
        'annees_dispo':   annees_dispo,
        'total_quantite': total_quantite, 'total_valeur': total_valeur,
        'prev_mois': prev_mois, 'prev_annee': prev_annee,
        'next_mois': next_mois, 'next_annee': next_annee,
        'today': today,
    })


# ---------------------------------------------------------------------------
# Saisie des éliminations / destructions (Feature 2)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def elimination_create(request):
    today = timezone.now().date()

    if request.method == 'POST':
        nb = 0
        notes_global = request.POST.get('notes', '').strip()
        for key, val in request.POST.items():
            if not key.startswith('qte_'):
                continue
            lot_pk = key[4:]
            try:
                qte = float(val)
            except (ValueError, TypeError):
                continue
            if qte <= 0:
                continue
            try:
                lot = LotProduit.objects.select_related('produit').get(pk=lot_pk)
            except LotProduit.DoesNotExist:
                continue
            qte = min(qte, float(lot.quantite_actuelle))
            if qte <= 0:
                continue
            sv = float(lot.produit.stock_actuel)
            sa = max(0, sv - qte)
            MouvementStock.objects.create(
                produit=lot.produit, lot=lot,
                type='peremption', motif='peremption',
                quantite=qte, stock_avant=sv, stock_apres=sa,
                notes=notes_global, cree_par=request.user,
            )
            lot.quantite_actuelle = max(0, float(lot.quantite_actuelle) - qte)
            lot.save(update_fields=['quantite_actuelle'])
            lot.produit.stock_actuel = sa
            lot.produit.save(update_fields=['stock_actuel'])
            nb += 1
        if nb:
            messages.success(request, f'{nb} lot(s) éliminé(s) et enregistré(s).')
        return redirect('stock_peremptions')

    # GET : lots périmés ou expirant dans 30 jours
    lots = LotProduit.objects.filter(
        quantite_actuelle__gt=0
    ).filter(
        Q(date_peremption__lt=today) | Q(date_peremption__lte=today + timezone.timedelta(days=30))
    ).select_related('produit', 'fournisseur').order_by('date_peremption')

    return render(request, 'stock/peremptions/eliminer.html', {
        'lots': lots, 'today': today,
    })


# ---------------------------------------------------------------------------
# Génération automatique de fiche de besoins (Feature 4)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
@require_POST
def besoins_generer_auto(request):
    import datetime as _dt
    today = timezone.now().date()
    debut = today.replace(day=1)
    if today.month == 12:
        fin = today.replace(day=31)
    else:
        fin = today.replace(month=today.month + 1, day=1) - _dt.timedelta(days=1)

    produits_all = list(Produit.objects.filter(actif=True))
    a_commander  = [p for p in produits_all if p.qte_a_commander > 0]

    if not a_commander:
        messages.warning(request, 'Aucun produit à commander actuellement.')
        return redirect('stock_rapports_indicateurs')

    fiche = FicheBesoins.objects.create(
        periode_debut=debut, periode_fin=fin,
        cree_par=request.user,
        notes='Généré automatiquement depuis les indicateurs de stock.',
    )
    for p in a_commander:
        LigneFicheBesoins.objects.create(
            fiche=fiche, produit=p,
            stock_initial=p.stock_actuel,
            cmm=p.cmm,
            qte_commander=p.qte_a_commander,
        )
    messages.success(request, f'Fiche {fiche.numero} créée avec {len(a_commander)} produit(s).')
    return redirect('stock_fiche_detail', pk=fiche.pk)


# ---------------------------------------------------------------------------
# Bilan mensuel (Feature 5)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rapports_bilan_mensuel(request):
    from collections import defaultdict
    today = timezone.now().date()
    mois  = int(request.GET.get('mois', today.month))
    annee = int(request.GET.get('annee', today.year))
    MOIS_NOMS = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    annees_dispo = list(range(today.year, today.year - 3, -1))
    prev_mois, prev_annee = (12, annee - 1) if mois == 1 else (mois - 1, annee)
    next_mois, next_annee = (1, annee + 1) if mois == 12 else (mois + 1, annee)

    mvts = list(MouvementStock.objects.filter(
        date__month=mois, date__year=annee,
    ).select_related('produit', 'lot').order_by('-date'))

    def _val(mv):
        prix = float(mv.lot.prix_achat_lot) if mv.lot_id else float(mv.produit.prix_achat)
        return float(mv.quantite) * prix

    entrees     = [mv for mv in mvts if mv.type == 'entree']
    sorties     = [mv for mv in mvts if mv.type == 'livraison']
    peremptes   = [mv for mv in mvts if mv.type == 'peremption']
    ajustements = [mv for mv in mvts if mv.type == 'ajustement']
    retours     = [mv for mv in mvts if mv.type == 'retour']

    conso = defaultdict(float)
    for mv in sorties:
        conso[mv.produit.nom[:30]] += float(mv.quantite)
    top_sorties = sorted(conso.items(), key=lambda x: x[1], reverse=True)[:5]

    return render(request, 'stock/rapports/bilan.html', {
        'mois': mois, 'annee': annee, 'mois_nom': MOIS_NOMS[mois],
        'annees_dispo': annees_dispo,
        'prev_mois': prev_mois, 'prev_annee': prev_annee,
        'next_mois': next_mois, 'next_annee': next_annee,
        'today': today,
        'entrees': entrees, 'sorties': sorties,
        'peremptes': peremptes, 'ajustements': ajustements, 'retours': retours,
        'qte_entrees':   sum(float(mv.quantite) for mv in entrees),
        'qte_sorties':   sum(float(mv.quantite) for mv in sorties),
        'qte_peremptes': sum(float(mv.quantite) for mv in peremptes),
        'val_entrees':   round(sum(_val(mv) for mv in entrees)),
        'val_sorties':   round(sum(_val(mv) for mv in sorties)),
        'val_peremptes': round(sum(_val(mv) for mv in peremptes)),
        'top_sorties':   top_sorties,
        'nb_ruptures':   Produit.objects.filter(actif=True, stock_actuel__lte=0).count(),
        'nb_alertes':    Produit.objects.filter(actif=True, stock_actuel__gt=0, stock_actuel__lte=F('stock_alerte')).count(),
    })


# ---------------------------------------------------------------------------
# Comparatif fournisseurs / historique des prix (Feature 6)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def rapports_fournisseurs_prix(request):
    from collections import defaultdict
    fournisseur_pk = request.GET.get('fournisseur', '')
    produit_pk     = request.GET.get('produit', '')

    lots_qs = LotProduit.objects.filter(
        prix_achat_lot__gt=0,
    ).select_related('produit', 'fournisseur').order_by('produit__nom', 'date_reception')

    if fournisseur_pk:
        lots_qs = lots_qs.filter(fournisseur_id=fournisseur_pk)
    if produit_pk:
        lots_qs = lots_qs.filter(produit_id=produit_pk)

    par_produit = defaultdict(list)
    for lot in lots_qs:
        par_produit[lot.produit].append(lot)

    produits_data = []
    for prod, lots in par_produit.items():
        prices = [float(l.prix_achat_lot) for l in lots]
        pmin, pmax = min(prices), max(prices)
        produits_data.append({
            'produit':   prod,
            'lots':      lots,
            'prix_min':  pmin,
            'prix_max':  pmax,
            'prix_moy':  round(sum(prices) / len(prices)),
            'variation': round((pmax - pmin) / pmin * 100, 1) if pmin > 0 else 0,
        })
    produits_data.sort(key=lambda x: x['variation'], reverse=True)

    from achats.models import Fournisseur as FournisseurAchat
    fournisseurs = FournisseurAchat.objects.filter(actif=True).order_by('nom')
    produits_avec_lots = Produit.objects.filter(
        lots__prix_achat_lot__gt=0, actif=True
    ).distinct().order_by('nom')

    return render(request, 'stock/rapports/fournisseurs_prix.html', {
        'produits_data':      produits_data,
        'fournisseurs':       fournisseurs,
        'produits_avec_lots': produits_avec_lots,
        'fournisseur_pk':     fournisseur_pk,
        'produit_pk':         produit_pk,
        'today':              timezone.now().date(),
    })


# ---------------------------------------------------------------------------
# Retours pharmacie → stock central (Feature 8)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def retour_create(request):
    if request.method == 'POST':
        produit_pk = request.POST.get('produit', '')
        lot_pk     = request.POST.get('lot', '')
        pharmacie  = request.POST.get('pharmacie', '')
        notes      = request.POST.get('notes', '').strip()
        try:
            qte = float(request.POST.get('quantite', 0) or 0)
        except ValueError:
            qte = 0

        if not produit_pk or qte <= 0:
            messages.error(request, 'Produit et quantité requis.')
            return redirect('stock_retour_create')

        produit = get_object_or_404(Produit, pk=produit_pk)
        lot = LotProduit.objects.filter(pk=lot_pk, produit=produit).first() if lot_pk else None

        sv = float(produit.stock_actuel)
        sa = sv + qte
        MouvementStock.objects.create(
            produit=produit, lot=lot,
            type='retour', motif='retour',
            pharmacie=pharmacie, quantite=qte,
            stock_avant=sv, stock_apres=sa,
            notes=notes, cree_par=request.user,
        )
        produit.stock_actuel = sa
        produit.save(update_fields=['stock_actuel'])
        if lot:
            lot.quantite_actuelle = float(lot.quantite_actuelle) + qte
            lot.save(update_fields=['quantite_actuelle'])

        messages.success(request, f'Retour de {qte:.0f} {produit.unite_mesure.code if produit.unite_mesure else "unité(s)"} enregistré pour « {produit.nom} ».')
        return redirect('stock_mouvements')

    produits  = Produit.objects.filter(actif=True).order_by('nom')
    return render(request, 'stock/retours/form.html', {
        'produits':   produits,
        'pharmacies': PHARMACIES,
        'today':      timezone.now().date(),
    })


# ---------------------------------------------------------------------------
# Export Excel (CSV)
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def export_stock_excel(request):
    import csv
    from django.http import HttpResponse
    type_filtre = request.GET.get('type', '')
    qs = Produit.objects.filter(actif=True).select_related('categorie')
    if type_filtre:
        qs = qs.filter(type=type_filtre)
    qs = qs.order_by('type', 'nom')

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="stock.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Code', 'Nom', 'Type', 'Catégorie', 'Unité', 'Stock actuel', 'Seuil alerte', 'Prix achat', 'Prix vente', 'État'])
    for p in qs:
        etat = 'Rupture' if p.en_rupture else ('Alerte' if p.en_alerte else 'OK')
        writer.writerow([
            p.code, p.nom, p.get_type_display(),
            p.categorie.nom if p.categorie else '',
            p.unite_mesure.code if p.unite_mesure else '', p.stock_actuel, p.stock_alerte,
            p.prix_achat, p.prix_vente, etat,
        ])
    return response


# ---------------------------------------------------------------------------
# Transfert interne
# ---------------------------------------------------------------------------

@login_required(login_url='login')
def transfert_create(request):
    from .models import PHARMACIES
    produits = Produit.objects.filter(actif=True, stock_actuel__gt=0).order_by('nom')
    errors = {}
    if request.method == 'POST':
        produit_pk = request.POST.get('produit', '')
        pharmacie  = request.POST.get('pharmacie', '')
        notes      = request.POST.get('notes', '').strip()
        try:
            quantite = float(request.POST.get('quantite', 0) or 0)
        except ValueError:
            quantite = 0

        produit = Produit.objects.filter(pk=produit_pk).first()
        if not produit:
            errors['produit'] = 'Sélectionnez un produit.'
        if not pharmacie:
            errors['pharmacie'] = 'Sélectionnez la pharmacie destinataire.'
        if quantite <= 0:
            errors['quantite'] = 'La quantité doit être supérieure à 0.'
        elif produit and float(produit.stock_actuel) < quantite:
            errors['quantite'] = f'Stock insuffisant — disponible : {produit.stock_actuel} {produit.unite_mesure.code if produit.unite_mesure else "unité(s)"}.'

        if not errors:
            stock_avant = float(produit.stock_actuel)
            stock_apres = stock_avant - quantite
            pharma_label = dict(PHARMACIES).get(pharmacie, pharmacie)
            MouvementStock.objects.create(
                produit=produit, type='livraison', motif='livraison',
                pharmacie=pharmacie,
                quantite=quantite, stock_avant=stock_avant, stock_apres=stock_apres,
                notes=notes, cree_par=request.user,
                reference=f'Livraison → {pharma_label}',
            )
            produit.stock_actuel = stock_apres
            produit.save(update_fields=['stock_actuel'])
            messages.success(request, f'{quantite} {produit.unite_mesure.code if produit.unite_mesure else "unité(s)"} de « {produit.nom} » livrés à {pharma_label}.')
            return redirect('stock_mouvements')

    return render(request, 'stock/transfert/form.html', {
        'produits':   produits,
        'pharmacies': PHARMACIES,
        'errors':     errors,
        'post':       request.POST if request.method == 'POST' else None,
    })


# ── Dotation / Demandes pharmacies ─────────────────────────────────────────

@login_required(login_url='login')
def dotation_list(request):
    statut_filtre = request.GET.get('statut', 'en_attente')
    qs = DemandePharmacie.objects.order_by('-date_demande')
    if statut_filtre and statut_filtre != 'tous':
        qs = qs.filter(statut=statut_filtre)
    stats = {
        'en_attente': DemandePharmacie.objects.filter(statut='en_attente').count(),
        'approuvee':  DemandePharmacie.objects.filter(statut='approuvee').count(),
        'partielle':  DemandePharmacie.objects.filter(statut='partielle').count(),
        'refusee':    DemandePharmacie.objects.filter(statut='refusee').count(),
    }
    paginator = Paginator(qs, 20)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/dotation/list.html', {
        'demandes':      page_obj,
        'page_obj':      page_obj,
        'statut_filtre': statut_filtre,
        'stats':         stats,
        'pharmacies':    PHARMACIES,
    })


@login_required(login_url='login')
def dotation_detail(request, pk):
    demande = get_object_or_404(DemandePharmacie, pk=pk)
    lignes  = demande.lignes.select_related('produit').all()
    lignes_enrichies = []
    for l in lignes:
        stock = float(l.produit.stock_actuel)
        demandee = float(l.quantite_demandee)
        lignes_enrichies.append({
            'ligne':        l,
            'produit':      l.produit,
            'stock':        stock,
            'suffisant':    stock >= demandee,
            'pct_dispo':    min(100, int(stock / demandee * 100)) if demandee > 0 else 0,
        })
    return render(request, 'stock/dotation/detail.html', {
        'demande':          demande,
        'lignes_enrichies': lignes_enrichies,
    })


@login_required(login_url='login')
@require_POST
def dotation_valider(request, pk):
    demande = get_object_or_404(DemandePharmacie, pk=pk)
    if demande.statut != 'en_attente':
        messages.error(request, 'Cette demande a déjà été traitée.')
        return redirect('stock_dotation_detail', pk=pk)

    action = request.POST.get('action', 'approuver')

    if action == 'refuser':
        demande.statut          = 'refusee'
        demande.notes_stock     = request.POST.get('notes_stock', '').strip()
        demande.traite_par      = request.user
        demande.date_traitement = timezone.now()
        demande.save()
        messages.success(request, f'Demande {demande.numero} refusée.')
        return redirect('stock_dotation_list')

    lignes = demande.lignes.select_related('produit').all()
    tout_approuve = True
    for ligne in lignes:
        try:
            qte = float(request.POST.get(f'approuve_{ligne.pk}', 0) or 0)
        except ValueError:
            qte = 0
        qte = max(0, min(qte, float(ligne.quantite_demandee)))
        ligne.quantite_approuvee = qte
        ligne.save(update_fields=['quantite_approuvee'])
        if qte < float(ligne.quantite_demandee):
            tout_approuve = False
        if qte > 0:
            # FIFO: déduit depuis les lots les plus anciens en premier
            qte_restante = qte
            lots_dispo = LotProduit.objects.filter(
                produit=ligne.produit, quantite_actuelle__gt=0,
            ).order_by('date_reception')
            for lot in lots_dispo:
                if qte_restante <= 0:
                    break
                qte_lot = min(float(lot.quantite_actuelle), qte_restante)
                sv = float(ligne.produit.stock_actuel)
                sa = max(0, sv - qte_lot)
                MouvementStock.objects.create(
                    produit=ligne.produit, lot=lot,
                    type='livraison', motif='livraison',
                    pharmacie=demande.pharmacie, quantite=qte_lot,
                    stock_avant=sv, stock_apres=sa,
                    reference=demande.numero,
                    notes=f'Dotation {demande.get_pharmacie_display()} — Lot {lot.numero_lot}',
                    cree_par=request.user,
                )
                lot.quantite_actuelle = max(0, float(lot.quantite_actuelle) - qte_lot)
                lot.save(update_fields=['quantite_actuelle'])
                ligne.produit.stock_actuel = sa
                ligne.produit.save(update_fields=['stock_actuel'])
                qte_restante -= qte_lot
            # Fallback si aucun lot enregistré
            if qte_restante > 0:
                sv = float(ligne.produit.stock_actuel)
                sa = max(0, sv - qte_restante)
                MouvementStock.objects.create(
                    produit=ligne.produit, type='livraison', motif='livraison',
                    pharmacie=demande.pharmacie, quantite=qte_restante,
                    stock_avant=sv, stock_apres=sa,
                    reference=demande.numero,
                    notes=f'Dotation {demande.get_pharmacie_display()}',
                    cree_par=request.user,
                )
                ligne.produit.stock_actuel = sa
                ligne.produit.save(update_fields=['stock_actuel'])

    # Le stock passe en "en_livraison" — la pharmacie doit confirmer la réception
    demande.statut          = 'en_livraison'
    demande.notes_stock     = request.POST.get('notes_stock', '').strip()
    demande.traite_par      = request.user
    demande.date_traitement = timezone.now()
    demande.save()
    messages.success(request, f'Demande {demande.numero} traitée — {demande.get_statut_display()}.')
    return redirect('stock_dotation_list')


@login_required(login_url='login')
def dotation_creer(request):
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    errors = {}
    if request.method == 'POST':
        pharmacie = request.POST.get('pharmacie', '')
        notes     = request.POST.get('notes', '').strip()
        if not pharmacie:
            errors['pharmacie'] = 'Sélectionnez une pharmacie.'
        if not errors:
            demande = DemandePharmacie.objects.create(
                pharmacie=pharmacie, notes=notes, cree_par=request.user,
            )
            for p in produits:
                val = request.POST.get(f'qte_{p.pk}', '').strip()
                if val:
                    try:
                        qte = float(val)
                        if qte > 0:
                            LigneDemande.objects.create(
                                demande=demande, produit=p, quantite_demandee=qte,
                            )
                    except ValueError:
                        pass
            if demande.lignes.exists():
                messages.success(request, f'Demande {demande.numero} créée.')
                return redirect('stock_dotation_detail', pk=demande.pk)
            demande.delete()
            errors['lignes'] = 'Ajoutez au moins un produit avec une quantité.'
    return render(request, 'stock/dotation/form.html', {
        'produits': produits, 'pharmacies': PHARMACIES, 'errors': errors,
        'post': request.POST if request.method == 'POST' else None,
    })


# ── Fiches de besoins ──────────────────────────────────────────────────────

@login_required(login_url='login')
def fiche_list(request):
    fiches = FicheBesoins.objects.order_by('-date_creation')
    return render(request, 'stock/fiches/list.html', {'fiches': fiches})


@login_required(login_url='login')
def fiche_create(request):
    produits = Produit.objects.filter(actif=True).select_related('categorie').order_by('categorie__type', 'categorie__nom', 'nom')
    if request.method == 'POST':
        periode_debut = request.POST.get('periode_debut', '')
        periode_fin   = request.POST.get('periode_fin', '')
        notes = request.POST.get('notes', '').strip()

        lignes_data = [(p, request.POST.get(f'cmd_{p.pk}', '').strip()) for p in produits]
        lignes_data = [(p, q) for p, q in lignes_data if q]

        if not lignes_data:
            messages.error(request, "Sélectionnez au moins un produit et renseignez les quantités.")
        elif periode_debut and periode_fin:
            from decimal import Decimal

            fiche = FicheBesoins.objects.create(
                periode_debut=periode_debut, periode_fin=periode_fin,
                notes=notes, cree_par=request.user, statut='brouillon',
            )
            for p, qte_cmd in lignes_data:
                qte = Decimal(qte_cmd)
                LigneFicheBesoins.objects.create(
                    fiche=fiche, produit=p,
                    stock_initial=Decimal(str(p.stock_actuel or 0)),
                    cmm=Decimal(str(p.cmm or 0)),
                    qte_commander=qte, qte_accordee=qte,
                )

            messages.success(request, f'Fiche {fiche.numero} créée. Vérifiez et envoyez aux achats.')
            return redirect('stock_fiche_detail', pk=fiche.pk)

    categories = CategorieStock.objects.filter(actif=True).order_by('type', 'nom')
    return render(request, 'stock/fiches/form.html', {
        'mode': 'create', 'produits': produits,
        'categories': categories,
        'today': timezone.now().date(),
    })


@login_required(login_url='login')
def fiche_detail(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    lignes = fiche.lignes.select_related('produit__categorie').order_by('produit__categorie__type', 'produit__categorie__nom', 'produit__nom')
    return render(request, 'stock/fiches/detail.html', {
        'fiche': fiche, 'lignes': lignes,
    })


@login_required(login_url='login')
def fiche_edit(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    if fiche.statut not in ('brouillon',):
        messages.error(request, 'Seule une fiche en brouillon est modifiable.')
        return redirect('stock_fiche_detail', pk=pk)
    lignes = fiche.lignes.select_related('produit__categorie').order_by('produit__categorie__type', 'produit__categorie__nom', 'produit__nom')
    if request.method == 'POST':
        from decimal import Decimal
        for ligne in lignes:
            ligne.qte_commander = Decimal(request.POST.get(f'cmd_{ligne.pk}', 0) or 0)
            ligne.notes         = request.POST.get(f'notes_{ligne.pk}', '').strip()
            ligne.save()
        fiche.notes = request.POST.get('notes', '').strip()
        fiche.save(update_fields=['notes'])
        messages.success(request, 'Fiche mise à jour.')
        return redirect('stock_fiche_detail', pk=pk)
    return render(request, 'stock/fiches/edit.html', {
        'fiche': fiche, 'lignes': lignes,
    })


@login_required(login_url='login')
@require_POST
def fiche_soumettre(request, pk):
    fiche = get_object_or_404(FicheBesoins, pk=pk)
    if fiche.statut == 'brouillon':
        fiche.statut = 'soumis'
        fiche.save(update_fields=['statut'])
        messages.success(request, f'Fiche {fiche.numero} soumise pour validation.')
    return redirect('stock_fiche_detail', pk=pk)


@login_required(login_url='login')
def fiche_valider(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    lignes = fiche.lignes.select_related('produit').all()
    if request.method == 'POST':
        from decimal import Decimal
        action = request.POST.get('action', 'valider')
        for ligne in lignes:
            ligne.qte_accordee = Decimal(request.POST.get(f'accorde_{ligne.pk}', ligne.qte_commander) or ligne.qte_commander)
            ligne.save(update_fields=['qte_accordee'])
        fiche.notes_direction = request.POST.get('notes_direction', '').strip()
        fiche.valide_par      = request.user
        fiche.date_validation = timezone.now()
        fiche.statut          = 'valide' if action == 'valider' else 'rejete'
        fiche.save()
        messages.success(request, f'Fiche {fiche.numero} {"validée" if action == "valider" else "rejetée"}.')
        return redirect('stock_fiche_detail', pk=pk)
    return render(request, 'stock/fiches/valider.html', {
        'fiche': fiche, 'lignes': lignes,
    })


@login_required(login_url='login')
@require_POST
def fiche_envoyer_achats(request, pk):
    from achats.models import BesoinAchat, LigneBesoin
    fiche = get_object_or_404(FicheBesoins, pk=pk)

    besoin_existant = fiche.besoins_achats.first()
    if besoin_existant:
        messages.warning(request, f"Cette fiche a déjà été transmise ({besoin_existant.numero}).")
        return redirect('achats:besoin_detail', pk=besoin_existant.pk)

    if fiche.statut not in ('soumis', 'valide'):
        messages.error(request, "La fiche doit être soumise ou validée avant de pouvoir être transmise aux achats.")
        return redirect('stock_fiche_detail', pk=pk)

    besoin = BesoinAchat.objects.create(
        titre=f"Fiche besoins {fiche.numero} — {fiche.periode_debut.strftime('%d/%m/%Y')} au {fiche.periode_fin.strftime('%d/%m/%Y')}",
        fiche_besoins=fiche, statut='soumis', cree_par=request.user,
        notes=f"Généré depuis la fiche {fiche.numero}",
    )
    lignes_creees = 0
    for ligne in fiche.lignes.select_related('produit').all():
        qte = ligne.qte_accordee if ligne.qte_accordee else ligne.qte_commander
        LigneBesoin.objects.create(
            besoin=besoin, produit=ligne.produit,
            quantite=qte,
            unite=ligne.produit.unite_mesure.code if ligne.produit.unite_mesure else 'unité',
        )
        lignes_creees += 1

    messages.success(request, f"Besoin {besoin.numero} transmis aux achats ({lignes_creees} produit(s)).")
    return redirect('achats:besoin_detail', pk=besoin.pk)


@login_required(login_url='login')
def fiche_print(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    lignes = fiche.lignes.select_related('produit').all()
    return render(request, 'stock/fiches/print.html', {
        'fiche': fiche, 'lignes': lignes, 'today': timezone.now().date(),
    })


# ──────────────────────────────────────────────────────────────
# INTÉGRATION DES RÉCEPTIONS D'ACHATS
# ──────────────────────────────────────────────────────────────

@login_required(login_url='login')
def receptions_a_integrer(request):
    from achats.models import ReceptionAchat
    receptions = ReceptionAchat.objects.filter(
        integre_en_stock=False
    ).select_related(
        'commande__fournisseur',
        'commande__proforma__besoin__fiche_besoins',
        'receptionne_par',
    ).order_by('-date_creation')
    return render(request, 'stock/receptions_a_integrer.html', {
        'receptions': receptions,
        'nb': receptions.count(),
    })


@login_required(login_url='login')
@require_POST
def integrer_reception(request, pk):
    from achats.models import ReceptionAchat, LigneReceptionAchat
    reception = get_object_or_404(ReceptionAchat, pk=pk, integre_en_stock=False)
    commande = reception.commande

    for lr in reception.lignes.select_related(
        'ligne_commande__ligne_proforma__ligne_besoin__produit'
    ).all():
        if lr.quantite_recue <= 0:
            continue
        lc = lr.ligne_commande
        produit = None
        if (lc.ligne_proforma and
                lc.ligne_proforma.ligne_besoin and
                lc.ligne_proforma.ligne_besoin.produit):
            produit = lc.ligne_proforma.ligne_besoin.produit
        if produit is None:
            continue

        numero_lot = lr.numero_lot or reception.numero
        lot = LotProduit.objects.filter(produit=produit, numero_lot=numero_lot).first()
        if lot:
            lot.quantite_actuelle += lr.quantite_recue
            lot.quantite_initiale += lr.quantite_recue
            update_lot_fields = ['quantite_actuelle', 'quantite_initiale']
            if not lot.date_peremption and lr.date_peremption:
                lot.date_peremption = lr.date_peremption
                update_lot_fields.append('date_peremption')
            lot.save(update_fields=update_lot_fields)
        else:
            lot = LotProduit.objects.create(
                produit=produit,
                numero_lot=numero_lot,
                date_reception=reception.date_reception,
                date_peremption=lr.date_peremption,
                quantite_initiale=lr.quantite_recue,
                quantite_actuelle=lr.quantite_recue,
                fournisseur=commande.fournisseur,
                prix_achat_lot=lc.prix_unitaire,
            )
        stock_avant = produit.stock_actuel
        produit.stock_actuel = produit.stock_actuel + lr.quantite_recue
        produit.save(update_fields=['stock_actuel'])
        MouvementStock.objects.create(
            produit=produit, lot=lot,
            type='entree', motif='achat',
            quantite=lr.quantite_recue,
            stock_avant=stock_avant,
            stock_apres=produit.stock_actuel,
            reference=reception.numero,
            notes=f'Réception {reception.numero} — Commande {commande.numero}',
            cree_par=request.user,
        )

    reception.integre_en_stock = True
    reception.date_integration = timezone.now()
    reception.integre_par = request.user
    reception.save(update_fields=['integre_en_stock', 'date_integration', 'integre_par'])

    messages.success(request, f'Réception {reception.numero} intégrée dans le stock.')
    return redirect('stock_receptions_a_integrer')


# ── Unités de mesure ──────────────────────────────────────────────────────────

@login_required(login_url='login')
def unites_list(request):
    q          = request.GET.get('q', '').strip()
    cat_filtre = request.GET.get('cat', '').strip()
    try:
        per_page = int(request.GET.get('per_page', 10))
        if per_page not in (5, 10, 20, 50):
            per_page = 10
    except ValueError:
        per_page = 10

    qs = UniteMesure.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q) | Q(categorie__icontains=q))
    if cat_filtre:
        qs = qs.filter(categorie=cat_filtre)

    categories = (UniteMesure.objects
                  .exclude(categorie__in=['', None])
                  .values_list('categorie', flat=True)
                  .distinct()
                  .order_by('categorie'))

    total_filtre = qs.count()
    paginator  = Paginator(qs, per_page)
    page_num   = request.GET.get('page', 1)
    page_obj   = paginator.get_page(page_num)

    return render(request, 'stock/unites/list.html', {
        'unites':       page_obj.object_list,
        'page_obj':     page_obj,
        'paginator':    paginator,
        'per_page':     per_page,
        'q':            q,
        'cat_filtre':   cat_filtre,
        'categories':   list(categories),
        'total':        UniteMesure.objects.count(),
        'total_filtre': total_filtre,
    })


def _get_unite_form():
    from django import forms as dj_forms

    class UniteMesureForm(dj_forms.ModelForm):
        class Meta:
            model = UniteMesure
            fields = ['nom', 'code', 'categorie', 'actif']
            widgets = {
                'nom':       dj_forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Millilitre'}),
                'code':      dj_forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : ml'}),
                'categorie': dj_forms.TextInput(attrs={'class': 'field-ul', 'placeholder': 'Ex : Volume, Poids, Forme galénique…', 'list': 'cats-list'}),
            }
    return UniteMesureForm


@login_required(login_url='login')
def unite_create(request):
    Form = _get_unite_form()
    categories = list(UniteMesure.objects.exclude(categorie__in=['', None]).values_list('categorie', flat=True).distinct().order_by('categorie'))
    if request.method == 'POST':
        form = Form(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Unité « {obj.nom} » créée.')
            return redirect('stock_unites')
        messages.error(request, 'Veuillez corriger les erreurs.')
    else:
        form = Form()
    return render(request, 'stock/unites/form.html', {'form': form, 'titre': 'Nouvelle unité de mesure', 'edit': False, 'categories': categories})


@login_required(login_url='login')
def unite_edit(request, pk):
    Form = _get_unite_form()
    obj = get_object_or_404(UniteMesure, pk=pk)
    categories = list(UniteMesure.objects.exclude(categorie__in=['', None]).values_list('categorie', flat=True).distinct().order_by('categorie'))
    if request.method == 'POST':
        form = Form(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Unité « {obj.nom} » mise à jour.')
            return redirect('stock_unites')
        messages.error(request, 'Veuillez corriger les erreurs.')
    else:
        form = Form(instance=obj)
    return render(request, 'stock/unites/form.html', {'form': form, 'obj': obj, 'titre': f'Modifier — {obj.nom}', 'edit': True, 'categories': categories})


@login_required(login_url='login')
@require_POST
def unite_delete(request, pk):
    obj = get_object_or_404(UniteMesure, pk=pk)
    nom = obj.nom
    obj.delete()
    messages.success(request, f'Unité « {nom} » supprimée.')
    return redirect('stock_unites')


@login_required(login_url='login')
@require_POST
def unite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = UniteMesure.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)
