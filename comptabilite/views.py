"""Écrans des sessions de caisse : ouvrir, suivre, compter, clôturer, valider."""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.views import log_event

from . import caisse as regles
from .models import JourneeCaisse, SessionCaissiere, coupures


def _suite(request, defaut):
    """Adresse de retour transmise par `next`, si elle est sûre."""
    cible = request.POST.get('next') or request.GET.get('next') or ''
    if cible and url_has_allowed_host_and_scheme(cible, allowed_hosts={request.get_host()},
                                                 require_https=request.is_secure()):
        return cible
    return defaut


def _session_visible(request, pk):
    """La caissière voit ses sessions, le superviseur toutes."""
    session = get_object_or_404(
        SessionCaissiere.all_objects.select_related('journee__caisse', 'caissiere'), pk=pk)
    if session.caissiere_id != request.user.pk and not regles.peut_superviser(request.user):
        raise PermissionDenied
    return session


@login_required(login_url='login')
def ouvrir(request):
    """Choix de la caisse et du fonds de caisse, juste après la connexion."""
    if not regles.peut_encaisser(request.user):
        raise PermissionDenied
    suite = _suite(request, reverse('comptabilite:ma_caisse'))

    en_cours = regles.session_ouverte(request.user)
    if en_cours:
        if not en_cours.est_du_jour:
            messages.warning(request, regles.message_sans_session(request.user))
            return redirect('comptabilite:cloturer', pk=en_cours.pk)
        return redirect(suite)

    caisses = list(regles.caisses_autorisees(request.user))
    if request.method == 'POST':
        caisse = next((c for c in caisses if str(c.pk) == request.POST.get('caisse')), None)
        if caisse is None:
            messages.error(request, "Choisissez une caisse.")
        else:
            try:
                session = regles.ouvrir_session(request.user, caisse,
                                                regles.montant(request.POST.get('fonds_initial')))
            except regles.ErreurCaisse as e:
                messages.error(request, str(e))
            else:
                log_event(session, request.user,
                          f'Session ouverte sur {caisse} — fonds {session.fonds_initial:,.0f} F'.replace(',', ' '),
                          type='statut', module='comptabilite')
                messages.success(request, f"Caisse {caisse} ouverte. Bon travail !")
                return redirect(suite)

    aujourdhui = timezone.localdate()
    journees = {j.caisse_id: j for j in JourneeCaisse.all_objects.filter(
        date_journee=aujourdhui, caisse__in=caisses).prefetch_related('sessions__caissiere')}
    choix = [{
        'caisse': c,
        'journee': journees.get(c.pk),
        'presentes': [s.nom_caissiere for s in journees[c.pk].sessions.all() if s.est_ouverte]
                     if c.pk in journees else [],
        'fonds': regles.fonds_propose(request.user, c),
    } for c in caisses]
    return render(request, 'comptabilite/ouvrir.html', {
        'choix': choix, 'suite': suite, 'aujourdhui': aujourdhui,
    })


@login_required(login_url='login')
def ma_caisse(request):
    """La session en cours de la caissière, ou l'invitation à ouvrir sa caisse."""
    session = regles.session_ouverte(request.user)
    if session is None:
        if regles.peut_encaisser(request.user):
            return redirect('comptabilite:ouvrir')
        if regles.peut_superviser(request.user):
            return redirect('comptabilite:journees')
        raise PermissionDenied
    return redirect('comptabilite:session', pk=session.pk)


@login_required(login_url='login')
def session_detail(request, pk):
    session = _session_visible(request, pk)
    resume = regles.resume_session(session)
    return render(request, 'comptabilite/session_detail.html', {
        'session': session, 'resume': resume,
        'peut_superviser': regles.peut_superviser(request.user),
        'est_la_mienne': session.caissiere_id == request.user.pk,
        'billetage': _lignes_billetage(session.billetage),
    })


@login_required(login_url='login')
def session_imprimer(request, pk):
    session = _session_visible(request, pk)
    return render(request, 'comptabilite/session_print.html', {
        'session': session, 'resume': regles.resume_session(session),
        'billetage': _lignes_billetage(session.billetage),
        'imprime_le': timezone.now(),
    })


def _lignes_billetage(billetage):
    lignes = []
    for cle, valeur, libelle in coupures():
        n = (billetage or {}).get(cle, 0)
        if n:
            lignes.append({'libelle': libelle, 'nombre': n, 'total': valeur * n})
    return lignes


@login_required(login_url='login')
def cloturer(request, pk):
    """Comptage de la pochette (billetage) puis clôture de la session."""
    session = _session_visible(request, pk)
    if not session.est_ouverte:
        messages.info(request, "Cette session est déjà clôturée.")
        return redirect('comptabilite:session', pk=session.pk)
    d_office = session.caissiere_id != request.user.pk

    saisie = request.POST if request.method == 'POST' else {}
    if request.method == 'POST':
        try:
            billetage, total = regles.lire_billetage(request.POST)
            regles.cloturer_session(session, request.user, billetage, total,
                                    justification=request.POST.get('justification', ''),
                                    motif_office=request.POST.get('motif_office', ''))
        except regles.ErreurCaisse as e:
            messages.error(request, str(e))
        else:
            texte = (f"Session clôturée — comptées {session.montant_compte:,.0f} F, "
                     f"attendues {session.montant_theorique:,.0f} F, écart {session.ecart:+,.0f} F").replace(',', ' ')
            if session.cloture_d_office:
                texte += f" (d'office : {session.motif_cloture_d_office})"
            log_event(session, request.user, texte, type='statut', module='comptabilite')
            messages.success(request, "Session clôturée. Imprimez le bilan et remettez votre pochette.")
            return redirect('comptabilite:session', pk=session.pk)

    resume = regles.resume_session(session)
    return render(request, 'comptabilite/cloturer.html', {
        'session': session, 'resume': resume, 'd_office': d_office,
        'coupures': [{'cle': c, 'valeur': v, 'libelle': l, 'saisi': saisie.get(f'n_{c}', '')}
                     for c, v, l in coupures()],
        'justification': saisie.get('justification', ''),
        'motif_office': saisie.get('motif_office', ''),
    })


@login_required(login_url='login')
@require_POST
def valider(request, pk):
    session = _session_visible(request, pk)
    try:
        regles.valider_session(session, request.user, request.POST.get('observation', ''))
    except regles.ErreurCaisse as e:
        messages.error(request, str(e))
    else:
        log_event(session, request.user, 'Session validée par le superviseur.',
                  type='statut', module='comptabilite')
        messages.success(request, f"Session {session.numero} validée.")
    return redirect(_suite(request, reverse('comptabilite:session', args=[session.pk])))


# ─── Journées ──────────────────────────────────────────────────────────────────

def _peut_voir_journees(user):
    return regles.peut_encaisser(user) or regles.peut_superviser(user)


@login_required(login_url='login')
def journees(request):
    """Journées de caisse d'une date (aujourd'hui par défaut)."""
    if not _peut_voir_journees(request.user):
        raise PermissionDenied
    try:
        jour = date.fromisoformat(request.GET.get('date', ''))
    except ValueError:
        jour = timezone.localdate()
    qs = (JourneeCaisse.objects.filter(date_journee=jour)
          .select_related('caisse', 'cloturee_par').order_by('caisse__nom'))
    lignes = [{'journee': j, 'resume': regles.resume_journee(j)} for j in qs]
    superviseur = regles.peut_superviser(request.user)
    a_valider = (SessionCaissiere.objects.filter(statut='cloturee')
                 .select_related('journee__caisse', 'caissiere').order_by('date_cloture')
                 if superviseur else [])
    from .models import SortieCaisse
    sorties_a_valider = (SortieCaisse.objects.filter(statut='en_attente')
                         .select_related('session__journee__caisse', 'session__caissiere', 'motif')
                         .order_by('date_demande') if superviseur else [])
    return render(request, 'comptabilite/journees.html', {
        'jour': jour, 'lignes': lignes, 'a_valider': a_valider,
        'sorties_a_valider': sorties_a_valider,
        'aujourdhui': timezone.localdate(),
        'veille': jour.fromordinal(jour.toordinal() - 1),
        'lendemain': jour.fromordinal(jour.toordinal() + 1),
    })


@login_required(login_url='login')
def journee_detail(request, pk):
    if not _peut_voir_journees(request.user):
        raise PermissionDenied
    journee = get_object_or_404(JourneeCaisse.objects.select_related('caisse'), pk=pk)
    return render(request, 'comptabilite/journee_detail.html', {
        'journee': journee, 'resume': regles.resume_journee(journee),
        'peut_cloturer': journee.est_ouverte and regles.peut_cloturer_journee(request.user, journee),
        'peut_superviser': regles.peut_superviser(request.user),
    })


@login_required(login_url='login')
@require_POST
def journee_cloturer(request, pk):
    journee = get_object_or_404(JourneeCaisse, pk=pk)
    try:
        regles.cloturer_journee(journee, request.user, request.POST.get('observations', ''))
    except regles.ErreurCaisse as e:
        messages.error(request, str(e))
    else:
        log_event(journee, request.user, 'Journée de caisse clôturée.', type='statut',
                  module='comptabilite')
        messages.success(request, f"Journée {journee} clôturée.")
        # Les écritures de la journée partent en brouillon, prêtes pour le
        # passage des écritures du comptable.
        from .ecritures import generer
        resultat = generer(journee.date_journee, journee.date_journee)
        if resultat['crees']:
            messages.info(request, f"{resultat['crees']} écriture(s) comptable(s) préparée(s) "
                                   "pour le passage des écritures.")
        for erreur in resultat['erreurs'][:5]:
            messages.warning(request, f"Écriture non préparée — {erreur}")
    return redirect('comptabilite:journee', pk=journee.pk)


@login_required(login_url='login')
@require_POST
def journee_rouvrir(request, pk):
    journee = get_object_or_404(JourneeCaisse, pk=pk)
    try:
        regles.rouvrir_journee(journee, request.user)
    except regles.ErreurCaisse as e:
        messages.error(request, str(e))
    else:
        log_event(journee, request.user, 'Journée de caisse rouverte.', type='statut',
                  module='comptabilite')
        messages.success(request, f"Journée {journee} rouverte.")
    return redirect('comptabilite:journee', pk=journee.pk)


# ─── Sorties de caisse ─────────────────────────────────────────────────────────

@login_required(login_url='login')
def sortie_creer(request, pk):
    """Petite dépense payée depuis la pochette de la caissière."""
    from .forms import SortieForm
    session = _session_visible(request, pk)
    if session.caissiere_id != request.user.pk:
        raise PermissionDenied
    form = SortieForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            sortie = regles.creer_sortie(session, request.user, d['motif'], d['libelle'],
                                         d['montant'], d['beneficiaire'], d['justificatif'],
                                         d.get('convention'))
        except regles.ErreurCaisse as e:
            messages.error(request, str(e))
        else:
            log_event(session, request.user, f'Sortie {sortie.numero} : {sortie.libelle} — '
                      f'{sortie.montant:,.0f} F ({sortie.get_statut_display()})'.replace(',', ' '),
                      type='modif', module='comptabilite')
            if sortie.statut == 'payee':
                messages.success(request, f"Sortie {sortie.numero} enregistrée : remettez l'argent "
                                          "et gardez le justificatif.")
            else:
                messages.info(request, f"Sortie {sortie.numero} au-delà du seuil de la caisse : "
                                       "elle attend la validation du superviseur. Ne remettez pas "
                                       "l'argent avant.")
            return redirect('comptabilite:session', pk=session.pk)
    return render(request, 'comptabilite/sortie_form.html', {
        'session': session, 'form': form,
        'disponible': regles.resume_session(session)['especes_attendues'],
    })


@login_required(login_url='login')
@require_POST
def sortie_decider(request, pk):
    from .models import SortieCaisse
    sortie = get_object_or_404(SortieCaisse.all_objects.select_related('session'), pk=pk)
    accepter = request.POST.get('decision') == 'accepter'
    try:
        regles.decider_sortie(sortie, request.user, accepter, request.POST.get('observation', ''))
    except regles.ErreurCaisse as e:
        messages.error(request, str(e))
    else:
        log_event(sortie.session, request.user,
                  f"Sortie {sortie.numero} {'acceptée' if accepter else 'refusée'} par le superviseur.",
                  type='statut', module='comptabilite')
        messages.success(request, f"Sortie {sortie.numero} {'acceptée' if accepter else 'refusée'}.")
    return redirect(_suite(request, reverse('comptabilite:journees')))


@login_required(login_url='login')
@require_POST
def sortie_annuler(request, pk):
    from .models import SortieCaisse
    sortie = get_object_or_404(SortieCaisse.all_objects.select_related('session'), pk=pk)
    try:
        regles.annuler_demande_sortie(sortie, request.user)
    except regles.ErreurCaisse as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f"Demande de sortie {sortie.numero} annulée.")
    return redirect('comptabilite:session', pk=sortie.session_id)


# ─── État des gratuités ────────────────────────────────────────────────────────

@login_required(login_url='login')
def gratuites(request):
    """Remises et gratuités accordées sur un mois, par motif : l'effort social."""
    import calendar
    from .gratuites import etat_gratuites
    if not (request.user.has_perm('facturation.view_facture') or regles.peut_superviser(request.user)):
        raise PermissionDenied
    aujourdhui = timezone.localdate()
    try:
        annee, mois = (int(x) for x in request.GET.get('mois', '').split('-'))
        debut = date(annee, mois, 1)
    except ValueError:
        debut = aujourdhui.replace(day=1)
    fin = debut.replace(day=calendar.monthrange(debut.year, debut.month)[1])
    precedent = (debut.replace(day=1) - timedelta(days=1)).replace(day=1)
    suivant = fin + timedelta(days=1)
    return render(request, 'comptabilite/gratuites.html', {
        'etat': etat_gratuites(debut, fin), 'debut': debut, 'fin': fin,
        'precedent': precedent, 'suivant': suivant if suivant <= aujourdhui else None,
    })


# ─── Configuration : motifs ────────────────────────────────────────────────────

def _motifs_config(nature):
    from .forms import MotifGratuiteForm, MotifSortieForm
    from .models import MotifGratuite, MotifSortie
    if nature == 'sortie':
        return MotifSortie, MotifSortieForm, 'comptabilite.change_motifsortie', "Motifs de sortie de caisse"
    if nature == 'gratuite':
        return MotifGratuite, MotifGratuiteForm, 'comptabilite.change_motifgratuite', "Motifs de gratuité"
    raise Http404


@login_required(login_url='login')
def motifs(request, nature, pk=None):
    """Liste et saisie des motifs (sortie de caisse ou gratuité) sur un même écran."""
    modele, classe_form, permission, titre = _motifs_config(nature)
    if not request.user.has_perm(permission):
        raise PermissionDenied
    objet = get_object_or_404(modele, pk=pk) if pk else None
    form = classe_form(request.POST or None, instance=objet)
    if request.method == 'POST' and form.is_valid():
        motif = form.save()
        messages.success(request, f"Motif « {motif} » enregistré.")
        return redirect('comptabilite:motifs', nature=nature)
    return render(request, 'comptabilite/motifs.html', {
        'nature': nature, 'titre': titre, 'form': form, 'objet': objet,
        'motifs': modele.objects.all(),
    })
