from django.db import migrations


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
                # ── Colonnes manquantes sur ressources_humaines_employe ──────────
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"sexe\" varchar(1) NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"date_naissance\" date NULL",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"lieu_naissance\" varchar(150) NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"nationalite\" varchar(50) NOT NULL DEFAULT 'Ivoirienne'",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"situation_matrimoniale\" varchar(20) NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"nombre_enfants\" integer NOT NULL DEFAULT 0",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"photo\" varchar(100) NULL",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"telephone2\" varchar(20) NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"adresse\" text NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"notes\" text NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"cree_le\" datetime NULL",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"modifie_le\" datetime NULL",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"service_id\" integer NULL REFERENCES \"medecins_service\" (\"id\")",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"fonction_id\" integer NULL REFERENCES \"ressources_humaines_fonction\" (\"id\")",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"grade_id\" integer NULL REFERENCES \"ressources_humaines_grade\" (\"id\")",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_employe\" ADD COLUMN \"type_contrat_id\" integer NULL REFERENCES \"ressources_humaines_typecontrat\" (\"id\")",
                    migrations.RunSQL.noop,
                ),
                # ── Colonnes manquantes sur ressources_humaines_conge (ajout 0007) ─
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_conge\" ADD COLUMN \"date_approbation\" datetime NULL",
                    migrations.RunSQL.noop,
                ),
                migrations.RunSQL(
                    "ALTER TABLE \"ressources_humaines_conge\" ADD COLUMN \"commentaire_rh\" text NOT NULL DEFAULT ''",
                    migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
