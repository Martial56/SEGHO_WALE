from django.urls import path
from . import views

urlpatterns = [
    path('',                          views.stock_dashboard,      name='stock_dashboard'),

    # Produits
    path('produits/',                 views.produits_list,         name='stock_produits'),
    path('produits/nouveau/',         views.produit_create,        name='stock_produit_create'),
    path('produits/<int:pk>/',        views.produit_detail,        name='stock_produit_detail'),
    path('produits/<int:pk>/modifier/', views.produit_edit,        name='stock_produit_edit'),
    path('produits/export/',          views.export_stock_excel,    name='stock_export_excel'),

    # Mouvements
    path('mouvements/',               views.mouvements_list,       name='stock_mouvements'),
    path('mouvements/nouveau/',       views.mouvement_create,      name='stock_mouvement_create'),

    # Transfert
    path('transfert/',                views.transfert_create,      name='stock_transfert'),

    # Commandes
    path('commandes/',                views.commandes_list,        name='stock_commandes'),
    path('commandes/nouvelle/',       views.commande_create,       name='stock_commande_create'),
    path('commandes/<int:pk>/',       views.commande_detail,       name='stock_commande_detail'),
    path('commandes/<int:pk>/ligne/ajouter/', views.commande_ajouter_ligne, name='stock_commande_ajouter_ligne'),
    path('commandes/<int:pk>/lignes/lot/',    views.commande_ajouter_lot,   name='stock_commande_ajouter_lot'),
    path('commandes/<int:pk>/ligne/<int:ligne_pk>/supprimer/', views.commande_supprimer_ligne, name='stock_commande_supprimer_ligne'),
    path('commandes/<int:pk>/receptionner/', views.commande_receptionner, name='stock_commande_receptionner'),
    path('commandes/<int:pk>/envoyer/',     views.commande_envoyer,      name='stock_commande_envoyer'),
    path('commandes/<int:pk>/modifier/',    views.commande_modifier,     name='stock_commande_modifier'),
    path('commandes/<int:pk>/imprimer/',   views.commande_print,        name='stock_commande_print'),

    # Inventaire
    path('inventaire/',               views.inventaire_list,       name='stock_inventaire_list'),
    path('inventaire/nouveau/',       views.inventaire_create,     name='stock_inventaire_create'),
    path('inventaire/<int:pk>/',      views.inventaire_detail,     name='stock_inventaire_detail'),

    # Péremptions
    path('peremptions/',              views.peremptions_list,      name='stock_peremptions'),

    # Valorisation
    path('valorisation/',             views.valorisation,          name='stock_valorisation'),

    # Rapports
    path('rapports/consommation/',    views.rapports_consommation, name='stock_rapports_consommation'),
    path('rapports/dotations/',       views.rapports_dotations,    name='stock_rapports_dotations'),
    path('rapports/besoins/',         views.rapports_besoins,      name='stock_rapports_besoins'),
    path('rapports/besoins/print/',   views.rapports_besoins_print, name='stock_rapports_besoins_print'),
    # Fiches de besoins
    path('fiches/',                    views.fiche_list,       name='stock_fiche_list'),
    path('fiches/nouvelle/',           views.fiche_create,     name='stock_fiche_create'),
    path('fiches/<int:pk>/',           views.fiche_detail,     name='stock_fiche_detail'),
    path('fiches/<int:pk>/modifier/',  views.fiche_edit,       name='stock_fiche_edit'),
    path('fiches/<int:pk>/soumettre/', views.fiche_soumettre,  name='stock_fiche_soumettre'),
    path('fiches/<int:pk>/valider/',   views.fiche_valider,    name='stock_fiche_valider'),
    path('fiches/<int:pk>/imprimer/',       views.fiche_print,           name='stock_fiche_print'),
    path('fiches/<int:pk>/envoyer-achats/', views.fiche_envoyer_achats,  name='stock_fiche_envoyer_achats'),
    path('rapports/indicateurs/',     views.rapports_indicateurs,  name='stock_rapports_indicateurs'),

    # Fournisseurs
    path('fournisseurs/',                views.fournisseurs_list,    name='stock_fournisseurs'),
    path('fournisseurs/nouveau/',        views.fournisseur_create,   name='stock_fournisseur_create'),
    path('fournisseurs/<int:pk>/modifier/', views.fournisseur_edit, name='stock_fournisseur_edit'),

    # Catégories AJAX
    path('dotation/',                  views.dotation_list,    name='stock_dotation_list'),
    path('dotation/nouvelle/',         views.dotation_creer,   name='stock_dotation_creer'),
    path('dotation/<int:pk>/',         views.dotation_detail,  name='stock_dotation_detail'),
    path('dotation/<int:pk>/valider/', views.dotation_valider, name='stock_dotation_valider'),
    path('categories/ajax/',          views.categorie_create_ajax, name='stock_categorie_ajax'),

    # Configuration : Type de produit / Catégorie de produit
    path('config/types/',                        views.stock_types_produit,   name='stock_types_produit'),
    path('config/categories/',                   views.stock_categories_list, name='stock_categories_list'),
    path('config/categories/nouveau/',            views.stock_categorie_create, name='stock_categorie_create'),
    path('config/categories/<int:pk>/modifier/',  views.stock_categorie_edit,   name='stock_categorie_edit'),
    path('config/categories/<int:pk>/supprimer/', views.stock_categorie_delete, name='stock_categorie_delete'),

    # Réceptions achats à intégrer dans le stock
    path('receptions-achats/',                   views.receptions_a_integrer, name='stock_receptions_a_integrer'),
    path('receptions-achats/<int:pk>/integrer/', views.integrer_reception,    name='stock_integrer_reception'),

    # Nouvelles fonctionnalités
    path('peremptions/eliminer/',                views.elimination_create,         name='stock_elimination_create'),
    path('retours/creer/',                       views.retour_create,              name='stock_retour_create'),
    path('fiches/generer-auto/',                 views.besoins_generer_auto,       name='stock_besoins_generer_auto'),
    path('rapports/peremptions/',                views.rapports_peremptions,       name='stock_rapports_peremptions'),
    path('rapports/bilan/',                      views.rapports_bilan_mensuel,     name='stock_rapports_bilan'),
    path('rapports/fournisseurs-prix/',          views.rapports_fournisseurs_prix, name='stock_rapports_fournisseurs_prix'),

    # Unités de mesure
    path('unites/', views.unites_list, name='stock_unites'),
    path('unites/nouveau/', views.unite_create, name='stock_unite_create'),
    path('unites/<int:pk>/', views.unite_detail, name='stock_unite_detail'),
    path('unites/<int:pk>/modifier/', views.unite_edit, name='stock_unite_edit'),
    path('unites/<int:pk>/supprimer/', views.unite_delete, name='stock_unite_delete'),
    path('unites/supprimer-selection/', views.unite_bulk_delete, name='stock_unite_bulk_delete'),

    # Catégories d'unités de mesure
    path('unites/categories/', views.categories_unites_list, name='stock_categories_unites'),
    path('unites/categories/nouveau/', views.categorie_unite_create, name='stock_categorie_unite_create'),
    path('unites/categories/<int:pk>/', views.categorie_unite_detail, name='stock_categorie_unite_detail'),
    path('unites/categories/<int:pk>/modifier/', views.categorie_unite_edit, name='stock_categorie_unite_edit'),
    path('unites/categories/<int:pk>/supprimer/', views.categorie_unite_delete, name='stock_categorie_unite_delete'),
    path('unites/categories/supprimer-selection/', views.categorie_unite_bulk_delete, name='stock_categorie_unite_bulk_delete'),

    # Export / Import unités de mesure
    path('export/unites/',            views.export_unites,            name='stock_export_unites'),
    path('export/categories-unites/', views.export_categories_unites, name='stock_export_categories_unites'),
    path('importer/unites/',            views.import_unites,            name='stock_import_unites'),
    path('importer/categories-unites/', views.import_categories_unites, name='stock_import_categories_unites'),
]
