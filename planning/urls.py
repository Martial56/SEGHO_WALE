from django.urls import path
from . import views

urlpatterns = [
    path('',                        views.planning_list,          name='planning_list'),
    path('courant/',                views.planning_courant,       name='planning_courant'),
    path('nouveau/',                views.planning_nouveau,       name='planning_nouveau'),
    path('mensuel/',                views.planning_mensuel,       name='planning_mensuel'),
    path('par-medecin/',            views.planning_par_medecin,   name='planning_par_medecin'),
    path('medecins.json',           views.planning_medecins_json, name='planning_medecins_json'),
    path('bureaux/',                views.planning_bureaux,       name='planning_bureaux'),
    path('bureaux/bureau/',         views.planning_bureau_save,   name='planning_bureau_save'),
    path('bureaux/bureau/<int:pk>/supprimer/', views.planning_bureau_delete, name='planning_bureau_delete'),
    path('bureaux/bureau/<int:pk>/ordre/',     views.planning_bureau_ordre,  name='planning_bureau_ordre'),
    path('bureaux/plage/',          views.planning_plage_save,    name='planning_plage_save'),
    path('bureaux/plage/<int:pk>/supprimer/',  views.planning_plage_delete,  name='planning_plage_delete'),
    path('stats/',                  views.planning_stats,         name='planning_stats'),
    path('<int:pk>/',               views.planning_detail,        name='planning_detail'),
    path('<int:pk>/modifier/',      views.planning_modifier,      name='planning_modifier'),
    path('<int:pk>/dupliquer/',     views.planning_dupliquer,     name='planning_dupliquer'),
    path('<int:pk>/publier/',       views.planning_publier,       name='planning_publier'),
    path('<int:pk>/supprimer/',           views.planning_supprimer,          name='planning_supprimer'),
    path('<int:pk>/export-excel/',        views.planning_export_excel,         name='planning_export_excel'),
    path('<int:pk>/sauvegarder-gabarit/', views.planning_gabarit_sauvegarder, name='planning_gabarit_sauvegarder'),
    path('<int:pk>/appliquer-gabarit/',   views.planning_gabarit_appliquer,   name='planning_gabarit_appliquer'),
    path('gabarit/<int:gabarit_pk>/supprimer/', views.planning_gabarit_supprimer, name='planning_gabarit_supprimer'),
]
