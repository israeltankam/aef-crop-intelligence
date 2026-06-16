# AEF UX and Agronomic Refinement Log

Date: 2026-06-12
Working copy: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822
Backup before this refinement: backups/pre_ux_agro_coop_refinement_2026-06-12T11-15-00-000Z

## 1. Priority Corrections Applied

- Revised cooperative plot definition so parcels are no longer forced to share the same size.
- Added automatic variable-size candidate parcel generation inside the cooperative perimeter, with explicit user validation on the satellite map.
- Fixed the cooperative area input regression that could raise StreamlitValueBelowMinError when a saved perimeter area was below 1 ha.
- Added DMS-cardinal coordinate display and parsing, while keeping decimal degrees internally.
- Added cooperative parcel quality warnings: extremely small polygons, unusually large smallholder plots, excessive total area compared with the perimeter, and low-confidence automatic boundaries.
- Added practical constraints for irrigation and fertilization: available water, application efficiency, irrigation method, fertilizer budget ceiling, and local fertilizer constraints.
- Added cautious decision snapshots and model-validity notes in dashboard and report outputs.
- Strengthened adaptive calibration so cooperative observations and single-field observations are normalized into one calibration format.
- Prevented calibration from reporting zero uncertainty when the Hessian approximation is missing, singular, or numerically overconfident.
- Improved fertilizer product selection from a broad type heuristic to a lightweight N-P-K vector matching score.

## 2. Cooperative Parcel Definition

The current implementation is a lightweight candidate generator, not a trained satellite instance-segmentation model. This is intentional for runtime robustness. It gives editable polygons that respect the perimeter and are clearly flagged as candidates requiring visual validation. A future model can replace src/models/cooperative_parcel_detector.py without changing the Streamlit workflow.

Given a perimeter polygon P, a typical parcel area A_t, and a deterministic seed based on the perimeter, the detector:

1. Converts latitude/longitude into a local metre grid.
2. Places staggered candidate centroids inside P.
3. Samples parcel area factors around the typical size: A_i = A_t * U(1 - v, 1 + v).
4. Samples aspect ratio and light rotation so parcels are not all identical rectangles.
5. Shrinks edge candidates until all vertices remain inside the perimeter.
6. Stores confidence, source, validation requirement, area and polygon vertices.

The previous regular grid implied false precision and equal-sized holdings. Smallholder systems commonly contain unequal and irregular parcels, and automatic field-boundary delineation from satellite imagery is normally an instance or boundary segmentation problem. The new implementation therefore avoids claiming automatic cadastral truth without a trained regional model.

## 3. Adaptive Calibration

The calibration engine now accepts both legacy single-field rows and cooperative observations. For each observation j, likelihood weight uses an observation-specific standard deviation:

sigma_j = sigma_base * scope_penalty / confidence_j
J(theta) = sum_j (f_j(theta) - y_j)^2 / (2 sigma_j^2) + lambda * sum_k (theta_k - 1)^2

- Plot-level measurements keep scope_penalty = 1.0.
- Cooperative-wide visual estimates use a larger penalty.
- Invalid or missing confidence values fall back to a finite conservative confidence.
- Parameter uncertainty now has non-zero floors, so dashboards and reports do not imply impossible certainty.

## 4. Fertilizer Recommendation

The fertilizer selector now ranks products by N-P-K profile match instead of simply choosing the highest-analysis product in a broad class.

For deficit vector d = (N_d, P_d, K_d) and product vector p = (N_p, P_p, K_p):
match(d, p) = (d . p) / (||d|| ||p||)
rate = max_i deficit_i / (content_i / 100)

A soft dose penalty avoids making very large applications look equally attractive. This remains a lightweight agronomic heuristic; local product availability and soil-test interpretation remain required.

## 5. Irrigation Feasibility Layer

The engine now interprets optimized irrigation through farm capacity:
max_event_mm = available_water_m3_day * irrigation_efficiency / (10 * area_ha)
because 1 mm over 1 ha requires about 10 m3 of water. If capacity is unknown, the report flags feasibility as unverified instead of pretending the schedule is automatically feasible.

## 6. Output Clarity

Dashboard and report outputs now include plain-language decision cards, model validity warnings, a caution that satellite canopy anomaly detection is not pathogen identification, cautious reality-check wording, and operational feasibility notes.

## 7. Known Scientific Limits Still Preserved Transparently

- Cooperative automatic parcel detection is not yet a trained Sentinel-2/high-resolution boundary segmentation model.
- Growth model selection still uses AEF-lite surrogate adapters where full STICS, DSSAT, APSIM, AquaCrop or CROPWAT engines are not installed.
- Disease models are stochastic and more realistic than concentric reaction-diffusion, but disease-specific parameters still need literature review and pilot calibration.
- Satellite disease detection remains canopy-stress detection. The application should propose likely diseases for validation, not assert pathogen identity from canopy signal alone.
- Economic optimization is still partial: fertilizer budget and availability are recorded, but full constrained economic optimization is not yet implemented.

## 8. Files Added

- src/utils/coordinate_format.py
- src/models/cooperative_parcel_detector.py
- src/utils/parcel_quality.py
- src/models/fertilizer_optimizer.py
- src/utils/decision_support.py
- src/models/operational_constraints.py
- src/models/model_validity.py

## 9. Files Modified

- pages/main/setup_page.py
- pages/main/dashboard.py
- pages/main/report.py
- src/models/state_manager.py
- src/models/simulation_engine.py
- src/models/calibration_engine.py
- src/models/growth_model_selector.py
- src/models/fertilizer_service.py
- src/utils/i18n.py

## 10. Scientific References Used for Direction

- Gillespie, D. T. stochastic simulation and tau-leaping foundations: https://doi.org/10.1063/1.1378322
- Cao, Y., Gillespie, D. T., Petzold, L. efficient tau-leaping step selection: https://doi.org/10.1063/1.2159468
- Andrieu, C., Doucet, A., Holenstein, R. Particle Markov chain Monte Carlo: https://doi.org/10.1111/j.1467-9868.2009.00736.x
- Waldner, F. and Diakogiannis, F. field boundary extraction with convolutional neural networks: https://arxiv.org/abs/1910.12023
- Aung, H. L. et al. farmland parcel delineation with spatio-temporal convolutional networks: https://arxiv.org/abs/2004.05471
- Jones, J. W. et al. DSSAT cropping system model, European Journal of Agronomy, 2003.
- Keating, B. A. et al. APSIM agricultural production systems simulator, European Journal of Agronomy, 2003.
- Steduto, P. et al. AquaCrop concepts and algorithms, Agronomy Journal, 2009.

## 11. Verification Status

Static verification was run because shell-based Streamlit/Python execution is not available in this session. The test report is written to support/test_results/aef_ux_agro_refinement_tests.json.
