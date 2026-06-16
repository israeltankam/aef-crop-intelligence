# Journal - calendriers détaillés dans les recommandations

Date: 2026-06-13  
Copie de travail: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822  
Backup préalable: backups/pre_recommendation_calendars_2026-06-13T00-00-00-000Z

## Objectif

Rendre la page Recommendations réellement opérationnelle. Avant cette correction, elle affichait surtout une synthèse économique et une liste d'actions. Les calendriers complets d'irrigation et de fertilisation n'étaient pas lisibles dans les onglets Agronomic optimum et Economic optimum, et les recommandations de contrôle des maladies n'étaient pas assez détaillées pour guider l'utilisateur.

## Modifications réalisées

- Ajout d'un bloc Detailed operational calendars dans les onglets Agronomic optimum et Economic optimum.
- Affichage du calendrier complet d'irrigation pour l'horizon sélectionné, avec date, dose en mm, volume d'eau, coût estimé et note agronomique.
- Affichage du calendrier complet de fertilisation pour l'horizon sélectionné, avec date, produit, dose kg/ha, quantité totale, coût estimé et justification.
- Affichage des calendriers coopératifs par parcelle quand le mode coopérative est utilisé.
- Conservation des calendriers agronomiques dans l'onglet économique, même lorsqu'ils ne sont pas retenus économiquement, avec un statut clair: retenu dans l'optimum économique ou calendrier agronomique seulement sous les prix actuels.
- Ajout d'une section de contrôle des maladies indiquant la maladie sélectionnée, la date de détection, les foyers, les plantes affectées, les protocoles de contrôle issus du CSV et l'équilibre roguing/taille quand le scénario le fournit.
- Internationalisation française de tous les nouveaux libellés visibles ajoutés par cette correction.

## Fichiers modifiés

- pages/main/recommendations.py
- src/utils/i18n.py
- src/models/cooperative_engine.py
- support/test_results/aef_recommendation_calendars_static_100_checks.json
- docs/RECOMMENDATION_CALENDARS_DETAIL_LOG.md
- support/refactor/refactor_manifest.json

## Validation

100 contrôles statiques ciblés ont été exécutés et enregistrés dans support/test_results/aef_recommendation_calendars_static_100_checks.json. Ils couvrent la structure Python, la présence des nouveaux blocs, la conservation des calendriers coopératifs, les traductions françaises et les garde-fous d'affichage.

## Dépendances

Aucune nouvelle dépendance n'a été ajoutée. Le fichier requirements.txt n'a pas été modifié.
