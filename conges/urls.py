from django.urls import path
from . import views

urlpatterns = [
    # ── Liste & Détail ───────────────────────────────────────────────────────
    path('',                             views.conge_list,                name='conge_list'),
    path('nouveau/',                     views.conge_nouveau,             name='conge_nouveau'),
    path('employe/<int:emp_pk>/info/',   views.conge_employe_info,        name='conge_employe_info'),
    path('<int:pk>/',                    views.conge_detail,              name='conge_detail'),

    # ── Actions RH sur un congé ───────────────────────────────────────────────
    path('<int:pk>/annuler/',            views.conge_annuler,             name='conge_annuler'),
    path('<int:pk>/en-cours/',           views.conge_marquer_en_cours,    name='conge_en_cours'),
    path('<int:pk>/terminer/',           views.conge_terminer,            name='conge_terminer'),
    path('<int:pk>/prolonger/',          views.conge_prolonger,           name='conge_prolonger'),
    path('<int:pk>/absence-injustifiee/',views.conge_absence_injustifiee, name='conge_absence_injustifiee'),
    path('<int:pk>/fractionner/',        views.conge_fractionner,         name='conge_fractionner'),

    # ── Documents ─────────────────────────────────────────────────────────────
    path('<int:pk>/bon/',                views.conge_bon,                 name='conge_bon'),
    path('<int:pk>/attestation/',        views.conge_attestation,         name='conge_attestation'),

    # ── Tableaux de bord & Suivi ──────────────────────────────────────────────
    path('tableau-de-bord/',             views.conge_dashboard,           name='conge_dashboard'),
    path('suivi-retours/',               views.conge_suivi_retours,       name='conge_suivi_retours'),
    path('historique/<int:emp_pk>/',     views.conge_historique_employe,  name='conge_historique_employe'),
    path('calendrier/',                  views.conge_calendrier,          name='conge_calendrier'),
    path('planning/equipe/',             views.conge_planning_equipe,     name='conge_planning_equipe'),

    # ── Soldes & Rapports ─────────────────────────────────────────────────────
    path('soldes/',                      views.conge_soldes,              name='conge_soldes'),
    path('soldes/recalcul/',             views.conge_solde_recalc,        name='conge_solde_recalc'),
    path('soldes/report-annuel/',        views.conge_report_solde_annuel, name='conge_report_solde_annuel'),
    path('stats/services/',              views.conge_stats_service,       name='conge_stats_service'),
    path('rapport/',                     views.conge_rapport,             name='conge_rapport'),
    path('direction/',                   views.conge_direction,           name='conge_direction'),
    path('export/csv/',                  views.conge_export_csv,          name='conge_export_csv'),

    # ── Notifications ─────────────────────────────────────────────────────────
    path('notifs/lire/',                 views.conge_notifs_lire,         name='conge_notifs_lire'),
    path('notifs/<int:pk>/lire/',        views.conge_notif_lire_une,      name='conge_notif_lire_une'),
]
