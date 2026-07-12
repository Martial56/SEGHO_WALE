import shutil
import sqlite3
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Sauvegarde la base de données (SQLite ou PostgreSQL) et le dossier media/ dans un dossier horodaté."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dest', default=None,
            help="Dossier racine des sauvegardes (défaut: <BASE_DIR>/backups).",
        )
        parser.add_argument(
            '--keep-days', type=int, default=30,
            help="Supprime les sauvegardes plus anciennes que N jours (défaut: 30, 0 = ne rien supprimer).",
        )
        parser.add_argument(
            '--skip-media', action='store_true',
            help="Ne pas archiver le dossier media/.",
        )

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        backup_root = Path(options['dest']) if options['dest'] else base_dir / 'backups'
        backup_root.mkdir(parents=True, exist_ok=True)

        stamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
        dest = backup_root / stamp
        dest.mkdir(parents=True)

        db_config = settings.DATABASES['default']
        engine = db_config['ENGINE']

        try:
            if 'sqlite3' in engine:
                self._backup_sqlite(Path(db_config['NAME']), dest)
            elif 'postgresql' in engine:
                self._backup_postgres(db_config, dest)
            else:
                raise CommandError(f"Moteur de base de données non pris en charge : {engine}")

            if not options['skip_media']:
                self._backup_media(dest)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise

        if options['keep_days'] > 0:
            self._prune_old(backup_root, options['keep_days'])

        self.stdout.write(self.style.SUCCESS(f"Sauvegarde terminée : {dest}"))

    def _backup_sqlite(self, db_path, dest):
        if not db_path.exists():
            raise CommandError(f"Fichier SQLite introuvable : {db_path}")
        target = dest / db_path.name
        source_conn = sqlite3.connect(str(db_path))
        dest_conn = sqlite3.connect(str(target))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()
        self.stdout.write(f"  Base SQLite copiée -> {target}")

    def _backup_postgres(self, db_config, dest):
        pg_dump = shutil.which('pg_dump')
        if not pg_dump:
            raise CommandError("pg_dump introuvable dans le PATH ; impossible de sauvegarder PostgreSQL.")
        target = dest / f"{db_config['NAME']}.dump"
        env = {
            'PGPASSWORD': db_config.get('PASSWORD', ''),
        }
        import os
        full_env = os.environ.copy()
        full_env.update(env)
        cmd = [
            pg_dump,
            '-h', db_config.get('HOST', 'localhost'),
            '-p', str(db_config.get('PORT', 5432)),
            '-U', db_config.get('USER', 'postgres'),
            '-F', 'c',
            '-f', str(target),
            db_config['NAME'],
        ]
        result = subprocess.run(cmd, env=full_env, capture_output=True, text=True)
        if result.returncode != 0:
            raise CommandError(f"pg_dump a échoué : {result.stderr}")
        self.stdout.write(f"  Base PostgreSQL exportée -> {target}")

    def _backup_media(self, dest):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists() or not any(media_root.iterdir()):
            self.stdout.write("  Dossier media/ vide ou absent, ignoré.")
            return
        archive_base = dest / 'media'
        shutil.make_archive(str(archive_base), 'zip', root_dir=str(media_root))
        self.stdout.write(f"  Dossier media/ archivé -> {archive_base}.zip")

    def _prune_old(self, backup_root, keep_days):
        cutoff = timezone.now() - timezone.timedelta(days=keep_days)
        removed = 0
        for entry in backup_root.iterdir():
            if not entry.is_dir():
                continue
            try:
                entry_time = timezone.datetime.strptime(entry.name, '%Y-%m-%d_%H-%M-%S')
                entry_time = timezone.make_aware(entry_time, timezone.get_current_timezone())
            except ValueError:
                continue
            if entry_time < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
        if removed:
            self.stdout.write(f"  {removed} ancienne(s) sauvegarde(s) supprimée(s) (> {keep_days} jours).")
