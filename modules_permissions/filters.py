from django import template

register = template.Library()

@register.filter
def filter_modules_by_group(modules, group):
    return modules.filter(groups=group)

@register.filter
def has_permission(module, permission):
    return module.permissions.filter(name=permission).exists()