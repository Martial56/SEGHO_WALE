from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blockchain_bridge', '0002_alter_ancrageblockchain_type_entite'),
    ]

    operations = [
        migrations.AddField(
            model_name='ancrageblockchain',
            name='version',
            field=models.PositiveIntegerField(default=1, verbose_name='Version'),
        ),
        migrations.AddConstraint(
            model_name='ancrageblockchain',
            constraint=models.UniqueConstraint(
                fields=('type_entite', 'id_entite', 'version'), name='ancrage_version_unique',
            ),
        ),
    ]
