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
