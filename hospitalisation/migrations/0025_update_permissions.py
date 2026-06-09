from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('hospitalisation', '0024_add_permissions'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='hospitalisation',
            options={
                'ordering': ['-date_admission'],
                'verbose_name': 'Hospitalisation',
                'permissions': [
                    ('can_confirmer_demande', "Peut confirmer une demande d'hospitalisation"),
                    ('can_creer_facture',     "Peut créer une facture d'hospitalisation"),
                    ('can_installer_patient', "Peut installer le patient (passage en Hospitalisé)"),
                    ('can_decharger_patient', "Peut décharger un patient (sortie médicale)"),
                    ('can_referer_patient',   "Peut référer un patient vers un autre établissement"),
                    ('can_cloturer_dossier',  "Peut clôturer un dossier (passage à Terminé)"),
                    ('can_annuler_demande',   "Peut annuler une demande"),
                ],
            },
        ),
    ]
