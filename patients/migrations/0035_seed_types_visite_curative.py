from django.db import migrations

# Les trois valeurs qui étaient écrites en dur dans le formulaire de rendez-vous.
# Le `code` est celui déjà enregistré dans le registre curatif (donnees →
# cur_type_visite) et lu par les rapports : il ne doit pas changer.
SEED = [
    ('consultant', 'Consultant'),
    ('controle',   'Contrôle'),
    ('soins',      'Soins'),
]


def seed(apps, schema_editor):
    TypeVisiteCurative = apps.get_model('patients', 'TypeVisiteCurative')
    for code, nom in SEED:
        TypeVisiteCurative.objects.get_or_create(code=code, defaults={'nom': nom, 'actif': True})


def unseed(apps, schema_editor):
    TypeVisiteCurative = apps.get_model('patients', 'TypeVisiteCurative')
    TypeVisiteCurative.objects.filter(code__in=[c for c, _ in SEED]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0034_typevisitecurative_alter_rendezvous_cur_type_visite'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
