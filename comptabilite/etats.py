"""
États du module Comptabilité (lot 4).

Chaque état est une fonction `(debut, fin, params) -> dict` qui rend un ou
plusieurs tableaux. Le même résultat sert à l'écran, à l'impression et à
l'export Excel : un chiffre ne peut pas différer d'une forme à l'autre.

    {'titre': …, 'tableaux': [{'titre': …, 'colonnes': [(libellé, genre)],
                                'lignes': [{'type': 'ligne'|'groupe'|'sous_total'|'total',
                                            'cellules': [...], 'lien': url|None}]}],
     'notes': [...]}

`genre` vaut 'texte', 'montant' ou 'nombre' : il dit comment afficher et
aligner la colonne.

Deux familles :
- les états de **caisse et de recettes** lisent directement les paiements,
  sessions et factures — ils sont justes dès l'encaissement, sans attendre la
  comptabilité ;
- les états **comptables** (journal, grand livre, balance, résultat) lisent les
  écritures. Par défaut, seules les écritures validées comptent ; les
  brouillons s'ajoutent sur demande, pour une situation provisoire.

Les écritures et les pièces suivent le centre actif (ModeleCentre) : chaque
centre a ses états.
"""
from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

ZERO = Decimal('0')


def _ligne(*cellules, type_='ligne', lien=None):
    return {'type': type_, 'cellules': list(cellules), 'lien': lien}


def _tableau(titre, colonnes, lignes, vide="Aucune donnée sur la période."):
    return {'titre': titre, 'colonnes': colonnes, 'lignes': lignes, 'vide': vide}


def _jour(dt):
    return timezone.localtime(dt).date() if timezone.is_aware(dt) else dt.date()


# ─── Recettes ──────────────────────────────────────────────────────────────────

def recettes(debut, fin, params):
    """Ce qui est entré, par jour et par caisse, par nature et par mode."""
    from facturation.models import Facture, Paiement
    from .ecritures import nature_de_ligne
    from .models import Avoir, SortieCaisse

    paiements = list(Paiement.objects.filter(date_paiement__date__range=[debut, fin])
                     .select_related('caisse', 'facture'))
    libelles_modes = dict(Paiement.MODE)
    libelles_types = dict(Facture.TYPE)

    # Par jour et par caisse
    caisses = sorted({p.caisse.nom if p.caisse_id else 'Sans caisse' for p in paiements})
    grille = OrderedDict()
    for p in sorted(paiements, key=lambda p: p.date_paiement):
        jour = _jour(p.date_paiement)
        nom = p.caisse.nom if p.caisse_id else 'Sans caisse'
        grille.setdefault(jour, {}).setdefault(nom, ZERO)
        grille[jour][nom] += p.montant
    lignes = []
    totaux = {c: ZERO for c in caisses}
    for jour, par_caisse in grille.items():
        valeurs = [par_caisse.get(c, ZERO) for c in caisses]
        for c, v in zip(caisses, valeurs):
            totaux[c] += v
        lignes.append(_ligne(jour.strftime('%d/%m/%Y'), *valeurs, sum(valeurs, ZERO)))
    if lignes:
        lignes.append(_ligne('Total', *[totaux[c] for c in caisses], sum(totaux.values(), ZERO), type_='total'))
    t1 = _tableau('Encaissements par jour et par caisse',
                  [('Jour', 'texte')] + [(c, 'montant') for c in caisses] + [('Total', 'montant')], lignes)

    # Par mode
    par_mode = OrderedDict((code, [0, ZERO]) for code, _ in Paiement.MODE)
    for p in paiements:
        par_mode.setdefault(p.mode_paiement, [0, ZERO])
        par_mode[p.mode_paiement][0] += 1
        par_mode[p.mode_paiement][1] += p.montant
    lignes = [_ligne(libelles_modes.get(code, code), n, m) for code, (n, m) in par_mode.items() if n]
    if lignes:
        lignes.append(_ligne('Total', len(paiements), sum((p.montant for p in paiements), ZERO), type_='total'))
    t2 = _tableau('Encaissements par mode de paiement',
                  [('Mode', 'texte'), ('Paiements', 'nombre'), ('Montant', 'montant')], lignes)

    # Par nature (au prorata des lignes de chaque facture encaissée)
    par_nature = {}
    for p in paiements:
        facture = p.facture
        lignes_f = list(facture.lignes.select_related('article__categorie'))
        base = sum((l.montant_ligne for l in lignes_f), ZERO)
        if not lignes_f or not base:
            nature = libelles_types.get(facture.type_facture, facture.type_facture)
            par_nature[nature] = par_nature.get(nature, ZERO) + p.montant
            continue
        for l in lignes_f:
            nature = libelles_types.get(nature_de_ligne(l, facture), 'Autre')
            par_nature[nature] = par_nature.get(nature, ZERO) + p.montant * l.montant_ligne / base
    lignes = [_ligne(n, m.quantize(Decimal('1'))) for n, m in sorted(par_nature.items(), key=lambda kv: -kv[1])]
    if lignes:
        lignes.append(_ligne('Total', sum((p.montant for p in paiements), ZERO), type_='total'))
    t3 = _tableau('Encaissements par nature de prestation', [('Nature', 'texte'), ('Montant', 'montant')], lignes)

    # Sorties d'argent
    rembourse = (Avoir.objects.filter(date_creation__date__range=[debut, fin])
                 .aggregate(s=Sum('montant_rembourse'))['s'] or ZERO)
    sorties = (SortieCaisse.objects.filter(statut='payee', date_paiement__date__range=[debut, fin])
               .aggregate(s=Sum('montant'))['s'] or ZERO)
    encaisse = sum((p.montant for p in paiements), ZERO)
    t4 = _tableau('Recettes nettes', [('', 'texte'), ('Montant', 'montant')], [
        _ligne('Encaissements', encaisse),
        _ligne('− Remboursements (avoirs)', rembourse),
        _ligne('− Sorties de caisse payées', sorties),
        _ligne('Recettes nettes', encaisse - rembourse - sorties, type_='total'),
    ])
    return {'titre': 'Recettes', 'tableaux': [t1, t2, t3, t4],
            'notes': ["La répartition par nature suit les lignes de chaque facture encaissée, "
                      "au prorata de leur montant."]}


def brouillard(debut, fin, params):
    """Mouvements d'espèces d'une caisse, dans l'ordre, avec le solde des pochettes."""
    from facturation.models import Caisse, Paiement
    from .models import Avoir, SessionCaissiere, SortieCaisse

    caisse = Caisse.objects.filter(pk=params.get('caisse')).first() if params.get('caisse') else None
    if caisse is None:
        caisse = Caisse.objects.filter(actif=True).order_by('nom').first()
    if caisse is None:
        return {'titre': 'Brouillard de caisse', 'tableaux': [], 'notes': ['Aucune caisse configurée.']}

    mouvements = []
    sessions = SessionCaissiere.objects.filter(journee__caisse=caisse,
                                               journee__date_journee__range=[debut, fin])
    for s in sessions.select_related('caissiere'):
        mouvements.append((s.date_ouverture, f'Fonds remis — {s.nom_caissiere}', s.numero, s.fonds_initial, ZERO,
                           reverse('comptabilite:session', args=[s.pk])))
        if s.ecart:
            mouvements.append((s.date_cloture, f'Écart de comptage — {s.nom_caissiere}', s.numero,
                               s.ecart if s.ecart > 0 else ZERO, -s.ecart if s.ecart < 0 else ZERO,
                               reverse('comptabilite:session', args=[s.pk])))
    for p in (Paiement.objects.filter(session__in=sessions, mode_paiement='especes')
              .select_related('facture__patient')):
        mouvements.append((p.date_paiement, f'Encaissement {p.facture.numero} — {p.facture.patient.nom}',
                           p.numero, p.montant, ZERO, reverse('facturation:detail', args=[p.facture_id])))
    for a in Avoir.objects.filter(session__in=sessions, mode_remboursement='especes').select_related('facture'):
        mouvements.append((a.date_creation, f'Remboursement facture {a.facture.numero}', a.numero,
                           ZERO, a.montant_rembourse, reverse('facturation:detail', args=[a.facture_id])))
    for so in SortieCaisse.objects.filter(session__in=sessions, statut='payee'):
        mouvements.append((so.date_paiement, f'Sortie — {so.libelle}', so.numero, ZERO, so.montant, None))

    lignes, solde, entrees, sorties_ = [], ZERO, ZERO, ZERO
    for quand, libelle, piece, entree, sortie, lien in sorted(mouvements, key=lambda m: m[0]):
        solde += entree - sortie
        entrees += entree
        sorties_ += sortie
        lignes.append(_ligne(timezone.localtime(quand).strftime('%d/%m/%Y %H:%M'), piece, libelle,
                             entree or None, sortie or None, solde, lien=lien))
    if lignes:
        lignes.append(_ligne('Total', '', '', entrees, sorties_, solde, type_='total'))
    return {'titre': f'Brouillard de caisse — {caisse.nom}', 'tableaux': [_tableau(
        'Mouvements d\'espèces', [('Date', 'texte'), ('Pièce', 'texte'), ('Libellé', 'texte'),
                                   ('Entrée', 'montant'), ('Sortie', 'montant'), ('Solde', 'montant')], lignes)],
        'notes': ["Espèces uniquement : les autres modes ne passent pas par les pochettes. "
                  "Le solde de fin doit égaler les espèces remises par les caissières."],
        'choix_caisse': {'actuelle': caisse.pk, 'caisses': list(Caisse.objects.order_by('nom'))}}


def ecarts(debut, fin, params):
    """Écarts constatés à la clôture des sessions, par caissière."""
    from .models import SessionCaissiere
    sessions = (SessionCaissiere.objects.exclude(statut='ouverte')
                .filter(date_cloture__date__range=[debut, fin])
                .select_related('caissiere', 'journee__caisse').order_by('caissiere__username', 'date_cloture'))
    lignes, par_caissiere = [], OrderedDict()
    for s in sessions:
        par_caissiere.setdefault(s.nom_caissiere, []).append(s)
    total = ZERO
    for nom, liste in par_caissiere.items():
        lignes.append(_ligne(nom, type_='groupe'))
        sous = ZERO
        for s in liste:
            sous += s.ecart or ZERO
            lignes.append(_ligne(s.journee.date_journee.strftime('%d/%m/%Y'), s.caisse.nom, s.numero,
                                 s.montant_theorique, s.montant_compte, s.ecart, s.justification_ecart,
                                 lien=reverse('comptabilite:session', args=[s.pk])))
        lignes.append(_ligne(f'Sous-total {nom} ({len(liste)} session{"s" if len(liste) > 1 else ""})',
                             '', '', None, None, sous, '', type_='sous_total'))
        total += sous
    if lignes:
        lignes.append(_ligne('Total', '', '', None, None, total, '', type_='total'))
    return {'titre': 'Écarts de caisse', 'tableaux': [_tableau(
        'Sessions clôturées', [('Journée', 'texte'), ('Caisse', 'texte'), ('Session', 'texte'),
                               ('Attendu', 'montant'), ('Compté', 'montant'), ('Écart', 'montant'),
                               ('Justification', 'texte')], lignes,
        vide="Aucune session clôturée sur la période.")],
        'notes': ["Écart négatif : manquant ; positif : excédent."]}


TRANCHES = [(30, '0 à 30 jours'), (60, '31 à 60 jours'), (90, '61 à 90 jours'), (None, 'Plus de 90 jours')]


def creances(debut, fin, params):
    """Factures émises non soldées à la date de fin, par ancienneté."""
    from facturation.models import Facture
    factures = (Facture.objects.filter(statut='emise', date_emission__date__lte=fin)
                .select_related('patient').order_by('date_emission'))
    groupes = OrderedDict((libelle, []) for _, libelle in TRANCHES)
    for f in factures:
        reste = f.montant_total - f.montant_paye
        if reste <= 0:
            continue
        age = (fin - _jour(f.date_emission)).days
        libelle = next(l for limite, l in TRANCHES if limite is None or age <= limite)
        groupes[libelle].append((f, reste, age))
    lignes, total = [], ZERO
    for libelle, liste in groupes.items():
        if not liste:
            continue
        lignes.append(_ligne(libelle, type_='groupe'))
        sous = ZERO
        for f, reste, age in liste:
            sous += reste
            lignes.append(_ligne(_jour(f.date_emission).strftime('%d/%m/%Y'), f.numero,
                                 f'{f.patient.nom} {f.patient.prenoms}', f.montant_total, f.montant_paye,
                                 reste, age, lien=reverse('facturation:detail', args=[f.pk])))
        lignes.append(_ligne(f'Sous-total {libelle}', '', '', None, None, sous, len(liste), type_='sous_total'))
        total += sous
    if lignes:
        lignes.append(_ligne('Total des créances', '', '', None, None, total, None, type_='total'))
    return {'titre': f'Factures non soldées au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Par ancienneté', [('Émise le', 'texte'), ('Facture', 'texte'), ('Patient', 'texte'),
                           ('Montant', 'montant'), ('Payé', 'montant'), ('Reste dû', 'montant'),
                           ('Âge (jours)', 'nombre')], lignes, vide="Aucune facture en attente de paiement.")],
        'notes': ["Seule la date de fin compte : l'état dit ce qui reste dû à cette date."]}


# ─── États comptables ──────────────────────────────────────────────────────────

def _ecritures(debut, fin, params):
    from .models import Ecriture
    qs = Ecriture.objects.all()
    if debut:
        qs = qs.filter(date__gte=debut)
    if fin:
        qs = qs.filter(date__lte=fin)
    if not params.get('brouillons'):
        qs = qs.filter(statut='validee')
    return qs


def _lignes_ecriture(debut, fin, params):
    from .models import LigneEcriture
    return LigneEcriture.objects.filter(ecriture__in=_ecritures(debut, fin, params).values('pk'))


def _note_brouillons(params):
    return ("Écritures validées et brouillons (situation provisoire)." if params.get('brouillons')
            else "Écritures validées seulement.")


def journal(debut, fin, params):
    from .models import Journal
    qs = (_ecritures(debut, fin, params).select_related('journal').prefetch_related('lignes__compte')
          .order_by('journal__code', 'date', 'numero', 'pk'))
    if params.get('journal'):
        qs = qs.filter(journal__code=params['journal'])
    lignes, td, tc = [], ZERO, ZERO
    for e in qs:
        lien = reverse('comptabilite:ecriture', args=[e.pk])
        lignes.append(_ligne(f'{e.date:%d/%m/%Y} · {e.journal.code} · {e.reference} · {e.piece} — {e.libelle}',
                             type_='groupe', lien=lien))
        for l in e.lignes.all():
            lignes.append(_ligne(l.compte.numero, l.compte.intitule, l.libelle, l.debit or None, l.credit or None))
            td += l.debit
            tc += l.credit
    if lignes:
        lignes.append(_ligne('Total', '', '', td, tc, type_='total'))
    return {'titre': 'Journal comptable', 'tableaux': [_tableau(
        'Écritures', [('Compte', 'texte'), ('Intitulé', 'texte'), ('Libellé', 'texte'),
                      ('Débit', 'montant'), ('Crédit', 'montant')], lignes)],
        'notes': [_note_brouillons(params)],
        'choix_journal': {'actuel': params.get('journal', ''), 'journaux': list(Journal.objects.order_by('code'))}}


def _comptes_filtres(params):
    from .models import Compte
    qs = Compte.objects.all()
    if params.get('compte'):
        qs = qs.filter(numero__startswith=params['compte'])
    return qs


def grand_livre(debut, fin, params):
    """Pour chaque compte mouvementé : solde antérieur, mouvements, solde cumulé."""
    anterieur = (_lignes_ecriture(None, debut - timedelta(days=1), params)
                 .values('compte_id').annotate(d=Sum('debit'), c=Sum('credit')))
    soldes_av = {a['compte_id']: (a['d'] or ZERO) - (a['c'] or ZERO) for a in anterieur}
    mouvements = (_lignes_ecriture(debut, fin, params)
                  .select_related('ecriture__journal', 'compte').order_by('compte__numero', 'ecriture__date', 'pk'))
    comptes = {c.pk: c for c in _comptes_filtres(params)}
    par_compte = OrderedDict()
    for l in mouvements:
        if l.compte_id in comptes:
            par_compte.setdefault(l.compte_id, []).append(l)
    for cid in soldes_av:
        if cid in comptes and soldes_av[cid] and cid not in par_compte:
            par_compte[cid] = []
    lignes, td, tc = [], ZERO, ZERO
    for cid in sorted(par_compte, key=lambda i: comptes[i].numero):
        c = comptes[cid]
        solde = soldes_av.get(cid, ZERO)
        lignes.append(_ligne(f'{c.numero} — {c.intitule}', type_='groupe'))
        lignes.append(_ligne('', '', 'Solde antérieur', None, None, solde))
        sd = sc = ZERO
        for l in par_compte[cid]:
            solde += l.debit - l.credit
            sd += l.debit
            sc += l.credit
            e = l.ecriture
            lignes.append(_ligne(e.date.strftime('%d/%m/%Y'), f'{e.journal.code} {e.reference if e.numero else ""}'.strip(),
                                 l.libelle or e.libelle, l.debit or None, l.credit or None, solde,
                                 lien=reverse('comptabilite:ecriture', args=[e.pk])))
        lignes.append(_ligne(f'Total {c.numero}', '', '', sd, sc, solde, type_='sous_total'))
        td += sd
        tc += sc
    if lignes:
        lignes.append(_ligne('Total des mouvements', '', '', td, tc, None, type_='total'))
    return {'titre': 'Grand livre', 'tableaux': [_tableau(
        'Comptes', [('Date', 'texte'), ('Journal / n°', 'texte'), ('Libellé', 'texte'),
                    ('Débit', 'montant'), ('Crédit', 'montant'), ('Solde', 'montant')], lignes)],
        'notes': [_note_brouillons(params), "Solde positif : débiteur ; négatif : créditeur."],
        'filtre_compte': params.get('compte', '')}


def _soldes_dc(solde):
    return (solde, None) if solde > 0 else (None, -solde) if solde < 0 else (None, None)


def balance(debut, fin, params):
    """Balance générale à six colonnes, sous-totaux par classe."""
    anterieur = {a['compte_id']: (a['d'] or ZERO) - (a['c'] or ZERO) for a in
                 _lignes_ecriture(None, debut - timedelta(days=1), params)
                 .values('compte_id').annotate(d=Sum('debit'), c=Sum('credit'))}
    periode = {a['compte_id']: (a['d'] or ZERO, a['c'] or ZERO) for a in
               _lignes_ecriture(debut, fin, params).values('compte_id').annotate(d=Sum('debit'), c=Sum('credit'))}
    comptes = [c for c in _comptes_filtres(params) if c.pk in anterieur or c.pk in periode]
    lignes = []
    tot = [ZERO] * 6
    classe_courante, sous = None, [ZERO] * 6

    def _ferme_classe():
        if classe_courante is not None:
            lignes.append(_ligne(f'Total classe {classe_courante}', '', *sous, type_='sous_total'))

    for c in comptes:
        if c.classe != classe_courante:
            _ferme_classe()
            classe_courante, sous = c.classe, [ZERO] * 6
        av = anterieur.get(c.pk, ZERO)
        d, cr = periode.get(c.pk, (ZERO, ZERO))
        fin_ = av + d - cr
        valeurs = [*_soldes_dc(av), d or None, cr or None, *_soldes_dc(fin_)]
        for i, v in enumerate(valeurs):
            sous[i] += v or ZERO
            tot[i] += v or ZERO
        lignes.append(_ligne(c.numero, c.intitule, *valeurs))
    _ferme_classe()
    if comptes:
        lignes.append(_ligne('Total général', '', *tot, type_='total'))
    return {'titre': 'Balance générale', 'tableaux': [_tableau(
        'Comptes', [('Compte', 'texte'), ('Intitulé', 'texte'),
                    ('Solde début — débit', 'montant'), ('Solde début — crédit', 'montant'),
                    ('Mouvements — débit', 'montant'), ('Mouvements — crédit', 'montant'),
                    ('Solde fin — débit', 'montant'), ('Solde fin — crédit', 'montant')], lignes)],
        'notes': [_note_brouillons(params),
                  "Une balance juste a des totaux égaux au débit et au crédit dans chaque paire de colonnes."],
        'filtre_compte': params.get('compte', '')}


def balance_tiers(debut, fin, params):
    """Balance des patients et des assurances (comptes 411), par tiers."""
    lignes_qs = _lignes_ecriture(None, fin, params).filter(compte__numero__startswith='411')
    donnees = OrderedDict()
    for row in (lignes_qs.values('compte__numero', 'compte__intitule', 'tiers')
                .annotate(d=Sum('debit'), c=Sum('credit')).order_by('compte__numero', 'tiers')):
        donnees.setdefault((row['compte__numero'], row['compte__intitule']), []).append(row)
    lignes, total = [], ZERO
    for (numero, intitule), rows in donnees.items():
        lignes.append(_ligne(f'{numero} — {intitule}', type_='groupe'))
        sous = ZERO
        for row in rows:
            solde = (row['d'] or ZERO) - (row['c'] or ZERO)
            if not solde:
                continue
            sous += solde
            lignes.append(_ligne(row['tiers'] or '(sans tiers)', row['d'] or None, row['c'] or None, solde))
        lignes.append(_ligne(f'Solde {numero}', None, None, sous, type_='sous_total'))
        total += sous
    if lignes:
        lignes.append(_ligne('Solde total', None, None, total, type_='total'))
    return {'titre': f'Balance des patients et des assurances au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Par tiers', [('Tiers', 'texte'), ('Débit', 'montant'), ('Crédit', 'montant'), ('Solde', 'montant')],
        lignes)],
        'notes': [_note_brouillons(params),
                  "Solde positif : le tiers doit au centre ; négatif : le centre lui doit (trop-perçu, avance)."]}


def resultat(debut, fin, params):
    """Compte de résultat simplifié : charges (classe 6) et ressources (classe 7)."""
    soldes = (_lignes_ecriture(debut, fin, params).filter(Q(compte__numero__startswith='6') |
                                                         Q(compte__numero__startswith='7'))
              .values('compte__numero', 'compte__intitule').annotate(d=Sum('debit'), c=Sum('credit'))
              .order_by('compte__numero'))
    charges, produits = [], []
    for s in soldes:
        if s['compte__numero'].startswith('6'):
            charges.append((s['compte__numero'], s['compte__intitule'], (s['d'] or ZERO) - (s['c'] or ZERO)))
        else:
            produits.append((s['compte__numero'], s['compte__intitule'], (s['c'] or ZERO) - (s['d'] or ZERO)))
    total_c = sum((m for _, _, m in charges), ZERO)
    total_p = sum((m for _, _, m in produits), ZERO)
    lignes = [_ligne('Ressources (classe 7)', type_='groupe')]
    lignes += [_ligne(n, i, m) for n, i, m in produits]
    lignes.append(_ligne('Total des ressources', '', total_p, type_='sous_total'))
    lignes.append(_ligne('Charges (classe 6)', type_='groupe'))
    lignes += [_ligne(n, i, m) for n, i, m in charges]
    lignes.append(_ligne('Total des charges', '', total_c, type_='sous_total'))
    resultat_ = total_p - total_c
    lignes.append(_ligne('Excédent de la période' if resultat_ >= 0 else 'Déficit de la période', '',
                         resultat_, type_='total'))
    return {'titre': 'Compte de résultat simplifié', 'tableaux': [_tableau(
        'Ressources et charges', [('Compte', 'texte'), ('Intitulé', 'texte'), ('Montant', 'montant')], lignes)],
        'notes': [_note_brouillons(params),
                  "Les remises et gratuités (709) viennent en diminution des ressources.",
                  "Présentation de gestion, pas les états financiers SYCEBNL de fin d'exercice."]}


def controle(debut, fin, params):
    """Ce qui manque ou cloche entre la facturation, la caisse et la comptabilité."""
    from facturation.models import Facture, Paiement
    from .models import Ecriture, SessionCaissiere

    origines = set(Ecriture.all_objects.exclude(origine__isnull=True).values_list('origine', flat=True))
    factures = [f for f in Facture.objects.filter(date_emission__date__range=[debut, fin])
                .exclude(statut='brouillon').prefetch_related('avoirs')
                if f'facture:{f.pk}' not in origines and f.montant_total
                and not (f.statut == 'annulee' and not f.avoirs.exists())]
    paiements = [p for p in Paiement.objects.filter(date_paiement__date__range=[debut, fin])
                 if f'paiement:{p.pk}' not in origines and p.montant]
    sans_session = Paiement.objects.filter(date_paiement__date__range=[debut, fin], session__isnull=True).count()
    brouillons = Ecriture.objects.filter(statut='brouillon', date__range=[debut, fin]).count()
    desequilibrees = [e for e in Ecriture.objects.filter(date__range=[debut, fin]).prefetch_related('lignes')
                      if sum((l.debit for l in e.lignes.all()), ZERO) != sum((l.credit for l in e.lignes.all()), ZERO)]
    ouvertes = SessionCaissiere.objects.filter(statut='ouverte',
                                               journee__date_journee__lt=timezone.localdate()).count()
    a_valider = SessionCaissiere.objects.filter(statut='cloturee').count()
    ecart_payee = [f for f in Facture.objects.filter(date_emission__date__range=[debut, fin], statut='payee')
                   .annotate(encaisse=Sum('paiements__montant'))
                   if (f.encaisse or ZERO) != f.montant_paye]

    def _etat(n):
        return 'OK' if not n else 'À traiter'

    ecritures_url = reverse('comptabilite:ecritures')
    lignes = [
        _ligne('Factures non comptabilisées', len(factures), _etat(len(factures)),
               'Générer les écritures de la période.', lien=ecritures_url),
        _ligne('Paiements non comptabilisés', len(paiements), _etat(len(paiements)),
               'Générer les écritures de la période.', lien=ecritures_url),
        _ligne('Écritures en brouillon', brouillons, _etat(brouillons),
               'À valider au passage des écritures.', lien=ecritures_url),
        _ligne('Écritures déséquilibrées', len(desequilibrees), _etat(len(desequilibrees)),
               'Ne devrait jamais arriver : à signaler.'),
        _ligne('Paiements sans session de caisse', sans_session, _etat(sans_session),
               'Paiements antérieurs aux sessions, ou anomalie.'),
        _ligne('Sessions des jours passés encore ouvertes', ouvertes, _etat(ouvertes),
               'À clôturer (d\'office si besoin).', lien=reverse('comptabilite:journees')),
        _ligne('Sessions clôturées non validées', a_valider, _etat(a_valider),
               'À valider par le superviseur.', lien=reverse('comptabilite:journees')),
        _ligne('Factures payées dont le montant payé ≠ paiements', len(ecart_payee), _etat(len(ecart_payee)),
               'Incohérence entre la facture et ses paiements.'),
    ]
    tableaux = [_tableau('Contrôles', [('Contrôle', 'texte'), ('Nombre', 'nombre'), ('État', 'texte'),
                                       ('Action', 'texte')], lignes)]
    detail = ([_ligne(f.numero, f'{f.patient.nom} {f.patient.prenoms}', f.montant_total,
                      lien=reverse('facturation:detail', args=[f.pk])) for f in factures[:50]])
    if detail:
        tableaux.append(_tableau('Factures non comptabilisées (50 premières)',
                                 [('Facture', 'texte'), ('Patient', 'texte'), ('Montant', 'montant')], detail))
    return {'titre': 'Contrôle de cohérence', 'tableaux': tableaux, 'notes': []}


# ─── Financements (lot 5) ──────────────────────────────────────────────────────

def conventions(debut, fin, params):
    """Suivi de toutes les conventions à la date de fin."""
    from . import financements
    from .models import Convention
    lignes = []
    tot = [ZERO] * 5
    for c in Convention.objects.select_related('bailleur').exclude(date_debut__gt=fin).order_by('code'):
        s = financements.suivi(c, fin=fin)
        valeurs = [s['accorde'], s['recu'], s['depense'], s['reste_a_recevoir'], s['disponible']]
        tot = [a + b for a, b in zip(tot, valeurs)]
        lignes.append(_ligne(c.code, c.intitule, str(c.bailleur), *valeurs,
                             f"{s['taux']:.0f} %" if s['taux'] is not None else '',
                             lien=reverse('comptabilite:convention', args=[c.pk])))
    if lignes:
        lignes.append(_ligne('Total', '', '', *tot, '', type_='total'))
    return {'titre': f'Suivi des conventions au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Conventions', [('Code', 'texte'), ('Projet', 'texte'), ('Bailleur', 'texte'), ('Accordé', 'montant'),
                        ('Reçu', 'montant'), ('Dépensé', 'montant'), ('Reste à recevoir', 'montant'),
                        ('Disponible', 'montant'), ('Exécution', 'texte')], lignes,
        vide="Aucune convention.")],
        'notes': ["Dépensé : charges imputées à la convention (brouillons compris). "
                  "Disponible : reçu et dons affectés, moins le dépensé."]}


def rapport_convention(debut, fin, params):
    """Rapport financier d'une convention, pour le bailleur."""
    from . import financements
    from .models import Convention, LigneEcriture
    convention = Convention.objects.filter(pk=params.get('convention')).select_related('bailleur').first() \
        if params.get('convention') else Convention.objects.order_by('-date_debut').first()
    choix = {'actuelle': convention.pk if convention else None,
             'conventions': list(Convention.objects.order_by('code'))}
    if convention is None:
        return {'titre': 'Rapport financier de convention', 'tableaux': [], 'notes': ['Aucune convention.'],
                'choix_convention': choix}
    s = financements.suivi(convention, fin=fin)
    synthese = _tableau('Synthèse', [('', 'texte'), ('Montant', 'montant')], [
        _ligne('Montant accordé', s['accorde']),
        _ligne('Versements reçus', s['recu']),
        _ligne('Dons affectés', s['dons']),
        _ligne('Dépenses réalisées', s['depense']),
        _ligne('Reste à recevoir', s['reste_a_recevoir']),
        _ligne('Disponible (reçu − dépensé)', s['disponible'], type_='total'),
    ])
    lignes = [_ligne(l['ligne'].libelle, l['ligne'].compte.numero, l['prevu'], l['realise'], l['reste'],
                     f"{l['taux']:.0f} %" if l['taux'] is not None else '') for l in s['lignes_budget']]
    if s['hors_budget']:
        lignes.append(_ligne('Dépenses hors lignes budgétaires', '', None, s['hors_budget'], None, ''))
    if lignes:
        lignes.append(_ligne('Total', '', s['budget_prevu'], s['depense'], s['budget_prevu'] - s['depense'], '',
                             type_='total'))
    budget = _tableau('Budget prévu / réalisé', [('Ligne', 'texte'), ('Compte', 'texte'), ('Prévu', 'montant'),
                                                 ('Réalisé', 'montant'), ('Reste', 'montant'), ('Taux', 'texte')],
                      lignes, vide="Aucune ligne budgétaire saisie.")
    versements = _tableau('Versements reçus', [('Date', 'texte'), ('N°', 'texte'), ('Mode', 'texte'),
                                               ('Référence', 'texte'), ('Montant', 'montant')],
                          [_ligne(v.date.strftime('%d/%m/%Y'), v.numero, v.get_mode_display(), v.reference, v.montant)
                           for v in convention.versements.filter(date__lte=fin).order_by('date')],
                          vide="Aucun versement.")
    depenses = (LigneEcriture.objects.filter(convention=convention, compte__numero__startswith='6',
                                             ecriture__date__range=[debut, fin])
                .select_related('ecriture__journal', 'compte').order_by('ecriture__date'))
    detail = _tableau(f'Dépenses du {debut:%d/%m/%Y} au {fin:%d/%m/%Y}',
                      [('Date', 'texte'), ('Pièce', 'texte'), ('Compte', 'texte'), ('Libellé', 'texte'),
                       ('Montant', 'montant')],
                      [_ligne(l.ecriture.date.strftime('%d/%m/%Y'), l.ecriture.piece, l.compte.numero, l.libelle,
                              l.debit - l.credit, lien=reverse('comptabilite:ecriture', args=[l.ecriture_id]))
                       for l in depenses], vide="Aucune dépense sur la période.")
    return {'titre': f'Rapport financier — {convention.code} {convention.intitule}',
            'tableaux': [synthese, budget, versements, detail],
            'notes': [f"Bailleur : {convention.bailleur}. Convention du {convention.date_debut:%d/%m/%Y} "
                      f"au {convention.date_fin:%d/%m/%Y}. Situation au {fin:%d/%m/%Y}."],
            'choix_convention': choix}


def budget(debut, fin, params):
    """Budget annuel et réalisé de l'exercice qui contient la date de fin."""
    from . import financements
    from .models import Exercice
    exercice = Exercice.objects.filter(date_debut__lte=fin, date_fin__gte=fin).first()
    if exercice is None:
        return {'titre': 'Budget / réalisé', 'tableaux': [], 'notes': ["Aucun exercice ne contient cette date."]}
    lignes, groupe = [], None
    totaux = {'6': [ZERO, ZERO], '7': [ZERO, ZERO]}
    for l in financements.budget_realise(exercice, fin):
        classe = l['ligne'].compte.classe
        if classe != groupe:
            groupe = classe
            lignes.append(_ligne('Charges' if classe == '6' else 'Ressources', type_='groupe'))
        totaux[classe][0] += l['prevu']
        totaux[classe][1] += l['realise']
        lignes.append(_ligne(l['ligne'].compte.numero, l['ligne'].compte.intitule, l['prevu'], l['realise'],
                             l['ecart'], f"{l['taux']:.0f} %" if l['taux'] is not None else ''))
    for classe, nom in (('7', 'ressources'), ('6', 'charges')):
        p, r = totaux[classe]
        if p or r:
            lignes.append(_ligne(f'Total des {nom}', '', p, r, r - p, '', type_='sous_total'))
    return {'titre': f'Budget / réalisé — exercice {exercice} au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Par compte', [('Compte', 'texte'), ('Intitulé', 'texte'), ('Budget annuel', 'montant'),
                       ('Réalisé', 'montant'), ('Écart', 'montant'), ('Taux', 'texte')], lignes,
        vide="Aucun budget saisi pour cet exercice (Financements → Budget annuel).")],
        'notes': ["Réalisé cumulé depuis le début de l'exercice, brouillons compris.",
                  "Le taux se lit au regard de l'avancement de l'année."]}


def dons(debut, fin, params):
    from .models import Don
    qs = Don.objects.filter(date__range=[debut, fin]).select_related('donateur', 'convention').order_by('date')
    lignes = [_ligne(d.date.strftime('%d/%m/%Y'), d.numero, d.nom_donateur, d.get_nature_display(),
                     d.convention.code if d.convention_id else 'Fonds propres', d.montant,
                     lien=reverse('comptabilite:don_recu', args=[d.pk])) for d in qs]
    if lignes:
        lignes.append(_ligne('Total', '', '', '', '', sum((d.montant for d in qs), ZERO), type_='total'))
    return {'titre': 'Dons reçus', 'tableaux': [_tableau(
        'Dons', [('Date', 'texte'), ('N°', 'texte'), ('Donateur', 'texte'), ('Nature', 'texte'),
                 ('Affectation', 'texte'), ('Montant / valeur', 'montant')], lignes)],
        'notes': ["Dons en nature à leur valeur estimée."]}


# ─── Assurances (lot 6) ────────────────────────────────────────────────────────

def creances_assurances(debut, fin, params):
    """Balance âgée des tiers payants : ce que doit chaque assureur, par ancienneté."""
    from . import assurances
    lignes, tot = [], [ZERO] * len(assurances.TRANCHES)
    for l in assurances.balance_agee(fin):
        tot = [a + b for a, b in zip(tot, l['tranches'])]
        lignes.append(_ligne(l['assurance'].nom, *l['tranches'], sum(l['tranches'], ZERO),
                             lien=reverse('comptabilite:creances_assureur', args=[l['assurance'].pk])))
    if lignes:
        lignes.append(_ligne('Total', *tot, sum(tot, ZERO), type_='total'))
    return {'titre': f'Créances des assurances au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Balance âgée par assureur', [('Assureur', 'texte')] + [(t, 'montant') for _, t in assurances.TRANCHES]
        + [('Total dû', 'montant')], lignes, vide="Aucune créance sur les assurances.")],
        'notes': ["Âge compté depuis la date de la facture. Part assurance restant due à la date de fin."]}


def reglements_assurances(debut, fin, params):
    from .models import ReglementAssurance
    qs = (ReglementAssurance.objects.filter(date__range=[debut, fin])
          .select_related('assurance', 'bordereau').order_by('date'))
    lignes = [_ligne(r.date.strftime('%d/%m/%Y'), r.numero, r.assurance.nom,
                     r.bordereau.numero if r.bordereau_id else '', r.get_mode_display(), r.reference, r.montant)
              for r in qs]
    if lignes:
        lignes.append(_ligne('Total', '', '', '', '', '', sum((r.montant for r in qs), ZERO), type_='total'))
    return {'titre': 'Règlements des assurances', 'tableaux': [_tableau(
        'Règlements', [('Date', 'texte'), ('N°', 'texte'), ('Assureur', 'texte'), ('Bordereau', 'texte'),
                       ('Mode', 'texte'), ('Référence', 'texte'), ('Montant', 'montant')], lignes)],
        'notes': []}


# ─── Trésorerie (lot 7) ────────────────────────────────────────────────────────

def position_tresorerie(debut, fin, params):
    from . import tresorerie
    lignes = [_ligne(l['compte'].numero, l['compte'].intitule, l['solde']) for l in tresorerie.position(fin)]
    if lignes:
        lignes.append(_ligne('Total', '', sum((l['cellules'][2] for l in lignes), ZERO), type_='total'))
    return {'titre': f'Position de trésorerie au {fin:%d/%m/%Y}', 'tableaux': [_tableau(
        'Comptes de trésorerie', [('Compte', 'texte'), ('Intitulé', 'texte'), ('Solde', 'montant')], lignes,
        vide="Aucun mouvement de trésorerie comptabilisé.")],
        'notes': ["Soldes selon les comptes, écritures en brouillon comprises."]}


def etat_rapprochement(debut, fin, params):
    from . import tresorerie
    from .models import CompteTresorerie
    ct = (CompteTresorerie.objects.filter(pk=params.get('compte_tresorerie')).first()
          if params.get('compte_tresorerie') else CompteTresorerie.objects.filter(actif=True).first())
    choix = {'actuel': ct.pk if ct else None, 'comptes': list(CompteTresorerie.objects.order_by('libelle'))}
    if ct is None:
        return {'titre': 'État de rapprochement', 'tableaux': [], 'notes': ['Aucun compte de trésorerie.'],
                'choix_tresorerie': choix}
    e = tresorerie.etat_rapprochement(ct, fin)
    synthese = _tableau('Synthèse', [('', 'texte'), ('Montant', 'montant')], [
        _ligne(f'Solde selon les comptes ({ct.compte.numero})', e['solde_compta']),
        _ligne('− Écritures absentes du relevé', e['total_ecritures']),
        _ligne('+ Opérations du relevé non comptabilisées', e['total_releve']),
        _ligne('= Solde attendu sur le relevé', e['solde_explique'], type_='sous_total'),
        _ligne('Solde du relevé', e['solde_releve']),
        _ligne('Écart inexpliqué', e['solde_releve'] - e['solde_explique'], type_='total'),
    ])
    ecritures = _tableau('Écritures absentes du relevé', [('Date', 'texte'), ('Libellé', 'texte'), ('Montant', 'montant')],
                         [_ligne(l.ecriture.date.strftime('%d/%m/%Y'), l.ecriture.libelle, l.debit - l.credit,
                                 lien=reverse('comptabilite:ecriture', args=[l.ecriture_id]))
                          for l in e['ecritures_seules']], vide="Aucune.")
    releve = _tableau('Opérations du relevé non comptabilisées', [('Date', 'texte'), ('Libellé', 'texte'),
                                                                  ('Montant', 'montant')],
                      [_ligne(l.date.strftime('%d/%m/%Y'), l.libelle, l.montant) for l in e['releve_seul']],
                      vide="Aucune.")
    return {'titre': f'État de rapprochement — {ct.libelle} au {fin:%d/%m/%Y}',
            'tableaux': [synthese, ecritures, releve], 'notes': [], 'choix_tresorerie': choix}


def rejets_assurances(debut, fin, params):
    from .models import RejetAssurance
    qs = (RejetAssurance.objects.filter(date__range=[debut, fin])
          .select_related('facture__patient', 'assurance').order_by('date'))
    lignes = [_ligne(r.date.strftime('%d/%m/%Y'), r.numero, r.assurance.nom, r.facture.numero,
                     f'{r.facture.patient.nom} {r.facture.patient.prenoms}', r.get_decision_display(), r.motif, r.montant,
                     lien=reverse('facturation:detail', args=[r.facture_id])) for r in qs]
    if lignes:
        lignes.append(_ligne('Total', '', '', '', '', '', '', sum((r.montant for r in qs), ZERO), type_='total'))
    return {'titre': 'Refus des assurances', 'tableaux': [_tableau(
        'Refus', [('Date', 'texte'), ('N°', 'texte'), ('Assureur', 'texte'), ('Facture', 'texte'), ('Patient', 'texte'),
                  ('Décision', 'texte'), ('Motif', 'texte'), ('Montant', 'montant')], lignes)],
        'notes': []}


# ─── Registre ──────────────────────────────────────────────────────────────────

PERM_CAISSE = 'caisse'        # facturation.view_facture ou superviseur de caisse
PERM_COMPTA = 'comptabilite.view_ecriture'

# Sections du sous-menu « États » et du sommaire, dans cet ordre.
GROUPES = [('caisse', 'Caisse et recettes'), ('comptabilite', 'Comptabilité générale'),
           ('tresorerie', 'Trésorerie'), ('assurances', 'Assurances et mutuelles'),
           ('financements', 'Financements et dons')]

ETATS = OrderedDict([
    ('recettes', {'groupe': 'caisse', 'icone': 'bi-graph-up-arrow', 'titre': 'Recettes', 'fonction': recettes, 'perm': PERM_CAISSE, 'periode': 'jour',
                  'description': "Encaissements par jour et caisse, par mode, par nature ; recettes nettes."}),
    ('brouillard', {'groupe': 'caisse', 'icone': 'bi-journal-text', 'titre': 'Brouillard de caisse', 'fonction': brouillard, 'perm': PERM_CAISSE, 'periode': 'jour',
                    'description': "Mouvements d'espèces d'une caisse dans l'ordre, avec le solde."}),
    ('ecarts', {'groupe': 'caisse', 'icone': 'bi-exclamation-diamond', 'titre': 'Écarts de caisse', 'fonction': ecarts, 'perm': PERM_CAISSE, 'periode': 'semaine',
                'description': "Écarts constatés à la clôture des sessions, par caissière."}),
    ('creances', {'groupe': 'caisse', 'icone': 'bi-hourglass-split', 'titre': 'Factures non soldées', 'fonction': creances, 'perm': PERM_CAISSE, 'periode': 'semaine',
                  'description': "Ce qui reste dû, par ancienneté (0-30, 31-60, 61-90, +90 jours)."}),
    ('journal', {'groupe': 'comptabilite', 'icone': 'bi-journals', 'titre': 'Journal comptable', 'fonction': journal, 'perm': PERM_COMPTA, 'periode': 'mois',
                 'description': "Les écritures de la période, journal par journal."}),
    ('grand_livre', {'groupe': 'comptabilite', 'icone': 'bi-book', 'titre': 'Grand livre', 'fonction': grand_livre, 'perm': PERM_COMPTA, 'periode': 'mois',
                     'description': "Chaque compte : solde antérieur, mouvements, solde cumulé."}),
    ('balance', {'groupe': 'comptabilite', 'icone': 'bi-columns-gap', 'titre': 'Balance générale', 'fonction': balance, 'perm': PERM_COMPTA, 'periode': 'mois',
                 'description': "Soldes de début, mouvements et soldes de fin de tous les comptes."}),
    ('balance_tiers', {'groupe': 'comptabilite', 'icone': 'bi-people', 'titre': 'Balance patients et assurances', 'fonction': balance_tiers, 'perm': PERM_COMPTA,
                       'periode': 'mois', 'description': "Ce que doit chaque patient et chaque assureur."}),
    ('resultat', {'groupe': 'comptabilite', 'icone': 'bi-bar-chart-line', 'titre': 'Compte de résultat', 'fonction': resultat, 'perm': PERM_COMPTA, 'periode': 'mois',
                  'description': "Ressources, charges et excédent ou déficit de la période."}),
    ('controle', {'groupe': 'comptabilite', 'icone': 'bi-shield-check', 'titre': 'Contrôle de cohérence', 'fonction': controle, 'perm': PERM_COMPTA, 'periode': 'mois',
                  'description': "Ce qui n'est pas comptabilisé, validé ou clôturé."}),
    ('position_tresorerie', {'groupe': 'tresorerie', 'icone': 'bi-wallet2', 'titre': 'Position de trésorerie',
                             'fonction': position_tresorerie, 'perm': 'comptabilite.view_comptetresorerie',
                             'periode': 'jour', 'description': "Solde de chaque caisse, banque et Mobile Money."}),
    ('rapprochement', {'groupe': 'tresorerie', 'icone': 'bi-check2-square', 'titre': 'État de rapprochement',
                       'fonction': etat_rapprochement, 'perm': 'comptabilite.view_lignereleve', 'periode': 'mois',
                       'description': "Écart entre le relevé et les comptes, et ce qui l'explique."}),
    ('rejets_assurances', {'groupe': 'assurances', 'icone': 'bi-x-octagon', 'titre': 'Refus des assurances',
                           'fonction': rejets_assurances, 'perm': 'comptabilite.view_rejetassurance',
                           'periode': 'annee', 'description': "Parts refusées par les assureurs, et leur suite."}),
    ('creances_assurances', {'groupe': 'assurances', 'icone': 'bi-shield-plus',
                             'titre': 'Créances des assurances (balance âgée)', 'fonction': creances_assurances,
                             'perm': 'comptabilite.view_bordereauassurance', 'periode': 'jour',
                             'description': "Ce que doit chaque assureur, par ancienneté."}),
    ('reglements_assurances', {'groupe': 'assurances', 'icone': 'bi-cash', 'titre': 'Règlements des assurances',
                               'fonction': reglements_assurances, 'perm': 'comptabilite.view_reglementassurance',
                               'periode': 'mois', 'description': "Argent reçu des assureurs sur la période."}),
    ('conventions', {'groupe': 'financements', 'icone': 'bi-briefcase', 'titre': 'Suivi des conventions',
                     'fonction': conventions, 'perm': 'comptabilite.view_convention', 'periode': 'annee',
                     'description': "Accordé, reçu, dépensé et disponible de chaque convention."}),
    ('rapport_convention', {'groupe': 'financements', 'icone': 'bi-file-earmark-text',
                            'titre': 'Rapport financier de convention', 'fonction': rapport_convention,
                            'perm': 'comptabilite.view_convention', 'periode': 'annee',
                            'description': "Le rapport d'une convention pour son bailleur."}),
    ('budget', {'groupe': 'financements', 'icone': 'bi-clipboard-data', 'titre': 'Budget / réalisé',
                'fonction': budget, 'perm': 'comptabilite.view_lignebudget', 'periode': 'annee',
                'description': "Budget annuel et réalisé cumulé, compte par compte."}),
    ('dons', {'groupe': 'financements', 'icone': 'bi-gift', 'titre': 'Dons reçus', 'fonction': dons,
              'perm': 'comptabilite.view_don', 'periode': 'annee',
              'description': "Les dons de la période, par donateur et affectation."}),
])


def peut_voir(user, etat):
    if etat['perm'] == PERM_CAISSE:
        return user.has_perm('facturation.view_facture') or user.has_perm('comptabilite.superviser_caisse')
    return user.has_perm(etat['perm'])
