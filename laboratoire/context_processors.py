from .models import AnalyseLaboratoire


def resultats_a_lire(request):
    """Alimente la cloche de notifications : les résultats d'examens arrivés
    pour le médecin connecté et qu'il n'a pas encore ouverts. Contrairement
    aux alertes de Soins, elle sort sur tous les modules — un résultat ne
    doit pas attendre que le médecin passe par le laboratoire."""
    if not request.user.is_authenticated:
        return {'resultats_a_lire': [], 'resultats_a_lire_count': 0}
    qs = (AnalyseLaboratoire.objects
          .filter(destinataire=request.user, vu_le__isnull=True)
          .select_related('patient', 'demande__rendez_vous__departement')
          .order_by('-date_resultat'))
    resultats = list(qs[:20])
    if resultats:
        from patients.rdv_destination import url_fiche_rdv
        from django.urls import reverse
        for a in resultats:
            rdv = a.demande.rendez_vous if a.demande_id else None
            a.url_notification = (
                url_fiche_rdv(request.user, rdv) + '?onglet=resultats' if rdv else
                reverse('patients:resultat_examen_detail', args=[a.patient_id, a.pk]))
    return {
        'resultats_a_lire': resultats,
        'resultats_a_lire_count': len(resultats) if len(resultats) < 20 else qs.count(),
    }
