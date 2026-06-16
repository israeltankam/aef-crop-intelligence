# Journal - correction de la logique économique des recommandations

Date: 2026-06-14  
Copie de travail: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822  
Backup préalable: backups/pre_recommendation_economic_logic_2026-06-14T00-00-00-000Z

## Problèmes corrigés

1. La page Recommendations lançait l'optimisation automatiquement à l'ouverture si aucun cache n'était présent ou si la signature avait changé. C'était mauvais pour l'ergonomie et pour la validité, car l'utilisateur devait d'abord fixer l'horizon économique.
2. La ligne baseline affichait un gain net nul. Le problème venait d'une confusion entre retour net total et gain incrémental versus baseline.
3. L'optimum économique pouvait afficher un retour net inférieur à l'optimum agronomique, car les formules n'étaient pas comparées sur la même base et une décote était appliquée seulement au scénario économique.

## Nouvelle règle économique

Chaque stratégie est désormais comparée sur un retour net total attendu:

retour net = revenu attendu - coût d'intervention

Le moteur évalue trois candidats:

- absence d'action;
- plan agronomique complet;
- sous-ensemble d'actions individuellement rentables.

L'optimum économique est le candidat ayant le plus grand retour net total attendu. Comme le plan agronomique complet est inclus parmi les candidats, l'optimum économique ne peut plus être inférieur au plan agronomique sous les mêmes hypothèses de prix, rendement et coût.

## Modifications réalisées

- src/models/economic_engine.py
  - Ajout de candidats économiques explicites.
  - Ajout de baseline_net_return, agronomic_net_return, economic_net_return.
  - Ajout de champs incremental_net_gain pour conserver la comparaison versus baseline sans ambiguïté.
  - Suppression de l'application asymétrique de la décote de risque uniquement sur l'optimum économique affiché.
  - Correction du coût coopératif pour séparer produit fertilisant et main-d'oeuvre partagée.

- pages/main/recommendations.py
  - L'optimisation ne se lance plus automatiquement au chargement.
  - L'utilisateur configure d'abord l'horizon, puis lance explicitement l'optimisation.
  - Le tableau affiche retour net total et gain net vs baseline dans deux colonnes distinctes.
  - Les métriques utilisent le retour net/ha.

- pages/main/what_if.py
  - Le plan optimisé de départ n'est plus généré automatiquement.
  - L'utilisateur configure d'abord l'horizon, puis clique sur Générer le plan optimisé de départ.
  - Les résultats existants sont invalidés quand le plan de départ est regénéré.

- pages/main/report.py
  - Les libellés économiques passent de net gain à net return quand il s'agit du retour net total.
  - La ligne baseline du tableau économique affiche aussi son retour net.

- src/utils/i18n.py
  - Ajout des traductions françaises des nouveaux libellés.

## Validation

100 contrôles statiques ciblés ont été exécutés et enregistrés dans:

support/test_results/aef_recommendation_economic_logic_100_checks.json

Ils vérifient notamment:

- absence de lancement automatique de Recommendations;
- horizon configuré avant bouton d'optimisation;
- baseline avec retour net non nul dans l'affichage;
- optimum économique choisi par maximum de retour net total;
- impossibilité structurelle que l'optimum économique soit inférieur au plan agronomique, puisque ce dernier est un candidat;
- What-if non lancé automatiquement;
- couverture i18n des nouveaux textes;
- absence de nouvelle dépendance.

## Dépendances

Aucune nouvelle dépendance n'a été ajoutée.
