"""Champs des registres de rendez-vous (CPN, accouchement, post-natale, curatif).

Les onglets du formulaire de rendez-vous n'ont pas de colonne en base : tout ce
qui y est saisi part dans le JSON du registre correspondant, sous le nom même du
champ du formulaire (cf. `patients.utils.save_registres`). Ces champs échappent
donc à la découverte automatique faite sur le modèle, et n'étaient proposés ni au
filtre ni au regroupement personnalisés — c'est ce que cette déclaration corrige.

Chaque entrée est un quadruplet (nom du champ, libellé, type, choix) :

* **nom** est à la fois le nom de l'entrée du formulaire et la clé JSON ; le
  chemin de requête s'en déduit (`registre_cpn__donnees__cpn_statut_vat`).
* **type** suit les catégories de `core.listing.OPERATEURS`. Deux d'entre elles
  sont propres au JSON : `date_json` et `nombre_json`. Une valeur JSON est
  toujours du texte, si bien que comparer des nombres par `>` reviendrait à les
  comparer lettre par lettre (« 9 » passerait pour plus grand que « 12 ») : ces
  catégories n'offrent donc que les opérateurs qui restent justes.
* **choix** reprend les valeurs proposées par le formulaire (listes, boutons
  radio, cases à cocher), ce qui permet d'afficher « Positif » plutôt que
  « positif » et de proposer une liste déroulante dans le constructeur de
  conditions.

Fichier obtenu en relevant les champs des deux formulaires de rendez-vous
(gynécologie et patients, qui portent les mêmes onglets). À compléter à la main
si un champ est ajouté au formulaire.
"""

#: Registre porteur de chaque groupe de champs.
REGISTRES = {
    'CPN': 'registre_cpn',
    'Accouchement': 'registre_accouchement',
    'Post-natale': 'registre_postnatale',
    'Curatif': 'registre_curatif',
}


#: Onglet « CPN » → registre_cpn.donnees (96 champs)
CHAMPS_CPN = [
    # Antécédents
    ('cpn_avortements', 'Avortements', 'nombre_json', ()),
    ('cpn_bdcf', 'BDCF', 'texte', ()),
    ('cpn_cesariennes', 'Césariennes', 'nombre_json', ()),
    ('cpn_atcd_chirurgicaux', 'Chirurgicaux', 'texte', ()),
    ('cpn_ddr', 'D.D.R.', 'date_json', ()),
    ('cpn_date_derniere_cpn', 'Date de la dernière CPN', 'date_json', ()),
    ('cpn_atcd_diabete', 'Diabète', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_enfants_decedes', 'Enfants décédés', 'nombre_json', ()),
    ('cpn_enfants_vivants', 'Enfants vivants', 'nombre_json', ()),
    ('cpn_gestite', 'Gestité', 'nombre_json', ()),
    ('cpn_atcd_gyneco', 'Gynéco-obstétricaux', 'texte', ()),
    ('cpn_atcd_hta', 'HTA', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_numero_depistage', 'Numéro de dépistage', 'texte', ()),
    ('cpn_parite', 'Parité', 'nombre_json', ()),
    ('cpn_proposition_test_vih', 'Proposition de test VIH', 'choix', (('propose', 'Proposé'), ('accepte', 'Accepté'), ('refuse', 'Refusé'))),
    ('cpn_retesting', 'Retesting', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_semaines_amenorrhee', 'Semaines d\'aménorrhée', 'nombre_json', ()),
    ('cpn_terme_prevu', 'Terme prévu le', 'date_json', ()),
    ('cpn_toxemie', 'Toxémie gravidique', 'texte', ()),
    # Constantes physiques
    ('cpn_date_vat1', 'Date du VAT 1', 'date_json', ()),
    ('cpn_date_vat2', 'Date du VAT 2', 'date_json', ()),
    ('cpn_date_vat_rappel', 'Date VAT rappel', 'date_json', ()),
    ('cpn_freq_resp', 'Fréquence respiratoire', 'texte', ()),
    ('cpn_imc', 'IMC', 'texte', ()),
    ('cpn_perimetre_brachial', 'Périmètre Brachial', 'texte', ()),
    ('cpn_perimetre_brachial_cm', 'Périmètre Brachial (cm)', 'texte', ()),
    ('cpn_poids', 'Poids', 'texte', ()),
    ('cpn_pouls', 'Pouls', 'texte', ()),
    ('cpn_statut_vat', 'Statut VAT', 'choix', (('0', 'Non vaccinée'), ('1', 'VAT1'), ('2', 'VAT2'), ('3', 'VAT3'), ('4', 'VAT4'), ('5', 'VAT5'))),
    ('cpn_statut_vih_accueil', 'Statut VIH à l\'accueil', 'choix', (('inconnu', 'Inconnu'), ('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cpn_ta_droit', 'TA Bras droit (mmHg)', 'texte', ()),
    ('cpn_ta_gauche', 'TA Bras gauche (mmHg)', 'texte', ()),
    ('cpn_taille', 'Taille', 'texte', ()),
    ('cpn_temperature', 'Température', 'texte', ()),
    # Données administratives
    ('cpn_numero_gestante', 'Numéro gestante de la visite', 'texte', ()),
    ('cpn_report_numero', 'Report numéro gestante précédent', 'texte', ()),
    # Examen général :
    ('cpn_examen_general_autres', 'Autres', 'texte', ()),
    ('cpn_conjonctives', 'Conjonctives', 'texte', ()),
    ('cpn_seins', 'Seins', 'texte', ()),
    ('cpn_varices', 'Varices', 'texte', ()),
    ('cpn_vergetures', 'Vergetures', 'texte', ()),
    ('cpn_oedemes', 'Œdèmes', 'texte', ()),
    # Examen obstétrical :
    ('cpn_age_gestationnel', 'Age gestationnel', 'texte', ()),
    ('cpn_anemie', 'Anémie Clinique', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_autres_medicaments', 'Autres médicaments', 'texte', ()),
    ('cpn_conseil_nutritionnel', 'Conseil nutritionnel', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_conseil_pf', 'Conseil PF', 'choix', (('1', 'Oui'),)),
    ('cpn_conseil_sante_sexuelle', 'Conseil santé sexuelle et reproductive', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_date_prochain_rdv', 'Date du prochain RDV', 'date_json', ()),
    ('cpn_etat_nutritionnel', 'Etat nutritionnel', 'choix', (('bon', 'Bon'), ('moyen', 'Moyen'), ('mauvais', 'Mauvais'))),
    ('cpn_examens_echo', 'Examens échographiques ou radiologiques', 'texte', ()),
    ('cpn_hu', 'H.U.', 'texte', ()),
    ('cpn_methode_souhaitee', 'Méthode souhaitée', 'choix', (('condom', 'Condom'), ('pilule', 'Pilule'), ('diu', 'DIU'), ('injectable', 'Injectable'), ('implant', 'Implant'), ('sterilisation', 'Stérilisation'))),
    ('cpn_po', 'P.O.', 'texte', ()),
    ('cpn_pathologies_associees', 'Pathologies associées', 'texte', ()),
    ('cpn_presentation', 'Présentation', 'texte', ()),
    ('cpn_resultat_consultation', 'Résultat consultation', 'choix', (('normale', 'Gross. normale'), ('risque', 'Gross. à risque'))),
    ('cpn_service_nutritionnel', 'Service nutritionnel', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_tv', 'T.V.', 'texte', ()),
    # Examens biologiques :
    ('cpn_albumine', 'Albumine', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cpn_annonce_resultat', 'Annonce du résultat', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_autres_examens_bio', 'Autres examens biologiques', 'texte', ()),
    ('cpn_charge_virale', 'Charge virale ≤ à 1000 copies/ml', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_depistage_conjoint', 'Dépistage VIH du conjoint', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_electrophorese', 'Électrophorèse et l\'hémoglobine', 'texte', ()),
    ('cpn_aghbs_demande', 'Examen AgHBs demandé', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_glycemie_demande', 'Examen glycémie demandé', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_groupe_sanguin', 'Group sanguin Rhésus', 'texte', ()),
    ('cpn_nitrite', 'Nitrite dans l\'urine/ECBU', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cpn_prelevement_charge_virale', 'Prélèvement pour la charge virale', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_resultat_aghbs', 'Résultat AgHBs', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    ('cpn_resultat_vih', 'Résultat du test VIH', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    ('cpn_resultat_glycemie', 'Résultat glycémie', 'texte', ()),
    ('cpn_aghbs_res_recu', 'Résultat reçu (AgHBs)', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_glycemie_res_recu', 'Résultat reçu (glycémie)', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cpn_syphilis_res_recu', 'Résultat reçu (Syphilis)', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_resultat_syphilis', 'Résultat Syphilis', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    ('cpn_serologie_rubeole', 'Sérologie Rubéole', 'texte', ()),
    ('cpn_serologie_toxo', 'Sérologie toxoplasmose', 'texte', ()),
    ('cpn_statut_sero_conjoint', 'Statut sérologique du conjoint', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    ('cpn_sucre', 'Sucre', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cpn_taux_hemoglobine', 'Taux d\'hémoglobine', 'texte', ()),
    ('cpn_syphilis_demande', 'Test Syphilis demandé', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    # Prescription
    ('cpn_ctx', 'CTX', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_deparasitant', 'Déparasitant', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_fer', 'Fer', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_fluor', 'Fluor', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_folates', 'FOLATES', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_initiation_arv', 'Initiation ARV', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_milda', 'MILDA', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_remarques', 'Remarques', 'texte', ()),
    ('cpn_sp1', 'SP1', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_sp2', 'SP2', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_sp3', 'SP3', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_sp4', 'SP4', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cpn_sp5', 'SP5 & Plus', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
]

#: Onglet « Accouchement » → registre_accouchement.donnees (120 champs)
CHAMPS_ACCOUCHEMENT = [
    # Accouchement et délivrance
    ('acc_complications_obst', 'Complications obstétricales', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_delivrance_a', 'Délivrance à', 'texte', ()),
    ('acc_etat_conjonctives', 'Etat des conjonctives', 'texte', ()),
    ('acc_examen', 'Examen', 'texte', ()),
    ('acc_globe_uterin', 'Globe utérin', 'texte', ()),
    ('acc_heure_delivrance', 'Heure', 'texte', ()),
    ('acc_imc_post', 'IMC (après accouchement)', 'nombre_json', ()),
    ('acc_membranes', 'Membranes', 'texte', ()),
    ('acc_mode_accouchement', 'Mode d\'accouchement', 'choix', (('voie_basse', 'Voie Basse'), ('cesarienne', 'Césarienne'))),
    ('acc_mode_expulsion', 'Mode d\'expulsion', 'texte', ()),
    ('acc_mode_delivrance', 'Mode de délivrance', 'choix', (('tcc', 'TCC'), ('normale', 'Normale'), ('artificielle', 'Artificielle'))),
    ('acc_nombre_vo', 'Nombre de V.O', 'nombre_json', ()),
    ('acc_particularite', 'Particularité', 'texte', ()),
    ('acc_perimetre_brachial_post', 'Périmètre brachial (après accouchement)', 'texte', ()),
    ('acc_poids_placenta', 'Poids de la placenta', 'nombre_json', ()),
    ('acc_pouls_post', 'Pouls après accouchement', 'nombre_json', ()),
    ('acc_prise_en_charge_hppi', 'Prise en charge des HPPI', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_revision_uterine', 'Révision utérine', 'choix', (('1', 'Oui'),)),
    ('acc_saignements_vulvaires', 'Saignements vulvaires', 'texte', ()),
    ('acc_ta_droit_post', 'TA bras droit (après accouchement)', 'texte', ()),
    ('acc_ta_gauche_post', 'TA bras gauche (après accouchement)', 'texte', ()),
    ('acc_type_avortement', 'Type d\'avortement', 'choix', (('spontane', 'Spontané'), ('provoque', 'Provoqué'), ('aucun', 'Aucun'))),
    # Antécédents médicaux
    ('acc_atcd_autres', 'Autres', 'texte', ()),
    ('acc_avortements', 'Avortements', 'nombre_json', ()),
    ('acc_cesariennes', 'Césariennes', 'nombre_json', ()),
    ('acc_atcd_chirurgicaux', 'Chirurgicaux', 'texte', ()),
    ('acc_atcd_diabete', 'Diabète', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_enfants_decedes', 'Enfants décédés', 'nombre_json', ()),
    ('acc_enfants_vivants', 'Enfants vivants', 'nombre_json', ()),
    ('acc_gemelite', 'Gémellité', 'nombre_json', ()),
    ('acc_gestite', 'Gestité', 'nombre_json', ()),
    ('acc_atcd_hta', 'HTA', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_lieu_accouchement', 'Lieu d\'accouchement', 'choix', (('cs', 'Centre de santé'), ('hopital', 'Hôpital'), ('domicile', 'Domicile'), ('en_route', 'En route'))),
    ('acc_numero_pec', 'Numéro PEC', 'texte', ()),
    ('acc_parite', 'Parité', 'nombre_json', ()),
    ('acc_prematurite', 'Prématurité', 'nombre_json', ()),
    ('acc_retesting', 'Retesting', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('acc_sous_arv', 'Sous ARV', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_statut_vih_accueil', 'Statut VIH à l\'accueil', 'choix', (('inconnu', 'Inconnu'), ('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('acc_toxemie', 'Toxémie gravidique', 'texte', ()),
    # Arrivée
    ('acc_aspect_liquide', 'Aspect du liquide amniotique', 'texte', ()),
    ('acc_contractions', 'Contractions', 'texte', ()),
    ('acc_date_arrivee', 'Date', 'date_json', ()),
    ('acc_en_travail', 'En travail', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_mode_entree', 'Mode d\'entrée', 'choix', (('venu_lui_meme', 'Patient venu de lui-même'), ('reference_centre', 'Référence d\'un centre de santé'), ('refere_tradipraticien', 'Référé par un tradipraticien'), ('autre', 'Autre'))),
    ('acc_motif_admission', 'Motif d\'admission', 'texte', ()),
    ('acc_poche_eaux', 'Poche des eaux intacte', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_mode_entree_autre', 'Préciser', 'texte', ()),
    # Informations cliniques et examen obstétrical
    ('acc_bassin', 'Bassin', 'texte', ()),
    ('acc_conjonctives', 'Conjonctives', 'texte', ()),
    ('acc_ddr', 'D.D.R.', 'date_json', ()),
    ('acc_excision', 'Excision', 'texte', ()),
    ('acc_freq_resp', 'Fréquence respiratoire', 'texte', ()),
    ('acc_groupe_rhesus', 'Groupe Rhésus', 'texte', ()),
    ('acc_hu', 'H.U.', 'texte', ()),
    ('acc_imc', 'IMC (à l\'admission)', 'texte', ()),
    ('acc_po', 'P.O.', 'texte', ()),
    ('acc_perimetre_brachial', 'Périmètre brachial (à l\'admission)', 'texte', ()),
    ('acc_poids', 'Poids (à l\'admission)', 'texte', ()),
    ('acc_pouls', 'Pouls', 'texte', ()),
    ('acc_presentation', 'Présentation', 'texte', ()),
    ('acc_rcf', 'R.C.F.', 'texte', ()),
    ('acc_tv', 'T.V.', 'texte', ()),
    ('acc_ta_droit', 'TA bras droit (à l\'admission)', 'texte', ()),
    ('acc_ta_gauche', 'TA bras gauche (à l\'admission)', 'texte', ()),
    ('acc_taille', 'Taille', 'texte', ()),
    ('acc_temperature', 'Température', 'texte', ()),
    ('acc_tp', 'TP', 'date_json', ()),
    ('acc_varices', 'Varices', 'texte', ()),
    ('acc_oedemes', 'Œdèmes', 'texte', ()),
    # L'Enfant
    ('acc_allaitement', 'Allaitement', 'texte', ()),
    ('acc_apgar_couleur_1mn', 'Apgar Couleur 1mn', 'nombre_json', ()),
    ('acc_apgar_couleur_5mn', 'Apgar Couleur 5mn', 'nombre_json', ()),
    ('acc_apgar_coeur_1mn', 'Apgar Cœur 1mn', 'nombre_json', ()),
    ('acc_apgar_coeur_5mn', 'Apgar Cœur 5mn', 'nombre_json', ()),
    ('acc_apgar_reflexes_1mn', 'Apgar Réflexes 1mn', 'nombre_json', ()),
    ('acc_apgar_reflexes_5mn', 'Apgar Réflexes 5mn', 'nombre_json', ()),
    ('acc_apgar_resp_1mn', 'Apgar Respiration 1mn', 'nombre_json', ()),
    ('acc_apgar_resp_5mn', 'Apgar Respiration 5mn', 'nombre_json', ()),
    ('acc_apgar_tonus_1mn', 'Apgar Tonus 1mn', 'nombre_json', ()),
    ('acc_apgar_tonus_5mn', 'Apgar Tonus 5mn', 'nombre_json', ()),
    ('acc_apgar_total_1mn', 'Apgar Total 1mn', 'nombre_json', ()),
    ('acc_apgar_total_5mn', 'Apgar Total 5mn', 'nombre_json', ()),
    ('acc_conseils_allaitement', 'Conseils pour l\'allaitement exclusif', 'choix', (('1', 'Oui'),)),
    ('acc_date_heure_sein', 'Date et heure de mise au sein', 'texte', ()),
    ('acc_decede_maternite', 'Décédé à la maternité', 'choix', (('1', 'Oui'),)),
    ('acc_etat_nouveau_ne', 'Etat du nouveau-né', 'choix', (('vivant', 'Vivant'), ('mort_ne', 'Mort-né'), ('macere', 'Macéré'))),
    ('acc_evacuation_nn', 'Evacuation du nouveau-né', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_fiche_naissance_renseignee', 'Fiche de déclaration de naissance renseigné', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_malformation', 'Malformation', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_enfant_perimetre_cranien', 'Périmètre crânien', 'nombre_json', ()),
    ('acc_enfant_poids', 'Poids du nouveau-né', 'nombre_json', ()),
    ('acc_prophylaxie_arv', 'Prophylaxie ARV', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'Non Applicable'))),
    ('acc_enfant_sexe', 'Sexe', 'choix', (('m', 'Masculin'), ('f', 'Féminin'))),
    ('acc_soins_kangourou', 'Soins Mère Kangourou', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_enfant_taille', 'Taille du bébé', 'nombre_json', ()),
    ('acc_traitement', 'Traitement', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    # Offre de service VIH
    ('acc_annonce_resultat', 'Annonce du résultat', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('acc_initiation_arv_vih', 'Initiation ARV (VIH)', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('acc_numero_depistage', 'Numéro de dépistage', 'texte', ()),
    ('acc_proposition_vih', 'Proposition de test VIH', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('acc_resultat_vih', 'Résultat du test VIH', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    # Ordonnances
    ('acc_actes', 'Actes', 'texte', ()),
    ('acc_ordo_enfant', 'Ordonnance enfant', 'texte', ()),
    ('acc_ordo_mere', 'Ordonnance mère', 'texte', ()),
    # P.M.I.
    ('acc_age_grossesse_cpn', 'Age de la grossesse à la 1ère CPN', 'nombre_json', ()),
    ('acc_nombre_cpn', 'Nombre de CPN', 'nombre_json', ()),
    ('acc_statut_vat', 'Statut vaccinal VAT', 'choix', (('0', 'Non vaccinée'), ('1', 'VAT1'), ('2', 'VAT2'), ('3', 'VAT3'), ('4', 'VAT4'), ('5', 'VAT5'))),
    # Réanimation du nouveau-né
    ('acc_respire_1min', 'A-t-il respiré/pleuré dans la 1ère minute', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('acc_autres_medicaments', 'Autres médicaments administrés', 'texte', ()),
    # Service de planification familial
    ('acc_conseil_pf_ppi', 'Conseil PF-PPI', 'choix', (('1', 'Oui'),)),
    ('acc_initiation_arv_pf', 'Initiation ARV (PF)', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    # Sortie (suite)
    ('acc_fiche_declaration', 'Fiche de déclaration de naissance', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('acc_rdv_postnatale', 'RDV pour la consultation postnatale', 'date_json', ()),
    ('acc_remarques', 'Remarques', 'texte', ()),
    ('acc_responsable', 'Responsable de l\'accouchement', 'medecin', ()),
    ('acc_vitamine_a', 'Supplémentation en vitamine A', 'choix', (('1', 'Oui'),)),
    # Sortie de la mère
    ('acc_date_sortie', 'Date de sortie', 'date_json', ()),
    ('acc_heure_depart', 'Heure de départ effectif', 'texte', ()),
    ('acc_mode_sortie', 'Mode de sortie', 'choix', (('gueri', 'Guéri'), ('transfere', 'Transféré'), ('decede', 'Décédé'), ('contre_avis', 'Contre avis médical'))),
]

#: Onglet « Post-natale » → registre_postnatale.donnees (89 champs)
CHAMPS_POST_NATALE = [
    # Antécédents
    ('cposo_atcd_autres', 'Autres', 'texte', ()),
    ('cposo_avortements', 'Avortements', 'nombre_json', ()),
    ('cposo_cesariennes', 'Césariennes', 'nombre_json', ()),
    ('cposo_atcd_chirurgicaux', 'Chirurgicaux', 'texte', ()),
    ('cposo_date_accouchement', 'Date de l\'accouchement', 'date_json', ()),
    ('cposo_atcd_diabete', 'Diabète', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_enfants_decedes', 'Enfants décédés', 'nombre_json', ()),
    ('cposo_gestite', 'Gestité', 'nombre_json', ()),
    ('cposo_atcd_hta', 'HTA', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_lieu_accouchement', 'Lieu d\'accouchement', 'choix', (('etablissement', 'En établissement de soins'), ('domicile', 'Domicile'), ('en_route', 'En route'))),
    ('cposo_mode_accouchement', 'Mode d\'accouchement', 'choix', (('voie_basse', 'Voie Basse'), ('cesarienne', 'Césarienne'))),
    ('cposo_enfants_vivants_nb', 'Nombre d\'enfants vivants', 'nombre_json', ()),
    ('cposo_atcd_obstetricaux', 'Obstétricaux', 'texte', ()),
    ('cposo_parite', 'Parité', 'nombre_json', ()),
    ('cposo_toxemie', 'Toxémie gravidique', 'texte', ()),
    # Conduite à tenir
    ('cposo_annonce_resultat', 'Annonce du résultat', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cposo_numero_depistage', 'Numéro de Dépistage VIH', 'texte', ()),
    ('cposo_prophylaxie_arv_enfant', 'Prophylaxie ARV pour l\'enfant', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'Non Applicable'))),
    ('cposo_proposition_vih', 'Proposition de test VIH', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cposo_resultat_vih', 'Résultat du test VIH', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('na', 'NA'))),
    ('cposo_retesting', 'Retesting', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    # Données administratives
    ('cposo_autre_preciser', 'Autre à préciser', 'texte', ()),
    ('cposo_conseil_pf_pp_prolonge', 'Conseil PF-PP prolongé', 'choix', (('1', 'Oui'),)),
    ('cposo_conseil_pf_pp_tardif', 'Conseil PF-PP tardif (données administratives)', 'choix', (('1', 'Oui'),)),
    ('cposo_conseil_pf_ppi', 'Conseil PF-PPI (données administratives)', 'choix', (('1', 'Oui'),)),
    ('cposo_date_vat1', 'Date du VAT 1', 'date_json', ()),
    ('cposo_date_vat2', 'Date du VAT 2', 'date_json', ()),
    ('cposo_date_vat_rappel', 'Date VAT rappel', 'date_json', ()),
    ('cposo_methode_adoptee', 'Méthode adoptée', 'choix', (('condom', 'Condom'), ('pilule', 'Pilule'), ('diu', 'DIU'), ('injectable', 'Injectable'), ('implant', 'Implant'), ('sterilisation', 'Stérilisation'))),
    ('cposo_mode_entree', 'Mode d\'entrée', 'choix', (('venu_lui_meme', 'Patient venu de lui-même'), ('reference_centre', 'Référence d\'un centre de santé'), ('refere_tradipraticien', 'Référé par un tradipraticien'), ('autre', 'Autre'))),
    ('cposo_mode_entree_autre', 'Mode d\'entrée (préciser)', 'texte', ()),
    ('cposo_report_numero', 'Report N° Gestante', 'texte', ()),
    ('cposo_statut_vat', 'Statut VAT', 'choix', (('0', 'Non vaccinée'), ('1', 'VAT1'), ('2', 'VAT2'), ('3', 'VAT3'), ('4', 'VAT4'), ('5', 'VAT5'))),
    ('cposo_statut_vih_accueil', 'Statut VIH à l\'accueil', 'choix', (('inconnu', 'Inconnu'), ('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cposo_traitement_arv', 'Traitement ARV', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_type_consultation', 'Type de consultation postnatale', 'choix', (('j3', 'J3'), ('j7', 'J7'), ('j28', 'J28'), ('j42', 'J42'))),
    # Examen de la patiente
    ('cposo_abdomen', 'Abdomen', 'texte', ()),
    ('cposo_allaitement_exclusif', 'Allaitement exclusif', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_autres_allaitement', 'Autres types d\'allaitement', 'texte', ()),
    ('cposo_conscience', 'Conscience', 'texte', ()),
    ('cposo_conseil_alim_enfant', 'Conseil en alimentation de l\'enfant', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_conseil_alim_mere', 'Conseil en alimentation de la mère', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_date_retour', 'Date de retour', 'date_json', ()),
    ('cposo_enfant_vaccins', 'Enfant à jour de ses vaccins', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_enfants_vivants_r', 'Enfants vivants (oui / non)', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_etat_conjonctives', 'Etat des conjonctives', 'texte', ()),
    ('cposo_etat_nutritionnel', 'Etat nutritionnel', 'choix', (('bon', 'Bon'), ('moyen', 'Moyen'), ('mauvais', 'Mauvais'))),
    ('cposo_examen_speculum', 'Examen au spéculum', 'texte', ()),
    ('cposo_femme_allaitante', 'Femme allaitante', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_freq_resp', 'Fréquence respiratoire', 'texte', ()),
    ('cposo_globe_uterin', 'Globe utérin', 'texte', ()),
    ('cposo_imc', 'IMC', 'texte', ()),
    ('cposo_lochies', 'Lochies', 'texte', ()),
    ('cposo_pathologies_associees', 'Pathologies associées', 'texte', ()),
    ('cposo_pb', 'PB', 'texte', ()),
    ('cposo_perimetre_brachial', 'Périmètre Brachial (cm)', 'texte', ()),
    ('cposo_poids', 'Poids', 'texte', ()),
    ('cposo_pouls', 'Pouls', 'texte', ()),
    ('cposo_retour_couches', 'Retour de couches', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_seins', 'Seins', 'texte', ()),
    ('cposo_tv', 'T.V.', 'texte', ()),
    ('cposo_ta_droit', 'TA Bras droit (mmHg)', 'texte', ()),
    ('cposo_ta_gauche', 'TA Bras gauche (mmHg)', 'texte', ()),
    ('cposo_taille', 'Taille', 'texte', ()),
    ('cposo_temperature', 'Température', 'texte', ()),
    ('cposo_test_acide_acetique', 'Test à l\'acide acétique', 'texte', ()),
    ('cposo_uterus', 'Utérus', 'texte', ()),
    ('cposo_varices', 'Varices', 'texte', ()),
    ('cposo_vessie', 'Vessie', 'texte', ()),
    ('cposo_vulve', 'Vulve', 'texte', ()),
    ('cposo_oedemes', 'Œdèmes', 'texte', ()),
    # Examens biologiques :
    ('cposo_acceptation_contraceptives', 'Acceptation de méthodes contraceptives', 'choix', (('condom', 'Condom'), ('pilule', 'Pilule'), ('diu', 'DIU'), ('injectable', 'Injectable'), ('implant', 'Implant'), ('sterilisation', 'Stérilisation'))),
    ('cposo_albumine', 'Albumine', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'))),
    ('cposo_analyse_urine', 'Analyse d\'urine', 'choix', (('1', 'Oui'),)),
    ('cposo_analyse_sang', 'Analyse de sang', 'choix', (('1', 'Oui'),)),
    ('cposo_autres_medicaments', 'Autres médicaments', 'texte', ()),
    ('cposo_conseil_pf_pp_tardif2', 'Conseil PF-PP tardif (conduite à tenir)', 'choix', (('1', 'Oui'),)),
    ('cposo_conseil_pf_ppi2', 'Conseil PF-PPI (conduite à tenir)', 'choix', (('1', 'Oui'),)),
    ('cposo_date_prochain_rdv', 'Date du prochain RDV', 'date_json', ()),
    ('cposo_glycemie', 'Glycémie', 'texte', ()),
    ('cposo_initiation_arv', 'Initiation ARV', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cposo_mode_sortie', 'Mode de sortie', 'choix', (('gueri', 'Guéri'), ('transfere', 'Transféré'), ('decede', 'Décédé'), ('contre_avis', 'Contre avis médical'))),
    ('cposo_observations', 'Observations', 'texte', ()),
    ('cposo_prescriptions', 'Prescriptions', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_remarques', 'Remarques', 'texte', ()),
    ('cposo_resultat_preciser', 'Résultat (préciser)', 'texte', ()),
    ('cposo_resultat_consultation', 'Résultat consultation', 'choix', (('normale', 'Normale'), ('complications', 'Complications'))),
    ('cposo_service_nutritionnel', 'Service nutritionnel', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cposo_sucre', 'Sucre', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'))),
]

#: Onglet « Curatif » → registre_curatif.donnees (31 champs)
CHAMPS_CURATIF = [
    # Antécédents et autres informations
    ('cur_alcool', 'Alcool', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_atcd_autres', 'Autres', 'texte', ()),
    ('cur_atcd_chirurgicaux', 'Chirurgicaux', 'texte', ()),
    ('cur_ddr', 'D.D.R.', 'date_json', ()),
    ('cur_atcd_diabete', 'Diabète', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_grossesse_en_cours', 'Grossesse en cours', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_atcd_hta', 'HTA', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_atcd_obstetricaux', 'Obstétricaux', 'texte', ()),
    ('cur_tabac', 'Tabac', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_atcd_traitement', 'Traitement antérieur/en cours (rdv gynécologie)', 'texte', ()),
    ('cur_traitement_anterieur', 'Traitement antérieur/en cours (rdv patients)', 'texte', ()),
    # Conduite à tenir et traitement
    ('cur_conseil_sante_sexuelle', 'Conseil santé sexuelle et reproductive', 'choix', (('oui', 'Oui'), ('non', 'Non'))),
    ('cur_issue_consultation', 'Issue de la consultation', 'choix', (('sorti', 'Sorti(e)'), ('hospitalise', 'Hospitalisé(e)'), ('mo', 'M.O'), ('refere_interne', 'Référé(e) en interne'), ('refere_externe', 'Référé(e) en externe'), ('tb_refere', 'Cas présumé de TB référé'), ('a_revoir', 'A revoir'), ('decede', 'Décédé(e)'))),
    ('cur_traitement', 'Traitement', 'texte', ()),
    # Données administratives
    ('cur_type_population', 'Type de population', 'choix', (('pop_generale', 'Population générale'), ('ts', 'TS'), ('ud', 'UD'), ('hsh', 'HSH'), ('pc', 'PC'), ('autre_risque', 'Autre à risque'))),
    # Examens cliniques et constantes
    ('cur_examen_physique', 'Examen physique', 'texte', ()),
    ('cur_motif_consultation', 'Motif de consultation', 'texte', ()),
    ('cur_tuberculose', 'Recherche de la tuberculose', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    # Examens complémentaires
    ('cur_autres_examens', 'Autres Examens', 'texte', ()),
    ('cur_cdip_propose', 'CDIP proposé', 'choix', (('oui', 'Oui'), ('na', 'NA'))),
    ('cur_cdip_realise', 'CDIP réalisé', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cur_code_depistage', 'Code dépistage client', 'texte', ()),
    ('cur_date_debut_mo', 'Date et heure de début M.O', 'texte', ()),
    ('cur_date_fin_mo', 'Date et heure de fin', 'texte', ()),
    ('cur_duree_mo', 'Durée M.O', 'texte', ()),
    ('cur_glycemie', 'Glycémie', 'texte', ()),
    ('cur_goutte_epaisse', 'Goutte épaisse', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('non_fait', 'Non fait'))),
    ('cur_milda_eligible', 'MILDA enfant 12 à 59 mois Eligible', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cur_remarques', 'Remarques', 'texte', ()),
    ('cur_remise_milda', 'Remise MILDA 12 à 59 mois', 'choix', (('oui', 'Oui'), ('non', 'Non'), ('na', 'NA'))),
    ('cur_tdr_paludisme', 'TDR Paludisme', 'choix', (('negatif', 'Négatif'), ('positif', 'Positif'), ('non_fait', 'Non fait'))),
]


#: Tous les groupes, dans l'ordre des onglets du formulaire.
GROUPES = [
    ('CPN', CHAMPS_CPN),
    ('Accouchement', CHAMPS_ACCOUCHEMENT),
    ('Post-natale', CHAMPS_POST_NATALE),
    ('Curatif', CHAMPS_CURATIF),
]


def champs_registres():
    """Champs des registres, au format attendu par `core.listing`.

    Le type `medecin` est résolu ici et non dans la déclaration : la liste des
    médecins vient de la base, elle ne peut pas être figée dans un fichier.
    """
    champs = []
    for groupe, declares in GROUPES:
        registre = REGISTRES[groupe]
        for nom, libelle, type_, choix in declares:
            if type_ == 'medecin':
                type_, choix = 'choix', _choix_medecins()
            champs.append({
                'chemin':  f'{registre}__donnees__{nom}',
                'libelle': libelle,
                'type':    type_,
                'choix':   list(choix),
                'groupe':  groupe,
                # Signale une valeur logée dans un JSONField : le regroupement
                # doit alors reconvertir en texte les valeurs relues en base
                # (cf. Dimension.valeurs_texte).
                'json':    True,
            })
    return champs


def _choix_medecins():
    """(identifiant, nom) des médecins, tels que le formulaire les enregistre.

    Le registre garde l'identifiant sous forme de texte : la clé du dictionnaire
    de libellés doit donc être une chaîne, sinon la valeur relue en JSON ne
    retrouverait pas son libellé.

    `select_related` n'est pas un détail : le nom d'un médecin vient de sa fiche
    d'employé, et l'omettre coûte une requête par médecin.
    """
    from medecins.models import Medecin
    return [(str(m.pk), str(m)) for m in Medecin.objects.select_related('employe')]
