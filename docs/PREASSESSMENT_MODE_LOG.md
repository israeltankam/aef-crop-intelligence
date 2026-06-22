# AEF Crop Intelligence - Pre-assessment Mode Change Log

Date: 2026-06-21
Target folder: C:/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822
Backup created before modification: C:/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822/backups/pre_preassessment_mode_2026-06-21T19-18-30-000Z

## Objective

Add a third operating mode, **Pre-planting assessment**, alongside **Single field** and **Agricultural cooperative**. This mode evaluates a candidate parcel before planting and answers: should this crop variety be planted here, when should planting occur, and what first-cycle irrigation, fertilization and disease-risk precautions should be planned?

## Main files added

- `pages/main/preassessment.py`: Streamlit page for the pre-planting workflow.
- `src/models/preassessment_engine.py`: transparent one-cycle suitability scoring engine.
- `src/utils/preassessment_pdf.py`: branded PDF dossier builder with Scale AG logo support and latin-1 text safety.
- `src/data/disease_pressure_literature.csv`: disease-pressure literature-prior mapping for the diseases currently handled by the app, focused first on Sub-Saharan Africa.
- `docs/PREASSESSMENT_MODE_LOG.md`: this implementation log.
- `support/test_results/aef_preassessment_mode_tests.json`: static test report.

## Main files updated

- `app.py`: added the third operating mode and route.
- `src/models/state_manager.py`: added default session keys for pre-assessment state.
- `src/utils/i18n.py`: added French/English keys for the new mode, fixed report labels, and common engine output phrases.
- `support/User guide.md`: added detailed French and English user-guide sections for pre-assessment.
- `support/User guide.html`: regenerated from the Markdown guide.
- `support/refactor/refactor_manifest.json`: updated to include this change set.

## Scientific and agronomic behaviour

The pre-assessment engine is intentionally a planning aid, not a diagnosis guarantee. It evaluates twelve monthly candidate planting windows from the earliest acceptable date selected by the user. For each candidate, it computes component scores for:

- climate fit relative to crop thermal limits,
- water feasibility from a light ET/rainfall balance,
- soil and nutrient starting conditions,
- regional disease pressure priors adjusted by forecast weather,
- early establishment window quality,
- data confidence.

For perennial crops, the mode assesses one production cycle only, capped at 365 days, as requested. Long-horizon perennial economics remain part of the operational recommendation/report workflow after planting.

Disease pressure is based on a curated CSV of literature-prior pressure levels, climate drivers, host/vector drivers, evidence level and update cadence. Risks are bounded between 0.02 and 0.95 so the tool does not claim impossible absence or certainty of future infection before field surveillance.

## User experience

The page is designed as a four-step flow:

1. Candidate field geometry: center, area, generated polygon, optional satellite/land-cover optimization, and manual polygon editing on the map.
2. Crop and variety selection from the existing crop database.
3. Soil starting point: manual values or automatic gridded soil estimate.
4. Explicit pre-assessment run with spinner, followed by score, candidate planting dates, irrigation calendar, fertilization calendar, disease priors and PDF/JSON exports.

The optimization is never run automatically on page load. Users must configure the parcel, crop and soil first, then launch the assessment.

## Internationalization

All new major page labels, buttons, warnings, spinners, report headings, recommendation labels and common fixed engine outputs were connected to the existing translation helper. Engine JSON keeps stable English keys for portability, while the page and PDF translate fixed farmer-facing text before display.

## Requirements

No new dependency was added. The new mode reuses existing libraries already present in the app: Streamlit, pandas, folium, streamlit-folium and fpdf.

## Tests

Static/invariant validation completed: **196 checks passed, 0 failed**.

The checks covered file presence, Python delimiter sanity, app routing, explicit-run behaviour, spinner presence, i18n coverage, PDF generation hooks, disease-pressure CSV structure, bounded disease uncertainty, one-cycle perennial handling, user-guide updates and absence of obvious placeholders.

Note: the current sandbox could not launch the full Python/Streamlit runtime, so runtime smoke testing should still be performed locally after copying the corrected folder back into the working app.

## 2026-06-22 - Pre-assessment bugfix: parcel placement, recommendation text, climate units and date format

Backup created before modification: `backups/preassessment_parcel_recommendation_fix_2026-06-22T00-00-00-000Z`

### Fixes

- Strengthened automatic candidate-parcel optimization so built-up, water, wetland and other hard non-field cover are treated as rejection conditions, not weak penalties.
- Expanded nearby candidate search offsets so the algorithm can avoid a road, building, water edge or yard near the selected centre while staying close to the intended location.
- Added explicit metadata for built-up percentage, water/wetland percentage, plausible field cover, accepted candidate count and manual-validation requirement.
- In Pre-planting assessment, rejected automatic candidates are no longer applied to the map. The user now receives a clear message and can move the centre or draw the parcel manually.
- Added weather-temperature normalization in the pre-assessment engine for Celsius, Kelvin and tenths-of-degree inputs before scoring and before report text generation.
- Changed climate-fit wording from ambiguous `C` text to explicit `°C` text and removed the path that could display impossible values such as `274 C`.
- Made planting-date candidate tables explicit: dates are labelled as `YYYY-MM-DD` / year-month-day.
- Added a final rich recommendation paragraph at the end of the Pre-planting assessment result and the PDF report.
- Updated French translations and the Markdown/HTML user guide for these visible changes.

### Tests

Static/invariant validation completed: **117 checks passed, 0 failed**.

Test report: `support/test_results/aef_preassessment_parcel_recommendation_fix_tests.json`.

Note: the sandbox still cannot launch the full Streamlit/Earth Engine runtime, so the automatic boundary behaviour should be smoke-tested locally with a known urban-centre case and a known cultivable-centre case.
