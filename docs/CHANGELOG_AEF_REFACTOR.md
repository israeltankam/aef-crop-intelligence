# AEF Crop Intelligence - Modification Log

## 2026-06-10 - Scientific refactor working copy

Backup created before changes:

- backups/pre_refactor_snapshot

Implemented in this working copy:

1. Added lightweight i18n registry for French/English text.
2. Added disease-family selector and stochastic tau-leaping disease engine.
3. Replaced the previous cumulative disease realisation in SimulationEngine with the new disease engine while preserving dashboard output keys.
4. Added growth-model selector that chooses the target validated family: STICS/APSIM, DSSAT/APSIM, AquaCrop/CROPWAT, or AEF-lite fallback.
5. Added counterfactual scenario runner: do nothing, minimum useful action, optimized recommendation.
6. Added active-learning measurement advice for adaptive surveillance.
7. Added PDF scenario-comparison section and safer Python 3.11-compatible f-string construction.
8. Added model documentation with equations.
9. Added standalone rollback utility.
10. Added 1000-check validation runner and generated validation report.

Known constraints:

- The original WSL workspace was inaccessible from this execution environment, so changes were produced in a temporary corrected working copy.
- External STICS/AquaCrop/APSIM/CROPWAT/DSSAT adapters are selected as target model families but not yet installed as executable backends.
- Scientific parameters are conservative pilot priors and must be refined from literature plus field pilots.

## Validation

- 1000 lightweight checks executed in the constrained Codex runtime: 1000 passed, 0 failed.
- Extra static checks: 16 passed, 0 failed.
- Result file: support/test_results/aef_1000_checks.json
- Limitation: this session could not spawn Python or Streamlit processes, so full runtime tests must be repeated in a normal Python environment before deployment.

## Satellite triage update

- Added src/models/satellite_disease_triage.py.
- Automatic detection now ranks crop-compatible disease candidates and stores alternatives for validation instead of returning only a generic anomaly.

## Validation after satellite triage

- 1000 lightweight checks re-executed: 1000/1000 passed.
- Extra static checks: 22/22 passed.
## 2026-06-11 - Scientific CSV Review

- Created CSV backup at `backups/pre_csv_scientific_review_2026-06-11T00-30-17-874Z`.
- Replaced weakly traceable crop variety labels with named cultivar or cultivar-group references.
- Added `Cycle_DD`, scientific name, source, evidence and notes columns to `crops_db.csv`.
- Added disease model-family, latency, reservoir, vector, rain-splash, jump-rate, source, evidence and notes columns to `diseases_db.csv`.
- Documented scientific interpretation and remaining validation limits in `docs/CSV_SCIENTIFIC_REVIEW.md`.
## 2026-06-11 - CSV Validation Pass

- Re-ran 1000 formal consistency checks after crop and disease CSV review: 1000 passed, 0 failed.
- Added app-relative CSV backup paths so `tools/rollback_selected_changes.py --backup backups/pre_csv_scientific_review_2026-06-11T00-30-17-874Z --files src/data/crops_db.csv src/data/diseases_db.csv` can restore only the CSVs.
- Stored validation result in `support/test_results/aef_1000_checks.json`.
## 2026-06-11 - Access Contact Update

- Created backup at `backups/pre_contact_update_2026-06-11T04-07-46-748Z`.
- Replaced access-code contact email from the previous personal contact to `contact@scale-ag.tech` in `app.py`.
## 2026-06-11 - Smart Field, Soil Detection, Requirements and Contact

- Created backup at `backups/pre_smart_field_soil_2026-06-11T03-36-25-703Z` before smart-field and soil edits.
- Kept the original Step 1 map display block unchanged: Esri satellite tile layer, zoom_start=17, max_zoom=20, LayerControl, polygon drawing/editing and st_folium dimensions.
- Added place-name search, center adjustment, non-square smart-field candidates and polygon editing controls.
- Added WorldCover scoring for non-cultivable cover and Sentinel-2 NDVI homogeneity refinement for the top 8 candidates.
- Improved OpenLandMap soil auto-detection with multi-depth layers, confidence metadata and preservation of auto profiles across reruns.
- Replaced access-code contact email with `contact@scale-ag.tech`.
- Added missing Flask extension requirements and `branca` to `requirements.txt`.
- Documented the audit and remaining limits in `docs/GEOSPATIAL_SOIL_AUDIT.md`.
## 2026-06-11 - 50-Test Validation and 50-Page Report

- Ran 50 targeted static tests after the smart-field, soil, contact and requirements changes: 50 passed, 0 failed.
- Stored the test result in `support/test_results/aef_50_targeted_tests.json`.
- Created `docs/RAPPORT_AEF_CROP_INTELLIGENCE_50_PAGES.md` with 50 Markdown page sections covering audit, corrections, limits, tests and next steps.
## 2026-06-11 - Visible Language Selector

- Created backup at `backups/pre_language_toggle_2026-06-11T10-46-40-947Z`.
- Moved the language selector into the login page so it is visible before access is granted.
- Kept a sidebar language selector after authentication so the selected language applies across app pages.
- Converted the access-code contact sentence to a translated key.

## 2026-06-11 - Intermediate strategy and roguing balance

- Added an explicit intermediate counterfactual strategy between minimum useful action and optimized recommendation.
- Updated disease-control profiles so tau-leaping scenarios now include none, minimum, intermediate, and optimized intervention intensities.
- Made roguing/pruning conditional on a benefit-cost comparison: expected inoculum reduction must exceed productive stand or canopy loss, with stricter durable-cost margins for perennial crops.
- Propagated roguing metrics into ensemble scenario summaries and the generated dossier so removal is never presented as an automatic response.
- Added translated spinner text for the scenario-comparison step and saved targeted validation results in support/test_results/aef_intermediate_roguing_tests.json.

## 2026-06-11 - Full visible UI internationalization pass

- Added a literal translation helper for legacy visible strings so remaining Streamlit and PDF text can switch between English and French without changing model logic.
- Internationalized Dashboard, Site Setup, Adaptive Surveillance, and Report visible labels, alerts, spinners, captions, buttons, PDF section titles, and scenario paragraphs.
- Kept internal option values unchanged where business logic depends on English identifiers, using display-only translation with format_func.
- Added targeted static checks in support/test_results/aef_full_ui_i18n_tests.json.

## 2026-06-11 - Deep dashboard and field-setup internationalization pass

- Completed a second i18n pass on Dashboard and Site Setup after live French review exposed remaining English text.
- Translated dashboard metrics, chart axes, legends, tab labels, map captions, stress summaries, and raw-data table column labels.
- Translated field-setup step labels, tabs, upload prompt, polygon editing controls, soil expert controls, soil texture display labels, infection-log editor columns, soil auto-detection summaries, and navigation buttons.
- Preserved internal English values where workflow logic depends on them, using display-only translation functions and translated display columns.
- Added targeted validation results in support/test_results/aef_dashboard_setup_i18n_deep_tests.json.

## 2026-06-11 - PDF French Unicode compatibility fix

- Added a PDF boundary sanitizer in PDFReport so legacy pyfpdf latin-1 output no longer crashes on French glyphs such as œ, typographic apostrophes, en dashes, narrow no-break spaces, or warning/check symbols.
- Kept the existing PDF engine and agronomic report logic unchanged; only text emitted to PDF cells/writes is normalized to latin-1-safe equivalents.
- Translated the PDF download button label and added targeted validation in support/test_results/aef_pdf_latin1_unicode_fix_tests.json.

## 2026-06-11 - Reality check, detection date, jump dispersal and uncertainty margins

- Created backup at `backups/pre_reality_detection_jumps_uncertainty_2026-06-11T19-44-05-347Z` before these corrections.
- Restricted dashboard and dossier satellite reality checks to the actual observed window from planting/simulation start to today and to the latest available Sentinel-2 observation; forecast dates are no longer compared against non-existent future imagery.
- Separated automatic disease satellite anomaly date from management diagnosis date: the anomaly keeps its Sentinel-2 observation date, while `detection_date` used for intervention scenarios is set to the current day.
- Strengthened disease-family tau-leaping with non-local jump seeding driven by infectious pressure, environmental favourability and insect/vector pressure so vector-borne epidemics can create secondary foci away from the initial focus.
- Added visible stochastic margins of error in the dashboard and generated dossier for forecast yield, total production and disease incidence.
- Updated `docs/SCIENTIFIC_MODELS.md` with the reality-check window, uncertainty envelope equations and non-local jump equation.
- Added targeted validation results in `support/test_results/aef_reality_detection_jumps_uncertainty_tests.json`.

## 2026-06-12 - French PDF report cleanup and prudent uncertainty margins

- Created backup at `backups/pre_pdf_i18n_uncertainty_fix_2026-06-12T00-00-00-000Z` before these corrections.
- Audited the generated French PDF `Exemple_report_AEF_Report_2026-06-12.pdf`; confirmed remaining English in headers, configuration labels, diagnostics, water status, planting-season advice, fertilizer rationales, epidemiology labels and disease-control recommendations.
- Added a PDF rendering translator for model-generated report prose, fertilizer rationale strings and disease-control protocol lines while preserving internal model values.
- Translated PDF header/footer labels, configuration labels, diagnostics, water/nutrition/epidemiology labels, alerts and chart labels.
- Reworked forecast margins so the ensemble combines stochastic spread variability with a conservative operational uncertainty floor based on soil-data confidence, crop horizon, disease uncertainty and adaptive calibration status.
- For perennial crops, report yield uncertainty now uses annual harvest peaks instead of an arbitrary final simulation day.
- Added targeted validation results in `support/test_results/aef_pdf_i18n_uncertainty_fix_tests.json`.

## 2026-06-12 - Dashboard prudent uncertainty floor

- Created backup at `backups/pre_dashboard_uncertainty_floor_2026-06-12T00-20-00-000Z` before this correction.
- Fixed dashboard margin display so yield and incidence intervals cannot collapse to `+/- 0.00` when the ensemble is numerically deterministic or an older cached uncertainty result lacks the conservative profile.
- Dashboard margins now use the maximum of ensemble dispersion and the operational uncertainty floor from the report logic.
- Updated the dashboard caption to state that margins combine stochastic ensemble runs with a conservative operational floor, and that adaptive surveillance can reduce that margin.
- Added targeted validation results in `support/test_results/aef_dashboard_uncertainty_floor_tests.json`.

## 2026-06-12 - Report generation speedup: two scenario comparison

- Created backup at `backups/pre_report_two_scenarios_speedup_2026-06-12T00-45-00-000Z` before this correction.
- Reduced the PDF scenario comparison from four ensemble scenarios to two: no action and Optimized Management.
- Removed minimum and intermediate scenario ensemble runs from report generation to avoid unnecessary long waits on small fields.
- Updated the PDF scenario table, roguing-balance section and scenario spinner text so they no longer reference minimum or intermediate strategies.
- Searched Python modules for vectorization opportunities. No extra vectorization was applied because the likely hotspots are stateful daily simulations, ensemble runs, or small display loops where forced vectorization would risk changing model behavior.
- Added targeted validation results in `support/test_results/aef_two_scenario_report_speedup_tests.json`.

## 2026-06-12 - Cooperative agricultural perimeter mode

- Created backup at `backups/pre_cooperative_mode_2026-06-12T01-30-00-000Z` before adding the cooperative workflow.
- Added a first-screen operating-mode selector so users choose between the unchanged single-field workflow and the new agricultural cooperative workflow.
- Added cooperative perimeter setup with satellite-map display, editable polygon drawing, automatic editable parcel candidates, parcel deletion, parcel redraw and missing-plot addition.
- Added shared or per-plot crop configuration, cooperative disease surveillance, shared soil profile detection/manual expert soil setup, and per-plot nutrient/history inputs while disabling manual irrigation and fertilization calendars in cooperative mode.
- Added a lightweight cooperative simulation adapter that keeps the existing crop/soil/weather physics per parcel and adds a distance-kernel metapopulation disease coupling between parcels.
- Added cooperative dashboard, cooperative adaptive surveillance view and cooperative PDF report, all routed separately from the single-field mode.
- Completed visible-text internationalization for the new cooperative screens and translated the cooperative satellite layer label/default parcel names.
- Fixed cooperative per-plot nutrient normalization so explicit zero nutrient values are preserved rather than replaced by defaults.
- Documented the mode in `docs/COOPERATIVE_MODE_LOG.md`, surveillance behavior in `docs/COOPERATIVE_SURVEILLANCE_LOG.md`, and the metapopulation equations in `docs/COOPERATIVE_METAPOPULATION_MODELS.md`.
- Ran 100 targeted cooperative-mode structural tests: 100 passed, 0 failed. Results stored in `support/test_results/aef_cooperative_mode_100_tests.json`.

## 2026-06-12 - UX, agronomic prudence and cooperative parcel refinement

- Added variable-size cooperative parcel candidate detection with quality warnings and DMS coordinate support.
- Fixed cooperative perimeter areas below 1 ha so saved small perimeters no longer crash Streamlit.
- Added adaptive-calibration normalization for cooperative observations and non-zero uncertainty floors.
- Added lightweight N-P-K vector matching for fertilizer product choice.
- Added practical irrigation/fertilizer feasibility constraints and clearer dashboard/report decision notes.
- Documentation: see docs/UX_AGRO_REFINEMENT_LOG.md.

## 2026-06-12 - Cooperative ergonomics, parcel precision and report optimization

- Cooperative auto-detected plots are now non-overlapping irregular polygons.
- Parcel detection precision was increased with denser candidate search and more shape attempts.
- Generate cooperative perimeter now follows DMS/decimal coordinate entry.
- Manual cooperative disease scouting was restored with marker-based foci and plot assignment.
- Soil/nutrient configuration now includes the cooperative parcel map and editable plot names.
- Cooperative PDF report now includes per-plot optimized irrigation/fertilization and no-action vs optimized comparison.
- Verification: 93/93 static tests in support/test_results/aef_coop_ergonomics_report_tests.json.
