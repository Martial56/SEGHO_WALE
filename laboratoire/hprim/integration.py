# -*- coding: utf-8 -*-
"""
Pont entre les modèles Django (laboratoire / patients) et le moteur HPRIM.

Deux flux :
  - construire_orm(demande) : transforme une DemandeExamen en message ORM.
  - integrer_oru(contenu)   : lit un message ORU reçu et crée les
                              AnalyseLaboratoire / ResultatAnalyse associés.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from django.utils import timezone

from .core import (
    HprimMessage, Entite, PatientData, AnalyseData, DemandeData,
    nom_fichier_hprim, parse_message, parse_err,
)


# --------------------------------------------------------------------------- #
# Helpers de conversion
# --------------------------------------------------------------------------- #
def _aware_to_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """HPRIM véhicule des dates locales sans fuseau ; on convertit en heure
    locale naïve à partir d'un datetime aware Django."""
    if dt is None:
        return None
    if timezone.is_aware(dt):
        return timezone.localtime(dt).replace(tzinfo=None)
    return dt


def _patient_data(patient, rang: int = 1) -> PatientData:
    naissance = patient.date_naissance
    dt_naissance = datetime(naissance.year, naissance.month, naissance.day) \
        if naissance else None
    return PatientData(
        rang=rang,
        id_demandeur=patient.code_patient,
        nom=patient.nom,
        prenom=patient.prenoms,
        date_naissance=dt_naissance,
        sexe=patient.sexe or "U",     # M / F déjà conformes ; sinon U
        telephone=patient.telephone or "",
    )


def _analyses_de_demande(demande):
    """Construit la liste des AnalyseData à partir des lignes de la demande."""
    analyses = []
    for ligne in demande.lignes.all():
        te = ligne.type_examen
        if te is not None:
            analyses.append(AnalyseData(code=te.code,
                                        libelle=te.nom or ligne.libelle, table="L"))
        else:
            # ligne libre : pas de code -> libellé seul (autorisé en ORA/ORM)
            analyses.append(AnalyseData(code="", libelle=ligne.libelle, table="L"))
    if not analyses:
        # repli : utiliser le type_test global
        analyses.append(AnalyseData(code=demande.type_test or "",
                                    libelle=demande.get_type_test_display()
                                    if demande.type_test else "Examen", table="L"))
    return analyses


# --------------------------------------------------------------------------- #
# Flux sortant : DemandeExamen -> message ORM
# --------------------------------------------------------------------------- #
def construire_orm(demande, config, numero_ordre: int):
    """
    Retourne (nom_fichier, contenu_str, message). 'config' est une
    ConfigurationHPRIM ; 'numero_ordre' alimente le nom de fichier.
    """
    nom = nom_fichier_hprim(config.prefixe_fichier, numero_ordre)

    msg = HprimMessage(
        contexte="ORM",
        emetteur=Entite(config.emetteur_code, config.emetteur_nom),
        recepteur=Entite(config.recepteur_code, config.recepteur_nom),
        type_liaison=config.type_liaison,
        nom_fichier=nom,
        date_message=_aware_to_naive(timezone.now()),
    )

    patient_data = _patient_data(demande.patient, rang=1)

    demande_data = DemandeData(
        rang=1,
        id_demande=demande.numero,            # 9.3.2 : n° demande SEGHO (clé de retour)
        analyses=_analyses_de_demande(demande),
        code_action="N",                       # nouvelle demande
        date_prelevement=_aware_to_naive(demande.date_prelevement),
        renseignements_cliniques=(demande.commentaire or "")[:300],
    )

    msg.ajouter_patient(patient_data, [demande_data])
    return nom, msg.render(), msg


# --------------------------------------------------------------------------- #
# Flux entrant : message ORU -> AnalyseLaboratoire + ResultatAnalyse
# --------------------------------------------------------------------------- #
_ANORMALITE_MAP = {
    "H": "eleve", "HH": "critique",
    "L": "bas", "LL": "critique",
    "N": "normal", "A": "eleve", "AA": "critique",
}


def integrer_oru(contenu: bytes):
    """
    Analyse un message ORU et crée/complète les enregistrements de résultats.
    Retourne un dict de synthèse {patients, demandes, resultats, details}.

    Le rapprochement se fait via :
      - 9.3.2 (id_demande) <-> DemandeExamen.numero
      - 8.3   (id_demandeur) <-> Patient.code_patient
    """
    # Imports locaux pour éviter les imports circulaires au chargement du module
    from laboratoire.models import (
        AnalyseLaboratoire, ResultatAnalyse, DemandeExamen, TypeExamen,
    )
    from patients.models import Patient

    parsed = parse_message(contenu)
    synthese = {"patients": 0, "demandes": 0, "resultats": 0, "details": []}

    for p in parsed.patients:
        patient_obj = Patient.objects.filter(code_patient=p.id_demandeur).first()
        if patient_obj is None and (p.nom or p.prenom):
            patient_obj = Patient.objects.filter(
                nom__iexact=p.nom, prenoms__iexact=p.prenom).first()
        synthese["patients"] += 1

        for d in p.demandes:
            demande_obj = DemandeExamen.objects.filter(numero=d.id_demande).first()
            if patient_obj is None and demande_obj is not None:
                patient_obj = demande_obj.patient

            if patient_obj is None:
                synthese["details"].append(
                    f"Demande {d.id_demande} ignorée : patient introuvable "
                    f"(IPP={p.id_demandeur}).")
                continue

            # Un OBR ORU -> une AnalyseLaboratoire (regroupe ses OBX)
            type_examen = None
            if demande_obj is not None:
                premiere_ligne = demande_obj.lignes.first()
                if premiere_ligne:
                    type_examen = premiere_ligne.type_examen

            analyse = AnalyseLaboratoire(
                patient=patient_obj,
                type_examen=type_examen,
                statut="valide" if (d.statut or "F").upper() == "F" else "resultat",
                date_resultat=parsed.date_message or timezone.now(),
                commentaire=f"Importé HPRIM (fichier {parsed.nom_fichier}, "
                            f"demande {d.id_demande}).",
            )
            analyse.save()
            synthese["demandes"] += 1

            for r in d.resultats:
                vmin = vmax = ""
                if r.normales and "-" in r.normales:
                    gauche, droite = r.normales.split("-", 1)
                    vmin, vmax = gauche.strip(), droite.strip()
                ResultatAnalyse.objects.create(
                    analyse=analyse,
                    parametre=(r.libelle_test or r.code_test)[:200],
                    valeur=(r.valeur or "")[:200],
                    unite=(r.unite or "")[:50],
                    valeur_normale_min=vmin[:100],
                    valeur_normale_max=vmax[:100],
                    interpretation=_ANORMALITE_MAP.get(
                        (r.anormalite or "").split("^")[0], ""),
                )
                synthese["resultats"] += 1

            # Avancer le statut de la demande d'origine
            if demande_obj is not None and (d.statut or "F").upper() == "F":
                demande_obj.statut = "termine"
                demande_obj.save(update_fields=["statut"])

    return parsed, synthese


# --------------------------------------------------------------------------- #
# Flux entrant : message ERR -> ErreurHPRIM (journalisation des rejets)
# --------------------------------------------------------------------------- #
def integrer_err(contenu: bytes, echange):
    """
    Analyse un message ERR reçu et crée les ErreurHPRIM rattachées.
    'echange' est l'EchangeHPRIM dans lequel le fichier a été journalisé.

    Rapprochement avec la demande d'origine :
      - via le nom de fichier erroné (25.3) <-> EchangeHPRIM.nom_fichier d'un
        envoi précédent, dont on récupère la DemandeExamen ;
      - à défaut, via les identifiants présents dans l'adresse du segment (25.7).

    Retourne (parsed, synthese) où synthese = {erreurs, rejet_total, details}.
    """
    from laboratoire.models import ErreurHPRIM, EchangeHPRIM, DemandeExamen

    parsed = parse_err(contenu)
    synthese = {"erreurs": 0, "rejet_total": parsed.rejet_total, "details": []}

    # Tenter de retrouver la demande d'origine via le fichier envoyé
    demande_origine = None
    if parsed.nom_fichier_errone:
        envoi = (EchangeHPRIM.objects
                 .filter(sens="envoi", nom_fichier=parsed.nom_fichier_errone)
                 .order_by("-date_creation").first())
        if envoi is not None:
            demande_origine = envoi.demande

    for e in parsed.erreurs:
        demande = demande_origine
        # Repli : chercher un numéro de demande dans l'adresse du segment (25.7)
        if demande is None and e.adresse_segment:
            for jeton in e.adresse_segment.replace("~", "&").split("&"):
                jeton = jeton.strip()
                if jeton.startswith("DEM"):
                    demande = DemandeExamen.objects.filter(numero=jeton).first()
                    if demande:
                        break

        ErreurHPRIM.objects.create(
            echange=echange,
            demande=demande,
            nom_fichier_errone=parsed.nom_fichier_errone[:20],
            gravite=e.gravite,
            type_erreur=e.type_erreur,
            numero_ligne=e.numero_ligne[:10],
            adresse_segment=e.adresse_segment[:200],
            donnee_erronee=e.donnee_erronee[:50],
            valeur_erronee=e.valeur_erronee,
            designation=e.designation,
        )
        synthese["erreurs"] += 1

        # Si rejet total et demande identifiée : remettre la demande en
        # "brouillon" pour correction/réémission, et le tracer.
        if e.gravite == "T" and demande is not None:
            demande.statut = "brouillon"
            demande.save(update_fields=["statut"])
            synthese["details"].append(
                f"Demande {demande.numero} rejetée (total) : {e.designation}")

    return parsed, synthese
