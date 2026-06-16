# Cooperative Ergonomics, Parcel Precision and Report Optimization Log

Date: 2026-06-12
Working copy: C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822
Backup before changes: backups/pre_coop_ergonomics_precision_report_2026-06-12T13-30-00-000Z
Test report: support/test_results/aef_coop_ergonomics_report_tests.json

## Changes Applied

- Reworked cooperative automatic parcel detection so accepted candidates are non-overlapping.
- Replaced rectangle-like generated plots with irregular 6-9 vertex polygons.
- Doubled the detection precision by using a denser centroid search, more shape attempts per centroid, and a larger default parcel budget.
- Moved the Generate cooperative perimeter button after the DMS/decimal coordinate entry workflow.
- Restored explicit manual disease scouting in cooperative mode with a manual tab, marker-based foci, affected plant count, severity, plot assignment, editable table and clear button.
- Added plot-name labels directly on cooperative maps so users can identify each plot visually.
- Added the cooperative parcel map to soil/nutrient configuration.
- Allowed plot names to be edited again from the soil/nutrient table and preserved in the JSON configuration through cooperative_parcels.
- Added a plot-reference table in the cooperative review step.
- Added cooperative report optimization: irrigation and fertilization are optimized by plot, compared against the no-action baseline, and summarized in the PDF.
- Added a maximum-plot optimization control for very large cooperatives, prioritizing highest-risk plots when the limit is below the number of active plots.
- Added French translations for new UI and report texts.

## Scientific and Practical Notes

The parcel detector remains a transparent candidate generator, not a trained cadastral or field-boundary segmentation model. Its output is now safer because it rejects overlapping polygons and creates more field-like irregular shapes, but visual validation on the satellite map remains mandatory.

The cooperative report optimization uses the existing single-plot engines per parcel, then aggregates expected production gain, irrigation water and fertilizer product needs. This is heavier than the previous report but gives a real no-action versus optimized-management comparison.

## Verification

Static tests: 93 / 93 passed.
Live Streamlit testing was not possible in this tool environment because shell/server execution is unavailable here.
