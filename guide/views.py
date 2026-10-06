from itertools import groupby

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect

from .models import GuideCategorie


def _sections():
    """Catégories groupées par section du sommaire, dans l'ordre d'affichage —
    structure unique partagée par la barre latérale sur toutes les pages."""
    categories = GuideCategorie.objects.prefetch_related('articles')
    return [
        {'nom': nom, 'categories': list(cats)}
        for nom, cats in groupby(categories, key=lambda c: c.groupe)
    ]


@login_required(login_url='login')
def guide_hub(request):
    """Page d'accueil du guide : barre latérale + première catégorie ouverte
    par défaut, pour ne jamais atterrir sur un panneau vide."""
    premiere = GuideCategorie.objects.first()
    if premiere:
        return redirect('guide:categorie', code=premiere.code)
    return render(request, 'guide/guide.html', {'sections': _sections(), 'categorie': None})


@login_required(login_url='login')
def guide_categorie(request, code):
    from django.contrib.staticfiles.finders import find
    from django.templatetags.static import static

    sections = _sections()
    categorie = next(
        (c for s in sections for c in s['categories'] if c.code == code),
        None,
    )
    if categorie is None:
        raise Http404("Cette rubrique du guide n'existe pas.")

    capture_path = f'guide/captures/{code}.png'
    capture_url = static(capture_path) if find(capture_path) else None

    formulaire_path = f'guide/captures/{code}_formulaire.png'
    formulaire_capture_url = static(formulaire_path) if find(formulaire_path) else None

    return render(request, 'guide/guide.html', {
        'sections': sections,
        'categorie': categorie,
        'articles': categorie.articles.all(),
        'capture_url': capture_url,
        'formulaire_capture_url': formulaire_capture_url,
    })
