from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('employer', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE ressources_humaines_employe SET date_embauche = '2020-01-01' WHERE date_embauche IS NULL",
            migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='employe',
            name='date_embauche',
            field=models.DateField(),
        ),
    ]
