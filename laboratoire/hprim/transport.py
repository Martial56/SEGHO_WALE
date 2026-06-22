# -*- coding: utf-8 -*-
"""Transport FTP des messages HPRIM (§6.3) avec fichier témoin .ok."""

from __future__ import annotations
import io
import os
import ssl
from ftplib import FTP, FTP_TLS, error_perm
from typing import List, Tuple


def _ssl_context() -> ssl.SSLContext:
    """Contexte SSL permissif pour FTPS :
    - sans vérification de certificat (auto-signé courant en intranet de labo)
    - compatible Python 3.10+ avec les serveurs qui ferment la connexion TLS
      sans envoyer le close_notify requis (EOF inattendu)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    # Python 3.11.3+ : supprime l'erreur SSL sur EOF non signalé
    if hasattr(ssl, 'OP_IGNORE_UNEXPECTED_EOF'):
        ctx.options |= ssl.OP_IGNORE_UNEXPECTED_EOF
    return ctx


class _FtpTls(FTP_TLS):
    """FTP_TLS compatible Python 3.10+ avec deux correctifs :
    - ntransfercmd : résume la session TLS du canal de contrôle sur le canal
      de données (corrige l'erreur 425 « TLS session not resumed »)
    - storbinary/retrbinary : rattrape les SSLEOFError des serveurs qui ferment
      la connexion sans envoyer le TLS close_notify."""

    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,  # reprise de la session TLS du canal de contrôle
            )
        return conn, size

    def storbinary(self, cmd, fp, blocksize=8192, callback=None, rest=None):
        try:
            return super().storbinary(cmd, fp, blocksize, callback, rest)
        except ssl.SSLEOFError:
            pass  # EOF sans close_notify = fin de transfert normale sur ces serveurs

    def retrbinary(self, cmd, callback, blocksize=8192, rest=None):
        try:
            return super().retrbinary(cmd, callback, blocksize, rest)
        except ssl.SSLEOFError:
            pass


def _connecter_ftp(host: str, port: int, user: str, password: str,
                   use_tls: bool, timeout: int):
    """Ouvre la connexion FTP. Si le serveur exige TLS (503) et que use_tls
    est False, retente automatiquement avec FTPS explicite."""
    if use_tls:
        ftp = _FtpTls(context=_ssl_context(), timeout=timeout)
        ftp.connect(host, port)
        ftp.login(user, password)
        ftp.prot_p()
        return ftp

    ftp = FTP(timeout=timeout)
    ftp.connect(host, port)
    try:
        ftp.login(user, password)
    except error_perm as exc:
        if "503" in str(exc):
            ftp.close()
            ftp = _FtpTls(context=_ssl_context(), timeout=timeout)
            ftp.connect(host, port)
            ftp.login(user, password)
            ftp.prot_p()
        else:
            raise
    return ftp


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

    ftp = _connecter_ftp(host, port, user, password, use_tls, timeout)
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
    ftp = _connecter_ftp(host, port, user, password, use_tls, timeout)

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
    # Normalise les antislashs Windows en slashes Unix
    chemin = chemin.replace("\\", "/")
    # Pour un chemin absolu, se positionner à la racine FTP d'abord
    if chemin.startswith("/"):
        try:
            ftp.cwd("/")
        except error_perm:
            pass
    for partie in chemin.strip("/").split("/"):
        if not partie:
            continue
        try:
            ftp.cwd(partie)
        except error_perm:
            try:
                ftp.mkd(partie)
            except error_perm:
                pass  # Répertoire déjà existant
            ftp.cwd(partie)


def _supprimer_silencieux(ftp, nom: str) -> None:
    try:
        ftp.delete(nom)
    except error_perm:
        pass
