import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import (
    Articleservice, CategorieArticle, FamilleArticle, CompagniePharma,
    LigneFournisseurArticle, ConditionnementArticle, VarianteAttributArticle, ReglePrix,
    UniteMesure, CategorieUniteMesure, Consommable, Typeservice,
)
from .forms import CategorieArticleForm, CategorieUniteMesureForm, UniteMesureForm, ConsommableForm, TypeserviceForm
from pharmacie.models import Fournisseur
from django.contrib.auth.models import User


@login_required
def services_list(request):
    qs = Articleservice.objects.select_related('categorie', 'famille').all()

    # Filtres
    q = request.GET.get('q', '').strip()
    categorie_id = request.GET.get('categorie', '')
    type_produit = request.GET.get('type_produit', '')
    statut = request.GET.get('statut', '')
    vue = request.GET.get('vue', 'liste')  # kanban ou liste

    if q:
        qs = qs.filter(
            Q(nom__icontains=q) |
            Q(reference_interne__icontains=q) |
            Q(code_barres__icontains=q)
        )
    if categorie_id:
        qs = qs.filter(categorie_id=categorie_id)
    if type_produit:
        qs = qs.filter(type_produit_hospitalier=type_produit)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    total = qs.count()
    paginator = Paginator(qs, 24 if vue == 'kanban' else 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    categories = CategorieArticle.objects.all()
    type_produit_choices = Articleservice.TYPE_PRODUIT_CHOICES

    return render(request, 'services/list.html', {
        'page_obj': page_obj,
        'categories': categories,
        'type_produit_choices': type_produit_choices,
        'q': q,
        'categorie_id': categorie_id,
        'type_produit': type_produit,
        'statut': statut,
        'vue': vue,
        'total': total,
    })


@login_required
def service_form(request, pk=None):
    article = get_object_or_404(Articleservice, pk=pk) if pk else None
    is_new = article is None

    if request.method == 'POST':
        data = request.POST

        # Champs en-tête
        nom = data.get('nom', '').strip()
        if not nom:
            messages.error(request, "Le nom de l'article est obligatoire.")
            return redirect(request.path)

        if is_new:
            article = Articleservice(cree_par=request.user)

        # En-tête
        article.nom = nom
        article.reference_interne = data.get('reference_interne', '')
        article.favori = 'favori' in data
        article.peut_etre_vendu = 'peut_etre_vendu' in data
        article.peut_etre_achete = 'peut_etre_achete' in data

        # Onglet 1 — Détails médicament
        article.forme = data.get('forme', '')
        article.voie_administration = data.get('voie_administration', '')
        article.dosage = data.get('dosage', '')
        article.dosage_unite = data.get('dosage_unite', '')
        article.quantite_prescription_manuelle = 'quantite_prescription_manuelle' in data
        article.frequence = data.get('frequence', '')
        article.composant_actif = data.get('composant_actif', '')
        article.effet_therapeutique = data.get('effet_therapeutique', '')
        article.effets_indesirables = data.get('effets_indesirables', '')
        compagnie_id = data.get('compagnie_pharmaceutique')
        article.compagnie_pharmaceutique_id = compagnie_id if compagnie_id else None
        article.code_produit = data.get('code_produit', '')
        article.url_produit = data.get('url_produit', '')
        article.nom_produit_fabricant = data.get('nom_produit_fabricant', '')
        article.avertissement_grossesse = 'avertissement_grossesse' in data
        article.avertissement_lactation = 'avertissement_lactation' in data
        article.indications = data.get('indications', '')
        article.remarques = data.get('remarques', '')

        # Onglet 2 — Information générale
        article.type_article = data.get('type_article', 'consommable')
        article.type_produit_hospitalier = data.get('type_produit_hospitalier', '')
        article.politique_facturation = data.get('politique_facturation', 'qtes_commandees')
        article.refacturer_depenses = data.get('refacturer_depenses', 'non')
        article.unite_mesure_id = data.get('unite_mesure') or None
        article.unite_achat_id = data.get('unite_achat') or None
        article.prix_vente = data.get('prix_vente') or 0
        article.taxes_vente = data.get('taxes_vente', '')
        article.cout = data.get('cout') or 0
        categorie_id = data.get('categorie')
        article.categorie_id = categorie_id if categorie_id else None
        article.code_barres = data.get('code_barres', '')
        famille_id = data.get('famille')
        article.famille_id = famille_id if famille_id else None
        article.notes_internes = data.get('notes_internes', '')

        # Onglet 4 — Vente
        article.description_vente = data.get('description_vente', '')

        # Onglet 5 — Achats
        article.taxes_fournisseur = data.get('taxes_fournisseur', '')
        article.politique_controle = data.get('politique_controle', 'qtes_recues')
        article.description_achat = data.get('description_achat', '')

        # Stock consommable / stockable
        article.quantite_stock = data.get('quantite_stock') or 0
        article.quantite_alerte = data.get('quantite_alerte') or 0

        # Onglet 6 — Stock
        responsable_id = data.get('responsable')
        article.responsable_id = responsable_id if responsable_id else None
        article.poids = data.get('poids') or 0
        article.volume = data.get('volume') or 0
        article.delai_livraison_client = data.get('delai_livraison_client') or 0
        article.description_reception = data.get('description_reception', '')
        article.description_livraison = data.get('description_livraison', '')
        article.description_transfert = data.get('description_transfert', '')

        # Onglet 7 — Comptabilité
        article.compte_revenus = data.get('compte_revenus', '')
        article.compte_charges = data.get('compte_charges', '')
        article.compte_ecart_prix = data.get('compte_ecart_prix', '')

        if not is_new:
            article.actif = 'actif' in data

        # Photo
        if 'photo' in request.FILES:
            article.photo = request.FILES['photo']

        article.save()
        # M2M types
        types_ids = request.POST.getlist('types')
        article.types.set(types_ids)
        messages.success(request, f"Article « {article.nom} » enregistré avec succès.")
        return redirect('services:detail', pk=article.pk)

    # GET — préparer le contexte
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    categories = CategorieArticle.objects.all()
    cat_codes_json = json.dumps({str(c.pk): c.code for c in categories})
    familles = FamilleArticle.objects.all()
    compagnies = CompagniePharma.objects.all()
    users = User.objects.filter(is_active=True).order_by('last_name')
    unites_mesure = UniteMesure.objects.filter(actif=True).select_related('categorie').order_by('nom')

    lignes_fournisseurs = article.fournisseurs.select_related('fournisseur').all() if article else []
    lignes_conditionnements = article.conditionnements.all() if article else []
    lignes_variantes = article.variantes.all() if article else []
    regles = article.regles_prix.all() if article else []
    tous_types = Typeservice.objects.filter(actif=True).order_by('nom')
    types_selectionnes = list(article.types.values_list('pk', flat=True)) if article else []

    return render(request, 'services/form.html', {
        'article': article,
        'is_new': is_new,
        'fournisseurs': fournisseurs,
        'categories': categories,
        'familles': familles,
        'compagnies': compagnies,
        'users': users,
        'unites_mesure': unites_mesure,
        'lignes_fournisseurs': lignes_fournisseurs,
        'lignes_conditionnements': lignes_conditionnements,
        'lignes_variantes': lignes_variantes,
        'regles': regles,
        'forme_choices': Articleservice.FORME_CHOICES,
        'voie_choices': Articleservice.VOIE_CHOICES,
        'type_article_choices': Articleservice.TYPE_ARTICLE_CHOICES,
        'type_produit_choices': Articleservice.TYPE_PRODUIT_CHOICES,
        'politique_fact_choices': Articleservice.POLITIQUE_FACT_CHOICES,
        'refacturer_choices': Articleservice.REFACTURER_CHOICES,
        'politique_controle_choices': Articleservice.POLITIQUE_CONTROLE_CHOICES,
        'tous_types': tous_types,
        'types_selectionnes': types_selectionnes,
        'cat_codes_json': cat_codes_json,
    })


@login_required
def regles_prix(request, pk):
    article = get_object_or_404(Articleservice, pk=pk)
    regles = article.regles_prix.all()
    return render(request, 'services/regles_prix.html', {
        'article': article,
        'regles': regles,
    })


# ── Vues AJAX pour les lignes dynamiques ─────────────────────

# ── Consommables ──────────────────────────────────────────────────────────

@login_required
def consommables_list(request):
    qs = Consommable.objects.select_related('categorie', 'unite_mesure').all()

    q = request.GET.get('q', '').strip()
    categorie_id = request.GET.get('categorie', '')
    statut = request.GET.get('statut', '')
    vue = request.GET.get('vue', 'liste')

    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    if categorie_id:
        qs = qs.filter(categorie_id=categorie_id)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    total = qs.count()
    paginator = Paginator(qs, 24 if vue == 'grille' else 40)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'services/consommables/list.html', {
        'page_obj': page_obj,
        'categories': CategorieArticle.objects.all(),
        'q': q,
        'categorie_id': categorie_id,
        'statut': statut,
        'vue': vue,
        'total': total,
    })


@login_required
def consommable_create(request):
    if request.method == 'POST':
        form = ConsommableForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Consommable « {obj.nom} » créé avec succès.')
            return redirect('services:consommables')
    else:
        form = ConsommableForm()
    return render(request, 'services/consommables/form.html', {
        'form': form,
        'titre': 'Nouveau consommable',
        'edit': False,
    })


@login_required
def consommable_edit(request, pk):
    obj = get_object_or_404(Consommable, pk=pk)
    if request.method == 'POST':
        form = ConsommableForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Consommable « {obj.nom} » mis à jour.')
            return redirect('services:consommables')
    else:
        form = ConsommableForm(instance=obj)
    return render(request, 'services/consommables/form.html', {
        'form': form,
        'obj': obj,
        'titre': f'Modifier — {obj.nom}',
        'edit': True,
    })


@login_required
def consommable_delete(request, pk):
    obj = get_object_or_404(Consommable, pk=pk)
    if request.method == 'POST':
        nom = obj.nom
        obj.delete()
        messages.success(request, f'Consommable « {nom} » supprimé.')
    return redirect('services:consommables')


@login_required
@require_POST
def service_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Articleservice.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False, 'error': 'Aucun élément sélectionné'}, status=400)


@login_required
@require_POST
def consommable_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Consommable.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False, 'error': 'Aucun élément sélectionné'}, status=400)


@login_required
@require_POST
def categorie_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = CategorieArticle.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


@login_required
@require_POST
def unite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = UniteMesure.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


# ── Catégories de service ──────────────────────────────────────────────────

@login_required
def categories_list(request):
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    qs = CategorieArticle.objects.all()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    total_all = CategorieArticle.objects.count()
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'services/categories/list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': total_all,
        'total_filtre': qs.count(),
    })


@login_required
def categorie_create(request):
    if request.method == 'POST':
        form = CategorieArticleForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Catégorie « {obj.nom} » créée.')
            return redirect('services:categories')
    else:
        form = CategorieArticleForm()
    return render(request, 'services/categories/form.html', {
        'form': form,
        'titre': 'Nouvelle catégorie de service',
        'edit': False,
    })


@login_required
def categorie_edit(request, pk):
    obj = get_object_or_404(CategorieArticle, pk=pk)
    if request.method == 'POST':
        form = CategorieArticleForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Catégorie « {obj.nom} » mise à jour.')
            return redirect('services:categories')
    else:
        form = CategorieArticleForm(instance=obj)
    return render(request, 'services/categories/form.html', {
        'form': form,
        'obj': obj,
        'titre': f'Modifier — {obj.nom}',
        'edit': True,
    })


@login_required
def categorie_delete(request, pk):
    obj = get_object_or_404(CategorieArticle, pk=pk)
    if request.method == 'POST':
        nom = obj.nom
        obj.delete()
        messages.success(request, f'Catégorie « {nom} » supprimée.')
    return redirect('services:categories')


# ── Unités de mesure ───────────────────────────────────────────────────────

@login_required
def unites_list(request):
    q = request.GET.get('q', '').strip()
    categorie_id = request.GET.get('categorie', '')
    vue = request.GET.get('vue', 'liste')
    qs = UniteMesure.objects.select_related('categorie').all()
    if q:
        qs = qs.filter(Q(nom__icontains=q) | Q(code__icontains=q))
    if categorie_id:
        qs = qs.filter(categorie_id=categorie_id)
    total_all = UniteMesure.objects.count()
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'services/unites/list.html', {
        'page_obj': page_obj,
        'categories_um': CategorieUniteMesure.objects.all(),
        'q': q,
        'categorie_id': categorie_id,
        'vue': vue,
        'total': total_all,
        'total_filtre': qs.count(),
    })


@login_required
def unite_create(request):
    if request.method == 'POST':
        form = UniteMesureForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Unité « {obj.nom} » créée.')
            return redirect('services:unites')
    else:
        form = UniteMesureForm()
    return render(request, 'services/unites/form.html', {
        'form': form,
        'titre': 'Nouvelle unité de mesure',
        'edit': False,
    })


@login_required
def unite_edit(request, pk):
    obj = get_object_or_404(UniteMesure, pk=pk)
    if request.method == 'POST':
        form = UniteMesureForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Unité « {obj.nom} » mise à jour.')
            return redirect('services:unites')
    else:
        form = UniteMesureForm(instance=obj)
    return render(request, 'services/unites/form.html', {
        'form': form,
        'obj': obj,
        'titre': f'Modifier — {obj.nom}',
        'edit': True,
    })


@login_required
def unite_delete(request, pk):
    obj = get_object_or_404(UniteMesure, pk=pk)
    if request.method == 'POST':
        nom = obj.nom
        obj.delete()
        messages.success(request, f'Unité « {nom} » supprimée.')
    return redirect('services:unites')


@login_required
def categories_unites_list(request):
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    qs = CategorieUniteMesure.objects.all()
    if q:
        qs = qs.filter(nom__icontains=q)
    total_all = CategorieUniteMesure.objects.count()
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'services/unites/categories/list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': total_all,
        'total_filtre': qs.count(),
    })


@login_required
def categorie_unite_create(request):
    if request.method == 'POST':
        form = CategorieUniteMesureForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Catégorie « {obj.nom} » créée.')
            return redirect('services:categories_unites')
    else:
        form = CategorieUniteMesureForm()
    return render(request, 'services/unites/categories/form.html', {
        'form': form,
        'titre': "Nouvelle catégorie d'unité",
        'edit': False,
    })


@login_required
def categorie_unite_edit(request, pk):
    obj = get_object_or_404(CategorieUniteMesure, pk=pk)
    if request.method == 'POST':
        form = CategorieUniteMesureForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Catégorie « {obj.nom} » mise à jour.')
            return redirect('services:categories_unites')
    else:
        form = CategorieUniteMesureForm(instance=obj)
    return render(request, 'services/unites/categories/form.html', {
        'form': form,
        'obj': obj,
        'titre': f'Modifier — {obj.nom}',
        'edit': True,
    })


@login_required
def categorie_unite_delete(request, pk):
    obj = get_object_or_404(CategorieUniteMesure, pk=pk)
    if request.method == 'POST':
        nom = obj.nom
        obj.delete()
        messages.success(request, f'Catégorie « {nom} » supprimée.')
    return redirect('services:categories_unites')


@login_required
@require_POST
def categorie_unite_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = CategorieUniteMesure.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


# ── Types de service ───────────────────────────────────────────────────────

@login_required
def types_list(request):
    q = request.GET.get('q', '').strip()
    vue = request.GET.get('vue', 'liste')
    qs = Typeservice.objects.all()
    if q:
        qs = qs.filter(nom__icontains=q)
    total_all = Typeservice.objects.count()
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'services/types/list.html', {
        'page_obj': page_obj,
        'q': q,
        'vue': vue,
        'total': total_all,
        'total_filtre': qs.count(),
    })


@login_required
def type_create(request):
    if request.method == 'POST':
        form = TypeserviceForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f'Type « {obj.nom} » créé.')
            return redirect('services:types')
    else:
        form = TypeserviceForm()
    return render(request, 'services/types/form.html', {
        'form': form,
        'titre': 'Nouveau type de service',
        'edit': False,
    })


@login_required
def type_edit(request, pk):
    obj = get_object_or_404(Typeservice, pk=pk)
    if request.method == 'POST':
        form = TypeserviceForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Type « {obj.nom} » mis à jour.')
            return redirect('services:types')
    else:
        form = TypeserviceForm(instance=obj)
    return render(request, 'services/types/form.html', {
        'form': form,
        'obj': obj,
        'titre': f'Modifier — {obj.nom}',
        'edit': True,
    })


@login_required
def type_delete(request, pk):
    obj = get_object_or_404(Typeservice, pk=pk)
    if request.method == 'POST':
        nom = obj.nom
        obj.delete()
        messages.success(request, f'Type « {nom} » supprimé.')
    return redirect('services:types')


@login_required
@require_POST
def type_bulk_delete(request):
    ids = request.POST.getlist('ids[]')
    if ids:
        count, _ = Typeservice.objects.filter(pk__in=ids).delete()
        return JsonResponse({'ok': True, 'count': count})
    return JsonResponse({'ok': False}, status=400)


@login_required
@require_POST
def ajax_add_fournisseur(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(Articleservice, pk=article_id)
    fournisseur_id = request.POST.get('fournisseur')
    if not fournisseur_id:
        return JsonResponse({'error': 'Fournisseur requis'}, status=400)
    unite_id = request.POST.get('unite_mesure') or None
    ligne = LigneFournisseurArticle.objects.create(
        article=article,
        fournisseur_id=fournisseur_id,
        nom_article_fournisseur=request.POST.get('nom_article_fournisseur', ''),
        reference_fournisseur=request.POST.get('reference_fournisseur', ''),
        quantite_min=request.POST.get('quantite_min') or 1,
        unite_mesure_id=unite_id,
        prix=request.POST.get('prix') or 0,
        delai_livraison=request.POST.get('delai_livraison') or 0,
    )
    unite_nom = ligne.unite_mesure.nom if ligne.unite_mesure else '—'
    return JsonResponse({'id': ligne.pk, 'fournisseur': ligne.fournisseur.nom, 'prix': str(ligne.prix), 'unite_mesure': unite_nom})


@login_required
@require_POST
def ajax_add_conditionnement(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(Articleservice, pk=article_id)
    unite_id = request.POST.get('unite_mesure') or None
    ligne = ConditionnementArticle.objects.create(
        article=article,
        conditionnement=request.POST.get('conditionnement', ''),
        quantite=request.POST.get('quantite') or 1,
        unite_mesure_id=unite_id,
        pour_vente='pour_vente' in request.POST,
        pour_achat='pour_achat' in request.POST,
    )
    unite_nom = ligne.unite_mesure.nom if ligne.unite_mesure else '—'
    return JsonResponse({'id': ligne.pk, 'conditionnement': ligne.conditionnement, 'unite_mesure': unite_nom})


@login_required
@require_POST
def ajax_add_variante(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(Articleservice, pk=article_id)
    ligne = VarianteAttributArticle.objects.create(
        article=article,
        caracteristique=request.POST.get('caracteristique', ''),
        valeurs=request.POST.get('valeurs', ''),
    )
    return JsonResponse({'id': ligne.pk, 'caracteristique': ligne.caracteristique})


@login_required
@require_POST
def ajax_add_regle_prix(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(Articleservice, pk=article_id)
    ligne = ReglePrix.objects.create(
        article=article,
        liste_prix=request.POST.get('liste_prix', ''),
        applique_sur=request.POST.get('applique_sur', ''),
        quantite_min=request.POST.get('quantite_min') or 1,
        prix=request.POST.get('prix') or 0,
    )
    return JsonResponse({'id': ligne.pk, 'liste_prix': ligne.liste_prix})


@login_required
@require_POST
def ajax_delete_ligne(request, model, pk):
    model_map = {
        'fournisseur': LigneFournisseurArticle,
        'conditionnement': ConditionnementArticle,
        'variante': VarianteAttributArticle,
        'regle': ReglePrix,
    }
    Model = model_map.get(model)
    if not Model:
        return JsonResponse({'error': 'Modèle inconnu'}, status=400)
    obj = get_object_or_404(Model, pk=pk)
    obj.delete()
    return JsonResponse({'ok': True})
