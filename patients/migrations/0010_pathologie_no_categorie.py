from django.db import migrations, models


MANQUANTES = [
    'PFA avec vaccination anti-polio cas',
    'PFA avec vaccination anti-polio décès',
    'PFA sans vaccination anti-polio cas',
    'PFA sans vaccination anti-polio décès',
    'PFA sans statut vaccinal connu cas',
    'PFA sans statut vaccinal connu décès',
]


def add_missing(apps, schema_editor):
    Pathologie = apps.get_model('patients', 'Pathologie')
    for nom in MANQUANTES:
        Pathologie.objects.get_or_create(nom=nom)


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0009_pathologie'),
    ]

    operations = [
        migrations.RemoveField(model_name='Pathologie', name='categorie'),
        migrations.AlterModelOptions(
            name='pathologie',
            options={'verbose_name': 'Pathologie', 'ordering': ['nom']},
        ),
        migrations.RunPython(add_missing, migrations.RunPython.noop),
    ]
