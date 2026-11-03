"""Import et export du plan comptable au format Excel.

Deux présentations sont lues :

- l'export « Liste des comptes » de **Sage 100 Comptabilité** que fournit
  l'expert-comptable : colonnes Type (Total / Détail), N° compte, Intitulé,
  Raccourci, Nature de compte, avec bandeau et en-têtes répétés à chaque page.
  Les cellules fusionnées décalent les valeurs par rapport aux en-têtes : on
  repère donc la ligne d'en-tête, puis on lit chaque ligne de compte par sa
  forme (numéro, puis premier texte qui suit, puis la nature reconnue) ;
- l'export de ce module (Numéro, Intitulé, Type, Nature, Actif, À confirmer),
  pour corriger le plan dans Excel et le réimporter.

L'import ne supprime rien et ne change jamais un numéro. Il crée les comptes
nouveaux et met à jour intitulé, type et nature des comptes existants. Un
compte déjà mouvementé ou désigné ailleurs (correspondance, motif, trésorerie,
budget…) ne devient pas compte de totalisation : il est signalé en conflit et
laissé tel quel, à remplacer d'abord dans les correspondances.
"""
import unicodedata

from django.db import transaction

from .models import Compte

NATURES = {cle: libelle for cle, libelle in Compte.NATURE}
_NATURE_PAR_LIBELLE = {}
COLONNES_EXPORT = ['Numéro', 'Intitulé', 'Type', 'Nature', 'Actif', 'À confirmer']


class ErreurImport(Exception):
    pass


def _norm(valeur):
    """Texte sans accents, minuscules, lettres et chiffres seulement."""
    texte = unicodedata.normalize('NFKD', str(valeur or ''))
    return ''.join(ch for ch in texte.lower() if ch.isalnum())


for _cle, _libelle in Compte.NATURE:
    _NATURE_PAR_LIBELLE[_norm(_libelle)] = _cle
_NATURE_PAR_LIBELLE.update({'amortissementprovision': 'amortissement', 'salarie': 'salarie'})


def _oui(valeur):
    return _norm(valeur) in ('oui', 'o', 'vrai', 'true', '1', 'x')


def _numero(valeur):
    if isinstance(valeur, float) and valeur.is_integer():
        valeur = int(valeur)
    return str(valeur).strip() if valeur is not None else ''


def _entete(ligne):
    """Positions des colonnes si `ligne` est une ligne d'en-tête, sinon None."""
    cols = {}
    for i, v in enumerate(ligne):
        n = _norm(v)
        if not n:
            continue
        if n in ('ncompte', 'numero', 'numerocompte', 'numerodecompte', 'compte', 'nocompte'):
            cols.setdefault('numero', i)
        elif n.startswith('intitule'):
            cols.setdefault('intitule', i)
        elif n == 'type':
            cols['type'] = i
        elif n.startswith('nature'):
            cols['nature'] = i
        elif n == 'actif':
            cols['actif'] = i
        elif n.startswith('aconfirmer'):
            cols['a_valider'] = i
    return cols if {'numero', 'intitule'} <= cols.keys() else None


def lire(fichier):
    """Comptes lus dans le classeur : ([{numero, intitule, totalisation,
    nature, actif?, a_valider?}], [anomalies])."""
    from openpyxl import load_workbook
    try:
        classeur = load_workbook(fichier, read_only=True, data_only=True)
    except Exception:
        raise ErreurImport("Ce fichier n'est pas un classeur Excel (.xlsx) lisible.")
    feuille = classeur.worksheets[0]
    cols, comptes, anomalies, vus = None, [], [], set()
    for rang, ligne in enumerate(feuille.iter_rows(values_only=True), start=1):
        ligne = list(ligne)
        if cols is None:
            cols = _entete(ligne)
            continue
        if cols['numero'] >= len(ligne):
            continue
        numero = _numero(ligne[cols['numero']])
        if not numero.isdigit():
            continue  # bandeau, en-tête répété, ligne vide
        # Intitulé : premier texte à droite du numéro (cellules fusionnées).
        suite = [(i, v) for i, v in enumerate(ligne) if i > cols['numero'] and v not in (None, '')]
        intitule = str(suite[0][1]).strip()[:200] if suite else ''
        if numero in vus:
            anomalies.append(f"Ligne {rang} : le compte {numero} figure deux fois, seule la première ligne est prise.")
            continue
        if numero[0] == '0' or len(numero) > 12:
            anomalies.append(f"Ligne {rang} : numéro « {numero} » invalide (12 chiffres au plus, classe 1 à 9), ignoré.")
            continue
        if not intitule:
            anomalies.append(f"Ligne {rang} : le compte {numero} n'a pas d'intitulé, ignoré.")
            continue
        vus.add(numero)
        type_ = _norm(ligne[cols['type']]) if 'type' in cols and cols['type'] < len(ligne) else ''
        nature = next((_NATURE_PAR_LIBELLE[_norm(v)] for _, v in suite[1:]
                       if _norm(v) in _NATURE_PAR_LIBELLE), '')
        compte = {'numero': numero, 'intitule': intitule, 'totalisation': type_ == 'total', 'nature': nature}
        if 'actif' in cols and cols['actif'] < len(ligne):
            compte['actif'] = _oui(ligne[cols['actif']])
        if 'a_valider' in cols and cols['a_valider'] < len(ligne):
            compte['a_valider'] = _oui(ligne[cols['a_valider']])
        comptes.append(compte)
    classeur.close()
    if cols is None:
        raise ErreurImport("Aucune ligne d'en-tête trouvée : le fichier doit avoir des colonnes "
                           "« N° compte » (ou « Numéro ») et « Intitulé ».")
    if not comptes:
        raise ErreurImport("Aucun compte trouvé dans le fichier.")
    return comptes, anomalies


def comptes_utilises():
    """Ids des comptes mouvementés ou désignés par un autre enregistrement."""
    ids = set()
    for relation in Compte._meta.related_objects:
        modele = relation.related_model
        ids.update(modele._base_manager.exclude(**{f'{relation.field.name}__isnull': True})
                   .values_list(relation.field.attname, flat=True))
    return ids


def _changements(existant, c):
    """[(champ, avant, après)] que l'import apporterait à `existant`."""
    voulu = {'intitule': c['intitule'], 'totalisation': c['totalisation'], 'nature': c['nature'],
             'a_valider': c.get('a_valider', False)}
    if 'actif' in c:
        voulu['actif'] = c['actif']
    return [(champ, getattr(existant, champ), v) for champ, v in voulu.items() if getattr(existant, champ) != v]


_LIBELLES = {'intitule': 'Intitulé', 'totalisation': 'Type', 'nature': 'Nature', 'a_valider': 'À confirmer',
             'actif': 'Actif'}


def _lisible(champ, valeur):
    if champ == 'totalisation':
        return 'Total' if valeur else 'Détail'
    if champ == 'nature':
        return NATURES.get(valeur, valeur)
    if isinstance(valeur, bool):
        return 'Oui' if valeur else 'Non'
    return valeur


def decrire(changes):
    """« Intitulé : avant → après » pour l'aperçu."""
    return [(_LIBELLES[champ], _lisible(champ, avant), _lisible(champ, apres)) for champ, avant, apres in changes]


def analyser(comptes):
    """Ce que ferait l'import, sans rien écrire."""
    existants = {c.numero: c for c in Compte.objects.all()}
    utilises = comptes_utilises()
    rapport = {'nouveaux': [], 'modifies': [], 'conflits': [], 'identiques': 0}
    for c in comptes:
        existant = existants.get(c['numero'])
        if existant is None:
            rapport['nouveaux'].append(c)
            continue
        changes = _changements(existant, c)
        if not changes:
            rapport['identiques'] += 1
        elif c['totalisation'] and not existant.totalisation and existant.pk in utilises:
            rapport['conflits'].append({'fichier': c, 'compte': existant})
        else:
            rapport['modifies'].append({'fichier': c, 'compte': existant, 'changes': changes,
                                        'lisible': decrire(changes)})
    numeros = {c['numero'] for c in comptes}
    rapport['absents'] = [{'compte': e, 'utilise': e.pk in utilises}
                          for n, e in sorted(existants.items()) if n not in numeros]
    return rapport


def appliquer(comptes):
    """Applique l'import ; renvoie le rapport de ce qui a été fait."""
    with transaction.atomic():
        rapport = analyser(comptes)
        Compte.objects.bulk_create([
            Compte(numero=c['numero'], intitule=c['intitule'], totalisation=c['totalisation'],
                   nature=c['nature'], actif=c.get('actif', True), a_valider=c.get('a_valider', False))
            for c in rapport['nouveaux']])
        for m in rapport['modifies']:
            compte = m['compte']
            for champ, _, apres in m['changes']:
                setattr(compte, champ, apres)
            compte.save(update_fields=[champ for champ, _, _ in m['changes']])
    return rapport


def classeur():
    """Le plan comptable dans un classeur Excel réimportable."""
    from django.utils import timezone
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    from rapports.export import POLICE, populate_sheet

    comptes = list(Compte.objects.order_by('numero'))
    lignes = [[c.numero, c.intitule, 'Total' if c.totalisation else 'Détail', NATURES.get(c.nature, ''),
               'Oui' if c.actif else 'Non', 'Oui' if c.a_valider else 'Non'] for c in comptes]
    wb = Workbook()
    ws = wb.active
    entete = populate_sheet(ws, 'Plan comptable', COLONNES_EXPORT, lignes, genere_le=timezone.localtime())
    gauche = Alignment(horizontal='left', vertical='center')
    gras = Font(name=POLICE, bold=True)
    for rang, c in enumerate(comptes, start=entete + 1):
        ws.cell(row=rang, column=1).number_format = '@'
        ws.cell(row=rang, column=2).alignment = gauche
        if c.totalisation:
            for cell in ws[rang]:
                cell.font = gras
    ws.column_dimensions['B'].width = 50
    return wb
