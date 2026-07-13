from django.db import migrations, models
import django.db.models.deletion


def supprimer_medecins_orphelins(apps, schema_editor):
    cursor = schema_editor.connection.cursor()
    cursor.execute("SELECT id FROM medecins_medecin WHERE employe_id IS NULL")
    orphan_ids = [row[0] for row in cursor.fetchall()]
    if not orphan_ids:
        return
    ids_str = ",".join(str(i) for i in orphan_ids)
    fk_refs = [
        ("consultations_consultation", "medecin_id"),
        ("consultations_ordonnance", "medecin_id"),
        ("hospitalisation_fichevisite", "medecin_id"),
        ("hospitalisation_hospitalisation", "infirmiere_primaire_id"),
        ("hospitalisation_hospitalisation", "medecin_referent_id"),
        ("hospitalisation_hospitalisation", "medecin_traitant_id"),
        ("hospitalisation_registredeces", "medecin_id"),
        ("hospitalisation_visitedocteur", "docteur_id"),
        ("hospitalisation_visiteinfirmiere", "infirmiere_id"),
        ("medecins_service", "chef_service_id"),
        ("patients_naissance", "medecin_id"),
        ("patients_rendezvous", "docteur_jr_id"),
        ("patients_rendezvous", "medecin_id"),
    ]
    for table, col in fk_refs:
        cursor.execute(f"UPDATE {table} SET {col} = NULL WHERE {col} IN ({ids_str})")
    cursor.execute(f"DELETE FROM medecins_medecin WHERE id IN ({ids_str})")


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
        migrations.RunPython(supprimer_medecins_orphelins, migrations.RunPython.noop),
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
