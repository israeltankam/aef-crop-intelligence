# Scientific CSV Review - Crops, Varieties and Diseases

Date: 2026-06-11
Scope: src/data/crops_db.csv and src/data/diseases_db.csv

## Objective

The CSV review replaces generic or weakly traceable entries with named crop varieties, cultivar groups, and disease parameters that can be defended scientifically during pilot validation. The values are not presented as final local truth. They are pilot priors: credible starting values that the adaptive calibration module must update with field measurements.

## Crop CSV Decisions

The crop table now keeps 13 crop-variety entries but adds traceability fields:

- Scientific_Name
- Variety_Status
- Parameter_Source
- Evidence_Level
- Parameter_Notes
- Cycle_DD, retained separately from Cycle_Days so thermal-time growth models do not confuse calendar duration with accumulated degree-days.

Replacements made:

- Cassava Local White was replaced by TMS 30572, a documented IITA cassava variety.
- Pioneer P1197 was replaced by African-relevant maize references: Obatanpa QPM and SAMMAZ 52.
- Generic winter wheat was replaced by Norman Borlaug 100, a named CIMMYT-derived bread wheat reference.
- Cocoa and coffee now use documented cultivar groups or clones and explicit pruning/woody biomass parameters.
- Rice uses IR64, an IRRI released variety, as a transparent lowland rice reference.
- Soybean uses TGx 1448-2E as an IITA TGx line reference.

## Disease CSV Decisions

The disease table still contains 28 diseases, but each disease now includes model-driving traits:

- Model_Family: viral_vector, fungal_airborne, bacterial_splash, or soil_reservoir.
- Latency_Days: reduces unrealistic immediate disease explosion.
- Reservoir_Persistence_Days: finite persistence, especially important for perennials.
- Vector_Weight and Rain_Splash_Weight: separate vector-driven disease from rain-splash disease.
- Long_Jump_Rate: keeps stochastic jumps for windborne/vector diseases so simulated spread is not a perfect circular front.
- Parameter_Source, Evidence_Level, and Parameter_Notes.

## Interpretation Rules

1. Parameters are priors, not local calibration endpoints.
2. Evidence_Level flags how confidently the value should be used before field calibration.
3. For perennial crops, reservoir persistence is finite and pruning modifies pressure without erasing the cost of lost canopy or removed plants.
4. Roguing is not always beneficial. The recommendation layer must compare inoculum reduction against the yield loss caused by removed plants.
5. Satellite disease detection should map canopy anomalies to several plausible diseases and let the user confirm the most likely disease in one click.

## Scientific Anchors

- FAO-56 is the anchor for crop coefficients, rooting depth concepts, water stress coefficients and irrigation scheduling.
- AquaCrop is the preferred light water-productivity reference for herbaceous crops under water limitation.
- DSSAT and APSIM are the target high-fidelity families for crop, soil, water, nutrient and management interactions where enough input data are available.
- Disease-specific parameters are structured around published epidemiological traits: latency, dispersal mode, vector dependency, survival reservoir and weather suitability.

## Known Limits

- Several cultivar-specific coefficients remain medium or medium-low evidence because exact cultivar parameters vary by site, management and soil.
- The table should be refined with regional seed catalogues, national variety-release documents and local trial datasets during pilots.
- The current CSVs cannot replace a full APSIM/DSSAT cultivar file; they are compatibility priors for the present app.
- Disease beta values must be re-estimated by adaptive calibration when field incidence time series become available.

## Review Checklist Before Production Deployment

- Confirm that every target deployment country has locally available varieties.
- Replace medium-low evidence rows with national variety-release data when available.
- Add cultivar-specific phenology, photoperiod and vernalization traits when APSIM/DSSAT backends are physically integrated.
- Validate disease latency and reservoir values against local plant pathology teams.
- Keep automatic satellite triage, but expose uncertainty and candidate diseases to users.
