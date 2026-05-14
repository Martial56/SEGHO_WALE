from django.db import migrations


def update_gynecologie_url(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='gynecologie').update(url_name='patients:gynecologie_rdv')


def revert_gynecologie_url(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='gynecologie').update(
        url_name='admin:consultations_consultation_changelist'
    )


class Migration(migrations.Migration):
    dependencies = [
        ('modules_permissions', '0003_add_missing_modules'),
    ]
    operations = [
        migrations.RunPython(update_gynecologie_url, revert_gynecologie_url),
    ]
