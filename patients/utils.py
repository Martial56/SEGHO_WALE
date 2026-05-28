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
