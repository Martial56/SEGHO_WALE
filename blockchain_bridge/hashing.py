"""Empreintes (hash SHA-256) canoniques des enregistrements ancrés sur la
blockchain. Seule l'empreinte quitte Django — jamais les champs eux-mêmes
(voir blockchain/README.md)."""

import hashlib
import json


def _empreinte(data):
    canonique = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonique.encode('utf-8')).hexdigest()


def empreinte_patient(patient):
    return _empreinte({
        'code_patient': patient.code_patient,
        'nom': patient.nom,
        'prenoms': patient.prenoms,
        'date_naissance': patient.date_naissance,
        'sexe': patient.sexe,
        'groupe_sanguin': patient.groupe_sanguin,
        'allergies': patient.allergies,
        'antecedents': patient.antecedents,
    })


def _libelle_ligne_ordonnance(ligne):
    if ligne.medicament_id:
        return str(ligne.medicament)
    if ligne.produit_id:
        return str(ligne.produit)
    return ligne.medicament_libre


def empreinte_ordonnance(ordonnance):
    patient = ordonnance.patient_effectif
    return _empreinte({
        'numero': ordonnance.numero,
        'patient': patient.code_patient if patient else '',
        'type_ordonnance': ordonnance.type_ordonnance,
        'lignes': [
            {
                'medicament': _libelle_ligne_ordonnance(ligne),
                'posologie': ligne.posologie,
                'duree': ligne.duree,
                'quantite': ligne.quantite,
            }
            for ligne in ordonnance.lignes.all().order_by('pk')
        ],
    })


def empreinte_consultation(consultation):
    constantes = {}
    if hasattr(consultation, 'constantes'):
        c = consultation.constantes
        constantes = {
            'poids': c.poids,
            'taille': c.taille,
            'temperature': c.temperature,
            'tension_systolique': c.tension_systolique,
            'tension_diastolique': c.tension_diastolique,
            'pouls': c.pouls,
            'frequence_respiratoire': c.frequence_respiratoire,
            'saturation_oxygene': c.saturation_oxygene,
        }
    return _empreinte({
        'numero': consultation.numero,
        'patient': consultation.patient.code_patient,
        'motif': consultation.motif,
        'anamnese': consultation.anamnese,
        'statut': consultation.statut,
        'constantes': constantes,
        'diagnostics': [
            {
                'type': d.type_diagnostic,
                'cim': d.cim.code if d.cim_id else '',
                'libelle_libre': d.libelle_libre,
                'notes': d.notes,
            }
            for d in consultation.diagnostics.all().order_by('pk')
        ],
        'ordonnances': [
            {
                'numero': o.numero,
                'lignes': [
                    {
                        'medicament': _libelle_ligne_ordonnance(ligne),
                        'posologie': ligne.posologie,
                        'duree': ligne.duree,
                        'quantite': ligne.quantite,
                    }
                    for ligne in o.lignes.all().order_by('pk')
                ],
            }
            for o in consultation.ordonnances.all().order_by('pk')
        ],
    })


def empreinte_facture(facture):
    return _empreinte({
        'numero': facture.numero,
        'patient': facture.patient.code_patient,
        'type_facture': facture.type_facture,
        'statut': facture.statut,
        'montant_total': str(facture.montant_total),
        'montant_assurance': str(facture.montant_assurance),
        'montant_paye': str(facture.montant_paye),
        'lignes': [
            {
                'libelle': ligne.libelle,
                'quantite': str(ligne.quantite),
                'prix_unitaire': str(ligne.prix_unitaire),
                'remise': str(ligne.remise),
            }
            for ligne in facture.lignes.all().order_by('pk')
        ],
    })


def empreinte_paiement(paiement):
    return _empreinte({
        'numero': paiement.numero,
        'facture': paiement.facture.numero,
        'montant': str(paiement.montant),
        'mode_paiement': paiement.mode_paiement,
        'reference': paiement.reference,
    })


def empreinte_echange_hprim(echange):
    """Empreinte du message HPRIM échangé (§ ORM/ORU/ERR) tel que transmis à
    ou reçu du système externe (laboratoire) — c'est le contenu qui a
    réellement franchi la frontière inter-systèmes, avant toute
    interprétation côté SEGHO (voir laboratoire/hprim/)."""
    return _empreinte({
        'sens': echange.sens,
        'contexte': echange.contexte,
        'nom_fichier': echange.nom_fichier,
        'contenu': echange.contenu,
    })


def empreinte_analyse_laboratoire(analyse):
    return _empreinte({
        'numero': analyse.numero,
        'patient': analyse.patient.code_patient,
        'type_examen': analyse.type_examen.code if analyse.type_examen_id else '',
        'statut': analyse.statut,
        'resultats': [
            {
                'parametre': r.parametre,
                'valeur': r.valeur,
                'unite': r.unite,
                'valeur_normale_min': r.valeur_normale_min,
                'valeur_normale_max': r.valeur_normale_max,
                'interpretation': r.interpretation,
            }
            for r in analyse.resultats.all().order_by('pk')
        ],
    })


# Association type_entite -> (app_label, nom_du_modele, champ de recherche,
# fonction d'empreinte) : utilisée pour recalculer une empreinte à partir de
# l'état courant de la base lors d'une vérification d'intégrité (voir
# services.verifier_integrite), sans dépendre du hash déjà stocké côté
# AncrageBlockchain.
ENTITES = {
    'patient': ('patients', 'Patient', 'code_patient', empreinte_patient),
    'consultation': ('consultations', 'Consultation', 'numero', empreinte_consultation),
    'ordonnance': ('consultations', 'Ordonnance', 'numero', empreinte_ordonnance),
    'facture': ('facturation', 'Facture', 'numero', empreinte_facture),
    'paiement': ('facturation', 'Paiement', 'numero', empreinte_paiement),
    'echange_hprim': ('laboratoire', 'EchangeHPRIM', 'pk', empreinte_echange_hprim),
    'analyse_laboratoire': ('laboratoire', 'AnalyseLaboratoire', 'numero', empreinte_analyse_laboratoire),
}


def recalculer_empreinte(type_entite, id_entite):
    """Recalcule l'empreinte d'une entité à partir de l'état courant de la
    base. Renvoie None si le type est inconnu ou si l'entité a été supprimée
    depuis son ancrage."""
    from django.apps import apps

    config = ENTITES.get(type_entite)
    if config is None:
        return None
    app_label, model_name, lookup_field, hash_fn = config
    model = apps.get_model(app_label, model_name)
    # `all_objects` (voir centres.models.ModeleCentre) pour ne pas dépendre du
    # centre actif de la requête admin en cours : une vérification d'intégrité
    # doit pouvoir retrouver l'entité quel que soit le centre qui l'a créée.
    manager = getattr(model, 'all_objects', model.objects)
    try:
        instance = manager.get(**{lookup_field: id_entite})
    except model.DoesNotExist:
        return None
    return hash_fn(instance)
