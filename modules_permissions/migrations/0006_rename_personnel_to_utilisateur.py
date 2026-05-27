from django.db import migrations


def apply(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='personnel').update(
        code='utilisateur',
        name='Utilisateur',
        icon='👤',
        url_name='utilisateur:list',
        order=17,
    )


def revert(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')
    Module.objects.filter(code='utilisateur').update(
        code='personnel',
        name='Personnel',
        icon='👤',
        url_name='personnel:list',
        order=17,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0005_replace_rh_with_personnel'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
