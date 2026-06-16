# Dashboard Calendar Date Input Log - 2026-06-13

## Backup

- Backup: `backups/pre_dashboard_calendar_date_input_2026-06-13T00-00-00-000Z`.
- Files backed up: `pages/main/dashboard.py`, `src/utils/i18n.py`.

## Change

The dashboard forecast-date navigation no longer uses a timeline slider. It now uses a calendar-style `st.date_input` bounded by the simulated forecast horizon.

## Rationale

A calendar is more intuitive for users who want to inspect the expected field state on a precise future event date. This is especially useful for perennial simulations and long cooperative horizons where a slider becomes imprecise.

## Internationalisation

Added French translations for:

- `Forecast date`
- `Choose the exact date where you want to inspect the simulated field status.`
- `Forecast horizon: {start} to {end}`

## Tests

- Result file: `support/test_results/aef_dashboard_calendar_date_input_tests.json`.
- Checks: 6/6 passed.
