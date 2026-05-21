from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('utilisateur', '0002_alter_employe_departements'),
    ]

    operations = [
        migrations.AlterModelTable('Specialite',              'utilisateur_specialite'),
        migrations.AlterModelTable('Diplome',                 'utilisateur_diplome'),
        migrations.AlterModelTable('Departement',             'utilisateur_departement'),
        migrations.AlterModelTable('Employe',                 'utilisateur_employe'),
        migrations.AlterModelTable('DiplomePersonnel',        'utilisateur_diplomepersonnel'),
        migrations.AlterModelTable('Etiquette',               'utilisateur_etiquette'),
        migrations.AlterModelTable('DocteurReferent',         'utilisateur_docteurreferent'),
        migrations.AlterModelTable('ContactAdresse',          'utilisateur_contactadresse'),
        migrations.AlterModelTable('EmployeDepartement',      'utilisateur_employe_departements'),
        migrations.AlterModelTable('DocteurReferentEtiquette','utilisateur_docteurreferent_etiquettes'),
    ]
