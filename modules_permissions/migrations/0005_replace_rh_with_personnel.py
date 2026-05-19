from django.db import migrations


def apply(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')

    # Convertir ressources_humaines → personnel
    Module.objects.filter(code='ressources_humaines').update(
        code='personnel',
        name='Personnel',
        icon='👤',
        url_name='personnel:list',
        order=17,
    )

    # Supprimer les modules qui référençaient l'admin RH supprimé
    Module.objects.filter(code__in=['evaluation', 'presence', 'conges']).delete()


def revert(apps, schema_editor):
    Module = apps.get_model('modules_permissions', 'Module')

    Module.objects.filter(code='personnel').update(
        code='ressources_humaines',
        name='Ressources Humaines',
        icon='👤',
        url_name='ressources_humaines_list',
        order=17,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('modules_permissions', '0004_rename_consultations_to_soins'),
    ]

    operations = [
        migrations.RunPython(apply, revert),
    ]
