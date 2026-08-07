# -*- coding: utf-8 -*-
"""
Service haut niveau : orchestre la construction, l'envoi FTP et la réception
des messages HPRIM, en journalisant chaque échange (EchangeHPRIM).
"""

from __future__ import annotations
from django.utils import timezone

from . import transport
from .core import detect_contexte
from .integration import construire_orm, integrer_oru, integrer_err


def envoyer_demande(demande):
    """
    Construit et envoie une DemandeExamen au laboratoire (ORM) par FTP.
    Journalise l'opération. Retourne l'EchangeHPRIM créé.
    Lève une exception si la configuration FTP est absente pour le centre de
    la demande.
    """
    from laboratoire.models import ConfigurationHPRIM, EchangeHPRIM

    config = ConfigurationHPRIM.active(demande.centre)
    if config is None:
        raise RuntimeError("Aucune configuration HPRIM active pour ce centre. "
                           "Créez-en une dans l'admin (Laboratoire > "
                           "Configurations HPRIM).")

    # Numéro d'ordre = nombre d'envois déjà journalisés pour ce centre + 1
    numero_ordre = EchangeHPRIM.all_objects.filter(sens="envoi", centre=demande.centre).count() + 1
    nom, contenu, _msg = construire_orm(demande, config, numero_ordre)

    echange = EchangeHPRIM.objects.create(
        sens="envoi", contexte="ORM", nom_fichier=nom,
        demande=demande, contenu=contenu, statut="en_attente",
        centre=demande.centre,
    )

    if not config.ftp_host:
        echange.statut = "erreur"
        echange.message_log = ("Fichier généré mais FTP non configuré "
                               "(ftp_host vide). Message non transmis.")
        echange.save(update_fields=["statut", "message_log"])
        return echange

    try:
        transport.envoyer_fichier(
            contenu=contenu.encode("iso-8859-1", errors="replace"),
            nom_fichier=nom,
            host=config.ftp_host, port=config.ftp_port,
            user=config.ftp_user, password=config.ftp_password,
            repertoire_distant=config.repertoire_envoi,
            extension_temoin=config.extension_temoin,
            use_tls=config.ftp_tls,
        )
        echange.statut = "transmis"
        echange.date_traitement = timezone.now()
        echange.message_log = "Demande transmise par FTP."
        # mettre à jour la demande métier
        if demande.statut in ("brouillon", "demande"):
            demande.statut = "demande"
            demande.save(update_fields=["statut"])
    except Exception as exc:   # noqa: BLE001 - on journalise toute erreur réseau
        echange.statut = "erreur"
        echange.message_log = f"Échec de l'envoi FTP : {exc}"
    echange.save()
    return echange


def relever_resultats():
    """
    Relève les fichiers de résultats (ORU) déposés par le laboratoire,
    les intègre et journalise. Retourne la liste des EchangeHPRIM créés.

    Appelée hors requête (cron / management command) : il n'y a donc pas de
    centre actif ambiant. On résout la config HPRIM active sans filtre de
    centre (aujourd'hui, un seul centre — WALE Yakro — en possède une), puis
    on route tout ce qui est créé pendant la relève vers le centre
    propriétaire de cette config via le gestionnaire de contexte centre_actif.
    """
    from laboratoire.models import ConfigurationHPRIM, EchangeHPRIM
    from core.middleware import centre_actif

    config = ConfigurationHPRIM.all_objects.filter(actif=True).order_by('-date_modification').first()
    if config is None:
        raise RuntimeError("Aucune configuration HPRIM active.")

    if not config.ftp_host:
        raise RuntimeError("FTP non configuré (ftp_host vide).")

    with centre_actif(config.centre):
        fichiers = transport.recuperer_fichiers(
            host=config.ftp_host, port=config.ftp_port,
            user=config.ftp_user, password=config.ftp_password,
            repertoire_distant=config.repertoire_reception or config.repertoire_envoi,
            extension_temoin=config.extension_temoin,
            use_tls=config.ftp_tls,
            supprimer_apres=True,
        )

        echanges = []
        for nom, contenu in fichiers:
            contexte = detect_contexte(contenu) or "ORU"
            echange = EchangeHPRIM.objects.create(
                sens="reception", contexte=contexte, nom_fichier=nom,
                contenu=contenu.decode("iso-8859-1", errors="replace"),
                statut="recu", centre=config.centre,
            )
            try:
                if contexte == "ERR":
                    _parsed, synthese = integrer_err(contenu, echange)
                    echange.statut = "traite"
                    echange.date_traitement = timezone.now()
                    gravite = "REJET TOTAL" if synthese["rejet_total"] else "signalement(s)"
                    echange.message_log = (
                        f"{synthese['erreurs']} erreur(s) — {gravite}."
                    )
                    if synthese["details"]:
                        echange.message_log += "\n" + "\n".join(synthese["details"])
                else:
                    _parsed, synthese = integrer_oru(contenu)
                    echange.statut = "traite"
                    echange.date_traitement = timezone.now()
                    echange.message_log = (
                        f"{synthese['patients']} patient(s), "
                        f"{synthese['demandes']} demande(s), "
                        f"{synthese['resultats']} résultat(s) intégré(s)."
                    )
                    if synthese["details"]:
                        echange.message_log += "\n" + "\n".join(synthese["details"])
            except Exception as exc:   # noqa: BLE001
                echange.statut = "erreur"
                echange.message_log = f"Échec d'intégration : {exc}"
            echange.save()
            echanges.append(echange)
        return echanges
