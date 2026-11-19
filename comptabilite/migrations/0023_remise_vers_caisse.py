from django.db import migrations, models

# Schéma de l'expert-comptable (journaux CAISSE PHARMACIE et PETITE CAISSE) :
# - les remises d'espèces passent par 58800000 « Autres virements internes »
#   et peuvent aller à une caisse hors guichet (petite caisse, caisse
#   principale), chacune dans son journal ;
# - les ventes vont au compte de produit de leur famille quand l'expert en a
#   un plus précis que celui de la nature.

CAISSES = [('Petite caisse', '57100005'), ('Caisse principale', '57100004')]

# (clé, libellé, compte)
VENTES = [
    ('vente:categorie:EC', 'Ventes — Échographies', '70522402'),
    ('vente:categorie:EG', 'Ventes — Électrocardiogrammes', '70522003'),
    ('vente:categorie:VC', 'Ventes — Vaccins', '70523003'),
    ('vente:categorie:AP', 'Ventes — Autres produits', '70510002'),
    ('vente:produit:consommable', 'Ventes — Consommables (autres produits pharmaceutiques)', '70510002'),
]


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    CompteTresorerie = apps.get_model('comptabilite', 'CompteTresorerie')
    comptes = {c.numero: c for c in Compte.objects.filter(totalisation=False)}

    if '58800000' in comptes:
        Correspondance.objects.filter(cle='virement_interne', compte__numero='58500000') \
            .update(compte=comptes['58800000'])

    for libelle, numero in CAISSES:
        compte = comptes.get(numero)
        if compte and not CompteTresorerie.objects.filter(compte=compte).exists() \
                and not CompteTresorerie.objects.filter(libelle=libelle).exists():
            CompteTresorerie.objects.create(libelle=libelle, type='caisse', compte=compte)

    for cle, libelle, numero in VENTES:
        if numero in comptes:
            Correspondance.objects.get_or_create(cle=cle, defaults={'libelle': libelle, 'compte': comptes[numero]})
    CategorieStock = apps.get_model('stock', 'CategorieStock')
    if '70512001' in comptes:
        for famille in CategorieStock.objects.filter(nom__icontains='eau'):
            Correspondance.objects.get_or_create(cle=f'vente:famille:{famille.pk}', defaults={
                'libelle': f'Ventes — {famille.nom}', 'compte': comptes['70512001']})


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0022_numerotation_pieces'),
    ]

    operations = [
        migrations.AlterField(
            model_name='comptetresorerie',
            name='type',
            field=models.CharField(choices=[('banque', 'Banque'), ('mobile_money', 'Mobile Money'), ('caisse', 'Caisse')], default='banque', max_length=15),
        ),
        migrations.RunPython(poser, migrations.RunPython.noop),
    ]
