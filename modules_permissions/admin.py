import json
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group
from django.utils.html import format_html
from django.urls import path
from django.http import JsonResponse

from .models import Module, GroupModule, UserModuleOverride


# ─── Module Admin ────────────────────────────────────────────────────────────

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'code', 'url_name', 'order', 'is_active', 'groupes_count')
    list_editable = ('order', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('order', 'name')

    def groupes_count(self, obj):
        count = obj.group_modules.count()
        return format_html('<span style="font-weight:bold">{}</span>', count)
    groupes_count.short_description = "Nb groupes"


# ─── GroupModule Admin ────────────────────────────────────────────────────────

class GroupModuleInline(admin.TabularInline):
    model = GroupModule
    extra = 1
    verbose_name = "Module autorisé"
    verbose_name_plural = "Modules autorisés pour ce groupe"


class GroupAdminWithModules(admin.ModelAdmin):
    """Remplace le GroupAdmin par défaut pour gérer les modules."""
    list_display = ('name', 'modules_list')
    inlines = [GroupModuleInline]
    filter_horizontal = ('permissions',)

    def modules_list(self, obj):
        modules = [gm.module for gm in obj.group_modules.select_related('module')]
        if not modules:
            return format_html('<span style="color:#999">Aucun module</span>')
        badges = ' '.join(
            f'<span style="background:#e8f4f8;padding:2px 8px;border-radius:10px;font-size:11px;margin:1px;display:inline-block">'
            f'{m.icon} {m.name}</span>'
            for m in modules
        )
        return format_html(badges)
    modules_list.short_description = "Modules autorisés"


# Désenregistrer le Group admin par défaut et le remplacer
admin.site.unregister(Group)
admin.site.register(Group, GroupAdminWithModules)


# ─── Widget JS pour filtrer les modules dans UserAdmin ───────────────────────

class UserModuleOverrideInline(admin.TabularInline):
    model = UserModuleOverride
    extra = 0
    verbose_name = "Override de module"
    verbose_name_plural = "Overrides de modules individuels"


class CustomUserAdmin(BaseUserAdmin):
    """
    UserAdmin étendu :
    - Affiche les modules du/des groupe(s) sélectionné(s) dans la section "Permissions"
    - Permet des overrides individuels via une inline
    - Ajoute un widget JS qui filtre les modules selon le groupe sélectionné
    """
    inlines = [UserModuleOverrideInline]

    # Ajouter la liste des modules en lecture seule dans le fieldset Permissions
    fieldsets = list(BaseUserAdmin.fieldsets)  # copie

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Injecter un champ "modules actifs" dans la section Permissions
        new_fieldsets = []
        for name, opts in fieldsets:
            if name == 'Permissions' or name == 'Droits':
                fields = list(opts.get('fields', []))
                new_fieldsets.append((name, {**opts, 'fields': fields}))
            else:
                new_fieldsets.append((name, opts))
        return new_fieldsets

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                'modules-par-groupe/',
                self.admin_site.admin_view(self.modules_par_groupe_view),
                name='modules_par_groupe',
            ),
        ]
        return extra + urls

    def modules_par_groupe_view(self, request):
        """
        API JSON : retourne les modules autorisés pour une liste de group IDs.
        Utilisée par le JS du formulaire UserAdmin.
        """
        group_ids_raw = request.GET.getlist('group_ids')
        try:
            group_ids = [int(g) for g in group_ids_raw if g]
        except ValueError:
            return JsonResponse({'modules': []})

        if not group_ids:
            return JsonResponse({'modules': []})

        group_modules = (
            GroupModule.objects
            .filter(group_id__in=group_ids)
            .select_related('module', 'group')
            .order_by('module__order', 'module__name')
        )

        # Dédoublonner par module
        seen = set()
        modules_data = []
        for gm in group_modules:
            if gm.module_id not in seen:
                seen.add(gm.module_id)
                modules_data.append({
                    'id': gm.module.id,
                    'name': gm.module.name,
                    'icon': gm.module.icon,
                    'code': gm.module.code,
                    'group': gm.group.name,
                })

        return JsonResponse({'modules': modules_data})

    class Media:
        css = {'all': ('modules_permissions/css/user_admin.css',)}
        js = ('modules_permissions/js/user_admin.js',)


# Désenregistrer le UserAdmin par défaut et le remplacer
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
