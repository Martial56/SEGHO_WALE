"""Ce qu'une fiche patient traîne derrière elle.

Un seul endroit sait quelles tables pointent vers `Patient`, et il le sait par
introspection : un module ajouté demain sera couvert sans qu'on y pense. Les
écrans de l'étape 4a s'en servent pour montrer (« 3 rendez-vous, 2 factures »)
et pour décider si une fiche peut être masquée ; la fusion s'en servira pour
déplacer, et pour compter avant et après.

Deux chemins échappent à cette introspection, et c'est voulu :

- les quatre registres (CPN, accouchement, postnatale, curatif) pendent d'un
  `RendezVous`, pas d'un patient : ils suivent leur rendez-vous ;
- `LogActivite` vise n'importe quel objet par un lien générique, invisible aux
  relations inverses. La fusion devra le traiter à part.
"""

#: Les liens internes au mécanisme des doublons. Ils parlent *de* la fiche, pas
#: de ce qui lui est arrivé : ni à compter comme données rattachées, ni à
#: déplacer lors d'une fusion. Voir docs/DOUBLONS_PATIENTS.md, étape 4.
LIENS_INTERNES = {
    ('patients', 'ClePhonetique'),
    ('patients', 'DoublonPaire'),
    ('patients', 'PaireEcartee'),
    ('patients', 'ChoixFicheGardee'),
    ('patients', 'FusionPatient'),    # le journal parle de la fiche, il ne la suit pas
    ('patients', 'Patient'),          # fusionne_dans, doublon_de
}

#: Libellés affichés, au singulier et au pluriel : « 1 factures » se lit mal,
#: et laisser tomber le « s » final ne suffit pas pour « demandes d'examen ».
#: Une table absente d'ici garde son `verbose_name` : l'oublier n'efface rien.
LIBELLES = {
    ('patients', 'RendezVous'): ('Rendez-vous', 'Rendez-vous'),
    ('consultations', 'Consultation'): ('Consultation', 'Consultations'),
    ('consultations', 'Ordonnance'): ('Ordonnance', 'Ordonnances'),
    ('facturation', 'Facture'): ('Facture', 'Factures'),
    ('soins', 'Soin'): ('Soin', 'Soins'),
    ('soins', 'ProcedureSoin'): ('Procédure de soin', 'Procédures de soin'),
    ('hospitalisation', 'Hospitalisation'): ('Hospitalisation', 'Hospitalisations'),
    ('hospitalisation', 'RegistreDeces'): ('Décès enregistré', 'Décès enregistrés'),
    ('laboratoire', 'AnalyseLaboratoire'): ('Analyse', 'Analyses'),
    ('laboratoire', 'DemandeExamen'): ("Demande d'examen", "Demandes d'examen"),
    ('laboratoire', 'ExamenImagerie'): ('Imagerie', 'Imageries'),
    ('pharmacie', 'VentePharmacie'): ('Vente pharmacie', 'Ventes pharmacie'),
    ('patients', 'Naissance'): ('Naissance', 'Naissances'),
}


def libelle(cle, modele, nombre=2):
    """Le libellé d'une table, accordé au nombre."""
    paire = LIBELLES.get(cle)
    if paire is None:
        singulier = str(modele._meta.verbose_name).capitalize()
        pluriel = str(modele._meta.verbose_name_plural).capitalize()
        paire = (singulier, pluriel)
    return paire[0] if nombre == 1 else paire[1]


def liens():
    """[(modèle, nom du champ, libellé)] — les tables à compter et à déplacer.

    Rendue triée, pour que l'écran affiche toujours dans le même ordre.
    """
    from .models import Patient

    trouves = []
    for relation in Patient._meta.get_fields():
        if not (relation.one_to_many or relation.one_to_one):
            continue
        if not relation.auto_created or relation.concrete:
            continue
        modele = relation.related_model
        cle = (modele._meta.app_label, modele.__name__)
        if cle in LIENS_INTERNES:
            continue
        trouves.append((modele, relation.field.name, libelle(cle, modele)))
    trouves.sort(key=lambda t: t[2])
    return trouves


def tables():
    """[(clé, libellé pluriel)] dans l'ordre d'affichage."""
    return [((modele._meta.app_label, modele.__name__), pluriel)
            for modele, _champ, pluriel in liens()]


def comptes_par_table(pks):
    """{pk: {(app, Modèle): nombre}} pour un lot de fiches.

    Une requête groupée par table, pas une par fiche : une page de 48 groupes
    demanderait sinon plus de mille requêtes.

    Rendu avec la clé de la table plutôt qu'avec son libellé : l'écran côte à
    côte aligne une ligne par table, et il lui faut un repère que « 1 facture »
    et « 2 factures » ne lui donnent pas.
    """
    from django.db.models import Count

    pks = list(pks)
    resultat = {pk: {} for pk in pks}
    if not pks:
        return resultat

    for modele, champ, _pluriel in liens():
        cle = (modele._meta.app_label, modele.__name__)
        gestionnaire = getattr(modele, 'all_objects', modele._default_manager)
        lignes = (gestionnaire.filter(**{f'{champ}__in': pks})
                  .values(champ).annotate(n=Count('pk')))
        for ligne in lignes:
            if ligne['n']:
                resultat[ligne[champ]][cle] = ligne['n']
    return resultat


def comptes(pks):
    """{pk: {libellé: nombre}} pour un lot de fiches, le libellé accordé."""
    modeles = {(modele._meta.app_label, modele.__name__): modele
               for modele, _champ, _pluriel in liens()}
    return {pk: {libelle(cle, modeles[cle], nombre): nombre
                 for cle, nombre in rattache.items()}
            for pk, rattache in comptes_par_table(pks).items()}


def total(pk):
    """Le nombre de lignes rattachées à une fiche, toutes tables confondues."""
    return sum(comptes([pk])[pk].values())


#: Le relevé entier représente dix-sept mille fiches : les compter coûte une
#: seconde et demie, treize requêtes groupées. Trop pour chaque frappe dans un
#: filtre, assez peu pour une minute de mémoire — d'autant que ces nombres ne
#: servent qu'à trier et à compter, jamais à autoriser : les cartes affichent
#: les leurs, relus à chaque page, et chaque action revérifie avant d'agir.
DUREE_CACHE_TOTAUX = 60

CLE_CACHE_TOTAUX = 'patients:totaux-rattaches'


def totaux_rattaches(pks):
    """{pk: nombre de lignes rattachées} pour un grand lot de fiches.

    Mis en cache une minute, et **oublié dès qu'une décision est prise**
    (voir `oublier_les_totaux`) : sans cela le filtre « aucune donnée »
    continuerait de proposer des groupes déjà traités.
    """
    from django.core.cache import cache

    pks = list(pks)
    if not pks:
        return {}
    connus = cache.get(CLE_CACHE_TOTAUX) or {}
    manquants = [pk for pk in pks if pk not in connus]
    if manquants:
        connus = dict(connus)
        connus.update({pk: sum(tables.values())
                       for pk, tables in comptes_par_table(manquants).items()})
        cache.set(CLE_CACHE_TOTAUX, connus, DUREE_CACHE_TOTAUX)
    return {pk: connus.get(pk, 0) for pk in pks}


def oublier_les_totaux():
    """À appeler après tout masquage, écartement, fusion ou suppression."""
    from django.core.cache import cache
    cache.delete(CLE_CACHE_TOTAUX)


#: Champs propres à la fiche qu'une comparaison doit ignorer : ils ne disent
#: rien du patient, ou se recalculent.
CHAMPS_TECHNIQUES = {
    'id', 'code_patient', 'centre', 'date_creation', 'date_modification',
    'masque', 'fusionne_dans', 'doublon_de', 'ancien_identifiant',
    'date_naissance_approx', 'masque_par', 'masque_le',
}


def champs_en_plus(fiche, autre):
    """Ce que `fiche` porte et que `autre` n'a pas.

    Une fiche sans rendez-vous ni facture peut tout de même valoir mieux qu'un
    masquage : allergies, antécédents, assurance, contact d'urgence, photo,
    second téléphone. Les perdre serait silencieux — d'où cet avertissement.
    """
    manquants = []
    for champ in fiche._meta.concrete_fields:
        if champ.name in CHAMPS_TECHNIQUES:
            continue
        valeur, valeur_autre = getattr(fiche, champ.name), getattr(autre, champ.name)
        if _rempli(valeur) and not _rempli(valeur_autre):
            manquants.append(champ.verbose_name.capitalize()
                             if champ.verbose_name else champ.name)
    return manquants


def _rempli(valeur):
    if valeur is None or valeur is False:
        return False
    if isinstance(valeur, str):
        return bool(valeur.strip())
    return bool(valeur) or valeur == 0 and False
