# Scientific Variety and Disease Database Review Log

Date: 2026-06-22
Target folder: `C:/Users/tankamch/AppData/Local/Temp/aef_corrected_1781125311822`
Backup created before modification: `backups/pre_scientific_variety_disease_review_2026-06-22T00-00-00-000Z`

## Scope

This review enriched the crop-variety and disease CSVs using only documented varieties, documented disease agents, and conservative trait interpretations. It did not invent variety names, did not assign immunity where the literature only supports tolerance, and did not treat one scalar resistance value as a complete disease profile.

Updated files:

- `src/data/crops_db.csv`
- `src/data/diseases_db.csv`
- `src/data/variety_scientific_review_evidence.csv`
- `docs/SCIENTIFIC_VARIETY_DISEASE_REVIEW_LOG.md`

## Curation Rules

1. A variety was added only when its name is documented in scientific, CGIAR, national research or specialist crop-catalogue literature.
2. Resistance was recorded disease-by-disease in `Resistance_Profile`; a variety was not labelled globally resistant unless the reviewed source supported that specific interpretation.
3. The legacy `Resistance_Score` in AEF is treated as a susceptibility-risk proxy: lower values mean stronger documented resistance. This matches the current disease-risk formula in the pre-assessment engine.
4. Crop model parameters such as RUE, LAI, harvest index, Kc and rooting depth are still model priors unless the source directly documents a variety-specific value. The notes explicitly mark them as priors.
5. If evidence was regional or cultivar performance is known to depend strongly on pathogen race or environment, `Evidence_Level` was kept at `medium-low` and `Curation_Status` says local validation is required.

## Variety Updates

Before review: 13 crop-variety rows.
After review: 29 crop-variety rows.

Added varieties:

| Crop | Added varieties | Review outcome |
|---|---|---|
| Cassava | IITA-TMS-IBA980581; NASE 14 | Added as documented improved cassava germplasm. CMD tolerance is represented cautiously; CBSD is not treated as immune. |
| Maize | ZM521; ZM523 | Added as CIMMYT/DTMA drought-tolerant OPV references. Disease resistance is not over-claimed. |
| Cocoa | Scavina 6; TSH 565 | SCA 6 is represented mainly as a resistance donor, especially for witches broom contexts; TSH 565 is kept as medium-low evidence with partial/context-dependent disease response. |
| Wheat | Kingbird; Danda’a | Added for rust-risk contexts; resistance remains race- and region-dependent. |
| Rice | NERICA 4; NERICA-L 19; IR36 | NERICA traits follow AfricaRice documentation. NERICA-L 19 receives stronger blast/iron-toxicity/drought prior than generic rice. IR36 is added as a historical IRRI resistant/short-cycle benchmark with race-evolution caution. |
| Soybean | TGx 1835-10E; TGx 1987-62F | Added as documented IITA/tropical soybean germplasm. Promiscuous nodulation is represented through lower mineral N demand, not through a full legume module. Disease immunity is not claimed. |
| Coffee | Ruiru 11; Batian; S795 Selection 3 | WCR catalog drives relative disease ranking: Ruiru 11 strongest coffee disease prior, Batian CBD-resistant/rust-tolerant, S795 not treated as rust-resistant because WCR currently rates rust resistance low/susceptible. |

New columns added to `crops_db.csv`:

- `Adaptation_Zone`
- `Documented_Traits`
- `Resistance_Profile`
- `Trait_Source_URL`
- `Curation_Date`
- `Curation_Status`

These columns are additive and preserve existing app logic. They make the database reviewable without forcing an immediate change to the simulation engine.

## Disease Updates

`diseases_db.csv` kept its 28 disease rows. The review added audit columns rather than inventing new diseases:

- `Causal_Agent`
- `Primary_Literature_Basis`
- `Disease_Curation_Status`
- `Parameter_Confidence_Rationale`

For example, rice blast is explicitly linked to `Magnaporthe oryzae / Pyricularia oryzae`, coffee leaf rust to `Hemileia vastatrix`, cocoa black pod to `Phytophthora megakarya` / `P. palmivora`, and cassava mosaic disease to the cassava mosaic begomovirus complex. Numeric beta/dispersal/recovery values were not made more confident simply because the causal agent was identified.

## Key Sources Consulted

- AfricaRice NERICA documentation: https://www.africarice.org/nerica
- World Coffee Research variety catalog, Ruiru 11: https://varieties.worldcoffeeresearch.org/varieties/ruiru-11
- World Coffee Research variety catalog, Batian: https://varieties.worldcoffeeresearch.org/varieties/batian
- World Coffee Research variety catalog, S795: https://varieties.worldcoffeeresearch.org/varieties/s795
- IRRI / Khush rice variety literature for IR36 and IR-series historical disease resistance.
- CIMMYT / DTMA maize literature for ZM drought-tolerant OPVs.
- CIMMYT / Borlaug Global Rust Initiative wheat rust literature for Kingbird/Danda’a style rust-resistance curation.
- IITA cassava and soybean breeding literature for TMS/NASE/TGx materials.
- Cocoa disease-resistance literature and ICCO/CacaoNet-style references for SCA/TSH clone interpretation.
- Plant pathology literature for causal agents and transmission classes of the 28 disease rows.

## Important Limitations

- This is a conservative enrichment pass, not a definitive national variety catalogue. Seed availability and official recommendation status must be checked by country before farmer-facing deployment.
- Resistance is pathogen-race dependent. A variety resistant in one source or region can be less resistant elsewhere.
- Crop-model parameters remain priors unless field calibration or a variety-specific physiological study is available.
- For crops where specific quantitative variety data were weak, the row is marked `medium-low` rather than being presented as certain.
- The next scientific pass should prioritize country-specific catalogues for Cameroon and neighbouring countries, especially cotton, cassava, maize, cocoa and coffee.

## Tests

Static CSV validation was run after the update and stored in `support/test_results/aef_scientific_variety_disease_review_tests.json`.
