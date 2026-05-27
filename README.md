# 🏥 SEGHO-WALE — Système de Gestion du Centre Médico-Social WALÉ

Système d'information médical développé en **Django 6** pour le Centre Médico-Social WALÉ de Yamoussoukro (Côte d'Ivoire).

---

## 🗂️ Architecture des modules

```
medisoft/
├── medisoft/               # Configuration principale Django
│   ├── settings.py         # Paramètres (BDD, apps, timezone Africa/Abidjan)
│   └── urls.py             # Routage principal
│
├── core/                   # 🏠 Dashboard & authentification
│
├── patients/               # 👤 Dossiers patients, assurances, rendez-vous
│
├── soins/                  # 🩺 Soins infirmiers, procédures, ordonnances
│
├── ordonnances/            # 💊 Ordonnances & groupes médicaments
│
├── pharmacie/              # 💊 Stock médicaments, lots, commandes fournisseurs
│
├── laboratoire/            # 🔬 Analyses biologiques & imagerie médicale
│
├── hospitalisation/        # 🛏️ Chambres, admissions, fiches de visite
│
├── facturation/            # 🧾 Factures, lignes, paiements (patient + assurance)
│
├── caisse/                 # 💰 Sessions de caisse & transactions
│
├── employer/               # 👥 RH — Employés, congés, présences, planning
│   ├── Employe             → dossier unifié (identité + profil médical + RH)
│   ├── Specialite          → spécialités médicales
│   ├── Departement         → services / départements hospitaliers
│   ├── DocteurReferent     → médecins référents externes
│   ├── Conge               → demandes et workflow de congés
│   ├── Presence            → pointage journalier
│   └── JourFerie           → calendrier des jours fériés
│
├── conges/                 # 📅 Vues et logique du module congés
│
├── planning/               # 📆 Planning médecins (hebdomadaire, bureaux)
│
├── presence/               # ⏱️ Suivi des présences / pointage
│
├── services/               # 🏷️ Catalogue : actes, médicaments, tarifs
│
├── utilisateur/            # 🔑 Profil utilisateur & gestion des comptes
│
├── modules_permissions/    # 🛡️ Contrôle d'accès par module
│
└── rapports/               # 📊 Rapports médicaux & registre vaccinations
```

---

## 🚀 Installation

### Prérequis
- Python 3.10+
- pip

### Démarrage rapide

```bash
# 1. Créer et activer l'environnement virtuel
python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Appliquer les migrations
python manage.py migrate

# 4. Créer un superutilisateur
python manage.py createsuperuser
# (par défaut : admin / wale2024)

# 5. Lancer le serveur
python manage.py runserver

# 6. Accéder à l'application
# http://127.0.0.1:8000/
```

---

## 🔑 Accès par défaut (démo)

| Utilisateur | Mot de passe | Rôle |
|-------------|--------------|------|
| `admin`     | `wale2024`   | Administrateur |

---

## 🗺️ URLs principales

| URL | Module |
|-----|--------|
| `/` | Dashboard (nécessite connexion) |
| `/login/` | Authentification |
| `/employer/` | Module RH (employés, congés, planning, présence) |
| `/conges/` | Gestion des congés |
| `/utilisateurs/` | Profils & comptes utilisateurs |
| `/admin/` | Interface Django Admin |

---

## 📋 Modules détaillés

### 👤 Patients (`patients`)
- Dossier patient avec **code automatique** (PAT20250001)
- Assurances (CNPS, MUGEF-CI, AXA, NSIA, SUNU…)
- Rendez-vous avec statut (planifié → confirmé → terminé/annulé)

### 🩺 Soins (`soins`)
- Soins infirmiers avec procédures associées
- Lien vers ordonnances, examens et facturation

### 💊 Ordonnances (`ordonnances`)
- Groupes de médicaments avec lignes de prescription
- Lien vers le médecin prescripteur (employer.Employe)

### 💊 Pharmacie (`pharmacie`)
- Catalogue médicaments avec stock par lot (+ date expiration)
- Mouvements de stock (entrée, sortie, ajustement)
- Commandes fournisseurs avec workflow (brouillon → envoyé → reçu)

### 🔬 Laboratoire (`laboratoire`)
- Analyses biologiques avec résultats et interprétation automatique
- Imagerie médicale (radio, écho, scanner, IRM)

### 🛏️ Hospitalisation (`hospitalisation`)
- Gestion des chambres (simple, double, VIP, soins intensifs)
- Dossier hospitalisation (HOSP20250001)
- Fiches de visite quotidiennes + protocoles de soins

### 🧾 Facturation (`facturation`)
- Factures multi-types avec co-paiement patient / assurance
- Paiements : espèces, mobile money, chèque, virement, bon

### 💰 Caisse (`caisse`)
- Sessions de caisse avec solde ouverture/fermeture
- Transactions (encaissements, décaissements, transferts)

### 👥 RH — Employer (`employer`)
- **Fiche employé unifiée** : identité, coordonnées, RH, profil médical
  - Section médicale conditionnelle (visible si `est_medecin = Oui`)
  - Spécialité, N° ordre, durée consultation, honoraires, signature
- Départements/services, fonctions, grades, types de contrat
- **Congés** : workflow en 2 niveaux (chef de service → RH)
  - Types : annuel, maladie, maternité, paternité, exceptionnel…
  - Soldes de congé par année
- **Présence** : pointage matin/soir avec calcul des retards
- **Planning médecins** : planning hebdomadaire par bureau
- Docteurs référents externes (contacts médicaux hors centre)

### 🔑 Utilisateur (`utilisateur`)
- Profil self-service : l'employé consulte et modifie ses propres infos
- Admin : liste et modification de tous les comptes utilisateurs
- Liaison dossier employé ↔ compte Django

### 🛡️ Permissions (`modules_permissions`)
- Contrôle d'accès par module (activer/désactiver par groupe ou utilisateur)

### 📊 Rapports (`rapports`)
- Rapports médicaux (mensuel, trimestriel, annuel)
- Registre des vaccinations

---

## 🔐 Groupes d'accès suggérés

| Groupe | Accès |
|--------|-------|
| Médecin | Soins, ordonnances, labo, hospitalisation |
| Infirmier | Soins, présences |
| Pharmacien | Pharmacie, stocks, commandes |
| Laborantin | Analyses, imagerie, résultats |
| Caissier | Facturation, caisse, paiements |
| Accueil | Patients, rendez-vous |
| Comptable | Facturation, trésorerie, rapports |
| RH | Employés, congés, présences, planning |
| Directeur | Tous modules (lecture) + rapports |
| Administrateur | Accès complet |

---

## 🔧 Patterns techniques

### Codes automatiques
Chaque entité principale génère un code lisible : `PREFIX + ANNÉE + séquence 4 chiffres`
> Ex : `PAT20250001`, `HOSP20250001`, `REF20250001`

### Workflow congés
```
demandé → validé_service → approuvé → en_cours → terminé
                        ↘ refusé
```

### Modèle Employe unifié
`employer.Employe` centralise RH + profil médical dans une seule table (`employes_employe`).
Les champs médicaux (`specialite`, `ordre_medecin`, `service_consultation`…) ne sont actifs que si `est_medecin = True`.

---

## 🗄️ Base de données

Défaut : **SQLite** (développement)

Production — configurer PostgreSQL dans `medisoft/settings.py` :
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'segho_wale_db',
        'USER': 'segho_user',
        'PASSWORD': 'votre_mot_de_passe',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## 🌍 Configuration locale

| Paramètre | Valeur |
|-----------|--------|
| Fuseau horaire | `Africa/Abidjan` |
| Langue | `fr-fr` |
| Monnaie | Franc CFA (XOF) |
| Nationalité par défaut | Ivoirienne |
| Pays préférés (téléphone) | CI, SN, ML, BF, GN, CM, TG, BJ… |

---

## 🌿 Branches

| Branche | Description |
|---------|-------------|
| `main` | Version stable de référence |
| `Orthiniel_Branch` | Développement actif — refonte architecture RH, modules congés/planning/présence |

---

*SEGHO-WALE — Centre Médico-Social WALÉ, Yamoussoukro, Côte d'Ivoire*
