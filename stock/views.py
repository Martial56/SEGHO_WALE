from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Sum, Count, F
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Produit, CategorieStock, Fournisseur, LotProduit, MouvementStock, CommandeStock, LigneCommande, Inventaire, LigneInventaire, DemandePharmacie, LigneDemande, PHARMACIES, FicheBesoins, LigneFicheBesoins


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
    errors = {}

    if request.method == 'POST':
        nom  = request.POST.get('nom', '').strip()
        type_ = request.POST.get('type', 'medicament')
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not errors:
            p = Produit(
                nom=nom, type=type_,
                dci=request.POST.get('dci', '').strip(),
                dosage=request.POST.get('dosage', '').strip(),
                forme=request.POST.get('forme', ''),
                unite_mesure=request.POST.get('unite_mesure', 'unité').strip() or 'unité',
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
        'errors':       errors,
        'post':         request.POST if request.method == 'POST' else None,
    })


@login_required(login_url='login')
def produit_edit(request, pk):
    produit = get_object_or_404(Produit, pk=pk)
    categories   = CategorieStock.objects.filter(actif=True).order_by('nom')
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    errors = {}

    if request.method == 'POST':
        nom = request.POST.get('nom', '').strip()
        if not nom:
            errors['nom'] = 'Le nom est obligatoire.'
        if not errors:
            produit.nom   = nom
            produit.type  = request.POST.get('type', produit.type)
            produit.dci   = request.POST.get('dci', '').strip()
            produit.dosage = request.POST.get('dosage', '').strip()
            produit.forme  = request.POST.get('forme', '')
            produit.unite_mesure = request.POST.get('unite_mesure', 'unité').strip() or 'unité'
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

    paginator = Paginator(qs, 40)
    page_obj  = paginator.get_page(request.GET.get('page'))
    return render(request, 'stock/mouvements/list.html', {
        'page_obj':    page_obj,
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
    ).select_related('produit')

    if type_filtre:
        mouvements = mouvements.filter(produit__type=type_filtre)

    # Agréger par produit
    consommation = defaultdict(lambda: {'produit': None, 'total': 0.0, 'nb_livraisons': 0})
    for mv in mouvements:
        k = mv.produit.pk
        consommation[k]['produit'] = mv.produit
        consommation[k]['total']         += float(mv.quantite)
        consommation[k]['nb_livraisons'] += 1

    lignes = sorted(consommation.values(), key=lambda x: x['total'], reverse=True)

    total_quantite = sum(l['total'] for l in lignes)

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
        'lignes':        lignes,
        'mois':          mois,
        'annee':         annee,
        'mois_nom':      MOIS_NOMS[mois],
        'mois_noms':     MOIS_NOMS,
        'annees_dispo':  annees_dispo,
        'type_filtre':   type_filtre,
        'total_quantite': total_quantite,
        'prev_mois':     prev_mois,
        'prev_annee':    prev_annee,
        'next_mois':     next_mois,
        'next_annee':    next_annee,
        'today':         today,
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
        'total_produits':  len(produits),
        'chart_service':   chart_service_data,
        'chart_critiques': chart_critiques_data,
        'chart_commander': chart_commander_data,
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
            p.unite_mesure, p.stock_actuel, p.stock_alerte,
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
            errors['quantite'] = f'Stock insuffisant — disponible : {produit.stock_actuel} {produit.unite_mesure}.'

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
            messages.success(request, f'{quantite} {produit.unite_mesure} de « {produit.nom} » livrés à {pharma_label}.')
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
            stock_avant = float(ligne.produit.stock_actuel)
            stock_apres = max(0, stock_avant - qte)
            MouvementStock.objects.create(
                produit=ligne.produit, type='livraison', motif='livraison',
                pharmacie=demande.pharmacie, quantite=qte,
                stock_avant=stock_avant, stock_apres=stock_apres,
                reference=demande.numero,
                notes=f'Dotation {demande.get_pharmacie_display()}',
                cree_par=request.user,
            )
            ligne.produit.stock_actuel = stock_apres
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
    produits = Produit.objects.filter(actif=True).order_by('type', 'nom')
    if request.method == 'POST':
        pharmacie = request.POST.get('pharmacie', '')
        periode_debut = request.POST.get('periode_debut', '')
        periode_fin   = request.POST.get('periode_fin', '')
        notes = request.POST.get('notes', '').strip()
        if pharmacie and periode_debut and periode_fin:
            fiche = FicheBesoins.objects.create(
                pharmacie=pharmacie, periode_debut=periode_debut,
                periode_fin=periode_fin, notes=notes, cree_par=request.user,
            )
            for p in produits:
                stock_init = request.POST.get(f'stock_{p.pk}', '').strip()
                qte_recue  = request.POST.get(f'recu_{p.pk}', '').strip()
                qte_disp   = request.POST.get(f'disp_{p.pk}', '').strip()
                qte_cmd    = request.POST.get(f'cmd_{p.pk}', '').strip()
                if any([stock_init, qte_recue, qte_disp, qte_cmd]):
                    from decimal import Decimal
                    LigneFicheBesoins.objects.create(
                        fiche=fiche, produit=p,
                        stock_initial=Decimal(stock_init or 0),
                        qte_recue=Decimal(qte_recue or 0),
                        qte_dispensee=Decimal(qte_disp or 0),
                        cmm=Decimal(str(p.cmm)),
                        qte_commander=Decimal(qte_cmd or str(p.qte_a_commander)),
                    )
            messages.success(request, f'Fiche {fiche.numero} créée.')
            return redirect('stock_fiche_detail', pk=fiche.pk)
    return render(request, 'stock/fiches/form.html', {
        'mode': 'create', 'produits': produits, 'pharmacies': PHARMACIES,
        'today': timezone.now().date(),
    })


@login_required(login_url='login')
def fiche_detail(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    lignes = fiche.lignes.select_related('produit').all()
    return render(request, 'stock/fiches/detail.html', {
        'fiche': fiche, 'lignes': lignes,
    })


@login_required(login_url='login')
def fiche_edit(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    if fiche.statut not in ('brouillon',):
        messages.error(request, 'Seule une fiche en brouillon est modifiable.')
        return redirect('stock_fiche_detail', pk=pk)
    lignes = fiche.lignes.select_related('produit').all()
    if request.method == 'POST':
        from decimal import Decimal
        for ligne in lignes:
            ligne.stock_initial  = Decimal(request.POST.get(f'stock_{ligne.pk}', 0) or 0)
            ligne.qte_recue      = Decimal(request.POST.get(f'recu_{ligne.pk}', 0) or 0)
            ligne.qte_dispensee  = Decimal(request.POST.get(f'disp_{ligne.pk}', 0) or 0)
            ligne.qte_commander  = Decimal(request.POST.get(f'cmd_{ligne.pk}', 0) or 0)
            ligne.notes          = request.POST.get(f'notes_{ligne.pk}', '').strip()
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
def fiche_print(request, pk):
    fiche  = get_object_or_404(FicheBesoins, pk=pk)
    lignes = fiche.lignes.select_related('produit').all()
    return render(request, 'stock/fiches/print.html', {
        'fiche': fiche, 'lignes': lignes, 'today': timezone.now().date(),
    })
