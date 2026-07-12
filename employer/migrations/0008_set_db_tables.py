from django.db import migrations

# Renommages nécessaires uniquement sur une base fraîchement créée (tests, nouvelle
# installation) : les tables y sont encore nommées employer_* (nom par défaut Django).
# Sur la base historique, elles s'appellent déjà ressources_humaines_* (l'app portait
# ce nom avant d'être renommée en "employer") : le renommage y est alors un no-op.
RENAMES = [
    ('employer_fonction',           'ressources_humaines_fonction'),
    ('employer_grade',              'ressources_humaines_grade'),
    ('employer_typecontrat',        'ressources_humaines_typecontrat'),
    ('employer_employe',            'ressources_humaines_employe'),
    ('employer_documentemploye',    'ressources_humaines_documentemploye'),
    ('employer_alertedocument',     'ressources_humaines_alertedocument'),
    ('employer_infosupplementaire', 'ressources_humaines_infosupplementaire'),
    ('employer_historiqueemploye',  'ressources_humaines_historiqueemploye'),
    ('employer_alertecontrat',      'ressources_humaines_alertecontrat'),
    ('employer_conge',              'ressources_humaines_conge'),
    ('employer_presence',           'ressources_humaines_presence'),
]

NEW_TABLES_SQL = [
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_fonction" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "nom" varchar(100) NOT NULL,
        "code" varchar(20) NOT NULL DEFAULT '',
        "description" text NOT NULL DEFAULT ''
    )''',
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_grade" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "nom" varchar(100) NOT NULL,
        "code" varchar(20) NOT NULL DEFAULT '',
        "description" text NOT NULL DEFAULT ''
    )''',
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_typecontrat" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "nom" varchar(100) NOT NULL,
        "description" text NOT NULL DEFAULT ''
    )''',
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_infosupplementaire" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "cle" varchar(100) NOT NULL,
        "valeur" text NOT NULL,
        "ordre" integer NOT NULL DEFAULT 0,
        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id")
    )''',
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
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_alertedocument" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "echeance" varchar(10) NOT NULL,
        "date_expiration" date NOT NULL,
        "lue" bool NOT NULL DEFAULT 0,
        "cree_le" datetime NOT NULL,
        "document_id" bigint NOT NULL REFERENCES "ressources_humaines_documentemploye" ("id"),
        UNIQUE ("document_id", "echeance")
    )''',
    '''CREATE TABLE IF NOT EXISTS "ressources_humaines_alertecontrat" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "echeance" varchar(10) NOT NULL,
        "date_fin_contrat" date NOT NULL,
        "lue" bool NOT NULL DEFAULT 0,
        "cree_le" datetime NOT NULL,
        "employe_id" bigint NOT NULL REFERENCES "ressources_humaines_employe" ("id"),
        UNIQUE ("employe_id", "echeance")
    )''',
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
]

ADD_COLUMNS = [
    ('ressources_humaines_employe', 'sexe',                   "varchar(1) NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'date_naissance',         "date NULL"),
    ('ressources_humaines_employe', 'lieu_naissance',         "varchar(150) NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'nationalite',            "varchar(50) NOT NULL DEFAULT 'Ivoirienne'"),
    ('ressources_humaines_employe', 'situation_matrimoniale', "varchar(20) NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'nombre_enfants',         "integer NOT NULL DEFAULT 0"),
    ('ressources_humaines_employe', 'photo',                  "varchar(100) NULL"),
    ('ressources_humaines_employe', 'telephone2',             "varchar(20) NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'adresse',                "text NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'notes',                  "text NOT NULL DEFAULT ''"),
    ('ressources_humaines_employe', 'cree_le',                "datetime NULL"),
    ('ressources_humaines_employe', 'modifie_le',              "datetime NULL"),
    ('ressources_humaines_employe', 'service_id',              "integer NULL REFERENCES \"medecins_service\" (\"id\")"),
    ('ressources_humaines_employe', 'fonction_id',             "integer NULL REFERENCES \"ressources_humaines_fonction\" (\"id\")"),
    ('ressources_humaines_employe', 'grade_id',                "integer NULL REFERENCES \"ressources_humaines_grade\" (\"id\")"),
    ('ressources_humaines_employe', 'type_contrat_id',         "integer NULL REFERENCES \"ressources_humaines_typecontrat\" (\"id\")"),
    ('ressources_humaines_conge',   'date_approbation',        "datetime NULL"),
    ('ressources_humaines_conge',   'commentaire_rh',          "text NOT NULL DEFAULT ''"),
]


def _existing_tables(schema_editor):
    with schema_editor.connection.cursor() as cursor:
        return set(schema_editor.connection.introspection.table_names(cursor))


def _existing_columns(schema_editor, table):
    with schema_editor.connection.cursor() as cursor:
        return {c.name for c in schema_editor.connection.introspection.get_table_description(cursor, table)}


def migrate_forward(apps, schema_editor):
    existing = _existing_tables(schema_editor)
    for old_name, new_name in RENAMES:
        if new_name in existing:
            continue
        if old_name in existing:
            schema_editor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')
            existing.discard(old_name)
            existing.add(new_name)

    for sql in NEW_TABLES_SQL:
        schema_editor.execute(sql)

    for table, column, coltype in ADD_COLUMNS:
        if column not in _existing_columns(schema_editor, table):
            schema_editor.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {coltype}')


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
                migrations.RunPython(migrate_forward, migrations.RunPython.noop),
            ],
        ),
    ]
