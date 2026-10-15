"""L'écran des doublons : voir, écarter, masquer, désigner.

Rien ne fusionne ici. Cet écran montre ce que le relevé a trouvé et recueille
les trois décisions qu'une personne peut prendre sans déplacer de données :
« ce n'est pas un doublon », « cette fiche-là ne sert à rien », « c'est
celle-ci qu'on garde ». Chacune est réversible.

La fusion viendra ensuite, et s'appuiera sur les mêmes comptes : voir
`patients.liens_patient`.
"""

from functools import wraps

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from core import taches
from . import journal_doublons
from .doublons import paire_ordonnee
from .doublons_acces import (centre_actif, exige_un_centre, fiche_du_centre,
                             fiches_du_centre, fiches_du_groupe, id_du_centre)
from .doublons_groupes import (DIMENSIONS, RATTACHEES, compter_par_raison,
                               compter_par_rattachees, fiche_a_garder, filtrer,
                               garnir, index, mots_marques, naissance_affichee,
                               resume_du_groupe, sections, valeur_affichee)
from .liens_patient import champs_en_plus, comptes, comptes_par_table, tables
from .models import (ChoixFicheGardee, LotDoublons, PaireEcartee,
                     Patient)

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


# Le centre actif commande tout cet écran, sans exception ni repli : les
# outils sont dans `doublons_acces`, et chaque vue d'ici porte
# `@exige_un_centre`.


# ── La liste ────────────────────────────────────────────────────────────────

def _filtres_demandes(donnees):
    """Les quatre filtres et le regroupement, lus dans une adresse ou un POST.

    Un seul endroit les lit : la liste et la sélection « tout le filtre »
    doivent retenir exactement le même relevé, sinon on confirmerait un
    nombre et on en traiterait un autre.
    """
    grouper = donnees.get('grouper') or ''
    return {
        # Aucun filtre d'office : arriver sur la page ne doit pas allumer un
        # bouton que l'utilisateur n'a pas choisi, ni lui cacher la moitié du
        # relevé sans le dire.
        'niveau': donnees.get('niveau') or 'tous',
        'q': donnees.get('q', ''),
        'raisons': donnees.getlist('raison'),
        'rattache': [c for c in donnees.getlist('rattache')
                     if c in dict(RATTACHEES)],
        'grouper': grouper if grouper in dict(DIMENSIONS) else '',
    }


def _releve_filtre(request, filtres):
    """(relevé entier, lignes retenues, totaux rattachés) pour ces filtres."""
    releve = index(id_du_centre(request))
    # Les totaux rattachés ne sont lus que s'ils servent : une seconde et
    # demie pour dix-sept mille fiches, on ne la paie pas pour rien.
    totaux = (_totaux_du_releve(releve)
              if filtres['rattache'] or filtres['grouper'] == 'rattachees'
              else {})
    lignes = filtrer(releve, filtres['niveau'], filtres['q'],
                     filtres['raisons'], filtres['rattache'], totaux)
    return releve, lignes, totaux


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
def doublons_liste(request):
    filtres = _filtres_demandes(request.GET)
    niveau, recherche = filtres['niveau'], filtres['q']
    raisons, rattache = filtres['raisons'], filtres['rattache']
    grouper = filtres['grouper']

    releve = index(id_du_centre(request))
    # Les totaux rattachés ne sont lus que s'ils servent : une seconde et
    # demie pour dix-sept mille fiches, on ne la paie pas pour rien.
    totaux = (_totaux_du_releve(releve)
              if rattache or grouper == 'rattachees' else {})
    lignes = filtrer(releve, niveau, recherche, raisons, rattache, totaux)
    # Chaque menu compte sur le relevé filtré par les **autres** filtres :
    # le nombre annoncé est celui qu'on obtiendra en cochant.
    comptes_raison = compter_par_raison(
        filtrer(releve, niveau, recherche, (), rattache, totaux))
    comptes_rattache = (compter_par_rattachees(
        filtrer(releve, niveau, recherche, raisons, (), totaux), totaux)
        if totaux else {})

    paquets = sections(lignes, grouper, totaux) if grouper else None
    if paquets is not None:
        # Une copie par ligne : l'index vient du cache, on n'y écrit pas.
        # Le total de la section voyage avec elle : la bande l'affiche, et il
        # vaut pour l'ensemble filtré, pas pour la page.
        # `section_rang` est le `data-chemin` que lit le script de repliage
        # partagé (static/js/listing_groupes.js) : les cartes et les lignes
        # d'une section le portent en `data-parent`.
        lignes = [dict(ligne, section=libelle, section_total=len(contenu),
                       section_rang=rang)
                  for rang, (libelle, contenu) in enumerate(paquets)
                  for ligne in contenu]

    pages = Paginator(lignes, PAR_PAGE)
    page = pages.get_page(request.GET.get('page'))

    contexte = {
        'page': page,
        'groupes': garnir(list(page.object_list)),
        'niveau': niveau,
        'q': recherche,
        'raisons': raisons,
        'rattache': rattache,
        'grouper': grouper,
        'dimensions': DIMENSIONS,
        'comptes_raison': comptes_raison,
        'rattachees_possibles': [(code, libelle, comptes_rattache.get(code, 0))
                                 for code, libelle in RATTACHEES],
        'sections_totaux': ({libelle: len(contenu)
                             for libelle, contenu in paquets}
                            if paquets is not None else {}),
        'pastilles': _pastilles(niveau, raisons, rattache, grouper),
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


def _totaux_du_releve(releve):
    """Les données rattachées de toutes les fiches du relevé, en cache court."""
    from .liens_patient import totaux_rattaches
    return totaux_rattaches({pk for ligne in releve for pk in ligne['membres']})


def _pastilles(niveau, raisons, rattache, grouper):
    """Ce qui est actif, en clair, pour l'afficher et pouvoir le retirer.

    Rendu : [{'libelle', 'cle', 'valeur'}] — `cle`/`valeur` disent au
    gabarit quel paramètre retirer d'un clic.
    """
    from .doublons_groupes import NIVEAUX_AFFICHES

    posees = []
    if niveau in NIVEAUX_AFFICHES:
        posees.append({'libelle': NIVEAUX_AFFICHES[niveau],
                       'cle': 'niveau', 'valeur': 'tous'})
    for phrase in raisons:
        posees.append({'libelle': phrase, 'cle': 'raison', 'valeur': phrase})
    libelles = dict(RATTACHEES)
    for code in rattache:
        posees.append({'libelle': libelles.get(code, code),
                       'cle': 'rattache', 'valeur': code})
    if grouper:
        posees.append({'libelle': 'Groupé par ' + dict(DIMENSIONS)[grouper].lower(),
                       'cle': 'grouper', 'valeur': ''})
    return posees


def _masquage_annoncee(request):
    """La fiche qu'on vient de masquer, pour la banderole et son « Annuler ».

    Lue dans l'adresse plutôt que gardée en session : rien ne traîne, et la
    vérification `masque=True` suffit à faire disparaître la banderole dès que
    le masquage a été annulé — y compris sur une page rechargée.
    """
    pk = request.GET.get('masque') or ''
    if not pk.isdigit():
        return None
    return (fiches_du_centre(request)
            .filter(pk=pk, masque=True).select_related('doublon_de').first())


def _retour_avec_masque(retour, fiche):
    """`retour`, augmentée de la fiche à annoncer."""
    separateur = '&' if '?' in retour else '?'
    return f"{retour}{separateur}{urlencode({'masque': fiche.pk})}"


# ── L'écran côte à côte ─────────────────────────────────────────────────────

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
        valeurs = [valeur_affichee(f, champ) for f in fiches]
        remplies = {v for v in valeurs if v}
        ligne = {'libelle': libelle, 'valeurs': valeurs,
                 'different': len(remplies) > 1, 'vide': not remplies}
        if champ in marques:
            ligne['mots'] = marques[champ]
        lignes.append(ligne)
    return lignes


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
def doublons_comparer(request, cle):
    fiches = fiches_du_groupe(
        request, cle,
        fiches_du_centre(request).select_related('assurance', 'doublon_de',
                                                 'fusionne_dans'))

    # `comptes_par_table` plutôt que `comptes` : l'écran aligne une ligne par
    # table, et `suggerer_a_garder` ne fait que sommer — le libellé accordé ne
    # servirait à personne ici.
    par_table = comptes_par_table([f.pk for f in fiches])
    garder, choisis = fiche_a_garder(fiches, par_table)

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
        'garder_code': next((f.code_patient for f in fiches if f.pk == garder), ''),
        # La position de la colonne gardée : le tableau la teinte sur toute sa
        # hauteur, et une cellule ne sait pas de quelle fiche elle relève.
        'garder_index': next((i for i, f in enumerate(fiches) if f.pk == garder), -1),
        'comparaison': comparaison,
        'champs_vides': sum(1 for ligne in comparaison if ligne['vide']),
        'rattachees': _lignes_rattachees(fiches, par_table),
        'ecartee': _paire_ecartee(fiches),
        # Le score et la raison lus sur la carte : les perdre en ouvrant
        # l'écran oblige à revenir en arrière pour se les rappeler.
        'resume': resume_du_groupe(fiches),
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
    fiches = fiches_du_groupe(request, cle)
    if len(fiches) != 2:
        raise Http404('Cette décision ne vaut que pour deux fiches.')
    return fiches


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
@exige_un_centre
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
@exige_un_centre
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
@exige_un_centre
def doublons_masquer(request, cle, pk):
    """Retire une fiche vide, au profit d'une autre du même groupe.

    Le contrôle est ici, pas seulement sur un bouton grisé : une requête
    forgée ne doit pas pouvoir faire disparaître un dossier qui porte des
    rendez-vous ou des factures.
    """
    membres = [f.pk for f in fiches_du_groupe(request, cle)]
    fiche = fiche_du_centre(request, pk)
    gardee = fiche_du_centre(request, request.POST.get('au_profit_de'))
    if fiche.pk not in membres or gardee.pk not in membres:
        raise Http404("Ces fiches ne sont pas du même groupe.")

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
        fiche.masque_par = request.user
        fiche.masque_le = timezone.now()
        fiche.save(update_fields=['masque', 'doublon_de', 'masque_par',
                                  'masque_le'])
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
@exige_un_centre
def doublons_reafficher(request, pk):
    """Annule un masquage : la fiche redevient un dossier ordinaire."""
    fiche = fiche_du_centre(request, pk, masque=True)
    fiche.masque = False
    fiche.doublon_de = None
    # Qui et quand sont effacés avec le masquage : les garder laisserait
    # croire, au masquage suivant, à une décision qui n'a pas été reprise.
    fiche.masque_par = None
    fiche.masque_le = None
    fiche.save(update_fields=['masque', 'doublon_de', 'masque_par',
                              'masque_le'])
    _relever(fiche)
    if _ajax(request):
        return JsonResponse({'ok': True, 'pk': fiche.pk,
                             'code': fiche.code_patient})
    messages.success(request, f'{fiche.code_patient} est de nouveau visible.')
    return redirect(request.POST.get('retour') or 'patients:doublons_liste')


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
@exige_un_centre
def doublons_garder(request, cle, pk):
    """Désigne la fiche à garder. Elle prime sur la suggestion automatique."""
    membres = [f.pk for f in fiches_du_groupe(request, cle)]
    fiche = fiche_du_centre(request, pk)
    if fiche.pk not in membres:
        raise Http404("Cette fiche n'est pas de ce groupe.")
    ChoixFicheGardee.all_objects.filter(patient_id__in=membres).delete()
    ChoixFicheGardee.all_objects.create(
        patient=fiche, utilisateur=request.user, centre_id=fiche.centre_id)
    messages.success(request, f'{fiche.code_patient} sera la fiche gardée.')
    return redirect('patients:doublons_comparer', cle=cle)


# ── L'onglet des créations forcées ──────────────────────────────────────────

def _filtrer_traces(request, traces, recherche):
    """Par la fiche visée ou par l'auteur de la trace.

    Jamais par le texte du message : il est écrit pour être lu, il se
    reformule, et une recherche qui s'appuierait dessus marcherait
    aujourd'hui et plus demain.
    """
    recherche = (recherche or '').strip()
    if not recherche:
        return traces
    fiches = fiches_du_centre(request).filter(
        Q(code_patient__icontains=recherche) | Q(nom__icontains=recherche)
        | Q(prenoms__icontains=recherche)
        | Q(ancien_identifiant__icontains=recherche)).values('pk')
    return traces.filter(Q(object_id__in=fiches)
                         | Q(user__username__icontains=recherche))


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
def doublons_journal(request):
    recherche = request.GET.get('q', '')
    traces = _filtrer_traces(
        request, journal_doublons.traces(centre_actif(request)), recherche)
    pages = Paginator(traces, 50)
    page = pages.get_page(request.GET.get('page'))
    fiches = {p.pk: p for p in fiches_du_centre(request).filter(
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
        'q': recherche,
        'qs_base': _sans_page(request),
        'titre': 'Créations forcées et confirmations',
    })


# ── Les actions en lot ──────────────────────────────────────────────────────

#: Au-delà, on ne fait pas attendre un navigateur : la fusion coûte un sixième
#: de seconde par groupe, et le masquage reste rapide mais pas gratuit.
LOT_EN_TACHE_DE_FOND = 40


def _permission_du_lot(action):
    return ('patients.fusionner_patients' if action == 'fusionner'
            else 'patients.gerer_doublons')


def _cles_demandees(request, filtres):
    """Les groupes visés : ceux cochés, ou tout le relevé filtré.

    « Tout le filtre » n'envoie pas neuf cents clés dans un formulaire : il
    envoie le filtre, et le serveur refait le tri lui-même. C'est moins de
    réseau, et surtout c'est le serveur qui décide de ce qu'il traite.
    """
    if request.POST.get('tout'):
        _releve, lignes, _totaux = _releve_filtre(request, filtres)
        return [ligne['cle'] for ligne in lignes]
    return request.POST.getlist('cle')


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
@require_POST
def doublons_lot_preparer(request):
    """Fige la sélection et montre ce qui va être fait, avant de le faire."""
    from .doublons_lots import LotRefuse, examiner, preparer

    action = request.POST.get('action', '')
    if action not in dict(LotDoublons.ACTIONS):
        raise Http404('Action inconnue.')
    if not request.user.has_perm(_permission_du_lot(action)):
        raise PermissionDenied("Vous n'avez pas le droit de fusionner.")

    filtres = _filtres_demandes(request.POST)
    cles = _cles_demandees(request, filtres)
    if not cles:
        messages.error(request, "Aucun groupe n'était sélectionné.")
        return redirect(request.POST.get('retour') or 'patients:doublons_liste')

    try:
        # `raison_commune` et non `raison` : ce dernier porte déjà le filtre
        # par raison, qui voyage dans le même formulaire.
        lot = preparer(action, cles, request.user, centre_actif(request),
                       raison=request.POST.get('raison_commune', ''))
    except LotRefuse as refus:
        messages.error(request, str(refus))
        return redirect(request.POST.get('retour') or 'patients:doublons_liste')

    prevus, ignores = examiner(action, cles, fiches_du_centre(request))
    return render(request, 'patients/doublons/lot_confirmer.html', {
        'lot': lot,
        'prevus': prevus,
        'ignores': ignores,
        'retour': request.POST.get('retour') or reverse('patients:doublons_liste'),
        'titre': dict(LotDoublons.ACTIONS)[action] + ' en lot',
    })


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
@require_POST
def doublons_lot_executer(request, pk):
    """Applique la liste figée — ici même, ou en tâche de fond si elle est longue."""
    from core import taches
    from .doublons_lots import LotRefuse, executer

    lot = get_object_or_404(LotDoublons.all_objects, pk=pk,
                            centre=centre_actif(request), etat='prepare')
    if not request.user.has_perm(_permission_du_lot(lot.action)):
        raise PermissionDenied("Vous n'avez pas le droit de fusionner.")
    retour = request.POST.get('retour') or reverse('patients:doublons_liste')

    if len(lot.cles) > LOT_EN_TACHE_DE_FOND:
        return _lancer_en_tache(request, lot, retour)
    try:
        executer(lot, fiches_du_centre(request), request.user)
    except LotRefuse as refus:
        messages.error(request, str(refus))
        return redirect(retour)
    return render(request, 'patients/doublons/lot_bilan.html',
                  {'lot': lot, 'retour': retour, 'titre': 'Bilan du lot'})


def _lancer_en_tache(request, lot, retour):
    """Le lot part en tâche de fond, avec la jauge du projet.

    Le périmètre est refait dans le fil : il porte le centre, et le centre
    actif est posé par `taches.lancer` pour la durée du travail.
    """
    from core import taches
    from .doublons_lots import executer

    centre = centre_actif(request)
    utilisateur = request.user

    def travail(avancement):
        avancement.etape('Préparation…', total=len(lot.cles))
        perimetre = Patient.all_objects.filter(centre=centre)
        executer(lot, perimetre, utilisateur, avancement)
        avancement.enregistrer()
        return (f'{len(lot.faits)} groupe(s) traité(s), '
                f'{len(lot.ignores) + len(lot.ecartes)} ignoré(s).')

    tache = taches.lancer(f'{lot.get_action_display()} en lot — {lot.numero}',
                          utilisateur, centre, travail)
    LotDoublons.all_objects.filter(pk=lot.pk).update(tache=tache)
    return redirect(f"{reverse('patients:doublons_lots')}?tache={tache.pk}")


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
def doublons_lots(request):
    """Le journal des lots : ce qui a été fait en masse, et de quoi le défaire."""
    lots = (LotDoublons.all_objects.filter(centre=centre_actif(request))
            .exclude(etat='prepare').select_related('utilisateur', 'annule_par'))
    recherche = (request.GET.get('q') or '').strip()
    if recherche:
        lots = lots.filter(Q(numero__icontains=recherche)
                           | Q(utilisateur__username__icontains=recherche))
    pages = Paginator(lots, 50)
    page = pages.get_page(request.GET.get('page'))
    return render(request, 'patients/doublons/lots.html', {
        'page': page,
        'lots': page.object_list,
        'q': recherche,
        'qs_base': _sans_page(request),
        'titre': 'Actions en lot',
    })


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
@require_POST
def doublons_lot_annuler(request, pk):
    """Défait un lot entier, et dit ce qui n'a pas pu l'être."""
    from .doublons_lots import LotRefuse, annuler

    lot = get_object_or_404(LotDoublons.all_objects, pk=pk,
                            centre=centre_actif(request))
    if not request.user.has_perm(_permission_du_lot(lot.action)):
        raise PermissionDenied("Vous n'avez pas le droit de fusionner.")
    try:
        restants = annuler(lot, fiches_du_centre(request), request.user)
    except LotRefuse as refus:
        messages.error(request, str(refus))
        return redirect('patients:doublons_lots')
    if restants:
        messages.error(
            request,
            f'{lot.numero} annulé, sauf {len(restants)} groupe(s) : '
            + ' ; '.join(f'{cle} — {raison}' for cle, raison in restants[:3])
            + ('…' if len(restants) > 3 else ''))
    else:
        messages.success(request, f'{lot.numero} a été entièrement annulé.')
    return redirect('patients:doublons_lots')


# ── L'onglet des fiches masquées ────────────────────────────────────────────

#: Les mêmes cinquante lignes que les deux autres journaux du menu.
PAR_PAGE_MASQUEES = 50


def _filtrer_masquees(fiches, recherche):
    """Par nom, prénoms, code ou ancien identifiant.

    L'ancien identifiant compte autant que le code : c'est lui qui figure sur
    les cartes imprimées, et c'est avec lui qu'on vient chercher une fiche
    qu'on ne retrouve plus ailleurs.
    """
    recherche = (recherche or '').strip()
    if not recherche:
        return fiches
    condition = Q()
    for champ in ('nom', 'prenoms', 'code_patient', 'ancien_identifiant'):
        condition |= Q(**{f'{champ}__icontains': recherche})
    return fiches.filter(condition)


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
def doublons_masquees(request):
    """Les fiches retirées à la main : le seul endroit où elles se voient.

    Une fiche masquée est introuvable partout ailleurs — recherche, listes,
    sélecteurs, adresse directe. Sans cet onglet, la rendre de nouveau
    visible demanderait de passer par l'admin, ou de se souvenir du groupe
    d'où elle a été retirée.
    """
    recherche = request.GET.get('q', '')
    fiches = _filtrer_masquees(
        fiches_du_centre(request).filter(masque=True)
        .select_related('doublon_de', 'masque_par')
        .order_by('-masque_le', '-pk'), recherche)
    pages = Paginator(fiches, PAR_PAGE_MASQUEES)
    page = pages.get_page(request.GET.get('page'))
    affichees = list(page.object_list)
    for fiche in affichees:
        # « ≈ 1996 » quand la date n'est qu'estimée : la même écriture que sur
        # les cartes, sinon la liste promettrait une date qu'on n'a pas.
        fiche.naissance = naissance_affichee(fiche)
    return render(request, 'patients/doublons/masquees.html', {
        'page': page,
        'fiches': affichees,
        'q': recherche,
        'qs_base': _sans_page(request),
        'titre': 'Fiches masquées',
    })


# ── La suppression définitive ───────────────────────────────────────────────

def _reserve_aux_super_utilisateurs(vue):
    """`is_superuser`, et non une permission.

    Une permission se donne à un groupe, et un groupe s'élargit sans qu'on y
    pense. Ce geste-là ne doit s'élargir par mégarde.
    """
    @wraps(vue)
    def enveloppe(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied(
                'La suppression définitive est réservée aux '
                'super-utilisateurs.')
        return vue(request, *args, **kwargs)
    return enveloppe


@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@exige_un_centre
@_reserve_aux_super_utilisateurs
def doublons_supprimer(request, pk):
    """Montre ce que la suppression emporte, puis l'exécute.

    Deux temps, et pas un bouton : on lit ce qui part, on tape le code, et
    seulement alors la fiche s'efface. Les contrôles sont refaits au moment
    de supprimer — entre l'affichage et le clic, quelqu'un a pu rattacher
    quelque chose à cette fiche.
    """
    from .suppression import (SuppressionRefusee, ce_qui_part, etat,
                              obstacles, supprimer)

    fiche = fiche_du_centre(request, pk)
    retour = (request.POST.get('retour') or request.GET.get('retour')
              or reverse('patients:doublons_masquees'))
    empechements = obstacles(fiche)
    erreur = ''

    if request.method == 'POST' and not empechements:
        if (request.POST.get('code') or '').strip().upper() != fiche.code_patient:
            erreur = ("Le code tapé ne correspond pas à celui de la fiche.")
        else:
            try:
                supprimer(fiche, request.user)
            except SuppressionRefusee as refus:
                erreur = str(refus)
            else:
                messages.success(
                    request,
                    f'{fiche.code_patient} a été supprimée définitivement. '
                    'La trace en est conservée.')
                return redirect(retour)

    return render(request, 'patients/doublons/supprimer.html', {
        'fiche': fiche,
        'etat': etat(fiche),
        'remplacante': fiche.remplacee_par,
        'obstacles': empechements,
        'emporte': ce_qui_part(fiche),
        'erreur': erreur,
        'retour': retour,
        'titre': 'Supprimer définitivement',
    })


# ── Le recalcul à la demande ────────────────────────────────────────────────

@login_required
@permission_required('patients.gerer_doublons', raise_exception=True)
@require_POST
@exige_un_centre
def doublons_recalculer(request):
    from .doublons_recalcul import RecalculDejaEnCours, recalculer_centre

    centre = centre_actif(request)

    def travail(avancement):
        nombre = recalculer_centre(centre.pk, avancement)
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

    Au passage, les totaux rattachés gardés une minute sont oubliés : sans
    cela le filtre « aucune donnée » continuerait de proposer des groupes
    qu'on vient de traiter.
    """
    from .doublons_recalcul import recalculer_fiche
    from .liens_patient import oublier_les_totaux

    oublier_les_totaux()
    try:
        recalculer_fiche(Patient.all_objects.get(pk=fiche.pk))
    except Exception:
        # Le passage de nuit rattrapera : ne pas faire tomber l'écran pour ça.
        pass
