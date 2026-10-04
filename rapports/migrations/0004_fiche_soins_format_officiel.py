"""Sème le format officiel de la fiche d'activité de soins.

Les quinze lignes vivaient dans deux constantes de `rapports/soins.py`. Elles
arrivent ici telles quelles — mêmes libellés, même ordre, mêmes prestations —
pour que la fiche sorte exactement les mêmes chiffres qu'avant le passage en
base. C'est la seule façon de vérifier que la bascule n'a rien changé.

Les prestations sont retrouvées **par leur nom exact**, comme le faisait le
calcul jusqu'ici. Dans une base où un article manque ou a été renommé, la ligne
arrive sans prestation cochée et continue d'afficher zéro, comme avant — à la
différence près que l'écran de configuration le montre, au lieu de le taire.
"""
from django.db import migrations


#: (libellé, source, [noms d'articles]) — l'ordre est celui de la feuille.
SOINS = [
    ('PERFUSION', 'mo_avec_soin', []),
    ('TRANSFUSION', 'articles', ['TRANSFUSION']),
    ('PANSEMENT', 'articles', ['PANSEMENT GRANDE PLAIE',
                               'PANSEMENT MOYENNE PLAIE',
                               'PANSEMENT PETITE PLAIE']),
    ("BAIN D'OREILLE", 'articles', ["LAVAGE D'OREILLE"]),
    ('INJECTION EXTERNE', 'articles', ['INJECTION EXTERNE']),
    ('INJECTION INTERNE', 'articles', ['INJECTION INTERNE']),
    ('Mise en Observation simple', 'mo_sans_soin', []),
    ('Suture', 'articles', ['FIL + SUTURE']),
]

AUTRES_SOINS = [
    ('Petite chirurgie, circoncision masculine', 'articles', ['CIRCONCISION']),
    ('Petite chirurgie, suture de plaie traumatique', 'articles',
     ['SUTURE PLAIE TRAUMATIQUE']),
    ("Petite chirurgie, incision d'abcès", 'articles', ["INCISION D'ABCÈS"]),
    ('Autres petites chirurgies', 'articles',
     ['COUPURE DE FREIN DE LANGUE', 'DRAINAGE', 'PONCTION']),
    ('Oxygénation', 'articles', ['OXYGENATION (DIX MINUTES)']),
    ('Nébulisateur', 'articles', ['NEBULISATION']),
    ('Ongle incarné', 'articles', ['ONGLE INCARNE']),
]

NOM_OFFICIEL = 'Format officiel'

#: Les deux blocs de la feuille, dans l'ordre d'impression.
BLOCS = (('Soins', SOINS), ('Autres soins à préciser', AUTRES_SOINS))


def _semer(apps, schema_editor):
    Configuration = apps.get_model('rapports', 'ConfigurationFicheSoins')
    Bloc = apps.get_model('rapports', 'BlocFicheSoins')
    Colonne = apps.get_model('rapports', 'ColonneFicheSoins')
    Ligne = apps.get_model('rapports', 'LigneFicheSoins')
    Article = apps.get_model('services', 'Articleservice')

    if Configuration.objects.filter(est_defaut=True).exists():
        return

    configuration = Configuration.objects.create(
        nom=NOM_OFFICIEL, est_defaut=True)

    for rang_bloc, (titre, lignes) in enumerate(BLOCS):
        bloc = Bloc.objects.create(
            configuration=configuration, titre=titre, ordre=rang_bloc)
        # Une seule colonne, « Nombre » : c'est la fiche d'aujourd'hui.
        Colonne.objects.create(bloc=bloc, titre='Nombre',
                               type_valeur='nombre', ordre=0)
        for rang, (libelle, source, noms) in enumerate(lignes):
            ligne = Ligne.objects.create(
                bloc=bloc, libelle=libelle, ordre=rang, source=source,
                origines='procedure')
            if noms:
                ligne.articles.set(Article.objects.filter(nom__in=noms))


def _oublier(apps, schema_editor):
    """Retire le format officiel. Les configurations personnelles restent :
    elles ont été copiées, elles ne pointent pas dessus."""
    Configuration = apps.get_model('rapports', 'ConfigurationFicheSoins')
    Configuration.objects.filter(est_defaut=True, nom=NOM_OFFICIEL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rapports', '0003_blocfichesoins_colonnefichesoins_and_more'),
        ('services', '0019_remove_articleservice_avertissement_grossesse_and_more'),
    ]

    operations = [
        migrations.RunPython(_semer, _oublier),
    ]
