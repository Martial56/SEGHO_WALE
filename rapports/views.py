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

from .configuration_soins import CompositionInvalide, appliquer, composition
from .export import csv_response, xlsx_response
from .maternite import calculer_rapport_maternite
from .soins import calculer_rapport_soins
from .gynecologie import calculer_rapport_gynecologie
from .med_generale import calculer_rapport_med_generale
from .models import (ConfigurationFicheSoins, HistoriqueRapport,
                     LigneFicheSoins)
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
def rapports_maternite(request):
    today = datetime.now().date()
    try:
        annee = int(request.GET.get('annee', today.year))
    except ValueError:
        annee = today.year
    try:
        mois = int(request.GET.get('mois', today.month))
    except ValueError:
        mois = today.month
    mois = min(max(mois, 1), 12)

    rapport = calculer_rapport_maternite(annee, mois)
    return render(request, 'rapports/rapport_maternite.html', rapport)


@login_required(login_url='login')
def rapports_soins(request):
    today = datetime.now().date()
    try:
        annee = int(request.GET.get('annee', today.year))
    except ValueError:
        annee = today.year
    try:
        mois = int(request.GET.get('mois', today.month))
    except ValueError:
        mois = today.month
    mois = min(max(mois, 1), 12)

    # La fiche se compose depuis la base : celle de l'utilisateur s'il s'en est
    # fait une, le format officiel sinon. Tant que personne n'a rien réglé,
    # tout le monde voit la même, et c'est celle d'avant.
    #
    # `?config=` permet d'en demander une autre, le temps d'un affichage : c'est
    # ainsi qu'on rouvre un mois passé tel qu'on l'avait rendu, en repassant la
    # composition de l'époque. Rien n'est changé pour autant — la sienne reste
    # la sienne au prochain chargement.
    visibles = ConfigurationFicheSoins.visibles_par(request.user)
    demandee = request.GET.get('config')
    if demandee:
        try:
            configuration = visibles.get(pk=int(demandee))
        except (ValueError, ConfigurationFicheSoins.DoesNotExist):
            raise Http404("Cette composition de fiche n'existe pas ou ne vous "
                          "est pas accessible.")
    else:
        configuration = ConfigurationFicheSoins.pour(request.user)

    rapport = calculer_rapport_soins(annee, mois, configuration=configuration)
    rapport['configurations'] = list(visibles.order_by('-est_defaut', 'nom'))
    return render(request, 'rapports/rapport_soins.html', rapport)


def _configuration_a_modifier(configuration, utilisateur):
    """Celle qu'on va réellement écrire, qui n'est pas toujours celle qu'on lit.

    Un utilisateur ordinaire qui part du format officiel ne le modifie pas : il
    en reçoit une copie, qui devient la sienne. C'est ce qui fait tenir tout le
    reste — sans cette copie, le premier réglage de n'importe qui changerait la
    fiche de tout le monde, et « revenir au format par défaut » ne voudrait
    plus rien dire.

    Un superutilisateur, lui, modifie bien le format officiel : c'est le seul à
    pouvoir le faire, et c'est voulu.
    """
    if configuration.est_defaut and not utilisateur.is_superuser:
        return configuration.dupliquer(
            utilisateur, nom="Ma fiche d'activité de soins", est_active=True)
    return configuration


def _fiche_designee(request, action):
    """La configuration visée par un bouton de la liste, ou None si refus.

    Le numéro vient d'un champ de formulaire : il ne décide de rien tant qu'on
    ne l'a pas confronté aux droits. Deux règles, et elles diffèrent —
    **reprendre** une fiche demande seulement de pouvoir la lire, donc la
    sienne, le format par défaut ou une fiche proposée ; la **partager**, la
    retirer du partage ou la **supprimer** demande d'en être le propriétaire.

    Le format par défaut ne se supprime ni ne se partage par ce chemin : il
    n'appartient à personne, et la règle du propriétaire l'écarte d'elle-même.
    """
    try:
        numero = int(request.POST.get('config', ''))
    except (TypeError, ValueError):
        messages.error(request, "Fiche introuvable.")
        return None

    if action == 'reprendre':
        candidates = ConfigurationFicheSoins.visibles_par(request.user)
    else:
        candidates = ConfigurationFicheSoins.objects.filter(
            utilisateur=request.user)

    fiche = candidates.filter(pk=numero).first()
    if fiche is None:
        messages.error(
            request, "Cette fiche n'existe pas ou ne vous appartient pas.")
    return fiche


def _ma_fiche(utilisateur):
    """Ma configuration de travail, créée au besoin.

    Reprendre une fiche mise de côté ou appliquer celle d'un collègue atterrit
    **toujours** ici, jamais dans le format par défaut — même pour un
    superutilisateur. Sans cette règle, appliquer la fiche d'un collègue
    changerait celle de tout le centre, ce que personne n'attend d'un bouton
    « Appliquer ».
    """
    sienne = ConfigurationFicheSoins.objects.filter(
        utilisateur=utilisateur, est_active=True).first()
    if sienne is not None:
        return sienne
    return ConfigurationFicheSoins.officielle().dupliquer(
        utilisateur, nom="Ma fiche d'activité de soins", est_active=True)


def _recopier_composition(source, cible):
    """Pose sur `cible` la composition de `source`, sans les relier.

    On passe par la forme sérialisée plutôt que de dupliquer : `cible` existe
    déjà, elle a son nom, son propriétaire et son historique, et seule sa
    composition doit changer.
    """
    import json as _json
    appliquer(cible, _json.dumps(composition(source)))


@login_required(login_url='login')
def rapports_soins_configuration(request):
    """L'écran de composition de la fiche d'activité de soins."""
    from services.models import Articleservice

    configuration = ConfigurationFicheSoins.pour(request.user)
    if configuration is None:
        raise Http404("Aucune configuration de fiche de soins n'est en place.")

    if request.method == 'POST':
        action = request.POST.get('action')
        retour = redirect('rapports:soins_configuration')

        if action == 'defaut':
            # Revenir au format officiel, c'est abandonner la sienne : celui
            # que les superutilisateurs ajustent reprend alors le dessus, tel
            # qu'ils l'ont laissé.
            ConfigurationFicheSoins.objects.filter(
                utilisateur=request.user).delete()
            messages.success(
                request, "La fiche est revenue au format par défaut.")
            return retour

        if action in ('reprendre', 'partager', 'ne_plus_partager', 'supprimer'):
            source = _fiche_designee(request, action)
            if source is None:
                return retour
            if action == 'reprendre':
                _recopier_composition(source, _ma_fiche(request.user))
                messages.success(
                    request, f"« {source.nom} » est devenue votre fiche.")
            elif action == 'supprimer':
                nom = source.nom
                source.delete()
                messages.success(request, f"« {nom} » a été supprimée.")
            else:
                source.partagee = (action == 'partager')
                source.save(update_fields=['partagee'])
                messages.success(request, (
                    f"« {source.nom} » est proposée aux autres utilisateurs."
                    if source.partagee else
                    f"« {source.nom} » n'est plus proposée."))
            return retour

        if action == 'enregistrer_sous':
            nom = (request.POST.get('nom') or '').strip()
            if not nom:
                messages.error(request, "Donnez un nom à cette fiche.")
            else:
                mise_de_cote = ConfigurationFicheSoins.objects.create(
                    nom=nom[:120], utilisateur=request.user, est_active=False)
                try:
                    appliquer(mise_de_cote, request.POST.get('composition'))
                except CompositionInvalide as erreur:
                    mise_de_cote.delete()
                    messages.error(request, str(erreur))
                else:
                    messages.success(
                        request, f"« {nom} » a été mise de côté.")
                    return retour
            configuration = ConfigurationFicheSoins.pour(request.user)
        else:
            cible = _configuration_a_modifier(configuration, request.user)
            try:
                appliquer(cible, request.POST.get('composition'))
            except CompositionInvalide as erreur:
                messages.error(request, str(erreur))
                configuration = cible
            else:
                messages.success(request, "La fiche a été enregistrée.")
                return retour

    prestations = list(Articleservice.objects.filter(actif=True)
                       .order_by('nom').values('pk', 'nom'))
    return render(request, 'rapports/configuration_soins.html', {
        'configuration': configuration,
        # Les objets eux-mêmes, pas du JSON : le gabarit les sérialise avec
        # `json_script`, qui échappe `<`, `>` et `&`. Un titre de bloc
        # contenant « </script> » refermerait sinon la balise et casserait la
        # page — et ces titres sont libres.
        'composition': composition(configuration),
        'prestations': [{'id': p['pk'], 'nom': p['nom']} for p in prestations],
        'nombre_prestations': len(prestations),
        'sources': LigneFicheSoins.SOURCE,
        'origines': LigneFicheSoins.ORIGINE,
        'modifie_le_defaut': configuration.est_defaut and request.user.is_superuser,
        'partira_en_copie': configuration.est_defaut and not request.user.is_superuser,
        # Les siennes mises de côté : tout ce qui lui appartient sans être sa
        # fiche de travail du moment.
        'mes_fiches': ConfigurationFicheSoins.objects.filter(
            utilisateur=request.user, est_active=False).order_by('nom'),
        'fiches_partagees': ConfigurationFicheSoins.objects.filter(
            partagee=True).exclude(utilisateur=request.user)
            .select_related('utilisateur').order_by('nom'),
    })


@login_required(login_url='login')
def rapports_gynecologie(request):
    today = datetime.now().date()
    try:
        annee = int(request.GET.get('annee', today.year))
    except ValueError:
        annee = today.year
    try:
        mois = int(request.GET.get('mois', today.month))
    except ValueError:
        mois = today.month
    mois = min(max(mois, 1), 12)

    rapport = calculer_rapport_gynecologie(annee, mois)
    return render(request, 'rapports/rapport_gynecologie.html', rapport)


@login_required(login_url='login')
def rapports_med_generale(request):
    today = datetime.now().date()
    try:
        annee = int(request.GET.get('annee', today.year))
    except ValueError:
        annee = today.year
    try:
        mois = int(request.GET.get('mois', today.month))
    except ValueError:
        mois = today.month
    mois = min(max(mois, 1), 12)

    rapport = calculer_rapport_med_generale(annee, mois)
    return render(request, 'rapports/rapport_med_generale.html', rapport)


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
