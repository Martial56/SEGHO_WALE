from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Lookup par clé variable — pour les tableaux âge × sexe où la clé de
    tranche d'âge est une variable de boucle (le point Django ne résout que
    des clés littérales)."""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None
