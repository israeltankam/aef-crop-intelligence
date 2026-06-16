# src/models/operational_constraints.py
"""Operational constraints for irrigation and fertilizer recommendations.

The biophysical optimum is not always feasible on a real farm.  These helpers
keep the model conservative by translating water availability, method efficiency
and field area into practical caps and totals.  They are intentionally light and
can run during report generation without adding heavy dependencies.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple


def max_irrigation_mm_per_event(config: Dict[str, object], area_ha: float) -> Tuple[float, str]:
    """Return the maximum feasible irrigation depth for the configured field.

    1 mm over 1 hectare equals 10 cubic metres of water.  The available water is
    multiplied by an application-efficiency factor so the schedule does not imply
    impossible delivered depths.
    """
    area = max(0.01, float(area_ha or 0.01))
    water_m3_day = float(config.get("available_water_m3_day", 0.0) or 0.0)
    efficiency = float(config.get("irrigation_efficiency", 0.70) or 0.70)
    if water_m3_day <= 0:
        return float("inf"), "No water-capacity limit supplied."
    feasible_mm = max(0.0, (water_m3_day * max(0.1, min(1.0, efficiency))) / (area * 10.0))
    return feasible_mm, f"Limited by available water: {water_m3_day:.0f} m3/day at {efficiency*100:.0f}% efficiency."


def annotate_irrigation_schedule(schedule: Iterable[Dict[str, object]], config: Dict[str, object], area_ha: float) -> Tuple[List[Dict[str, object]], List[str]]:
    """Add total m3 and feasibility notes to irrigation events."""
    annotated: List[Dict[str, object]] = []
    warnings: List[str] = []
    cap_mm, cap_reason = max_irrigation_mm_per_event(config, area_ha)
    for event in schedule or []:
        amount_mm = float(event.get("amount", 0.0) or 0.0)
        total_m3 = amount_mm * max(0.01, float(area_ha or 0.01)) * 10.0
        feasible = amount_mm <= cap_mm if cap_mm != float("inf") else True
        row = dict(event)
        row["total_m3"] = round(total_m3, 1)
        row["feasible_with_constraints"] = feasible
        if not feasible:
            row["constraint_note"] = cap_reason
            warnings.append(f"{event.get('date')}: {amount_mm:.1f} mm exceeds feasible {cap_mm:.1f} mm/event.")
        annotated.append(row)
    return annotated, warnings


def fertilizer_totals_by_product(schedule: Iterable[Dict[str, object]], area_ha: float) -> Dict[str, float]:
    """Convert kg/ha recommendations into total product needs per field."""
    totals: Dict[str, float] = {}
    area = max(0.01, float(area_ha or 0.01))
    for event in schedule or []:
        product = str(event.get("product", "Unknown product"))
        amount = float(event.get("amount", 0.0) or 0.0) * area
        totals[product] = totals.get(product, 0.0) + amount
    return {k: round(v, 1) for k, v in totals.items()}
