"""L'écran de fusion : choisir, prévoir, valider — et défaire.

Le moteur est dans `patients.fusion` ; ici on ne fait que recueillir ce qu'une
personne décide, le lui montrer avant, et le lui rendre après.

La permission est séparée de `gerer_doublons` : masquer se défait d'un clic,
fusionner déplace des factures et des rendez-vous.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from django.db.models import Q

from .doublons_acces import (centre_actif, exige_un_centre, fiches_du_centre,
                             fiches_du_groupe)
from .doublons_groupes import fiche_a_garder
from .doublons_vues import _sans_page
from .fusion import (Choix, FusionIncoherente, FusionRefusee, annuler, apercu,
                     fusion_bloquante, fusionner, obstacles, propositions)
from .liens_patient import comptes_par_table
from .models import FusionPatient

PERMISSION = 'patients.fusionner_patients'


def _le_couple(request, cle, pk):
    """La fiche gardée du groupe et celle qu'on veut y verser.

    Les deux sont relues dans le centre actif : la clé et l'identifiant
    viennent de l'adresse, ils ne prouvent rien par eux-mêmes.
    """
    fiches = fiches_du_groupe(request, cle,
                              fiches_du_centre(request).select_related('assurance'))
    membres = [f.pk for f in fiches]
    garder, _choisis = fiche_a_garder(fiches, comptes_par_table(membres))
    gardee = next((f for f in fiches if f.pk == garder), None)
    absorbee = next((f for f in fiches if str(f.pk) == str(pk)), None)
    if gardee is None or absorbee is None or gardee.pk == absorbee.pk:
        raise Http404('Cette fiche ne peut pas être versée dans celle-là.')
    return gardee, absorbee


def _retour(request):
    return (request.POST.get('retour') or request.GET.get('retour')
            or reverse('patients:doublons_liste'))


# ── L'écran ─────────────────────────────────────────────────────────────────

@login_required
@permission_required(PERMISSION, raise_exception=True)
@exige_un_centre
def fusion_ecran(request, cle, pk):
    gardee, absorbee = _le_couple(request, cle, pk)
    if request.method == 'POST':
        return _executer(request, cle, gardee, absorbee)
    return render(request, 'patients/doublons/fusionner.html',
                  _contexte(request, cle, gardee, absorbee))


def _contexte(request, cle, gardee, absorbee, erreur=''):
    lignes = propositions(gardee, absorbee)
    empechements = obstacles(gardee, absorbee)
    par_code = {o.code: o for o in empechements}
    return {
        'cle': cle,
        'gardee': gardee,
        'absorbee': absorbee,
        'lignes': lignes,
        'identiques': sum(1 for l in lignes if l.identique),
        'obstacles': empechements,
        'refus': [o for o in empechements if o.gravite == 'refus'],
        'hospitalisations': par_code.get('hospitalisations'),
        'sexe': par_code.get('sexe'),
        'deces': par_code.get('deces'),
        'rdv': par_code.get('rdv'),
        'apercu': apercu(gardee, absorbee),
        'erreur': erreur,
        'retour': _retour(request),
        'titre': 'Fusionner deux fiches',
    }


def _choix_depuis(request, gardee, absorbee):
    champs = {}
    for proposition in propositions(gardee, absorbee):
        retenu = request.POST.get(f'champ_{proposition.champ}')
        if retenu:
            champs[proposition.champ] = (
                retenu, request.POST.get(f'manuel_{proposition.champ}', ''))
    return Choix(
        champs=champs,
        hospitalisation_active=_entier(request.POST.get('hospitalisation_active')),
        rdv_a_annuler=[int(x) for x in request.POST.getlist('annuler_rdv')
                       if str(x).isdigit()],
        deces_confirme=bool(request.POST.get('deces_confirme')))


def _entier(valeur):
    return int(valeur) if valeur and str(valeur).isdigit() else None


def _executer(request, cle, gardee, absorbee):
    try:
        fusion = fusionner(gardee, absorbee, _choix_depuis(request, gardee, absorbee),
                           request.user)
    except (FusionRefusee, FusionIncoherente) as erreur:
        # L'écran est réaffiché avec ce qui a été saisi : renvoyer à la liste
        # obligerait à tout recommencer pour une case oubliée.
        return render(request, 'patients/doublons/fusionner.html',
                      _contexte(request, cle, gardee, absorbee, str(erreur)))
    messages.success(
        request,
        f'{absorbee.code_patient} a été fusionnée dans {gardee.code_patient} : '
        f'{fusion.lignes and sum(len(v) for v in fusion.lignes.values()) or 0} '
        'ligne(s) déplacée(s).')
    return redirect(_retour(request))


# ── Le journal des fusions ──────────────────────────────────────────────────

def _filtrer_fusions(fusions, recherche):
    """Par l'une ou l'autre des deux fiches, ou par qui a fusionné."""
    recherche = (recherche or '').strip()
    if not recherche:
        return fusions
    condition = Q(utilisateur__username__icontains=recherche)
    for cote in ('gardee', 'absorbee'):
        for champ in ('code_patient', 'nom', 'prenoms', 'ancien_identifiant'):
            condition |= Q(**{f'{cote}__{champ}__icontains': recherche})
    return fusions.filter(condition)


@login_required
@permission_required(PERMISSION, raise_exception=True)
@exige_un_centre
def fusion_journal(request):
    recherche = request.GET.get('q', '')
    fusions = FusionPatient.all_objects.filter(centre=centre_actif(request))
    fusions = _filtrer_fusions(
        fusions.select_related('gardee', 'absorbee', 'utilisateur',
                               'annulee_par'), recherche)
    pages = Paginator(fusions, 50)
    page = pages.get_page(request.GET.get('page'))
    lignes = [{'fusion': fusion,
               'total': sum(len(v) for v in (fusion.lignes or {}).values()),
               'bloquante': fusion_bloquante(fusion) if fusion.active else None}
              for fusion in page.object_list]
    return render(request, 'patients/doublons/fusions.html', {
        'page': page,
        'lignes': lignes,
        'q': recherche,
        'qs_base': _sans_page(request),
        'titre': 'Fusions',
    })


@login_required
@permission_required(PERMISSION, raise_exception=True)
@require_POST
@exige_un_centre
def fusion_annuler(request, pk):
    fusion = get_object_or_404(FusionPatient.all_objects, pk=pk,
                               centre=centre_actif(request))
    try:
        retenues = annuler(fusion, request.user)
    except FusionRefusee as erreur:
        messages.error(request, str(erreur))
        return redirect('patients:fusions')
    if retenues:
        # Une annulation qui ne rend pas tout doit le dire : la taire laisserait
        # croire que la base est revenue à ce qu'elle était.
        messages.error(request, 'Fusion annulée, sauf : ' + ' ; '.join(retenues))
    else:
        messages.success(
            request,
            f'{fusion.absorbee.code_patient} est de nouveau une fiche à part.')
    return redirect('patients:fusions')
