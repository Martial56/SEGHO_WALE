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
