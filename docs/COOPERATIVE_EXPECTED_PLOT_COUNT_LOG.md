# Cooperative Expected Plot Count Detection Log

Date: 2026-06-22

## Objective

Improve automatic parcel delineation in cooperative mode by allowing the user to enter the expected number of non-overlapping individual plots inside the cooperative perimeter.

## Why this matters

The previous detector inferred plot count mostly from perimeter area and typical parcel size. In smallholder mosaics, that can over-detect or under-detect because parcel sizes vary, paths and uncultivable gaps exist, and Sentinel-2 segmentation may split or merge fields. A known plot count is useful field knowledge and should guide the algorithm.

## Changes applied

- Added `cooperative_expected_plot_count` to default state, JSON export and JSON import.
- Added an `Expected number of plots` input in cooperative perimeter setup. The value 0 means unknown and preserves the previous behaviour.
- Passed the expected count into the Sentinel-2 internal detector and the deterministic geometric fallback.
- In Sentinel-2 detection, the expected count now adjusts the effective target parcel area, SNIC seed spacing, area filters and final candidate selection.
- In geometric fallback, the expected count now adjusts target parcel area and hard-stops candidate generation at the requested non-overlapping count.
- Added UI feedback showing expected plots, detected plots and the difference.
- Added a warning when the detected count differs materially from the expected count.
- Updated French translations and user guide MD/HTML.

## Scientific and operational caution

The expected count is a strong prior, not proof of true boundaries. AEF still presents editable candidate polygons and requires validation on the satellite map. If the detected count and the expected count disagree, the user should edit polygons or adjust the count before using cooperative recommendations.

## Backup

A full pre-change backup was created in the Windows temp directory before edits.

## Verification

- 100 static and consistency checks passed.
- Test results: `support/test_results/aef_cooperative_expected_plot_count_tests.json`.
- Python execution/py_compile could not be launched from the current Codex sandbox because Windows process spawning is blocked, so the verification focused on deterministic code, wiring, i18n, guide and JSON-persistence checks.

## Backup path

`C:/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822_backup_coop_expected_plots_2026-06-22T15-49-56-225Z`
