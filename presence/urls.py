from django.urls import path
from . import views

urlpatterns = [
    path('',                    views.presence_registre,       name='presence_registre'),
    path('deverrouiller/',      views.presence_deverrouiller,  name='presence_deverrouiller'),
    path('recap/',              views.presence_recap_mensuel,  name='presence_recap'),
    path('stats/',              views.presence_stats,          name='presence_stats'),
    path('employe/<int:pk>/',   views.presence_employe,        name='presence_employe'),
    path('rapport/',            views.presence_rapport,        name='presence_rapport'),
    path('rapport/export/',     views.presence_rapport_export, name='presence_rapport_export'),
    path('parametres/',         views.presence_parametres,     name='presence_parametres'),
    path('parametres/medecins/', views.presence_parametres, {'type_permanence': 'medecins'},
         name='presence_parametres_medecins'),
    # Kiosque
    path('pointage/',           views.presence_pointage,       name='presence_pointage'),
    path('pointage/chercher/',  views.presence_chercher,       name='presence_chercher'),
    path('pointage/pointer/',   views.presence_pointer,        name='presence_pointer'),
]
