from django.urls import path
from django.views.generic import RedirectView

from . import doublons_vues, fusion_vues, views

app_name = 'patients'


def _renvoi(vers):
    """Renvoi vers la page du module gynécologie, sous son adresse actuelle.

    Le module a d'abord vécu ici, puis a été refait dans `core` ; ces deux
    adresses en sont les vestiges. Elles restent déclarées, car la tuile du
    lanceur d'applications (Module.url_name = « patients:gynecologie_rdv ») et
    les favoris des utilisateurs y mènent encore : les retirer donnerait une page
    d'erreur. Elles ne font plus que renvoyer, il n'y a donc plus de code en
    double à maintenir.

    Renvoi temporaire et non permanent : un permanent se graverait dans le cache
    du navigateur, impossible à reprendre. `query_string` conserve les filtres
    d'un favori.
    """
    return RedirectView.as_view(pattern_name=vers, permanent=False, query_string=True)


urlpatterns = [
    path('', views.patient_list, name='list'),
    path('gynecologie/', _renvoi('gynecologie_list'), name='gynecologie_patients'),
    path('gynecologie/rendez-vous/', _renvoi('gynecologie_rdv'), name='gynecologie_rdv'),
    path('rendez-vous/', views.rdv_global_list, name='rdv_global'),
    path('rendez-vous/export/', views.rdv_export, name='rdv_export'),
    path('rendez-vous/nouveau/', views.rdv_create, name='rdv_create'),
    path('rendez-vous/<int:pk>/modifier/', views.rdv_edit, name='rdv_edit'),
    path('<int:pk>/info/', views.patient_info_json, name='patient_info'),
    path('recherche/', views.patient_search_json, name='patient_search'),
    path('nouveau/', views.patient_create, name='create'),
    path('<int:pk>/', views.patient_detail, name='detail'),
    path('<int:pk>/modifier/', views.patient_edit, name='edit'),
    path('<int:pk>/rendez-vous/', views.patient_rdv_list, name='rdv_list'),
    path('<int:pk>/consultations/', views.patient_consultation_list, name='consultation_list'),
    path('<int:pk>/soins/', views.patient_soin_list, name='soin_list'),
    path('<int:pk>/ordonnances/', views.patient_ordonnance_list, name='ordonnance_list'),
    path('<int:pk>/ordonnances/creer/', views.ordonnance_create, name='ordonnance_create'),
    path('<int:pk>/hospitalisations/', views.patient_hospitalisation_list, name='hospitalisation_list'),
    path('<int:pk>/examens-demandes/', views.patient_demande_examens_list, name='demande_examens_list'),
    path('<int:pk>/examens-resultats/', views.patient_resultat_examens_list, name='resultat_examens_list'),
    path('doublons/verifier/', views.doublons_verifier, name='doublons_verifier'),
    path('doublons/journaliser/', views.doublons_journaliser, name='doublons_journaliser'),
    # ── L'écran des doublons (étape 4a) ──────────────────────────────────
    # Les adresses fixes d'abord : `<str:cle>` attrape n'importe quel segment,
    # et prendrait « journaliser » pour un groupe à comparer.
    path('doublons/', doublons_vues.doublons_liste, name='doublons_liste'),
    path('doublons/fusions/', fusion_vues.fusion_journal, name='fusions'),
    path('doublons/fusions/<int:pk>/annuler/', fusion_vues.fusion_annuler,
         name='fusion_annuler'),
    path('doublons/journal/', doublons_vues.doublons_journal, name='doublons_journal'),
    path('doublons/masquees/', doublons_vues.doublons_masquees,
         name='doublons_masquees'),
    path('doublons/lots/', doublons_vues.doublons_lots, name='doublons_lots'),
    path('doublons/lots/preparer/', doublons_vues.doublons_lot_preparer,
         name='doublons_lot_preparer'),
    path('doublons/lots/<int:pk>/executer/', doublons_vues.doublons_lot_executer,
         name='doublons_lot_executer'),
    path('doublons/lots/<int:pk>/annuler/', doublons_vues.doublons_lot_annuler,
         name='doublons_lot_annuler'),
    path('doublons/supprimer/<int:pk>/', doublons_vues.doublons_supprimer,
         name='doublons_supprimer'),
    path('doublons/recalculer/', doublons_vues.doublons_recalculer,
         name='doublons_recalculer'),
    path('doublons/reafficher/<int:pk>/', doublons_vues.doublons_reafficher,
         name='doublons_reafficher'),
    path('doublons/<str:cle>/', doublons_vues.doublons_comparer,
         name='doublons_comparer'),
    path('doublons/<str:cle>/ecarter/', doublons_vues.doublons_ecarter,
         name='doublons_ecarter'),
    path('doublons/<str:cle>/reprendre/', doublons_vues.doublons_reprendre,
         name='doublons_reprendre'),
    path('doublons/<str:cle>/garder/<int:pk>/', doublons_vues.doublons_garder,
         name='doublons_garder'),
    path('doublons/<str:cle>/masquer/<int:pk>/', doublons_vues.doublons_masquer,
         name='doublons_masquer'),
    path('doublons/<str:cle>/fusionner/<int:pk>/', fusion_vues.fusion_ecran,
         name='fusionner'),
    path('export/', views.export_patients, name='export_patients'),
    path('import/', views.import_patients, name='import_patients'),
    path('import/modele/', views.patients_modele_excel, name='patients_modele'),
    path('pathologies/', views.pathologie_list, name='pathologie_list'),
    path('pathologies/nouveau/', views.pathologie_create, name='pathologie_create'),
    path('pathologies/<int:pk>/modifier/', views.pathologie_edit, name='pathologie_edit'),
    path('pathologies/<int:pk>/supprimer/', views.pathologie_delete, name='pathologie_delete'),
    # Types de visite curative : configuration rattachée aux rendez-vous
    # (le pendant gynécologique vit dans core/urls.py sous gynecologie/types-visite/).
    path('types-visite-curative/', views.typevisitecurative_list, name='typevisitecurative_list'),
    path('types-visite-curative/nouveau/', views.typevisitecurative_create, name='typevisitecurative_create'),
    path('types-visite-curative/<int:pk>/modifier/', views.typevisitecurative_edit, name='typevisitecurative_edit'),
    path('types-visite-curative/<int:pk>/supprimer/', views.typevisitecurative_delete, name='typevisitecurative_delete'),
    path('pathologies/export/', views.export_pathologies, name='export_pathologies'),
    path('pathologies/import/', views.import_pathologies, name='import_pathologies'),
]
