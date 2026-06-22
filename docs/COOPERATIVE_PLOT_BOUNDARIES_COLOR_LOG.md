# Cooperative Plot Boundary Separation and Map Color Log

Date: 2026-06-22

## Objective

Improve the cooperative-mode internal parcel delineation so automatically suggested plots are not visually or geometrically glued together, are not nested/overlapped, and remain easy for a non-technical user to inspect and edit on the satellite map. Preserve the FTW fallback recommendation when AEF internal confidence is limited.

## Changes Made

- Added a lightweight geometry clearance check to the deterministic cooperative fallback detector.
- The fallback now rejects candidate polygons that overlap, touch, or sit closer than a small size-scaled boundary gap.
- Reduced fallback total coverage from 96% to 92% of the perimeter so paths, ridges, drainage lines, uncultivable strips and unassigned gaps can remain visible.
- Kept polygon shapes irregular and editable; no rectangular grid forcing was added.
- Added a four-colour-inspired display palette for cooperative plots on the setup map.
- Added a white under-stroke below each plot outline so narrow boundaries remain readable over satellite imagery.
- Kept the selected parcel highlight in amber.
- Kept FTW fallback signalling unchanged: internal Sentinel-2 detections still set `ftw_fallback_recommended` when confidence is low, and the geometric fallback still recommends user validation.
- Updated the Markdown and HTML user guides to explain the thin boundary requirement, contrasting plot colours and FTW fallback role.

## Files Modified

- `src/models/cooperative_parcel_detector.py`
- `pages/main/setup_page.py`
- `support/User guide.md`
- `support/User guide.html`
- `support/test_results/aef_cooperative_plot_boundaries_colors_tests.json`

## Scientific and Agronomic Rationale

Smallholder cooperative perimeters are usually mosaics of management units, not one continuous cadastral block. Even when plot borders are narrow, they often correspond to footpaths, ridges, drainage lines, crop-row discontinuities, tenure limits or management differences. A fallback detector that fills all available area with touching polygons risks inventing artificial boundaries and making the map harder to audit. The improved fallback therefore keeps a narrow explicit separation between synthetic candidate polygons. Sentinel-2 and future FTW-derived boundaries remain preferable when image evidence is strong.

## Validation

- 100 static and geometry micro-tests passed.
- Test file: `support/test_results/aef_cooperative_plot_boundaries_colors_tests.json`
- Python/Streamlit execution was not available from this sandboxed Windows-temp access path, so runtime UI validation should still be done once the user copies the corrected folder into the normal app environment.

## Requirements

No new dependency was added. The implementation deliberately avoids heavy geometry packages so page loading remains responsive.
