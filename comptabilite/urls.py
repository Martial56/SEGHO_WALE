from django.urls import path

from . import views, vues_compta, vues_etats

app_name = 'comptabilite'

urlpatterns = [
    path('caisse/', views.ma_caisse, name='ma_caisse'),
    path('caisse/ouvrir/', views.ouvrir, name='ouvrir'),
    path('sessions/<int:pk>/', views.session_detail, name='session'),
    path('sessions/<int:pk>/cloturer/', views.cloturer, name='cloturer'),
    path('sessions/<int:pk>/valider/', views.valider, name='valider'),
    path('sessions/<int:pk>/imprimer/', views.session_imprimer, name='imprimer'),
    path('sessions/<int:pk>/sortie/', views.sortie_creer, name='sortie_creer'),
    path('sorties/<int:pk>/decider/', views.sortie_decider, name='sortie_decider'),
    path('sorties/<int:pk>/annuler/', views.sortie_annuler, name='sortie_annuler'),
    path('gratuites/', views.gratuites, name='gratuites'),
    path('configuration/motifs/<str:nature>/', views.motifs, name='motifs'),
    path('configuration/motifs/<str:nature>/<int:pk>/', views.motifs, name='motif_modifier'),
    path('ecritures/', vues_compta.ecritures, name='ecritures'),
    path('ecritures/<int:pk>/', vues_compta.ecriture_detail, name='ecriture'),
    path('ecritures/<int:pk>/action/', vues_compta.ecriture_action, name='ecriture_action'),
    path('ecritures/operation-diverse/', vues_compta.od_saisie, name='od_saisie'),
    path('configuration/plan-comptable/', vues_compta.plan_comptable, name='plan_comptable'),
    path('configuration/plan-comptable/<int:pk>/', vues_compta.plan_comptable, name='compte_modifier'),
    path('configuration/correspondances/', vues_compta.correspondances, name='correspondances'),
    path('etats/', vues_etats.etats, name='etats'),
    path('etats/<str:code>/', vues_etats.etat, name='etat'),
    path('journees/', views.journees, name='journees'),
    path('journees/<int:pk>/', views.journee_detail, name='journee'),
    path('journees/<int:pk>/cloturer/', views.journee_cloturer, name='journee_cloturer'),
    path('journees/<int:pk>/rouvrir/', views.journee_rouvrir, name='journee_rouvrir'),
]
