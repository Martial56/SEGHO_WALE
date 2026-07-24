from django.db import migrations, models


def nettoyer_ordre_vide(apps, schema_editor):
    Medecin = apps.get_model('medecins', 'Medecin')
    Medecin.objects.filter(ordre_medecin='').update(ordre_medecin=None)


def revenir_arriere(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0014_delete_modulespecialise'),
    ]

    operations = [
        migrations.AlterField(
            model_name='medecin',
            name='ordre_medecin',
            field=models.CharField(max_length=50, blank=True, null=True),
        ),
        migrations.RunPython(nettoyer_ordre_vide, revenir_arriere),
        migrations.AlterField(
            model_name='medecin',
            name='ordre_medecin',
            field=models.CharField(max_length=50, blank=True, null=True, unique=True),
        ),
    ]
