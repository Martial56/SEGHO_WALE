"""L'écran des doublons : voir, écarter, masquer, désigner.

Rien ne fusionne ici. Cet écran montre ce que le relevé a trouvé et recueille
les trois décisions qu'une personne peut prendre sans déplacer de données :
« ce n'est pas un doublon », « cette fiche-là ne sert à rien », « c'est
celle-ci qu'on garde ». Chacune est réversible.

La fusion viendra ensuite, et s'appuiera sur les mêmes comptes : voir
`patients.liens_patient`.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from core import taches
from . import journal_doublons
from .doublons import paire_ordonnee
from .doublons_groupes import (filtrer, garnir, index, membres_depuis_cle,
                               mots_marques, naissance_affichee,
                               suggerer_a_garder)
from .liens_patient import champs_en_plus, comptes, comptes_par_table, tables
from .models import ChoixFicheGardee, PaireEcartee, Patient

#: Quatre colonnes de cartes : vingt-cinq par page laissaient la moitié de
#: l'écran vide, et neuf cents groupes se parcourent mieux par douze rangées.
PAR_PAGE = 48

#: Ce que l'écran côte à côte montre, dans cet ordre. Les champs techniques
#: n'y sont pas : ils ne disent rien du patient.
CHAMPS_COMPARES = [
    ('nom', 'Nom'), ('prenoms', 'Prénoms'), ('date_naissance', 'Naissance'),
    ('sexe', 'Sexe'), ('telephone', 'Téléphone'), ('telephone2', 'Téléphone 2'),
    ('email', 'Courriel'), ('adresse', 'Adresse'), ('ville', 'Ville'),
    ('lieu_naissance', 'Lieu de naissance'), ('nationalite', 'Nationalité'),
    ('profession', 'Profession'), ('groupe_sanguin', 'Groupe sanguin'),
    ('allergies', 'Allergies'), ('antecedents', 'Antécédents'),
    ('assurance', 'Assurance'), ('numero_assurance', "N° d'assuré"),
    ('contact_urgence_nom', "Contact d'urgence"),
    ('contact_urgence_telephone', "Téléphone d'urgence"),
    ('photo', 'Photo'),
]


def _sans_page(request):
    """Les paramètres de l'adresse, moins `page` : de quoi fabriquer les liens
    de pagination sans perdre le filtre ni la recherche."""
    params = request.GET.copy()
    params.pop('page', None)
    encode = params.urlencode()
    return f'{encode}&' if encode else ''


def _ajax(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _centre(request):
    return getattr(request, 'centre', None)


def _centre_id(request):
    centre = _centre(request)
    if centre is not None:
        return centre.pk
    # Un superuser sans centre actif : on lui montre le relevé du centre qui
    # en a un, plutôt qu'une page vide sans explication.
    from .models import DoublonPaire
    return (DoublonPaire.all_objects.values_list('centre_id', flat=True).first())


# ── La liste ────────────────────────────────────────────────────────────────

@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
def doublons_liste(request):
    niveau = request.GET.get('niveau') or 'certain'
    recherche = request.GET.get('q', '')
    centre_id = _centre_id(request)

    lignes = filtrer(index(centre_id), niveau, recherche) if centre_id else []
    pages = Paginator(lignes, PAR_PAGE)
    page = pages.get_page(request.GET.get('page'))

    contexte = {
        'page': page,
        'groupes': garnir(list(page.object_list)),
        'niveau': niveau,
        'q': recherche,
        'total': len(lignes),
        'qs_base': _sans_page(request),
        'masquage': _masquage_annoncee(request),
        'titre': 'Doublons',
    }
    # En AJAX on ne renvoie que la zone qui change : les pastilles, le compte,
    # la pagination et les cartes. La recherche et le bouton de recalcul, eux,
    # restent en place.
    gabarit = ('patients/doublons/includes/zone.html' if _ajax(request)
               else 'patients/doublons/liste.html')
    return render(request, gabarit, contexte)


def _masquage_annoncee(request):
    """La fiche qu'on vient de masquer, pour la banderole et son « Annuler ».

    Lue dans l'adresse plutôt que gardée en session : rien ne traîne, et la
    vérification `masque=True` suffit à faire disparaître la banderole dès que
    le masquage a été annulé — y compris sur une page rechargée.
    """
    pk = request.GET.get('masque')
    if not pk:
        return None
    return (Patient.all_objects
            .filter(pk=pk, masque=True).select_related('doublon_de').first())


def _retour_avec_masque(retour, fiche):
    """`retour`, augmentée de la fiche à annoncer."""
    separateur = '&' if '?' in retour else '?'
    return f"{retour}{separateur}{urlencode({'masque': fiche.pk})}"


# ── L'écran côte à côte ─────────────────────────────────────────────────────

def _valeur(fiche, champ):
    if champ == 'date_naissance':
        return naissance_affichee(fiche)
    if champ == 'sexe':
        return fiche.get_sexe_display() if fiche.sexe else ''
    if champ == 'assurance':
        return str(fiche.assurance) if fiche.assurance_id else ''
    if champ == 'photo':
        return 'oui' if fiche.photo else ''
    return getattr(fiche, champ, '') or ''


def _comparaison(fiches):
    """[(libellé, [valeur par fiche], diffèrent)] — ce que l'écran surligne.

    Une ligne où tout le monde dit la même chose n'apprend rien ; c'est
    l'écart qu'on doit voir d'un coup d'œil.

    Nom et prénoms portent en plus leurs mots marqués un à un : entre
    « ASSENA ELIAQUIM » et « ASSENA ELIAKIM », surligner la ligne entière
    noierait l'écart dans ce que les deux fiches ont en commun.
    """
    marques = {'nom': mots_marques([f.nom for f in fiches]),
               'prenoms': mots_marques([f.prenoms for f in fiches])}
    lignes = []
    for champ, libelle in CHAMPS_COMPARES:
        valeurs = [_valeur(f, champ) for f in fiches]
        remplies = {v for v in valeurs if v}
        ligne = {'libelle': libelle, 'valeurs': valeurs,
                 'different': len(remplies) > 1, 'vide': not remplies}
        if champ in marques:
            ligne['mots'] = marques[champ]
        lignes.append(ligne)
    return lignes


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
def doublons_comparer(request, cle):
    membres = membres_depuis_cle(cle)
    fiches = list(Patient.all_objects.filter(pk__in=membres)
                  .select_related('assurance', 'doublon_de', 'fusionne_dans'))
    if len(fiches) < 2:
        raise Http404("Ce groupe n'existe plus.")
    fiches.sort(key=lambda p: membres.index(p.pk))

    # `comptes_par_table` plutôt que `comptes` : l'écran aligne une ligne par
    # table, et `suggerer_a_garder` ne fait que sommer — le libellé accordé ne
    # servirait à personne ici.
    par_table = comptes_par_table([f.pk for f in fiches])
    choisis = set(ChoixFicheGardee.all_objects.filter(patient__in=fiches)
                  .values_list('patient_id', flat=True))
    garder = next((f.pk for f in fiches if f.pk in choisis),
                  suggerer_a_garder(fiches, par_table))

    cartes = []
    for fiche in fiches:
        autres = [f for f in fiches if f.pk != fiche.pk]
        porte = sum(par_table.get(fiche.pk, {}).values())
        # Masquer ne se propose que sur une fiche qui ne porte rien, et jamais
        # sur celle qu'on garde : la masquer effacerait le groupe entier.
        en_plus = sorted({c for autre in autres for c in champs_en_plus(fiche, autre)})
        cartes.append({
            'fiche': fiche,
            'total': porte,
            'garder': fiche.pk == garder,
            'choix_humain': fiche.pk in choisis,
            'peut_masquer': not porte and fiche.pk != garder and not fiche.masque,
            'raison_blocage': _raison_blocage(fiche, porte, garder),
            'informations_en_plus': en_plus,
        })

    comparaison = _comparaison(fiches)
    return render(request, 'patients/doublons/comparer.html', {
        'cle': cle,
        'cartes': cartes,
        # La fiche au profit de laquelle on masque : celle qu'on garde.
        'garder_pk': garder,
        'comparaison': comparaison,
        'champs_vides': sum(1 for ligne in comparaison if ligne['vide']),
        'rattachees': _lignes_rattachees(fiches, par_table),
        'ecartee': _paire_ecartee(fiches),
        'titre': 'Comparer les fiches',
        'retour': request.GET.get('retour') or reverse('patients:doublons_liste'),
    })


def _raison_blocage(fiche, porte, garder):
    """Pourquoi « Masquer » est grisé — écrit sous le bouton, pas au survol.

    Un bouton gris sans explication se lit comme une panne ; et la raison au
    survol ne se lit pas du tout sur une tablette.
    """
    if fiche.masque:
        return ''
    if fiche.pk == garder:
        return "C'est la fiche qu'on garde."
    if porte:
        return 'Contient des données : il faut la fusionner.'
    return ''


def _lignes_rattachees(fiches, par_table):
    """Une ligne par table, alignée sur les mêmes colonnes que la comparaison.

    Seules les tables où au moins une fiche porte quelque chose : treize lignes
    de tirets n'apprendraient rien de plus qu'une absence.
    """
    lignes = []
    for cle, libelle in tables():
        nombres = [par_table.get(f.pk, {}).get(cle, 0) for f in fiches]
        if not any(nombres):
            continue
        lignes.append({'libelle': libelle, 'nombres': nombres})
    totaux = [sum(par_table.get(f.pk, {}).values()) for f in fiches]
    return {'lignes': lignes, 'totaux': totaux, 'rien': not any(totaux)}


def _paire_ecartee(fiches):
    """La décision « pas un doublon » si elle existe déjà pour ce duo."""
    if len(fiches) != 2:
        return None
    a, b = paire_ordonnee(fiches[0].pk, fiches[1].pk)
    return PaireEcartee.all_objects.filter(patient_a_id=a, patient_b_id=b).first()


# ── Les décisions ───────────────────────────────────────────────────────────

def _deux_fiches(request, cle):
    membres = membres_depuis_cle(cle)
    fiches = list(Patient.all_objects.filter(pk__in=membres))
    if len(fiches) != 2:
        raise Http404('Cette décision ne vaut que pour deux fiches.')
    return fiches


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_ecarter(request, cle):
    """« Pas un doublon » : la paire ne revient plus, même après recalcul."""
    fiches = _deux_fiches(request, cle)
    a, b = paire_ordonnee(fiches[0].pk, fiches[1].pk)
    PaireEcartee.all_objects.update_or_create(
        patient_a_id=a, patient_b_id=b,
        defaults={'utilisateur': request.user,
                  'raison': (request.POST.get('raison') or '').strip(),
                  'centre_id': fiches[0].centre_id})
    _oublier_la_paire(a, b)
    messages.success(request, 'Ces deux fiches ne seront plus rapprochées.')
    return redirect(request.POST.get('retour') or 'patients:doublons_liste')


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_reprendre(request, cle):
    """Annule un « pas un doublon » : la paire revient au relevé."""
    fiches = _deux_fiches(request, cle)
    a, b = paire_ordonnee(fiches[0].pk, fiches[1].pk)
    PaireEcartee.all_objects.filter(patient_a_id=a, patient_b_id=b).delete()
    _relever(fiches[0])
    messages.success(request, 'Cette paire est revenue dans la liste.')
    return redirect(request.POST.get('retour') or 'patients:doublons_liste')


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_masquer(request, cle, pk):
    """Retire une fiche vide, au profit d'une autre du même groupe.

    Le contrôle est ici, pas seulement sur un bouton grisé : une requête
    forgée ne doit pas pouvoir faire disparaître un dossier qui porte des
    rendez-vous ou des factures.
    """
    membres = membres_depuis_cle(cle)
    fiche = get_object_or_404(Patient.all_objects, pk=pk, pk__in=membres)
    gardee = get_object_or_404(
        Patient.all_objects, pk=request.POST.get('au_profit_de'), pk__in=membres)

    if gardee.pk == fiche.pk:
        raise Http404('Une fiche ne peut pas être le doublon d\'elle-même.')
    if comptes([fiche.pk])[fiche.pk]:
        refus = 'Cette fiche contient des données : il faut la fusionner.'
        if _ajax(request):
            return JsonResponse({'ok': False, 'message': refus}, status=409)
        messages.error(request, refus)
        return redirect('patients:doublons_comparer', cle=cle)

    with transaction.atomic():
        fiche.masque = True
        fiche.doublon_de = gardee
        fiche.save(update_fields=['masque', 'doublon_de'])
    _relever(fiche)

    # La banderole porte l'annulation : pas de message en plus, il ferait
    # doublon avec elle — et c'est le genre d'ironie qu'on évite ici.
    if _ajax(request):
        return JsonResponse({
            'ok': True, 'pk': fiche.pk, 'code': fiche.code_patient,
            'code_gardee': gardee.code_patient,
            'annuler': reverse('patients:doublons_reafficher', args=[fiche.pk])})
    retour = request.POST.get('retour') or reverse('patients:doublons_liste')
    return redirect(_retour_avec_masque(retour, fiche))


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_reafficher(request, pk):
    """Annule un masquage : la fiche redevient un dossier ordinaire."""
    fiche = get_object_or_404(Patient.all_objects, pk=pk, masque=True)
    fiche.masque = False
    fiche.doublon_de = None
    fiche.save(update_fields=['masque', 'doublon_de'])
    _relever(fiche)
    if _ajax(request):
        return JsonResponse({'ok': True, 'pk': fiche.pk,
                             'code': fiche.code_patient})
    messages.success(request, f'{fiche.code_patient} est de nouveau visible.')
    return redirect(request.POST.get('retour') or 'patients:doublons_liste')


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_garder(request, cle, pk):
    """Désigne la fiche à garder. Elle prime sur la suggestion automatique."""
    membres = membres_depuis_cle(cle)
    fiche = get_object_or_404(Patient.all_objects, pk=pk, pk__in=membres)
    ChoixFicheGardee.all_objects.filter(patient_id__in=membres).delete()
    ChoixFicheGardee.all_objects.create(
        patient=fiche, utilisateur=request.user, centre_id=fiche.centre_id)
    messages.success(request, f'{fiche.code_patient} sera la fiche gardée.')
    return redirect('patients:doublons_comparer', cle=cle)


# ── L'onglet des créations forcées ──────────────────────────────────────────

@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
def doublons_journal(request):
    traces = journal_doublons.traces(_centre(request))
    pages = Paginator(traces, 50)
    page = pages.get_page(request.GET.get('page'))
    fiches = {p.pk: p for p in Patient.all_objects.filter(
        pk__in=[t.object_id for t in page.object_list])}
    # Les lignes sont assemblées ici : chercher la fiche et le libellé depuis
    # le gabarit demanderait des contorsions pour un résultat moins lisible.
    lignes = [{'trace': trace,
               'fiche': fiches.get(trace.object_id),
               'libelle': journal_doublons.LIBELLES.get(trace.code, trace.code)}
              for trace in page.object_list]
    return render(request, 'patients/doublons/journal.html', {
        'page': page,
        'lignes': lignes,
        'forcage': journal_doublons.FORCAGE,
        'qs_base': _sans_page(request),
        'titre': 'Créations forcées et confirmations',
    })


# ── Le recalcul à la demande ────────────────────────────────────────────────

@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
def doublons_recalculer(request):
    from .doublons_recalcul import RecalculDejaEnCours, recalculer_centre

    centre = _centre(request)
    centre_id = _centre_id(request)

    def travail(avancement):
        nombre = recalculer_centre(centre_id, avancement)
        return f'{nombre} paire(s) relevée(s).'

    def travail_protege(avancement):
        try:
            return travail(avancement)
        except RecalculDejaEnCours as erreur:
            return str(erreur)

    tache = taches.lancer('Recalcul des doublons', request.user, centre,
                          travail_protege)
    return redirect(f"{reverse('patients:doublons_liste')}?tache={tache.pk}")


# ── Outils ──────────────────────────────────────────────────────────────────

def _oublier_la_paire(pk_a, pk_b):
    from .models import DoublonPaire
    DoublonPaire.all_objects.filter(patient_a_id=pk_a, patient_b_id=pk_b).delete()


def _relever(fiche):
    """Reprend le relevé de cette fiche tout de suite.

    Sans cela, annuler une décision ne montrerait rien avant le passage de
    nuit : on cliquerait sans voir revenir ce qu'on vient de rendre.
    """
    from .doublons_recalcul import recalculer_fiche
    try:
        recalculer_fiche(Patient.all_objects.get(pk=fiche.pk))
    except Exception:
        # Le passage de nuit rattrapera : ne pas faire tomber l'écran pour ça.
        pass
