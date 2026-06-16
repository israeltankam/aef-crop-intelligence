# src/utils/decision_support.py
"""Plain-language decision support helpers.

The simulation engine produces scientifically useful quantities, but a farm
manager needs a shorter answer: what to check, what to do, and how cautious to
be.  These helpers translate model outputs into decision cards without changing
underlying agronomic calculations.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Iterable, List


@dataclass
class DecisionCard:
    area: str
    level: str
    title: str
    message: str
    recommended_next_step: str
    confidence: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def confidence_label(yield_margin_fraction: float, has_field_observations: bool, auto_soil: bool) -> str:
    """Return an operational confidence label from uncertainty drivers."""
    if yield_margin_fraction >= 0.25 or (auto_soil and not has_field_observations):
        return "Low - field validation recommended"
    if yield_margin_fraction >= 0.14 or auto_soil:
        return "Medium - useful for planning, confirm before costly action"
    return "Higher - still monitor with field observations"


def build_decision_snapshot(history: Iterable[Dict[str, object]], config: Dict[str, object], crop_params: Dict[str, object], uncertainty_profile: Dict[str, object] | None = None) -> List[Dict[str, str]]:
    """Create short, conservative decision cards from a simulated trajectory."""
    rows = list(history or [])
    if not rows:
        return []
    last = rows[-1]
    max_water = max(float(r.get("Avg_Stress", 0.0) or 0.0) for r in rows)
    max_n = max(float(r.get("Avg_N_Stress", 0.0) or 0.0) for r in rows)
    final_inc = float(last.get("Incidence", 0.0) or 0.0)
    yield_val = float(last.get("Yield", last.get("Fruit_Biomass", 0.0)) or 0.0)
    profile = uncertainty_profile or {}
    margin_fraction = float(profile.get("yield_ci_fraction_95", 0.18))
    has_obs = int(profile.get("adaptive_observation_count", 0) or 0) > 0
    auto_soil = str(config.get("soil_data_source", "manual")) != "manual"
    conf = confidence_label(margin_fraction, has_obs, auto_soil)

    cards: List[DecisionCard] = []
    if final_inc > 0.25:
        cards.append(DecisionCard("Disease", "High", "Disease pressure requires field confirmation", "The model projects substantial incidence. Satellite-only disease identity should not trigger irreversible action without scouting.", "Inspect the highest-risk foci, confirm symptoms, then apply the roguing/pruning balance before removal.", conf))
    elif final_inc > 0.05:
        cards.append(DecisionCard("Disease", "Medium", "Disease pressure is emerging", "The disease signal is not negligible, but the best action depends on field confirmation and pathogen type.", "Scout the mapped foci and record incidence in adaptive surveillance.", conf))
    else:
        cards.append(DecisionCard("Disease", "Watch", "No major disease pressure projected", "Disease risk is currently low in the simulation.", "Keep routine scouting, especially after wet or vector-favourable periods.", conf))

    if max_water > 0.60:
        cards.append(DecisionCard("Water", "High", "Water stress is a priority", "The simulated crop spends time above the severe water-stress threshold.", "Check water availability, pump capacity and irrigation method before adopting the optimized calendar.", conf))
    elif max_water > 0.30:
        cards.append(DecisionCard("Water", "Medium", "Water stress is moderate", "Supplemental irrigation may improve resilience during sensitive periods.", "Prioritize irrigation around the stress peaks rather than uniform watering.", conf))

    if max_n > 0.50:
        cards.append(DecisionCard("Nutrition", "High", "Nitrogen limitation is likely", "The model projects repeated nitrogen stress, but fertilizer choice should reflect local availability and cost.", "Confirm with a soil or leaf test when possible, then compare total product requirement and budget.", conf))
    elif max_n > 0.25:
        cards.append(DecisionCard("Nutrition", "Medium", "Nutrient stress should be monitored", "The nutrient signal is moderate and may reflect soil data uncertainty.", "Add a soil nutrient observation to reduce the fertilizer recommendation margin.", conf))

    if yield_val <= 0.01:
        cards.append(DecisionCard("Yield", "Caution", "Yield forecast is near zero", "This can happen for future planting dates, missing crop age in perennials, or severe stress assumptions.", "Review planting date, crop age, soil water and disease inputs before using the forecast operationally.", conf))
    return [c.to_dict() for c in cards]
