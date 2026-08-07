# Guide — Pharmacie multi-centres (Walé Yamoussoukro / Walé Toumbokro)

Ce guide explique les changements récents apportés au module **Pharmacie** :
le cloisonnement des ordonnances et de l'accès par centre, et le nouveau
système de permissions pour les actions de gestion (dispensation, dotation,
caisse, rapports).

---

## 1. Ce qui a changé

Avant ces modifications, les deux pharmacies (Walé Yamoussoukro et Walé
Toumbokro) partageaient les mêmes listes d'ordonnances, et n'importe quel
utilisateur connecté pouvait ouvrir l'une ou l'autre pharmacie. Désormais :

- **Chaque pharmacie est rattachée à un centre** : Walé Yamoussoukro → centre
  *WALE*, Walé Toumbokro → centre *TOUMBOKRO*.
- **Les ordonnances sont cloisonnées par centre** : une ordonnance prescrite
  par un médecin de Walé Yamoussoukro n'apparaît plus dans la liste « à
  dispenser » de Toumbokro, et inversement.
- **L'accès à une pharmacie dépend du centre actuellement actif** de
  l'utilisateur (et non plus de tous les centres auxquels il a accès).
- **Les actions qui modifient le stock** (dispensation, demande de dotation,
  livraisons, retours, inventaire, caisse, rapports financiers) sont
  protégées par des **permissions** assignables individuellement à chaque
  utilisateur, sans avoir à créer de groupe au nom précis.

---

## 2. Accéder à sa pharmacie

Sur la page d'accueil **Pharmacie** (`/pharmacie/`), les deux pharmacies sont
présentées sous forme de cartes.

- La carte de la pharmacie **du centre actif** de l'utilisateur est
  cliquable normalement.
- La carte de **l'autre centre** est grisée, non cliquable, et affiche
  « Accès réservé à ce centre ».

Le centre actif est celui sélectionné via le changeur de centre de
l'application (menu utilisateur). Un utilisateur qui n'a accès qu'à un seul
centre n'a rien à faire de particulier : sa pharmacie est toujours celle
affichée en clair.

> Taper directement l'adresse de l'autre pharmacie dans le navigateur ne
> permet pas de contourner la restriction : le serveur refuse l'accès
> (erreur **403**) si le centre actif ne correspond pas à la pharmacie
> demandée. Seul un superutilisateur (administrateur technique) voit les
> deux pharmacies sans restriction.

### Cas d'un utilisateur affecté aux deux centres

Un médecin ou un membre du personnel qui intervient dans les deux centres
(profil configuré avec les deux centres) doit **changer son centre actif**
pour basculer d'une pharmacie à l'autre — exactement comme pour changer de
centre sur le reste de l'application (patients, laboratoire, etc.). Une fois
le centre actif changé, la carte de la pharmacie correspondante se débloque
et l'autre se verrouille.

---

## 3. Ordonnances par centre

Dans chaque pharmacie, les écrans suivants ne montrent désormais que les
ordonnances dont le patient dépend du centre de cette pharmacie :

- le tableau de bord (« ordonnances en attente ») ;
- la liste des ordonnances du jour ;
- l'action de dispensation elle-même (impossible de dispenser une ordonnance
  d'un autre centre, même en connaissant son numéro/URL).

Le compteur « Ordonnances » affiché sur chaque carte d'accueil reflète
également désormais le nombre réel d'ordonnances en attente **pour ce
centre**, et non plus le total tous centres confondus.

---

## 4. Droits de gestion de la pharmacie (permissions)

Consulter le stock et les ordonnances ne suffit pas pour agir dessus. Trois
actions sensibles sont protégées par des **permissions Django**, visibles et
assignables directement sur la fiche de chaque utilisateur dans l'admin :

| Permission (visible dans l'admin) | Ce qu'elle autorise |
|---|---|
| **Peut gérer le stock d'une pharmacie** (dispensation, dotation, inventaire, retours, livraisons) `pharmacie \| gerer_stock_pharmacie` | Dispenser une ordonnance, faire une **demande de dotation** au stock central, confirmer une livraison, saisir un retour, créer/valider un inventaire. |
| **Peut valider ou annuler une vente en pharmacie** `pharmacie \| valider_vente_pharmacie` | Encaisser une vente au comptoir (caisse), annuler une vente déjà enregistrée. |
| **Peut voir les rapports financiers de la pharmacie** `pharmacie \| voir_rapport_financier_pharmacie` | Consulter la recette du jour, le rapport journalier/mensuel, la répartition par mode de paiement. |

### Comment assigner une permission à un utilisateur

1. Aller dans l'admin Django : `/admin/auth/user/`.
2. Ouvrir la fiche de l'utilisateur concerné.
3. Dans la section **« Permissions de l'utilisateur »**, chercher
   `pharmacie` et cocher la ou les permissions voulues dans la liste
   disponible, puis les faire passer dans la liste « choisi(s) ».
4. Enregistrer.

L'utilisateur voit l'effet immédiatement (pas besoin de se reconnecter).
Sans une de ces permissions, la page correspondante renvoie une erreur
**403 Forbidden** — c'est le comportement attendu, pas un bug : cela
signifie simplement que l'utilisateur n'a pas été habilité pour cette
action précise.

> Un superutilisateur a automatiquement toutes les permissions, sans rien à
> cocher.
>
> Il reste possible de regrouper ces permissions dans un groupe (ex.
> « Pharmacien ») si vous préférez gérer les droits par groupe plutôt
> qu'individuellement : créez le groupe dans `/admin/auth/group/`, cochez-y
> les mêmes permissions, puis ajoutez les utilisateurs à ce groupe. Les deux
> approches (directe ou par groupe) fonctionnent et peuvent être combinées.

---

## 5. Demande de dotation au stock central

Chaque pharmacie (Yamoussoukro **et** Toumbokro) garde la possibilité de
faire une demande de dotation au stock central, à condition que
l'utilisateur :

- ait pour centre actif le centre de cette pharmacie (ou soit
  superutilisateur) ;
- dispose de la permission **« Peut gérer le stock d'une pharmacie »**.

Cette fonctionnalité n'a pas été restreinte par le cloisonnement par
centre : elle reste symétrique entre les deux pharmacies.

---

## 6. Foire aux questions

**J'obtiens une erreur 403 en essayant d'accéder à une pharmacie.**
Votre centre actif ne correspond pas à cette pharmacie. Changez de centre
actif si vous êtes habilité pour les deux, ou contactez un administrateur
si vous pensez ne pas avoir le bon centre configuré sur votre compte.

**J'obtiens une erreur 403 en essayant de dispenser / faire une demande de
dotation / encaisser une vente / voir un rapport financier, alors que
j'accède bien à ma pharmacie.**
Il vous manque la permission correspondante (voir tableau section 4).
Demandez à un administrateur de vous l'ajouter sur votre fiche utilisateur.

**Une carte pharmacie est grisée sur la page d'accueil.**
C'est normal : elle correspond à un centre différent de votre centre actif.
Ce n'est pas une erreur, l'accès est simplement réservé à ce centre.

**Je ne vois plus les ordonnances de l'autre centre dans ma pharmacie.**
C'est le comportement attendu depuis cette mise à jour : chaque pharmacie ne
traite que les ordonnances de son propre centre.

---

## Annexe technique

*Pour l'administrateur technique / le développeur qui maintient
l'application.*

- **Rattachement pharmacie ↔ centre** :
  `pharmacie/models.py` → `PHARMACIE_CENTRE_CODE` (`wale_yamoussoukro` →
  `WALE`, `wale_toumbokro` → `TOUMBOKRO`).
- **Filtrage des ordonnances par centre** :
  `pharmacie/views.py` → `_ordonnances_du_centre(pharmacie)`, utilisée dans
  `pharmacie_accueil`, `pharmacie_dashboard`, `pharmacie_ordonnances` et
  `pharmacie_dispenser`.
- **Contrôle d'accès à une pharmacie (centre actif)** :
  `pharmacie/views.py` → `peut_acceder_pharmacie(request, pharmacie)`,
  appliquée par `get_pharmacie_or_404` sur toutes les vues de l'app ; se
  base sur `request.centre` (résolu par `core.middleware`), pas sur
  l'ensemble des centres autorisés du profil.
- **Permissions de gestion** : `pharmacie/models.py` →
  `PharmaciePermissions` (modèle technique sans table, `managed = False`)
  porte les trois permissions `gerer_stock_pharmacie`,
  `valider_vente_pharmacie`, `voir_rapport_financier_pharmacie` ; utilisées
  via `user.has_perm('pharmacie.<codename>')` dans `can_manage_pharmacie`,
  `can_valider_vente`, `can_view_rapport_financier`.
- **Migration associée** : `pharmacie/migrations/0009_pharmaciepermissions.py`.
- **Rattachement des patients/ordonnances à un centre** : s'appuie sur
  `patients.Patient` (modèle `ModeleCentre`, champ `centre`) et sur
  `consultations.Ordonnance` (champs `patient` et `consultation__patient`).
