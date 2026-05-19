from django.db import migrations


REBUILD_ANALYSE = [
    # Drop existing indexes
    'DROP INDEX IF EXISTS "laboratoire_analyselaboratoire_patient_id_bc490b18"',
    'DROP INDEX IF EXISTS "laboratoire_analyselaboratoire_technicien_id_d44d8a17"',
    'DROP INDEX IF EXISTS "laboratoire_analyselaboratoire_validateur_id_eb20fac3"',
    'DROP INDEX IF EXISTS "laboratoire_analyselaboratoire_type_examen_id_0821dd6b"',
    # Recreate table without examen_demande_id
    '''CREATE TABLE "laboratoire_analyselaboratoire_new" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "numero" varchar(20) NOT NULL UNIQUE,
        "date_prelevement" datetime NOT NULL,
        "date_resultat" datetime NULL,
        "statut" varchar(20) NOT NULL,
        "commentaire" text NOT NULL,
        "urgent" bool NOT NULL,
        "patient_id" bigint NOT NULL REFERENCES "patients_patient" ("id") DEFERRABLE INITIALLY DEFERRED,
        "technicien_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
        "validateur_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED,
        "type_examen_id" bigint NULL REFERENCES "laboratoire_typeexamen" ("id") DEFERRABLE INITIALLY DEFERRED
    )''',
    '''INSERT INTO "laboratoire_analyselaboratoire_new"
        ("id","numero","date_prelevement","date_resultat","statut","commentaire","urgent",
         "patient_id","technicien_id","validateur_id","type_examen_id")
       SELECT "id","numero","date_prelevement","date_resultat","statut","commentaire","urgent",
              "patient_id","technicien_id","validateur_id","type_examen_id"
       FROM "laboratoire_analyselaboratoire"''',
    'DROP TABLE "laboratoire_analyselaboratoire"',
    'ALTER TABLE "laboratoire_analyselaboratoire_new" RENAME TO "laboratoire_analyselaboratoire"',
    # Recreate indexes
    'CREATE INDEX "laboratoire_analyselaboratoire_patient_id_bc490b18" ON "laboratoire_analyselaboratoire" ("patient_id")',
    'CREATE INDEX "laboratoire_analyselaboratoire_technicien_id_d44d8a17" ON "laboratoire_analyselaboratoire" ("technicien_id")',
    'CREATE INDEX "laboratoire_analyselaboratoire_validateur_id_eb20fac3" ON "laboratoire_analyselaboratoire" ("validateur_id")',
    'CREATE INDEX "laboratoire_analyselaboratoire_type_examen_id_0821dd6b" ON "laboratoire_analyselaboratoire" ("type_examen_id")',
]

REBUILD_IMAGERIE = [
    'DROP INDEX IF EXISTS "laboratoire_examenimagerie_patient_id_7647989c"',
    'DROP INDEX IF EXISTS "laboratoire_examenimagerie_radiologue_id_92a4ea4e"',
    '''CREATE TABLE "laboratoire_examenimagerie_new" (
        "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
        "numero" varchar(20) NOT NULL UNIQUE,
        "type_imagerie" varchar(20) NOT NULL,
        "zone_examinee" varchar(200) NOT NULL,
        "date_examen" datetime NOT NULL,
        "statut" varchar(20) NOT NULL,
        "compte_rendu" text NOT NULL,
        "conclusion" text NOT NULL,
        "image" varchar(100) NULL,
        "urgent" bool NOT NULL,
        "patient_id" bigint NOT NULL REFERENCES "patients_patient" ("id") DEFERRABLE INITIALLY DEFERRED,
        "radiologue_id" integer NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
    )''',
    '''INSERT INTO "laboratoire_examenimagerie_new"
        ("id","numero","type_imagerie","zone_examinee","date_examen","statut",
         "compte_rendu","conclusion","image","urgent","patient_id","radiologue_id")
       SELECT "id","numero","type_imagerie","zone_examinee","date_examen","statut",
              "compte_rendu","conclusion","image","urgent","patient_id","radiologue_id"
       FROM "laboratoire_examenimagerie"''',
    'DROP TABLE "laboratoire_examenimagerie"',
    'ALTER TABLE "laboratoire_examenimagerie_new" RENAME TO "laboratoire_examenimagerie"',
    'CREATE INDEX "laboratoire_examenimagerie_patient_id_7647989c" ON "laboratoire_examenimagerie" ("patient_id")',
    'CREATE INDEX "laboratoire_examenimagerie_radiologue_id_92a4ea4e" ON "laboratoire_examenimagerie" ("radiologue_id")',
]


class Migration(migrations.Migration):

    dependencies = [
        ('laboratoire', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(sql=REBUILD_ANALYSE, reverse_sql=""),
        migrations.RunSQL(sql=REBUILD_IMAGERIE, reverse_sql=""),
    ]
