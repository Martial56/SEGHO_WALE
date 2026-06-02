from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()

MODULE_COLORS = [
    'mod-teal', 'mod-green', 'mod-sky', 'mod-violet', 'mod-coral',
    'mod-teal2', 'mod-rose', 'mod-amber', 'mod-indigo', 'mod-plum',
    'mod-green', 'mod-teal',
]


@register.simple_tag
def module_url(url_name):
    """Résout un nom d'URL de module en URL absolue, ou retourne '#' si inexistant."""
    if not url_name:
        return '/admin/'
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return '#'


@register.simple_tag
def module_color(index):
    """Retourne une classe de couleur cyclique pour une carte module."""
    return MODULE_COLORS[index % len(MODULE_COLORS)]
