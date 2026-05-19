from django.db import migrations


TYPES_CONTRAT = [
    'Vacataire',
    'Contractuel',
    'CDD',
    'CDI',
    'Prestataire',
    'Autre',
]


def add_types_contrat(apps, schema_editor):
    TypeContrat = apps.get_model('employer', 'TypeContrat')
    for nom in TYPES_CONTRAT:
        TypeContrat.objects.get_or_create(nom=nom)


def remove_types_contrat(apps, schema_editor):
    TypeContrat = apps.get_model('employer', 'TypeContrat')
    TypeContrat.objects.filter(nom__in=TYPES_CONTRAT).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0003_alertecontrat'),
    ]

    operations = [
        migrations.RunPython(add_types_contrat, remove_types_contrat),
    ]
