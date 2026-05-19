from django.db import migrations


def rename_module(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='consultations').update(
        code='soins',
        name='Soins',
        url_name='soins_list',
    )


def reverse_rename(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='soins').update(
        code='consultations',
        name='Consultations',
        url_name='consultations_list',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0003_add_missing_modules'),
    ]

    operations = [
        migrations.RunPython(rename_module, reverse_rename),
    ]
