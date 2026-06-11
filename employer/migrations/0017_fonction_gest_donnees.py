from django.db import migrations


def ajouter(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    Fonction.objects.get_or_create(code='GEST-DATA', defaults={'nom': 'Gestionnaire de Données'})


def supprimer(apps, schema_editor):
    Fonction = apps.get_model('employer', 'Fonction')
    Fonction.objects.filter(code='GEST-DATA').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0016_fonctions_supplementaires'),
    ]

    operations = [
        migrations.RunPython(ajouter, supprimer),
    ]
