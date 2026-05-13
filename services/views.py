from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import (
    ArticleService, CategorieArticle, FamilleArticle, CompagniePharma,
    LigneFournisseurArticle, ConditionnementArticle, VarianteAttributArticle, ReglePrix,
)
from pharmacie.models import Fournisseur
from django.contrib.auth.models import User


@login_required
def services_list(request):
    qs = ArticleService.objects.select_related('categorie', 'famille').all()

    # Filtres
    q = request.GET.get('q', '').strip()
    categorie_id = request.GET.get('categorie', '')
    type_produit = request.GET.get('type_produit', '')
    statut = request.GET.get('statut', '')
    vue = request.GET.get('vue', 'kanban')  # kanban ou liste

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
    type_produit_choices = ArticleService.TYPE_PRODUIT_CHOICES

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
    article = get_object_or_404(ArticleService, pk=pk) if pk else None
    is_new = article is None

    if request.method == 'POST':
        data = request.POST

        # Champs en-tête
        nom = data.get('nom', '').strip()
        if not nom:
            messages.error(request, "Le nom de l'article est obligatoire.")
            return redirect(request.path)

        if is_new:
            article = ArticleService(cree_par=request.user)

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
        article.unite_mesure = data.get('unite_mesure', 'Unités')
        article.unite_achat = data.get('unite_achat', 'Unités')
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

        article.actif = 'actif' in data

        # Photo
        if 'photo' in request.FILES:
            article.photo = request.FILES['photo']

        article.save()
        messages.success(request, f"Article « {article.nom} » enregistré avec succès.")
        return redirect('services:detail', pk=article.pk)

    # GET — préparer le contexte
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom')
    categories = CategorieArticle.objects.all()
    familles = FamilleArticle.objects.all()
    compagnies = CompagniePharma.objects.all()
    users = User.objects.filter(is_active=True).order_by('last_name')

    lignes_fournisseurs = article.fournisseurs.select_related('fournisseur').all() if article else []
    lignes_conditionnements = article.conditionnements.all() if article else []
    lignes_variantes = article.variantes.all() if article else []
    regles = article.regles_prix.all() if article else []

    return render(request, 'services/form.html', {
        'article': article,
        'is_new': is_new,
        'fournisseurs': fournisseurs,
        'categories': categories,
        'familles': familles,
        'compagnies': compagnies,
        'users': users,
        'lignes_fournisseurs': lignes_fournisseurs,
        'lignes_conditionnements': lignes_conditionnements,
        'lignes_variantes': lignes_variantes,
        'regles': regles,
        'forme_choices': ArticleService.FORME_CHOICES,
        'voie_choices': ArticleService.VOIE_CHOICES,
        'type_article_choices': ArticleService.TYPE_ARTICLE_CHOICES,
        'type_produit_choices': ArticleService.TYPE_PRODUIT_CHOICES,
        'politique_fact_choices': ArticleService.POLITIQUE_FACT_CHOICES,
        'refacturer_choices': ArticleService.REFACTURER_CHOICES,
        'politique_controle_choices': ArticleService.POLITIQUE_CONTROLE_CHOICES,
    })


@login_required
def regles_prix(request, pk):
    article = get_object_or_404(ArticleService, pk=pk)
    regles = article.regles_prix.all()
    return render(request, 'services/regles_prix.html', {
        'article': article,
        'regles': regles,
    })


# ── Vues AJAX pour les lignes dynamiques ─────────────────────

@login_required
@require_POST
def ajax_add_fournisseur(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(ArticleService, pk=article_id)
    fournisseur_id = request.POST.get('fournisseur')
    if not fournisseur_id:
        return JsonResponse({'error': 'Fournisseur requis'}, status=400)
    ligne = LigneFournisseurArticle.objects.create(
        article=article,
        fournisseur_id=fournisseur_id,
        nom_article_fournisseur=request.POST.get('nom_article_fournisseur', ''),
        reference_fournisseur=request.POST.get('reference_fournisseur', ''),
        quantite_min=request.POST.get('quantite_min') or 1,
        unite_mesure=request.POST.get('unite_mesure', 'Unités'),
        prix=request.POST.get('prix') or 0,
        delai_livraison=request.POST.get('delai_livraison') or 0,
    )
    return JsonResponse({'id': ligne.pk, 'fournisseur': ligne.fournisseur.nom, 'prix': str(ligne.prix)})


@login_required
@require_POST
def ajax_add_conditionnement(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(ArticleService, pk=article_id)
    ligne = ConditionnementArticle.objects.create(
        article=article,
        conditionnement=request.POST.get('conditionnement', ''),
        quantite=request.POST.get('quantite') or 1,
        unite_mesure=request.POST.get('unite_mesure', 'Unités'),
        pour_vente='pour_vente' in request.POST,
        pour_achat='pour_achat' in request.POST,
    )
    return JsonResponse({'id': ligne.pk, 'conditionnement': ligne.conditionnement})


@login_required
@require_POST
def ajax_add_variante(request):
    article_id = request.POST.get('article_id')
    article = get_object_or_404(ArticleService, pk=article_id)
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
    article = get_object_or_404(ArticleService, pk=article_id)
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
