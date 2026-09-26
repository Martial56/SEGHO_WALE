import django.db.models.deletion
from django.db import migrations, models


class SupprimerChampSiPresent(migrations.RemoveField):
    """RemoveField qui ne supprime la colonne que si elle existe réellement.

    0003_replace_type_rdv_with_service_fk n'ajoute `service` qu'à l'état Django
    (database_operations vide), en supposant la colonne créée par 0007 — qui,
    patchée elle aussi, ne crée rien. Sur une base neuve la colonne service_id
    n'existe donc pas et le DROP COLUMN échouait sous PostgreSQL (sur SQLite, une
    reconstruction de table antérieure l'a matérialisée : elle y est supprimée).
    L'état Django, lui, évolue exactement comme avec un RemoveField ordinaire.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        modele = from_state.apps.get_model(app_label, self.model_name)
        champ = modele._meta.get_field(self.name)
        connection = schema_editor.connection
        with connection.cursor() as cursor:
            colonnes = {c.name for c in connection.introspection.get_table_description(cursor, modele._meta.db_table)}
        if champ.column in colonnes:
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # Sans effet : avant cette migration, la colonne n'existe pas sur une base neuve.
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('medecins', '0010_service_medecine_generale_gynecologie'),
        ('patients', '0017_merge_0016'),
    ]

    operations = [
        SupprimerChampSiPresent(
            model_name='rendezvous',
            name='service',
        ),
        migrations.RenameField(
            model_name='rendezvous',
            old_name='departement',
            new_name='departement_code_old',
        ),
        migrations.AlterField(
            model_name='rendezvous',
            name='departement_code_old',
            field=models.CharField(max_length=30, blank=True, default=''),
        ),
        migrations.AddField(
            model_name='rendezvous',
            name='departement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rendez_vous', to='medecins.service', verbose_name='Service'),
        ),
    ]
