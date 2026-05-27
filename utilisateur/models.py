# utilisateur/models.py
#
# Ce module gère UNIQUEMENT les comptes utilisateurs :
#   - Chaque utilisateur voit et modifie son propre profil
#   - L'admin voit et modifie tous les comptes
#
# Les modèles RH (Employe, Departement, Specialite, Diplome, DocteurReferent…)
# sont dans employer/models.py

# Aucun modèle custom — on s'appuie directement sur django.contrib.auth.User
# complété par employer.Employe (via user.employe_profile)
