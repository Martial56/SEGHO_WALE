# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SEGHO-WALE is a Django-based medical information management system for Centre Médico-Social WALÉ (Yamoussoukro, Côte d'Ivoire). The primary UI is the **Django admin interface** — custom views exist only for the dashboard and authentication. The system is fully in French with Africa/Abidjan timezone and CFA Franc currency.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Apply migrations
python manage.py migrate

# Create initial superuser (default: admin / wale2024)
python manage.py createsuperuser

# Run development server (access at http://127.0.0.1:8000)
python manage.py runserver

# Create migrations after model changes
python manage.py makemigrations

# Run tests (currently empty test suites)
python manage.py test

# Run tests for a specific app
python manage.py test patients
```

## Architecture

### Tech Stack
- **Backend**: Python 3.10+, Django 6.0.4
- **Database**: SQLite (dev), PostgreSQL-ready via psycopg2-binary
- **Frontend**: Django admin + custom HTML/CSS/JS templates (no framework)
- **Auth**: Django built-in user/group system

### Django Apps & Responsibilities

| App | Domain |
|-----|--------|
| `core` | Dashboard view, login/logout |
| `patients` | Patient records, insurance, appointments |
| `medecins` | Doctors, specialties, hospital services |
| `consultations` | Consultations, vital signs, ICD-10 diagnoses, prescriptions, exam orders |
| `pharmacie` | Drug catalog, stock lots, movements, supplier orders |
| `laboratoire` | Lab analyses and imaging studies |
| `hospitalisation` | Room management, admissions, daily visit notes |
| `facturation` | Invoices, line items, payments (espèces/mobile money/assurance) |
| `caisse` | Cash register sessions and transactions |
| `ressources_humaines` | Employee records, leave requests, attendance |
| `rapports` | Medical reports, vaccination registry |

### Auto-Generated ID Codes
Every main entity has an auto-generated human-readable code following the pattern `PREFIX + YEAR + 4-digit sequence` (e.g., `PAT20250001`, `CONS20250001`, `FAC20250001`). These are set in the model's `save()` method — never set them manually.

### Key Patterns
- **Inline admin**: `Constante`, `Diagnostic`, `Ordonnance`, and `LigneOrdonnance` are managed inline within `ConsultationAdmin`.
- **Status workflows**: `RendezVous` (planifié → confirmé → terminé/annulé/absent), `Conge` (demandé → approuvé/refusé → en cours → terminé), `CommandePharmacies` (brouillon → envoyé → reçu).
- **Billing split**: `Facture` supports co-payment between patient and insurance (`montant_patient` + `montant_assurance`).
- **Stock tracking**: Pharmacy uses `LotMedicament` (with expiration) + `MouvementStock` for full traceability.

### URL Structure
- `/admin/` — Django admin (primary interface)
- `/` — Dashboard (requires login)
- `/login/`, `/logout/` — Auth
- Media files served from `MEDIA_ROOT` in DEBUG mode

### Settings & Configuration
- Main config: [medisoft/settings.py](medisoft/settings.py)
- URL routing: [medisoft/urls.py](medisoft/urls.py)
- `LANGUAGE_CODE = 'fr-fr'`, `TIME_ZONE = 'Africa/Abidjan'`
- `LOGIN_URL = '/login/'` — redirects unauthenticated users from dashboard
- Media uploads enabled (patient photos, imaging files, medical reports)

### Suggested User Groups (defined in README, not enforced in code)
Médecin, Infirmier, Pharmacien, Laborantin, Caissier, Accueil, Comptable, RH, Directeur, Administrateur
