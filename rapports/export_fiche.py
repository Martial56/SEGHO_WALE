"""Export Excel / CSV des fiches de rapport mensuel (maternité, soins,
gynécologie, médecine générale).

Les fiches sont d'abord des pages HTML calquées sur le papier. Plutôt que de
réécrire la disposition de chacune une seconde fois pour Excel — et de voir
les deux diverger au premier ajout de ligne —, on relit la page rendue : les
titres de section deviennent des lignes de texte, les tableaux sont recopiés
case pour case, fusions (colspan / rowspan) et cases grisées comprises. Ce qui
ne s'imprime pas (barre d'outils, notes d'écran) ne s'exporte pas non plus.
"""
import csv
import io
import re
from html.parser import HTMLParser

# Blocs dont rien ne doit passer dans le fichier.
CLASSES_IGNOREES = {'print-toolbar', 'rm-note-ecran', 'rm-header', 'rm-page-num', 'rm-signatures'}
BALISES_IGNOREES = {'script', 'style', 'head', 'form', 'button'}
# Blocs de texte repris comme une ligne à part entière.
CLASSES_TEXTE = {'rm-title', 'rm-ligne-info', 'rm-section-title', 'rm-sub-title',
                 'rm-nb', 'rm-legende', 'rm-legende-fiche'}
BALISES_VIDES = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                 'link', 'meta', 'source', 'track', 'wbr'}


def _texte(morceaux):
    return re.sub(r'\s+', ' ', ''.join(morceaux)).strip()


def _valeur(texte):
    """« 12 » → 12 : Excel doit pouvoir additionner les cases."""
    if re.fullmatch(r'-?\d+', texte):
        return int(texte)
    return texte


class _LecteurFiche(HTMLParser):
    """Découpe la page en blocs : ('titre', texte, niveau), ('page',) ou
    ('table', lignes) où chaque ligne est une liste de cellules
    {texte, colspan, rowspan, entete, style}."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocs = []
        self.pile = []          # [(balise, ignore, texte)] des éléments ouverts
        self.texte = None       # morceaux du bloc de texte en cours
        self.table = None
        self.ligne = None
        self.cellule = None

    def _ignore(self):
        return any(e[1] for e in self.pile)

    def handle_starttag(self, tag, attrs):
        if tag in BALISES_VIDES:
            if tag == 'br':
                self.handle_data(' ')
            return
        attrs = dict(attrs)
        classes = set((attrs.get('class') or '').split())
        ignore = tag in BALISES_IGNOREES or bool(classes & CLASSES_IGNOREES)
        texte = False
        if not ignore and not self._ignore():
            if 'rm-page' in classes and self.blocs:
                self.blocs.append(('page',))
            if self.table is None and self.texte is None and (classes & CLASSES_TEXTE or tag == 'h3'):
                self.texte = []
                texte = 'titre' if classes & {'rm-title'} else 'section'
            elif tag == 'table':
                self.table = []
            elif tag == 'tr' and self.table is not None:
                self.ligne = []
                self.table.append(self.ligne)
            elif tag in ('td', 'th') and self.ligne is not None:
                style = None
                if 'rmg-noir' in classes:
                    style = 'noir'
                elif 'rmg-grise' in classes:
                    style = 'grise'
                elif 'rmg-total' in classes:
                    style = 'total'
                self.cellule = {
                    'morceaux': [], 'entete': tag == 'th', 'style': style,
                    'colspan': int(attrs.get('colspan') or 1),
                    'rowspan': int(attrs.get('rowspan') or 1),
                    'libelle': 'rmg-label-col' in classes or 'lib' in classes,
                }
        self.pile.append((tag, ignore, texte))

    def handle_endtag(self, tag):
        if tag in BALISES_VIDES:
            return
        # Balise orpheline : on remonte jusqu'à l'élément correspondant.
        if not any(e[0] == tag for e in self.pile):
            return
        while self.pile:
            balise, ignore, texte = self.pile.pop()
            if texte and self.texte is not None:
                contenu = _texte(self.texte)
                if contenu:
                    self.blocs.append(('titre', contenu, texte))
                self.texte = None
            if balise in ('td', 'th') and self.cellule is not None and self.ligne is not None:
                self.cellule['texte'] = _texte(self.cellule.pop('morceaux'))
                self.ligne.append(self.cellule)
                self.cellule = None
            elif balise == 'tr':
                self.ligne = None
            elif balise == 'table' and self.table is not None:
                if self.table:
                    self.blocs.append(('table', self.table))
                self.table = None
            if balise == tag:
                break

    def handle_data(self, data):
        if self._ignore():
            return
        if self.cellule is not None:
            self.cellule['morceaux'].append(data)
        elif self.texte is not None:
            self.texte.append(data)


def _grille(lignes):
    """Place les cellules d'un tableau HTML sur une grille, en tenant compte des
    fusions. Retourne [(ligne, colonne, cellule)] (0-indexés) et la largeur."""
    occupees = set()
    placees = []
    largeur = 0
    for r, ligne in enumerate(lignes):
        c = 0
        for cellule in ligne:
            while (r, c) in occupees:
                c += 1
            for dr in range(cellule['rowspan']):
                for dc in range(cellule['colspan']):
                    occupees.add((r + dr, c + dc))
            placees.append((r, c, cellule))
            c += cellule['colspan']
            largeur = max(largeur, c)
    return placees, largeur


def lire_fiche(html):
    lecteur = _LecteurFiche()
    lecteur.feed(html)
    lecteur.close()
    # Un saut de page en tête ou en fin n'a pas de sens.
    blocs = lecteur.blocs
    while blocs and blocs[-1][0] == 'page':
        blocs.pop()
    return blocs


def nb_lignes(blocs):
    return sum(len(b[1]) for b in blocs if b[0] == 'table')


def construire_csv(html):
    tampon = io.StringIO()
    tampon.write('﻿')  # BOM : Excel lit l'UTF-8 et les accents
    ecrivain = csv.writer(tampon, delimiter=';')
    for bloc in lire_fiche(html):
        if bloc[0] == 'titre':
            ecrivain.writerow([bloc[1]])
        elif bloc[0] == 'page':
            ecrivain.writerow([])
        else:
            placees, largeur = _grille(bloc[1])
            hauteur = max(r for r, _, _ in placees) + 1 if placees else 0
            grille = [[''] * largeur for _ in range(hauteur)]
            for r, c, cellule in placees:
                grille[r][c] = cellule['texte']
            for ligne in grille:
                ecrivain.writerow(ligne)
            ecrivain.writerow([])
    return tampon.getvalue().encode('utf-8')


def construire_xlsx(html, titre_feuille='Fiche', paysage=False):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    trait = Side(style='thin', color='FF333333')
    bordure = Border(left=trait, right=trait, top=trait, bottom=trait)
    fonds = {
        'entete': PatternFill('solid', start_color='FFE0E0E0'),
        'grise': PatternFill('solid', start_color='FFA6A6A6'),
        'noir': PatternFill('solid', start_color='FF000000'),
        'total': PatternFill('solid', start_color='FFF3F4F6'),
    }
    centre = Alignment(horizontal='center', vertical='center', wrap_text=True)
    gauche = Alignment(horizontal='left', vertical='center', wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = titre_feuille[:31]
    largeurs = {}
    ligne_xl = 1

    for bloc in lire_fiche(html):
        if bloc[0] == 'titre':
            cellule = ws.cell(row=ligne_xl, column=1, value=bloc[1])
            cellule.font = Font(bold=True, size=13 if bloc[2] == 'titre' else 11)
            ligne_xl += 1
            continue
        if bloc[0] == 'page':
            ligne_xl += 1
            continue

        placees, _ = _grille(bloc[1])
        for r, c, info in placees:
            ligne, colonne = ligne_xl + r, 1 + c
            fin_ligne = ligne + info['rowspan'] - 1
            fin_colonne = colonne + info['colspan'] - 1
            cellule = ws.cell(row=ligne, column=colonne, value=_valeur(info['texte']))
            # Toutes les cases de la fusion portent la bordure, sinon Excel
            # n'encadre que la première.
            for rr in range(ligne, fin_ligne + 1):
                for cc in range(colonne, fin_colonne + 1):
                    ws.cell(row=rr, column=cc).border = bordure
            if fin_ligne > ligne or fin_colonne > colonne:
                ws.merge_cells(start_row=ligne, start_column=colonne,
                               end_row=fin_ligne, end_column=fin_colonne)
            libelle = info['libelle'] or (c == 0 and not info['entete'])
            cellule.alignment = gauche if libelle else centre
            if info['entete']:
                cellule.font = Font(bold=True)
                cellule.fill = fonds['entete']
            elif info['style']:
                cellule.fill = fonds[info['style']]
            if libelle:
                cellule.font = Font(bold=True)
            if info['colspan'] == 1:
                taille = 60 if libelle else len(info['texte']) + 2
                largeurs[colonne] = max(largeurs.get(colonne, 6), min(taille, 60))
        hauteur = max(r for r, _, _ in placees) + 1 if placees else 0
        ligne_xl += hauteur + 1

    for colonne, largeur in largeurs.items():
        ws.column_dimensions[get_column_letter(colonne)].width = largeur

    ws.page_setup.orientation = 'landscape' if paysage else 'portrait'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()
