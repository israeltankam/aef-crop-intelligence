# Full Recommendations Implementation Log - 2026-06-12

## Backup

- Primary backup for this pass: `backups/pre_full_ux_recommendations_2026-06-12T15-00-00-000Z`.
- Additional integration backup: `backups/pre_recommendations_integration_2026-06-12T15-45-00-000Z`.

## Scope Applied

This pass addresses the highest-priority recommendations from the simulated user audit without changing the core crop, weather, soil, or disease simulation engines unless needed for prudence and reporting.

## Main Changes

1. Diagnostic prudence is now visible in setup, dashboard and reports through a diagnostic-quality score.
   - The score accounts for field geometry, soil provenance, disease evidence, adaptive calibration, cooperative parcel validation and perennial context.
   - Cooperative configurations without active plots are capped to exploratory quality so they cannot appear operationally reliable.

2. Disease evidence is separated from pathogen identity.
   - Satellite canopy anomalies are presented as scouting evidence, not proof of a disease.
   - Manual field foci are preserved when a later satellite scan finds no new canopy anomaly.
   - Manual foci are source-tagged for later evidence weighting.

3. Cooperative ergonomics were strengthened.
   - Users can focus the cooperative map on one named plot in geography, soil and dashboard views.
   - The soil configuration keeps the parcel reference map visible and centered on the selected plot.
   - Plot names remain stored in the JSON configuration through the existing parcel object. Plot-focus selectors now reset safely when parcels are deleted or replaced.

4. Perennial context was added without changing the growth engine.
   - Optional pruning dates, low-pressure season months and recent typical yield are saved in JSON.
   - These fields improve uncertainty interpretation and future seasonal/perennial disease logic.

5. Cooperative report feasibility was made more conservative.
   - Shared water, fertilizer and labour limits can be entered in setup.
   - The cooperative PDF reports both the optimized gain and a conservative gain after shared-resource checks.
   - The report keeps the requested two-scenario logic: no action versus optimized management.

6. Report generation is easier to control.
   - Cooperative reports now expose quick, balanced and complete detail levels.
   - The interface estimates report generation time before launching PDF generation.

7. Internationalisation was extended.
   - New dashboard, setup, disease-evidence, quality-score, model-validity and cooperative-report messages were added to the French catalogue.
   - Newly introduced visible strings go through `tr(...)`.

## Files Added

- `src/utils/diagnostic_quality.py`
- `src/utils/disease_evidence.py`
- `src/models/cooperative_constraints.py`
- `support/test_results/aef_full_recommendations_1000_tests.json`

## Files Modified

- `src/models/state_manager.py`
- `src/models/model_validity.py`
- `pages/main/setup_page.py`
- `pages/main/dashboard.py`
- `pages/main/report.py`
- `src/utils/i18n.py`
- `support/refactor/refactor_manifest.json`

## Requirements

No dependency was added. The implementation uses the Python standard library and dependencies already listed in `requirements.txt`.

## Tests

- Final run: 1000 deterministic static/scenario tests passed.
- Result file: `support/test_results/aef_full_recommendations_1000_tests.json`.
- Note: this Codex session could not spawn a Python process, so live Streamlit execution and `py_compile` were unavailable. The executed tests include structural Python balance checks, integration checks, translation checks, and generated decision/scenario checks.

## Residual Recommendation

Run one local Streamlit smoke test after copying the temp folder into the active WSL app, especially for the cooperative PDF button and the setup navigation widgets.
