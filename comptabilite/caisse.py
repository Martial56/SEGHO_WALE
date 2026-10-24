"""
Règles des sessions de caisse (voir comptabilite/models.py pour le principe).

Les vues et la facturation passent toutes par ici : ouvrir, retrouver la
session d'une caissière, résumer ce qu'elle a encaissé, compter sa pochette,
clôturer, valider, clôturer la journée. Une règle écrite deux fois finit
toujours par diverger.
"""
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import JourneeCaisse, SessionCaissiere, coupures

ZERO = Decimal('0')


class ErreurCaisse(Exception):
    """Refus d'une opération de caisse, avec un message pour l'utilisateur."""


# ─── Qui fait quoi ─────────────────────────────────────────────────────────────

def peut_encaisser(user):
    return user.is_authenticated and user.has_perm('facturation.can_encaisser')


def peut_superviser(user):
    return user.is_authenticated and user.has_perm('comptabilite.superviser_caisse')


def doit_ouvrir_sa_caisse(user):
    """Une caissière (droit d'encaisser) qui n'a pas de session utilisable.

    Les superutilisateurs ont tous les droits, donc celui d'encaisser : on ne
    les envoie pas d'office ouvrir une caisse à chaque connexion. Ils doivent
    quand même en ouvrir une pour encaisser (voir `session_pour_encaisser`).
    """
    return (peut_encaisser(user) and not user.is_superuser
            and session_pour_encaisser(user) is None)


def caisses_autorisees(user):
    """Caisses actives que cette personne peut ouvrir.

    Une caisse sans caissière désignée reste ouverte à toute personne qui a le
    droit d'encaisser : sans cela, toutes les caisses deviendraient
    inaccessibles le jour de la mise en service, avant que quiconque ait eu le
    temps de les configurer.
    """
    from facturation.models import Caisse
    qs = Caisse.objects.filter(actif=True)
    if not user.is_superuser:
        qs = qs.filter(Q(caissiers=user) | Q(caissiers__isnull=True)).distinct()
    return qs.order_by('nom')


# ─── Retrouver la session ──────────────────────────────────────────────────────

def session_ouverte(user):
    """La session ouverte de cette caissière, quel que soit son jour.

    `all_objects` : la session suit la caissière, pas le centre sélectionné à
    l'écran ni l'ordinateur.
    """
    if not user.is_authenticated:
        return None
    return (SessionCaissiere.all_objects
            .select_related('journee__caisse', 'caissiere')
            .filter(caissiere=user, statut='ouverte').first())


def session_pour_encaisser(user):
    """Session dans laquelle ranger un encaissement, ou None.

    Une session ouverte un jour précédent ne sert plus : l'argent du jour irait
    dans la pochette de la veille et fausserait les deux bilans. Elle doit
    d'abord être clôturée.
    """
    session = session_ouverte(user)
    if session and session.est_du_jour:
        return session
    return None


def message_sans_session(user):
    session = session_ouverte(user)
    if session:
        return (f"Votre session du {session.journee.date_journee:%d/%m/%Y} sur "
                f"{session.caisse} n'est pas clôturée. Clôturez-la avant d'encaisser.")
    return "Ouvrez votre caisse avant d'encaisser (menu Comptabilité → Ma caisse)."


# ─── Ouvrir ────────────────────────────────────────────────────────────────────

def montant(valeur, defaut=ZERO):
    """Montant saisi, ou `defaut` s'il est vide, illisible ou négatif."""
    try:
        m = Decimal(str(valeur).replace(' ', '').replace(',', '.'))
    except (InvalidOperation, TypeError, ValueError):
        return defaut
    return m if m >= 0 else defaut


def fonds_propose(user, caisse):
    """Fonds de la dernière session de cette caissière sur cette caisse : avec
    des pochettes séparées, chacune reçoit en général le même fonds chaque jour."""
    derniere = (SessionCaissiere.all_objects
                .filter(caissiere=user, journee__caisse=caisse)
                .order_by('-date_ouverture').first())
    return derniere.fonds_initial if derniere else ZERO


def ouvrir_session(user, caisse, fonds_initial):
    if not peut_encaisser(user):
        raise ErreurCaisse("Vous n'avez pas le droit d'encaisser.")
    if session_ouverte(user):
        raise ErreurCaisse("Vous avez déjà une session ouverte. Clôturez-la avant d'en ouvrir une autre.")
    if not caisses_autorisees(user).filter(pk=caisse.pk).exists():
        raise ErreurCaisse(f"Vous n'êtes pas habilitée à utiliser la caisse {caisse}.")

    aujourdhui = timezone.localdate()
    try:
        with transaction.atomic():
            journee, _ = JourneeCaisse.all_objects.get_or_create(
                caisse=caisse, date_journee=aujourdhui,
                defaults={'ouverte_par': user})
            if not journee.est_ouverte:
                raise ErreurCaisse(
                    f"La journée du {aujourdhui:%d/%m/%Y} de {caisse} est déjà clôturée. "
                    "Un superviseur peut la rouvrir.")
            return SessionCaissiere.objects.create(
                journee=journee, caissiere=user, fonds_initial=fonds_initial,
                centre=journee.centre)
    except IntegrityError:
        # Deux clics, ou deux onglets : la contrainte « une session ouverte
        # par caissière » a joué. La session existe, on la rend.
        session = session_ouverte(user)
        if session:
            return session
        raise ErreurCaisse("L'ouverture n'a pas pu aboutir, réessayez.")


# ─── Résumer ───────────────────────────────────────────────────────────────────

def resume_session(session):
    """Ce que la caissière a encaissé, et les espèces qu'elle doit avoir.

    Espèces attendues = fonds remis + espèces encaissées − remboursements en
    espèces faits dans cette session − sorties de caisse payées. Le
    remboursement d'une facture annulée sort de la pochette de la personne qui
    rend l'argent (voir `Avoir.session`), pas de celle qui l'avait encaissé.
    Les autres modes (Mobile Money, chèque, virement…) sont listés à part : ils
    ne sont pas dans la pochette.
    """
    from facturation.models import Facture, Paiement
    from .models import Avoir, SortieCaisse

    paiements = list(Paiement.all_objects.filter(session=session)
                     .select_related('facture__patient').order_by('date_paiement'))
    libelles_modes = dict(Paiement.MODE)
    libelles_types = dict(Facture.TYPE)

    par_mode, par_nature = {}, {}
    especes = ZERO
    for p in paiements:
        ligne = par_mode.setdefault(p.mode_paiement, {
            'code': p.mode_paiement, 'libelle': libelles_modes.get(p.mode_paiement, p.mode_paiement),
            'montant': ZERO, 'nb': 0})
        ligne['montant'] += p.montant
        ligne['nb'] += 1
        nature = libelles_types.get(p.facture.type_facture, p.facture.type_facture)
        par_nature[nature] = par_nature.get(nature, ZERO) + p.montant
        if p.mode_paiement == 'especes':
            especes += p.montant

    avoirs = list(Avoir.all_objects.filter(session=session)
                  .select_related('facture__patient').order_by('date_creation'))
    rembourse = sum((a.montant_rembourse for a in avoirs if a.mode_remboursement == 'especes'), ZERO)
    sorties = list(SortieCaisse.all_objects.filter(session=session)
                   .select_related('motif').order_by('date_demande'))
    sorties_payees = sum((s.montant for s in sorties if s.statut == 'payee'), ZERO)
    sorties_en_attente = [s for s in sorties if s.statut == 'en_attente']

    ordre = [code for code, _ in Paiement.MODE]
    modes = sorted(par_mode.values(), key=lambda m: ordre.index(m['code']) if m['code'] in ordre else 99)
    autres = sum((m['montant'] for m in modes if m['code'] != 'especes'), ZERO)
    return {
        'paiements': paiements,
        'nb_paiements': len(paiements),
        'total_encaisse': especes + autres,
        'par_mode': modes,
        'par_nature': sorted(par_nature.items(), key=lambda kv: -kv[1]),
        'especes_encaissees': especes,
        'avoirs': avoirs,
        'especes_remboursees': rembourse,
        'sorties': sorties,
        'sorties_payees': sorties_payees,
        'sorties_en_attente': sorties_en_attente,
        'autres_modes': autres,
        'fonds_initial': session.fonds_initial,
        'especes_attendues': session.fonds_initial + especes - rembourse - sorties_payees,
    }


def lire_billetage(donnees):
    """Nombre de billets et pièces par coupure, lus dans `donnees` (le POST).

    Rend (billetage, total) : les quantités vides ou illisibles comptent 0,
    les négatives sont refusées.
    """
    billetage, total = {}, ZERO
    for cle, valeur, _ in coupures():
        brut = (donnees.get(f'n_{cle}') or '').strip()
        if not brut:
            continue
        try:
            n = int(brut)
        except ValueError:
            raise ErreurCaisse(f"Quantité illisible pour {cle[1:]} F : « {brut} ».")
        if n < 0:
            raise ErreurCaisse("Une quantité de billets ou de pièces ne peut pas être négative.")
        if n:
            billetage[cle] = n
            total += Decimal(valeur) * n
    return billetage, total


# ─── Clôturer, valider ─────────────────────────────────────────────────────────

def cloturer_session(session, par, billetage, total_compte, justification='', motif_office=''):
    if not session.est_ouverte:
        raise ErreurCaisse("Cette session est déjà clôturée.")
    d_office = par.pk != session.caissiere_id
    if d_office:
        if not peut_superviser(par):
            raise ErreurCaisse("Seule la caissière ou un superviseur peut clôturer cette session.")
        if not motif_office.strip():
            raise ErreurCaisse("Le motif est obligatoire pour clôturer la session d'une autre personne.")

    resume = resume_session(session)
    if resume['sorties_en_attente']:
        raise ErreurCaisse("Des sorties de caisse attendent encore la décision du superviseur. "
                           "Faites-les valider ou annulez-les avant de clôturer.")
    attendu = resume['especes_attendues']
    ecart = total_compte - attendu
    if ecart and not justification.strip():
        raise ErreurCaisse(
            f"Écart de {'+' if ecart > 0 else ''}{_francs(ecart)} F entre le comptage et les "
            "espèces attendues : une justification est obligatoire.")

    session.statut = 'cloturee'
    session.date_cloture = timezone.now()
    session.cloturee_par = par
    session.cloture_d_office = d_office
    session.motif_cloture_d_office = motif_office.strip()
    session.billetage = billetage
    session.montant_theorique = attendu
    session.montant_compte = total_compte
    session.ecart = ecart
    session.justification_ecart = justification.strip()
    session.save()
    return session


def valider_session(session, par, observation=''):
    """Le superviseur reconnaît le comptage et la remise des espèces.

    Une caissière ne valide pas sa propre session : c'est tout l'intérêt d'un
    second regard. Un superutilisateur garde la main, pour les petites
    structures où il est seul.
    """
    if not peut_superviser(par):
        raise ErreurCaisse("Vous n'avez pas le droit de valider une session.")
    if session.statut != 'cloturee':
        raise ErreurCaisse("Seule une session clôturée peut être validée.")
    if par.pk == session.caissiere_id and not par.is_superuser:
        raise ErreurCaisse("Une caissière ne valide pas sa propre session.")
    session.statut = 'validee'
    session.validee_par = par
    session.date_validation = timezone.now()
    session.observation_validation = observation.strip()
    session.save()
    return session


# ─── Journée ───────────────────────────────────────────────────────────────────

def peut_cloturer_journee(user, journee):
    """Le superviseur, ou une caissière qui a travaillé sur cette journée."""
    return peut_superviser(user) or journee.sessions.filter(caissiere=user).exists()


def cloturer_journee(journee, par, observations=''):
    if not journee.est_ouverte:
        raise ErreurCaisse("Cette journée est déjà clôturée.")
    if not peut_cloturer_journee(par, journee):
        raise ErreurCaisse("Seul un superviseur ou une caissière de cette journée peut la clôturer.")
    encore = [s.nom_caissiere for s in journee.sessions_ouvertes().select_related('caissiere')]
    if encore:
        raise ErreurCaisse("Sessions encore ouvertes : " + ", ".join(encore)
                           + ". Chacune doit être clôturée avant la journée.")
    journee.statut = 'cloturee'
    journee.date_cloture = timezone.now()
    journee.cloturee_par = par
    if observations.strip():
        journee.observations = observations.strip()
    journee.save()
    return journee


def rouvrir_journee(journee, par):
    if not peut_superviser(par):
        raise ErreurCaisse("Seul un superviseur peut rouvrir une journée.")
    if journee.est_ouverte:
        raise ErreurCaisse("Cette journée est déjà ouverte.")
    journee.statut = 'ouverte'
    journee.date_cloture = None
    journee.cloturee_par = None
    journee.save()
    return journee


def resume_journee(journee):
    """Une ligne par session — ce que chaque caissière a encaissé sur cette
    caisse ce jour-là — et les totaux de la caisse."""
    lignes = []
    totaux = {'nb_paiements': 0, 'especes': ZERO, 'autres': ZERO, 'rembourse': ZERO,
              'sorties': ZERO, 'fonds': ZERO, 'attendu': ZERO, 'compte': ZERO, 'ecart': ZERO}
    for session in journee.sessions.select_related('caissiere').order_by('date_ouverture'):
        r = resume_session(session)
        attendu = session.montant_theorique if session.montant_theorique is not None else r['especes_attendues']
        lignes.append({'session': session, 'resume': r, 'attendu': attendu})
        totaux['nb_paiements'] += r['nb_paiements']
        totaux['especes'] += r['especes_encaissees']
        totaux['autres'] += r['autres_modes']
        totaux['rembourse'] += r['especes_remboursees']
        totaux['sorties'] += r['sorties_payees']
        totaux['fonds'] += session.fonds_initial
        totaux['attendu'] += attendu
        totaux['compte'] += session.montant_compte or ZERO
        totaux['ecart'] += session.ecart or ZERO
    totaux['total_encaisse'] = totaux['especes'] + totaux['autres']
    return {'lignes': lignes, 'totaux': totaux,
            'toutes_closes': all(not l['session'].est_ouverte for l in lignes)}


# ─── Sorties de caisse ─────────────────────────────────────────────────────────

def _session_active_de(user, session):
    if session.caissiere_id != user.pk or not session.est_ouverte or not session.est_du_jour:
        raise ErreurCaisse("Une sortie se fait depuis votre propre session ouverte aujourd'hui.")


def _francs(montant):
    return f"{montant:,.0f}".replace(',', ' ')


def creer_sortie(session, par, motif, libelle, montant, beneficiaire='', justificatif=None):
    """Sous le seuil de la caisse, la sortie est payée tout de suite ; au-dessus,
    elle attend le superviseur et l'argent reste dans la pochette."""
    from .models import SortieCaisse
    _session_active_de(par, session)
    if montant <= 0:
        raise ErreurCaisse("Le montant de la sortie doit être positif.")
    if not libelle.strip():
        raise ErreurCaisse("Précisez l'objet de la sortie.")
    disponible = resume_session(session)['especes_attendues']
    if montant > disponible:
        raise ErreurCaisse(f"Votre pochette ne contient que {_francs(disponible)} F : "
                           "la sortie ne peut pas dépasser ce montant.")
    immediate = montant <= session.caisse.seuil_sortie
    return SortieCaisse.objects.create(
        session=session, motif=motif, libelle=libelle.strip(), beneficiaire=beneficiaire.strip(),
        montant=montant, justificatif=justificatif or '', demandee_par=par,
        statut='payee' if immediate else 'en_attente',
        date_paiement=timezone.now() if immediate else None, centre=session.centre)


def decider_sortie(sortie, par, accepter, observation=''):
    if not peut_superviser(par):
        raise ErreurCaisse("Seul un superviseur décide d'une sortie au-delà du seuil.")
    if sortie.statut != 'en_attente':
        raise ErreurCaisse("Cette sortie a déjà été traitée.")
    if par.pk == sortie.demandee_par_id and not par.is_superuser:
        raise ErreurCaisse("On ne valide pas sa propre demande de sortie.")
    if accepter:
        session = sortie.session
        if not session.est_ouverte:
            raise ErreurCaisse("La session de la caissière est clôturée : la sortie ne peut plus être payée.")
        disponible = resume_session(session)['especes_attendues']
        if sortie.montant > disponible:
            raise ErreurCaisse(f"La pochette ne contient plus que {_francs(disponible)} F.")
        sortie.statut = 'payee'
        sortie.date_paiement = timezone.now()
    else:
        if not observation.strip():
            raise ErreurCaisse("Indiquez la raison du refus.")
        sortie.statut = 'refusee'
    sortie.decidee_par = par
    sortie.date_decision = timezone.now()
    sortie.observation = observation.strip()
    sortie.save()
    return sortie


def annuler_demande_sortie(sortie, par):
    if sortie.statut != 'en_attente':
        raise ErreurCaisse("Seule une demande en attente peut être annulée.")
    if par.pk != sortie.demandee_par_id and not peut_superviser(par):
        raise ErreurCaisse("Seule la personne qui a fait la demande peut l'annuler.")
    sortie.statut = 'annulee'
    sortie.save(update_fields=['statut'])
    return sortie


# ─── Avoirs et remboursements ──────────────────────────────────────────────────

def preparer_remboursement(user, montant, mode):
    """Session d'où sortira le remboursement, après contrôle.

    En espèces, l'argent sort de la pochette de la personne qui rembourse :
    elle doit avoir une session ouverte aujourd'hui, et assez d'espèces. Par
    un autre mode, la session est notée si elle existe, sans être exigée.
    """
    from facturation.models import Paiement
    if montant <= 0:
        return None
    if mode not in dict(Paiement.MODE):
        raise ErreurCaisse("Mode de remboursement inconnu.")
    session = session_pour_encaisser(user)
    if mode == 'especes':
        if session is None:
            raise ErreurCaisse("Pour rembourser en espèces, ouvrez d'abord votre caisse : "
                               "l'argent sort de votre pochette.")
        disponible = resume_session(session)['especes_attendues']
        if montant > disponible:
            raise ErreurCaisse(f"Votre pochette ne contient que {_francs(disponible)} F : "
                               "remboursement impossible en espèces. Choisissez un autre mode "
                               "ou demandez un complément au superviseur.")
    return session


def creer_avoir(facture, par, motif, mode_remboursement='especes', reference='', session=None):
    """Avoir du montant de la facture ; le remboursement porte sur ce que le
    patient avait réellement payé."""
    from .models import Avoir
    rembourse = facture.montant_paye or ZERO
    return Avoir.objects.create(
        facture=facture, montant=facture.montant_total, motif=motif,
        montant_rembourse=rembourse,
        mode_remboursement=mode_remboursement if rembourse > 0 else '',
        reference=reference, session=session, cree_par=par,
        centre=facture.centre)
