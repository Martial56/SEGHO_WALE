"""
Logique d'autorisation centralisée pour le module hospitalisation.

Point d'entrée unique :
  get_actions_disponibles(hosp, user)
    → dict {action_key: {visible, enabled, raison_blocage}}

  check_action(hosp, user, action_key)
    → (ok: bool, erreur: str | None)

Règle d'affichage dans les templates :
  - visible=False  → bouton caché (la personne ne sait pas que l'action existe)
  - visible=True, enabled=False → bouton grisé + tooltip raison_blocage
  - visible=True, enabled=True  → bouton actif

Les vues de transition appellent check_action() pour refuser côté serveur
toute action dont le bouton aurait été forgé.
"""

from .models import ResumeDecharge


def get_actions_disponibles(hosp, user):
    """
    Calcule la visibilité et l'activation de chaque bouton d'action.

    Le superuser voit et peut tout (visible=True, enabled=True pour toutes les actions),
    comme dans le module soins. Les noms de groupes ne sont JAMAIS utilisés ici.
    """
    from facturation.models import Facture

    su = user.is_superuser

    if su:
        return {k: {'visible': True, 'enabled': True, 'raison_blocage': ''}
                for k in ('confirmer', 'creer_facture', 'installer',
                          'decharger', 'terminer', 'annuler')}

    def perm(codename):
        return user.has_perm(f'hospitalisation.{codename}')

    statut = hosp.statut

    # ── Données métier (requêtes regroupées) ────────────────────────────────
    facture_payee = Facture.objects.filter(hospitalisation=hosp, statut='payee').exists()
    nb_saf_nf = hosp.services_a_facturer.filter(
        facture__isnull=True, service__isnull=False
    ).count()
    nb_fac_imp = Facture.objects.filter(hospitalisation=hosp).exclude(
        statut__in=['payee', 'annulee']
    ).count()
    try:
        resume_ok = bool(hosp.resume_decharge.diagnostic_decharge.strip())
    except (ResumeDecharge.DoesNotExist, AttributeError):
        resume_ok = False

    def _act(visible, enabled, raison=''):
        return {'visible': bool(visible), 'enabled': bool(enabled), 'raison_blocage': raison}

    result = {}

    # ── Confirmer (double rôle selon statut) ─────────────────────────────────
    # brouillon → confirme (transition) | confirme/hospitalise → sync soins
    if not perm('can_confirmer_demande'):
        result['confirmer'] = _act(False, False)
    elif statut in ('decharge', 'termine', 'annule'):
        result['confirmer'] = _act(False, False)  # caché — soins figés
    elif statut == 'brouillon':
        if hosp.soins_apportes.count() == 0:
            result['confirmer'] = _act(True, False, "Au moins un soin requis pour confirmer")
        else:
            result['confirmer'] = _act(True, True)
    else:  # confirme, hospitalise
        # Visible mais désactivé — le JS le dégripe dès qu'un soin change
        result['confirmer'] = _act(
            True, False,
            "Accédez au formulaire de modification pour ajouter des soins"
        )

    # ── Créer facture (initiale ou complémentaire) ───────────────────────────
    # Rôle typique : Caisse
    if not perm('can_creer_facture'):
        result['creer_facture'] = _act(False, False)
    elif statut not in ('confirme', 'hospitalise', 'decharge'):
        result['creer_facture'] = _act(
            True, False,
            f"Statut actuel : {hosp.get_statut_display()}"
        )
    elif nb_saf_nf == 0:
        result['creer_facture'] = _act(True, False, "Aucun service à facturer")
    else:
        result['creer_facture'] = _act(True, True)

    # ── Installer le patient (confirme → hospitalise) ───────────────────────
    # Rôle typique : Infirmier, Major
    if not perm('can_installer_patient'):
        result['installer'] = _act(False, False)
    elif statut != 'confirme':
        result['installer'] = _act(
            True, False,
            f"Statut actuel : {hosp.get_statut_display()} — confirmé requis"
        )
    elif not facture_payee:
        result['installer'] = _act(True, False, "Facture non payée")
    elif not hosp.chambre_id:
        result['installer'] = _act(
            True, False,
            "Une chambre doit être attribuée avant d'hospitaliser"
        )
    else:
        result['installer'] = _act(True, True)

    # ── Décharger (hospitalise → decharge) ──────────────────────────────────
    # Rôle typique : Médecin, groupe Soins
    if not perm('can_decharger_patient'):
        result['decharger'] = _act(False, False)
    elif statut != 'hospitalise':
        result['decharger'] = _act(
            True, False,
            f"Statut actuel : {hosp.get_statut_display()} — hospitalisé requis"
        )
    elif not resume_ok:
        result['decharger'] = _act(
            True, False,
            "Résumé de décharge manquant (champ « Diagnostic de décharge » requis)"
        )
    else:
        result['decharger'] = _act(True, True)

    # ── Terminer le dossier (decharge → termine) ────────────────────────────
    # Rôle typique : Caisse, Admin
    if not perm('can_cloturer_dossier'):
        result['terminer'] = _act(False, False)
    elif statut != 'decharge':
        result['terminer'] = _act(
            True, False,
            f"Statut actuel : {hosp.get_statut_display()} — déchargé requis"
        )
    elif nb_saf_nf > 0:
        result['terminer'] = _act(
            True, False,
            f"{nb_saf_nf} service(s) non facturé(s)"
        )
    elif nb_fac_imp > 0:
        result['terminer'] = _act(
            True, False,
            f"{nb_fac_imp} facture(s) impayée(s)"
        )
    else:
        result['terminer'] = _act(True, True)

    # ── Annuler (brouillon/confirme/hospitalise → annule) ───────────────────
    # Rôle typique : Médecin, Accueil, Major
    if not perm('can_annuler_demande'):
        result['annuler'] = _act(False, False)
    elif statut not in ('brouillon', 'confirme', 'hospitalise'):
        result['annuler'] = _act(
            True, False,
            f"Statut actuel : {hosp.get_statut_display()} — annulation impossible depuis cet état"
        )
    else:
        result['annuler'] = _act(True, True)

    return result


def check_action(hosp, user, action_key):
    """
    Vérification serveur avant d'exécuter une transition.
    Retourne (ok: bool, erreur: str | None).
    Appelé par chaque helper _transition_* dans views.py.
    """
    actions = get_actions_disponibles(hosp, user)
    a = actions.get(action_key)
    if a is None:
        return False, "Action inconnue."
    if not a['enabled']:
        raison = a['raison_blocage'] or "Action non autorisée."
        return False, raison
    return True, None
