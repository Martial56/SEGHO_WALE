# 🏥 SEGHO-WALE — Système de Gestion du Centre Médico-Social WALÉ

## Vue d'ensemble

SEGHO-WALE est un système d'information médical complet développé en **Django** pour le Centre Médico-Social WALÉ de Yamoussoukro (Côte d'Ivoire), conforme au cahier des charges HISOFT.

---

## 🗂️ Architecture du projet

```
medisoft/
├── medisoft/               # Configuration principale Django
│   ├── settings.py         # Paramètres (BDD, apps, timezone Africa/Abidjan)
│   └── urls.py             # Routage principal
│
├── patients/               # 👤 Gestion des patients
│   └── models.py           → Patient, Assurance, RendezVous
│
├── medecins/               # 👨‍⚕️ Gestion du personnel médical
│   └── models.py           → Medecin, Specialite, Service
│
├── consultations/          # 🩺 Consultations & dossiers médicaux
│   └── models.py           → Consultation, Constante, Diagnostic,
│                              Ordonnance, LigneOrdonnance, ExamenDemande
│
├── pharmacie/              # 💊 Pharmacie & gestion des stocks
│   └── models.py           → Medicament, LotMedicament, MouvementStock,
│                              CommandePharmacies, Fournisseur
│
├── laboratoire/            # 🔬 Laboratoire & Imagerie
│   └── models.py           → AnalyseLaboratoire, ResultatAnalyse,
│                              ExamenImagerie, TypeExamen
│
├── hospitalisation/        # 🛏️ Gestion des hospitalisations
│   └── models.py           → Hospitalisation, Chambre, FicheVisite,
│                              ProtocoleHospitalisation
│
├── facturation/            # 🧾 Facturation & paiements
│   └── models.py           → Facture, LigneFacture, Paiement, Acte
│
├── caisse/                 # 💰 Gestion de caisse & trésorerie
│   └── models.py           → Caisse, SessionCaisse, TransactionCaisse
│
├── ressources_humaines/    # 👥 RH — Personnel, congés, présences
│   └── models.py           → Employe, Poste, Conge, Presence
│
└── rapports/               # 📊 Rapports médicaux & vaccinations
    └── models.py           → RapportMedical, Vaccination
```

---

## 🚀 Installation et démarrage

### Prérequis
- Python 3.10+
- pip

### Étapes

```bash
# 1. Cloner/déplacer le projet
cd medisoft/

# 2. Installer les dépendances
pip install django pillow

# 3. Appliquer les migrations
python manage.py migrate

# 4. Créer un superutilisateur
python manage.py createsuperuser

# 5. Lancer le serveur
python manage.py runserver

# 6. Accéder à l'interface
# http://127.0.0.1:8000/admin/
```

---

## 🔑 Accès par défaut (démo)

| Utilisateur | Mot de passe | Rôle |
|-------------|--------------|------|
| `admin`     | `wale2024`   | Administrateur |

---

## 📋 Modules fonctionnels

### 1. 👤 Gestion des Patients (`patients`)
- Création de dossier avec **code patient automatique** (PAT20250001)
- Informations démographiques complètes + photo
- Gestion des **assurances** (CNPS, MUGEF-CI, AXA, NSIA, SUNU...)
- Numéro et date d'expiration de carte d'assurance
- Contact d'urgence
- **Rendez-vous** (consultation, contrôle, urgence, vaccination)

### 2. 👨‍⚕️ Gestion Médicale (`medecins`, `consultations`)
- Fichier médecin avec spécialité, honoraires
- Organisation en **Services** (Consultations, Gynéco, Pédiatrie, Labo, Pharmacie...)
- **Dossier médical** : anamnèse, constantes (poids, taille, TA, température, SpO2, IMC calculé auto)
- **Diagnostics CIM-10** avec choix principal/associé/différentiel
- **Ordonnances** internes et externes avec lignes de médicaments
- **Demandes d'examens** (labo ou imagerie)

### 3. 💊 Pharmacie (`pharmacie`)
- Catalogue médicaments avec DCI, forme, dosage
- **Gestion des lots** avec dates de péremption
- **Mouvements de stock** (entrée, sortie, ajustement)
- **Alertes de stock** (seuil minimum et d'alerte)
- **Commandes fournisseurs** (brouillon → envoyé → reçu)

### 4. 🔬 Laboratoire & Imagerie (`laboratoire`)
- **Analyses biologiques** avec numéro auto (LAB20250001)
- Saisie des résultats par paramètre (valeur, unité, norme min/max)
- Interprétation automatique (normal/élevé/bas/critique)
- **Imagerie** : échographies, radios, scanner, IRM
- Compte-rendu et conclusion radiologue
- Lien avec les examens demandés en consultation

### 5. 🛏️ Hospitalisation (`hospitalisation`)
- **Chambres** : simple, double, VIP, soins intensifs (avec tarif/jour)
- Dossier d'hospitalisation avec numéro auto (HOSP20250001)
- **Fiches de visite quotidiennes** (médecin, observations, constantes JSON)
- **Protocoles de soins** personnalisés
- Calcul automatique de la **durée de séjour**
- Gestion de la **caution**

### 6. 🧾 Facturation (`facturation`)
- **Factures** par type (consultation, hospit, pharmacie, labo, imagerie)
- Lignes de facturation (actes médicaux + médicaments)
- Calcul **ticket modérateur** (patient) vs **part assurance**
- **Paiements** multi-modes : espèces, chèque, mobile money, virement, bon
- Suivi du solde restant dû

### 7. 💰 Caisse & Trésorerie (`caisse`)
- **Sessions de caisse** (ouverture/fermeture avec solde)
- Transactions : encaissements, décaissements, transferts
- Historique complet des opérations

### 8. 👥 Ressources Humaines (`ressources_humaines`)
- Fichier employé avec poste et service
- **Gestion des congés** (annuel, maladie, maternité, exceptionnel)
- Workflow d'approbation des congés
- **Pointage et présences** journalières

### 9. 📊 Rapports (`rapports`)
- **Rapports médicaux** (mensuel, trimestriel, annuel, activité, directeur)
- Validation des rapports par la hiérarchie
- **Registre des vaccinations** avec rappels

---

## 🔐 Groupes d'accès suggérés

| Groupe | Accès |
|--------|-------|
| Médecin | Consultations, ordonnances, diagnostics, examens |
| Infirmier | Constantes, soins, hospitalisations |
| Pharmacien | Pharmacie, stocks, commandes |
| Laborantin | Analyses, imagerie, résultats |
| Caissier | Facturation, caisse, paiements |
| Accueil | Patients, rendez-vous, admission |
| Comptable | Facturation, trésorerie, rapports financiers |
| RH | Employés, congés, présences |
| Directeur | Tous les modules (lecture) + rapports |
| Administrateur | Accès complet |

---

## 🗄️ Base de données

Par défaut : **SQLite** (développement)

Pour la production, configurer PostgreSQL dans `settings.py` :
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'medisoft_db',
        'USER': 'medisoft_user',
        'PASSWORD': 'votre_mot_de_passe',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## 📈 Évolutions recommandées

1. **API REST** (Django REST Framework) pour intégration mobile/tablette
2. **Tableau de bord** avec graphiques (Chart.js ou ApexCharts)
3. **Impression PDF** des ordonnances, factures, résultats labo
4. **Notifications** SMS/email pour rappels rendez-vous
5. **Interface dédiée** par rôle (médecin, caissier, pharmacien)
6. **Intégration automates** laboratoire (HL7/FHIR)
7. **Module BI** pour statistiques épidémiologiques

---

## 🌍 Configuration Côte d'Ivoire

- Fuseau horaire : `Africa/Abidjan`
- Langue : Français (`fr-fr`)
- Monnaie : Franc CFA (XOF)
- Assurances préconfigurées : CNPS, MUGEF-CI, AXA, SUNU, NSIA

---

*SEGHO-WALE v1.0 — Développé pour le Centre Médico-Social WALÉ, Yamoussoukro, Côte d'Ivoire*
