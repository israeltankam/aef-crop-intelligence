# Sentinel-2 internal cooperative parcel detection log

Date: 2026-06-21
Backup: backups/pre_sentinel_internal_parcel_detection_2026-06-21T18-48-50-876Z

## Objective

Improve AEF Crop Intelligence's own parcel-boundary algorithm before relying on Fields of The World. The previous cooperative detector generated plausible non-overlapping irregular polygons from perimeter geometry and typical parcel size. It did not use satellite imagery and therefore could not be considered real boundary detection.

## What changed

- Added `src/models/sentinel_parcel_detector.py`, an AEF internal detector using Earth Engine, Sentinel-2 SR Harmonized and ESA WorldCover.
- The cooperative setup now tries Sentinel-2 image-guided segmentation first.
- If Earth Engine is unavailable, the perimeter is too large, clear Sentinel-2 observations are insufficient, or segmentation returns no usable parcel, the app falls back to the existing geometric candidate generator.
- The geometric fallback confidence is capped lower because it has no image evidence.
- The UI now displays:
  - detection method;
  - estimated boundary precision;
  - mean confidence;
  - Sentinel-2 image window and clear observation count when available;
  - a warning when low precision suggests future FTW precomputed-boundary fallback.
- The user guide Markdown and HTML were updated to explain the new Sentinel-2 first workflow and the fallback logic.
- No FTW API or FTW dataset query was integrated in this pass; FTW remains the next optional fallback after AEF's internal detector.

## Algorithm retained

The new internal detector follows this sequence:

1. Build a cloud-masked Sentinel-2 median composite over the cooperative perimeter.
2. Compute NDVI, NDMI and a brightness proxy.
3. Use ESA WorldCover to focus on vegetated/cultivable pixels, including tree cover for perennial plantations.
4. Run Earth Engine SNIC segmentation with seed spacing tied to the user's typical parcel size.
5. Polygonize server-side segments into editable parcel geometries.
6. Filter tiny fragments and excessively large merged blobs.
7. Estimate confidence from area plausibility, NDVI level, NDVI homogeneity, cultivable fraction, valid-pixel fraction and compactness.
8. Mark the result as high, moderate or low estimated precision.

## Scientific caution

The confidence score is not a cadastral accuracy metric. It is an interpretable proxy for field use. Detection remains limited when crops are too young, canopies are not visible, clouds reduce clear observations, field boundaries have weak spectral contrast, or several adjacent parcels have the same vegetation signal.

## FTW position

FTW precomputed boundaries remain scientifically attractive as a free/public fallback if the app later reads only the required region. This pass deliberately does not depend on FTW so AEF first improves its own algorithm inside the selected perimeter.

## Validation

149 static and product-invariant checks passed. They cover:

- module creation and Sentinel-2/WorldCover/SNIC use;
- fallback behavior;
- confidence and precision display;
- i18n coverage;
- guide updates;
- requirements stability;
- Python structure checks for edited files.

Test result file: support/test_results/aef_sentinel_internal_parcel_detection_tests.json
