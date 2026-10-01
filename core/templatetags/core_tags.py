from django import template

register = template.Library()


@register.filter
def app_label(obj):
    return obj._meta.app_label


@register.filter
def model_name(obj):
    return obj._meta.model_name


@register.simple_tag
def range_tag(n):
    return range(n)


@register.filter
def duree_hms(secondes):
    """3723 -> '01:02:03' ; 65 -> '01:05' ; None -> '—'. Même format que
    RendezVous._fmt_sec (patients/models.py) pour rester cohérent."""
    if secondes is None:
        return '—'
    secondes = max(0, int(secondes))
    h, rem = divmod(secondes, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


@register.filter
def get_item(mapping, key):
    """Lookup par clé variable — le point Django ne résout que des clés
    littérales, ceci permet un dict[variable] dans le gabarit."""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.inclusion_tag('includes/historique_sidebar.html')
def historique_sidebar(obj):
    from core.models import LogActivite
    from django.contrib.contenttypes.models import ContentType
    if obj is None or not hasattr(obj, 'pk') or obj.pk is None:
        return {'logs': []}
    ct = ContentType.objects.get_for_model(obj)
    logs = LogActivite.objects.filter(
        content_type=ct, object_id=obj.pk
    ).select_related('user').order_by('-date')[:50]
    return {'logs': logs}


@register.filter
def nombre(valeur):
    """Un nombre sans décimales inutiles, pour du texte affiché.

    `quantite` × `prix_unitaire` additionne les décimales des deux : un
    montant sortait à quatre décimales, « 4 000,0000 » là où on attend
    « 4 000 ». Et même sans multiplication, un `DecimalField(decimal_places=2)`
    rend « 1,00 » pour une boîte.

    Les décimales réellement significatives sont conservées : 4000,25 le reste.
    Le séparateur suit la langue — virgule en français.
    """
    from decimal import Decimal, InvalidOperation

    from django.utils.formats import number_format

    if valeur in (None, ''):
        return ''
    try:
        d = Decimal(str(valeur)).normalize()
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    # `normalize()` transforme 4000 en 4E+3 : on le ramène en notation simple.
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    decimales = max(0, -d.as_tuple().exponent)
    return number_format(d, decimal_pos=decimales, use_l10n=True)


@register.filter
def nom_court_planning(valeur):
    """Raccourcit chaque nom d'une cellule de planning à 2 mots au plus — ex.
    « Dr YAPI ASSI RODOLPHE » devient « Dr YAPI R » (titre + premier mot du
    nom + initiale du dernier mot). Plusieurs médecins sur une même cellule
    sont séparés par « / », chacun est raccourci indépendamment.

    Purement un raccourci d'AFFICHAGE : n'altère jamais la valeur stockée en
    base (le texte brut continue de servir au rapprochement avec les congés
    et aux exports), seul le gabarit qui l'affiche applique ce filtre.
    """
    if not valeur:
        return valeur
    segments = [s.strip() for s in str(valeur).split('/')]
    out = []
    for seg in segments:
        if not seg:
            continue
        mots = seg.split()
        if len(mots) <= 2 or mots[0] not in ('Dr', 'SF'):
            out.append(seg)
            continue
        titre, *noms = mots
        out.append(f"{titre} {noms[0]} {noms[-1][0].upper()}")
    return ' / '.join(out)


@register.filter
def valeur_champ(valeur):
    """Le même nombre, mais pour l'attribut `value` d'un `<input type=number>`.

    Un champ numérique HTML n'accepte que le point décimal. Rendu par le
    gabarit sous une langue française, un Decimal devient « 1,00 » — et le
    navigateur, ne sachant pas le lire, **affiche le champ vide**. La quantité
    d'une facture qu'on rouvrait pour la corriger disparaissait ainsi de
    l'écran ; il suffisait d'enregistrer pour la perdre.
    """
    from decimal import Decimal, InvalidOperation

    if valeur in (None, ''):
        return ''
    try:
        d = Decimal(str(valeur)).normalize()
    except (InvalidOperation, TypeError, ValueError):
        return valeur
    if d == d.to_integral_value():
        d = d.quantize(Decimal(1))
    return f'{d:f}'
