"""Import et export du plan tiers au format Excel.

Deux présentations sont lues :

- l'export « Liste des tiers » de **Sage 100 Comptabilité** que fournit
  l'expert-comptable : Type, Compte tiers, Intitulé du tiers, Code
  postal/Ville, avec bandeau et en-têtes répétés à chaque page. Les cellules
  fusionnées décalent les valeurs : une ligne de tiers est lue par sa forme
  (le type, puis le numéro, l'intitulé et la ville dans cet ordre) ;
- l'export de ce module (Type, N° compte tiers, Intitulé, Compte collectif,
  Ville, Actif), lu colonne par colonne.

L'import ne supprime rien et ne change jamais un numéro. Il crée les tiers
nouveaux, avec le compte collectif du fichier ou à défaut celui déduit du
numéro, et met à jour intitulé, type et ville des tiers existants (compte
collectif et actif aussi quand le fichier les donne).
"""
from django.db import transaction

from .models import Compte, Tiers, collectif_deduit
from .plan_import import ErreurImport, _norm, _numero, _oui

TYPES = {cle: libelle for cle, libelle in Tiers.TYPE}
_TYPE_PAR_LIBELLE = {_norm(libelle): cle for cle, libelle in Tiers.TYPE}
COLONNES_EXPORT = ['Type', 'N° compte tiers', 'Intitulé du tiers', 'Compte collectif', 'Code postal / ville',
                   'Actif']


def _entete(ligne):
    """Positions des colonnes si `ligne` est une ligne d'en-tête, sinon None."""
    cols = {}
    for i, v in enumerate(ligne):
        n = _norm(v)
        if n == 'type':
            cols['type'] = i
        elif n in ('comptetiers', 'ncomptetiers', 'numero'):
            cols['numero'] = i
        elif n.startswith('intitule'):
            cols['intitule'] = i
        elif n.startswith('comptecollectif'):
            cols['collectif'] = i
        elif n.startswith('codepostal') or n == 'ville':
            cols['ville'] = i
        elif n == 'actif':
            cols['actif'] = i
    return cols if {'type', 'numero', 'intitule'} <= cols.keys() else None


def _cellule(ligne, cols, cle):
    i = cols.get(cle)
    return ligne[i] if i is not None and i < len(ligne) else None


def lire(fichier):
    """Tiers lus dans le classeur : ([{numero, intitule, type, ville,
    collectif?, actif?}], [anomalies])."""
    from openpyxl import load_workbook
    try:
        classeur = load_workbook(fichier, read_only=True, data_only=True)
    except Exception:
        raise ErreurImport("Ce fichier n'est pas un classeur Excel (.xlsx) lisible.")
    feuille = classeur.worksheets[0]
    cols, tiers, anomalies, vus = None, [], [], set()
    for rang, ligne in enumerate(feuille.iter_rows(values_only=True), start=1):
        ligne = list(ligne)
        if cols is None:
            cols = _entete(ligne)
            continue
        valeurs = [_numero(v) for v in ligne if _numero(v)]
        if not valeurs or _norm(valeurs[0]) not in _TYPE_PAR_LIBELLE:
            continue  # bandeau, en-tête répété, ligne vide
        type_ = _TYPE_PAR_LIBELLE[_norm(valeurs[0])]
        if 'collectif' in cols:  # export de ce module : pas de cellules fusionnées
            numero = _numero(_cellule(ligne, cols, 'numero'))
            intitule = _numero(_cellule(ligne, cols, 'intitule'))
            ville = _numero(_cellule(ligne, cols, 'ville'))
        else:
            numero, intitule = (valeurs + ['', ''])[1:3]
            ville = ' '.join(valeurs[3:])
        numero = numero.upper()
        if not numero:
            continue
        if numero in vus:
            anomalies.append(f"Ligne {rang} : le tiers {numero} figure deux fois, seule la première ligne est prise.")
            continue
        if len(numero) > 17 or not numero.replace(' ', '').isalnum():
            anomalies.append(f"Ligne {rang} : numéro « {numero} » invalide (17 lettres ou chiffres au plus), ignoré.")
            continue
        if not intitule:
            anomalies.append(f"Ligne {rang} : le tiers {numero} n'a pas d'intitulé, ignoré.")
            continue
        vus.add(numero)
        t = {'numero': numero, 'intitule': intitule[:200], 'type': type_, 'ville': ville[:100]}
        if 'collectif' in cols:
            t['collectif'] = _numero(_cellule(ligne, cols, 'collectif'))
        if 'actif' in cols:
            t['actif'] = _oui(_cellule(ligne, cols, 'actif'))
        tiers.append(t)
    classeur.close()
    if cols is None:
        raise ErreurImport("Aucune ligne d'en-tête trouvée : le fichier doit avoir des colonnes "
                           "« Type », « Compte tiers » et « Intitulé du tiers ».")
    if not tiers:
        raise ErreurImport("Aucun tiers trouvé dans le fichier.")
    return tiers, anomalies


def _collectifs():
    """{numéro: compte} des comptes qui peuvent être collectifs (imputables)."""
    return {c.numero: c for c in Compte.objects.imputables()}


def _changements(existant, t, collectifs):
    """[(champ, avant, après)] que l'import apporterait à `existant`."""
    voulu = {'intitule': t['intitule'], 'type': t['type'], 'ville': t['ville']}
    if t.get('collectif') in collectifs:
        voulu['compte_collectif'] = collectifs[t['collectif']]
    if 'actif' in t:
        voulu['actif'] = t['actif']
    return [(champ, getattr(existant, champ), v) for champ, v in voulu.items() if getattr(existant, champ) != v]


_LIBELLES = {'intitule': 'Intitulé', 'type': 'Type', 'ville': 'Ville', 'compte_collectif': 'Compte collectif',
             'actif': 'Actif'}


def _lisible(champ, valeur):
    if champ == 'type':
        return TYPES.get(valeur, valeur)
    if champ == 'compte_collectif':
        return valeur.numero if valeur else '—'
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    return valeur or '—'


def analyser(tiers):
    """Ce que ferait l'import, sans rien écrire."""
    existants = {t.numero: t for t in Tiers.objects.select_related('compte_collectif')}
    collectifs = _collectifs()
    rapport = {'nouveaux': [], 'modifies': [], 'identiques': 0, 'collectifs_inconnus': []}
    for t in tiers:
        if t.get('collectif') and t['collectif'] not in collectifs:
            rapport['collectifs_inconnus'].append(t)
        existant = existants.get(t['numero'])
        if existant is None:
            rapport['nouveaux'].append(t)
            continue
        changes = _changements(existant, t, collectifs)
        if changes:
            rapport['modifies'].append({'fichier': t, 'tiers': existant, 'changes': changes,
                                        'lisible': [(_LIBELLES[c], _lisible(c, a), _lisible(c, b))
                                                    for c, a, b in changes]})
        else:
            rapport['identiques'] += 1
    numeros = {t['numero'] for t in tiers}
    rapport['absents'] = [e for n, e in sorted(existants.items()) if n not in numeros]
    return rapport


def appliquer(tiers):
    """Applique l'import ; renvoie le rapport de ce qui a été fait."""
    with transaction.atomic():
        rapport = analyser(tiers)
        collectifs = _collectifs()
        par_numero = [(n, c.pk) for n, c in collectifs.items()]
        Tiers.objects.bulk_create([
            Tiers(numero=t['numero'], intitule=t['intitule'], type=t['type'], ville=t['ville'],
                  actif=t.get('actif', True),
                  compte_collectif_id=(collectifs[t['collectif']].pk if t.get('collectif') in collectifs
                                       else collectif_deduit(t['numero'], par_numero)))
            for t in rapport['nouveaux']])
        for m in rapport['modifies']:
            objet = m['tiers']
            for champ, _, apres in m['changes']:
                setattr(objet, champ, apres)
            objet.save(update_fields=[champ for champ, _, _ in m['changes']])
    return rapport


def classeur():
    """Le plan tiers dans un classeur Excel réimportable."""
    from django.utils import timezone
    from openpyxl import Workbook
    from openpyxl.styles import Alignment
    from rapports.export import populate_sheet

    tiers = list(Tiers.objects.select_related('compte_collectif').order_by('type', 'numero'))
    lignes = [[t.get_type_display(), t.numero, t.intitule,
               t.compte_collectif.numero if t.compte_collectif else '', t.ville, 'Oui' if t.actif else 'Non']
              for t in tiers]
    wb = Workbook()
    ws = wb.active
    entete = populate_sheet(ws, 'Plan tiers', COLONNES_EXPORT, lignes, genere_le=timezone.localtime())
    gauche = Alignment(horizontal='left', vertical='center')
    for rang in range(entete + 1, entete + 1 + len(tiers)):
        for col in (2, 4):
            ws.cell(row=rang, column=col).number_format = '@'
        ws.cell(row=rang, column=3).alignment = gauche
    ws.column_dimensions['C'].width = 45
    return wb
