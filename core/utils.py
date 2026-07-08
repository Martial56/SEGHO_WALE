import colorsys
import csv
import re

from django.http import HttpResponse

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
        writer.writerow(['' if v is None else v for v in row])
    return response
