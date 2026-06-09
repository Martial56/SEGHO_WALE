from django.shortcuts import render, get_object_or_404
from .models import Module, Permission, Group
from .filters import ModuleFilter

def module_list(request):
    modules = Module.objects.all()
    module_filter = ModuleFilter(request.GET, queryset=modules)
    return render(request, 'modules_permissions/module_list.html', {'filter': module_filter})

def module_detail(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    return render(request, 'modules_permissions/module_detail.html', {'module': module})

def group_permissions(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    permissions = Permission.objects.filter(groups=group)
    return render(request, 'modules_permissions/group_permissions.html', {'group': group, 'permissions': permissions})

def permission_matrix(request):
    groups = Group.objects.all()
    modules = Module.objects.all()
    permissions = Permission.objects.all()
    return render(request, 'modules_permissions/permission_matrix.html', {'groups': groups, 'modules': modules, 'permissions': permissions})