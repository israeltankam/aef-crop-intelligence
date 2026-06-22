# src/models/cooperative_parcel_detector.py
"""Lightweight cooperative parcel candidate delineation.

Scientific note
---------------
Operational agricultural parcel delineation from satellite imagery is normally
framed as boundary or instance segmentation.  A full trained regional model is
outside this app's lightweight runtime today, so this module deliberately returns
editable *candidate parcels*.  The generator is deterministic, non-overlapping,
more precise than the first grid pass, and produces irregular polygons rather
than equal rectangles.  Human validation on the satellite map remains mandatory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import random
from typing import Iterable, List, Sequence, Tuple

LatLon = Tuple[float, float]
PointXY = Tuple[float, float]


@dataclass
class ParcelCandidate:
    """Editable parcel proposal returned to the Streamlit setup page."""

    id: str
    name: str
    active: bool
    coords: List[LatLon]
    area_ha: float
    confidence: float
    source: str
    requires_validation: bool
    notes: str

    def to_dict(self) -> dict:
        return asdict(self)


def _meters_per_degree(lat: float) -> Tuple[float, float]:
    return 111_320.0, 111_320.0 * max(0.2, math.cos(math.radians(lat)))


def _centroid(coords: Sequence[LatLon]) -> LatLon:
    pts = list(coords or [])
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _centroid_xy(points: Sequence[PointXY]) -> PointXY:
    pts = list(points or [])
    if not pts:
        return (0.0, 0.0)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _to_xy(coords: Sequence[LatLon], origin: LatLon) -> List[PointXY]:
    mlat, mlon = _meters_per_degree(origin[0])
    return [((lon - origin[1]) * mlon, (lat - origin[0]) * mlat) for lat, lon in coords]


def _to_latlon(points: Sequence[PointXY], origin: LatLon) -> List[LatLon]:
    mlat, mlon = _meters_per_degree(origin[0])
    return [(origin[0] + y / mlat, origin[1] + x / mlon) for x, y in points]


def _point_in_poly_xy(point: PointXY, poly: Sequence[PointXY]) -> bool:
    x, y = point
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            x_at_y = (xj - xi) * (y - yi) / ((yj - yi) + 1e-12) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


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


def _bbox(points: Sequence[PointXY]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_overlap(a: Sequence[PointXY], b: Sequence[PointXY], gap_m: float = 0.0) -> bool:
    ax1, ay1, ax2, ay2 = _bbox(a)
    bx1, by1, bx2, by2 = _bbox(b)
    return not (ax2 + gap_m < bx1 or bx2 + gap_m < ax1 or ay2 + gap_m < by1 or by2 + gap_m < ay1)


def _orientation(a: PointXY, b: PointXY, c: PointXY) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: PointXY, b: PointXY, c: PointXY) -> bool:
    return min(a[0], c[0]) - 1e-9 <= b[0] <= max(a[0], c[0]) + 1e-9 and min(a[1], c[1]) - 1e-9 <= b[1] <= max(a[1], c[1]) + 1e-9


def _segments_intersect(a1: PointXY, a2: PointXY, b1: PointXY, b2: PointXY) -> bool:
    o1 = _orientation(a1, a2, b1)
    o2 = _orientation(a1, a2, b2)
    o3 = _orientation(b1, b2, a1)
    o4 = _orientation(b1, b2, a2)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if abs(o1) < 1e-9 and _on_segment(a1, b1, a2):
        return True
    if abs(o2) < 1e-9 and _on_segment(a1, b2, a2):
        return True
    if abs(o3) < 1e-9 and _on_segment(b1, a1, b2):
        return True
    if abs(o4) < 1e-9 and _on_segment(b1, a2, b2):
        return True
    return False


def _polygons_overlap_xy(a: Sequence[PointXY], b: Sequence[PointXY]) -> bool:
    """Return True when two simple polygons intersect or contain one another."""
    if not a or not b or not _bbox_overlap(a, b):
        return False
    aa = list(a) + [a[0]]
    bb = list(b) + [b[0]]
    for i in range(len(aa) - 1):
        for j in range(len(bb) - 1):
            if _segments_intersect(aa[i], aa[i + 1], bb[j], bb[j + 1]):
                return True
    return _point_in_poly_xy(a[0], b) or _point_in_poly_xy(b[0], a)


def _seed_from_perimeter(perimeter: Sequence[LatLon], typical_area_ha: float) -> int:
    raw = repr([(round(a, 6), round(b, 6)) for a, b in perimeter]) + "|{:.3f}".format(typical_area_ha)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


def _irregular_plot_polygon(cx: float, cy: float, area_m2: float, aspect: float, angle_rad: float, rng: random.Random, vertices: int = 7) -> List[PointXY]:
    """Create a simple irregular field-like polygon around a centroid.

    The polygon is generated in polar order, so it stays editable and usually
    simple, while vertex radii vary enough to avoid artificial rectangles.
    """
    radius = math.sqrt(max(area_m2, 1.0) / math.pi)
    sx = radius * math.sqrt(max(0.35, aspect))
    sy = radius / math.sqrt(max(0.35, aspect))
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    points: List[PointXY] = []
    for i in range(vertices):
        theta = (2.0 * math.pi * i / vertices) + rng.uniform(-0.13, 0.13)
        roughness = rng.uniform(0.78, 1.22)
        x = math.cos(theta) * sx * roughness
        y = math.sin(theta) * sy * roughness
        points.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return points


def _inside_perimeter(poly: Sequence[PointXY], perimeter: Sequence[PointXY]) -> bool:
    if not all(_point_in_poly_xy(p, perimeter) for p in poly):
        return False
    cx, cy = _centroid_xy(poly)
    return _point_in_poly_xy((cx, cy), perimeter)


def detect_candidate_parcels(
    perimeter: Iterable[LatLon],
    typical_area_ha: float = 1.5,
    max_parcels: int = 240,
    variability: float = 0.65,
    precision_passes: int = 2,
) -> List[dict]:
    """Generate non-overlapping irregular parcel candidates inside a perimeter.

    Precision is increased by using a denser centroid search and multiple local
    shape attempts per centroid.  Runtime is allowed to grow roughly 2-4x compared
    with the earlier grid, which is acceptable because this runs only when the
    user explicitly asks for automatic cooperative plot candidates.
    """
    pts = list(perimeter or [])
    if len(pts) < 3:
        return []
    if pts[0] == pts[-1]:
        pts = pts[:-1]

    typical_area_ha = max(0.05, float(typical_area_ha or 1.5))
    max_parcels = max(1, int(max_parcels or 240))
    variability = min(0.95, max(0.10, float(variability)))
    precision_passes = max(1, min(4, int(precision_passes or 2)))

    origin = _centroid(pts)
    poly_xy = _to_xy(pts, origin)
    xs = [p[0] for p in poly_xy]
    ys = [p[1] for p in poly_xy]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    perimeter_area_ha = _polygon_area_m2(poly_xy) / 10_000.0
    target_m2 = typical_area_ha * 10_000.0
    nominal_side = math.sqrt(target_m2)
    rng = random.Random(_seed_from_perimeter(pts, typical_area_ha))

    candidates: List[ParcelCandidate] = []
    accepted_xy: List[List[PointXY]] = []
    step = nominal_side * (0.56 / precision_passes)
    min_area_ha = max(0.03, typical_area_ha * 0.14)
    max_total_area_ha = perimeter_area_ha * 0.96

    # Build a dense, deterministic cloud of potential centroids.  Sorting by a
    # random key gives organic placement without changing between clicks.
    centers: List[PointXY] = []
    y = min_y + step * 0.7
    while y < max_y:
        x = min_x + step * 0.7
        while x < max_x:
            jitter_x = rng.uniform(-0.24, 0.24) * step
            jitter_y = rng.uniform(-0.24, 0.24) * step
            p = (x + jitter_x, y + jitter_y)
            if _point_in_poly_xy(p, poly_xy):
                centers.append(p)
            x += step
        y += step
    centers.sort(key=lambda _: rng.random())

    total_area = 0.0
    for cx, cy in centers:
        if len(candidates) >= max_parcels or total_area >= max_total_area_ha:
            break
        # More attempts per centroid substantially improves coverage around
        # irregular perimeter edges and reduces accidental gaps.
        for _ in range(10 * precision_passes):
            area_factor = max(0.30, min(2.35, rng.uniform(1.0 - variability, 1.0 + variability)))
            aspect = rng.uniform(0.55, 2.15)
            angle = math.radians(rng.uniform(-28.0, 28.0))
            vertices = rng.choice([6, 7, 8, 9])
            raw = _irregular_plot_polygon(cx, cy, target_m2 * area_factor, aspect, angle, rng, vertices)
            accepted = None
            for shrink in [1.00, 0.90, 0.80, 0.70, 0.60, 0.50, 0.42]:
                ccx, ccy = _centroid_xy(raw)
                trial = [(ccx + (x - ccx) * shrink, ccy + (y - ccy) * shrink) for x, y in raw]
                area_ha = _polygon_area_m2(trial) / 10_000.0
                if area_ha < min_area_ha:
                    continue
                if not _inside_perimeter(trial, poly_xy):
                    continue
                if any(_polygons_overlap_xy(trial, prev) for prev in accepted_xy):
                    continue
                accepted = (trial, area_ha)
                break
            if accepted is None:
                continue
            trial, area_ha = accepted
            idx = len(candidates) + 1
            shape_complexity = min(0.12, (len(trial) - 4) * 0.02)
            edge_penalty = 0.08 if area_ha < typical_area_ha * 0.45 else 0.0
            # This fallback has no image evidence. Keep confidence deliberately
            # modest so users do not confuse plausible geometry with observed
            # field boundaries. Sentinel-2/FTW paths can score higher.
            conf = max(0.38, min(0.62, 0.50 + shape_complexity - edge_penalty))
            accepted_xy.append(trial)
            total_area += area_ha
            candidates.append(ParcelCandidate(
                id="P{:03d}".format(idx),
                name="Parcel {}".format(idx),
                active=True,
                coords=_to_latlon(trial, origin),
                area_ha=round(area_ha, 3),
                confidence=round(conf, 2),
                source="non_overlapping_irregular_candidate_detector",
                requires_validation=True,
                notes="Non-overlapping irregular candidate generated inside perimeter; validate against the satellite map.",
            ))
            break

    candidates.sort(key=lambda c: (-_centroid(c.coords)[0], _centroid(c.coords)[1]))
    for i, c in enumerate(candidates, start=1):
        c.id = "P{:03d}".format(i)
        c.name = "Parcel {}".format(i)
    return [c.to_dict() for c in candidates]
