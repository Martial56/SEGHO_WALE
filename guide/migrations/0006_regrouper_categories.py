# Regroupe les catégories du guide par grandes sections dans le sommaire —
# notamment les modules liés aux ressources humaines (Employés, Présence,
# Congés), auparavant dispersés dans une grille plate.

from django.db import migrations

GROUPES = [
    ("Prise en main", 0, ['demarrage']),
    ("Patients & Soins", 1, ['patients', 'medecins', 'services', 'soins', 'hospitalisation', 'gynecologie']),
    ("Pharmacie & Laboratoire", 2, ['pharmacie', 'ordonnance', 'laboratoire']),
    ("Facturation & Caisse", 3, ['facturation', 'caisse']),
    ("Ressources humaines", 4, ['employer', 'presence', 'conges']),
    ("Logistique", 5, ['achats', 'stock']),
    ("Organisation", 6, ['planning', 'rapports']),
    ("Compte & Administration", 7, ['compte', 'admin']),
]


def regrouper(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    for nom_groupe, groupe_ordre, codes in GROUPES:
        GuideCategorie.objects.filter(code__in=codes).update(
            groupe=nom_groupe, groupe_ordre=groupe_ordre,
        )


def degrouper(apps, schema_editor):
    GuideCategorie = apps.get_model('guide', 'GuideCategorie')
    GuideCategorie.objects.update(groupe='', groupe_ordre=0)


class Migration(migrations.Migration):

    dependencies = [
        ('guide', '0005_alter_guidecategorie_options_guidecategorie_groupe_and_more'),
    ]

    operations = [
        migrations.RunPython(regrouper, degrouper),
    ]
