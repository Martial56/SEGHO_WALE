from django.db import migrations


def rename_statuts(apps, schema_editor):
    Soin = apps.get_model('soins', 'Soin')
    ProcedureSoin = apps.get_model('soins', 'ProcedureSoin')

    Soin.objects.filter(statut='courant').update(statut='en_cours')
    Soin.objects.filter(statut='complete').update(statut='termine')

    ProcedureSoin.objects.filter(statut='courant').update(statut='en_cours')


def reverse_rename_statuts(apps, schema_editor):
    Soin = apps.get_model('soins', 'Soin')
    ProcedureSoin = apps.get_model('soins', 'ProcedureSoin')

    Soin.objects.filter(statut='en_cours').update(statut='courant')
    Soin.objects.filter(statut='termine').update(statut='complete')

    ProcedureSoin.objects.filter(statut='en_cours').update(statut='courant')


class Migration(migrations.Migration):

    dependencies = [
        ('soins', '0008_update_statut_choices'),
    ]

    operations = [
        migrations.RunPython(rename_statuts, reverse_rename_statuts),
    ]
