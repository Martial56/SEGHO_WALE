# -*- coding: utf-8 -*-
"""Transport FTP des messages HPRIM (§6.3) avec fichier témoin .ok."""

from __future__ import annotations
import io
import os
from ftplib import FTP, FTP_TLS, error_perm
from typing import List, Tuple


def envoyer_fichier(
    contenu: bytes,
    nom_fichier: str,
    host: str,
    user: str,
    password: str,
    port: int = 21,
    repertoire_distant: str = "",
    extension_temoin: str = ".ok",
    use_tls: bool = False,
    timeout: int = 10,
) -> None:
    """Dépose <nom>.HPR puis le témoin <nom>.ok (déposé APRÈS, §6.3)."""
    base = os.path.splitext(nom_fichier)[0]
    nom_temoin = base + extension_temoin

    ftp = (FTP_TLS if use_tls else FTP)(timeout=timeout)
    ftp.connect(host, port)
    ftp.login(user, password)
    if use_tls:
        ftp.prot_p()
    try:
        if repertoire_distant:
            _cd_ou_creer(ftp, repertoire_distant)
        ftp.storbinary(f"STOR {nom_fichier}", io.BytesIO(contenu))
        ftp.storbinary(f"STOR {nom_temoin}", io.BytesIO(b""))
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


def recuperer_fichiers(
    host: str,
    user: str,
    password: str,
    port: int = 21,
    repertoire_distant: str = "",
    extension: str = ".HPR",
    extension_temoin: str = ".ok",
    supprimer_apres: bool = True,
    use_tls: bool = False,
    timeout: int = 30,
) -> List[Tuple[str, bytes]]:
    """
    Récupère les fichiers de résultats présents (ne traite que ceux dont le
    fichier témoin .ok existe), retourne [(nom_fichier, contenu)], et les
    supprime ensuite si demandé.
    """
    ftp = (FTP_TLS if use_tls else FTP)(timeout=timeout)
    ftp.connect(host, port)
    ftp.login(user, password)
    if use_tls:
        ftp.prot_p()

    resultats: List[Tuple[str, bytes]] = []
    try:
        if repertoire_distant:
            _cd_ou_creer(ftp, repertoire_distant)

        noms = ftp.nlst()
        bases_pretes = {
            os.path.splitext(n)[0]
            for n in noms
            if n.lower().endswith(extension_temoin.lower())
        }

        for nom in noms:
            base, ext = os.path.splitext(nom)
            if ext.lower() != extension.lower():
                continue
            if base not in bases_pretes:
                continue  # pas encore de témoin -> message incomplet
            buf = io.BytesIO()
            ftp.retrbinary(f"RETR {nom}", buf.write)
            resultats.append((nom, buf.getvalue()))
            if supprimer_apres:
                _supprimer_silencieux(ftp, nom)
                _supprimer_silencieux(ftp, base + extension_temoin)
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()
    return resultats


def _cd_ou_creer(ftp, chemin: str) -> None:
    for partie in chemin.strip("/").split("/"):
        if not partie:
            continue
        try:
            ftp.cwd(partie)
        except error_perm:
            ftp.mkd(partie)
            ftp.cwd(partie)


def _supprimer_silencieux(ftp, nom: str) -> None:
    try:
        ftp.delete(nom)
    except error_perm:
        pass
