from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Les données ont été migrées séparément (script ponctuel, hors migration —
    RunPython dans une migration provoquait un blocage 'database is locked' sur
    SQLite lors de l'exécution de Employe.save() ; exécuté avec succès en dehors
    du contexte de migration à la place). Cette migration n'applique plus que le
    changement de schéma, une fois les 4 médecins orphelins déjà rattachés."""

    dependencies = [
        ('employer', '0029_nationalite'),
        ('medecins', '0011_medecin_departement_alter_medecin_service'),
    ]

    operations = [
        migrations.RemoveField(model_name='medecin', name='matricule'),
        migrations.RemoveField(model_name='medecin', name='nom'),
        migrations.RemoveField(model_name='medecin', name='prenoms'),
        migrations.RemoveField(model_name='medecin', name='telephone'),
        migrations.RemoveField(model_name='medecin', name='email'),
        migrations.RemoveField(model_name='medecin', name='photo'),
        migrations.AlterField(
            model_name='medecin',
            name='employe',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='fiche_medecin', to='employer.employe',
                verbose_name='Employé lié',
            ),
        ),
        migrations.AlterModelOptions(
            name='medecin',
            options={'ordering': ['employe__nom'], 'verbose_name': 'Médecin'},
        ),
    ]
