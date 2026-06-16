# Cooperative Adaptive Surveillance Log

Date: 2026-06-12

## Purpose

The cooperative surveillance workflow records field observations either for the full cooperative perimeter or for one specific plot. This is required because smallholders in the same perimeter may have different planting dates, nutrient histories and disease pressure.

## Observation Model

Each observation record may include:

- mode = cooperative;
- scope = cooperative or plot;
- plot_id when the observation targets one plot;
- observation date;
- measurement category;
- confidence score;
- disease incidence, soil N/P/K, or yield/biomass value depending on category.

## Adaptive Use

The dashboard simulation produces plot-level risk indicators. The surveillance page ranks plots by disease incidence and metapopulation pressure and suggests the next field check on the highest-risk plot. These observations are stored in the same surveillance log structure so that the calibration module can later use them.

## Calibration Roadmap

1. Use plot-level disease observations to update local infection pressure and the inter-plot coupling rate.
2. Use plot-level nutrient observations to update initial N/P/K for the corresponding plot.
3. Use cooperative-level observations as weaker, aggregated evidence across all active plots.
4. Reduce the operational uncertainty floor only when enough dated field observations exist.

## Current Implementation Limit

The current pass records and prioritizes cooperative observations, but it does not yet perform full hierarchical Bayesian calibration by plot. That remains a pilot-stage extension.
