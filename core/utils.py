import colorsys
import csv
import re
import unicodedata

from django.http import HttpResponse


def annees_avant(d, n):
    """Recule la date `d` de `n` années, sans planter un 29 février.

    `d.replace(year=...)` lève ValueError quand `d` est un 29 février et que
    l'année d'arrivée n'est pas bissextile (ex. 2028-02-29 moins 18 ans →
    2010-02-29 qui n'existe pas). On retombe alors sur le 28 février. Sert au
    calcul des bornes de tranche d'âge des patients (majorité, senior)."""
    try:
        return d.replace(year=d.year - n)
    except ValueError:
        return d.replace(year=d.year - n, day=28)


# Préfixes d'URL utilisés pour savoir "dans quel module" se trouve l'utilisateur,
# afin de n'afficher dans la cloche de notifications que les alertes pertinentes
# pour ce module (pas de mélange, rien sur la page d'accueil des modules).
MODULE_URL_PREFIXES = {
    'employer': '/employes/',
    'conges': '/conges/',
    'pharmacie': '/pharmacie/',
    'facturation': '/facturation/',
    'laboratoire': '/laboratoire/',
    'planning': '/planning/',
    'soins': '/soins/',
}


def current_module(request):
    """Retourne la clé du module courant d'après le préfixe de l'URL, ou None
    (page d'accueil, compte, ou tout module sans notifications dédiées)."""
    path = request.path
    for module, prefix in MODULE_URL_PREFIXES.items():
        if path.startswith(prefix):
            return module
    return None

# Couleur par défaut = couleur du logo (vert sauge), échantillonnée depuis static/img/logo.png
DEFAULT_ACCENT_COLOR = '#4f9b4b'

# Courbe de luminosité utilisée pour dériver les 11 nuances à partir d'une seule
# couleur de base (teinte + saturation conservées, seule la luminosité varie).
_LIGHTNESS_STEPS = {
    50: 0.955, 100: 0.90, 200: 0.80, 300: 0.68, 400: 0.54,
    500: 0.42, 600: 0.34, 700: 0.26, 800: 0.16, 900: 0.11, 950: 0.07,
}

HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def is_valid_hex_color(value):
    return bool(value) and bool(HEX_RE.match(value))


def build_accent_ramp(base_hex, var_prefix='teal'):
    """Génère les 11 nuances --{prefix}-50 .. --{prefix}-950 à partir d'une couleur
    de base, en conservant sa teinte/saturation et en ne faisant varier que la
    luminosité. La couleur de base fournie correspond à la nuance 600 (bouton
    principal / accent le plus utilisé dans l'application)."""
    if not is_valid_hex_color(base_hex):
        base_hex = DEFAULT_ACCENT_COLOR

    r = int(base_hex[1:3], 16) / 255
    g = int(base_hex[3:5], 16) / 255
    b = int(base_hex[5:7], 16) / 255
    h, _l, s = colorsys.rgb_to_hls(r, g, b)

    ramp = {}
    for step, l in _LIGHTNESS_STEPS.items():
        rr, gg, bb = colorsys.hls_to_rgb(h, l, s)
        ramp[step] = '#{:02x}{:02x}{:02x}'.format(round(rr * 255), round(gg * 255), round(bb * 255))

    # La nuance 600 (bouton principal) doit correspondre exactement à la couleur
    # choisie — pas une approximation issue de l'aller-retour HLS.
    ramp[600] = base_hex.lower()

    return {f'--{var_prefix}-{step}': color for step, color in ramp.items()}


def _hex_to_rgb_triplet(hex_color):
    return f'{int(hex_color[1:3], 16)},{int(hex_color[3:5], 16)},{int(hex_color[5:7], 16)}'


def build_accent_css(base_hex, var_prefix='teal'):
    """Retourne un bloc de déclarations CSS prêt à injecter dans un :root { ... }."""
    ramp = build_accent_ramp(base_hex, var_prefix=var_prefix)
    declarations = [f'{name}: {value};' for name, value in ramp.items()]
    # Variantes "R,G,B" utilisées par les rgba(var(--teal-600-rgb), .1) des modules
    for step in _LIGHTNESS_STEPS:
        declarations.append(f'--{var_prefix}-{step}-rgb: {_hex_to_rgb_triplet(ramp[f"--{var_prefix}-{step}"])};')
    return ' '.join(declarations)


_FORMULA_LEAD_CHARS = ('=', '+', '-', '@', '\t', '\r')


def _csv_safe_cell(value):
    """Neutralise l'injection de formule Excel/DDE (=CMD(), =HYPERLINK(), etc.)
    en préfixant d'une apostrophe toute valeur texte commençant par un
    caractère déclencheur de formule — Excel l'interprète alors comme du
    texte forcé, les autres tableurs/CSV l'ignorent silencieusement."""
    if isinstance(value, str) and value and value[0] in _FORMULA_LEAD_CHARS:
        return "'" + value
    return value


def csv_response(filename, headers, rows, delimiter=';'):
    """Génère une réponse CSV téléchargeable, avec BOM UTF-8 pour un affichage
    correct des accents dans Excel. `rows` est un itérable de listes/tuples ;
    les valeurs None sont converties en chaîne vide."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    response.write('﻿')
    writer = csv.writer(response, delimiter=delimiter)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_safe_cell('' if v is None else v) for v in row])
    return response


# ── Anciens badges vCard (module Présence / employer) ───────────────────────
# Les cartes imprimées avant SEGHO-WALE encodent une vCard (Nom, Téléphone,
# Adresse, Société, Titre) plutôt que le matricule. Le téléphone et l'adresse
# sont identiques sur toutes les cartes (pas des identifiants) ; seul le
# couple Nom complet + Titre diffère d'un employé à l'autre.

_VCARD_FIELD_RE = {
    'fn':    re.compile(r'^FN:(.*)$', re.IGNORECASE | re.MULTILINE),
    'n':     re.compile(r'^N:(.*)$', re.IGNORECASE | re.MULTILINE),
    'titre': re.compile(r'^TITLE:(.*)$', re.IGNORECASE | re.MULTILINE),
}


def normalize_badge_text(value):
    """Majuscules, sans accents, espaces réduits — pour comparer un texte
    scanné à une valeur stockée sans être sensible aux variations de casse,
    d'accents ou d'espacement."""
    if not value:
        return ''
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = value.upper()
    return ' '.join(value.split())


def parse_vcard_nom_titre(raw_text):
    """Extrait (nom, titre) d'une vCard scannée (BEGIN:VCARD...END:VCARD).
    Retourne (None, None) si le texte n'est pas une vCard reconnaissable."""
    if not raw_text or 'BEGIN:VCARD' not in raw_text.upper():
        return None, None
    nom = titre = None
    # FN (nom complet déjà formaté) est prioritaire sur N (structuré
    # famille;prénoms;...), présent en secours seulement sur certaines vCards.
    m = _VCARD_FIELD_RE['fn'].search(raw_text)
    if m:
        nom = m.group(1).strip()
    else:
        m = _VCARD_FIELD_RE['n'].search(raw_text)
        if m:
            parts = [p.strip() for p in m.group(1).split(';') if p.strip()]
            nom = ' '.join(parts) if parts else None
    m = _VCARD_FIELD_RE['titre'].search(raw_text)
    if m:
        titre = m.group(1).strip()
    return nom, titre


def code_ancien_badge_from_vcard(raw_text):
    """Construit la clé normalisée « NOM|TITRE » à partir du texte brut d'un
    ancien badge scanné. Retourne None si ce n'est pas une vCard exploitable."""
    nom, titre = parse_vcard_nom_titre(raw_text)
    if not nom:
        return None
    return f'{normalize_badge_text(nom)}|{normalize_badge_text(titre)}'
