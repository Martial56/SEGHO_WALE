import django.db.models.deletion
from django.db import migrations, models

# Les journaux deviennent ceux de l'expert-comptable (docs/CODE JOURNAUX.xlsx,
# export Sage 100 « Liste des codes journaux »). Chaque journal de trésorerie
# porte son compte : une écriture qui mouvemente ce compte va dans ce journal.
# Les écritures des journaux semés passent dans le journal de l'expert
# correspondant, puis ces journaux sont supprimés.

# (code, intitulé, type, n° compte trésorerie)
JOURNAUX = [
    ('ACH', 'ACHATS', 'achats', None),
    ('BQ CC', 'SGCI COMPTE PRINCIPAL', 'tresorerie', '52110001'),
    ('BQ EGP', 'SIB EGPAF', 'tresorerie', '52110008'),
    ('BQ SIB', 'SIB COMPTE PRINCIPAL', 'tresorerie', '52110002'),
    ('BQDASY', 'SIB PROJET DASYC', 'tresorerie', '52110006'),
    ('BQICLI', 'SIB GUIPUZCOA ICLIC 2', 'tresorerie', '52110003'),
    ('BQIRC', 'SIB PROJET IRC', 'tresorerie', '52110005'),
    ('BQMANO', 'SIB PROJET MANOS UNIDAS', 'tresorerie', '52110009'),
    ('BQTENE', 'SIB PROJET TENERIFE', 'tresorerie', '52110007'),
    ('CAI AC', 'CAISSE ACCUEIL', 'tresorerie', '57100001'),
    ('CAI PH', 'CAISSE PHARMACIE', 'tresorerie', '57100002'),
    ('CAI PP', 'CAISSE PRINCIPALE', 'tresorerie', '57100004'),
    ('CAI TB', 'CAISSE TOUMBOKRO', 'tresorerie', '57100003'),
    ('CAISPC', 'PETITE CAISSE', 'tresorerie', '57100005'),
    ('OD', 'OPERATIONS DIVERSES', 'od', None),
    ('RAN', 'REPORTS A NOUVEAU', 'an', None),
    ('RAN.', 'REPORTS A NOUVEAU', 'od', None),
    ('SIBDEP', 'SIB COMPTE DEPOSIT', 'tresorerie', '52110004'),
    ('VTE', 'VENTE', 'ventes', None),
]

# Journal semé → journal de l'expert. Les journaux de caisse « CA-<code> »
# suivent le compte de leur caisse ; Mobile Money n'a pas de journal chez
# l'expert : ses écritures vont aux opérations diverses.
REMPLACEMENTS = {'CAI': 'CAI PP', 'BQ': 'BQ SIB', 'MM': 'OD', 'AN': 'RAN'}


def _deplacer(Ecriture, ancien, nouveau):
    """Toutes les écritures de `ancien` dans `nouveau` ; une écriture validée
    dont le numéro est déjà pris dans le nouveau journal prend le suivant."""
    for e in Ecriture._base_manager.filter(journal=ancien).order_by('exercice_id', 'numero', 'pk'):
        if e.numero is not None and Ecriture._base_manager.filter(
                journal=nouveau, exercice_id=e.exercice_id, numero=e.numero).exists():
            pris = Ecriture._base_manager.filter(journal=nouveau, exercice_id=e.exercice_id) \
                .aggregate(m=models.Max('numero'))['m'] or 0
            e.numero = pris + 1
        e.journal = nouveau
        e.save(update_fields=['journal', 'numero'])


def poser(apps, schema_editor):
    Journal = apps.get_model('comptabilite', 'Journal')
    Compte = apps.get_model('comptabilite', 'Compte')
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    Ecriture = apps.get_model('comptabilite', 'Ecriture')

    experts = {}
    for code, libelle, type_, numero in JOURNAUX:
        compte = Compte.objects.filter(numero=numero).first() if numero else None
        experts[code], _ = Journal.objects.update_or_create(code=code, defaults={
            'libelle': libelle, 'type': type_, 'compte_tresorerie': compte, 'actif': True})
    par_compte = {j.compte_tresorerie_id: j for j in experts.values() if j.compte_tresorerie_id}

    for ancien in Journal.objects.exclude(code__in=experts):
        nouveau = experts.get(REMPLACEMENTS.get(ancien.code))
        if nouveau is None and ancien.code.startswith('CA-') and ancien.caisse_id:
            corr = Correspondance.objects.filter(cle=f'caisse:{ancien.caisse.code}').first()
            nouveau = par_compte.get(corr.compte_id) if corr else None
        if nouveau is None:
            nouveau = experts['OD']
        _deplacer(Ecriture, ancien, nouveau)
        ancien.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0016_plan_expert_seul'),
    ]

    operations = [
        migrations.AddField(
            model_name='journal',
            name='compte_tresorerie',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='journaux', to='comptabilite.compte', verbose_name='N° compte trésorerie'),
        ),
        migrations.AlterField(
            model_name='journal',
            name='type',
            field=models.CharField(choices=[('ventes', 'Ventes'), ('achats', 'Achats'), ('tresorerie', 'Trésorerie'), ('od', 'Général'), ('an', 'Situation')], max_length=12),
        ),
        migrations.RunPython(poser, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='journal',
            name='caisse',
        ),
    ]
