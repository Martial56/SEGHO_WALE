from django.db import migrations

# Tables historiquement créées par l'ancienne app `ressources_humaines`
# (avant sa fusion dans `employer`). Sur les bases anciennes, elles existent
# déjà sous ce nom. Sur une base neuve, 0001-0007 viennent de les créer sous
# le nom par défaut `employer_*` (aucun Meta.db_table avant cette migration) —
# il faut donc les renommer pour rejoindre le nom que l'état Django adopte
# juste après (AlterModelTable ci-dessous), sinon les ADD COLUMN suivants
# échouent avec "no such table" sur une base neuve.
_TABLES_HERITEES = (
    ('employer_employe', 'ressources_humaines_employe'),
    ('employer_conge', 'ressources_humaines_conge'),
    ('employer_presence', 'ressources_humaines_presence'),
)


def _renommer_tables_heritees(apps, schema_editor):
    connection = schema_editor.connection
    existantes = set(connection.introspection.table_names())
    for old, new in _TABLES_HERITEES:
        if old in existantes and new not in existantes:
            schema_editor.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')


def _renommer_tables_heritees_reverse(apps, schema_editor):
    connection = schema_editor.connection
    existantes = set(connection.introspection.table_names())
    for old, new in _TABLES_HERITEES:
        if new in existantes and old not in existantes:
            schema_editor.execute(f'ALTER TABLE "{new}" RENAME TO "{old}"')


# Colonnes ajoutées à la main sur les tables héritées, historiquement absentes
# de ressources_humaines_employe/conge. Sur une base neuve, ces colonnes
# existent déjà (créées directement par 0001-0007 avec l'état actuel du
# modèle) — un ALTER TABLE ADD COLUMN aveugle échoue alors avec
# "duplicate column name".
_COLONNES_HERITEES = (
    ('ressources_humaines_employe', 'sexe',                  '"sexe" varchar(1) NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'date_naissance',         '"date_naissance" date NULL'),
    ('ressources_humaines_employe', 'lieu_naissance',         '"lieu_naissance" varchar(150) NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'nationalite',            '"nationalite" varchar(50) NOT NULL DEFAULT \'Ivoirienne\''),
    ('ressources_humaines_employe', 'situation_matrimoniale', '"situation_matrimoniale" varchar(20) NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'nombre_enfants',         '"nombre_enfants" integer NOT NULL DEFAULT 0'),
    ('ressources_humaines_employe', 'photo',                  '"photo" varchar(100) NULL'),
    ('ressources_humaines_employe', 'telephone2',             '"telephone2" varchar(20) NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'adresse',                '"adresse" text NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'notes',                  '"notes" text NOT NULL DEFAULT \'\''),
    ('ressources_humaines_employe', 'cree_le',                '"cree_le" datetime NULL'),
    ('ressources_humaines_employe', 'modifie_le',             '"modifie_le" datetime NULL'),
    ('ressources_humaines_employe', 'service_id',             '"service_id" integer NULL REFERENCES "medecins_service" ("id")'),
    ('ressources_humaines_employe', 'fonction_id',            '"fonction_id" integer NULL REFERENCES "ressources_humaines_fonction" ("id")'),
    ('ressources_humaines_employe', 'grade_id',               '"grade_id" integer NULL REFERENCES "ressources_humaines_grade" ("id")'),
    ('ressources_humaines_employe', 'type_contrat_id',        '"type_contrat_id" integer NULL REFERENCES "ressources_humaines_typecontrat" ("id")'),
    ('ressources_humaines_conge',   'date_approbation',       '"date_approbation" datetime NULL'),
    ('ressources_humaines_conge',   'commentaire_rh',         '"commentaire_rh" text NOT NULL DEFAULT \'\''),
)


def _ajouter_colonnes_heritees(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        colonnes_par_table = {}
        for table, _col, _ddl in _COLONNES_HERITEES:
            if table not in colonnes_par_table:
                colonnes_par_table[table] = {
                    c.name for c in connection.introspection.get_table_description(cursor, table)
                }
    for table, col, ddl in _COLONNES_HERITEES:
        if col not in colonnes_par_table[table]:
            schema_editor.execute(f'ALTER TABLE "{table}" ADD COLUMN {ddl}')


def _ajouter_colonnes_heritees_reverse(apps, schema_editor):
    # Pas de retour arrière : ces colonnes font partie de l'état normal du
    # modèle (state_operations ne les a jamais ajoutées séparément), les
    # supprimer casserait le modèle même sur une base neuve.
    pass


class Migration(migrations.Migration):
    """
    Synchronise l'état Django avec les vraies tables SQLite (préfixe ressources_humaines_*).
    Les tables existantes (employe, conge, presence) sont conservées — seules les nouvelles
    tables sont créées et les colonnes manquantes sont ajoutées.
    """

    dependencies = [
        ('employer', '0007_conge_champs_approbation'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
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
            ],
            database_operations=[
                # ── Tables héritées (employe/conge/presence) : renommées seulement
                # si elles viennent d'être créées sous employer_* par 0001-0007 ──
                migrations.RunPython(_renommer_tables_heritees, _renommer_tables_heritees_reverse),
                # ── Nouvelles tables (absentes de l'ancien app ressources_humaines) ──
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_fonction" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "nom" varchar(100) NOT NULL,
                        "code" varchar(20) NOT NULL DEFAULT '',
                        "description" text NOT NULL DEFAULT ''
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_grade" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "nom" varchar(100) NOT NULL,
                        "code" varchar(20) NOT NULL DEFAULT '',
                        "description" text NOT NULL DEFAULT ''
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_typecontrat" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "nom" varchar(100) NOT NULL,
                        "description" text NOT NULL DEFAULT ''
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_infosupplementaire" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "cle" varchar(100) NOT NULL,
                        "valeur" text NOT NULL,
                        "ordre" integer NOT NULL DEFAULT 0,
                        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id")
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_documentemploye" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "type_document" varchar(20) NOT NULL DEFAULT 'autre',
                        "titre" varchar(200) NOT NULL,
                        "fichier" varchar(100) NOT NULL,
                        "date_ajout" datetime NOT NULL,
                        "date_expiration" date NULL,
                        "notes" text NOT NULL DEFAULT '',
                        "ajoute_par_id" integer NULL REFERENCES "auth_user" ("id"),
                        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id")
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_alertedocument" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "echeance" varchar(10) NOT NULL,
                        "date_expiration" date NOT NULL,
                        "lue" bool NOT NULL DEFAULT 0,
                        "cree_le" datetime NOT NULL,
                        "document_id" bigint NOT NULL REFERENCES "ressources_humaines_documentemploye" ("id"),
                        UNIQUE ("document_id", "echeance")
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_alertecontrat" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "echeance" varchar(10) NOT NULL,
                        "date_fin_contrat" date NOT NULL,
                        "lue" bool NOT NULL DEFAULT 0,
                        "cree_le" datetime NOT NULL,
                        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id"),
                        UNIQUE ("employe_id", "echeance")
                    )''',
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_historiqueemploye" (
                        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                        "type_changement" varchar(20) NOT NULL,
                        "ancienne_valeur" varchar(300) NOT NULL DEFAULT '',
                        "nouvelle_valeur" varchar(300) NOT NULL DEFAULT '',
                        "note" varchar(300) NOT NULL DEFAULT '',
                        "date" datetime NOT NULL,
                        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id"),
                        "fait_par_id" integer NULL REFERENCES "auth_user" ("id")
                    )''',
                    migrations.RunSQL.noop,
                ),
                # ── Colonnes manquantes sur ressources_humaines_employe / _conge ──
                # (ajoutées seulement si absentes — voir _ajouter_colonnes_heritees)
                migrations.RunPython(_ajouter_colonnes_heritees, _ajouter_colonnes_heritees_reverse),
            ],
        ),
    ]
