from django.urls import path
from . import views

urlpatterns = [
    # ── Vues existantes ──────────────────────────────────────────────────────
    path('',                             views.conge_list,                name='conge_list'),
    path('nouveau/',                     views.conge_nouveau,             name='conge_nouveau'),
    path('<int:pk>/',                    views.conge_detail,              name='conge_detail'),
    path('<int:pk>/approuver/',          views.conge_approuver,           name='conge_approuver'),
    path('<int:pk>/refuser/',            views.conge_refuser,             name='conge_refuser'),
    path('<int:pk>/annuler/',            views.conge_annuler,             name='conge_annuler'),
    path('<int:pk>/en-cours/',           views.conge_marquer_en_cours,    name='conge_en_cours'),
    path('<int:pk>/terminer/',           views.conge_terminer,            name='conge_terminer'),

    # ── Nouvelles vues ────────────────────────────────────────────────────────
    path('tableau-de-bord/',             views.conge_dashboard,           name='conge_dashboard'),
    path('calendrier/',                  views.conge_calendrier,          name='conge_calendrier'),
    path('mes-conges/',                  views.conge_mes_conges,          name='conge_mes_conges'),
    path('soldes/',                      views.conge_soldes,              name='conge_soldes'),
    path('soldes/recalcul/',             views.conge_solde_recalc,        name='conge_solde_recalc'),
    path('soldes/report-annuel/',        views.conge_report_solde_annuel, name='conge_report_solde_annuel'),
    path('<int:pk>/bon/',                views.conge_bon,                 name='conge_bon'),
    path('export/csv/',                  views.conge_export_csv,          name='conge_export_csv'),

    # ── Validation service ────────────────────────────────────────────────────
    path('<int:pk>/valider-service/',    views.conge_valider_service,     name='conge_valider_service'),
    path('<int:pk>/fractionner/',        views.conge_fractionner,         name='conge_fractionner'),
    path('<int:pk>/attestation/',        views.conge_attestation,         name='conge_attestation'),
    path('<int:pk>/prolonger/',          views.conge_prolonger,           name='conge_prolonger'),
    path('<int:pk>/absence-injustifiee/',views.conge_absence_injustifiee, name='conge_absence_injustifiee'),

    # ── Statistiques & Planning ───────────────────────────────────────────────
    path('stats/services/',              views.conge_stats_service,       name='conge_stats_service'),
    path('planning/equipe/',             views.conge_planning_equipe,     name='conge_planning_equipe'),
    path('rapport/',                     views.conge_rapport,             name='conge_rapport'),

    # ── Notifications ─────────────────────────────────────────────────────────
    path('notifs/lire/',                 views.conge_notifs_lire,         name='conge_notifs_lire'),
    path('notifs/<int:pk>/lire/',        views.conge_notif_lire_une,      name='conge_notif_lire_une'),
]
