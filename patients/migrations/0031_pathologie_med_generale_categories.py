# Recatégorise le catalogue Pathologie pour le rapport mensuel de médecine
# générale (rapports/med_generale.py), qui passe d'un matching par nom exact
# codé en dur à un filtre sur Pathologie.categorie + departement — même
# principe que rapports/gynecologie.py.
#
# Ce mapping nom -> catégorie reprend exactement les listes SECTION_A/B/C de
# rapports/med_generale.py (avant sa réécriture) : ce sont les libellés du
# formulaire papier d'origine, déjà rapprochés du catalogue par nom exact.
from django.db import migrations

# ── A : Maladies infectieuses ──
NOMS_INFECTIEUSE = [
    'Cas suspect de Paludisme', 'Cas suspect de Paludisme FE', 'Cas de Paludisme simple',
    'Cas de Paludisme simple chez FE', 'Cas suspect de Paludisme grave référé',
    'Cas suspect de Paludisme grave référée chez FE', 'Cas présumé de paludisme',
    'Cas présumé de paludisme chez la FE',
    'Cas de paludisme simple avec prescription de CTA (y compris femmes enceintes)',
    'Cas de paludisme simple chez FE avec prescription de CTA',
    'Cas de paludisme simple chez FE avec prescription de quinine',
    'Cas suspect de paludisme avec prescription de CTA (présumé), y compris femme enceinte',
    'Cas suspect de paludisme chez la femme enceinte avec prescription de CTA (présumé)',
    'Diarrhée aiguë sans déshydratation', 'Diarrhée aiguë avec signes évidents de déshydratation',
    'Diarrhée aiguë avec déshydratation sévère', 'Diarrhée aiguë sanglante',
    'Pneumonie Simple (IRA basse)', 'Pneumonie grave (IRA basse)', 'Broncho-pneumonie (IRA basse)',
    'Otite moyenne aigue (IRA haute)', 'Rhinopharyngite (IRA haute)', 'Angine (IRA haute)',
    'Sinusite (IRA haute)', 'Laryngite (IRA haute)', 'Pian', 'Bilharziose urinaire (CS)',
    'Trichiasis trachomateux (CS)', "Cas suspect d'hydrocèle", 'Cas suspects de lymphodoedème',
    'Onchocercose', 'Tétanos', 'Coqueluche', 'Conjonctivite', 'Fièvre Typhoïde / Salmonellose',
    'Fièvre Jaune', 'Choléra', 'Méningite', 'Tuberculose (cas suspecte)',
    'Ulcère de burili (cas suspect)', 'Varicelle', 'Dermatose', 'Zona', 'Hépatite virale B',
    'Hépatite virale C', 'Autres maladies infectieuses',
    "Nombre d'enfants atteints de la pneumonie et ayant reçu une prescription d'antibiotique",
    "Nombre d'enfants atteint de la diarrhée et ayant réçu une prescription de SRO + ZINC",
]

# ── B : Autres maladies non infectieuses et facteurs de risque cardiovasculaire ──
NOMS_NON_INFECTIEUSE = [
    'Malnutrition modérée', 'Malnutrition aiguë sévère référé',
    "HTA sans antécédent de HTA connu chez l'adulte, y compris FE",
    'HTA sans antécédent de HTA connu chez les FE (adulte)',
    "HTA avec antécédent de HTA connu chez l'adulte, y compris FE",
    'HTA avec antécédent de HTA connu chez les FE (adulte)',
    'Hyperglycémie sans antécédent de diabète connu', 'Diabète gestationnel', 'Asthme',
    'Drépanocytose', 'Insuffisance rénale aiguë', 'Accidenté de la voie publique',
    'Troubles psychiatriques', 'Retard psychomoteur', 'Anémie modérée', 'Anémie grave', 'GEU',
    'Fibrome utérin', 'Appendicite', 'Occlusion intestinale', 'Hernie', 'Péritonite', 'Goitre',
    'Brûlure', 'Accident vasculaire cérébral (AVC)', 'Morsure de serpent', 'Tentative de suicide',
    'Autres traumatismes', 'Maladies indéterminées', 'Autres maladies non infectieuses',
]

# ── C : Infections sexuellement transmissibles ──
NOMS_IST = [
    'Écoulement urétral masculin et/ou douleur et/ou prurit et/ou gêne intra urétral',
    'Écoulement vaginal et/ou brûlure ou prurit et/ou malodeur vaginale',
    'Ulcération génitale et/ou bubon masculin', 'Ulcération génitale et/ou bubon féminin',
    'Douleur testiculaire', 'Douleurs abdominales basses (pelviennes) chez la femme',
    'Conjonctivite du nouveau-né',
    'Condylome (végétation vénériennes ou crêtes de coq) masculin',
    'Condylome (végétation vénériennes ou crêtes de coq) féminin',
]

CATEGORIE_PAR_NOM = (
    [(nom, 'infectieuse') for nom in NOMS_INFECTIEUSE]
    + [(nom, 'non_infectieuse') for nom in NOMS_NON_INFECTIEUSE]
    + [(nom, 'ist') for nom in NOMS_IST]
)


def recategoriser(apps, schema_editor):
    Pathologie = apps.get_model('patients', 'Pathologie')
    Departement = apps.get_model('medecins', 'Departement')

    # 'medg' est le département "Médecine générale" réellement utilisé en base
    # (voir patients/migrations/0029_pathologie_departement_data.py) — 'MEDGEN'
    # est un doublon orphelin qu'il ne faut pas préférer, même si un .first()
    # sans order_by explicite peut le remonter en premier (tri par nom).
    medg = (
        Departement.objects.filter(code='medg').first()
        or Departement.objects.filter(code='MEDGEN').first()
    )

    for nom, categorie in CATEGORIE_PAR_NOM:
        Pathologie.objects.update_or_create(
            nom=nom, defaults={'categorie': categorie, 'departement': medg},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0030_alter_pathologie_categorie'),
    ]

    operations = [
        migrations.RunPython(recategoriser, noop_reverse),
    ]
