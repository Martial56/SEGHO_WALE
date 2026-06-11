"""
Migration de synchronisation : rattrapage du schéma réel de la DB.

Les migrations 0001-0023 ont été fakées car les tables ressources_humaines_*
existaient déjà (ancienne app). Cette migration applique physiquement
toutes les colonnes et tables manquantes.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0023_employe_biometric_id_alter_conge_statut'),
        ('medecins', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(

            # ── Nouvelles tables ───────────────────────────────────────────────
            sql="""
-- Fonction
CREATE TABLE IF NOT EXISTS "ressources_humaines_fonction" (
    "id"          integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "nom"         varchar(100) NOT NULL,
    "code"        varchar(20)  NOT NULL DEFAULT '',
    "description" text         NOT NULL DEFAULT '',
    "categorie"   varchar(20)  NOT NULL DEFAULT 'support'
);

-- Grade
CREATE TABLE IF NOT EXISTS "ressources_humaines_grade" (
    "id"          integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "nom"         varchar(100) NOT NULL,
    "code"        varchar(20)  NOT NULL DEFAULT '',
    "description" text         NOT NULL DEFAULT ''
);

-- TypeContrat
CREATE TABLE IF NOT EXISTS "ressources_humaines_typecontrat" (
    "id"             integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "nom"            varchar(100) NOT NULL,
    "description"    text         NOT NULL DEFAULT '',
    "droit_au_conge" bool         NOT NULL DEFAULT 1
);

-- AlerteContrat
CREATE TABLE IF NOT EXISTS "ressources_humaines_alertecontrat" (
    "id"               integer     NOT NULL PRIMARY KEY AUTOINCREMENT,
    "echeance"         varchar(10) NOT NULL,
    "date_fin_contrat" date        NOT NULL,
    "lue"              bool        NOT NULL DEFAULT 0,
    "cree_le"          datetime    NOT NULL,
    "employe_id"       integer     NOT NULL REFERENCES "ressources_humaines_employe" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("employe_id", "echeance")
);

-- DocumentEmploye
CREATE TABLE IF NOT EXISTS "ressources_humaines_documentemploye" (
    "id"              integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "type_document"   varchar(20)  NOT NULL DEFAULT 'autre',
    "titre"           varchar(200) NOT NULL,
    "fichier"         varchar(100) NOT NULL,
    "date_expiration" date         NULL,
    "date_ajout"      datetime     NOT NULL,
    "notes"           text         NOT NULL DEFAULT '',
    "employe_id"      integer      NOT NULL REFERENCES "ressources_humaines_employe" ("id") DEFERRABLE INITIALLY DEFERRED,
    "ajoute_par_id"   integer      NULL     REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);

-- AlerteDocument
CREATE TABLE IF NOT EXISTS "ressources_humaines_alertedocument" (
    "id"              integer     NOT NULL PRIMARY KEY AUTOINCREMENT,
    "echeance"        varchar(10) NOT NULL,
    "date_expiration" date        NOT NULL,
    "lue"             bool        NOT NULL DEFAULT 0,
    "cree_le"         datetime    NOT NULL,
    "document_id"     integer     NOT NULL REFERENCES "ressources_humaines_documentemploye" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("document_id", "echeance")
);

-- InfoSupplementaire
CREATE TABLE IF NOT EXISTS "ressources_humaines_infosupplementaire" (
    "id"         integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "cle"        varchar(100) NOT NULL,
    "valeur"     text         NOT NULL,
    "ordre"      smallint     NOT NULL DEFAULT 0,
    "employe_id" integer      NOT NULL REFERENCES "ressources_humaines_employe" ("id") DEFERRABLE INITIALLY DEFERRED
);

-- HistoriqueEmploye
CREATE TABLE IF NOT EXISTS "ressources_humaines_historiqueemploye" (
    "id"               integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "type_changement"  varchar(20)  NOT NULL,
    "ancienne_valeur"  varchar(300) NOT NULL DEFAULT '',
    "nouvelle_valeur"  varchar(300) NOT NULL DEFAULT '',
    "note"             varchar(300) NOT NULL DEFAULT '',
    "date"             datetime     NOT NULL,
    "employe_id"       integer      NOT NULL REFERENCES "ressources_humaines_employe" ("id") DEFERRABLE INITIALLY DEFERRED,
    "fait_par_id"      integer      NULL     REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);

-- SoldeConge
CREATE TABLE IF NOT EXISTS "ressources_humaines_soldeconge" (
    "id"             integer        NOT NULL PRIMARY KEY AUTOINCREMENT,
    "annee"          smallint       NOT NULL,
    "quota"          decimal(5,1)   NOT NULL DEFAULT 0,
    "jours_pris"     decimal(5,1)   NOT NULL DEFAULT 0,
    "jours_reporter" decimal(5,1)   NOT NULL DEFAULT 0,
    "note"           text           NOT NULL DEFAULT '',
    "mis_a_jour_le"  datetime       NOT NULL,
    "employe_id"     integer        NOT NULL REFERENCES "ressources_humaines_employe" ("id") DEFERRABLE INITIALLY DEFERRED,
    UNIQUE ("employe_id", "annee")
);

-- JourFerie
CREATE TABLE IF NOT EXISTS "ressources_humaines_jourferie" (
    "id"        integer      NOT NULL PRIMARY KEY AUTOINCREMENT,
    "date"      date         NOT NULL UNIQUE,
    "nom"       varchar(100) NOT NULL,
    "recurrent" bool         NOT NULL DEFAULT 0
);

-- NotificationConge
CREATE TABLE IF NOT EXISTS "ressources_humaines_notificationconge" (
    "id"              integer     NOT NULL PRIMARY KEY AUTOINCREMENT,
    "type_notif"      varchar(20) NOT NULL,
    "message"         text        NOT NULL,
    "lue"             bool        NOT NULL DEFAULT 0,
    "cree_le"         datetime    NOT NULL,
    "conge_id"        integer     NOT NULL REFERENCES "ressources_humaines_conge" ("id") DEFERRABLE INITIALLY DEFERRED,
    "destinataire_id" integer     NOT NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);

-- HistoriqueConge
CREATE TABLE IF NOT EXISTS "ressources_humaines_historiqueconge" (
    "id"          integer     NOT NULL PRIMARY KEY AUTOINCREMENT,
    "action"      varchar(20) NOT NULL,
    "date"        datetime    NOT NULL,
    "commentaire" text        NOT NULL DEFAULT '',
    "conge_id"    integer     NOT NULL REFERENCES "ressources_humaines_conge" ("id") DEFERRABLE INITIALLY DEFERRED,
    "fait_par_id" integer     NULL     REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED
);

-- ── Colonnes manquantes : ressources_humaines_employe ─────────────────────────
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "sexe"                   varchar(1)  NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "date_naissance"          date        NULL;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "lieu_naissance"          varchar(150) NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "nationalite"             varchar(50)  NOT NULL DEFAULT 'Ivoirienne';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "situation_matrimoniale"  varchar(20)  NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "nombre_enfants"          integer      NOT NULL DEFAULT 0;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "photo"                   varchar(100) NULL;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "telephone2"              varchar(20)  NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "adresse"                 text         NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "service_id"              integer      NULL REFERENCES "medecins_service" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "fonction_id"             integer      NULL REFERENCES "ressources_humaines_fonction" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "grade_id"                integer      NULL REFERENCES "ressources_humaines_grade" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "type_contrat_id"         integer      NULL REFERENCES "ressources_humaines_typecontrat" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "notes"                   text         NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "biometric_id"            varchar(100) NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "cree_le"                 datetime     NULL;
ALTER TABLE "ressources_humaines_employe" ADD COLUMN "modifie_le"              datetime     NULL;

-- ── Colonnes manquantes : ressources_humaines_conge ───────────────────────────
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "nb_jours_ouvres"           smallint     NOT NULL DEFAULT 0;
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "date_approbation"          datetime     NULL;
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "commentaire_rh"            text         NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "valide_par_service_id"     integer      NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "date_validation_service"   datetime     NULL;
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "chef_service_commentaire"  text         NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_conge" ADD COLUMN "conge_parent_id"           integer      NULL REFERENCES "ressources_humaines_conge" ("id") DEFERRABLE INITIALLY DEFERRED;

-- ── Colonnes manquantes : ressources_humaines_presence ────────────────────────
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "heure_arrivee_matin"   time         NULL;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "heure_depart_matin"    time         NULL;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "heure_arrivee_soir"    time         NULL;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "heure_depart_soir"     time         NULL;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "permanence"            bool         NOT NULL DEFAULT 0;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "remarques"             varchar(300) NOT NULL DEFAULT '';
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "modifie_par_id"        integer      NULL REFERENCES "auth_user" ("id") DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE "ressources_humaines_presence" ADD COLUMN "modifie_le"            datetime     NULL;
""",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
