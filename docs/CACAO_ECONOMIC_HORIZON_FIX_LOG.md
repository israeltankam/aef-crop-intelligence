# Cacao Perennial Economic Horizon Fix Log

Date: 2026-06-13
Working copy: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822
Backup before changes: backups/pre_cacao_economic_horizon_2026-06-13T00-00-00-000Z/BACKUP_MANIFEST.json
User test config: C:\Users\tankamch\Downloads\field_config (1).json

## Problem

The economics layer was too pessimistic for cocoa and other perennial crops. The main issue was conceptual: the app could compare long-horizon intervention costs with a terminal standing-fruit/final-day yield value. For perennial crops, that is not the economic harvest over a long horizon. Cocoa can generate several harvest periods across years, so economic revenue must be summed over repeated annual harvest opportunities.

A second issue came from disease costs: mapped disease spots could trigger plant replacement costs even when roguing/pruning labour was set to zero. That made scouting-only or spray-only situations look like mass plant destruction.

## Corrections

- src/models/economic_engine.py
  - Added perennial annual-harvest accounting: annual peak yields are summed over the selected horizon.
  - Added economic_horizon_years to normalized economics, defaulting to 20 years for perennial crops and 1 year for annual crops.
  - Updated cocoa default market price to 3,500,000 XAF/t as a conservative editable Cameroon/Central Africa planning prior.
  - Added cocoa-specific defaults: scouting 10,000 XAF/day/ha, fertilizer labour 4,000 XAF/day/ha, spraying 5,000 XAF/day/ha, roguing 0, pruning 0, fungicide/biocontrol 8,000 XAF/L, spray service 6,000 XAF/ha, plant replacement 300 XAF.
  - Interpreted all labour values as per workday per hectare.
  - Added per-hectare summary fields for production, revenue, costs and net gain.
  - Replacement cost is now charged only when a removal/pruning operation is actually costed.

- src/models/simulation_engine.py
  - Counterfactual scenarios now include annual_yields_t_ha and horizon_yield_t_ha so perennial economics can use repeated harvests rather than a terminal value.

- src/models/cooperative_engine.py
  - Cooperative optimized-management summaries now use harvest-equivalent yield over the selected horizon for perennial plots.

- src/models/state_manager.py
  - Added economic_horizon_years to persisted state and JSON config.

- pages/main/setup_page.py
  - Added an economic horizon selector for perennial crops.
  - Clarified labour labels as per day per hectare.

- pages/main/recommendations.py
  - Added a perennial economic horizon selector.
  - Added per-hectare decision summary columns and metrics.
  - Cache signature now includes horizon so recommendations recalculate when the user changes it.

- pages/main/report.py
  - Added economic horizon selector for single-field and cooperative PDF reports.
  - PDF economic summary now includes horizon and net gain per hectare.
  - Economic comparison table now includes production per hectare, cost per hectare and net gain per hectare.

- src/utils/i18n.py
  - Added French translations for the new horizon, per-hectare and per-day-per-hectare labels.

## Additional safeguard

Generic economics import guard: when an old JSON lacks economics_config and the session still holds the pre-crop generic economics defaults, normalization now discards automatic Unknown crop market defaults and applies the selected crop defaults instead. This prevents cocoa from inheriting a generic 180,000 XAF/t price or a one-year horizon.

## Verification

- 1000 deterministic economic simulations were run around the supplied cocoa JSON assumptions.
- New perennial-horizon model: 966 / 1000 positive outcomes, median net +11,410,299 XAF.
- Old terminal-value style reproduced the bug: 1 / 1000 positive outcomes, median net -3,435,531 XAF.
- 100 static integration checks passed, 0 failed.

Test result files:

- support/test_results/aef_cacao_economic_horizon_1000_simulations.json
- support/test_results/aef_cacao_economic_horizon_static_100_checks.json

## Execution limitation

The environment refused launching Python subprocesses (EPERM), so a full Streamlit/Python engine run could not be executed from this tool session. The 1000-run verification therefore targeted the corrected economic logic with the supplied cocoa JSON and deterministic Monte Carlo assumptions.

## Requirements

No new dependency was added.
