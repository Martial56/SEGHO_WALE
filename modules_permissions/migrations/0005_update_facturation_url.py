from django.db import migrations


def update_facturation_url(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='facturation').update(url_name='facturation:list')


def revert_facturation_url(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='facturation').update(url_name='facturation_list')


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0004_update_gynecologie_module'),
    ]

    operations = [
        migrations.RunPython(update_facturation_url, revert_facturation_url),
    ]
