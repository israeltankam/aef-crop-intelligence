# Journal - onglet What-if scenarios

Date: 2026-06-14  
Copie de travail: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822  
Backup préalable: backups/pre_what_if_scenarios_2026-06-14T00-00-00-000Z

## Objectif

Ajouter un onglet adjacent aux recommandations pour tester des scénarios de gestion. L'utilisateur doit partir des calendriers optimaux, supprimer ou éditer des événements d'irrigation et de fertilisation, désactiver le contrôle de maladie si souhaité, puis obtenir une comparaison en rendement et retour économique.

## Choix de conception

- Page séparée pages/main/what_if.py afin de ne pas surcharger la page Recommendations.
- Simulation rapide déterministe pour préserver l'interactivité. Les ensembles probabilistes lourds restent dans le rapport complet.
- Point de départ généré depuis les mêmes optimiseurs que Recommendations.
- Éditeurs Streamlit avec cases à cocher, dates, volumes, doses et produits.
- Comparaison systématique de trois lignes: absence d'action, gestion optimisée, scénario édité.
- PDF de scénario généré avec fpdf, déjà présent dans requirements.txt.
- En mode coopérative, les scénarios réexécutent les parcelles incluses dans le plan optimisé et laissent les parcelles non sélectionnées sur leur baseline documentée.

## Fichiers modifiés

- app.py: ajout de l'onglet de navigation et du routage What-if.
- pages/main/what_if.py: nouvelle page de test de scénarios.
- src/utils/i18n.py: libellés français/anglais de navigation et traductions littérales de la page.
- docs/WHAT_IF_SCENARIOS_LOG.md: présent journal.
- support/test_results/aef_what_if_scenarios_static_100_checks.json: résultats des contrôles.
- support/refactor/refactor_manifest.json: entrée de suivi.

## Validation

100 contrôles statiques ciblés ont été exécutés. Ils vérifient la structure Python, la présence de l'onglet, les spinners, les éditeurs, le PDF, les traductions, la non-ajout de dépendances et les principaux garde-fous ergonomiques.

## Dépendances

Aucune nouvelle dépendance n'a été ajoutée. fpdf était déjà listé dans requirements.txt.
