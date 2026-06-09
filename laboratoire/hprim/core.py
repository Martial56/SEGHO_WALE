# -*- coding: utf-8 -*-
"""
Génération et lecture de messages HPRIM Santé v2.4 (norme ASTM E1238).

Module sans dépendance Django : il manipule des chaînes/dataclasses, ce qui le
rend testable isolément. Les ponts vers les modèles Django sont dans
`integration.py`.

Contextes couverts :
  - ORM : transfert de demandes d'analyses (SEGHO -> laboratoire)
  - ORU : transfert de résultats d'analyses (laboratoire -> SEGHO)

Conformité (cf. recommandation HPRIM 2.4) :
  - Segment H déclarant les 5 séparateurs (§7.2)
  - Encodage ISO-8859-1 / fins de segment CR+LF (§7.1, §5.1)
  - Champs vides transmis vides ; pas de délimiteurs après le dernier champ
    renseigné (§5.1)
  - Découpage en segments A au-delà de 220 caractères (§5.8)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence


# --------------------------------------------------------------------------- #
# Séparateurs (§7.2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Separators:
    field: str = "|"
    component: str = "~"
    repeat: str = "^"
    escape: str = "\\"
    subcomponent: str = "&"

    def header_token(self) -> str:
        return (self.field + self.component + self.repeat
                + self.escape + self.subcomponent)


SEGMENT_TERMINATOR = "\r\n"
ENCODING = "iso-8859-1"
MAX_SEGMENT_LEN = 220


# --------------------------------------------------------------------------- #
# Helpers d'assemblage
# --------------------------------------------------------------------------- #
def comp(*parts, sep: Separators) -> str:
    return sep.component.join("" if p is None else str(p) for p in parts)


def repeat(*values, sep: Separators) -> str:
    return sep.repeat.join("" if v is None else str(v) for v in values)


def fmt_ts(dt: Optional[datetime], with_time: bool = True) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y%m%d%H%M" if with_time else "%Y%m%d")


def parse_ts(value: str) -> Optional[datetime]:
    value = (value or "").strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(value[: len(fmt.replace("%", "")) + 4], fmt)
        except (ValueError, TypeError):
            continue
    # tentative tolérante
    for length, fmt in ((12, "%Y%m%d%H%M"), (8, "%Y%m%d")):
        try:
            return datetime.strptime(value[:length], fmt)
        except (ValueError, TypeError):
            continue
    return None


# --------------------------------------------------------------------------- #
# Modèles de données métier
# --------------------------------------------------------------------------- #
@dataclass
class Entite:
    code: str
    nom: str


@dataclass
class PatientData:
    rang: int
    id_demandeur: str
    nom: str
    prenom: str = ""
    date_naissance: Optional[datetime] = None
    sexe: str = ""           # M / F / U
    telephone: str = ""
    dossier_admin: str = ""


@dataclass
class AnalyseData:
    code: str
    libelle: str = ""
    table: str = "L"


@dataclass
class ResultatData:
    rang: int
    type_resultat: str       # 10.3 : NM, CE, TX, ST...
    test: AnalyseData        # 10.4
    valeur: str              # 10.6
    unite: str = ""          # 10.7
    normales: str = ""       # 10.8
    anormalite: str = ""     # 10.9
    statut: str = ""         # 10.12


@dataclass
class DemandeData:
    rang: int
    id_demande: str
    analyses: Sequence[AnalyseData]
    code_action: str = "N"
    id_echantillon: str = ""
    date_prelevement: Optional[datetime] = None
    renseignements_cliniques: str = ""
    prescripteur: str = ""
    statut: str = ""
    resultats: List[ResultatData] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Construction d'un message
# --------------------------------------------------------------------------- #
class HprimMessage:
    def __init__(
        self,
        contexte: str,
        emetteur: Entite,
        recepteur: Entite,
        type_liaison: str = "L",
        nom_fichier: str = "",
        date_message: Optional[datetime] = None,
        separators: Optional[Separators] = None,
    ):
        contexte = contexte.upper()
        if contexte not in ("ORM", "ORU"):
            raise ValueError("Contexte supporté : ORM ou ORU")
        self.contexte = contexte
        self.emetteur = emetteur
        self.recepteur = recepteur
        self.type_liaison = type_liaison
        self.nom_fichier = nom_fichier
        self.date_message = date_message or datetime.now()
        self.sep = separators or Separators()
        self.patients: List[tuple] = []

    def ajouter_patient(self, patient: PatientData,
                        demandes: Sequence[DemandeData]) -> None:
        self.patients.append((patient, list(demandes)))

    # ---- segments --------------------------------------------------------- #
    def _seg_H(self) -> str:
        s = self.sep
        champs = [
            "H" + s.header_token(),
            self.nom_fichier,
            "",
            comp(self.emetteur.code, self.emetteur.nom, sep=s),
            "",
            self.contexte,
            "",
            "",
            comp(self.recepteur.code, self.recepteur.nom, sep=s),
            "",
            "",
            comp("H2.4", self.type_liaison, sep=s),
            fmt_ts(self.date_message),
        ]
        return _join_trim(champs, s.field)

    def _seg_P(self, p: PatientData) -> str:
        s = self.sep
        champs = [
            "P",
            str(p.rang),
            p.id_demandeur,
            "",
            p.dossier_admin,
            comp(p.nom, p.prenom, sep=s),
            "",
            fmt_ts(p.date_naissance, with_time=False),
            p.sexe,
            "",
            "",
            "",
            p.telephone,
        ]
        return _join_trim(champs, s.field)

    def _seg_OBR(self, d: DemandeData) -> str:
        s = self.sep
        analyses = repeat(
            *(comp(a.code, a.libelle, a.table, sep=s) for a in d.analyses),
            sep=s,
        )
        champs = [
            "OBR",
            str(d.rang),
            comp(d.id_echantillon, d.id_demande, sep=s),
            "",
            analyses,
            "",
            "",
            fmt_ts(d.date_prelevement),
            "",
            "",
            "",
            d.code_action if self.contexte == "ORM" else "",
            "",
            d.renseignements_cliniques,
            "",
            "",
            d.prescripteur,
        ]
        if self.contexte == "ORU":
            champs += ["", "", "", "", "", fmt_ts(self.date_message),
                       "", "", d.statut or "F"]
        return _join_trim(champs, s.field)

    def _seg_OBX(self, r: ResultatData) -> str:
        s = self.sep
        champs = [
            "OBX",
            str(r.rang),
            r.type_resultat,
            comp(r.test.code, r.test.libelle, r.test.table, sep=s),
            "",
            r.valeur,
            r.unite,
            r.normales,
            r.anormalite,
            "",
            "",
            r.statut,
        ]
        return _join_trim(champs, s.field)

    def _seg_L(self, nb_patients: int, nb_segments: int) -> str:
        s = self.sep
        champs = ["L", "1", "", str(nb_patients), str(nb_segments)]
        return _join_trim(champs, s.field)

    # ---- assemblage ------------------------------------------------------- #
    def build_segments(self) -> List[str]:
        segments = [self._seg_H()]
        for patient, demandes in self.patients:
            segments.append(self._seg_P(patient))
            for d in demandes:
                segments.append(self._seg_OBR(d))
                if self.contexte == "ORU":
                    for r in d.resultats:
                        segments.append(self._seg_OBX(r))
        nb_p = len(self.patients)
        segments.append(self._seg_L(nb_p, len(segments) + 1))
        return segments

    def render(self) -> str:
        out: List[str] = []
        for seg in self.build_segments():
            out.extend(_split_segment(seg, self.sep))
        return SEGMENT_TERMINATOR.join(out) + SEGMENT_TERMINATOR

    def to_bytes(self) -> bytes:
        return self.render().encode(ENCODING, errors="replace")


# --------------------------------------------------------------------------- #
# Lecture (parsing) d'un message ORU reçu
# --------------------------------------------------------------------------- #
@dataclass
class OruResultat:
    rang: str
    type_resultat: str
    code_test: str
    libelle_test: str
    valeur: str
    unite: str
    normales: str
    anormalite: str
    statut: str


@dataclass
class OruDemande:
    rang: str
    id_echantillon: str
    id_demande: str          # 9.3.2 : correspond au numéro de la demande SEGHO
    statut: str              # 9.26
    resultats: List[OruResultat] = field(default_factory=list)


@dataclass
class OruPatient:
    rang: str
    id_demandeur: str        # 8.3 : IPP transmis dans l'ORM
    nom: str
    prenom: str
    demandes: List[OruDemande] = field(default_factory=list)


@dataclass
class OruMessage:
    contexte: str
    emetteur_code: str
    emetteur_nom: str
    recepteur_code: str
    recepteur_nom: str
    nom_fichier: str
    date_message: Optional[datetime]
    patients: List[OruPatient] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lecture (parsing) d'un message ERR reçu (§5.14)
# --------------------------------------------------------------------------- #
# Table HPRIM 4 : statut/gravité de l'erreur
ERR_GRAVITE = {
    "T": "Rejet total du message",
    "P": "Rejet partiel du message",
    "I": "Pour information",
}
# Table HPRIM 6 : types d'erreurs
ERR_TYPE = {
    "A": "Champ obligatoire absent",
    "I": "Donnée inconnue ou incohérente",
    "S": "Erreur de syntaxe (structure du message)",
}


@dataclass
class ErrLigne:
    """Un segment ERR : une erreur signalée par le récepteur."""
    rang: str                # 25.2
    gravite: str             # 25.5 : T / P / I
    gravite_libelle: str     # libellé déduit (table HPRIM 4)
    numero_ligne: str        # 25.6 : n° de ligne du message erroné
    adresse_segment: str     # 25.7 : type~rang~identifiants du segment fautif
    donnee_erronee: str      # 25.8 : n° HPRIM du champ (ex. 22.3.1)
    valeur_erronee: str      # 25.9
    type_erreur: str         # 25.10 : A / I / S
    type_erreur_libelle: str # libellé déduit (table HPRIM 6)
    designation: str         # 25.11 : description en clair


@dataclass
class ErrMessage:
    contexte: str            # "ERR"
    emetteur_code: str
    emetteur_nom: str
    recepteur_code: str
    recepteur_nom: str
    nom_fichier: str         # 7.3 de CE message ERR
    date_message: Optional[datetime]
    # Champs identifiant le message d'origine (segment ERR) :
    nom_fichier_errone: str  # 25.3 : reprend le 7.3 du message en erreur
    date_reception: Optional[datetime]  # 25.4
    erreurs: List[ErrLigne] = field(default_factory=list)

    @property
    def rejet_total(self) -> bool:
        return any(e.gravite == "T" for e in self.erreurs)


def detect_contexte(raw: bytes) -> str:
    """Renvoie le contexte (champ 7.7) sans parser tout le message."""
    text = raw.decode(ENCODING, errors="replace")
    premiere = text.replace("\r\n", "\r").replace("\n", "\r").split("\r")[0]
    if not premiere.startswith("H") or len(premiere) < 6:
        return ""
    field_sep = premiere[1]
    parts = premiere.split(field_sep)
    return parts[6] if len(parts) > 6 else ""


def _decoupe(raw: bytes):
    """Factorisation : renvoie (segments, field_sep, component_sep) après
    réassemblage des segments A. Lève ValueError si H manquant."""
    text = raw.decode(ENCODING, errors="replace")
    lignes = [l for l in text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if l]
    if not lignes or not lignes[0].startswith("H"):
        raise ValueError("Message HPRIM invalide : segment H manquant")
    field_sep = lignes[0][1]
    component_sep = lignes[0][2]
    segments: List[str] = []
    for ligne in lignes:
        if ligne.startswith("A" + field_sep):
            if segments:
                segments[-1] += ligne[2:]
            continue
        segments.append(ligne)
    return segments, field_sep, component_sep


def parse_err(raw: bytes) -> ErrMessage:
    """Lit un message d'erreur HPRIM (contexte ERR, §5.14)."""
    segments, field_sep, component_sep = _decoupe(raw)

    def champs(seg: str) -> List[str]:
        return seg.split(field_sep)

    def sous(val: str, idx: int) -> str:
        parts = val.split(component_sep)
        return parts[idx] if idx < len(parts) else ""

    h = champs(segments[0])
    msg = ErrMessage(
        contexte=_get(h, 6),
        emetteur_code=sous(_get(h, 4), 0),
        emetteur_nom=sous(_get(h, 4), 1),
        recepteur_code=sous(_get(h, 9), 0),
        recepteur_nom=sous(_get(h, 9), 1),
        nom_fichier=_get(h, 2),
        date_message=parse_ts(_get(h, 13)),
        nom_fichier_errone="",
        date_reception=None,
    )

    for seg in segments[1:]:
        c = champs(seg)
        if c[0] != "ERR":
            continue
        gravite = _get(c, 4)        # 25.5
        type_err = _get(c, 9)       # 25.10
        # 25.3 / 25.4 : on prend les premières valeurs rencontrées
        if not msg.nom_fichier_errone and _get(c, 2):
            msg.nom_fichier_errone = _get(c, 2)
        if msg.date_reception is None and _get(c, 3):
            msg.date_reception = parse_ts(_get(c, 3))
        msg.erreurs.append(ErrLigne(
            rang=_get(c, 1),
            gravite=gravite,
            gravite_libelle=ERR_GRAVITE.get(gravite, gravite),
            numero_ligne=_get(c, 5),       # 25.6
            adresse_segment=_get(c, 6),    # 25.7
            donnee_erronee=_get(c, 7),     # 25.8
            valeur_erronee=_get(c, 8),     # 25.9
            type_erreur=type_err,
            type_erreur_libelle=ERR_TYPE.get(type_err, type_err),
            designation=_get(c, 10),       # 25.11
        ))
    return msg


def parse_message(raw: bytes) -> OruMessage:
    """Lit un message HPRIM (typiquement ORU) et renvoie une structure
    exploitable. Les séparateurs sont lus dans le segment H, pas supposés."""
    text = raw.decode(ENCODING, errors="replace")
    # Recoller les segments A à leur segment d'origine
    lignes = [l for l in text.replace("\r\n", "\r").replace("\n", "\r").split("\r") if l]
    if not lignes or not lignes[0].startswith("H"):
        raise ValueError("Message HPRIM invalide : segment H manquant")

    header = lignes[0]
    field_sep = header[1]
    component_sep = header[2]
    # repeat = header[3]; escape = header[4]; subcomp = header[5]

    # Réassemblage des segments A
    segments: List[str] = []
    for ligne in lignes:
        if ligne.startswith("A" + field_sep):
            if segments:
                segments[-1] += ligne[2:]
            continue
        segments.append(ligne)

    def champs(seg: str) -> List[str]:
        return seg.split(field_sep)

    def sous(val: str, idx: int) -> str:
        parts = val.split(component_sep)
        return parts[idx] if idx < len(parts) else ""

    h = champs(segments[0])
    msg = OruMessage(
        contexte=_get(h, 6),
        emetteur_code=sous(_get(h, 4), 0),
        emetteur_nom=sous(_get(h, 4), 1),
        recepteur_code=sous(_get(h, 9), 0),
        recepteur_nom=sous(_get(h, 9), 1),
        nom_fichier=_get(h, 2),
        date_message=parse_ts(_get(h, 13)),
    )

    patient: Optional[OruPatient] = None
    demande: Optional[OruDemande] = None
    for seg in segments[1:]:
        c = champs(seg)
        kind = c[0]
        if kind == "P":
            patient = OruPatient(
                rang=_get(c, 1),
                id_demandeur=sous(_get(c, 2), 0),
                nom=sous(_get(c, 5), 0),
                prenom=sous(_get(c, 5), 1),
            )
            msg.patients.append(patient)
            demande = None
        elif kind == "OBR" and patient is not None:
            id_dem = _get(c, 2)
            demande = OruDemande(
                rang=_get(c, 1),
                id_echantillon=sous(id_dem, 0),
                id_demande=sous(id_dem, 1),
                statut=_get(c, 25),  # 9.26
            )
            patient.demandes.append(demande)
        elif kind == "OBX" and demande is not None:
            test = _get(c, 3)
            demande.resultats.append(OruResultat(
                rang=_get(c, 1),
                type_resultat=_get(c, 2),
                code_test=sous(test, 0),
                libelle_test=sous(test, 1),
                valeur=_get(c, 5),
                unite=_get(c, 6),
                normales=_get(c, 7),
                anormalite=_get(c, 8),
                statut=_get(c, 11),
            ))
        # C, A, L : ignorés / déjà traités
    return msg


# --------------------------------------------------------------------------- #
# Bas niveau
# --------------------------------------------------------------------------- #
def _get(lst: Sequence[str], idx: int) -> str:
    return lst[idx] if idx < len(lst) else ""


def _join_trim(champs: Sequence[str], field_sep: str) -> str:
    last = -1
    for i, c in enumerate(champs):
        if c != "":
            last = i
    if last < 0:
        return champs[0]
    return field_sep.join(champs[: last + 1])


def _split_segment(segment: str, sep: Separators) -> List[str]:
    limit = MAX_SEGMENT_LEN - len(SEGMENT_TERMINATOR)
    if len(segment) <= limit:
        return [segment]
    parts = [segment[:limit]]
    rest = segment[limit:]
    prefix = "A" + sep.field
    chunk = limit - len(prefix)
    while rest:
        parts.append(prefix + rest[:chunk])
        rest = rest[chunk:]
    return parts


def nom_fichier_hprim(prefixe_emetteur: str, numero_ordre: int) -> str:
    """Nom conforme §7.2 : préfixe RADIX 50 (A-Z, 0-9) <=8 car. + '.HPR'."""
    import re
    base = re.sub(r"[^A-Z0-9]", "", (prefixe_emetteur or "").upper())[:4] or "SEGH"
    largeur = max(1, 8 - len(base))
    numero = str(numero_ordre).zfill(largeur)[-largeur:]
    return f"{base}{numero}.HPR"


# --------------------------------------------------------------------------- #
# Construction d'un message ERR (pour signaler au labo un message reçu invalide)
# --------------------------------------------------------------------------- #
@dataclass
class ErreurAEmettre:
    """Une erreur à signaler dans un segment ERR sortant."""
    gravite: str = "I"            # 25.5 : T / P / I
    designation: str = ""         # 25.11 : description en clair
    type_erreur: str = ""         # 25.10 : A / I / S
    numero_ligne: str = ""        # 25.6
    adresse_segment: str = ""     # 25.7
    donnee_erronee: str = ""      # 25.8
    valeur_erronee: str = ""      # 25.9


def construire_err(
    emetteur: Entite,
    recepteur: Entite,
    erreurs: Sequence[ErreurAEmettre],
    nom_fichier: str,
    nom_fichier_errone: str = "",
    date_reception: Optional[datetime] = None,
    type_liaison: str = "L",
    date_message: Optional[datetime] = None,
    separators: Optional[Separators] = None,
) -> str:
    """Génère un message ERR complet (H + n×ERR + L), prêt à transmettre."""
    sep = separators or Separators()
    date_message = date_message or datetime.now()

    seg_h = _join_trim([
        "H" + sep.header_token(),
        nom_fichier, "",
        comp(emetteur.code, emetteur.nom, sep=sep),
        "",
        "ERR",                                       # 7.7 contexte
        "", "",
        comp(recepteur.code, recepteur.nom, sep=sep),
        "", "",
        comp("H2.4", type_liaison, sep=sep),
        fmt_ts(date_message),
    ], sep.field)

    segments = [seg_h]
    for i, e in enumerate(erreurs, start=1):
        seg_err = _join_trim([
            "ERR",                       # 25.1
            str(i),                      # 25.2
            nom_fichier_errone,          # 25.3
            fmt_ts(date_reception),      # 25.4
            e.gravite,                   # 25.5
            e.numero_ligne,              # 25.6
            e.adresse_segment,           # 25.7
            e.donnee_erronee,            # 25.8
            e.valeur_erronee,            # 25.9
            e.type_erreur,               # 25.10
            e.designation,               # 25.11
        ], sep.field)
        segments.append(seg_err)

    segments.append(_join_trim(["L", "1", "", "0", str(len(segments) + 1)],
                               sep.field))

    out: List[str] = []
    for seg in segments:
        out.extend(_split_segment(seg, sep))
    return SEGMENT_TERMINATOR.join(out) + SEGMENT_TERMINATOR
