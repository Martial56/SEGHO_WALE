from django.db import migrations


class Migration(migrations.Migration):
    """
    Synchronise l'état Django avec les vraies tables SQLite (préfixe ressources_humaines_*).
    Les tables existent déjà — aucune opération SQL n'est exécutée.
    """

    dependencies = [
        ('employer', '0007_conge_champs_approbation'),
    ]

    operations = [
        migrations.AlterModelTable('Fonction',           'ressources_humaines_fonction'),
        migrations.AlterModelTable('Grade',              'ressources_humaines_grade'),
        migrations.AlterModelTable('TypeContrat',        'ressources_humaines_typecontrat'),
        migrations.AlterModelTable('Employe',            'ressources_humaines_employe'),
        migrations.AlterModelTable('DocumentEmploye',    'ressources_humaines_documentemploye'),
        migrations.AlterModelTable('AlerteDocument',     'ressources_humaines_alertedocument'),
        migrations.AlterModelTable('InfoSupplementaire', 'ressources_humaines_infosupplementaire'),
        migrations.AlterModelTable('HistoriqueEmploye',  'ressources_humaines_historiqueemploye'),
        migrations.AlterModelTable('AlerteContrat',      'ressources_humaines_alertecontrat'),
        migrations.AlterModelTable('Conge',              'ressources_humaines_conge'),
        migrations.AlterModelTable('Presence',           'ressources_humaines_presence'),
    ]
