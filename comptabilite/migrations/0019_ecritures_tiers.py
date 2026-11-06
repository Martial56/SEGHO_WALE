import unicodedata

import django.db.models.deletion
from django.db import migrations, models

# Les écritures se rattachent au plan tiers de l'expert-comptable. Les
# patients d'une caisse sont le client « CLIENT CAISSE … » de cette caisse,
# chaque assureur a son compte client, chaque fournisseur le sien. On désigne
# ici ce qui se reconnaît au nom, puis les lignes de classe 4 déjà passées
# reçoivent leur compte tiers.

# Mot du nom de la caisse → client de l'expert.
CAISSES = [('PHARMA', '41250007'), ('ACCU', '41250008'), ('TOUMBOKRO', '41250006')]


def _norm(texte):
    texte = unicodedata.normalize('NFKD', str(texte or ''))
    return ''.join(ch for ch in texte.upper() if ch.isalnum())


def designer(apps):
    Caisse = apps.get_model('facturation', 'Caisse')
    Assurance = apps.get_model('patients', 'Assurance')
    Tiers = apps.get_model('comptabilite', 'Tiers')
    CorrespondanceTiers = apps.get_model('comptabilite', 'CorrespondanceTiers')
    FactureFournisseur = apps.get_model('comptabilite', 'FactureFournisseur')
    clients = {t.numero: t for t in Tiers.objects.filter(type='client')}
    for caisse in Caisse.objects.all():
        numero = next((n for mot, n in CAISSES if mot in _norm(caisse.nom)), None)
        if numero in clients:
            CorrespondanceTiers.objects.get_or_create(cle=f'caisse:{caisse.code}', defaults={
                'libelle': f'Caisse {caisse.nom}', 'tiers': clients[numero]})
    assureurs = [t for t in clients.values() if t.numero.startswith('4125')]
    for a in Assurance.objects.all():
        nom = _norm(a.nom)
        trouves = [t for t in assureurs if nom and (nom in _norm(t.intitule) or _norm(t.intitule) in nom)]
        if len(trouves) == 1:
            CorrespondanceTiers.objects.get_or_create(cle=f'assurance:{a.code}', defaults={
                'libelle': f'Assurance {a.nom}', 'tiers': trouves[0]})
    fournisseurs = {}
    for t in Tiers.objects.filter(type='fournisseur', actif=True):
        fournisseurs.setdefault(t.intitule.strip().upper(), []).append(t)
    for f in FactureFournisseur._base_manager.filter(compte_tiers__isnull=True):
        trouves = fournisseurs.get(f.fournisseur.strip().upper(), [])
        if len(trouves) == 1:
            f.compte_tiers = trouves[0]
            f.save(update_fields=['compte_tiers'])


def rattacher(apps):
    """Compte tiers des lignes de classe 4 déjà passées, d'après leur origine."""
    Correspondance = apps.get_model('comptabilite', 'Correspondance')
    CorrespondanceTiers = apps.get_model('comptabilite', 'CorrespondanceTiers')
    LigneEcriture = apps.get_model('comptabilite', 'LigneEcriture')
    Paiement = apps.get_model('facturation', 'Paiement')
    Facture = apps.get_model('facturation', 'Facture')
    Avoir = apps.get_model('comptabilite', 'Avoir')
    RejetAssurance = apps.get_model('comptabilite', 'RejetAssurance')
    ReglementAssurance = apps.get_model('comptabilite', 'ReglementAssurance')
    FactureFournisseur = apps.get_model('comptabilite', 'FactureFournisseur')
    ReglementFournisseur = apps.get_model('comptabilite', 'ReglementFournisseur')
    Caisse = apps.get_model('facturation', 'Caisse')
    Assurance = apps.get_model('patients', 'Assurance')

    designes = {c.cle: c.tiers_id for c in CorrespondanceTiers.objects.all()}
    patient = Correspondance.objects.filter(cle='patient').values_list('compte_id', flat=True).first()
    codes_caisse = dict(Caisse.objects.values_list('pk', 'code'))
    codes_assurance = dict(Assurance.objects.values_list('pk', 'code'))

    def de_caisse(caisse_id):
        return designes.get(f'caisse:{codes_caisse.get(caisse_id)}')

    def de_assurance(assurance_id):
        return designes.get(f'assurance:{codes_assurance.get(assurance_id)}')

    def premiere_caisse(facture_id):
        return (Paiement._base_manager.filter(facture_id=facture_id, caisse__isnull=False)
                .order_by('date_paiement', 'pk').values_list('caisse_id', flat=True).first())

    def de_facture(facture_id, compte_id, caisse_id=None):
        if compte_id == patient:
            return de_caisse(caisse_id or premiere_caisse(facture_id))
        return de_assurance(Facture._base_manager.filter(pk=facture_id)
                            .values_list('assurance_id', flat=True).first())

    for ligne in (LigneEcriture.objects.filter(compte__numero__startswith='4', compte_tiers__isnull=True)
                  .exclude(ecriture__origine__isnull=True).select_related('ecriture')):
        nature, _, pk = (ligne.ecriture.origine or '').partition(':')
        if not pk.isdigit():
            continue
        pk, tiers = int(pk), None
        if nature == 'facture':
            tiers = de_facture(pk, ligne.compte_id)
        elif nature == 'paiement':
            p = Paiement._base_manager.filter(pk=pk).first()
            tiers = p and de_facture(p.facture_id, ligne.compte_id, p.caisse_id)
        elif nature in ('avoir', 'remboursement'):
            a = Avoir._base_manager.filter(pk=pk).select_related('session__journee').first()
            caisse_id = a.session.journee.caisse_id if a and a.session_id and nature == 'remboursement' else None
            tiers = a and de_facture(a.facture_id, ligne.compte_id, caisse_id)
        elif nature == 'rejet':
            r = RejetAssurance._base_manager.filter(pk=pk).first()
            tiers = r and de_facture(r.facture_id, ligne.compte_id)
        elif nature == 'reglement':
            r = ReglementAssurance._base_manager.filter(pk=pk).first()
            tiers = r and de_assurance(r.assurance_id)
        elif nature == 'facture_fournisseur':
            tiers = FactureFournisseur._base_manager.filter(pk=pk).values_list('compte_tiers_id', flat=True).first()
        elif nature == 'reglement_fournisseur':
            tiers = (ReglementFournisseur._base_manager.filter(pk=pk)
                     .values_list('facture__compte_tiers_id', flat=True).first())
        if tiers:
            ligne.compte_tiers_id = tiers
            ligne.save(update_fields=['compte_tiers'])


def poser(apps, schema_editor):
    designer(apps)
    rattacher(apps)


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0018_plan_tiers'),
    ]

    operations = [
        migrations.AddField(
            model_name='facturefournisseur',
            name='compte_tiers',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='factures_fournisseur', to='comptabilite.tiers', verbose_name='Compte tiers'),
        ),
        migrations.AddField(
            model_name='ligneecriture',
            name='compte_tiers',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lignes', to='comptabilite.tiers', verbose_name='Compte tiers'),
        ),
        migrations.CreateModel(
            name='CorrespondanceTiers',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cle', models.CharField(max_length=60, unique=True)),
                ('libelle', models.CharField(max_length=150)),
                ('tiers', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='correspondances', to='comptabilite.tiers')),
            ],
            options={
                'verbose_name': 'Correspondance tiers',
                'verbose_name_plural': 'Correspondances tiers',
                'ordering': ['cle'],
            },
        ),
        migrations.RunPython(poser, migrations.RunPython.noop),
    ]
