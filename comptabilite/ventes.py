"""Documents des ventes : ce que chaque caisse a vendu, présenté comme les
« Documents des ventes » de Sage 100 Gestion commerciale.

Un document (type FA) par session de caissière **validée par le
superviseur** : le client est la caisse, le représentant la caissière, les
lignes celles des factures encaissées dans la session. Une facture payée en
plusieurs fois appartient à la session de son premier encaissement, pour ne
jamais être vendue deux fois ; une facture annulée n'est plus une vente.

Le statut suit la comptabilité : « À comptabiliser » tant qu'une écriture de
la session (factures, paiements) manque ou reste en brouillon, puis
« Comptabilisé ».
"""
from collections import OrderedDict
from decimal import Decimal

ZERO = Decimal('0')


def _premiere_session(facture_ids):
    """{facture_id: session_id} : la session du premier encaissement."""
    from facturation.models import Paiement
    premiere = {}
    for facture_id, session_id in (Paiement.all_objects.filter(facture_id__in=facture_ids, session__isnull=False)
                                   .order_by('date_paiement', 'pk').values_list('facture_id', 'session_id')):
        premiere.setdefault(facture_id, session_id)
    return premiere


def _factures_par_session(sessions):
    """{session_id: [facture_id]} des ventes de chaque session."""
    from facturation.models import Facture, Paiement
    ids = {s.pk for s in sessions}
    encaissees = set(Paiement.all_objects.filter(session_id__in=ids).values_list('facture_id', flat=True))
    vivantes = set(Facture.all_objects.filter(pk__in=encaissees).exclude(statut='annulee')
                   .values_list('pk', flat=True))
    resultat = {pk: [] for pk in ids}
    for facture_id, session_id in _premiere_session(vivantes).items():
        if session_id in resultat:
            resultat[session_id].append(facture_id)
    return resultat


def _statut(session, facture_ids):
    """« comptabilise » si toutes les écritures de la session sont validées."""
    from facturation.models import Paiement
    from .models import Ecriture
    origines = {f'facture:{pk}' for pk in facture_ids}
    origines |= {f'paiement:{pk}' for pk in Paiement.all_objects.filter(session=session).values_list('pk', flat=True)}
    if not origines:
        return 'comptabilise'
    validees = Ecriture.all_objects.filter(origine__in=origines, statut='validee').count()
    return 'comptabilise' if validees == len(origines) else 'a_comptabiliser'


STATUTS = OrderedDict([('a_comptabiliser', 'À comptabiliser'), ('comptabilise', 'Comptabilisé')])


def _client(caisse, comptes_caisse):
    compte = comptes_caisse.get(f'caisse:{caisse.code}')
    return (compte.numero if compte else ''), f'CLIENT {caisse.nom}'.upper()


def _comptes_caisse():
    from .models import Correspondance
    return {c.cle: c.compte for c in Correspondance.objects.filter(cle__startswith='caisse:').select_related('compte')}


def documents(debut, fin, caisse=None, statut=None):
    """Documents des ventes des sessions validées dont la journée est dans la période."""
    from facturation.models import LigneFacture
    from .models import SessionCaissiere
    sessions = list(SessionCaissiere.objects.filter(statut='validee', journee__date_journee__range=[debut, fin])
                    .select_related('journee__caisse', 'caissiere')
                    .order_by('-journee__date_journee', 'journee__caisse__nom', 'numero'))
    if caisse:
        sessions = [s for s in sessions if s.journee.caisse_id == caisse.pk]
    factures = _factures_par_session(sessions)
    totaux = {}
    for l in LigneFacture.objects.filter(facture_id__in=[f for fs in factures.values() for f in fs]):
        totaux[l.facture_id] = totaux.get(l.facture_id, ZERO) + l.montant_ligne
    comptes_caisse = _comptes_caisse()
    resultat = []
    for s in sessions:
        etat = _statut(s, factures[s.pk])
        if statut and etat != statut:
            continue
        numero_client, intitule_client = _client(s.journee.caisse, comptes_caisse)
        resultat.append({
            'session': s, 'type': 'FA', 'statut': etat, 'statut_libelle': STATUTS[etat],
            'piece': s.numero, 'date': s.journee.date_journee, 'caisse': s.journee.caisse,
            'numero_client': numero_client, 'intitule_client': intitule_client,
            'representant': s.nom_caissiere, 'nb_factures': len(factures[s.pk]),
            'total': sum((totaux.get(f, ZERO) for f in factures[s.pk]), ZERO),
        })
    return resultat


def _reference(ligne):
    if ligne.article_id and ligne.article.reference_interne:
        return ligne.article.reference_interne
    if ligne.produit_id and ligne.produit.code:
        return ligne.produit.code
    if ligne.acte_id:
        return ligne.acte.code
    return ''


def document(session):
    """Le document d'une session : en-tête, lignes regroupées par article et
    prix, factures reprises."""
    from facturation.models import Facture, LigneFacture
    facture_ids = _factures_par_session([session])[session.pk]
    regroupees = OrderedDict()
    for l in (LigneFacture.objects.filter(facture_id__in=facture_ids)
              .select_related('article', 'produit', 'acte').order_by('libelle', 'pk')):
        reference = _reference(l)
        cle = (reference, l.libelle, l.prix_unitaire, l.remise)
        if cle not in regroupees:
            regroupees[cle] = {'reference': reference, 'designation': l.libelle, 'prix_unitaire': l.prix_unitaire,
                               'remise': l.remise, 'quantite': ZERO, 'montant': ZERO}
        regroupees[cle]['quantite'] += l.quantite
        regroupees[cle]['montant'] += l.montant_ligne
    lignes = sorted(regroupees.values(), key=lambda x: (x['reference'] or '~', x['designation']))
    etat = _statut(session, facture_ids)
    numero_client, intitule_client = _client(session.journee.caisse, _comptes_caisse())
    return {
        'session': session, 'type': 'FA', 'statut': etat, 'statut_libelle': STATUTS[etat],
        'piece': session.numero, 'date': session.journee.date_journee, 'caisse': session.journee.caisse,
        'numero_client': numero_client, 'intitule_client': intitule_client,
        'representant': session.nom_caissiere, 'lignes': lignes,
        'total': sum((l['montant'] for l in lignes), ZERO),
        'factures': list(Facture.all_objects.filter(pk__in=facture_ids).select_related('patient').order_by('numero')),
    }
