from django.urls import path
from . import views

urlpatterns = [
    path('',                                    views.pharmacie_accueil,        name='pharmacie_accueil'),
    path('<str:pharmacie>/',                    views.pharmacie_dashboard,      name='pharmacie_dashboard'),
    path('<str:pharmacie>/stock/',              views.pharmacie_stock,          name='pharmacie_stock'),
    path('<str:pharmacie>/ordonnances/',        views.pharmacie_ordonnances,    name='pharmacie_ordonnances'),
    path('<str:pharmacie>/dispenser/<int:pk>/', views.pharmacie_dispenser,      name='pharmacie_dispenser'),
    path('<str:pharmacie>/demande/',            views.pharmacie_demande,        name='pharmacie_demande'),
    path('<str:pharmacie>/journal/',            views.pharmacie_journal,        name='pharmacie_journal'),
    path('<str:pharmacie>/caisse/',            views.pharmacie_caisse,   name='pharmacie_caisse'),
    path('<str:pharmacie>/caisse/<int:pk>/',   views.pharmacie_ticket,   name='pharmacie_ticket'),
    path('<str:pharmacie>/recette/',           views.pharmacie_recette,  name='pharmacie_recette'),
    path('<str:pharmacie>/rapport/', views.pharmacie_rapport_journalier, name='pharmacie_rapport_journalier'),
    path('<str:pharmacie>/livraisons/',         views.pharmacie_livraisons,     name='pharmacie_livraisons'),
    path('<str:pharmacie>/livraisons/<int:pk>/confirmer/', views.pharmacie_confirmer_livraison, name='pharmacie_confirmer_livraison'),
    path('<str:pharmacie>/fiche/<int:pk>/',              views.pharmacie_fiche_dispensation,    name='pharmacie_fiche_dispensation'),
    path('<str:pharmacie>/alertes/',                     views.pharmacie_alertes_reappro,        name='pharmacie_alertes_reappro'),
    path('<str:pharmacie>/peremptions/',                 views.pharmacie_peremptions,            name='pharmacie_peremptions'),
    path('<str:pharmacie>/retours/',                     views.pharmacie_retours,                name='pharmacie_retours'),
    path('<str:pharmacie>/inventaire/',                  views.pharmacie_inventaire_list,        name='pharmacie_inventaire_list'),
    path('<str:pharmacie>/inventaire/nouveau/',          views.pharmacie_inventaire_nouveau,     name='pharmacie_inventaire_nouveau'),
    path('<str:pharmacie>/inventaire/<int:pk>/',         views.pharmacie_inventaire_detail,      name='pharmacie_inventaire_detail'),
    path('<str:pharmacie>/rapport-mensuel/',             views.pharmacie_rapport_mensuel,        name='pharmacie_rapport_mensuel'),
    path('<str:pharmacie>/rapport-dispensation/',        views.pharmacie_rapport_dispensation,   name='pharmacie_rapport_dispensation'),
    path('<str:pharmacie>/comparaison/',                 views.pharmacie_comparaison,            name='pharmacie_comparaison'),
]
