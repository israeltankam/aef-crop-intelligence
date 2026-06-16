# Journal - effet réel du champ Price source

Date: 2026-06-14  
Copie de travail: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822  
Backup préalable: backups/pre_price_source_effect_2026-06-14T00-00-00-000Z

## Problème

Dans la configuration économique, changer le champ Price source ne modifiait pratiquement rien d'utile pour l'utilisateur. Le prix utilisé par les recommandations restait piloté par Sale price of crop per tonne, et la source ne mettait pas à jour de façon fiable la confiance, la note ou la référence automatique.

Il existait aussi un bug de cohérence: Refresh automatic market reference pouvait enregistrer une source comme automatic Cameroon/Central Africa prior, mais cette valeur n'était pas listée dans le selectbox. Au rendu suivant, le widget pouvait donc retomber sur manual et effacer la source réellement appliquée.

## Correction

- Ajout de ECONOMIC_PRICE_SOURCE_OPTIONS dans src/models/economic_engine.py avec toutes les sources utilisées par l'application.
- Ajout de apply_price_source_choice(...), qui donne un effet concret au choix de source:
  - automatic regional/local/Cameroon prior: rafraîchit le prix de référence, la confiance, la note et la date de mise à jour;
  - manual, market quote, cooperative quote, national statistics, international reference: conserve le prix saisi mais ajuste la confiance et la note explicative.
- Réorganisation de l'onglet Market price dans pages/main/setup_page.py pour choisir Price source avant le prix et la confiance.
- Ajout de clés Streamlit dépendantes de la source pour que le prix, la confiance et la note affichés se mettent réellement à jour quand la source change.
- Stabilisation du bouton Refresh automatic market reference pour que le selectbox garde la source automatique appliquée.
- Traduction française des nouvelles sources et notes.

## Validation

100 contrôles statiques ciblés ont été exécutés et enregistrés dans:

support/test_results/aef_price_source_effect_100_checks.json

Ils couvrent la structure Python, l'existence du helper, les options de source, l'effet des profils, la stabilité du selectbox, la couverture i18n et l'absence de nouvelle dépendance.

## Dépendances

Aucune nouvelle dépendance n'a été ajoutée.
