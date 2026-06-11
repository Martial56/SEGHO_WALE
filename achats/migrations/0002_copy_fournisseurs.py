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


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('achats', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(copy_fournisseurs_from_stock, noop),
    ]
