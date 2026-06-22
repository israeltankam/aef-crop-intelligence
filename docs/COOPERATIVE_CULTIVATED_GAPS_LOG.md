# Cooperative Cultivated Gaps Implementation Log

Date: 2026-06-22

## Objective

Make cooperative mode aware that a cooperative perimeter can contain large non-cultivated gaps. The app must not force parcel candidates to fill the whole perimeter, and the metapopulation disease layer must not treat distant plots across roads, fallows, water, buildings or uncultivated land as if they were adjacent crop cover.

## Main Changes

### Parcel Detection

- The expected plot count is now a count prior, not a perimeter-filling prior.
- Sentinel-2 segmentation and the geometric fallback now keep the typical plot size when the expected number of plots multiplied by the typical plot size covers only a sparse fraction of the perimeter.
- The older behaviour that implicitly allocated about 92% of the perimeter to plots has been removed.
- The fallback now caps total generated plot area well below the full perimeter and, when the expected plot count is known, around the expected cultivated area.
- Sentinel-2 detection estimates a rough image-cultivable fraction from the candidate mask so the UI can communicate whether the perimeter contains large non-cultivated regions.
- FTW fallback signalling remains in place when internal boundary confidence is limited.

### Configuration and UI

- Added persistent cooperative fields:
  - `cooperative_cultivated_area_ha`
  - `cooperative_unassigned_area_ha`
  - `cooperative_cultivated_fraction`
- These values are recalculated after detection and after the user edits/enables/disables plots.
- The cooperative setup page displays active cultivated area, unassigned/non-cultivated area and cultivated fraction.
- The cooperative dashboard and final report expose the same gap-aware metrics.
- The user guide was updated in Markdown and HTML.

### Disease Metapopulation

- The cooperative metapopulation kernel is no longer row-normalized. Absolute distance now matters.
- A landscape gap factor is applied:

$$
G = clip(0.25 + 0.75F_c, 0.25, 1.0)
$$

where `F_c` is the cultivated fraction inside the cooperative perimeter.
- Disease pressure still has a floor because vectors, labour, tools, water and wind can move inoculum across gaps, but wide non-cultivated spaces now reduce coupling.
- Aggregate history now records `Metapopulation_Gap_Factor` and `Cooperative_Cultivated_Fraction`.

## Files Modified

- `src/models/cooperative_parcel_detector.py`
- `src/models/sentinel_parcel_detector.py`
- `pages/main/setup_page.py`
- `src/models/cooperative_engine.py`
- `src/models/state_manager.py`
- `src/utils/parcel_quality.py`
- `src/utils/i18n.py`
- `pages/main/dashboard.py`
- `pages/main/report.py`
- `docs/COOPERATIVE_METAPOPULATION_MODELS.md`
- `support/User guide.md`
- `support/User guide.html`
- `support/test_results/aef_cooperative_cultivated_gaps_tests.json`

## Validation

- 100/100 static and algorithm micro-tests passed.
- Test report: `support/test_results/aef_cooperative_cultivated_gaps_tests.json`
- Python/Streamlit runtime validation was not possible from this sandbox because child process spawning is blocked, so the next check should be a visual app run in the normal Streamlit environment.

## Remaining Practical Limit

The geometric fallback remains a conservative candidate generator, not an image-true boundary detector. It now avoids the worst perimeter-filling bias, but Sentinel-2/WorldCover and eventually FTW-derived boundaries remain the better path when the image signal is strong enough.
