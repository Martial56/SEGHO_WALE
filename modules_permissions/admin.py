import json
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User, Group
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.urls import path, reverse
from django.http import JsonResponse

from .models import (
    Module, GroupModule, UserModuleOverride,
    NavItem, GroupNavItemRestriction, UserNavItemOverride,
    get_navitems_grouped, get_user_modules,
)


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


# ─── NavItem Admin (menus/sous-menus des barres de navigation internes) ──────

@admin.register(NavItem)
class NavItemAdmin(admin.ModelAdmin):
    list_display = ('label', 'code', 'module', 'is_active')
    list_editable = ('is_active',)
    list_filter = ('module', 'is_active')
    search_fields = ('label', 'code')
    ordering = ('module__order', 'label')


# ─── GroupModule Admin ────────────────────────────────────────────────────────

class GroupModuleInline(admin.TabularInline):
    model = GroupModule
    extra = 1
    verbose_name = "Module autorisé"
    verbose_name_plural = "Modules autorisés pour ce groupe"


class GroupAdminWithModules(admin.ModelAdmin):
    """Remplace le GroupAdmin par défaut pour gérer les modules."""
    list_display = ('name', 'modules_list', 'navitems_link')
    inlines = [GroupModuleInline]
    filter_horizontal = ('permissions',)
    readonly_fields = ('navitems_link',)

    def modules_list(self, obj):
        modules = [gm.module for gm in obj.group_modules.select_related('module')]
        if not modules:
            return mark_safe('<span style="color:#999">Aucun module</span>')
        return format_html_join(
            ' ',
            '<span style="background:#e8f4f8;padding:2px 8px;border-radius:10px;font-size:11px;margin:1px;display:inline-block">{} {}</span>',
            ((m.icon, m.name) for m in modules),
        )
    modules_list.short_description = "Modules autorisés"

    def navitems_link(self, obj):
        if not obj.pk:
            return "Enregistrer le groupe pour gérer ses menus."
        url = reverse('admin:modperm_group_navitems', args=[obj.pk])
        return format_html('<a class="button" href="{}">🗂️ Gérer les menus par module</a>', url)
    navitems_link.short_description = "Menus par module"

    def get_fields(self, request, obj=None):
        fields = ['name', 'permissions']
        if obj is not None:
            fields.append('navitems_link')
        return fields

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                '<int:group_id>/navitems/',
                self.admin_site.admin_view(self.group_navitems_view),
                name='modperm_group_navitems',
            ),
        ]
        return extra + urls

    def group_navitems_view(self, request, group_id):
        """
        Checklist des menus des SEULS modules attribués à ce groupe (section "Modules
        autorisés" de sa fiche) : coché = menu visible pour ce groupe (visible par défaut).
        """
        group = get_object_or_404(Group, pk=group_id)
        granted_module_ids = set(
            GroupModule.objects.filter(group=group).values_list('module_id', flat=True)
        )
        grouped = {
            module: items
            for module, items in get_navitems_grouped().items()
            if module and module.id in granted_module_ids
        }
        restricted_ids = set(
            GroupNavItemRestriction.objects.filter(group=group).values_list('nav_item_id', flat=True)
        )

        if request.method == 'POST':
            for items in grouped.values():
                for item in items:
                    checked = request.POST.get(f'nav_{item.id}') == 'on'
                    is_restricted = item.id in restricted_ids
                    if checked and is_restricted:
                        GroupNavItemRestriction.objects.filter(group=group, nav_item=item).delete()
                    elif not checked and not is_restricted:
                        GroupNavItemRestriction.objects.get_or_create(group=group, nav_item=item)
            messages.success(request, f"Menus mis à jour pour le groupe « {group.name} ».")
            return redirect(reverse('admin:modperm_group_navitems', args=[group.pk]))

        sections = [
            {
                'module': module,
                'items': [
                    {'item': item, 'checked': item.id not in restricted_ids}
                    for item in items
                ],
            }
            for module, items in grouped.items()
        ]

        context = dict(
            self.admin_site.each_context(request),
            title=f"Menus visibles — groupe « {group.name} »",
            group=group,
            sections=sections,
            opts=self.model._meta,
        )
        return render(request, 'modules_permissions/group_navitems.html', context)


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
    readonly_fields = ('navitems_link',)

    # Ajouter la liste des modules en lecture seule dans le fieldset Permissions
    fieldsets = list(BaseUserAdmin.fieldsets)  # copie

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        new_fieldsets = []
        for name, opts in fieldsets:
            if name == 'Permissions' or name == 'Droits':
                fields = list(opts.get('fields', []))
                if obj is not None:
                    fields.append('navitems_link')
                new_fieldsets.append((name, {**opts, 'fields': fields}))
            else:
                new_fieldsets.append((name, opts))
        return new_fieldsets

    def navitems_link(self, obj):
        if not obj or not obj.pk:
            return "Enregistrer l'utilisateur pour gérer ses menus."
        url = reverse('admin:modperm_user_navitems', args=[obj.pk])
        return format_html('<a class="button" href="{}">🗂️ Gérer les menus par module</a>', url)
    navitems_link.short_description = "Menus par module"

    def get_urls(self):
        urls = super().get_urls()
        extra = [
            path(
                'modules-par-groupe/',
                self.admin_site.admin_view(self.modules_par_groupe_view),
                name='modules_par_groupe',
            ),
            path(
                '<int:user_id>/navitems/',
                self.admin_site.admin_view(self.user_navitems_view),
                name='modperm_user_navitems',
            ),
        ]
        return extra + urls

    def user_navitems_view(self, request, user_id):
        """
        Checklist par module pour un utilisateur précis : coché = menu visible.
        L'état par défaut de chaque case reflète ce que ses groupes autorisent déjà ;
        ne cocher/décocher que crée une exception (UserNavItemOverride) si elle diffère
        de cet état de groupe — sinon l'exception existante est supprimée.
        """
        target_user = get_object_or_404(User, pk=user_id)
        accessible_module_ids = set(get_user_modules(target_user).values_list('id', flat=True))
        grouped = {
            module: items
            for module, items in get_navitems_grouped().items()
            if module and module.id in accessible_module_ids
        }
        group_hidden_ids = set(
            GroupNavItemRestriction.objects
            .filter(group__in=target_user.groups.all())
            .values_list('nav_item_id', flat=True)
        )
        overrides = {
            o.nav_item_id: o.override_type
            for o in UserNavItemOverride.objects.filter(user=target_user)
        }

        if request.method == 'POST':
            for items in grouped.values():
                for item in items:
                    checked = request.POST.get(f'nav_{item.id}') == 'on'
                    default_visible = item.id not in group_hidden_ids
                    if checked == default_visible:
                        UserNavItemOverride.objects.filter(user=target_user, nav_item=item).delete()
                    else:
                        UserNavItemOverride.objects.update_or_create(
                            user=target_user, nav_item=item,
                            defaults={'override_type': 'show' if checked else 'hide'},
                        )
            messages.success(request, f"Menus mis à jour pour « {target_user.username} ».")
            return redirect(reverse('admin:modperm_user_navitems', args=[target_user.pk]))

        sections = []
        for module, items in grouped.items():
            entries = []
            for item in items:
                default_visible = item.id not in group_hidden_ids
                override = overrides.get(item.id)
                checked = {'show': True, 'hide': False}.get(override, default_visible)
                entries.append({'item': item, 'checked': checked, 'is_override': override is not None})
            sections.append({'module': module, 'items': entries})

        context = dict(
            self.admin_site.each_context(request),
            title=f"Menus visibles — {target_user.username}",
            target_user=target_user,
            sections=sections,
            opts=self.model._meta,
        )
        return render(request, 'modules_permissions/user_navitems.html', context)

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
