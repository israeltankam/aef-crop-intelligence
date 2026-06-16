# src/models/cooperative_constraints.py
"""Shared-resource checks for cooperative recommendations.

A cooperative report should not silently add together plot-level optima and imply
that the group can execute all of them.  These helpers evaluate shared water,
fertilizer and labour limits and return conservative feasibility notes.  They do
not replace detailed economic optimization; they prevent overconfident reports.
"""
from __future__ import annotations

from typing import Dict, Iterable, List


def evaluate_shared_resource_constraints(summary: Dict[str, float], config: Dict[str, object]) -> Dict[str, object]:
    water_limit = float(config.get("cooperative_report_water_limit_m3", 0.0) or 0.0)
    fert_limit = float(config.get("cooperative_report_fertilizer_limit_kg", 0.0) or 0.0)
    labour_limit = float(config.get("cooperative_report_labour_days", 0.0) or 0.0)
    water_need = float(summary.get("water_m3", 0.0) or 0.0)
    fert_need = float(summary.get("fertilizer_kg", 0.0) or 0.0)
    optimized_plots = int(summary.get("optimized_plot_count", 0) or 0)

    constraints: List[str] = []
    factors: List[float] = [1.0]
    if water_limit > 0 and water_need > water_limit:
        factors.append(max(0.0, water_limit / max(water_need, 1e-9)))
        constraints.append("Optimized irrigation exceeds the cooperative shared water limit.")
    if fert_limit > 0 and fert_need > fert_limit:
        factors.append(max(0.0, fert_limit / max(fert_need, 1e-9)))
        constraints.append("Optimized fertilizer demand exceeds the cooperative shared fertilizer limit.")
    if labour_limit > 0:
        estimated_labour = optimized_plots * 0.25
        if estimated_labour > labour_limit:
            factors.append(max(0.0, labour_limit / max(estimated_labour, 1e-9)))
            constraints.append("Optimized actions may exceed available cooperative labour days.")
    resource_factor = min(factors)
    return {
        "resource_feasible": not constraints,
        "resource_factor": round(resource_factor, 3),
        "constraints": constraints,
        "water_limit_m3": water_limit,
        "fertilizer_limit_kg": fert_limit,
        "labour_limit_days": labour_limit,
    }
