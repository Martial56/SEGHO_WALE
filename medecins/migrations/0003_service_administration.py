from django.db import migrations


def ajouter(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    Service.objects.get_or_create(code='ADMIN', defaults={'nom': 'Administration', 'actif': True})


def supprimer(apps, schema_editor):
    Service = apps.get_model('medecins', 'Service')
    Service.objects.filter(code='ADMIN').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0002_services_initiaux'),
    ]

    operations = [
        migrations.RunPython(ajouter, supprimer),
    ]
