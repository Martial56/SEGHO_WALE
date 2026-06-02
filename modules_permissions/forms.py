from django import forms
from .models import Module, Permission

class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ['name', 'description', 'permissions']
        widgets = {
            'permissions': forms.CheckboxSelectMultiple(),
        }

class PermissionForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = ['name', 'description']