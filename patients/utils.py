def save_registres(request, rdv, prefixes=None):
    """
    Collecte les champs POST dont le nom commence par un préfixe donné
    et les persiste dans le modèle Registre correspondant (JSONField).
    prefixes : liste de préfixes à traiter ; None = tous les 4.
    """
    from patients.models import (
        RegistreCPN, RegistreAccouchement,
        RegistrePostnatale, RegistreCuratif,
    )

    prefix_model = [
        ('cpn_',   RegistreCPN),
        ('acc_',   RegistreAccouchement),
        ('cposo_', RegistrePostnatale),
        ('cur_',   RegistreCuratif),
    ]

    for prefix, Model in prefix_model:
        if prefixes is not None and prefix not in prefixes:
            continue
        data = {}
        for key in request.POST:
            if key.startswith(prefix):
                vals = request.POST.getlist(key)
                data[key] = vals if len(vals) > 1 else (vals[0] if vals else '')
        if data:
            obj, _ = Model.objects.get_or_create(rdv=rdv)
            obj.donnees = data
            obj.save()


#: Codes du département « Médecine générale ». 'medg' est celui présent en base ;
#: 'MEDGEN' est le doublon que créerait la migration medecins/0015 (voir
#: rapports/med_generale.py). Les deux sont reconnus.
CODES_MEDECINE_GENERALE = ('medg', 'MEDGEN')


def departements_medecine_generale_ids():
    """Identifiants des départements « Médecine générale » (pour le JS des fiches)."""
    from medecins.models import Departement
    return list(Departement.objects.filter(code__in=CODES_MEDECINE_GENERALE)
                .values_list('pk', flat=True))


def type_visite_curative_obligatoire(rdv):
    """Le type de visite curative est exigé une fois la consultation démarrée,
    pour un type de consultation rattaché au département « Médecine générale ».

    `rdv` est lu tel quel : après `form.is_valid()`, il porte déjà le type de
    consultation posté.
    """
    if rdv.statut not in ('en_consultation', 'termine'):
        return False
    tc = rdv.type_consultation
    return bool(tc and tc.departement and tc.departement.code in CODES_MEDECINE_GENERALE)
