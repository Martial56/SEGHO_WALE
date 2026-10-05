import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# Le contenu du guide signale systématiquement un bouton, un champ ou une
# valeur d'exemple entre guillemets français « ... » — on les met en gras
# plutôt que de réécrire chaque article en HTML.
_GUILLEMETS = re.compile(r'«\s*([^»]+?)\s*»')


@register.filter(name='guide_format', is_safe=True)
def guide_format(texte):
    if not texte:
        return ''
    echappe = escape(texte)
    gras = _GUILLEMETS.sub(lambda m: '« <strong>%s</strong> »' % m.group(1), echappe)
    paragraphes = [p for p in gras.split('\n\n') if p.strip()]
    return mark_safe(''.join('<p>%s</p>' % p.replace('\n', '<br>') for p in paragraphes))
