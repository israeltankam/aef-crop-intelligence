# src/models/sentinel_parcel_detector.py
"""Sentinel-2 guided cooperative parcel delineation.

This module is deliberately still an *AEF internal* detector: it does not call
Fields of The World.  It uses open Sentinel-2 and ESA WorldCover layers already
available through Earth Engine, then polygonizes image segments inside the user
perimeter.  The result is not cadastral truth; it is a better, image-guided set
of editable parcel candidates with an explicit confidence estimate.  When the
user knows the number of plots inside the perimeter, that count is used as a
strong prior for segmentation scale and candidate selection.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Dict, Iterable, List, Sequence, Tuple

import ee

LatLon = Tuple[float, float]
PointXY = Tuple[float, float]


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _meters_per_degree(lat: float) -> Tuple[float, float]:
    """Approximate local metres per degree for small agricultural perimeters."""
    return 111_320.0, 111_320.0 * max(0.2, math.cos(math.radians(lat)))


def _centroid(coords: Sequence[LatLon]) -> LatLon:
    pts = list(coords or [])
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _to_xy(coords: Sequence[LatLon], origin: LatLon) -> List[PointXY]:
    mlat, mlon = _meters_per_degree(origin[0])
    return [((lon - origin[1]) * mlon, (lat - origin[0]) * mlat) for lat, lon in coords]


def _polygon_area_m2(points: Sequence[PointXY]) -> float:
    if len(points) < 3:
        return 0.0
    pts = list(points)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    area = 0.0
    for i in range(len(pts) - 1):
        area += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return abs(area) / 2.0


def _polygon_perimeter_m(points: Sequence[PointXY]) -> float:
    if len(points) < 2:
        return 0.0
    pts = list(points)
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))


def _compactness(coords: Sequence[LatLon]) -> float:
    """Return 0-1 Polsby-Popper compactness, used only as a weak plausibility cue."""
    origin = _centroid(coords)
    xy = _to_xy(coords, origin)
    area = _polygon_area_m2(xy)
    perimeter = _polygon_perimeter_m(xy)
    if area <= 0 or perimeter <= 0:
        return 0.0
    return max(0.0, min(1.0, 4.0 * math.pi * area / (perimeter * perimeter)))


def _ee_polygon(coords: Sequence[LatLon]):
    ee_coords = [[lon, lat] for lat, lon in coords]
    if ee_coords[0] != ee_coords[-1]:
        ee_coords.append(ee_coords[0])
    return ee.Geometry.Polygon([ee_coords])


def _mask_sentinel2_clouds(image):
    """Mask SCL cloud, shadow and no-data classes before compositing.

    Sentinel-2 SCL masks are conservative here: unclear/cloudy pixels are removed
    because boundary detection is very sensitive to cloud edges that look like
    artificial field borders.
    """
    scl = image.select("SCL")
    clear = (
        scl.neq(0)   # no data
        .And(scl.neq(1))   # saturated/defective
        .And(scl.neq(3))   # cloud shadow
        .And(scl.neq(7))   # unclassified / low-probability cloud
        .And(scl.neq(8))   # medium cloud
        .And(scl.neq(9))   # high cloud
        .And(scl.neq(10))  # cirrus
        .And(scl.neq(11))  # snow/ice
    )
    return image.updateMask(clear).divide(10_000).copyProperties(image, ["system:time_start"])


def _extract_outer_rings(geometry: Dict) -> List[List[LatLon]]:
    """Convert GeoJSON Polygon/MultiPolygon coordinates to AEF lat/lon rings."""
    if not geometry:
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates") or []
    rings: List[List[LatLon]] = []
    if gtype == "Polygon" and coords:
        rings.append([(lat, lon) for lon, lat in coords[0]])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly and poly[0]:
                rings.append([(lat, lon) for lon, lat in poly[0]])
    cleaned = []
    for ring in rings:
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) >= 3:
            cleaned.append(ring)
    return cleaned


def _score_confidence(area_ha: float, typical_area_ha: float, ndvi_mean: float, ndvi_std: float,
                      cultivable_fraction: float, valid_fraction: float, compactness: float) -> float:
    """Estimate detection confidence from interpretable, field-scale cues.

    The score is intentionally cautious.  It is not a validated accuracy metric;
    it is a transparent proxy shown to the user so uncertain boundaries are not
    presented as ground truth.
    """
    typical = max(0.05, typical_area_ha)
    ratio = max(0.05, area_ha) / typical
    area_score = max(0.0, 1.0 - min(1.0, abs(math.log(ratio)) / math.log(5.0)))
    vegetation_score = max(0.0, min(1.0, (ndvi_mean - 0.12) / 0.38))
    homogeneity_score = max(0.0, min(1.0, 1.0 - ndvi_std / 0.22))
    cover_score = max(0.0, min(1.0, cultivable_fraction))
    valid_score = max(0.0, min(1.0, valid_fraction))
    compact_score = max(0.0, min(1.0, compactness / 0.55))
    score = (
        0.22 * area_score
        + 0.18 * vegetation_score
        + 0.22 * homogeneity_score
        + 0.18 * cover_score
        + 0.12 * valid_score
        + 0.08 * compact_score
    )
    return round(max(0.35, min(0.92, score)), 2)


def _precision_label(mean_confidence: float) -> str:
    if mean_confidence >= 0.74:
        return "high"
    if mean_confidence >= 0.60:
        return "moderate"
    return "low"


def _count_guided_area_ha(perimeter_area_ha: float, typical_area_ha: float, expected_parcel_count: int) -> float:
    """Choose a plot scale without assuming the perimeter is fully cultivated.

    A known plot count tells the detector how many objects to seek, but not that
    the whole cooperative perimeter is crop cover.  If the count multiplied by
    the typical plot size covers only a small fraction of the perimeter, wide
    gaps are expected and the typical size remains the dominant scale.
    """
    typical = max(0.05, typical_area_ha)
    if expected_parcel_count <= 0 or perimeter_area_ha <= 0:
        return typical
    expected_cultivated = expected_parcel_count * typical
    coverage_guess = expected_cultivated / max(perimeter_area_ha, 1e-6)
    if coverage_guess < 0.72:
        return typical
    count_area = max(0.03, perimeter_area_ha * 0.86 / expected_parcel_count)
    return max(0.03, 0.40 * count_area + 0.60 * typical)


def _metadata(method: str, status: str, message: str, **extra) -> Dict[str, object]:
    meta = {"method": method, "status": status, "message": message}
    meta.update(extra)
    return meta


def detect_sentinel2_parcels(
    perimeter: Iterable[LatLon],
    typical_area_ha: float = 1.5,
    max_parcels: int = 240,
    reference_date=None,
    expected_parcel_count: int = 0,
) -> Tuple[List[dict], Dict[str, object]]:
    """Detect editable parcel candidates from Sentinel-2 image segmentation.

    Workflow:
    1. Build a recent cloud-masked Sentinel-2 median composite inside the perimeter.
    2. Combine NDVI/NDMI with ESA WorldCover to focus on vegetated/cultivable pixels.
    3. Run Earth Engine SNIC segmentation, sized from typical plot area and,
       when supplied, the expected number of plots.
    4. Polygonize segments and score them with transparent confidence proxies.

    If any Earth Engine step fails or the area is too large for a responsive setup
    page, the caller should fall back to the deterministic geometric detector.
    """
    pts = list(perimeter or [])
    if len(pts) < 3:
        return [], _metadata("sentinel2_snic", "failed", "No valid cooperative perimeter was provided.")
    if pts[0] == pts[-1]:
        pts = pts[:-1]

    typical_area_ha = max(0.05, _safe_float(typical_area_ha, 1.5))
    max_parcels = max(1, int(max_parcels or 240))
    expected_parcel_count = max(0, int(expected_parcel_count or 0))
    if expected_parcel_count > 0:
        max_parcels = min(max_parcels, expected_parcel_count)
    origin = _centroid(pts)
    perimeter_area_ha = _polygon_area_m2(_to_xy(pts, origin)) / 10_000.0
    if perimeter_area_ha <= 0:
        return [], _metadata("sentinel2_snic", "failed", "The cooperative perimeter has no measurable area.")
    if perimeter_area_ha > 3000:
        return [], _metadata(
            "sentinel2_snic",
            "skipped",
            "The perimeter is too large for interactive Sentinel-2 segmentation; geometric fallback was used.",
            perimeter_area_ha=round(perimeter_area_ha, 2),
            expected_plot_count=expected_parcel_count,
        )

    effective_area_ha = _count_guided_area_ha(perimeter_area_ha, typical_area_ha, expected_parcel_count)
    ref = reference_date or date.today()
    if isinstance(ref, str):
        try:
            ref = datetime.fromisoformat(ref[:10]).date()
        except Exception:
            ref = date.today()
    end = min(date.today(), ref if isinstance(ref, date) else date.today())
    # One year gives the detector a chance to see a grown canopy even if the
    # current crop is young, while still keeping the result recent enough for use.
    start = end - timedelta(days=365)

    try:
        geom = _ee_polygon(pts)
        collection = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(start.isoformat(), end.isoformat())
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 55))
            .map(_mask_sentinel2_clouds)
        )
        image_count = int(collection.size().getInfo() or 0)
        if image_count < 2:
            return [], _metadata(
                "sentinel2_snic",
                "failed",
                "Not enough clear Sentinel-2 observations were available for image-guided parcel detection.",
                image_count=image_count,
                date_window=f"{start.isoformat()} to {end.isoformat()}",
            )

        # Median compositing favours persistent canopy/soil patterns and damps
        # remaining outliers. This is important for smallholder mosaics where one
        # cloudy edge can otherwise become a false parcel boundary.
        composite = collection.median().clip(geom)
        ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
        ndmi = composite.normalizedDifference(["B8", "B11"]).rename("ndmi")
        brightness = composite.select(["B2", "B3", "B4", "B8"]).reduce(ee.Reducer.mean()).rename("brightness")
        worldcover = ee.ImageCollection("ESA/WorldCover/v100").filterBounds(geom).mosaic().select("Map").clip(geom)
        cultivable = (
            worldcover.eq(10)  # tree cover, important for perennial plantations
            .Or(worldcover.eq(20))
            .Or(worldcover.eq(30))
            .Or(worldcover.eq(40))
            .rename("cultivable")
        )
        valid = ndvi.mask().rename("valid")
        candidate_mask = cultivable.eq(1).And(ndvi.gt(0.12).Or(worldcover.eq(40))).selfMask()
        # Estimate how much of the perimeter is actually vegetated/cultivable.
        # This is not cadastral truth, but it keeps downstream messages and
        # metapopulation coupling aware that large internal gaps may be real.
        cultivated_area_ha = 0.0
        try:
            area_stats = ee.Image.pixelArea().rename("area").updateMask(candidate_mask).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=geom,
                scale=10,
                maxPixels=1e8,
                tileScale=4,
            ).getInfo()
            cultivated_area_ha = max(0.0, float((area_stats or {}).get("area", 0.0) or 0.0) / 10_000.0)
        except Exception:
            cultivated_area_ha = 0.0
        feature_image = ee.Image.cat([ndvi, ndmi, brightness]).updateMask(candidate_mask).toFloat()

        # SNIC seed spacing is in pixels.  We tie it to the requested typical
        # parcel area so smallholder settings use finer segmentation than large
        # plantations without creating an unbounded number of objects.
        typical_side_m = math.sqrt(effective_area_ha * 10_000.0)
        seed_spacing_px = int(max(4, min(30, round((typical_side_m / 10.0) * 0.85))))
        seeds = ee.Algorithms.Image.Segmentation.seedGrid(seed_spacing_px)
        snic = ee.Algorithms.Image.Segmentation.SNIC(
            image=feature_image,
            size=seed_spacing_px,
            compactness=0.45,
            connectivity=8,
            neighborhoodSize=128,
            seeds=seeds,
        )
        clusters = snic.select("clusters").updateMask(candidate_mask).toInt()
        # Polygonization is intentionally done on the server side: downloading
        # rasters to Streamlit would be slower and brittle for non-expert users.
        # The returned geometries remain editable in the existing AEF map.
        vectors = clusters.reduceToVectors(
            geometry=geom,
            scale=10,
            geometryType="polygon",
            eightConnected=True,
            labelProperty="segment_id",
            reducer=ee.Reducer.countEvery(),
            maxPixels=1e8,
            tileScale=4,
        )
        # Area filters remove tiny SNIC fragments and very large merged blobs.
        # They are broad because cooperative plots are not all the same size.
        min_area = max(0.02, effective_area_ha * 0.10)
        max_area = max(effective_area_ha * 4.5, min(10.0, perimeter_area_ha * 0.40))
        vectors = vectors.map(lambda f: f.set({
            "area_ha": f.geometry().area(1).divide(10_000),
            "perimeter_m": f.geometry().perimeter(1),
        }))
        vectors = vectors.filter(ee.Filter.gte("area_ha", min_area)).filter(ee.Filter.lte("area_ha", max_area))
        stats_image = ee.Image.cat([ndvi, ndmi, cultivable, valid]).clip(geom)
        reducer = ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True)
        vectors = stats_image.reduceRegions(collection=vectors, reducer=reducer, scale=10, tileScale=4)
        candidate_fetch_limit = max_parcels * (6 if expected_parcel_count else 4)
        candidate_fetch_limit = max(40, min(4000, candidate_fetch_limit))
        info = vectors.sort("area_ha", False).limit(candidate_fetch_limit).getInfo()
    except Exception as exc:
        return [], _metadata(
            "sentinel2_snic",
            "failed",
            "Sentinel-2 image-guided parcel detection failed; geometric fallback was used.",
            error=str(exc),
        )

    # Client-side post-processing only handles vectors and metadata, never raw
    # imagery. That keeps the app responsive and makes the fallback decision easy
    # to explain to the user.
    parcels: List[dict] = []
    for feature in (info.get("features") or []):
        props = feature.get("properties") or {}
        for ring in _extract_outer_rings(feature.get("geometry") or {}):
            area_ha = _safe_float(props.get("area_ha"), 0.0)
            if area_ha <= 0:
                area_ha = _polygon_area_m2(_to_xy(ring, _centroid(ring))) / 10_000.0
            if area_ha < min_area or area_ha > max_area:
                continue
            ndvi_mean = _safe_float(props.get("ndvi_mean"), _safe_float(props.get("mean"), 0.0))
            ndvi_std = _safe_float(props.get("ndvi_stdDev"), 0.12)
            cultivable_mean = _safe_float(props.get("cultivable_mean"), 0.5)
            valid_mean = _safe_float(props.get("valid_mean"), 0.65)
            compact = _compactness(ring)
            conf = _score_confidence(area_ha, effective_area_ha, ndvi_mean, ndvi_std, cultivable_mean, valid_mean, compact)
            idx = len(parcels) + 1
            parcels.append({
                "id": f"P{idx:03d}",
                "name": f"Parcel {idx}",
                "active": True,
                "coords": ring,
                "area_ha": round(area_ha, 3),
                "confidence": conf,
                "source": "sentinel2_snic_internal_detector",
                "requires_validation": True,
                "notes": "Sentinel-2 guided segment; validate boundary on the satellite map before using recommendations.",
                "ndvi_mean": None if ndvi_mean == 0.0 else round(ndvi_mean, 3),
                "ndvi_std": round(ndvi_std, 3),
                "cultivable_fraction": round(cultivable_mean, 2),
            })
            if len(parcels) >= candidate_fetch_limit:
                break
        if len(parcels) >= candidate_fetch_limit:
            break

    if expected_parcel_count > 0:
        # SNIC can over-segment a field mosaic.  Keep the count-consistent best
        # candidates by combining confidence with area closeness to the count-
        # guided target size; the polygons remain non-overlapping SNIC objects.
        def _selection_key(parcel):
            ratio = max(0.03, parcel.get("area_ha", effective_area_ha)) / max(0.03, effective_area_ha)
            area_penalty = min(1.0, abs(math.log(max(0.05, ratio))) / math.log(4.0))
            score = float(parcel.get("confidence", 0.5)) - 0.18 * area_penalty
            return (-score, abs(float(parcel.get("area_ha", effective_area_ha)) - effective_area_ha), parcel.get("id", ""))
        parcels = sorted(parcels, key=_selection_key)[:max_parcels]
    else:
        parcels = parcels[:max_parcels]

    for idx, parcel in enumerate(parcels, start=1):
        parcel["id"] = f"P{idx:03d}"
        parcel["name"] = f"Parcel {idx}"

    if not parcels:
        return [], _metadata(
            "sentinel2_snic",
            "failed",
            "Sentinel-2 segmentation returned no usable parcel candidate; geometric fallback was used.",
            image_count=image_count,
            date_window=f"{start.isoformat()} to {end.isoformat()}",
            perimeter_area_ha=round(perimeter_area_ha, 2),
        )

    mean_conf = sum(p["confidence"] for p in parcels) / len(parcels)
    label = _precision_label(mean_conf)
    return parcels, _metadata(
        "sentinel2_snic",
        "ok",
        "Sentinel-2 image-guided parcel candidates were generated inside the cooperative perimeter.",
        image_count=image_count,
        date_window=f"{start.isoformat()} to {end.isoformat()}",
        perimeter_area_ha=round(perimeter_area_ha, 2),
        parcel_count=len(parcels),
        expected_plot_count=expected_parcel_count,
        detected_expected_delta=(len(parcels) - expected_parcel_count) if expected_parcel_count else None,
        count_guided_typical_area_ha=round(effective_area_ha, 3),
        cultivated_area_ha=round(cultivated_area_ha, 2),
        unassigned_area_ha=round(max(0.0, perimeter_area_ha - sum(float(p.get("area_ha", 0.0) or 0.0) for p in parcels)), 2),
        cultivated_fraction=round(min(1.0, max(0.0, sum(float(p.get("area_ha", 0.0) or 0.0) for p in parcels) / max(perimeter_area_ha, 1e-6))), 3),
        image_cultivable_fraction=round(min(1.0, max(0.0, cultivated_area_ha / max(perimeter_area_ha, 1e-6))), 3) if cultivated_area_ha else 0.0,
        large_internal_gaps_allowed=True,
        mean_confidence=round(mean_conf, 2),
        estimated_precision_label=label,
        seed_spacing_pixels=seed_spacing_px,
        requires_user_validation=True,
        ftw_fallback_recommended=mean_conf < 0.60,
    )
