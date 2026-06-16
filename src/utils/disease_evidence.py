# src/utils/disease_evidence.py
"""Disease evidence synthesis for satellite and manual observations.

The satellite module detects canopy stress, not pathogen identity.  This helper
keeps that distinction visible by summarising what evidence exists, where it came
from, and what the user should validate before taking costly or irreversible
actions.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional


def build_disease_evidence(config: Dict[str, object], disease_name: Optional[str] = None) -> Dict[str, object]:
    spots: List[Dict[str, object]] = list(config.get("disease_spots", []) or [])
    manual = [s for s in spots if str(s.get("source", "manual")) == "manual"]
    automatic = [s for s in spots if str(s.get("source", "")) != "manual"]
    has_satellite = bool(config.get("satellite_anomaly_date")) or bool(automatic)
    selected = disease_name or str(config.get("selected_disease_id") or "")

    evidence = []
    if has_satellite:
        evidence.append({
            "source": "Satellite canopy scan",
            "status": "Canopy stress detected" if selected else "Canopy stress screen available",
            "confidence": "Medium",
            "decision_impact": "Suggests where to scout; does not prove pathogen identity.",
        })
    if manual:
        evidence.append({
            "source": "Manual field scouting",
            "status": "Mapped disease foci",
            "count": len(manual),
            "confidence": "Higher" if selected else "Medium",
            "decision_impact": "Can support roguing, pruning or targeted treatment if symptoms match the suspected disease.",
        })
    if not evidence:
        evidence.append({
            "source": "No direct evidence",
            "status": "No mapped disease evidence yet",
            "confidence": "Low",
            "decision_impact": "Disease recommendations should remain preventive and scouting-oriented.",
        })

    conflict = has_satellite and manual and not selected
    if conflict:
        interpretation = "Satellite and manual evidence exist, but no disease identity has been selected. Validate likely diseases before intervention."
    elif has_satellite and not manual:
        interpretation = "Satellite evidence should guide field scouting before costly disease control."
    elif manual:
        interpretation = "Manual foci improve confidence, but treatment still depends on symptoms, crop stage and pathogen type."
    else:
        interpretation = "No active disease evidence; keep routine scouting."

    return {
        "disease_name": selected or "Unspecified disease",
        "evidence": evidence,
        "manual_focus_count": len(manual),
        "automatic_focus_count": len(automatic),
        "has_satellite_evidence": has_satellite,
        "has_manual_evidence": bool(manual),
        "conflict_or_gap": conflict,
        "interpretation": interpretation,
    }
