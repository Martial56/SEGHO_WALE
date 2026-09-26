from django.core.management.color import no_style
from django.db import migrations
from django.utils import timezone


def copy_fournisseurs_from_stock(apps, schema_editor):
    Fournisseur = apps.get_model('achats', 'Fournisseur')
    db = schema_editor.connection
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, code, nom, telephone, email, adresse, actif FROM stock_fournisseur"
        )
        rows = cursor.fetchall()
    now = timezone.now()
    for row in rows:
        pk, code, nom, tel, email, adresse, actif = row
        if not Fournisseur.objects.filter(pk=pk).exists():
            Fournisseur.objects.create(
                id=pk,
                code=code or '',
                nom=nom or '',
                telephone=tel or '',
                email=email or '',
                adresse=adresse or '',
                actif=bool(actif),
            )

    # Les id recopiés explicitement ne font pas avancer la séquence PostgreSQL :
    # sans cette remise à niveau, le prochain Fournisseur créé entrerait en
    # conflit de clé primaire. SQLite n'en a pas besoin (rowid).
    if rows and db.vendor != 'sqlite':
        with db.cursor() as cursor:
            for sql in db.ops.sequence_reset_sql(no_style(), [Fournisseur]):
                cursor.execute(sql)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('achats', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_fournisseurs_from_stock, noop),
    ]
