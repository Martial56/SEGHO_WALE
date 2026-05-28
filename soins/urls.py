from django.urls import path
from . import views

app_name = 'soins'

urlpatterns = [
    # Soins infirmiers
    path('patient-counts/', views.soins_patient_counts, name='patient_counts'),
    path('', views.soins_list, name='list'),
    path('nouveau/', views.soins_create, name='create'),
    path('<int:pk>/', views.soins_detail, name='detail'),
    path('<int:pk>/modifier/', views.soins_edit, name='edit'),
    path('<int:pk>/terminer/', views.soins_terminer, name='terminer'),

    # Liste des soins (procédures)
    path('procedures/', views.procedure_list, name='procedure_list'),
    path('procedures/nouveau/', views.procedure_create, name='procedure_create'),
    path('procedures/<int:pk>/', views.procedure_detail, name='procedure_detail'),
    path('procedures/<int:pk>/modifier/', views.procedure_edit, name='procedure_edit'),
    path('procedures/<int:pk>/facturer/', views.procedure_facturer, name='procedure_facturer'),
    path('procedures/<int:pk>/terminer/', views.procedure_terminer, name='procedure_terminer'),
    path('procedures/<int:pk>/annuler/', views.procedure_annuler, name='procedure_annuler'),

    # Rendez-vous dans le module soins
    path('rendez-vous/nouveau/', views.soins_rdv_create, name='rdv_create'),
    path('rendez-vous/', views.soins_rdv_list, name='rdv_list'),

    # Demandes d'examen
    path('examens/', views.demande_examen_list, name='demande_examen_list'),
    path('examens/nouveau/', views.demande_examen_create, name='demande_examen_create'),
    path('examens/<int:pk>/', views.demande_examen_detail, name='demande_examen_detail'),
    path('examens/<int:pk>/envoyer/', views.demande_examen_envoyer, name='demande_examen_envoyer'),
    path('examens/<int:pk>/terminer/', views.demande_examen_terminer, name='demande_examen_terminer'),
    path('examens/<int:pk>/annuler/', views.demande_examen_annuler, name='demande_examen_annuler'),

    # Maladies
    path('maladies/nouveau/', views.maladie_create, name='maladie_create'),

    # Actions sur un soin
    path('<int:pk>/enregistrer/', views.soins_creer_facture, name='creer_facture'),
    path('<int:pk>/administrer/', views.soins_administrer, name='administrer'),

    # Facturation depuis soins infirmiers (admin / ancien flux)
    path('<int:pk>/facturer/', views.soin_facturer, name='soin_facturer'),

    # Factures dans le module soins
    path('factures/<int:pk>/', views.soins_facture_detail, name='facture_detail'),
    path('factures/<int:pk>/paiement/', views.soins_facture_paiement, name='facture_paiement'),
    path('factures/<int:pk>/modifier/', views.soins_facture_edit, name='facture_edit'),
    path('factures/<int:pk>/valider/', views.soins_facture_valider, name='facture_valider'),
    path('factures/<int:pk>/payer/', views.soins_facture_payer, name='facture_payer'),
    path('factures/<int:pk>/imprimer/', views.soins_facture_print, name='facture_print'),
]
