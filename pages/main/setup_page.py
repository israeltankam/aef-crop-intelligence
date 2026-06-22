# pages/main/setup_page.py
import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from geopy.geocoders import Nominatim
from geopy.point import Point
import math
from src.models.state_manager import StateManager
from src.utils.i18n import tr
from src.models.fertilizer_service import FertilizerService
from src.models.disease_service import DiseaseService # NEW IMPORT
from src.models.cooperative_parcel_detector import detect_candidate_parcels
from src.models.sentinel_parcel_detector import detect_sentinel2_parcels
from src.utils.coordinate_format import format_latlon_dms, parse_coordinate_pair
from src.utils.parcel_quality import cooperative_parcel_quality
from src.utils.diagnostic_quality import build_diagnostic_quality
from src.utils.disease_evidence import build_disease_evidence
from src.models.economic_engine import normalize_economics_config, auto_update_market_reference, apply_price_source_choice, ECONOMIC_PRICE_SOURCE_OPTIONS
from datetime import date, timedelta
import json
import ee
from google.oauth2.service_account import Credentials
import geocoder

# --- CONSTANTS ---
_SOIL_TABLE = {
    'sand':            {'field_capacity': 0.10, 'wilting_point': 0.03},
    'loamy sand':      {'field_capacity': 0.13, 'wilting_point': 0.05},
    'sandy loam':      {'field_capacity': 0.18, 'wilting_point': 0.07},
    'loam':            {'field_capacity': 0.27, 'wilting_point': 0.11},
    'silt loam':       {'field_capacity': 0.36, 'wilting_point': 0.20},
    'silt':            {'field_capacity': 0.45, 'wilting_point': 0.30},
    'sandy clay loam': {'field_capacity': 0.20, 'wilting_point': 0.10},
    'clay loam':       {'field_capacity': 0.35, 'wilting_point': 0.18},
    'silty clay loam': {'field_capacity': 0.38, 'wilting_point': 0.23},
    'sandy clay':      {'field_capacity': 0.23, 'wilting_point': 0.13},
    'silty clay':      {'field_capacity': 0.41, 'wilting_point': 0.26},
    'clay':            {'field_capacity': 0.47, 'wilting_point': 0.27}
}

def initialize_ee():
    if st.session_state.get('ee_initialized', False): return True
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/earthengine']
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        ee.Initialize(credentials=creds)
        st.session_state['ee_initialized'] = True
        return True
    except Exception as e:
        st.error("🛑 " + tr("Earth Engine Authentication Failed"))
        return False

def is_point_in_polygon(point, polygon_coords):
    x, y = point[0], point[1] 
    n = len(polygon_coords)
    inside = False
    p1x, p1y = polygon_coords[0]
    for i in range(n + 1):
        p2x, p2y = polygon_coords[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def get_bounds(coords):
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]

def _meters_per_degree(lat):
    """Return local meter/degree factors for small field-scale geometry."""
    m_per_deg_lat = 111132.0
    m_per_deg_lon = max(1.0, 111132.0 * math.cos(math.radians(lat)))
    return m_per_deg_lat, m_per_deg_lon

def calculate_area_ha(coords):
    if not coords or len(coords) < 3: return 0.0
    pts = np.array(coords)
    lats, lons = pts[:, 0], pts[:, 1]
    mean_lat = np.mean(lats)
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(mean_lat)
    y = (lats - lats[0]) * m_per_deg_lat
    x = (lons - lons[0]) * m_per_deg_lon
    area_m2 = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    return round(area_m2 / 10000.0, 2)

def _polygon_centroid(coords):
    if not coords:
        return st.session_state.get('center_lat', 0.0), st.session_state.get('center_lon', 0.0)
    usable = coords[:-1] if coords[0] == coords[-1] else coords
    return float(np.mean([p[0] for p in usable])), float(np.mean([p[1] for p in usable]))

def _local_area_m2(points):
    arr = np.array(points, dtype=float)
    x, y = arr[:, 0], arr[:, 1]
    return abs(0.5 * (np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))

def _rotate_points(points, angle_deg):
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    return [[x * c - y * s, x * s + y * c] for x, y in points]

def _base_shape_points(shape_name, aspect=1.0):
    """Normalized local shapes; later scaled so every candidate has the requested area."""
    aspect = max(0.35, min(3.2, float(aspect)))
    half_w = math.sqrt(aspect) / 2.0
    half_h = 1.0 / (2.0 * math.sqrt(aspect))
    if shape_name == 'rectangle':
        return [[-half_w, -half_h], [half_w, -half_h], [half_w, half_h], [-half_w, half_h]]
    if shape_name == 'diamond':
        return [[0.0, -0.72], [0.72, 0.0], [0.0, 0.72], [-0.72, 0.0]]
    if shape_name == 'hexagon':
        return [[math.cos(i * math.pi / 3.0), math.sin(i * math.pi / 3.0)] for i in range(6)]
    if shape_name == 'octagon':
        return [[math.cos(i * math.pi / 4.0), math.sin(i * math.pi / 4.0)] for i in range(8)]
    # Concave candidates help avoid small unsuitable corners such as roads or water edges.
    if shape_name == 'notched':
        return [[-0.75, -0.55], [0.75, -0.55], [0.75, 0.10], [0.22, 0.10], [0.22, 0.62], [-0.75, 0.62]]
    if shape_name == 'trapezoid':
        return [[-0.70, -0.48], [0.78, -0.38], [0.48, 0.58], [-0.62, 0.50]]
    return [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]]

def _local_to_latlon(center_lat, center_lon, points):
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(center_lat)
    coords = [[center_lat + y / m_per_deg_lat, center_lon + x / m_per_deg_lon] for x, y in points]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords

def _candidate_polygon(center_lat, center_lon, area_ha, shape_name, aspect, angle_deg, offset_m=(0.0, 0.0)):
    base = _base_shape_points(shape_name, aspect)
    base_area = max(1e-9, _local_area_m2(base))
    scale = math.sqrt((area_ha * 10000.0) / base_area)
    scaled = [[x * scale + offset_m[0], y * scale + offset_m[1]] for x, y in base]
    rotated = _rotate_points(scaled, angle_deg)
    return _local_to_latlon(center_lat, center_lon, rotated)

def generate_square_polygon(lat, lon, area_ha):
    return _candidate_polygon(lat, lon, area_ha, 'rectangle', 1.0, 0.0)

def offset_polygon(coords, north_m=0.0, east_m=0.0):
    lat, _ = _polygon_centroid(coords)
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(lat)
    return [[p[0] + north_m / m_per_deg_lat, p[1] + east_m / m_per_deg_lon] for p in coords]

def rotate_polygon(coords, angle_deg):
    center_lat, center_lon = _polygon_centroid(coords)
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(center_lat)
    local = [[(p[1] - center_lon) * m_per_deg_lon, (p[0] - center_lat) * m_per_deg_lat] for p in coords]
    return _local_to_latlon(center_lat, center_lon, _rotate_points(local, angle_deg))

def scale_polygon(coords, factor):
    center_lat, center_lon = _polygon_centroid(coords)
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(center_lat)
    local = [[(p[1] - center_lon) * m_per_deg_lon * factor, (p[0] - center_lat) * m_per_deg_lat * factor] for p in coords]
    return _local_to_latlon(center_lat, center_lon, local)

def generate_field_candidates(center_lat, center_lon, area_ha):
    """Generate plausible field shapes instead of assuming that every field is a square."""
    side = math.sqrt(max(area_ha, 0.1) * 10000.0)
    specs = [
        ('rectangle', 1.0, 0), ('rectangle', 1.6, 0), ('rectangle', 1.6, 45),
        ('rectangle', 2.4, 20), ('rectangle', 2.4, 70), ('diamond', 1.0, 0),
        ('hexagon', 1.0, 0), ('octagon', 1.0, 22), ('trapezoid', 1.0, 0),
        ('trapezoid', 1.0, 90), ('notched', 1.0, 0), ('notched', 1.0, 90),
        ('notched', 1.0, 180), ('notched', 1.0, 270)
    ]
    # Search more than the exact centre.  The user-supplied point is a guide,
    # but a centroid can fall on a track, house, yard, stream edge, or road.
    # These offsets keep the candidate close while giving the algorithm room to
    # avoid non-cultivable pixels visible in WorldCover/Sentinel products.
    offsets = [
        (0.0, 0.0),
        (side * 0.25, 0.0), (-side * 0.25, 0.0), (0.0, side * 0.25), (0.0, -side * 0.25),
        (side * 0.50, 0.0), (-side * 0.50, 0.0), (0.0, side * 0.50), (0.0, -side * 0.50),
        (side * 0.35, side * 0.35), (side * 0.35, -side * 0.35), (-side * 0.35, side * 0.35), (-side * 0.35, -side * 0.35),
        (side * 0.75, 0.0), (-side * 0.75, 0.0), (0.0, side * 0.75), (0.0, -side * 0.75),
    ]
    candidates = []
    for shape_name, aspect, angle in specs:
        for east_m, north_m in offsets:
            if (east_m or north_m) and shape_name not in {'rectangle', 'hexagon', 'notched'}:
                continue
            poly = _candidate_polygon(center_lat, center_lon, area_ha, shape_name, aspect, angle, (east_m, north_m))
            candidates.append({
                'poly': poly,
                'shape': shape_name,
                'aspect': aspect,
                'angle_deg': angle,
                'offset_m': {'east': round(east_m, 1), 'north': round(north_m, 1)},
                'area_ha': calculate_area_ha(poly)
            })
    return candidates

_WORLD_COVER_LABELS = {
    '10': 'tree cover', '20': 'shrubland', '30': 'grassland', '40': 'cropland',
    '50': 'built-up', '60': 'bare or sparse vegetation', '70': 'snow or ice',
    '80': 'permanent water', '90': 'herbaceous wetland', '95': 'mangroves', '100': 'moss or lichen'
}
_CULTIVABLE_COVER = {'10', '20', '30', '40'}
# For pre-planting and smart-field boundary search, bare/sparse land can still
# be agriculturally plausible.  Built-up, permanent water, wetlands, mangroves,
# snow/ice and moss/lichen are treated as hard non-cultivable warnings.
_FIELD_PLAUSIBLE_COVER = {'10', '20', '30', '40', '60'}
_NON_CULTIVABLE_COVER = {'50', '70', '80', '90', '95', '100'}
_HARD_NON_FIELD_COVER = {'50', '70', '80', '90', '95', '100'}
_SOIL_DEPTH_BANDS = [('b0', 0.00, 0.10), ('b10', 0.10, 0.30), ('b30', 0.30, 0.60), ('b60', 0.60, 1.00), ('b100', 1.00, 1.50)]
_USDA_TEXTURE_MAP = {1:'clay',2:'silty clay',3:'sandy clay',4:'clay loam',5:'silty clay loam',6:'sandy clay loam',7:'loam',8:'silt loam',9:'sandy loam',10:'silt',11:'loamy sand',12:'sand'}

def _normalize_hist(hist):
    if not hist:
        return {}
    normalized = {}
    for key, value in hist.items():
        try:
            normalized[str(int(float(key)))] = float(value)
        except Exception:
            normalized[str(key)] = float(value)
    return normalized

def _hist_pct(hist, classes):
    total = sum(hist.values())
    if total <= 0:
        return 0.0
    return 100.0 * sum(hist.get(str(code), 0.0) for code in classes) / total

def _dominant_cover(hist):
    if not hist:
        return 'unknown', 0.0
    total = sum(hist.values())
    code, count = max(hist.items(), key=lambda kv: kv[1])
    return _WORLD_COVER_LABELS.get(str(code), str(code)), 100.0 * count / total if total else 0.0

def _ee_polygon(coords):
    ee_coords = [[p[1], p[0]] for p in coords]
    if ee_coords[0] != ee_coords[-1]:
        ee_coords.append(ee_coords[0])
    return ee.Geometry.Polygon([ee_coords])

def get_land_cover_stats(polygon_coords_latlon):
    if not initialize_ee(): return None
    try:
        geom = _ee_polygon(polygon_coords_latlon)
        img = ee.ImageCollection("ESA/WorldCover/v100").filterBounds(geom).mosaic().select("Map").clip(geom)
        stats = img.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=geom, scale=10, maxPixels=1e9, bestEffort=True)
        return _normalize_hist(stats.get('Map').getInfo())
    except Exception:
        return None

def get_ndvi_homogeneity(polygon_coords_latlon):
    """Use recent Sentinel-2 NDVI variability as a light same-cover proxy."""
    if not initialize_ee(): return None
    try:
        geom = _ee_polygon(polygon_coords_latlon)
        end = date.today()
        start = end - timedelta(days=365)
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
            .filterBounds(geom)
            .filterDate(start.isoformat(), end.isoformat())
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 45)))
        if collection.size().getInfo() == 0:
            return None
        ndvi = collection.median().normalizedDifference(['B8', 'B4']).rename('NDVI').clip(geom)
        stats = ndvi.reduceRegion(
            reducer=ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True),
            geometry=geom, scale=10, maxPixels=1e9, bestEffort=True
        ).getInfo()
        return {'ndvi_mean': stats.get('NDVI_mean'), 'ndvi_std': stats.get('NDVI_stdDev')}
    except Exception:
        return None

def analyze_risk_level(hist):
    hist = _normalize_hist(hist)
    if not hist: return "UNKNOWN", "gray", tr("No satellite land-cover data available.")
    total_pixels = sum(hist.values())
    if total_pixels == 0: return "UNKNOWN", "gray", tr("Empty region.")
    built_pct = _hist_pct(hist, {'50'})
    water_pct = _hist_pct(hist, {'80', '90', '95'})
    non_cultivable_pct = _hist_pct(hist, _NON_CULTIVABLE_COVER)
    cultivable_pct = _hist_pct(hist, _CULTIVABLE_COVER)
    plausible_field_pct = _hist_pct(hist, _FIELD_PLAUSIBLE_COVER)
    dominant_label, dominant_pct = _dominant_cover(hist)
    dominant_label_display = tr(dominant_label)
    if built_pct > 2.0 or water_pct > 2.0 or non_cultivable_pct > 8.0:
        return "CRITICAL", "red", tr("Unsuitable pixels detected ({pct:.1f}% not cultivable; dominant cover: {cover}).", pct=non_cultivable_pct, cover=dominant_label_display)
    if built_pct > 0.2 or water_pct > 0.2 or plausible_field_pct < 70.0 or dominant_pct < 55.0:
        return "WARNING", "orange", tr("Mixed cover detected ({cultivable:.1f}% plausible field cover; dominant cover: {cover}, {dominant:.0f}%).", cultivable=plausible_field_pct, cover=dominant_label_display, dominant=dominant_pct)
    return "SAFE", "green", tr("Mostly consistent vegetated/cultivable cover ({cover}, {dominant:.0f}%).", cover=dominant_label_display, dominant=dominant_pct)

def score_field_candidate(candidate, requested_area_ha, center_lat, center_lon, include_ndvi=False):
    poly = candidate['poly']
    hist_raw = candidate.get('hist') if candidate.get('hist') is not None else get_land_cover_stats(poly)
    level, color, msg = analyze_risk_level(hist_raw)
    ndvi = get_ndvi_homogeneity(poly) if include_ndvi else None
    hist = _normalize_hist(hist_raw)
    area_error_pct = abs(calculate_area_ha(poly) - requested_area_ha) / max(0.01, requested_area_ha) * 100.0
    centroid_lat, centroid_lon = _polygon_centroid(poly)
    m_per_deg_lat, m_per_deg_lon = _meters_per_degree(center_lat)
    distance_m = math.hypot((centroid_lat - center_lat) * m_per_deg_lat, (centroid_lon - center_lon) * m_per_deg_lon)
    built_pct = _hist_pct(hist, {'50'})
    water_pct = _hist_pct(hist, {'80', '90', '95'})
    hard_non_field_pct = _hist_pct(hist, _HARD_NON_FIELD_COVER)
    non_cultivable_pct = _hist_pct(hist, _NON_CULTIVABLE_COVER)
    cultivable_pct = _hist_pct(hist, _CULTIVABLE_COVER)
    plausible_field_pct = _hist_pct(hist, _FIELD_PLAUSIBLE_COVER)
    dominant_label, dominant_pct = _dominant_cover(hist)
    ndvi_std = ndvi.get('ndvi_std') if ndvi else None
    ndvi_mean = ndvi.get('ndvi_mean') if ndvi else None
    ndvi_penalty = 14.0 if ndvi_std is None else min(42.0, max(0.0, ndvi_std) * 180.0)
    hard_reject = bool(hist) and (built_pct > 2.0 or water_pct > 2.0 or hard_non_field_pct > 8.0)
    unknown_reject = not bool(hist)
    # Built-up and water pixels are much more serious than ordinary mixed
    # vegetation.  This prevents a neat geometric polygon from being selected
    # over a slightly shifted but genuinely field-like candidate.
    infrastructure_penalty = built_pct * 35.0 + water_pct * 40.0 + hard_non_field_pct * 18.0
    plausible_cover_penalty = max(0.0, 70.0 - plausible_field_pct) * 2.2
    reject_penalty = 12000.0 if hard_reject else (2500.0 if unknown_reject else 0.0)
    score = (non_cultivable_pct * 8.0) + infrastructure_penalty + plausible_cover_penalty + ((100.0 - dominant_pct) * 0.35) + (area_error_pct * 1.2) + (distance_m / max(20.0, math.sqrt(requested_area_ha * 10000.0)) * 7.0) + ndvi_penalty + reject_penalty
    auto_boundary_accepted = bool(hist) and not hard_reject and plausible_field_pct >= 55.0
    candidate.update({
        'hist': hist, 'level': level, 'color': color, 'msg': msg, 'score': score,
        'built_up_pct': built_pct, 'water_or_wetland_pct': water_pct,
        'hard_non_field_pct': hard_non_field_pct,
        'non_cultivable_pct': non_cultivable_pct, 'cultivable_pct': cultivable_pct,
        'plausible_field_pct': plausible_field_pct,
        'dominant_cover': dominant_label, 'dominant_cover_pct': dominant_pct,
        'ndvi_mean': ndvi_mean, 'ndvi_std': ndvi_std,
        'center_shift_m': round(distance_m, 1),
        'hard_reject': hard_reject, 'unknown_reject': unknown_reject,
        'auto_boundary_accepted': auto_boundary_accepted,
    })
    return candidate

def optimize_field_location(center_lat, center_lon, area_ha):
    candidates = []
    for candidate in generate_field_candidates(center_lat, center_lon, area_ha):
        candidates.append(score_field_candidate(candidate, area_ha, center_lat, center_lon, include_ndvi=False))
    candidates.sort(key=lambda x: (not x.get('auto_boundary_accepted', False), x.get('hard_reject', False), x.get('unknown_reject', False), x['level'] == 'CRITICAL', x['score']))
    # Sentinel-2 homogeneity is useful, but expensive.  Refine the best accepted
    # candidates first, then a few rejected ones for diagnostics.  This improves
    # precision without making every geometric candidate call Sentinel-2.
    accepted = [c for c in candidates if c.get('auto_boundary_accepted', False)]
    rejected = [c for c in candidates if not c.get('auto_boundary_accepted', False)]
    shortlist_source = (accepted[:14] + rejected[:4]) if accepted else candidates[:18]
    refined_ids = {id(c) for c in shortlist_source}
    shortlist = [score_field_candidate(c, area_ha, center_lat, center_lon, include_ndvi=True) for c in shortlist_source]
    candidates = shortlist + [c for c in candidates if id(c) not in refined_ids]
    candidates.sort(key=lambda x: (not x.get('auto_boundary_accepted', False), x.get('hard_reject', False), x.get('unknown_reject', False), x['level'] == 'CRITICAL', x['score']))
    best = candidates[0]
    accepted_count = sum(1 for c in candidates if c.get('auto_boundary_accepted', False))
    metadata = {
        'source': 'smart_field_auto',
        'shape': best['shape'],
        'area_ha': best['area_ha'],
        'requested_area_ha': area_ha,
        'score': round(best['score'], 2),
        'level': best['level'],
        'dominant_cover': best['dominant_cover'],
        'dominant_cover_pct': round(best['dominant_cover_pct'], 1),
        'cultivable_pct': round(best['cultivable_pct'], 1),
        'plausible_field_pct': round(best.get('plausible_field_pct', 0.0), 1),
        'non_cultivable_pct': round(best['non_cultivable_pct'], 1),
        'built_up_pct': round(best.get('built_up_pct', 0.0), 1),
        'water_or_wetland_pct': round(best.get('water_or_wetland_pct', 0.0), 1),
        'hard_non_field_pct': round(best.get('hard_non_field_pct', 0.0), 1),
        'ndvi_mean': None if best['ndvi_mean'] is None else round(float(best['ndvi_mean']), 3),
        'ndvi_std': None if best['ndvi_std'] is None else round(float(best['ndvi_std']), 3),
        'center_shift_m': best['center_shift_m'],
        'candidate_count': len(candidates),
        'accepted_candidate_count': accepted_count,
        'auto_boundary_accepted': bool(best.get('auto_boundary_accepted', False)),
        'hard_reject': bool(best.get('hard_reject', False)),
        'unknown_reject': bool(best.get('unknown_reject', False)),
        'manual_validation_required': not bool(best.get('auto_boundary_accepted', False)),
        'note': 'WorldCover/Sentinel filters built-up, water and wetland pixels; bare land can be plausible before planting, but every automatic boundary still requires visual validation.'
    }
    return best['poly'], best['level'], best['color'], best['msg'], metadata

def geocode_place_candidates(query):
    if not query or len(query.strip()) < 3:
        return []
    geolocator = Nominatim(user_agent="aef_crop_intelligence_field_search", timeout=10)
    results = geolocator.geocode(query, exactly_one=False, limit=5, addressdetails=True)
    if not results:
        return []
    return [{'label': loc.address, 'lat': float(loc.latitude), 'lon': float(loc.longitude)} for loc in results]

def _reduce_band(asset, band, geom, reducer, scale=250):
    image = ee.Image(asset).select(band).clip(geom)
    stats = image.reduceRegion(reducer=reducer, geometry=geom, scale=scale, maxPixels=1e9, bestEffort=True)
    value = stats.get(band).getInfo()
    return None if value is None else float(value)

def _safe_soil_band(asset, band, geom, reducer):
    try:
        return _reduce_band(asset, band, geom, reducer)
    except Exception:
        return None

def _weighted_average(values):
    total_weight = sum(w for value, w in values if value is not None)
    if total_weight <= 0:
        return None
    return sum(value * w for value, w in values if value is not None) / total_weight

def get_auto_soil_profile(coords):
    if not initialize_ee():
        return False, {}, tr("Earth Engine API is offline or not authenticated.")
    try:
        geom = _ee_polygon(coords)
        texture_asset = "OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02"
        carbon_asset = "OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02"
        clay_asset = "OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02"
        texture_bands = set(ee.Image(texture_asset).bandNames().getInfo())
        layers, oc_values, clay_values = [], [], []
        for band, top_m, bottom_m in _SOIL_DEPTH_BANDS:
            if band not in texture_bands:
                continue
            texture_id = _safe_soil_band(texture_asset, band, geom, ee.Reducer.mode())
            if texture_id is None:
                continue
            texture = _USDA_TEXTURE_MAP.get(int(round(texture_id)), 'loam')
            props = _SOIL_TABLE.get(texture, _SOIL_TABLE['loam'])
            clay_pct = _safe_soil_band(clay_asset, band, geom, ee.Reducer.mean())
            oc_raw = _safe_soil_band(carbon_asset, band, geom, ee.Reducer.mean())
            organic_carbon_g_kg = oc_raw * 5.0 if oc_raw is not None else None
            thickness = bottom_m - top_m
            if organic_carbon_g_kg is not None:
                oc_values.append((organic_carbon_g_kg, thickness))
            if clay_pct is not None:
                clay_values.append((clay_pct, thickness))
            layers.append({
                'depth_top': round(top_m, 2), 'depth_bottom': round(bottom_m, 2),
                'texture': texture, 'field_capacity': props['field_capacity'],
                'wilting_point': props['wilting_point'], 'clay_pct': None if clay_pct is None else round(clay_pct, 1),
                'organic_carbon_g_kg': None if organic_carbon_g_kg is None else round(organic_carbon_g_kg, 1),
                'source_band': band
            })
        if not layers:
            return False, {}, tr("Region outside of soil dataset coverage or no valid OpenLandMap pixels.")
        surface = layers[0]
        organic_carbon_g_kg = _weighted_average(oc_values) or 5.0
        clay_content = _weighted_average(clay_values) or 20.0
        total_n_mg_kg = (organic_carbon_g_kg * 1000.0) / 11.0
        texture = surface['texture']
        if 'sand' in texture:
            availability_factor = 0.014
        elif 'clay' in texture:
            availability_factor = 0.024
        else:
            availability_factor = 0.019
        available_n = max(8.0, min(80.0, total_n_mg_kg * availability_factor))
        profile_depth = max(layer['depth_bottom'] for layer in layers)
        confidence = 0.62 if len(layers) >= 3 else 0.52
        return True, {
            'texture': texture, 'carbon': organic_carbon_g_kg, 'clay': clay_content,
            'n_total': total_n_mg_kg, 'n_available': available_n, 'soil_layers': layers,
            'profile_depth_m': profile_depth, 'confidence': confidence,
            'source': tr('OpenLandMap 250 m gridded prediction'),
            'warning': tr('Automatic soil data are useful for non-expert setup, but should be replaced by field or laboratory measurements when available.')
        }, tr("Success")
    except Exception as e:
        return False, {}, f"{tr('Earth Engine Error:')} {str(e)}"

def get_default_location():
    try:
        g = geocoder.ip('me')
        if g.latlng: return g.latlng[0], g.latlng[1]
    except: pass
    return 4.0, 11.5


def _coop_point_in_polygon(lat, lon, coords):
    """Ray-casting test used to keep auto-detected parcels inside the perimeter."""
    pts = list(coords or [])
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        if (xi > lon) != (xj > lon):
            y_at_lon = (yj - yi) * (lon - xi) / ((xj - xi) + 1e-12) + yi
            if lat < y_at_lon:
                inside = not inside
        j = i
    return inside


def _coop_polygon_centroid(coords):
    pts = list(coords or [])
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return st.session_state.get('center_lat', 0.0), st.session_state.get('center_lon', 0.0)
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _coop_rectangle_from_center(lat, lon, area_ha, aspect=1.35):
    """Create a small field-like rectangle around a centre point."""
    area_m2 = max(0.05, float(area_ha)) * 10000.0
    width = math.sqrt(area_m2 * aspect)
    height = area_m2 / max(width, 1.0)
    dlat = (height / 2.0) / 111320.0
    dlon = (width / 2.0) / (111320.0 * max(0.2, math.cos(math.radians(lat))))
    return [(lat-dlat, lon-dlon), (lat-dlat, lon+dlon), (lat+dlat, lon+dlon), (lat+dlat, lon-dlon), (lat-dlat, lon-dlon)]


def _coop_detect_parcels(perimeter, target_area_ha=1.5, max_parcels=240):
    """Detect editable parcel candidates inside a cooperative perimeter.

    AEF first tries its own image-guided detector: recent Sentinel-2 composites
    are segmented inside the perimeter and converted to editable polygons.  If
    Earth Engine is unavailable, cloudy, or too uncertain, the older geometric
    candidate generator remains as a transparent fallback.  In both cases the
    user sees a confidence estimate and must validate the map.
    """
    detection_meta = {}
    parcels = []
    if initialize_ee():
        parcels, detection_meta = detect_sentinel2_parcels(
            perimeter,
            typical_area_ha=max(0.05, float(target_area_ha or 1.5)),
            max_parcels=max_parcels,
            reference_date=date.today(),
        )

    if not parcels:
        fallback_reason = detection_meta.get('message') or 'Sentinel-2 image-guided detection was unavailable; geometric fallback was used.'
        parcels = detect_candidate_parcels(
            perimeter,
            typical_area_ha=max(0.05, float(target_area_ha or 1.5)),
            max_parcels=max_parcels,
            variability=0.72,
            precision_passes=4,
        )
        detection_meta = {
            'method': 'geometric_fallback',
            'status': 'fallback',
            'message': fallback_reason,
            'estimated_precision_label': 'low',
            'mean_confidence': round(sum(p.get('confidence', 0.45) for p in parcels) / len(parcels), 2) if parcels else 0.0,
            'parcel_count': len(parcels),
            'ftw_fallback_recommended': True,
            'requires_user_validation': True,
        }

    for parcel in parcels:
        idx = int(str(parcel.get('id', 'P0')).replace('P', '') or 0)
        parcel['name'] = f"{tr('Parcel')} {idx}"
        parcel['planting_date'] = str(st.session_state.get('planting_date', date.today()))
        parcel['planting_density'] = float(st.session_state.get('planting_density', 10000))
        parcel['selected_crop_id'] = st.session_state.get('selected_crop_id')
        parcel['initial_nitrogen'] = float(st.session_state.get('initial_nitrogen', 10.0))
        parcel['initial_phosphorus'] = float(st.session_state.get('initial_phosphorus', 20.0))
        parcel['initial_potassium'] = float(st.session_state.get('initial_potassium', 100.0))
        parcel['years_without_fertilizer'] = float(st.session_state.get('history_years', 0))

    if parcels:
        mean_confidence = round(sum(p.get('confidence', 0.5) for p in parcels) / len(parcels), 2)
        detection_meta['mean_confidence'] = mean_confidence
        detection_meta['parcel_count'] = len(parcels)
        st.session_state['cooperative_detection_confidence'] = mean_confidence
        st.session_state['cooperative_detection_meta'] = detection_meta
        st.session_state['cooperative_detection_notes'] = detection_meta.get('message') or 'Automatic parcel candidates require validation on the satellite map.'
    return parcels


def _coop_normalize_parcels():
    """Fill missing parcel keys so editors and simulations remain stable."""
    parcels = st.session_state.get('cooperative_parcels', []) or []
    normalized = []
    for idx, parcel in enumerate(parcels, start=1):
        coords = parcel.get('coords', [])
        normalized.append({
            'id': parcel.get('id') or f'P{idx:03d}',
            'name': parcel.get('name') or f"{tr('Parcel')} {idx}",
            'active': bool(parcel.get('active', True)),
            'coords': coords,
            'area_ha': float(parcel.get('area_ha') or calculate_area_ha(coords) or 0.1),
            'planting_date': str(parcel.get('planting_date') or st.session_state.get('planting_date', date.today())),
            'planting_density': float(parcel.get('planting_density') if parcel.get('planting_density') not in (None, '') else st.session_state.get('planting_density', 10000)),
            'selected_crop_id': parcel.get('selected_crop_id') or st.session_state.get('selected_crop_id'),
            'initial_nitrogen': float(parcel.get('initial_nitrogen') if parcel.get('initial_nitrogen') not in (None, '') else st.session_state.get('initial_nitrogen', 10.0)),
            'initial_phosphorus': float(parcel.get('initial_phosphorus') if parcel.get('initial_phosphorus') not in (None, '') else st.session_state.get('initial_phosphorus', 20.0)),
            'initial_potassium': float(parcel.get('initial_potassium') if parcel.get('initial_potassium') not in (None, '') else st.session_state.get('initial_potassium', 100.0)),
            'years_without_fertilizer': float(parcel.get('years_without_fertilizer') if parcel.get('years_without_fertilizer') not in (None, '') else 0.0),
            'confidence': float(parcel.get('confidence', 1.0) if parcel.get('confidence') not in (None, '') else 1.0),
            'source': parcel.get('source', 'manual'),
            'requires_validation': bool(parcel.get('requires_validation', False)),
            'notes': parcel.get('notes', ''),
        })
    st.session_state['cooperative_parcels'] = normalized
    return normalized


def _coop_apply_shared_crop_to_parcels():
    for parcel in _coop_normalize_parcels():
        parcel['selected_crop_id'] = st.session_state.get('selected_crop_id')
        parcel['planting_date'] = str(st.session_state.get('planting_date', date.today()))
        parcel['planting_density'] = float(st.session_state.get('planting_density', 10000))


def _coop_apply_shared_nutrients_to_parcels():
    for parcel in _coop_normalize_parcels():
        years = float(parcel.get('years_without_fertilizer', 0.0) or 0.0)
        parcel['initial_nitrogen'] = round(float(st.session_state.get('initial_nitrogen', 10.0)) * ((1 - 0.05) ** years), 1)
        parcel['initial_phosphorus'] = round(float(st.session_state.get('initial_phosphorus', 20.0)) * ((1 - 0.02) ** years), 1)
        parcel['initial_potassium'] = round(float(st.session_state.get('initial_potassium', 100.0)) * ((1 - 0.03) ** years), 1)


def _coop_draw_map(map_key, draw_mode='perimeter', selected_parcel_id=None):
    """Render cooperative perimeter, parcels and disease markers on a satellite map.

    The same map is reused in geography, disease, soil and review steps so users
    never have to remember which P-code corresponds to which field.  Plot names
    are displayed as lightweight labels and stored in the configuration JSON.
    """
    perimeter = st.session_state.get('cooperative_perimeter_coords') or st.session_state.get('field_coords') or []
    selected_parcel = next((p for p in _coop_normalize_parcels() if p.get('id') == selected_parcel_id and p.get('coords')), None)
    # Focusing the selected plot avoids forcing users to mentally match P-codes
    # against many small fields, which is a major ergonomics issue in cooperative mode.
    center = _coop_polygon_centroid(selected_parcel.get('coords')) if selected_parcel else (_coop_polygon_centroid(perimeter) if perimeter else (st.session_state.get('center_lat', 4.0), st.session_state.get('center_lon', 11.5)))
    zoom_start = 17 if selected_parcel else 16
    m = folium.Map(location=list(center), zoom_start=zoom_start, max_zoom=20)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name=tr('Esri Satellite'), overlay=False, control=True).add_to(m)
    if perimeter:
        folium.Polygon(locations=perimeter, color='#0057B8', weight=4, fill=True, fill_opacity=0.08, popup=tr('Cooperative perimeter')).add_to(m)
    for parcel in _coop_normalize_parcels():
        if not parcel.get('active', True):
            continue
        color = '#00A65A' if parcel.get('id') != selected_parcel_id else '#FFB000'
        name = str(parcel.get('name') or parcel.get('id') or tr('Parcel'))
        folium.Polygon(locations=parcel.get('coords', []), color=color, weight=2, fill=True, fill_opacity=0.22, popup=name).add_to(m)
        if parcel.get('coords'):
            label_lat, label_lon = _coop_polygon_centroid(parcel.get('coords', []))
            safe_name = name.replace('<', '').replace('>', '')[:24]
            folium.Marker(
                location=[label_lat, label_lon],
                icon=folium.DivIcon(html=f"<div style='font-size:11px;font-weight:700;color:#0B3D2E;background:rgba(255,255,255,.82);border:1px solid #0B3D2E;border-radius:3px;padding:1px 4px;white-space:nowrap'>{safe_name}</div>")
            ).add_to(m)
    for spot in st.session_state.get('disease_spots', []) or []:
        folium.CircleMarker(location=[spot['lat'], spot['lon']], radius=5, color='crimson', fill=True, fill_opacity=0.85, popup=tr('Disease spot')).add_to(m)
    if draw_mode != 'view':
        Draw(
            export=False,
            position='topleft',
            draw_options={'polyline': False, 'rectangle': False, 'circle': False, 'marker': draw_mode == 'disease', 'circlemarker': False, 'polygon': draw_mode != 'disease'},
            edit_options={'edit': True}
        ).add_to(m)
    folium.LayerControl().add_to(m)
    return st_folium(m, height=520, width=None, key=map_key)


def _config_snapshot():
    """Build a lightweight configuration snapshot for explanatory panels.

    The setup page uses this read-only snapshot to render confidence and evidence
    messages before the simulation runs.  It intentionally mirrors saved JSON
    fields so these warnings survive reloads.
    """
    return {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys()}


def _selected_disease_name():
    dis_id = st.session_state.get('selected_disease_id')
    df = st.session_state.get('df_diseases')
    if dis_id and df is not None and dis_id in df['Disease_ID'].values:
        return df[df['Disease_ID'] == dis_id].iloc[0]['Disease_Name']
    return None


def _merge_disease_spots_preserving_manual(new_spots):
    """Merge satellite spots while preserving field observations.

    A healthy satellite scan should not erase a scout's manual focus.  The scan
    only reports canopy stress visibility at acquisition time; field evidence can
    still be valid and should remain in the configuration until the user clears it.
    """
    existing = st.session_state.get('disease_spots', []) or []
    manual_spots = [s for s in existing if str(s.get('source', 'manual')) == 'manual']
    satellite_spots = []
    for spot in new_spots or []:
        enriched = dict(spot)
        enriched.setdefault('source', 'satellite')
        satellite_spots.append(enriched)
    return manual_spots + satellite_spots


def _render_disease_evidence_panel():
    evidence = build_disease_evidence(_config_snapshot(), _selected_disease_name())
    st.markdown('##### ' + tr('Disease evidence status'))
    st.info(tr(evidence['interpretation']))
    for item in evidence.get('evidence', []):
        status_text = tr(item['status'])
        if item.get('count'):
            status_text = f"{item['count']} {status_text}"
        st.caption(f"**{tr(item['source'])}** - {status_text}. {tr('Confidence:')} {tr(item['confidence'])}. {tr(item['decision_impact'])}")


def _render_diagnostic_quality_panel():
    quality = build_diagnostic_quality(_config_snapshot())
    st.markdown('##### ' + tr('Diagnostic quality'))
    q1, q2 = st.columns([1, 2])
    q1.metric(tr('Diagnostic quality score'), f"{quality['overall_score']:.1f}%", tr(quality['label']))
    q2.info(f"{tr('Next best measurement')}: {tr(quality['next_best_measurement'])}")
    with st.expander(tr('Why this confidence level?')):
        component_rows = [{
            tr('Component'): tr(c['name']),
            tr('Score'): f"{c['score']:.1f}%",
            tr('Status'): tr(c['status']),
            tr('Decision impact'): tr(c['impact']),
            tr('Next step'): tr(c['next_step']),
        } for c in quality.get('components', [])]
        st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)


def _month_label(month_number):
    months = ['Unknown', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
    return tr(months[int(month_number)]) if 0 <= int(month_number) <= 12 else tr('Unknown')


def _render_perennial_context(prefix=''):
    """Collect perennial context without changing the crop engine itself.

    Age, pruning and dormancy information mainly improves interpretation,
    uncertainty scoring and future disease-pressure corrections.  Keeping it
    modular avoids hard-coding perennial assumptions into annual workflows.
    """
    st.markdown('##### ' + tr('Perennial context'))
    known_pruning = st.checkbox(tr('I know pruning or severe canopy-management dates'), value=bool(st.session_state.get('perennial_last_pruning_date') or st.session_state.get('perennial_next_pruning_date')), key=f'{prefix}perennial_known_pruning')
    if known_pruning:
        p1, p2 = st.columns(2)
        with p1:
            last_value = st.session_state.get('perennial_last_pruning_date') or date.today()
            st.session_state['perennial_last_pruning_date'] = st.date_input(tr('Last pruning date'), value=last_value, key=f'{prefix}perennial_last_pruning_date')
        with p2:
            next_value = st.session_state.get('perennial_next_pruning_date') or date.today()
            st.session_state['perennial_next_pruning_date'] = st.date_input(tr('Next planned pruning date'), value=next_value, key=f'{prefix}perennial_next_pruning_date')
    else:
        st.session_state['perennial_last_pruning_date'] = None
        st.session_state['perennial_next_pruning_date'] = None
    m1, m2, y1 = st.columns(3)
    month_options = list(range(13))
    with m1:
        start_month = int(st.session_state.get('perennial_dormancy_start_month', 0) or 0)
        st.session_state['perennial_dormancy_start_month'] = st.selectbox(tr('Low-pressure season start'), month_options, index=month_options.index(start_month) if start_month in month_options else 0, format_func=_month_label, key=f'{prefix}perennial_dormancy_start_month')
    with m2:
        end_month = int(st.session_state.get('perennial_dormancy_end_month', 0) or 0)
        st.session_state['perennial_dormancy_end_month'] = st.selectbox(tr('Low-pressure season end'), month_options, index=month_options.index(end_month) if end_month in month_options else 0, format_func=_month_label, key=f'{prefix}perennial_dormancy_end_month')
    with y1:
        st.session_state['perennial_historical_yield_t_ha'] = st.number_input(tr('Recent typical yield (t/ha)'), min_value=0.0, max_value=200.0, value=float(st.session_state.get('perennial_historical_yield_t_ha', 0.0) or 0.0), step=0.1, key=f'{prefix}perennial_historical_yield_t_ha')
    st.caption(tr('These values help interpret perennial uncertainty, pruning cost and seasonal disease pressure.'))


def _render_cooperative_shared_report_constraints():
    st.markdown('##### ' + tr('Shared cooperative resources for report feasibility'))
    st.caption(tr('Use 0 when a shared limit is unknown; the report will flag feasibility instead of pretending certainty.'))
    r1, r2, r3 = st.columns(3)
    with r1:
        st.session_state['cooperative_report_water_limit_m3'] = st.number_input(tr('Shared water available for optimized plan (m3)'), min_value=0.0, max_value=100000000.0, value=float(st.session_state.get('cooperative_report_water_limit_m3', 0.0) or 0.0), step=100.0)
    with r2:
        st.session_state['cooperative_report_fertilizer_limit_kg'] = st.number_input(tr('Shared fertilizer available for optimized plan (kg)'), min_value=0.0, max_value=100000000.0, value=float(st.session_state.get('cooperative_report_fertilizer_limit_kg', 0.0) or 0.0), step=100.0)
    with r3:
        st.session_state['cooperative_report_labour_days'] = st.number_input(tr('Shared labour available for interventions (person-days)'), min_value=0.0, max_value=1000000.0, value=float(st.session_state.get('cooperative_report_labour_days', 0.0) or 0.0), step=1.0)


def _coop_last_polygon(output):
    drawing = (output or {}).get('last_active_drawing')
    if not drawing or drawing.get('geometry', {}).get('type') != 'Polygon':
        return None
    raw = drawing['geometry']['coordinates'][0]
    return [(lat, lon) for lon, lat in raw]


def _coop_last_marker(output):
    """Return the last manually placed disease marker from the cooperative map."""
    drawing = (output or {}).get('last_active_drawing')
    if drawing and drawing.get('geometry', {}).get('type') == 'Point':
        lon, lat = drawing['geometry']['coordinates'][:2]
        return {'lat': lat, 'lon': lon}
    clicked = (output or {}).get('last_clicked')
    if clicked:
        return {'lat': clicked['lat'], 'lon': clicked['lng']}
    return None


def _coop_find_parcel_for_point(lat, lon):
    """Identify the active parcel containing a manual disease observation."""
    for parcel in _coop_normalize_parcels():
        if parcel.get('active', True) and _coop_point_in_polygon(lat, lon, parcel.get('coords', [])):
            return parcel
    return None



def _render_operational_constraints(prefix=''):
    """Collect practical farm constraints used to interpret optimization results.

    These inputs do not remove the existing scientific engines.  They add a
    feasibility layer so irrigation and fertilizer recommendations can be read as
    operational plans rather than abstract biophysical optima.
    """
    st.markdown('##### ' + tr('Operational feasibility constraints'))
    c_water, c_fert = st.columns(2)
    with c_water:
        st.session_state['water_source_type'] = st.selectbox(
            tr('Water source'),
            ['unknown', 'rainfed only', 'well/borehole', 'river/canal', 'reservoir', 'public irrigation scheme'],
            index=['unknown', 'rainfed only', 'well/borehole', 'river/canal', 'reservoir', 'public irrigation scheme'].index(st.session_state.get('water_source_type', 'unknown')) if st.session_state.get('water_source_type', 'unknown') in ['unknown', 'rainfed only', 'well/borehole', 'river/canal', 'reservoir', 'public irrigation scheme'] else 0,
            format_func=tr,
            key=f'{prefix}water_source_type'
        )
        st.session_state['available_water_m3_day'] = st.number_input(
            tr('Available irrigation water (m3/day)'),
            min_value=0.0,
            max_value=100000.0,
            value=float(st.session_state.get('available_water_m3_day', 0.0) or 0.0),
            step=10.0,
            key=f'{prefix}available_water_m3_day',
            help=tr('Use 0 when the limit is unknown; the report will then flag feasibility as unverified.')
        )
        st.session_state['irrigation_efficiency'] = st.slider(
            tr('Application efficiency'),
            min_value=0.10,
            max_value=1.00,
            value=float(st.session_state.get('irrigation_efficiency', 0.70) or 0.70),
            step=0.05,
            key=f'{prefix}irrigation_efficiency'
        )
    with c_fert:
        st.session_state['irrigation_method'] = st.selectbox(
            tr('Irrigation method'),
            ['unspecified', 'manual watering', 'furrow', 'sprinkler', 'drip', 'center pivot'],
            index=['unspecified', 'manual watering', 'furrow', 'sprinkler', 'drip', 'center pivot'].index(st.session_state.get('irrigation_method', 'unspecified')) if st.session_state.get('irrigation_method', 'unspecified') in ['unspecified', 'manual watering', 'furrow', 'sprinkler', 'drip', 'center pivot'] else 0,
            format_func=tr,
            key=f'{prefix}irrigation_method'
        )
        st.session_state['fertilizer_budget_per_ha'] = st.number_input(
            tr('Fertilizer budget ceiling per ha'),
            min_value=0.0,
            max_value=10000000.0,
            value=float(st.session_state.get('fertilizer_budget_per_ha', 0.0) or 0.0),
            step=1000.0,
            key=f'{prefix}fertilizer_budget_per_ha',
            help=tr('Use 0 when budget is unknown; recommendations will be marked as agronomic, not economic.')
        )
        st.session_state['fertilizer_availability_note'] = st.text_input(
            tr('Locally available fertilizers or constraints'),
            value=st.session_state.get('fertilizer_availability_note', ''),
            key=f'{prefix}fertilizer_availability_note'
        )
    st.caption(tr('These constraints help convert model optima into feasible field actions.'))


def _current_crop_params_for_economics():
    """Return the currently selected crop row as a dictionary for price defaults.

    The economic screen uses this only to pre-fill editable market assumptions.
    It never changes crop parameters or model outputs.
    """
    crop_id = st.session_state.get('selected_crop_id')
    df = st.session_state.get('df_crops')
    if crop_id and df is not None and crop_id in df['Crop_ID'].values:
        return df[df['Crop_ID'] == crop_id].iloc[0].to_dict()
    return {}


def _render_economics_setup(prefix='economics'):
    """Render the economic assumptions editor used by reports and recommendations.

    The layout deliberately starts with the minimum fields a farmer or manager can
    answer, then places detailed labour/product costs in secondary tabs.  All
    values are persisted in a single JSON-compatible economics_config object.
    """
    crop_params = _current_crop_params_for_economics()
    context = _config_snapshot()
    economics = normalize_economics_config(st.session_state.get('economics_config', {}), context, crop_params)
    st.subheader('💰 ' + tr('Economic assumptions'))
    st.caption(tr('These values convert agronomic recommendations into revenue, cost, margin and ROI estimates.'))
    c_auto, c_quality = st.columns([1, 2])
    with c_auto:
        if st.button(tr('Refresh automatic market reference'), key=f'{prefix}_refresh_market', use_container_width=True):
            with st.spinner(tr('Refreshing local market reference from crop and field location...')):
                economics = auto_update_market_reference(economics, context, crop_params)
                st.session_state['economics_config'] = economics
                st.session_state[f'{prefix}_price_source'] = economics.get('price_source', 'automatic regional prior')
                st.success(tr('Market reference refreshed. Verify with local prices before investment.'))
                st.rerun()
    with c_quality:
        st.info(f"{tr('Current price source')}: {tr(str(economics.get('price_source', 'manual')))} | {tr('Confidence:')} {float(economics.get('price_confidence', 0.0))*100:.0f}%")

    if str(crop_params.get('Type', 'Annual')) == 'Perennial':
        economics['economic_horizon_years'] = st.number_input(tr('Economic analysis horizon (years)'), min_value=1, max_value=20, value=int(float(economics.get('economic_horizon_years', 20) or 20)), step=1, key=f'{prefix}_economic_horizon_years')
        st.session_state['economic_horizon_years'] = int(economics['economic_horizon_years'])
        st.caption(tr('For perennial crops, revenue is summed over annual harvest peaks within this horizon.'))
    else:
        economics['economic_horizon_years'] = 1
        st.session_state['economic_horizon_years'] = 1

    tab_market, tab_inputs, tab_labor, tab_json = st.tabs([tr('Market price'), tr('Input costs'), tr('Labor and disease costs'), tr('Economics JSON')])
    with tab_market:
        price_source_options = list(ECONOMIC_PRICE_SOURCE_OPTIONS)
        current_source = str(economics.get('price_source', 'manual') or 'manual')
        if current_source not in price_source_options:
            current_source = 'manual'
        selected_source = st.selectbox(
            tr('Price source'),
            price_source_options,
            index=price_source_options.index(current_source),
            format_func=tr,
            key=f'{prefix}_price_source'
        )
        if selected_source != str(economics.get('price_source', 'manual') or 'manual'):
            # Price source is an economic assumption, not only a label.  Automatic
            # sources refresh the planning prior; quote/statistical sources update
            # confidence and source notes while preserving the user-entered price.
            economics = apply_price_source_choice(economics, selected_source, context, crop_params)
            st.info(tr('Price source applied. Review the price, confidence and note below before saving or running recommendations.'))
        else:
            economics['price_source'] = selected_source
        source_key = ''.join(ch if ch.isalnum() else '_' for ch in selected_source)
        st.caption(tr('Changing the price source updates the default price reference, confidence level and explanatory note used by recommendations.'))

        m1, m2, m3 = st.columns(3)
        with m1:
            economics['currency'] = st.selectbox(tr('Currency'), ['XAF', 'USD', 'EUR'], index=['XAF', 'USD', 'EUR'].index(economics.get('currency', 'XAF')) if economics.get('currency', 'XAF') in ['XAF', 'USD', 'EUR'] else 0, key=f'{prefix}_currency')
            economics['country'] = st.text_input(tr('Country'), value=str(economics.get('country', 'Cameroon')), key=f'{prefix}_country')
        with m2:
            economics['market_region'] = st.text_input(tr('Market region'), value=str(economics.get('market_region', 'Central Africa')), key=f'{prefix}_market_region')
            economics['market_level'] = st.selectbox(tr('Market level'), ['farmgate', 'cooperative', 'wholesale', 'export'], index=['farmgate', 'cooperative', 'wholesale', 'export'].index(economics.get('market_level', 'farmgate')) if economics.get('market_level', 'farmgate') in ['farmgate', 'cooperative', 'wholesale', 'export'] else 0, format_func=tr, key=f'{prefix}_market_level')
        with m3:
            economics['sale_price_per_t'] = st.number_input(tr('Sale price of crop per tonne'), min_value=0.0, max_value=100000000.0, value=float(economics.get('sale_price_per_t', 0.0) or 0.0), step=1000.0, key=f'{prefix}_sale_price_{source_key}')
            economics['price_confidence'] = st.slider(tr('Price confidence'), 0.0, 1.0, float(economics.get('price_confidence', 0.55) or 0.55), 0.05, key=f'{prefix}_price_confidence_{source_key}')
        economics['price_source_detail'] = st.text_area(tr('Price source note'), value=tr(str(economics.get('price_source_detail', ''))), key=f'{prefix}_price_source_detail_{source_key}')
        loss_col, risk_col, transport_col = st.columns(3)
        with loss_col:
            economics['postharvest_loss_pct'] = st.number_input(tr('Post-harvest loss or quality discount (%)'), min_value=0.0, max_value=80.0, value=float(economics.get('postharvest_loss_pct', 5.0) or 0.0), step=0.5, key=f'{prefix}_postharvest_loss')
        with risk_col:
            economics['risk_discount_pct'] = st.number_input(tr('Economic risk discount (%)'), min_value=0.0, max_value=80.0, value=float(economics.get('risk_discount_pct', 10.0) or 0.0), step=0.5, key=f'{prefix}_risk_discount')
        with transport_col:
            economics['transport_cost_per_t'] = st.number_input(tr('Transport/marketing cost per tonne'), min_value=0.0, max_value=10000000.0, value=float(economics.get('transport_cost_per_t', 0.0) or 0.0), step=100.0, key=f'{prefix}_transport_cost')

    with tab_inputs:
        economics['default_fertilizer_price_per_kg'] = st.number_input(tr('Default fertilizer price per kg'), min_value=0.0, max_value=1000000.0, value=float(economics.get('default_fertilizer_price_per_kg', 520.0) or 0.0), step=10.0, key=f'{prefix}_default_fert_price')
        prices = economics.get('fertilizer_prices', {}) or {}
        price_df = pd.DataFrame([{'product': k, 'price_per_kg': v} for k, v in prices.items()])
        edited_prices = st.data_editor(price_df, num_rows='dynamic', use_container_width=True, hide_index=True, column_config={
            'product': st.column_config.TextColumn(tr('Fertilizer product')),
            'price_per_kg': st.column_config.NumberColumn(tr('Price per kg'), min_value=0.0, step=10.0),
        }, key=f'{prefix}_fertilizer_prices')
        economics['fertilizer_prices'] = {str(row['product']): float(row['price_per_kg']) for row in edited_prices.dropna(subset=['product']).to_dict('records') if str(row.get('product', '')).strip()}
        i1, i2, i3 = st.columns(3)
        with i1:
            economics['irrigation_cost_per_m3'] = st.number_input(tr('Irrigation water cost per m3'), min_value=0.0, max_value=1000000.0, value=float(economics.get('irrigation_cost_per_m3', 35.0) or 0.0), step=5.0, key=f'{prefix}_water_cost')
        with i2:
            economics['energy_cost_per_kwh'] = st.number_input(tr('Energy cost per kWh'), min_value=0.0, max_value=1000000.0, value=float(economics.get('energy_cost_per_kwh', 120.0) or 0.0), step=5.0, key=f'{prefix}_energy_cost')
        with i3:
            economics['irrigation_labor_cost_per_event'] = st.number_input(tr('Irrigation labor cost per event'), min_value=0.0, max_value=10000000.0, value=float(economics.get('irrigation_labor_cost_per_event', 2500.0) or 0.0), step=100.0, key=f'{prefix}_irrigation_labor')

    with tab_labor:
        st.caption(tr('Labour values are costs per workday per hectare. Set roguing or pruning to zero when scouting should not imply plant removal.'))
        labor = economics.get('labor_costs', {}) or {}
        l1, l2, l3 = st.columns(3)
        with l1:
            labor['scouting_day'] = st.number_input(tr('Scouting labour per day per ha'), min_value=0.0, max_value=10000000.0, value=float(labor.get('scouting_day', 3000.0) or 0.0), step=100.0, key=f'{prefix}_scouting_day')
            labor['fertilizer_application_day'] = st.number_input(tr('Fertilizer application labour per day per ha'), min_value=0.0, max_value=10000000.0, value=float(labor.get('fertilizer_application_day', 4000.0) or 0.0), step=100.0, key=f'{prefix}_fert_labor_day')
        with l2:
            labor['spraying_day'] = st.number_input(tr('Spraying labour per day per ha'), min_value=0.0, max_value=10000000.0, value=float(labor.get('spraying_day', 5000.0) or 0.0), step=100.0, key=f'{prefix}_spraying_day')
            labor['roguing_day'] = st.number_input(tr('Roguing labour per day per ha'), min_value=0.0, max_value=10000000.0, value=float(labor.get('roguing_day', 3500.0) or 0.0), step=100.0, key=f'{prefix}_roguing_day')
        with l3:
            labor['pruning_day'] = st.number_input(tr('Pruning labour per day per ha'), min_value=0.0, max_value=10000000.0, value=float(labor.get('pruning_day', 4500.0) or 0.0), step=100.0, key=f'{prefix}_pruning_day')
        economics['labor_costs'] = labor
        disease_costs = economics.get('disease_control_costs', {}) or {}
        d1, d2, d3 = st.columns(3)
        with d1:
            disease_costs['fungicide_per_l'] = st.number_input(tr('Fungicide or biocontrol cost per litre'), min_value=0.0, max_value=10000000.0, value=float(disease_costs.get('fungicide_per_l', 8000.0) or 0.0), step=100.0, key=f'{prefix}_fungicide_cost')
        with d2:
            disease_costs['spray_service_per_ha'] = st.number_input(tr('Spray service cost per ha'), min_value=0.0, max_value=10000000.0, value=float(disease_costs.get('spray_service_per_ha', 6000.0) or 0.0), step=100.0, key=f'{prefix}_spray_service')
        with d3:
            disease_costs['plant_replacement_cost'] = st.number_input(tr('Plant replacement cost'), min_value=0.0, max_value=10000000.0, value=float(disease_costs.get('plant_replacement_cost', 300.0) or 0.0), step=10.0, key=f'{prefix}_replacement_cost')
        economics['disease_control_costs'] = disease_costs
        economics['notes'] = st.text_area(tr('Economic notes'), value=str(economics.get('notes', '')), key=f'{prefix}_notes')

    with tab_json:
        uploaded_economics = st.file_uploader(tr('Load economics JSON'), type=['json'], key=f'{prefix}_economics_upload')
        if uploaded_economics is not None:
            if StateManager.load_economics_from_json(uploaded_economics):
                st.success(tr('Economics configuration loaded.'))
                st.rerun()
        st.download_button('💾 ' + tr('Save economics JSON'), data=StateManager.save_economics_to_json(), file_name='economics_config.json', mime='application/json', use_container_width=True, key=f'{prefix}_economics_download')
        st.caption(tr('The field configuration JSON also includes the current economics configuration.'))

    st.session_state['economics_config'] = normalize_economics_config(economics, context, crop_params)


def render_cooperative_setup():
    """Configuration workflow for many small fields inside one cooperative perimeter."""
    st.title('🤝 ' + tr('Cooperative Digital Twin Configuration'))
    st.caption(tr('Configure one perimeter, then curate the individual farmer plots inside it.'))
    st.session_state['interface_level'] = st.radio(tr('Interface level'), ['guided', 'expert'], horizontal=True, format_func=lambda x: tr('Guided') if x == 'guided' else tr('Expert'), key='coop_interface_level')
    steps = {1: tr('1. Perimeter & plots'), 2: tr('2. Crop system'), 3: tr('3. Disease'), 4: tr('4. Soil & parcel nutrients'), 5: tr('5. Economy'), 6: tr('6. Review')}
    if 'coop_step' not in st.session_state:
        st.session_state['coop_step'] = 1
    cols = st.columns(6)
    can_continue = bool(st.session_state.get('cooperative_perimeter_coords')) and len(_coop_normalize_parcels()) > 0
    for i, (step_num, step_label) in enumerate(steps.items()):
        with cols[i]:
            label = f"🟦 {step_label}" if step_num == st.session_state['coop_step'] else step_label
            if st.button(label, key=f'coop_nav_{step_num}', disabled=(step_num > 1 and not can_continue)):
                st.session_state['coop_step'] = step_num
                st.rerun()
    st.progress(st.session_state['coop_step'] / 6)
    st.divider()

    if st.session_state['coop_step'] == 1:
        st.subheader('🌍 ' + tr('Cooperative perimeter and plot detection'))
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            st.session_state['cooperative_name'] = st.text_input(tr('Cooperative name'), st.session_state.get('cooperative_name', 'My Cooperative'))
            st.session_state['center_lat'] = st.number_input(tr('Latitude'), value=float(st.session_state.get('center_lat', 9.30)), format='%.6f')
        with c2:
            st.session_state['center_lon'] = st.number_input(tr('Longitude'), value=float(st.session_state.get('center_lon', 13.40)), format='%.6f')
            stored_area = max(0.05, min(50000.0, float(st.session_state.get('cooperative_perimeter_area_ha', 100.0) or 100.0)))
            perimeter_area = st.number_input(tr('Cooperative perimeter area (ha)'), min_value=0.05, max_value=50000.0, value=stored_area, step=0.1 if stored_area < 5 else 5.0)
            st.session_state['cooperative_perimeter_area_ha'] = perimeter_area
        with c3:
            stored_target = max(0.05, min(20.0, float(st.session_state.get('cooperative_target_parcel_area_ha', 1.5) or 1.5)))
            target_area = st.number_input(tr('Typical parcel size (ha)'), min_value=0.05, max_value=20.0, value=stored_target, step=0.05)
            st.session_state['cooperative_target_parcel_area_ha'] = target_area
            st.caption(tr('Typical size guides detection; detected parcels may have different areas.'))
        st.caption(f"{tr('Current center (DMS):')} {format_latlon_dms(st.session_state['center_lat'], st.session_state['center_lon'])}")
        coord_text = st.text_input(tr('Center coordinate (DMS or decimal)'), value='', placeholder='9° 27′ 46″ N 14° 8′ 45″ E', key='coop_center_coordinate_text')
        c_use_coord, c_generate_perimeter = st.columns(2)
        with c_use_coord:
            if st.button(tr('Use DMS / decimal coordinate'), key='coop_use_dms_coordinate', use_container_width=True):
                parsed = parse_coordinate_pair(coord_text)
                if parsed:
                    st.session_state['center_lat'], st.session_state['center_lon'] = parsed
                    st.success(tr('Center coordinate updated.'))
                    st.rerun()
                else:
                    st.error(tr('Could not parse coordinates. Use decimal degrees or DMS with N/S/E/W.'))
        with c_generate_perimeter:
            if st.button(tr('Generate cooperative perimeter'), use_container_width=True):
                st.session_state['cooperative_perimeter_coords'] = generate_square_polygon(st.session_state['center_lat'], st.session_state['center_lon'], perimeter_area)
                st.rerun()
        draw_action = st.radio(tr('Map drawing action'), ['perimeter', 'add_plot', 'replace_plot'], format_func=lambda x: tr({'perimeter':'Draw or replace perimeter','add_plot':'Add missing plot','replace_plot':'Replace selected plot'}[x]), horizontal=True)
        selected_id = None
        active_parcel_options = [p for p in _coop_normalize_parcels() if p.get('active', True)]
        active_ids = [p['id'] for p in active_parcel_options]
        if active_ids:
            label_by_id = {p['id']: f"{p.get('name', p['id'])} ({p['id']})" for p in active_parcel_options}
            focus_options = [None] + active_ids
            if st.session_state.get('coop_focus_plot_geography') not in focus_options:
                st.session_state['coop_focus_plot_geography'] = None
            selected_id = st.selectbox(tr('Focus plot on map'), focus_options, format_func=lambda x: tr('All plots') if x is None else label_by_id.get(x, x), key='coop_focus_plot_geography')
            st.session_state['focused_cooperative_plot_id'] = selected_id
        if draw_action == 'replace_plot' and active_ids:
            selected_id = st.selectbox(tr('Plot to replace'), active_ids, format_func=lambda x: label_by_id.get(x, x), key='coop_plot_to_replace')
            st.session_state['focused_cooperative_plot_id'] = selected_id
        out = _coop_draw_map('coop_geography_map', draw_mode='perimeter', selected_parcel_id=selected_id)
        drawn_poly = _coop_last_polygon(out)
        if drawn_poly:
            if draw_action == 'perimeter':
                st.session_state['cooperative_perimeter_coords'] = drawn_poly
                st.session_state['cooperative_perimeter_area_ha'] = calculate_area_ha(drawn_poly)
                st.success(tr('Perimeter updated.'))
                st.rerun()
            elif draw_action == 'add_plot':
                parcels = _coop_normalize_parcels()
                parcels.append({'id': f'P{len(parcels)+1:03d}', 'name': f"{tr('Parcel')} {len(parcels)+1}", 'active': True, 'coords': drawn_poly, 'area_ha': calculate_area_ha(drawn_poly), 'confidence': 1.0, 'source': 'manual', 'requires_validation': False})
                st.session_state['cooperative_parcels'] = parcels
                st.success(tr('Plot added.'))
                st.rerun()
            elif draw_action == 'replace_plot' and selected_id:
                for parcel in _coop_normalize_parcels():
                    if parcel['id'] == selected_id:
                        parcel['coords'] = drawn_poly
                        parcel['area_ha'] = calculate_area_ha(drawn_poly)
                st.success(tr('Plot boundary replaced.'))
                st.rerun()
        col_detect, col_clear = st.columns(2)
        with col_detect:
            if st.button(tr('Auto-detect plots inside perimeter'), disabled=not bool(st.session_state.get('cooperative_perimeter_coords')), type='primary', use_container_width=True):
                with st.spinner(tr('Analyzing Sentinel-2 imagery and tracing editable parcel boundaries...')):
                    st.session_state['cooperative_parcels'] = _coop_detect_parcels(st.session_state['cooperative_perimeter_coords'], target_area)
                    st.success(tr('Parcel candidates placed. Please validate boundaries on the satellite map.'))
                    st.rerun()
        with col_clear:
            if st.button(tr('Clear detected plots'), use_container_width=True):
                st.session_state['cooperative_parcels'] = []
                st.session_state.pop('cooperative_detection_meta', None)
                st.session_state.pop('cooperative_detection_notes', None)
                st.session_state.pop('cooperative_detection_confidence', None)
                st.rerun()
        parcels = _coop_normalize_parcels()
        if parcels:
            st.markdown('##### ' + tr('Detected and editable plots'))
            df = pd.DataFrame([{k: p.get(k) for k in ['id','name','active','area_ha','confidence','source']} for p in parcels])
            edited = st.data_editor(df, use_container_width=True, hide_index=True, column_config={
                'id': st.column_config.TextColumn(tr('Plot ID'), disabled=True),
                'name': st.column_config.TextColumn(tr('Plot name')),
                'active': st.column_config.CheckboxColumn(tr('Keep plot')),
                'area_ha': st.column_config.NumberColumn(tr('Area'), disabled=True),
                'confidence': st.column_config.NumberColumn(tr('Detection confidence'), disabled=True, format='%.2f'),
                'source': st.column_config.TextColumn(tr('Source'), disabled=True),
            }, key='coop_parcel_editor')
            by_id = {p['id']: p for p in parcels}
            for row in edited.to_dict('records'):
                if row['id'] in by_id:
                    by_id[row['id']]['name'] = row.get('name', by_id[row['id']]['name'])
                    by_id[row['id']]['active'] = bool(row.get('active', True))
            st.session_state['cooperative_parcels'] = list(by_id.values())
            quality = cooperative_parcel_quality(st.session_state['cooperative_parcels'], st.session_state.get('cooperative_perimeter_area_ha'))
            area_range = f"{quality['min_area_ha']:.2f}-{quality['max_area_ha']:.2f} ha" if quality['active_count'] else 'n/a'
            st.info(f"{tr('Active plots')}: {quality['active_count']} | {tr('Total active area')}: {quality['total_area_ha']:.2f} ha | {tr('Parcel area range')}: {area_range} | {tr('Mean detection confidence')}: {quality['mean_confidence']:.2f}")
            detection_meta = st.session_state.get('cooperative_detection_meta', {}) or {}
            if detection_meta:
                method_label = tr('Sentinel-2 image-guided segmentation') if detection_meta.get('method') == 'sentinel2_snic' else tr('Geometric fallback candidate generator')
                precision_label = tr(str(detection_meta.get('estimated_precision_label', 'unknown')))
                mean_conf = float(detection_meta.get('mean_confidence', quality['mean_confidence']) or 0.0)
                st.info(f"{tr('Detection method')}: {method_label} | {tr('Estimated boundary precision')}: {precision_label} | {tr('Mean confidence')}: {mean_conf:.2f}")
                if detection_meta.get('date_window'):
                    st.caption(f"{tr('Satellite image window')}: {detection_meta.get('date_window')} | {tr('Clear Sentinel-2 observations')}: {detection_meta.get('image_count', 'n/a')}")
                if detection_meta.get('ftw_fallback_recommended'):
                    st.warning(tr('Boundary precision is limited. Validate or edit these polygons; FTW precomputed boundaries should be used as a free fallback when the integration is enabled.'))
            for warning in quality.get('warnings', []):
                st.warning(tr(warning))
            if st.session_state.get('cooperative_detection_notes'):
                st.caption(tr(st.session_state['cooperative_detection_notes']))

    elif st.session_state['coop_step'] == 2:
        st.subheader('🌱 ' + tr('Cooperative crop system'))
        df_c = st.session_state['df_crops']
        crop_names = sorted(df_c['Crop_Name'].unique())
        current_crop = df_c[df_c['Crop_ID'] == st.session_state.get('selected_crop_id')]['Crop_Name'].iloc[0] if st.session_state.get('selected_crop_id') in df_c['Crop_ID'].values else crop_names[0]
        crop_name = st.selectbox(tr('Select Crop Species'), crop_names, index=crop_names.index(current_crop))
        varieties = df_c[df_c['Crop_Name'] == crop_name]
        variety_names = varieties['Variety'].tolist()
        variety = st.selectbox(tr('Select Variety'), variety_names)
        st.session_state['selected_crop_id'] = varieties[varieties['Variety'] == variety].iloc[0]['Crop_ID']
        st.session_state['cooperative_crop_mode'] = st.radio(tr('Crop configuration mode'), ['shared', 'per_plot'], format_func=lambda x: tr('Same crop settings for all plots') if x == 'shared' else tr('Edit planting settings by plot'), horizontal=True)
        c1, c2 = st.columns(2)
        with c1:
            st.session_state['planting_date'] = st.date_input(tr('Planting Date'), value=st.session_state.get('planting_date', date.today()))
        with c2:
            st.session_state['planting_density'] = st.number_input(tr('Planting Density (plants/ha)'), value=float(st.session_state.get('planting_density', 10000)), step=100.0)
        selected_crop_row = varieties[varieties['Variety'] == variety].iloc[0]
        if selected_crop_row.get('Type') == 'Perennial':
            st.session_state['initial_plant_age_years'] = st.number_input(tr('Current plantation age (years)'), min_value=0.0, max_value=80.0, value=float(st.session_state.get('initial_plant_age_years', 0.0) or 0.0), step=0.5)
            st.caption(tr('For perennial crops, the simulation starts from the current plantation age rather than assuming new planting.'))
            _render_perennial_context(prefix='coop_')
        if st.session_state['cooperative_crop_mode'] == 'shared':
            if st.button(tr('Apply crop settings to all plots'), type='primary'):
                _coop_apply_shared_crop_to_parcels()
                st.success(tr('Crop settings applied to all plots.'))
        else:
            parcels = _coop_normalize_parcels()
            df = pd.DataFrame([{k: p.get(k) for k in ['id','name','planting_date','planting_density']} for p in parcels])
            edited = st.data_editor(df, use_container_width=True, hide_index=True, column_config={
                'id': st.column_config.TextColumn(tr('Plot ID'), disabled=True),
                'name': st.column_config.TextColumn(tr('Plot name')),
                'planting_date': st.column_config.DateColumn(tr('Planting Date')),
                'planting_density': st.column_config.NumberColumn(tr('Planting Density (plants/ha)'), min_value=100.0, step=100.0),
            }, key='coop_crop_editor')
            by_id = {p['id']: p for p in parcels}
            for row in edited.to_dict('records'):
                by_id[row['id']]['planting_date'] = str(row['planting_date'])
                by_id[row['id']]['planting_density'] = float(row['planting_density'])
                by_id[row['id']]['selected_crop_id'] = st.session_state['selected_crop_id']
            st.session_state['cooperative_parcels'] = list(by_id.values())

    elif st.session_state['coop_step'] == 3:
        st.subheader('🦠 ' + tr('Cooperative disease surveillance'))
        df_d = st.session_state['df_diseases']
        crop_row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == st.session_state.get('selected_crop_id')].iloc[0]
        diseases = df_d[df_d['Target_Crop_Name'] == crop_row['Crop_Name']]
        if not diseases.empty:
            options = [None] + diseases['Disease_ID'].tolist()
            st.session_state['selected_disease_id'] = st.selectbox(tr('Identified Threat'), options, format_func=lambda x: tr('No anomaly detected') if x is None else diseases[diseases['Disease_ID']==x].iloc[0]['Disease_Name'])
        st.session_state['detection_date'] = st.date_input(tr('Detection Date'), value=st.session_state.get('detection_date', date.today()))

        tab_auto_disease, tab_manual_disease = st.tabs(['📡 ' + tr('Automatic canopy scan'), '✍️ ' + tr('Manual disease scouting')])
        with tab_auto_disease:
            st.caption(tr('Satellite analysis looks for canopy stress patterns. It does not prove pathogen identity without field validation.'))
            if st.button('📡 ' + tr('Auto-Detect via Satellite (LAI/NDMI Analysis)'), disabled=not bool(st.session_state.get('cooperative_perimeter_coords')), type='primary'):
                with st.spinner(tr('Analyzing spectral signatures (Sentinel-2) for canopy stress patterns...')):
                    service = DiseaseService()
                    success, msg, disease_profile, spots, detected_date = service.analyze_field_health(st.session_state['cooperative_perimeter_coords'], st.session_state['planting_date'], st.session_state['planting_density'])
                    if success and disease_profile:
                        st.session_state['disease_spots'] = _merge_disease_spots_preserving_manual(spots or [])
                        st.session_state['selected_disease_id'] = disease_profile.get('Disease_ID', st.session_state.get('selected_disease_id'))
                        st.session_state['satellite_anomaly_date'] = detected_date
                        st.session_state['detection_date'] = date.today()
                        st.success(tr('Potential disease detected'))
                    elif success:
                        st.session_state['disease_spots'] = _merge_disease_spots_preserving_manual([])
                        if st.session_state.get('disease_spots'):
                            st.warning(tr('Satellite scan found no new canopy anomaly; manual disease foci were preserved.'))
                        else:
                            st.success(tr('Healthy canopy detected'))
                    else:
                        st.error(f"{tr('Detection failed:')} {msg}")

        with tab_manual_disease:
            st.info(tr('Use the marker tool on the map to add observed disease foci. Each marker is attached to the plot that contains it.'))
            c_manual_a, c_manual_b = st.columns(2)
            with c_manual_a:
                manual_plants = st.number_input(tr('Affected plants at this focus'), min_value=1, max_value=100000, value=1, step=1, key='coop_manual_disease_plants')
            with c_manual_b:
                manual_severity = st.selectbox(tr('Observed severity'), ['low', 'medium', 'high'], format_func=lambda x: tr(x.title()), key='coop_manual_disease_severity')
            out = _coop_draw_map('coop_disease_manual_map', draw_mode='disease')
            marker = _coop_last_marker(out)
            if marker:
                lat, lon = float(marker['lat']), float(marker['lon'])
                parcel = _coop_find_parcel_for_point(lat, lon)
                if parcel is None:
                    st.warning(tr('The marker is outside active cooperative plots and was not recorded.'))
                else:
                    new_spot = {
                        'lat': lat,
                        'lon': lon,
                        'plants': int(manual_plants),
                        'severity': manual_severity,
                        'date': str(st.session_state.get('detection_date', date.today())),
                        'source': 'manual',
                        'plot_id': parcel.get('id'),
                        'plot_name': parcel.get('name'),
                    }
                    existing = st.session_state.get('disease_spots', []) or []
                    duplicate = any(abs(float(s.get('lat', 0)) - lat) < 1e-7 and abs(float(s.get('lon', 0)) - lon) < 1e-7 and s.get('source') == 'manual' for s in existing)
                    if not duplicate:
                        st.session_state['disease_spots'] = existing + [new_spot]
                        st.success(tr('Manual disease focus added to plot {plot}.', plot=parcel.get('name')))
                        st.rerun()
            if st.session_state.get('disease_spots'):
                st.markdown('##### ' + tr('Recorded disease foci'))
                editor_df = pd.DataFrame(st.session_state['disease_spots'])
                edited_spots = st.data_editor(editor_df, num_rows='dynamic', use_container_width=True, key='coop_disease_spots')
                st.session_state['disease_spots'] = edited_spots.to_dict('records')
                if st.button(tr('Clear disease foci'), key='coop_clear_disease_foci'):
                    st.session_state['disease_spots'] = []
                    st.rerun()
            else:
                st.caption(tr('No disease foci recorded yet.'))
            _render_disease_evidence_panel()

    elif st.session_state['coop_step'] == 4:
        st.subheader('🪨 ' + tr('Cooperative soil and parcel nutrients'))
        perimeter = st.session_state.get('cooperative_perimeter_coords')
        st.markdown('##### ' + tr('Parcel reference map'))
        st.caption(tr('Use this map to match each plot name with its location before editing soil nutrients.'))
        soil_focus_options = [None] + [p['id'] for p in _coop_normalize_parcels() if p.get('active', True)]
        if len(soil_focus_options) > 1:
            soil_labels = {p['id']: f"{p.get('name', p['id'])} ({p['id']})" for p in _coop_normalize_parcels()}
            if st.session_state.get('coop_focus_plot_soil') not in soil_focus_options:
                st.session_state['coop_focus_plot_soil'] = None
            st.session_state['focused_cooperative_plot_id'] = st.selectbox(tr('Focus plot on map'), soil_focus_options, format_func=lambda x: tr('All plots') if x is None else soil_labels.get(x, x), key='coop_focus_plot_soil')
        _coop_draw_map('coop_soil_reference_map', draw_mode='view', selected_parcel_id=st.session_state.get('focused_cooperative_plot_id'))
        if st.button(tr('Auto-detect soil'), disabled=not bool(perimeter), help=tr('Uses OpenLandMap 250 m gridded soil layers from 0 to 150 cm when available.')):
            with st.spinner(tr('Reading gridded soil texture, carbon and clay layers...')):
                success, data, error_msg = get_auto_soil_profile(perimeter)
                if success:
                    st.session_state['soil_type'] = data['texture']
                    st.session_state['soil_layers'] = pd.DataFrame(data.get('soil_layers', []))
                    st.session_state['soil_data_source'] = data.get('source', 'auto')
                    st.session_state['soil_confidence'] = data.get('confidence', 0.55)
                    st.session_state['soil_detection_notes'] = data.get('warning', '')
                    st.success(tr('Analysis successful'))
                else:
                    st.error(f"{tr('Detection failed:')} {error_msg}")
        expert_mode = st.toggle(tr('Expert Mode (Edit Soil Physics)'), value=st.session_state.get('use_expert_soil', False))
        st.session_state['use_expert_soil'] = expert_mode
        soils = list(_SOIL_TABLE.keys())
        curr_soil = st.session_state.get('soil_type', 'loam').lower()
        if curr_soil not in soils:
            curr_soil = 'loam'
        if not expert_mode:
            st.session_state['soil_type'] = st.selectbox(tr('Soil Texture Class'), soils, index=soils.index(curr_soil), format_func=lambda soil: tr(soil.title()))
            props = _SOIL_TABLE[st.session_state['soil_type']]
            st.session_state['soil_layers'] = pd.DataFrame([{'depth_top':0.0,'depth_bottom':1.5,'texture':st.session_state['soil_type'],'field_capacity':props['field_capacity'],'wilting_point':props['wilting_point']}])
        else:
            st.session_state['soil_layers'] = st.data_editor(st.session_state['soil_layers'], num_rows='dynamic', use_container_width=True, key='coop_editor_layers')
        st.markdown('##### ' + tr('Initial nutrients by plot'))
        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state['initial_nitrogen'] = st.number_input(tr('Nitrogen (N-NO3)'), value=float(st.session_state.get('initial_nitrogen', 10.0)), step=1.0)
        with c2:
            st.session_state['initial_phosphorus'] = st.number_input(tr('Phosphorus (P)'), value=float(st.session_state.get('initial_phosphorus', 20.0)), step=1.0)
        with c3:
            st.session_state['initial_potassium'] = st.number_input(tr('Potassium (K)'), value=float(st.session_state.get('initial_potassium', 100.0)), step=5.0)
        if st.button(tr('Apply nutrient baseline to all plots')):
            _coop_apply_shared_nutrients_to_parcels()
            st.success(tr('Nutrient baseline applied to all plots.'))
        parcels = _coop_normalize_parcels()
        df = pd.DataFrame([{k:p.get(k) for k in ['id','name','years_without_fertilizer','initial_nitrogen','initial_phosphorus','initial_potassium']} for p in parcels])
        edited = st.data_editor(df, use_container_width=True, hide_index=True, column_config={
            'id': st.column_config.TextColumn(tr('Plot ID'), disabled=True),
            'name': st.column_config.TextColumn(tr('Plot name')),
            'years_without_fertilizer': st.column_config.NumberColumn(tr('Land Use History (Years farmed without fertilizer)'), min_value=0, max_value=50, step=1),
            'initial_nitrogen': st.column_config.NumberColumn(tr('Nitrogen (N-NO3)'), min_value=0.0, step=1.0),
            'initial_phosphorus': st.column_config.NumberColumn(tr('Phosphorus (P)'), min_value=0.0, step=1.0),
            'initial_potassium': st.column_config.NumberColumn(tr('Potassium (K)'), min_value=0.0, step=5.0),
        }, key='coop_nutrient_editor')
        by_id = {p['id']:p for p in parcels}
        for row in edited.to_dict('records'):
            by_id[row['id']]['name'] = row.get('name', by_id[row['id']].get('name'))
            for k in ['years_without_fertilizer','initial_nitrogen','initial_phosphorus','initial_potassium']:
                by_id[row['id']][k] = float(row[k])
        st.session_state['cooperative_parcels'] = list(by_id.values())
        st.info(tr('In cooperative mode, manual irrigation and fertilization calendars are disabled.'))
        _render_operational_constraints(prefix='coop_')
        _render_cooperative_shared_report_constraints()
        st.session_state['irr_schedule'] = pd.DataFrame(columns=['date','amount'])
        st.session_state['fert_schedule'] = pd.DataFrame(columns=['date','product','amount'])

    elif st.session_state['coop_step'] == 5:
        _render_economics_setup(prefix='coop_economics')
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ " + tr("Back"), key='coop_economics_back'):
            st.session_state['coop_step'] = 4
            st.rerun()
        if c_next.button(tr("Next: Review") + " ➡️", key='coop_economics_next'):
            st.session_state['coop_step'] = 6
            st.rerun()

    elif st.session_state['coop_step'] == 6:
        st.subheader('🚀 ' + tr('Review cooperative configuration'))
        parcels = [p for p in _coop_normalize_parcels() if p.get('active', True)]
        total_area = sum(p.get('area_ha', 0.0) for p in parcels)
        st.metric(tr('Active plots'), len(parcels))
        st.metric(tr('Total active area'), f"{total_area:.2f} ha")
        crop_label = st.session_state.get('selected_crop_id')
        if crop_label and crop_label in st.session_state['df_crops']['Crop_ID'].values:
            crop_row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == crop_label].iloc[0]
            crop_label = f"{crop_row['Crop_Name']} - {crop_row['Variety']}"
        st.write(f"**{tr('Crop:')}** {crop_label}")
        st.write(f"**{tr('Disease Spots:')}** {len(st.session_state.get('disease_spots', []))}")
        _render_diagnostic_quality_panel()
        if parcels:
            st.markdown('##### ' + tr('Plot reference'))
            st.dataframe(pd.DataFrame([{tr('Plot ID'): p.get('id'), tr('Plot name'): p.get('name'), tr('Area'): round(float(p.get('area_ha', 0.0) or 0.0), 2)} for p in parcels]), use_container_width=True, hide_index=True)
        st.download_button('💾 ' + tr('Save Config'), data=StateManager.save_config_to_json(), file_name='cooperative_config.json', mime='application/json', use_container_width=True)
        if st.button('🚀 ' + tr('Initialize Cooperative Digital Twin'), type='primary', use_container_width=True, disabled=len(parcels)==0):
            st.session_state['field_coords'] = st.session_state.get('cooperative_perimeter_coords', [])
            st.session_state['area_ha'] = total_area
            st.session_state['setup_complete'] = True
            st.session_state.pop('sim_results', None)
            st.session_state.pop('sim_uncertainty', None)
            st.session_state['nav_target'] = 'Intelligence Dashboard'
            st.success(tr('Configuration saved. Launching dashboard...'))
            st.rerun()

def app():
    if 'step' not in st.session_state: StateManager.initialize()
    if st.session_state.get('app_mode') == 'cooperative':
        render_cooperative_setup()
        return
    st.title("🛠️ " + tr("Digital Twin Configuration"))
    st.session_state['interface_level'] = st.radio(tr('Interface level'), ['guided', 'expert'], horizontal=True, format_func=lambda x: tr('Guided') if x == 'guided' else tr('Expert'), key='single_interface_level')

    steps = {1: tr("1. Geography"), 2: tr("2. Crop"), 3: tr("3. Disease"), 4: tr("4. Management"), 5: tr("5. Economy"), 6: tr("6. Launch")}
    can_navigate = st.session_state.get('field_coords') is not None and len(st.session_state['field_coords']) > 0
    cols = st.columns(6)
    for i, (step_num, step_label) in enumerate(steps.items()):
        with cols[i]:
            if step_num == st.session_state['step']:
                st.button(f"🟦 {step_label}", key=f"nav_{step_num}")
            else:
                if st.button(f"{step_label}", key=f"nav_{step_num}", disabled=not can_navigate):
                    st.session_state['step'] = step_num
                    st.rerun()
    st.progress(st.session_state['step'] / 6)
    st.divider()

    # ==========================================================================
    # STEP 1: GEOGRAPHY
    # ==========================================================================
    if st.session_state['step'] == 1:
        st.subheader("🌍 " + tr("Step 1: Define Field Geography"))
        if 'center_lat' not in st.session_state or st.session_state['center_lat'] == 9.30: 
             lat, lon = get_default_location()
             if lat != 4.0 and lon != 11.5: 
                 st.session_state['center_lat'] = lat
                 st.session_state['center_lon'] = lon
        tab_auto, tab_manual, tab_upload = st.tabs(["✨ " + tr("Assisted Setup"), "✍️ " + tr("Manual Draw"), "📂 " + tr("Load Config")])
        with tab_auto:
            st.info(tr("Use GPS coordinates when available. If not, search a place name, adjust the proposed center, then generate the field."))
            locate_mode = st.radio(
                tr("How do you want to locate the field center?"),
                ["GPS coordinates (preferred)", "Place name search"],
                horizontal=True,
                format_func=tr,
            )
            c_input, c_area = st.columns([2, 1])
            with c_input:
                if locate_mode.startswith("GPS"):
                    coord_str = st.text_input(tr("Center coordinate"), value="", placeholder="9° 27′ 46″ N 14° 8′ 45″ E")
                    st.caption(f"{tr('Current center (DMS):')} {format_latlon_dms(st.session_state.get('center_lat', 0.0), st.session_state.get('center_lon', 0.0))}")
                    if st.button(tr("Use these coordinates")):
                        try:
                            parsed = parse_coordinate_pair(coord_str)
                            if parsed is None:
                                p = Point(coord_str)
                                parsed = (float(p.latitude), float(p.longitude))
                            st.session_state['center_lat'] = float(parsed[0])
                            st.session_state['center_lon'] = float(parsed[1])
                            st.session_state['place_search_results'] = []
                            st.rerun()
                        except Exception as e:
                            st.error(f"{tr('Could not parse coordinates:')} {e}")
                else:
                    place_query = st.text_input(tr("Place name"), value="", placeholder="e.g., Yaounde Mont Mbankolo")
                    if st.button(tr("Search place")):
                        with st.spinner(tr("Searching the place and preparing map suggestions...")):
                            st.session_state['place_search_results'] = geocode_place_candidates(place_query)
                        if not st.session_state['place_search_results']:
                            st.warning(tr("No matching place found. Try adding the country or nearest town."))
                    if st.session_state.get('place_search_results'):
                        labels = [f"{r['label']} ({r['lat']:.5f}, {r['lon']:.5f})" for r in st.session_state['place_search_results']]
                        selected_label = st.selectbox(tr("Choose the closest result"), labels)
                        selected_result = st.session_state['place_search_results'][labels.index(selected_label)]
                        if st.button(tr("Use selected place")):
                            st.session_state['center_lat'] = selected_result['lat']
                            st.session_state['center_lon'] = selected_result['lon']
                            st.rerun()
            with c_area:
                area_input = st.number_input(tr("Field area (hectares)"), min_value=0.1, max_value=1000.0, value=float(st.session_state.get('area_ha', 1.0) or 1.0), step=0.1)
            st.caption(tr("Adjust the proposed center before generating the field boundary."))
            c_lat, c_lon = st.columns(2)
            with c_lat:
                st.session_state['center_lat'] = st.number_input(tr("Latitude"), value=float(st.session_state.get('center_lat', 4.0)), format="%.6f")
            with c_lon:
                st.session_state['center_lon'] = st.number_input(tr("Longitude"), value=float(st.session_state.get('center_lon', 11.5)), format="%.6f")
            st.caption(f"{tr('Current center (DMS):')} {format_latlon_dms(st.session_state['center_lat'], st.session_state['center_lon'])}")
            if st.button(tr("Generate Smart Field"), type="primary"):
                lat = float(st.session_state['center_lat'])
                lon = float(st.session_state['center_lon'])
                with st.spinner(tr("Scanning nearby vegetation, roads, water and field-like shapes...")):
                    poly, level, color, msg, metadata = optimize_field_location(lat, lon, area_input)
                if level == "CRITICAL": st.error(f"{tr('Blocking issue:')} {msg}")
                elif level == "WARNING":
                    st.warning(f"{tr('Review needed:')} {msg}")
                    st.success(tr("Best nearby polygon generated. You can adjust it below."))
                else:
                    st.success(f"{tr('Good field match:')} {msg}")
                st.session_state['field_coords'] = poly
                st.session_state['area_ha'] = calculate_area_ha(poly)
                st.session_state['field_design_metadata'] = metadata
                st.session_state['last_validation'] = msg
                st.rerun()
        with tab_manual:
            st.info(tr("Use the Polygon tool (pentagon icon) to draw your field."))
            c1, c2 = st.columns([3, 1])
            with c1: search = st.text_input(tr("Search Location"), key="search_manual")
            with c2:
                st.write("")
                if st.button("🔍 " + tr("Locate"), key="btn_locate"):
                     try:
                        geolocator = Nominatim(user_agent="aef_app_v2")
                        if not search: lat, lon = st.session_state['center_lat'], st.session_state['center_lon']
                        else:
                            loc = geolocator.geocode(search)
                            if loc:
                                 st.session_state['center_lat'] = loc.latitude
                                 st.session_state['center_lon'] = loc.longitude
                                 st.rerun()
                     except: st.error(tr("Location not found."))
        with tab_upload:
            uploaded_file = st.file_uploader(tr("Drop your field_config.json here"), type="json")
            if uploaded_file is not None:
                if StateManager.load_config_from_json(uploaded_file):
                    st.success(tr("Configuration loaded!"))
                    if st.button("🚀 " + tr("Jump to Review")): st.session_state['step'] = 5; st.rerun()
        st.divider()
        if st.session_state['field_coords']:
            st.markdown("##### " + tr("Fine-tune field boundary"))
            if 'last_validation' in st.session_state:
                st.caption(f"{tr('Current status:')} {tr(st.session_state['last_validation'])}")
            c_nudge, c_shape, c_info = st.columns([1.4, 1.6, 1.2])
            with c_nudge:
                st.caption(tr("Move boundary"))
                col_l, col_u, col_d, col_r = st.columns(4)
                shift_m = st.number_input(tr("Move step (m)"), min_value=1.0, max_value=100.0, value=5.0, step=1.0)
                if col_l.button("⬅️"):
                    st.session_state['field_coords'] = offset_polygon(st.session_state['field_coords'], east_m=-shift_m); st.rerun()
                if col_u.button("⬆️"):
                    st.session_state['field_coords'] = offset_polygon(st.session_state['field_coords'], north_m=shift_m); st.rerun()
                if col_d.button("⬇️"):
                    st.session_state['field_coords'] = offset_polygon(st.session_state['field_coords'], north_m=-shift_m); st.rerun()
                if col_r.button("➡️"):
                    st.session_state['field_coords'] = offset_polygon(st.session_state['field_coords'], east_m=shift_m); st.rerun()
            with c_shape:
                st.caption(tr("Shape tools"))
                rot, scale_pct = st.columns(2)
                with rot:
                    angle = st.number_input(tr("Rotate"), min_value=-45.0, max_value=45.0, value=0.0, step=1.0)
                with scale_pct:
                    scale_value = st.number_input(tr("Resize (%)"), min_value=50.0, max_value=150.0, value=100.0, step=2.5)
                apply_rot, apply_scale = st.columns(2)
                if apply_rot.button(tr("Apply rotation")) and angle != 0:
                    st.session_state['field_coords'] = rotate_polygon(st.session_state['field_coords'], angle)
                    st.session_state['area_ha'] = calculate_area_ha(st.session_state['field_coords'])
                    st.rerun()
                if apply_scale.button(tr("Apply resize")) and scale_value != 100:
                    st.session_state['field_coords'] = scale_polygon(st.session_state['field_coords'], scale_value / 100.0)
                    st.session_state['area_ha'] = calculate_area_ha(st.session_state['field_coords'])
                    st.rerun()
            with c_info:
                area = calculate_area_ha(st.session_state['field_coords'])
                st.session_state['area_ha'] = area
                st.metric(tr("Area"), f"{area} ha")
                meta = st.session_state.get('field_design_metadata', {}) or {}
                if meta:
                    st.caption(f"{tr('Cover:')} {tr(meta.get('dominant_cover', 'unknown'))} | {tr('cultivable:')} {meta.get('cultivable_pct', 'n/a')}% | {tr('shift:')} {meta.get('center_shift_m', 'n/a')} m")
            if st.session_state.get('interface_level', 'guided') == 'expert':
                with st.expander(tr("Edit polygon points")):
                    current_vertices = st.session_state['field_coords'][:-1] if st.session_state['field_coords'][0] == st.session_state['field_coords'][-1] else st.session_state['field_coords']
                    vertex_df = pd.DataFrame(current_vertices, columns=['lat', 'lon'])
                    edited_vertices = st.data_editor(vertex_df, num_rows="dynamic", use_container_width=True, key="field_vertex_editor")
                    if st.button(tr("Apply edited points")):
                        coords = edited_vertices[['lat', 'lon']].dropna().values.tolist()
                        if len(coords) >= 3:
                            if coords[0] != coords[-1]: coords.append(coords[0])
                            st.session_state['field_coords'] = coords
                            st.session_state['area_ha'] = calculate_area_ha(coords)
                            st.session_state['field_design_metadata'] = {'source': 'manual_vertex_edit', 'area_ha': st.session_state['area_ha']}
                            st.rerun()
                        else:
                            st.warning(tr("Keep at least three points for a valid field polygon."))
            else:
                st.caption(tr('Switch to Expert mode to edit raw polygon vertices.'))
        m = folium.Map(location=[st.session_state['center_lat'], st.session_state['center_lon']], zoom_start=17, max_zoom=20)
        folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name=tr('Esri Satellite'), overlay=False, control=True).add_to(m)
        if st.session_state['field_coords']:
            folium.Polygon(locations=st.session_state['field_coords'], color="#00FF00", weight=3, fill=True, fill_opacity=0.2, popup=tr("Field Boundary")).add_to(m)
        Draw(export=False, position='topleft', draw_options={'polyline':False,'rectangle':False,'circle':False,'marker':False,'circlemarker':False,'polygon':True}, edit_options={'edit': True}).add_to(m)
        folium.LayerControl().add_to(m)
        output = st_folium(m, height=500, width=800, key="map_step_1")
        if output['all_drawings']:
            last_draw = output['all_drawings'][-1]
            if last_draw['geometry']['type'] == 'Polygon':
                raw = last_draw['geometry']['coordinates'][0]
                coords = [[p[1], p[0]] for p in raw] 
                current = st.session_state.get('field_coords', [])
                if not current or (coords != current):
                    hist = get_land_cover_stats(coords)
                    level, color, msg = analyze_risk_level(hist)
                    if level == "CRITICAL": st.error(f"🛑 {tr(msg)}")
                    elif level == "WARNING": st.warning(f"⚠️ {tr(msg)}")
                    else: st.success(f"✅ {tr(msg)}")
                    st.session_state['field_coords'] = coords
                    st.session_state['area_ha'] = calculate_area_ha(coords)
                    st.session_state['last_validation'] = msg
                    st.session_state['field_design_metadata'] = {'source': 'manual_draw', 'area_ha': st.session_state['area_ha'], 'validation': msg}
                    st.rerun()
        if st.session_state['field_coords']:
            st.divider()
            c_back, c_next = st.columns([1, 6])
            with c_next:
                if st.button(tr("Next Step") + " ➡️"): st.session_state['step'] = 2; st.rerun()
            with c_back:
                 if st.button("🗑️ " + tr("Clear")): st.session_state['field_coords'] = []; st.session_state['area_ha'] = 0.0; st.rerun()

    # ==========================================================================
    # STEP 2: CROP SELECTION
    # ==========================================================================
    elif st.session_state['step'] == 2:
        st.subheader("🌱 " + tr("Step 2: Crop System"))
        df_crops = st.session_state['df_crops']
        crops = df_crops['Crop_Name'].unique()
        c_sel, c_date = st.columns(2)
        with c_sel:
            curr_id = st.session_state.get('selected_crop_id')
            default_idx = 0
            if curr_id:
                curr_name = df_crops[df_crops['Crop_ID'] == curr_id].iloc[0]['Crop_Name']
                if curr_name in crops: default_idx = list(crops).index(curr_name)
            selected_crop_name = st.selectbox(tr("Select Crop Species"), crops, index=default_idx)
            varieties = df_crops[df_crops['Crop_Name'] == selected_crop_name]
            selected_var = st.selectbox(tr("Select Variety"), varieties['Variety'].unique())
            row = varieties[varieties['Variety'] == selected_var].iloc[0]
            new_crop_id = row['Crop_ID']
            if st.session_state.get('selected_crop_id') != new_crop_id:
                st.session_state['selected_crop_id'] = new_crop_id
                if 'Default_Density' in row: st.session_state['planting_density'] = int(row['Default_Density'])
                st.rerun()
        with c_date:
            st.session_state['planting_date'] = st.date_input(tr("Planting Date"), value=st.session_state['planting_date'])
            st.session_state['planting_density'] = st.number_input(tr("Planting Density (plants/ha)"), value=int(st.session_state.get('planting_density', 10000)), step=100)
            if row.get('Type') == 'Perennial':
                st.session_state['initial_plant_age_years'] = st.number_input(tr("Current plantation age (years)"), min_value=0.0, max_value=80.0, value=float(st.session_state.get('initial_plant_age_years', 0.0) or 0.0), step=0.5)
                st.caption(tr("For perennial crops, the simulation starts from the current plantation age rather than assuming new planting."))
                _render_perennial_context(prefix='single_')
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ " + tr("Back")): st.session_state['step'] = 1; st.rerun()
        if c_next.button(tr("Next") + " ➡️"): st.session_state['step'] = 3; st.rerun()

    # ==========================================================================
    # STEP 3: DISEASE
    # ==========================================================================
    elif st.session_state['step'] == 3:
        st.subheader("🦠 " + tr("Step 3: Disease Surveillance"))
        c_id = st.session_state['selected_crop_id']
        c_row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
        df_d = st.session_state['df_diseases']
        
        # --- SATELLITE AUTO-DETECT SECTION ---
        st.markdown("##### 🛰️ " + tr("Automated Surveillance"))
        if st.button("📡 " + tr("Auto-Detect via Satellite (LAI/NDMI Analysis)"), type="primary", use_container_width=True):
            with st.spinner(tr("Analyzing spectral signatures (Sentinel-2) for canopy stress patterns...")):
                ds = DiseaseService()
                planting = st.session_state['planting_date']
                density = st.session_state.get('planting_density', 1000)
                
                # Updated call signature to accept density and return date
                success, msg, disease_profile, spots, detected_date = ds.analyze_field_health(
                    st.session_state['field_coords'], 
                    planting,
                    density
                )
                
                if success:
                    if disease_profile:
                        # Case 1: Disease Found. Satellite spots are merged with,
                        # not substituted for, manual scouting evidence.
                        st.session_state['disease_spots'] = _merge_disease_spots_preserving_manual(spots or [])
                        
                        if disease_profile['Disease_ID'] not in df_d['Disease_ID'].values:
                            new_row = pd.DataFrame([disease_profile])
                            st.session_state['df_diseases'] = pd.concat([df_d, new_row], ignore_index=True)
                        
                        st.session_state['selected_disease_id'] = disease_profile['Disease_ID']
                        
                        # Satellite imagery identifies when the canopy anomaly was last observed,
                        # but the management simulation starts from today's diagnosis.
                        st.session_state['satellite_anomaly_date'] = detected_date
                        st.session_state['detection_date'] = date.today()
                        
                        st.success(f"⚠️ **{tr(msg)}**: {disease_profile['Disease_Name']}")
                        st.info(f"**{tr('Satellite anomaly observation:')}** {detected_date}")
                        st.info(f"**{tr('Management detection date set to today:')}** {st.session_state['detection_date']}")
                        st.caption(f"**{tr('Inferred Parameters:')}** Beta={disease_profile['Beta_Infection']}, Dispersal={disease_profile['Dispersal_Sigma_m']}m")
                        if disease_profile.get('Candidate_Diseases'):
                            cand_txt = "; ".join([f"{c['disease_name']} ({c['confidence']*100:.0f}%)" for c in disease_profile['Candidate_Diseases']])
                            st.info(f"{tr('Other plausible causes to validate:')} {cand_txt}")
                        st.rerun() # Rerun to refresh the map and date input below
                    else:
                        st.session_state['selected_disease_id'] = None
                        st.session_state['disease_spots'] = _merge_disease_spots_preserving_manual([])
                        if st.session_state.get('disease_spots'):
                            st.warning(tr('Satellite scan found no new canopy anomaly; manual disease foci were preserved.'))
                        else:
                            st.success(f"✅ {tr(msg)}")
                else:
                    st.error(f"{tr('Detection Failed:')} {tr(msg)}")
                
        st.caption(tr("Algorithm uses LAI vs NDMI correlation to distinguish disease from water stress."))
        st.divider()

        # --- MANUAL OVERRIDE SECTION ---
        st.markdown("##### ✍️ " + tr("Manual Configuration / Verification"))
        
        # Refresh df_d in case auto-detect added something
        df_d = st.session_state['df_diseases']
        rel_d = df_d[df_d['Target_Crop_Name'] == c_row['Crop_Name']]
        # Include Generic if present
        if not df_d[df_d['Disease_ID'] == 'D_GEN_01'].empty:
             rel_d = pd.concat([rel_d, df_d[df_d['Disease_ID'] == 'D_GEN_01']])

        c_dis, c_date = st.columns([2, 1])
        selected_d_type = ""

        with c_dis:
            if rel_d.empty: 
                st.warning(tr("No specific diseases found for this crop."))
                st.session_state['selected_disease_id'] = None
            else:
                curr_dis_id = st.session_state.get('selected_disease_id')
                # Find index
                dis_names = rel_d['Disease_Name'].unique()
                idx = 0
                if curr_dis_id:
                    row = rel_d[rel_d['Disease_ID'] == curr_dis_id]
                    if not row.empty:
                        nm = row.iloc[0]['Disease_Name']
                        if nm in dis_names:
                             idx = list(dis_names).index(nm)

                d_name = st.selectbox(tr("Identified Threat"), dis_names, index=idx)
                dis_row = rel_d[rel_d['Disease_Name'] == d_name].iloc[0]
                st.session_state['selected_disease_id'] = dis_row['Disease_ID']
                selected_d_type = dis_row['Type']

        with c_date:
            st.session_state['detection_date'] = st.date_input(tr("Detection Date"), value=st.session_state['detection_date'])
            if 'fungal' in str(selected_d_type).lower() or 'bacterial' in str(selected_d_type).lower():
                st.info(f"💨 **{tr('Wind/Rain:')}** {selected_d_type}")
                st.session_state['insect_pressure'] = 1.0 
            elif 'unknown' in str(selected_d_type).lower():
                st.warning(f"❓ **{tr('Modeled:')}** {selected_d_type}")
                st.session_state['insect_pressure'] = 1.0
            else:
                st.info(f"🦟 **{tr('Vector:')}** {selected_d_type}")
                st.session_state['insect_pressure'] = st.slider(tr("Vector Pressure"), 0.0, 5.0, st.session_state.get('insect_pressure', 1.0))
        
        st.divider()
        col_map, col_list = st.columns([2, 1])
        with col_map:
            st.markdown("#### 📍 " + tr("Field Map"))
            coords = st.session_state['field_coords']
            bounds = get_bounds(coords)
            center = [(bounds[0][0]+bounds[1][0])/2, (bounds[0][1]+bounds[1][1])/2]
            m = folium.Map(location=center, zoom_start=18)
            m.fit_bounds(bounds)
            folium.Polygon(locations=coords, color="blue", weight=3, fill=False).add_to(m)
            for spot in st.session_state['disease_spots']:
                r = 2 + (spot.get('plants', 1) * 0.5)
                folium.CircleMarker(location=[spot['lat'], spot['lon']], radius=r, color='crimson', fill=True, fill_opacity=0.9).add_to(m)
            Draw(export=False, position='topleft', draw_options={'polyline':False,'polygon':False,'rectangle':False,'circle':False,'circlemarker':False,'marker':True}, edit_options={'edit': False}).add_to(m)
            out = st_folium(m, height=450, width=None, key="map_step_3")
            if out['last_active_drawing']:
                draw = out['last_active_drawing']
                if draw['geometry']['type'] == 'Point':
                    lon, lat = draw['geometry']['coordinates']
                    if is_point_in_polygon([lat, lon], coords):
                        if not any(abs(s['lat']-lat)<1e-5 for s in st.session_state['disease_spots']):
                            st.session_state['disease_spots'].append({'lat': lat, 'lon': lon, 'plants': 1, 'date': str(st.session_state['detection_date']), 'source': 'manual'})
                            st.rerun()
                    else: st.toast("⚠️ " + tr("Outside boundary"), icon="🚫")
        with col_list:
            st.markdown("#### 📝 " + tr("Infection Log"))
            spots = st.session_state['disease_spots']
            if spots:
                edf = st.data_editor(pd.DataFrame(spots), num_rows="dynamic", column_config={"plants": st.column_config.NumberColumn(tr("Count"), min_value=1), "lat": st.column_config.NumberColumn(tr("Latitude"), disabled=True), "lon": st.column_config.NumberColumn(tr("Longitude"), disabled=True), "date": st.column_config.TextColumn(tr("Date"), disabled=True)}, hide_index=True, key="editor_spots")
                if edf.to_dict('records') != spots:
                    st.session_state['disease_spots'] = edf.to_dict('records')
                    st.rerun()
            else: st.info(tr("No spots marked."))
        _render_disease_evidence_panel()
        
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ " + tr("Back")): st.session_state['step'] = 2; st.rerun()
        if c_next.button(tr("Next") + " ➡️"): st.session_state['step'] = 4; st.rerun()

    # ==========================================================================
    # STEP 4: SOIL & MANAGEMENT
    # ==========================================================================
    elif st.session_state['step'] == 4:
        st.subheader("🪨 " + tr("Step 4: Soil & Management Operations"))
        c_id = st.session_state.get('selected_crop_id')
        row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
        is_perennial = row['Type'] == 'Perennial'
        st.markdown("##### " + tr("Soil Profile & Nutrient Intelligence"))
        status_container = st.container()
        c_auto, c_hist = st.columns([1, 2])
        with c_auto:
            if st.button(tr("Auto-detect soil"), help=tr("Uses OpenLandMap 250 m gridded soil layers from 0 to 150 cm when available.")):
                with st.spinner(tr("Reading gridded soil texture, carbon and clay layers...")):
                    success, data, error_msg = get_auto_soil_profile(st.session_state['field_coords'])
                    if success:
                        st.session_state['soil_type'] = data['texture']
                        st.session_state['soil_layers'] = pd.DataFrame(data.get('soil_layers', []))
                        st.session_state['soil_data_source'] = data.get('source', 'auto')
                        st.session_state['soil_confidence'] = data.get('confidence', 0.55)
                        st.session_state['soil_detection_notes'] = data.get('warning', '')
                        years_farming = st.session_state.get('history_years', 0)
                        base_n = data['n_available']
                        base_p = max(6.0, min(45.0, (12.0 + (data['carbon'] * 0.35)) - (data['clay'] * 0.10)))
                        base_k = max(45.0, min(240.0, 55.0 + (data['clay'] * 2.2)))
                        final_n = base_n * ((1 - 0.05) ** years_farming)
                        final_p = base_p * ((1 - 0.02) ** years_farming)
                        final_k = base_k * ((1 - 0.03) ** years_farming)
                        st.session_state['initial_nitrogen'] = round(final_n, 1)
                        st.session_state['initial_phosphorus'] = round(final_p, 1)
                        st.session_state['initial_potassium'] = round(final_k, 1)
                        status_container.success(f"{tr('Analysis successful')}\n\n{tr('Texture:')} {data['texture'].upper()}\n{tr('Profile depth:')} {data['profile_depth_m']:.1f} m\n{tr('Organic carbon:')} {data['carbon']:.1f} g/kg\n{tr('Total N estimate:')} {data['n_total']:.0f} mg/kg\n{tr('Available N start:')} {final_n:.1f} mg/kg\n{tr('Confidence:')} {data['confidence']*100:.0f}%")
                        status_container.caption(tr(data.get('warning', '')))
                        import time; time.sleep(1.0); st.rerun()
                    else: status_container.error(f"{tr('Detection failed:')} {error_msg}")
        with c_hist:
            st.session_state['history_years'] = st.slider("📉 " + tr("Land Use History (Years farmed without fertilizer)"), 0, 20, 0, help=tr("Reduces initial nutrient levels to account for soil mining."))
        st.divider()
        c_soil_cfg, c_soil_info = st.columns([1, 1])
        with c_soil_cfg:
            expert_mode = st.toggle(tr("Expert Mode (Edit Soil Physics)"), value=st.session_state.get('use_expert_soil', False))
            st.session_state['use_expert_soil'] = expert_mode
            if not expert_mode:
                soils = list(_SOIL_TABLE.keys())
                curr_soil = st.session_state.get('soil_type', 'loam').lower()
                if curr_soil not in soils: curr_soil = 'loam'
                selected_soil = st.selectbox(tr("Soil Texture Class"), options=soils, index=soils.index(curr_soil), format_func=lambda soil: tr(soil.title()))
                selected_soil_key = selected_soil
                auto_profile_active = (
                    st.session_state.get('soil_data_source', 'manual') != 'manual'
                    and st.session_state.get('soil_layers') is not None
                    and not st.session_state['soil_layers'].empty
                    and selected_soil_key == curr_soil
                )
                st.session_state['soil_type'] = selected_soil_key
                props = _SOIL_TABLE[st.session_state['soil_type']]
                if not auto_profile_active:
                    st.session_state['soil_data_source'] = 'manual'
                    st.session_state['soil_confidence'] = 1.0
                    st.session_state['soil_detection_notes'] = ''
                    st.session_state['soil_layers'] = pd.DataFrame([{
                        'depth_top': 0.0, 'depth_bottom': 1.5,
                        'texture': st.session_state['soil_type'],
                        'field_capacity': props['field_capacity'],
                        'wilting_point': props['wilting_point']
                    }])
            st.markdown("###### " + tr("Initial Available Nutrients (mg/kg)"))
            c_n, c_p, c_k = st.columns(3)
            with c_n: st.session_state['initial_nitrogen'] = st.number_input(tr("Nitrogen (N-NO3)"), value=float(st.session_state.get('initial_nitrogen', 15.0)), step=1.0, help=tr("Available Nitrogen. <10 is critical deficiency."))
            with c_p: st.session_state['initial_phosphorus'] = st.number_input(tr("Phosphorus (P)"), value=float(st.session_state.get('initial_phosphorus', 20.0)), step=1.0)
            with c_k: st.session_state['initial_potassium'] = st.number_input(tr("Potassium (K)"), value=float(st.session_state.get('initial_potassium', 100.0)), step=5.0)
        with c_soil_info:
            if expert_mode: st.info(f"🔧 **{tr('Expert Mode Active')}**: {tr('Define horizons manually.')}")
            else:
                props = _SOIL_TABLE[st.session_state['soil_type']]
                whc = (props['field_capacity'] - props['wilting_point']) * 100
                source = st.session_state.get('soil_data_source', 'manual')
                confidence = st.session_state.get('soil_confidence', 1.0)
                st.info(f"**{tr('Properties')} ({tr(st.session_state['soil_type'].title())})**")
                if source != 'manual':
                    st.caption(f"{tr('Automatic soil estimate:')} {tr(source)}; {tr('confidence')} {confidence*100:.0f}%. {tr('Replace with field or lab data when available.')}")
                st.write(f"{tr('Field Capacity:')} **{props['field_capacity']*100:.0f}%**")
                st.write(f"{tr('Wilting Point:')} **{props['wilting_point']*100:.0f}%**")
                st.metric(tr("Water Holding Capacity"), f"{whc:.1f}%")
        if expert_mode:
            st.session_state['soil_layers'] = st.data_editor(
                st.session_state['soil_layers'],
                num_rows="dynamic",
                key="editor_layers",
                use_container_width=True,
                column_config={
                    "depth_top": st.column_config.NumberColumn(tr("Depth top")),
                    "depth_bottom": st.column_config.NumberColumn(tr("Depth bottom")),
                    "texture": st.column_config.TextColumn(tr("Texture")),
                    "field_capacity": st.column_config.NumberColumn(tr("Field capacity")),
                    "wilting_point": st.column_config.NumberColumn(tr("Wilting point")),
                },
            )
        st.divider()
        _render_operational_constraints(prefix='single_')
        st.divider()
        c_fert, c_irr = st.columns(2)
        fert_service = FertilizerService()
        product_names = [p['name'] for p in fert_service.products]
        with c_fert:
            st.markdown("##### 🧪 " + tr("Fertilizer & Operations"))
            if is_perennial: st.info(f"📅 **{tr('Recurring Schedule (10 years)')}**")
            else: st.caption(tr("Add fertilization events."))
            df_fert = st.session_state['fert_schedule']
            if df_fert.empty: df_fert = pd.DataFrame({"date": [date.today() + timedelta(days=30)], "product": ["NPK 15-15-15 Compound"], "amount": [100.0]})
            if 'date' in df_fert.columns: df_fert['date'] = pd.to_datetime(df_fert['date']).dt.date
            edited_fert = st.data_editor(df_fert, num_rows="dynamic", column_config={"date": st.column_config.DateColumn(tr("Date")), "product": st.column_config.SelectboxColumn(tr("Product"), options=product_names, width="medium"), "amount": st.column_config.NumberColumn(tr("Amount (kg/ha)"), min_value=0, max_value=1000, step=50)}, key="editor_fert")
            st.session_state['fert_schedule'] = edited_fert
        with c_irr:
            st.markdown("##### 💧 " + tr("Irrigation Schedule"))
            if is_perennial: st.info(f"📅 **{tr('Recurring Schedule')}**")
            else: st.caption(tr("Inputs in **mm** (1 mm = 10,000 L/ha)."))
            df_irr = st.session_state['irr_schedule']
            if not df_irr.empty: df_irr['date'] = pd.to_datetime(df_irr['date']).dt.date
            st.session_state['irr_schedule'] = st.data_editor(df_irr, num_rows="dynamic", column_config={"date": st.column_config.DateColumn(tr("Date")), "amount": st.column_config.NumberColumn(tr("Amount (mm)"))}, key="editor_irr")
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ " + tr("Back")): st.session_state['step'] = 3; st.rerun()
        if c_next.button(tr("Next: Economy") + " ➡️"): st.session_state['step'] = 5; st.rerun()

    # ==========================================================================
    # STEP 5: ECONOMY
    # ==========================================================================
    elif st.session_state['step'] == 5:
        _render_economics_setup(prefix='single_economics')
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ " + tr("Back"), key='economics_back'): st.session_state['step'] = 4; st.rerun()
        if c_next.button(tr("Next: Review") + " ➡️", key='economics_next'): st.session_state['step'] = 6; st.rerun()

    # ==========================================================================
    # STEP 6: LAUNCH
    # ==========================================================================
    elif st.session_state['step'] == 6:
        st.subheader("🚀 " + tr("Step 6: Review & Launch"))
        c_sum1, c_sum2 = st.columns(2)
        with c_sum1:
            c_id = st.session_state.get('selected_crop_id')
            row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
            st.success(f"**{tr('Crop:')}** {row['Crop_Name']} ({row['Variety']})")
            st.info(f"**{tr('Planting:')}** {st.session_state['planting_date']}")
        with c_sum2:
            st.info(f"**{tr('Field Area:')}** {st.session_state.get('area_ha', 0)} ha")
            st.info(f"**{tr('Disease Spots:')}** {len(st.session_state['disease_spots'])}")
        _render_diagnostic_quality_panel()
        c_save, c_run = st.columns(2)
        with c_save:
            st.download_button("💾 " + tr("Save Config"), data=StateManager.save_config_to_json(), file_name="field_config.json", mime="application/json", use_container_width=True)
        with c_run:
            if st.button("🔥 " + tr("Initialize Digital Twin"), type="primary", use_container_width=True):
                st.session_state['setup_complete'] = True
                st.session_state['nav_target'] = "Intelligence Dashboard"
                if 'sim_results' in st.session_state: del st.session_state['sim_results']
                st.rerun()
        if st.button("⬅️ " + tr("Back to Economy")): st.session_state['step'] = 5; st.rerun()