# src/utils/diagnostic_quality.py
"""Diagnostic-quality scoring for AEF Crop Intelligence.

This module translates data provenance into a plain-language readiness score.  It
is deliberately separate from the crop engines: the score does not change model
outputs, it tells the user how much confidence to place in the diagnosis and what
measurement would most reduce uncertainty.
"""
from __future__ import annotations

from typing import Dict, Iterable, List


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _component(name: str, score: float, status: str, impact: str, next_step: str) -> Dict[str, object]:
    """Return one serialisable quality component for UI/report rendering."""
    return {
        "name": name,
        "score": round(_clamp(score) * 100.0, 1),
        "status": status,
        "impact": impact,
        "next_step": next_step,
    }


def _has_manual_disease_spot(spots: Iterable[Dict[str, object]]) -> bool:
    return any(str(s.get("source", "manual")) == "manual" for s in spots or [])


def build_diagnostic_quality(config: Dict[str, object], result: Dict[str, object] | None = None) -> Dict[str, object]:
    """Build a user-facing diagnostic quality score from available evidence.

    Scores intentionally penalise automatic or missing inputs without blocking the
    workflow.  AEF remains usable for non-experts, but the output makes clear when
    a recommendation is only preliminary.
    """
    mode = str(config.get("app_mode") or result.get("mode") if result else config.get("app_mode") or "single")
    soil_source = str(config.get("soil_data_source", "manual") or "manual")
    soil_conf = _clamp(float(config.get("soil_confidence", 1.0) or 1.0), 0.25, 1.0)
    spots = config.get("disease_spots", []) or []
    has_satellite = bool(config.get("satellite_anomaly_date"))
    has_manual_spots = _has_manual_disease_spot(spots)
    surveillance_count = len(config.get("surveillance_logs", []) or [])
    calibrated = bool(config.get("calibrated_params"))
    geometry_ok = bool(config.get("field_coords") or config.get("cooperative_perimeter_coords"))
    active_parcels = [p for p in config.get("cooperative_parcels", []) or [] if p.get("active", True)]
    auto_parcels = [p for p in active_parcels if "candidate" in str(p.get("source", ""))]
    perennial_age = float(config.get("initial_plant_age_years", 0.0) or 0.0)
    is_perennial = perennial_age > 0 or bool(config.get("perennial_last_pruning_date") or config.get("perennial_dormancy_start_month"))

    components: List[Dict[str, object]] = []
    components.append(_component(
        "Field geometry",
        0.90 if geometry_ok else 0.25,
        "usable" if geometry_ok else "missing",
        "Geometry controls area, weather extraction and parcel-level aggregation.",
        "Validate field or cooperative boundaries on the satellite map.",
    ))
    components.append(_component(
        "Soil information",
        soil_conf if soil_source == "manual" else min(soil_conf, 0.68),
        "field-entered" if soil_source == "manual" else "automatic coarse grid",
        "Soil uncertainty mainly affects irrigation and fertilization decisions.",
        "Add a soil test or expert soil profile before costly fertilizer decisions.",
    ))
    disease_score = 0.85 if has_manual_spots else 0.62 if has_satellite else 0.55 if config.get("selected_disease_id") else 0.72
    components.append(_component(
        "Disease evidence",
        disease_score,
        "manual and/or satellite evidence" if (has_manual_spots or has_satellite) else "no field evidence",
        "Disease evidence can change roguing, pruning, scouting and yield-risk decisions.",
        "Confirm suspected canopy anomalies with field scouting and record incidence.",
    ))
    components.append(_component(
        "Adaptive calibration",
        0.86 if calibrated else min(0.72, 0.42 + surveillance_count * 0.08),
        "calibrated" if calibrated else "uncalibrated" if surveillance_count == 0 else "observations available",
        "Calibration reduces yield, nutrient and disease uncertainty over repeated use.",
        "Add yield, biomass, soil nutrient or disease observations after field visits.",
    ))
    if mode == "cooperative":
        parcel_score = 0.82
        if active_parcels:
            low_conf = [p for p in active_parcels if float(p.get("confidence", 1.0) or 1.0) < 0.58]
            parcel_score -= min(0.30, len(low_conf) / max(1, len(active_parcels)) * 0.35)
            parcel_score -= 0.08 if auto_parcels else 0.0
        else:
            parcel_score = 0.20
        components.append(_component(
            "Cooperative parcel curation",
            parcel_score,
            "needs map validation" if auto_parcels else "manual or validated",
            "Parcel quality controls per-farmer recommendations and cooperative aggregation.",
            "Name plots and validate low-confidence candidates before producing final advice.",
        ))
    if is_perennial:
        perennial_score = 0.78 if perennial_age > 0 else 0.42
        if not config.get("perennial_last_pruning_date"):
            perennial_score -= 0.10
        components.append(_component(
            "Perennial context",
            perennial_score,
            "age/pruning context entered" if perennial_score >= 0.70 else "incomplete perennial context",
            "Perennial age, pruning and dormancy affect yield horizon and disease pressure.",
            "Record plantation age, recent pruning and expected low-pressure season.",
        ))

    overall = round(sum(c["score"] for c in components) / max(1, len(components)), 1)
    # A cooperative configuration without active plots is not actionable even if
    # soil or crop inputs are otherwise complete.  Cap the score so the UI cannot
    # present it as operational planning quality.
    if mode == "cooperative" and not active_parcels:
        overall = min(overall, 49.0)
    if overall >= 78:
        label = "Operational planning quality"
        color = "green"
    elif overall >= 58:
        label = "Preliminary decision-support quality"
        color = "orange"
    else:
        label = "Exploratory diagnosis only"
        color = "red"
    blockers = [c for c in components if c["score"] < 50]
    costly = [c for c in components if 50 <= c["score"] < 70]
    return {
        "overall_score": overall,
        "label": label,
        "color": color,
        "components": components,
        "decision_impact": {
            "blocking": [c["name"] for c in blockers],
            "verify_before_costly_action": [c["name"] for c in costly],
            "ready_for_planning": [c["name"] for c in components if c["score"] >= 70],
        },
        "next_best_measurement": blockers[0]["next_step"] if blockers else costly[0]["next_step"] if costly else "Continue routine adaptive surveillance to keep uncertainty shrinking.",
    }
