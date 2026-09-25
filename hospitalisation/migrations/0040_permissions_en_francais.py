from django.db import migrations


# Django écrit le libellé d'une permission en base au moment des migrations, et
# il l'écrit en anglais : « Can add Chambre ». C'est pourtant ce libellé que lit
# la personne qui compose un groupe dans /admin/. Les modèles déclarent
# désormais des libellés français (voir l'en-tête de hospitalisation/models.py),
# mais cela ne vaut que pour les permissions encore à créer — celles d'une base
# déjà en service gardent leur nom d'origine. On les renomme donc ici.
#
# Les libellés ne sont pas recopiés : ils sont lus sur l'état historique des
# modèles figé par la migration 0039, donc une correction de libellé dans
# models.py ne peut pas désynchroniser ce fichier.

ACTIONS = ('view', 'add', 'change', 'delete')

MODELES = [
    'batiment', 'chambre', 'hospitalisation', 'fichevisite', 'visiteinfirmiere',
    'visitedocteur', 'serviceafacturer', 'resumedecharge', 'evaluationclinique',
    'checklistadmission', 'checklistverification', 'logactivitehospitalisation',
    'listeverificationservice', 'listecontroleadmission', 'registredeces',
]


def _renommer(apps, anglais):
    Permission = apps.get_model('auth', 'Permission')
    for nom_modele in MODELES:
        modele = apps.get_model('hospitalisation', nom_modele)
        libelles = dict(modele._meta.permissions)
        for action in ACTIONS:
            codename = '%s_%s' % (action, nom_modele)
            if anglais:
                nom = 'Can %s %s' % (action, modele._meta.verbose_name_raw)
            else:
                nom = libelles.get(codename)
                if nom is None:
                    continue
            # Rien à faire sur une base neuve : les permissions n'y sont créées
            # qu'après les migrations, et le modèle leur donne déjà le bon nom.
            Permission.objects.filter(
                content_type__app_label='hospitalisation',
                content_type__model=nom_modele,
                codename=codename,
            ).update(name=nom)


def en_francais(apps, schema_editor):
    _renommer(apps, anglais=False)


def en_anglais(apps, schema_editor):
    _renommer(apps, anglais=True)


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0001_initial'),
        ('hospitalisation', '0039_alter_batiment_options_alter_chambre_options_and_more'),
    ]

    operations = [
        migrations.RunPython(en_francais, en_anglais),
    ]
