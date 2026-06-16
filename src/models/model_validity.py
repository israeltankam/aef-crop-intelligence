# src/models/model_validity.py
"""Scientific validity messages for model outputs.

These functions do not change model results.  They make the app more honest by
separating the selected scientific model family from the lightweight internal
adapter currently used at runtime.
"""
from __future__ import annotations

from typing import Dict, List


def growth_model_caveat(growth_model: Dict[str, object] | None) -> str:
    model = growth_model or {}
    if model.get("fallback_used", False) or str(model.get("adapter_status", "")).startswith("surrogate"):
        return "AEF-lite surrogate is active: the selected family guides assumptions, but the full external simulator is not running. Treat outputs as decision support until locally calibrated."
    return "External validated growth-model adapter reported as active. Continue local validation before operational use."


def disease_detection_caveat(auto_detected: bool, disease_model: Dict[str, object] | None = None) -> str:
    if auto_detected:
        return "Satellite detection identifies canopy stress patterns, not a pathogen with certainty. Field symptom validation is required before irreversible disease-control actions."
    return "Disease configuration is user supplied; confidence depends on field diagnosis quality and local scouting."


def model_validity_cards(growth_model: Dict[str, object] | None, disease_model: Dict[str, object] | None, auto_detected: bool = False) -> List[str]:
    return [growth_model_caveat(growth_model), disease_detection_caveat(auto_detected, disease_model)]


def model_validity_impact_cards(growth_model: Dict[str, object] | None, disease_model: Dict[str, object] | None, auto_detected: bool = False) -> List[Dict[str, str]]:
    """Return model caveats with explicit decision impact.

    The plain string caveats are kept for backward compatibility.  These richer
    cards are used in the dashboard and PDF so users understand which expensive
    or irreversible decisions need validation before execution.
    """
    cards: List[Dict[str, str]] = []
    growth_message = growth_model_caveat(growth_model)
    growth_level = "Verify before costly action" if "AEF-lite" in growth_message else "Planning support"
    cards.append({
        "area": "Growth model",
        "level": growth_level,
        "message": growth_message,
        "decision_impact": "Can shift sowing-date, irrigation and fertilizer timing decisions; validate with local yield or biomass observations.",
    })

    disease_message = disease_detection_caveat(auto_detected, disease_model)
    disease_level = "Field validation required" if auto_detected else "Diagnosis quality dependent"
    cards.append({
        "area": "Disease diagnosis",
        "level": disease_level,
        "message": disease_message,
        "decision_impact": "Can affect roguing, pruning or treatment recommendations; avoid irreversible action without symptom confirmation.",
    })
    return cards
