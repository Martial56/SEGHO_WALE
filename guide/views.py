from itertools import groupby

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect

from .models import GuideCategorie


# Longueur combinée (en caractères) des articles qu'une page A4 encaisse
# sans déborder — mesurée empiriquement sur le rendu réel (au-delà, une page
# fixe de 480×679px avec cet habillage commence à dépasser).
CHAPITRE_CARACTERES_PAR_PAGE = 1000


def _paginer_chapitre(articles):
    """Répartit les articles d'une catégorie sur autant de pages A4 que
    nécessaire pour ne jamais déborder — jamais de défilement dans une page,
    comme un vrai livre. La plupart des chapitres tiennent sur une seule
    page ; les plus longs continuent sur la suivante."""
    pages = []
    page_courante = []
    longueur = 0
    for article in articles:
        poids = len(article.contenu)
        if page_courante and longueur + poids > CHAPITRE_CARACTERES_PAR_PAGE:
            pages.append(page_courante)
            page_courante = []
            longueur = 0
        page_courante.append(article)
        longueur += poids
    pages.append(page_courante)
    return pages


def _construire_pages():
    """Liste à plat des pages du livre, dans l'ordre de lecture : une ou
    plusieurs pages par catégorie (selon la longueur de ses articles —
    Vue d'ensemble, Actions courantes, Bon à savoir), jamais de défilement."""
    categories = GuideCategorie.objects.prefetch_related('articles')
    pages = []
    for categorie in categories:
        sous_pages = _paginer_chapitre(list(categorie.articles.all()))
        for i, groupe_articles in enumerate(sous_pages):
            pages.append({
                'categorie': categorie,
                'articles': groupe_articles,
                'suite': i > 0,
            })
    return pages


# Capacité approximative d'une page A4 de sommaire, en « unités » — un
# en-tête de section pèse plus qu'une simple ligne de catégorie. Purement
# empirique : ajuster si la mise en page du sommaire change.
TOC_UNITES_PAR_PAGE = 15
TOC_POIDS_ENTETE = 1.4


def _paginer_sommaire(sections):
    """Répartit les sections du sommaire sur autant de pages A4 que
    nécessaire, comme un vrai livre — jamais de défilement interne. Une
    section trop longue pour tenir seule est scindée, avec un en-tête
    « (suite) » sur la page suivante ; un en-tête n'est jamais laissé seul
    en bas d'une page sans au moins une catégorie sous lui."""
    pages = []
    page_courante = []
    unites = 0

    for section in sections:
        header_ouvert = False
        premiere_fois = True

        for cat in section['categories']:
            if not header_ouvert:
                if page_courante and unites + TOC_POIDS_ENTETE + 1 > TOC_UNITES_PAR_PAGE:
                    pages.append(page_courante)
                    page_courante = []
                    unites = 0
                nom = section['nom'] if premiere_fois else f"{section['nom']} (suite)"
                page_courante.append({'nom': nom, 'categories': []})
                unites += TOC_POIDS_ENTETE
                header_ouvert = True
                premiere_fois = False

            if page_courante[-1]['categories'] and unites + 1 > TOC_UNITES_PAR_PAGE:
                pages.append(page_courante)
                page_courante = [{'nom': f"{section['nom']} (suite)", 'categories': []}]
                unites = TOC_POIDS_ENTETE

            page_courante[-1]['categories'].append(cat)
            unites += 1

    if page_courante:
        pages.append(page_courante)
    return pages


def _romain(n):
    """Chiffre romain minuscule — convention des pages liminaires (sommaire)
    d'un livre, distincte de la numérotation arabe des chapitres."""
    valeurs = [(10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i')]
    resultat = ''
    for valeur, symbole in valeurs:
        while n >= valeur:
            resultat += symbole
            n -= valeur
    return resultat or 'i'


@login_required(login_url='login')
def guide_couverture(request):
    return render(request, 'guide/couverture.html', {
        'total_pages': len(_construire_pages()),
    })


@login_required(login_url='login')
def guide_hub(request, page=1):
    pages = _construire_pages()
    page_de_depart = {}
    for numero, item in enumerate(pages, start=1):
        page_de_depart.setdefault(item['categorie'].code, numero)

    categories = GuideCategorie.objects.prefetch_related('articles')
    sections_brutes = [
        {
            'nom': nom,
            'categories': [{'obj': c, 'page': page_de_depart[c.code]} for c in cats],
        }
        for nom, cats in groupby(categories, key=lambda c: c.groupe)
    ]

    toc_pages = _paginer_sommaire(sections_brutes)
    toc_total = len(toc_pages)
    if toc_total:
        page = max(1, min(page, toc_total))
        sections = toc_pages[page - 1]
    else:
        page, sections = 1, []

    return render(request, 'guide/hub.html', {
        'sections': sections,
        'total_pages': len(pages),
        'toc_numero': page,
        'toc_numero_romain': _romain(page),
        'toc_total': toc_total,
        'toc_precedent': page - 1 if page > 1 else None,
        'toc_suivant': page + 1 if page < toc_total else None,
    })


@login_required(login_url='login')
def guide_page(request, numero):
    """Affiche une double page (livre ouvert) : la page de gauche est
    toujours impaire, la page de droite paire — comme dans un vrai livre.
    `numero` peut pointer sur l'une ou l'autre, la planche entière s'affiche."""
    pages = _construire_pages()
    total = len(pages)
    if numero < 1 or numero > total:
        raise Http404("Cette page du guide n'existe pas.")

    gauche = numero if numero % 2 == 1 else numero - 1
    droite = gauche + 1 if gauche + 1 <= total else None

    return render(request, 'guide/page.html', {
        'gauche': pages[gauche - 1],
        'droite': pages[droite - 1] if droite else None,
        'numero_gauche': gauche,
        'numero_droite': droite,
        'total': total,
        'total_pages': total,
        'precedent': gauche - 2 if gauche > 1 else None,
        'suivant': gauche + 2 if gauche + 2 <= total else None,
    })


@login_required(login_url='login')
def guide_dos(request):
    """Quatrième de couverture : referme le livre après la dernière page."""
    total = len(_construire_pages())
    return render(request, 'guide/dos.html', {
        'total_pages': total,
    })


@login_required(login_url='login')
def guide_categorie(request, code):
    """Ancien lien par code de catégorie : redirige vers la page du chapitre
    correspondant, pour rester compatible avec un signet existant."""
    pages = _construire_pages()
    for numero, item in enumerate(pages, start=1):
        if item['categorie'].code == code:
            return redirect('guide:page', numero=numero)
    raise Http404("Cette rubrique du guide n'existe pas.")
