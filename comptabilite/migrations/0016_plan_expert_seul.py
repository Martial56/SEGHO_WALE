import json
from pathlib import Path

from django.db import migrations

# Le plan comptable devient exactement celui de l'expert-comptable
# (comptabilite/data/plan_expert.json, tiré de docs/PLAN COMPTABLE.xlsx).
# Les comptes semés aux lots 3 à 8 et les deux comptes ajoutés en 0015
# disparaissent : tout ce qui les désignait — lignes d'écriture comprises —
# passe sur le compte de l'expert ci-dessous, puis ils sont supprimés. Un
# numéro semé que l'expert emploie aussi (601, 701, 706…) reste, avec
# l'intitulé et le type (totalisation) de l'expert.
PLAN = Path(__file__).resolve().parent.parent / 'data' / 'plan_expert.json'

REMPLACEMENTS = {
    '101': '10110000', '102': '10210000', '121': '12110000', '129': '12910000',
    '131': '12810000', '139': '12890000', '141': '14170000',
    # Fonds dédiés : fonds affectés à un projet spécifique (165), leur
    # reprise (7925) ; la dotation va en 6911, faute de compte d'engagement.
    '195': '16510000', '689': '69110000', '789': '79250000',
    '231': '23130000', '241': '24150000', '244': '24410000', '245': '24510000',
    '311': '32100000', '331': '33100001',
    '401': '40110000', '411': '41250000', '4111': '41250000', '4112': '41250001', '419': '41920000',
    '421': '42110000', '422': '42200000', '458': '46920000',
    # Chèques : l'expert n'a que le compte de totalisation 513 ; ils vont en banque.
    '513': '52110002', '51310000': '52110002', '521': '52110002',
    '552': '55200000', '5521': '55800002', '5522': '55800001', '5523': '55800000', '55800003': '55800000',
    '571': '57100004', '5711': '57100002', '5712': '57100001', '585': '58500000',
    '601': '60210001', '6031': '60320000', '6033': '60330000', '604': '60410000', '605': '60580001',
    '618': '61830002', '624': '62480000', '631': '63180000',
    '651': '65110000', '658': '65880000', '661': '66110000',
    # Remises et gratuités : pas de 709 chez l'expert ; elles sont une aide
    # accordée aux patients (6582 Dons).
    '709': '65820000',
    '701': '70510001', '706': '70520000', '7061': '70520100', '7062': '70523002', '7063': '70523001',
    '7064': '70522001', '7065': '70522002', '7068': '70524002',
    '718': '71300200', '758': '75880000', '7581': '70410000', '7582': '75880000',
}


def _relations(Compte):
    return [(r.related_model, r.field.name) for r in Compte._meta.related_objects]


def _deplacer(apps, Compte, ancien, nouveau):
    for modele, champ in _relations(Compte):
        qs = modele._base_manager.filter(**{champ: ancien})
        if modele._meta.model_name == 'lignebudget':
            for lb in qs:
                existante = modele._base_manager.filter(exercice_id=lb.exercice_id, compte=nouveau).first()
                if existante:
                    existante.montant += lb.montant
                    existante.save(update_fields=['montant'])
                    lb.delete()
                else:
                    lb.compte = nouveau
                    lb.save(update_fields=['compte'])
        elif modele._meta.model_name == 'comptetresorerie':
            if not modele._base_manager.filter(compte=nouveau).exists():
                qs.update(compte=nouveau)
        else:
            qs.update(**{champ: nouveau})


def _designe(Compte, compte):
    return any(m._base_manager.filter(**{c: compte}).exists() for m, c in _relations(Compte))


def poser(apps, schema_editor):
    Compte = apps.get_model('comptabilite', 'Compte')
    plan = {n: (i, t, nat) for n, i, t, nat in json.loads(PLAN.read_text(encoding='utf-8'))}

    existants = set(Compte.objects.values_list('numero', flat=True))
    Compte.objects.bulk_create([Compte(numero=n, intitule=i, totalisation=t, nature=nat)
                                for n, (i, t, nat) in plan.items() if n not in existants])
    comptes = {c.numero: c for c in Compte.objects.all()}

    for ancien, nouveau in REMPLACEMENTS.items():
        if ancien in comptes:
            _deplacer(apps, Compte, comptes[ancien], comptes[nouveau])

    for numero, compte in comptes.items():
        if numero in plan:
            intitule, totalisation, nature = plan[numero]
            compte.intitule, compte.totalisation, compte.nature = intitule, totalisation, nature
            compte.actif, compte.a_valider = True, False
            compte.save(update_fields=['intitule', 'totalisation', 'nature', 'actif', 'a_valider'])
        elif not _designe(Compte, compte):
            compte.delete()
        # Un compte hors plan encore désigné (sous-compte de caisse créé à
        # l'écran, par exemple) est gardé : le supprimer perdrait des données.


class Migration(migrations.Migration):

    dependencies = [
        ('comptabilite', '0015_plan_expert_correspondances'),
    ]

    operations = [
        migrations.RunPython(poser, migrations.RunPython.noop),
    ]
