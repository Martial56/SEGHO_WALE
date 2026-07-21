import re
import unicodedata
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .export import csv_response, xlsx_response
from .models import HistoriqueRapport
from .registry import REPORT_CATALOGUE, REPORTS_BY_SLUG


@login_required(login_url='login')
def rapports_hub(request):
    tous_rapports = [
        {**rapport, 'categorie': categorie['nom']}
        for categorie in REPORT_CATALOGUE
        for rapport in categorie['rapports']
    ]
    recents = HistoriqueRapport.objects.select_related('utilisateur').order_by('-date_generation')[:8]
    return render(request, 'rapports/hub.html', {
        'categories': REPORT_CATALOGUE,
        'tous_rapports': tous_rapports,
        'recents': recents,
    })


def _parse_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _nom_fichier(rapport):
    """« Listing_des_Patients_inscrits »."""
    nom = rapport['nom'].replace('(', '').replace(')', '')
    nom = unicodedata.normalize('NFKD', nom).encode('ascii', 'ignore').decode('ascii')
    nom = re.sub(r'[^\w\-]+', '_', nom)
    nom = re.sub(r'_+', '_', nom).strip('_')
    return f"Listing_des_{nom}"


@login_required(login_url='login')
def rapports_generer(request, slug):
    rapport = REPORTS_BY_SLUG.get(slug)
    if not rapport:
        raise Http404

    erreur = None
    periode_debut = request.POST.get('periode_debut') or request.GET.get('periode_debut', '')
    periode_fin = request.POST.get('periode_fin') or request.GET.get('periode_fin', '')
    format_fichier = request.POST.get('format', 'xlsx')

    if request.method == 'POST':
        debut = _parse_date(periode_debut)
        fin = _parse_date(periode_fin)
        if not debut and not fin:
            erreur = "Merci de renseigner au moins une date (début ou fin)."
        elif debut and fin and debut > fin:
            erreur = "La date de début doit être antérieure ou égale à la date de fin."
        else:
            if not fin:
                fin = timezone.now().date()
            columns, rows = rapport['fn'](debut, fin)
            filename = _nom_fichier(rapport)

            if format_fichier == 'csv':
                response, content = csv_response(filename, columns, rows)
            elif rapport.get('build_xlsx_fn'):
                content = rapport['build_xlsx_fn'](debut, fin, timezone.now())
                response = HttpResponse(
                    content,
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                )
                response['Content-Disposition'] = f'attachment; filename="{filename}.xlsx"'
            else:
                response, content = xlsx_response(
                    filename, rapport['nom'], columns, rows,
                    periode_debut=debut, periode_fin=fin, genere_le=timezone.now(),
                )

            historique = HistoriqueRapport(
                slug=slug, nom=filename, utilisateur=request.user,
                periode_debut=debut, periode_fin=fin, format_fichier=format_fichier,
                nb_lignes=len(rows),
            )
            historique.fichier.save(f"{filename}.{format_fichier}", ContentFile(content), save=False)
            historique.save()

            return response

    historique_rapport = HistoriqueRapport.objects.filter(slug=slug).select_related('utilisateur').order_by('-date_generation')[:10]

    return render(request, 'rapports/generer.html', {
        'rapport': rapport,
        'erreur': erreur,
        'periode_debut': periode_debut,
        'periode_fin': periode_fin,
        'format_fichier': format_fichier,
        'historique_rapport': historique_rapport,
    })


@login_required(login_url='login')
def rapports_historique(request):
    qs = HistoriqueRapport.objects.select_related('utilisateur').all()

    slug = request.GET.get('rapport', '')
    if slug:
        qs = qs.filter(slug=slug)

    utilisateur_id = request.GET.get('utilisateur', '')
    if utilisateur_id:
        qs = qs.filter(utilisateur_id=utilisateur_id)

    date_debut = _parse_date(request.GET.get('date_debut', ''))
    if date_debut:
        qs = qs.filter(date_generation__date__gte=date_debut)
    date_fin = _parse_date(request.GET.get('date_fin', ''))
    if date_fin:
        qs = qs.filter(date_generation__date__lte=date_fin)

    from django.contrib.auth.models import User
    utilisateurs = User.objects.filter(rapports_generes__isnull=False).distinct().order_by('username')

    from django.core.paginator import Paginator
    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'rapports/historique.html', {
        'page_obj': page_obj,
        'rapports_disponibles': REPORTS_BY_SLUG,
        'utilisateurs': utilisateurs,
        'slug': slug,
        'utilisateur_id': utilisateur_id,
        'date_debut': request.GET.get('date_debut', ''),
        'date_fin': request.GET.get('date_fin', ''),
    })


@login_required(login_url='login')
def rapports_retelecharger(request, pk):
    historique = HistoriqueRapport.objects.filter(pk=pk).first()
    if not historique or not historique.fichier:
        messages.error(request, "Ce fichier n'est plus disponible.")
        return redirect(reverse('rapports:historique'))
    from django.http import FileResponse
    return FileResponse(
        historique.fichier.open('rb'), as_attachment=True,
        filename=historique.fichier.name.rsplit('/', 1)[-1],
    )
