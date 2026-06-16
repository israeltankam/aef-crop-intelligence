# Smart Field and Soil Detection Audit

Date: 2026-06-11
Scope: pages/main/setup_page.py, src/models/state_manager.py, requirements.txt

## Field Geography Audit

The previous assisted field generator used nine square candidates around the GPS center. It validated these candidates with ESA WorldCover classes, mainly checking built-up and water pixels. This was useful but too restrictive because real fields are often rectangular, angled, elongated, clipped by roads or streams, or irregular.

The map display itself was already good and has been preserved exactly: Folium map centered on the selected point, zoom_start=17, max_zoom=20, Esri World Imagery as a selectable base layer, LayerControl, polygon drawing and editing, and st_folium height 500 / width 800.

## Field Geography Changes

- Added place-name search as an alternative to GPS coordinates, while keeping GPS as the preferred path.
- Added editable latitude and longitude fields so users can adjust a place-search result before generating the field.
- Replaced square-only generation with multiple lightweight polygon candidates: square, elongated rectangles, diamond, hexagon, octagon, trapezoid and notched polygons.
- Candidate scoring now balances requested area, distance from the requested center, cultivable cover, non-cultivable cover, dominant-cover consistency and Sentinel-2 NDVI homogeneity.
- WorldCover is used as a first pass. Sentinel-2 NDVI homogeneity is only run on the top 8 candidates to avoid heavy setup latency.
- Added move, rotate, resize and point-table editing tools while preserving the original map block.

## Soil Detection Audit

The previous auto-soil logic used OpenLandMap texture at b0 only, organic carbon at b0, clay at b0, then derived N/P/K with simple heuristics. This kept the workflow accessible, but treated a 250 m gridded prediction as if it were a direct field soil test.

## Soil Detection Changes

- Reads OpenLandMap layers across available depth bands from 0 to about 1.5 m where present.
- Builds a multi-layer soil profile with texture, field capacity and wilting point per layer.
- Computes organic carbon and clay as thickness-weighted averages.
- Adds soil_data_source, soil_confidence and soil_detection_notes to session state and exported JSON.
- Preserves the auto-detected multi-layer profile across reruns unless the user manually changes the texture class.
- Displays a visible confidence note to remind users that automatic soil detection should be replaced by lab or field measurements when possible.

## Data Sources

- ESA WorldCover via Google Earth Engine: https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v100
- Sentinel-2 Surface Reflectance Harmonized via Google Earth Engine: https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED
- OpenLandMap USDA soil texture classes: https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_TEXTURE-CLASS_USDA-TT_M_v02
- OpenLandMap organic carbon: https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_ORGANIC-CARBON_USDA-6A1C_M_v02
- OpenLandMap clay fraction: https://developers.google.com/earth-engine/datasets/catalog/OpenLandMap_SOL_SOL_CLAY-WFRACTION_USDA-3A1A1A_M_v02

## Remaining Limits

- WorldCover and OpenLandMap are gridded products; they can miss narrow roads, small streams, boundaries, and intra-field variability.
- The generated polygon is a decision-support proposal, not a cadastral boundary.
- Soil nutrients are still approximations. They should be calibrated with field measurements through the adaptive surveillance module.
