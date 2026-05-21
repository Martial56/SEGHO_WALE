from django.urls import path
from . import views

urlpatterns = [
    path('',                                          views.employe_list,          name='ressources_humaines_list'),
    path('dashboard/',                                views.rh_dashboard,          name='rh_dashboard'),
    path('organigramme/',                             views.rh_organigramme,       name='rh_organigramme'),
    path('nouveau/',                                  views.employe_nouveau,       name='rh_nouveau'),
    path('import/',                                   views.employe_import,        name='rh_import'),
    path('export/excel/',                             views.employe_export_excel,  name='rh_export_excel'),
    path('<int:pk>/',                                 views.employe_detail,        name='rh_detail'),
    path('<int:pk>/modifier/',                        views.employe_modifier,      name='rh_modifier'),
    path('<int:pk>/renouveler/',                      views.employe_renouveler,    name='rh_renouveler'),
    path('<int:pk>/fiche-pdf/',                       views.employe_fiche_pdf,     name='rh_fiche_pdf'),
    path('<int:pk>/document/upload/',                 views.employe_doc_upload,    name='rh_doc_upload'),
    path('<int:pk>/document/<int:doc_pk>/supprimer/', views.employe_doc_delete,    name='rh_doc_delete'),
    path('<int:pk>/info/sauvegarder/',                views.employe_info_save,     name='rh_info_save'),
    path('<int:pk>/info/<int:info_pk>/supprimer/',    views.employe_info_delete,   name='rh_info_delete'),
    path('annuaire/',                                 views.rh_annuaire,           name='rh_annuaire'),
    path('alertes/<int:alerte_id>/lue/',              views.alerte_marquer_lue,    name='rh_alerte_lue'),
    path('alertes/tout-lire/',                        views.alertes_tout_lire,     name='rh_alertes_tout_lire'),
    path('alertes/doc/<int:alerte_id>/lue/',          views.alerte_doc_lue,        name='rh_alerte_doc_lue'),

    # Configuration — Spécialités
    path('configuration/specialites/',                               views.specialite_list,          name='specialites'),
    path('configuration/specialites/nouveau/',                       views.specialite_create,        name='specialite_create'),
    path('configuration/specialites/<int:pk>/',                      views.specialite_detail,        name='specialite_detail'),
    path('configuration/specialites/<int:pk>/modifier/',             views.specialite_edit,          name='specialite_edit'),
    path('configuration/specialites/supprimer-selection/',           views.specialite_bulk_delete,   name='specialite_bulk_delete'),
    # Configuration — Départements
    path('configuration/departements/',                              views.departement_list_config,  name='departements'),
    path('configuration/departements/nouveau/',                      views.departement_create,       name='departement_create'),
    path('configuration/departements/<int:pk>/',                     views.departement_detail_config, name='departement_detail'),
    path('configuration/departements/<int:pk>/modifier/',            views.departement_edit,         name='departement_edit'),
    path('configuration/departements/supprimer-selection/',          views.departement_bulk_delete,  name='departement_bulk_delete'),
    # Configuration — Diplômes
    path('configuration/diplomes/',                                  views.diplome_list,             name='diplomes'),
    path('configuration/diplomes/nouveau/',                          views.diplome_create,           name='diplome_create'),
    path('configuration/diplomes/<int:pk>/',                         views.diplome_detail,           name='diplome_detail'),
    path('configuration/diplomes/<int:pk>/modifier/',                views.diplome_edit,             name='diplome_edit'),
    path('configuration/diplomes/supprimer-selection/',              views.diplome_bulk_delete,      name='diplome_bulk_delete'),
    # Configuration RH — Fonctions / Grades / Types de contrat
    path('configuration/fonctions/',    views.config_fonctions,       name='config_fonctions'),
    path('configuration/grades/',       views.config_grades,          name='config_grades'),
    path('configuration/types-contrat/',views.config_types_contrat,   name='config_types_contrat'),
    path('configuration/creation-rapide/', views.config_item_create_ajax, name='config_item_create_ajax'),
]
