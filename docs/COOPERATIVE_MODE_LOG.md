# Cooperative Mode Addition Log

Date: 2026-06-12
Backup: backups/pre_cooperative_mode_2026-06-12T01-30-00-000Z

## Scope

This change adds a second operating mode for agricultural cooperatives while preserving the original single-field workflow.

## User Flow

1. After authentication, the user chooses either Single field or Agricultural cooperative.
2. Single field keeps the existing workflow unchanged.
3. Cooperative mode opens a separate setup flow with one perimeter and many editable plots.
4. The cooperative setup supports perimeter drawing, automatic candidate plot detection, manual plot addition, plot replacement, plot removal, shared crop settings, per-plot planting/nutrient settings, disease surveillance, shared soil profile detection and review.

## Files Added Or Changed

- app.py: first-run mode selector and active-mode sidebar display.
- src/models/state_manager.py: cooperative state keys and save/load support.
- src/models/cooperative_engine.py: per-plot simulation adapter and metapopulation aggregation.
- pages/main/setup_page.py: cooperative setup workflow.
- pages/main/dashboard.py: cooperative dashboard view.
- pages/main/surveillance.py: cooperative adaptive surveillance view.
- pages/main/report.py: cooperative PDF dossier.
- src/utils/i18n.py: translated cooperative UI strings.

## Robustness Choices

- Cooperative mode does not alter the single-field workflow.
- Plot detection is deterministic and editable; it is not presented as a final remote-sensing classifier.
- Manual irrigation and fertilization calendars are disabled in cooperative setup as requested.
- Soil physics remains shared across the perimeter, while initial nutrients and land-use history can differ by plot.
- Disease coupling is added after plot-level simulations to preserve existing phenology and within-plot disease engines.

## Known Limits For Pilot Review

- Automatic parcel detection currently uses a conservative geometric candidate generator inside the perimeter. It should later be replaced or augmented by validated Sentinel-2/Sentinel-1 parcel segmentation.
- Cooperative simulations run plot by plot. For very large cooperatives, batching or a reduced preview mode may be needed.
- The metapopulation layer is a light distance-kernel coupling and should be calibrated during pilots.
