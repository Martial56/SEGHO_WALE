from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):
    """
    Migration initiale de l'app employe.
    Toutes les tables DB existent déjà (sous le nom medecins_*).
    On utilise SeparateDatabaseAndState pour enregistrer l'état Django
    sans toucher à la base de données.
    """

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('services', '__first__'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='Specialite',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nom', models.CharField(max_length=100)),
                        ('code', models.CharField(max_length=20, unique=True)),
                        ('description', models.TextField(blank=True)),
                    ],
                    options={
                        'verbose_name': 'Spécialité',
                        'ordering': ['nom'],
                        'db_table': 'medecins_specialite',
                    },
                ),
                migrations.CreateModel(
                    name='Diplome',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('titre', models.CharField(max_length=200)),
                        ('description', models.TextField(blank=True)),
                    ],
                    options={
                        'verbose_name': 'Diplôme',
                        'verbose_name_plural': 'Diplômes',
                        'ordering': ['titre'],
                        'db_table': 'medecins_diplome',
                    },
                ),
                migrations.CreateModel(
                    name='Departement',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nom', models.CharField(max_length=100)),
                        ('code', models.CharField(max_length=20, unique=True)),
                        ('description', models.TextField(blank=True)),
                        ('actif', models.BooleanField(default=True)),
                    ],
                    options={
                        'verbose_name': 'Département',
                        'verbose_name_plural': 'Départements',
                        'ordering': ['nom'],
                        'db_table': 'medecins_departement',
                    },
                ),
                migrations.CreateModel(
                    name='Etiquette',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('nom', models.CharField(max_length=50, unique=True)),
                        ('couleur', models.CharField(blank=True, default='#0ea5e9', max_length=7)),
                    ],
                    options={
                        'verbose_name': 'Étiquette',
                        'verbose_name_plural': 'Étiquettes',
                        'ordering': ['nom'],
                        'db_table': 'medecins_etiquette',
                    },
                ),
                migrations.CreateModel(
                    name='Employe',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('code', models.CharField(blank=True, max_length=20, null=True, unique=True)),
                        ('matricule', models.CharField(blank=True, max_length=20, null=True, unique=True)),
                        ('nom', models.CharField(max_length=100)),
                        ('prenoms', models.CharField(max_length=200)),
                        ('genre', models.CharField(blank=True, choices=[('', '—'), ('M', 'Masculin'), ('F', 'Féminin')], default='', max_length=1, verbose_name='Genre')),
                        ('titre', models.CharField(blank=True, choices=[('', '—'), ('dr', 'Dr'), ('pr', 'Pr'), ('m', 'M.'), ('mme', 'Mme'), ('prof', 'Prof.')], max_length=10, verbose_name='Titre')),
                        ('date_naissance', models.DateField(blank=True, null=True, verbose_name='Date de naissance')),
                        ('lieu_naissance', models.CharField(blank=True, max_length=200, verbose_name='Lieu de naissance')),
                        ('photo', models.ImageField(blank=True, null=True, upload_to='medecins/photos/')),
                        ('est_medecin', models.BooleanField(default=False, verbose_name='Est Médecin/Docteur')),
                        ('est_referent', models.BooleanField(default=False, verbose_name='Est Médecin Référent')),
                        ('fonction', models.CharField(blank=True, max_length=100, verbose_name='Fonction / Poste')),
                        ('telephone', models.CharField(blank=True, max_length=20)),
                        ('mobile', models.CharField(blank=True, max_length=20)),
                        ('email', models.EmailField(blank=True, verbose_name='Email professionnel')),
                        ('adresse', models.TextField(blank=True, verbose_name="Lieu d'habitation")),
                        ('tva_numero_fiscal', models.CharField(blank=True, max_length=50, verbose_name='TVA / N° fiscal')),
                        ('ordre_medecin', models.CharField(blank=True, max_length=50)),
                        ('duree_consultation', models.PositiveSmallIntegerField(default=15, verbose_name='Durée consultation (min)')),
                        ('chirurgien_principal', models.BooleanField(default=False)),
                        ('taux_honoraire', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                        ('employe_societe', models.BooleanField(default=True, verbose_name='Employé de la société')),
                        ('signature', models.ImageField(blank=True, null=True, upload_to='medecins/signatures/', verbose_name='Signature')),
                        ('etablissement', models.CharField(blank=True, max_length=200, verbose_name='Établissement')),
                        ('langue', models.CharField(blank=True, default='Français', max_length=50, verbose_name='Langue')),
                        ('notes_internes', models.TextField(blank=True, verbose_name='Notes internes')),
                        ('actif', models.BooleanField(default=True)),
                        ('date_creation', models.DateTimeField(auto_now_add=True)),
                        ('user', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                        ('diplome', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='employe.diplome', verbose_name='Éducation')),
                        ('specialite', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='employe.specialite')),
                        ('departements', models.ManyToManyField(blank=True, related_name='employes', to='employe.departement', verbose_name='Départements')),
                        ('service_consultation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employes_consultation', to='services.articleservice', verbose_name='service de consultation')),
                        ('service_suivi', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='employes_suivi', to='services.articleservice', verbose_name='service de suivi')),
                    ],
                    options={
                        'verbose_name': 'Employé',
                        'verbose_name_plural': 'Employés',
                        'ordering': ['nom'],
                        'db_table': 'medecins_medecin',
                    },
                ),
                migrations.CreateModel(
                    name='DocteurReferent',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('code', models.CharField(blank=True, max_length=20, unique=True)),
                        ('type_contact', models.CharField(choices=[('individu', 'Individu'), ('societe', 'Société')], default='individu', max_length=10, verbose_name='Type')),
                        ('titre', models.CharField(blank=True, choices=[('', '—'), ('dr', 'Dr'), ('pr', 'Pr'), ('m', 'M.'), ('mme', 'Mme'), ('prof', 'Prof.')], max_length=10, verbose_name='Titre')),
                        ('nom', models.CharField(max_length=100)),
                        ('prenoms', models.CharField(blank=True, max_length=200, verbose_name='Prénom(s)')),
                        ('genre', models.CharField(blank=True, choices=[('', '—'), ('M', 'Masculin'), ('F', 'Féminin')], default='', max_length=1, verbose_name='Genre')),
                        ('photo', models.ImageField(blank=True, null=True, upload_to='medecins/referents/')),
                        ('poste_occupe', models.CharField(blank=True, max_length=100, verbose_name='Poste Occupé')),
                        ('etablissement', models.CharField(blank=True, max_length=200, verbose_name='Établissement')),
                        ('telephone', models.CharField(blank=True, max_length=20, verbose_name='Téléphone')),
                        ('mobile', models.CharField(blank=True, max_length=20)),
                        ('email', models.EmailField(blank=True)),
                        ('site_web', models.URLField(blank=True, verbose_name='Site Web')),
                        ('langue', models.CharField(blank=True, default='Français', max_length=50, verbose_name='Langue')),
                        ('adresse', models.TextField(blank=True)),
                        ('tva', models.CharField(blank=True, max_length=50, verbose_name='TVA')),
                        ('est_referent', models.BooleanField(default=True, verbose_name='Est le médecin référent')),
                        ('reference_externe', models.CharField(blank=True, max_length=100, verbose_name='Référence')),
                        ('compte_client', models.CharField(blank=True, max_length=100, verbose_name='Compte client')),
                        ('compte_fournisseur', models.CharField(blank=True, max_length=100, verbose_name='Compte fournisseur')),
                        ('notes', models.TextField(blank=True, verbose_name='Notes internes')),
                        ('actif', models.BooleanField(default=True)),
                        ('date_creation', models.DateTimeField(auto_now_add=True)),
                        ('specialite', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='employe.specialite', verbose_name='Spécialité')),
                        ('etiquettes', models.ManyToManyField(blank=True, to='employe.etiquette', verbose_name='Étiquettes')),
                        ('medecin_interne', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='referents_associes', to='employe.employe', verbose_name='Docteur référent (interne)')),
                    ],
                    options={
                        'verbose_name': 'Docteur Référent',
                        'verbose_name_plural': 'Docteurs Référents',
                        'ordering': ['nom'],
                        'db_table': 'medecins_docteurreferent',
                    },
                ),
                migrations.CreateModel(
                    name='ContactAdresse',
                    fields=[
                        ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('type_adresse', models.CharField(choices=[('contact', 'Contact'), ('facturation', 'Adresse de facturation'), ('livraison', 'Adresse de livraison'), ('autre', 'Autre adresse')], default='contact', max_length=20, verbose_name='Type')),
                        ('nom', models.CharField(blank=True, max_length=100, verbose_name='Nom')),
                        ('telephone', models.CharField(blank=True, max_length=20, verbose_name='Téléphone')),
                        ('email', models.EmailField(blank=True, verbose_name='Courriel')),
                        ('adresse', models.TextField(blank=True, verbose_name='Adresse')),
                        ('referent', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contacts_adresses', to='employe.docteurreferent')),
                    ],
                    options={
                        'verbose_name': 'Contact / Adresse',
                        'verbose_name_plural': 'Contacts / Adresses',
                        'db_table': 'medecins_contactadresse',
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
