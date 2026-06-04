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
    path('<int:pk>/badge/',                           views.employe_badge,         name='rh_badge'),
    path('<int:pk>/qrcode/',                          views.employe_qrcode,        name='rh_qrcode'),
    path('<int:pk>/biometric/save/',                  views.employe_biometric_save,name='rh_biometric_save'),
    path('<int:pk>/document/upload/',                 views.employe_doc_upload,    name='rh_doc_upload'),
    path('<int:pk>/document/<int:doc_pk>/supprimer/', views.employe_doc_delete,    name='rh_doc_delete'),
    path('<int:pk>/info/sauvegarder/',                views.employe_info_save,     name='rh_info_save'),
    path('<int:pk>/info/<int:info_pk>/supprimer/',    views.employe_info_delete,   name='rh_info_delete'),
    path('annuaire/',                                 views.rh_annuaire,           name='rh_annuaire'),
    path('registre/',                                 views.rh_registre,           name='rh_registre'),
    path('registre/export/',                          views.rh_registre_export,    name='rh_registre_export'),
    path('alertes/<int:alerte_id>/lue/',              views.alerte_marquer_lue,    name='rh_alerte_lue'),
    path('alertes/tout-lire/',                        views.alertes_tout_lire,     name='rh_alertes_tout_lire'),
    path('alertes/doc/<int:alerte_id>/lue/',          views.alerte_doc_lue,        name='rh_alerte_doc_lue'),
]
