"""
Catalogue des rapports du module.

Chaque rapport « interne » sait construire ses propres colonnes/lignes pour
une période donnée (periode_debut, periode_fin : objets date) ; le moteur
d'export (voir export.py) se charge ensuite de produire le fichier Excel/CSV.

Les rapports « externes » pointent simplement vers des pages de rapport déjà
existantes dans d'autres modules — on ne les déplace pas, on les rend juste
visibles depuis ce catalogue central.
"""


def _patients_inscrits(periode_debut, periode_fin):
    from patients.models import Patient
    qs = Patient.objects.filter(
        date_creation__date__range=[periode_debut, periode_fin]
    ).order_by('date_creation')
    columns = ['Code patient', 'Ville', "Date d'inscription", 'Nom', 'Prénoms', 'Sexe',
               'Date de naissance', 'Âge', 'Téléphone']
    rows = [[
        p.code_patient, p.ville, p.date_creation.strftime('%d/%m/%Y'),
        p.nom, p.prenoms, p.sexe, p.date_naissance.strftime('%d/%m/%Y'), p.age, p.telephone,
    ] for p in qs]
    return columns, rows


def _rendez_vous_columns_rows(qs):
    columns = ['Code RDV', 'Patient', 'Médecin', 'Service', 'Date/heure', 'Type', 'Statut']
    rows = [[
        r.code_rdv, str(r.patient), str(r.medecin) if r.medecin else '—',
        str(r.departement) if r.departement else '—',
        r.date_heure.strftime('%d/%m/%Y %H:%M'), r.get_type_rdv_display(), r.get_statut_display(),
    ] for r in qs]
    return columns, rows


def _gyneco_filter(qs):
    from django.db.models import Q
    return qs.filter(Q(departement__code='GYN') | Q(medecin__specialite__nom__icontains='gyn'))


def _rendez_vous_medecine(periode_debut, periode_fin):
    from patients.models import RendezVous
    qs = RendezVous.objects.filter(
        date_heure__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin', 'departement')
    ids_gyneco = _gyneco_filter(qs).values_list('pk', flat=True)
    qs = qs.exclude(pk__in=list(ids_gyneco)).order_by('date_heure')
    return _rendez_vous_columns_rows(qs)


def _rendez_vous_gynecologie(periode_debut, periode_fin):
    from patients.models import RendezVous
    qs = RendezVous.objects.filter(
        date_heure__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin', 'departement')
    qs = _gyneco_filter(qs).order_by('date_heure')
    return _rendez_vous_columns_rows(qs)


def _soins_dispenses(periode_debut, periode_fin):
    from soins.models import Soin
    qs = Soin.objects.filter(
        date_heure__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'infirmier', 'departement').order_by('date_heure')
    columns = ['Numéro', 'Patient', 'Infirmier', 'Service', 'Motif', 'Date/heure', 'Statut']
    rows = [[
        s.numero, str(s.patient), str(s.infirmier) if s.infirmier else '—',
        str(s.departement) if s.departement else '—', s.motif[:150],
        s.date_heure.strftime('%d/%m/%Y %H:%M'), s.get_statut_display(),
    ] for s in qs]
    return columns, rows


def _consultations(periode_debut, periode_fin):
    from consultations.models import Consultation
    qs = Consultation.objects.filter(
        date_heure__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin').order_by('date_heure')
    columns = ['Numéro', 'Patient', 'Médecin', 'Date/heure', 'Motif', 'Statut']
    rows = [[
        c.numero, str(c.patient), str(c.medecin) if c.medecin else '—',
        c.date_heure.strftime('%d/%m/%Y %H:%M'), c.motif[:150], c.get_statut_display(),
    ] for c in qs]
    return columns, rows


def _ordonnances(periode_debut, periode_fin):
    from consultations.models import Ordonnance
    qs = Ordonnance.objects.filter(
        date_emission__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin').order_by('date_emission')
    columns = ['Numéro', 'Patient', 'Médecin prescripteur', "Date d'émission", 'Type', 'Statut']
    rows = [[
        o.numero, str(o.patient) if o.patient else '—', str(o.medecin) if o.medecin else '—',
        o.date_emission.strftime('%d/%m/%Y %H:%M'), o.get_type_ordonnance_display(), o.get_statut_display(),
    ] for o in qs]
    return columns, rows


def _hospitalisations(periode_debut, periode_fin):
    from hospitalisation.models import Hospitalisation
    qs = Hospitalisation.objects.filter(
        date_admission__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin_traitant', 'chambre').order_by('date_admission')
    columns = ['Numéro', 'Patient', 'Médecin traitant', 'Chambre', "Date d'admission", 'Statut']
    rows = [[
        h.numero, str(h.patient), str(h.medecin_traitant) if h.medecin_traitant else '—',
        str(h.chambre) if h.chambre else '—', h.date_admission.strftime('%d/%m/%Y %H:%M'),
        h.get_statut_display(),
    ] for h in qs]
    return columns, rows


def _deces(periode_debut, periode_fin):
    from hospitalisation.models import RegistreDeces
    qs = RegistreDeces.objects.filter(
        date_deces__range=[periode_debut, periode_fin]
    ).select_related('patient', 'medecin').order_by('date_deces')
    columns = ['Code', 'Patient', 'Date de décès', 'Médecin', 'Raison', 'Statut']
    rows = [[
        d.code, str(d.patient), d.date_deces.strftime('%d/%m/%Y'),
        str(d.medecin) if d.medecin else '—', d.raison_deces[:200], d.get_statut_display(),
    ] for d in qs]
    return columns, rows


def _analyses_laboratoire(periode_debut, periode_fin):
    from laboratoire.models import AnalyseLaboratoire
    qs = AnalyseLaboratoire.objects.filter(
        date_prelevement__date__range=[periode_debut, periode_fin]
    ).select_related('patient', 'type_examen').order_by('date_prelevement')
    columns = ['Numéro', 'Patient', "Type d'examen", 'Date de prélèvement', 'Statut', 'Urgent']
    rows = [[
        a.numero, str(a.patient), str(a.type_examen) if a.type_examen else '—',
        a.date_prelevement.strftime('%d/%m/%Y %H:%M'), a.get_statut_display(),
        'Oui' if a.urgent else 'Non',
    ] for a in qs]
    return columns, rows


def _factures(periode_debut, periode_fin):
    from facturation.models import Facture
    qs = Facture.objects.filter(
        date_emission__date__range=[periode_debut, periode_fin]
    ).select_related('patient').order_by('date_emission')
    columns = ['Numéro', 'Patient', 'Type', "Date d'émission", 'Montant total (FCFA)',
               'Montant assurance (FCFA)', 'Montant payé (FCFA)', 'Solde restant (FCFA)', 'Statut']
    rows = [[
        f.numero, str(f.patient), f.get_type_facture_display(), f.date_emission.strftime('%d/%m/%Y %H:%M'),
        float(f.montant_total), float(f.montant_assurance), float(f.montant_paye),
        float(f.solde_restant), f.get_statut_display(),
    ] for f in qs]
    return columns, rows


def _paiements(periode_debut, periode_fin):
    from facturation.models import Paiement
    qs = Paiement.objects.filter(
        date_paiement__date__range=[periode_debut, periode_fin]
    ).select_related('facture', 'facture__patient', 'recu_par').order_by('date_paiement')
    columns = ['Numéro', 'Facture', 'Patient', 'Montant (FCFA)', 'Mode de paiement', 'Reçu par', 'Date']
    rows = [[
        p.numero, p.facture.numero if p.facture else '—',
        str(p.facture.patient) if p.facture else '—', float(p.montant), p.get_mode_paiement_display(),
        str(p.recu_par) if p.recu_par else '—', p.date_paiement.strftime('%d/%m/%Y %H:%M'),
    ] for p in qs]
    return columns, rows


def _transactions_caisse(periode_debut, periode_fin):
    from caisse.models import TransactionCaisse
    qs = TransactionCaisse.objects.filter(
        date_transaction__date__range=[periode_debut, periode_fin]
    ).select_related('session__caisse', 'cree_par').order_by('date_transaction')
    columns = ['Numéro', 'Caisse', 'Type', 'Mode de paiement', 'Montant (FCFA)', 'Créé par', 'Date']
    rows = [[
        t.numero, str(t.session.caisse) if t.session_id else '—', t.get_type_transaction_display(),
        t.get_mode_paiement_display(), float(t.montant), str(t.cree_par) if t.cree_par else '—',
        t.date_transaction.strftime('%d/%m/%Y %H:%M'),
    ] for t in qs]
    return columns, rows


def _mouvements_stock_pharmacie(periode_debut, periode_fin):
    from pharmacie.models import MouvementStock
    qs = MouvementStock.objects.filter(
        date_mouvement__date__range=[periode_debut, periode_fin]
    ).select_related('medicament', 'cree_par').order_by('date_mouvement')
    columns = ['Médicament', 'Type', 'Motif', 'Quantité', 'Stock avant', 'Stock après', 'Créé par', 'Date']
    rows = [[
        str(m.medicament), m.get_type_mouvement_display(), m.get_motif_display(), m.quantite,
        m.stock_avant, m.stock_apres, str(m.cree_par) if m.cree_par else '—',
        m.date_mouvement.strftime('%d/%m/%Y %H:%M'),
    ] for m in qs]
    return columns, rows


def _employes_embauches(periode_debut, periode_fin):
    from employer.models import Employe
    qs = Employe.objects.filter(
        date_embauche__range=[periode_debut, periode_fin]
    ).select_related('service', 'fonction').order_by('date_embauche')
    columns = ['Matricule', 'Nom', 'Prénoms', 'Service', 'Fonction', "Date d'embauche", 'Statut']
    rows = [[
        e.matricule, e.nom, e.prenoms, str(e.service) if e.service else '—',
        str(e.fonction) if e.fonction else '—', e.date_embauche.strftime('%d/%m/%Y'), e.get_statut_display(),
    ] for e in qs]
    return columns, rows


def _conges(periode_debut, periode_fin):
    from employer.models import Conge
    qs = Conge.objects.filter(
        date_debut__range=[periode_debut, periode_fin]
    ).select_related('employe').order_by('date_debut')
    columns = ['Employé', 'Type de congé', 'Du', 'Au', 'Durée (jours)', 'Statut']
    rows = [[
        str(c.employe), c.get_type_conge_display(), c.date_debut.strftime('%d/%m/%Y'),
        c.date_fin.strftime('%d/%m/%Y'), c.duree, c.get_statut_display(),
    ] for c in qs]
    return columns, rows


def _presences(periode_debut, periode_fin):
    from employer.models import Presence
    qs = Presence.objects.filter(
        date__range=[periode_debut, periode_fin]
    ).select_related('employe').order_by('date')
    columns = ['Employé', 'Date', 'Arrivée matin', 'Départ matin', 'Arrivée soir', 'Départ soir',
               'Présent', 'Durée totale (min)']
    rows = [[
        str(p.employe), p.date.strftime('%d/%m/%Y'),
        p.heure_arrivee_matin.strftime('%H:%M') if p.heure_arrivee_matin else '—',
        p.heure_depart_matin.strftime('%H:%M') if p.heure_depart_matin else '—',
        p.heure_arrivee_soir.strftime('%H:%M') if p.heure_arrivee_soir else '—',
        p.heure_depart_soir.strftime('%H:%M') if p.heure_depart_soir else '—',
        'Oui' if p.present else 'Non', p.duree_totale if p.duree_totale is not None else '—',
    ] for p in qs]
    return columns, rows


REPORT_CATALOGUE = [
    {
        'nom': 'Patients',
        'icone': 'bi-people-fill',
        'rapports': [
            {'slug': 'patients_inscrits', 'nom': 'Patients inscrits', 'icone': 'bi-person-plus-fill',
             'description': 'Liste des patients enregistrés sur la période.', 'fn': _patients_inscrits},
            {'slug': 'rendez_vous_medecine', 'nom': 'Rendez-vous (Médecine)', 'icone': 'bi-calendar-check-fill',
             'description': 'Rendez-vous de médecine générale planifiés sur la période (hors gynécologie).',
             'fn': _rendez_vous_medecine},
            {'slug': 'rendez_vous_gynecologie', 'nom': 'Rendez-vous (Gynécologie)', 'icone': 'bi-calendar-heart-fill',
             'description': 'Rendez-vous de gynécologie planifiés sur la période.', 'fn': _rendez_vous_gynecologie},
        ],
    },
    {
        'nom': 'Consultations & soins',
        'icone': 'bi-clipboard2-pulse-fill',
        'rapports': [
            {'slug': 'consultations', 'nom': 'Consultations', 'icone': 'bi-clipboard2-pulse',
             'description': 'Consultations réalisées sur la période.', 'fn': _consultations},
            {'slug': 'soins_dispenses', 'nom': 'Soins dispensés', 'icone': 'bi-bandaid-fill',
             'description': 'Soins infirmiers dispensés sur la période.', 'fn': _soins_dispenses},
            {'slug': 'ordonnances', 'nom': 'Ordonnances', 'icone': 'bi-file-earmark-medical-fill',
             'description': 'Ordonnances prescrites sur la période.', 'fn': _ordonnances},
            {'slug': 'hospitalisations', 'nom': 'Hospitalisations', 'icone': 'bi-hospital-fill',
             'description': "Admissions d'hospitalisation sur la période.", 'fn': _hospitalisations},
            {'slug': 'deces', 'nom': 'Registre des décès', 'icone': 'bi-journal-x',
             'description': 'Décès enregistrés sur la période.', 'fn': _deces},
        ],
    },
    {
        'nom': 'Laboratoire',
        'icone': 'bi-droplet-half',
        'rapports': [
            {'slug': 'analyses_laboratoire', 'nom': 'Analyses de laboratoire', 'icone': 'bi-droplet-half',
             'description': 'Analyses prélevées sur la période.', 'fn': _analyses_laboratoire},
        ],
    },
    {
        'nom': 'Facturation & Caisse',
        'icone': 'bi-cash-coin',
        'rapports': [
            {'slug': 'factures', 'nom': 'Factures', 'icone': 'bi-receipt',
             'description': 'Factures émises sur la période.', 'fn': _factures},
            {'slug': 'paiements', 'nom': 'Paiements', 'icone': 'bi-credit-card-fill',
             'description': 'Paiements encaissés sur la période.', 'fn': _paiements},
            {'slug': 'transactions_caisse', 'nom': 'Transactions de caisse', 'icone': 'bi-cash-stack',
             'description': 'Encaissements/décaissements de caisse sur la période.', 'fn': _transactions_caisse},
        ],
    },
    {
        'nom': 'Pharmacie',
        'icone': 'bi-capsule',
        'rapports': [
            {'slug': 'mouvements_stock_pharmacie', 'nom': 'Mouvements de stock', 'icone': 'bi-arrow-left-right',
             'description': 'Entrées/sorties de médicaments sur la période.', 'fn': _mouvements_stock_pharmacie},
        ],
    },
    {
        'nom': 'Ressources humaines',
        'icone': 'bi-people',
        'rapports': [
            {'slug': 'employes_embauches', 'nom': 'Employés embauchés', 'icone': 'bi-person-badge-fill',
             'description': "Employés dont la date d'embauche tombe dans la période.", 'fn': _employes_embauches},
            {'slug': 'conges', 'nom': 'Congés', 'icone': 'bi-airplane-fill',
             'description': 'Congés démarrant sur la période.', 'fn': _conges},
            {'slug': 'presences', 'nom': 'Présences', 'icone': 'bi-calendar2-check-fill',
             'description': 'Registre de présence journalier sur la période.', 'fn': _presences},
        ],
    },
]

def resolve_external_reports():
    """Résout les URLs des rapports externes (calcul fait ici plutôt qu'au
    template, car {% url %} ne sait pas dérouler une liste d'arguments)."""
    from django.urls import reverse
    resolved = []
    for categorie in EXTERNAL_REPORTS:
        rapports = []
        for rapport in categorie['rapports']:
            rapports.append({
                'nom': rapport['nom'],
                'url': reverse(rapport['url_name'], args=rapport.get('url_args', [])),
            })
        resolved.append({'nom': categorie['nom'], 'icone': categorie['icone'], 'rapports': rapports})
    return resolved


REPORTS_BY_SLUG = {
    rapport['slug']: {**rapport, 'categorie': categorie['nom']}
    for categorie in REPORT_CATALOGUE
    for rapport in categorie['rapports']
}


# ── Rapports existants ailleurs dans l'application ──
# On ne les déplace pas : ce sont de simples liens vers les pages déjà en place.
EXTERNAL_REPORTS = [
    {
        'nom': 'Pharmacie',
        'icone': 'bi-capsule',
        'rapports': [
            {'nom': 'Rapport du jour — Walé Toumbokro', 'url_name': 'pharmacie_rapport_journalier',
             'url_args': ['wale_toumbokro']},
            {'nom': 'Rapport du jour — Walé Yamoussoukro', 'url_name': 'pharmacie_rapport_journalier',
             'url_args': ['wale_yamoussoukro']},
            {'nom': 'Rapport mensuel — Walé Toumbokro', 'url_name': 'pharmacie_rapport_mensuel',
             'url_args': ['wale_toumbokro']},
            {'nom': 'Rapport mensuel — Walé Yamoussoukro', 'url_name': 'pharmacie_rapport_mensuel',
             'url_args': ['wale_yamoussoukro']},
            {'nom': 'Dispensations — Walé Toumbokro', 'url_name': 'pharmacie_rapport_dispensation',
             'url_args': ['wale_toumbokro']},
            {'nom': 'Dispensations — Walé Yamoussoukro', 'url_name': 'pharmacie_rapport_dispensation',
             'url_args': ['wale_yamoussoukro']},
        ],
    },
    {
        'nom': 'Stock (magasin)',
        'icone': 'bi-box-seam-fill',
        'rapports': [
            {'nom': 'Consommation', 'url_name': 'stock_rapports_consommation'},
            {'nom': 'Dotations', 'url_name': 'stock_rapports_dotations'},
            {'nom': 'Besoins', 'url_name': 'stock_rapports_besoins'},
            {'nom': 'Indicateurs', 'url_name': 'stock_rapports_indicateurs'},
            {'nom': 'Péremptions', 'url_name': 'stock_rapports_peremptions'},
            {'nom': 'Bilan mensuel', 'url_name': 'stock_rapports_bilan'},
            {'nom': 'Prix fournisseurs', 'url_name': 'stock_rapports_fournisseurs_prix'},
        ],
    },
    {
        'nom': 'Ressources humaines',
        'icone': 'bi-people',
        'rapports': [
            {'nom': 'Congés', 'url_name': 'conge_rapport'},
            {'nom': 'Présence (quotidien)', 'url_name': 'presence_rapport'},
            {'nom': 'Présence (mensuel)', 'url_name': 'rh_presence_rapport'},
        ],
    },
]
