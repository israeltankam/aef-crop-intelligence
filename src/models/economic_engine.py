# src/models/economic_engine.py
"""Lightweight economics engine for AEF Crop Intelligence.

The agronomic engines estimate crop state, stress and production.  This module is
kept separate so economic assumptions remain transparent, editable and easy to
save in JSON.  Automatic prices are deliberately treated as local/regional priors,
not as guaranteed farm-gate quotes; the UI always allows manual replacement.

Important perennial convention
------------------------------
For perennial crops such as cocoa, the economic production is not the fruit or
yield visible on the last simulated day.  The crop can be harvested many times
within the forecast horizon.  We therefore sum the annual harvest peaks over the
chosen economic horizon.  This avoids the misleading situation where twenty years
of intervention costs are compared with only one terminal standing-fruit value.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Tuple


# Conservative editable priors in XAF/t.  They are intentionally rounded and
# source-labeled because market prices vary by basin, season, quality and buyer.
# Cocoa is set higher than the former 2,000,000 XAF/t default because recent
# Cameroon farm-gate/export references have often been in the 3,500-4,350 XAF/kg
# range.  The UI still asks users to verify current local prices before investing.
CAMEROON_PRICE_REFERENCES = {
    "Cassava": 90000.0,
    "Maize": 180000.0,
    "Cotton": 450000.0,
    "Cocoa": 3500000.0,
    "Wheat": 220000.0,
    "Rice": 250000.0,
    "Soybean": 300000.0,
    "Coffee": 1500000.0,
}

DEFAULT_FERTILIZER_PRICES = {
    "Urea (Granular)": 450.0,
    "NPK 15-15-15 (Compound)": 520.0,
    "NPK 20-20-20+TE (Soluble)": 900.0,
    "NPK 12-12-17 (Compound)": 540.0,
    "Ammonium Sulphate": 380.0,
}

ECONOMIC_PRICE_SOURCE_OPTIONS = [
    "manual",
    "automatic regional prior",
    "automatic Cameroon/Central Africa prior",
    "automatic local prior",
    "market quote",
    "cooperative quote",
    "national statistics",
    "international reference",
]

PRICE_SOURCE_PROFILES = {
    "manual": {
        "confidence": 0.70,
        "detail": "Manual farm-gate price entered by the user; verify date, unit and buyer before investment.",
    },
    "market quote": {
        "confidence": 0.80,
        "detail": "Recent local market or buyer quote entered by the user; keep the quote date in the note.",
    },
    "cooperative quote": {
        "confidence": 0.78,
        "detail": "Cooperative or buyer-group quote entered by the user; confirm payment conditions and quality grade.",
    },
    "national statistics": {
        "confidence": 0.62,
        "detail": "National or public statistics reference; adjust for local farm-gate conditions, quality and transport.",
    },
    "international reference": {
        "confidence": 0.50,
        "detail": "International reference price; convert to local currency and discount for local farm-gate realities.",
    },
}

# Crop-specific defaults are meant to be good starting points, not hard-coded
# prescriptions.  Cacao uses the user's proposed labour structure, interpreted as
# cost per workday per hectare.  Roguing/pruning labour defaults to zero because
# these actions are not always required and should not be silently charged when
# scouting only leads to monitoring or targeted spraying.
CROP_SPECIFIC_DEFAULTS = {
    "Cocoa": {
        "postharvest_loss_pct": 3.0,
        "risk_discount_pct": 8.0,
        "price_confidence": 0.50,
        "price_source": "automatic Cameroon/Central Africa prior",
        "price_source_detail": "Editable cocoa prior from recent Cameroon farm-gate/export references; verify with the current buyer or cooperative price before investment.",
        "labor_costs": {
            "scouting_day": 10000.0,
            "fertilizer_application_day": 4000.0,
            "spraying_day": 5000.0,
            "roguing_day": 0.0,
            "pruning_day": 0.0,
        },
        "disease_control_costs": {
            "fungicide_per_l": 8000.0,
            "spray_service_per_ha": 6000.0,
            "plant_replacement_cost": 300.0,
        },
    }
}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return float(default)


def _crop_name(crop_params: Dict[str, object] | None, config: Dict[str, object] | None = None) -> str:
    if crop_params and crop_params.get("Crop_Name"):
        return str(crop_params.get("Crop_Name"))
    if config and config.get("crop_name"):
        return str(config.get("crop_name"))
    return "Unknown crop"


def _is_perennial(crop_params: Dict[str, object] | None) -> bool:
    return str((crop_params or {}).get("Type", "Annual")) == "Perennial"


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def infer_market_context(config: Dict[str, object] | None = None) -> Dict[str, object]:
    """Infer a cautious market context from field coordinates.

    This is not reverse geocoding.  It only gives a sensible default for the main
    current pilot geography.  Manual country/currency inputs remain authoritative.
    """
    config = config or {}
    lat = _safe_float(config.get("center_lat"), 0.0)
    lon = _safe_float(config.get("center_lon"), 0.0)
    if 1.0 <= lat <= 13.5 and 8.0 <= lon <= 17.5:
        return {"country": "Cameroon", "market_region": "Central Africa", "currency": "XAF"}
    return {"country": str(config.get("economics_country") or "Local market"), "market_region": str(config.get("economics_market_region") or "Local region"), "currency": str(config.get("economics_currency") or "XAF")}


def _default_horizon_years(crop_params: Dict[str, object] | None) -> int:
    return 20 if _is_perennial(crop_params) else 1


def _economic_horizon_years(economics: Dict[str, object], crop_params: Dict[str, object] | None = None) -> int:
    """Return the economic horizon, clipped to the simulated perennial window."""
    default = _default_horizon_years(crop_params)
    raw = int(round(_safe_float(economics.get("economic_horizon_years"), default)))
    return max(1, min(20 if _is_perennial(crop_params) else 1, raw))


def default_economics_config(config: Dict[str, object] | None = None, crop_params: Dict[str, object] | None = None) -> Dict[str, object]:
    """Return editable default economic assumptions for the current field."""
    context = infer_market_context(config)
    crop = _crop_name(crop_params, config)
    price = CAMEROON_PRICE_REFERENCES.get(crop, 180000.0 if context["currency"] == "XAF" else 300.0)
    defaults = {
        "enabled": True,
        "currency": context["currency"],
        "country": context["country"],
        "market_region": context["market_region"],
        "commodity_crop": crop,
        "market_level": "farmgate",
        "sale_price_per_t": price,
        "price_source": "automatic regional prior",
        "price_source_detail": "Editable prior from country/crop context; replace with a local buyer, cooperative or market quote when available.",
        "price_confidence": 0.55,
        "last_updated": str(date.today()),
        "economic_horizon_years": _default_horizon_years(crop_params),
        "postharvest_loss_pct": 5.0,
        "risk_discount_pct": 10.0,
        "transport_cost_per_t": 0.0,
        "default_fertilizer_price_per_kg": 520.0,
        "fertilizer_prices": deepcopy(DEFAULT_FERTILIZER_PRICES),
        "irrigation_cost_per_m3": 35.0,
        "energy_cost_per_kwh": 120.0,
        "irrigation_labor_cost_per_event": 2500.0,
        # All labour costs are per workday per hectare.  The cost engine multiplies
        # them by the configured area and by the number of intervention days/events.
        "labor_costs": {
            "scouting_day": 3000.0,
            "fertilizer_application_day": 4000.0,
            "spraying_day": 5000.0,
            "roguing_day": 3500.0,
            "pruning_day": 4500.0,
        },
        "disease_control_costs": {
            "fungicide_per_l": 8000.0,
            "spray_service_per_ha": 6000.0,
            "plant_replacement_cost": 300.0,
        },
        "notes": "",
    }
    crop_defaults = CROP_SPECIFIC_DEFAULTS.get(crop, {})
    for key, value in crop_defaults.items():
        if key in {"labor_costs", "disease_control_costs"} and isinstance(value, dict):
            nested = dict(defaults.get(key, {}))
            nested.update(value)
            defaults[key] = nested
        else:
            defaults[key] = value
    return defaults


def normalize_economics_config(economics: Dict[str, object] | None, config: Dict[str, object] | None = None, crop_params: Dict[str, object] | None = None) -> Dict[str, object]:
    """Merge user economics with current defaults while preserving nested prices."""
    merged = default_economics_config(config, crop_params)
    crop = _crop_name(crop_params, config)
    if isinstance(economics, dict):
        incoming_crop = str(economics.get("commodity_crop", "Unknown crop") or "Unknown crop")
        incoming_source = str(economics.get("price_source", "automatic regional prior") or "automatic regional prior")
        crop_sensitive_keys = {
            "commodity_crop", "sale_price_per_t", "price_source", "price_source_detail",
            "price_confidence", "postharvest_loss_pct", "risk_discount_pct",
            "labor_costs", "disease_control_costs",
        }
        use_current_crop_defaults = (
            crop != "Unknown crop"
            and incoming_crop not in {crop, ""}
            and incoming_source.startswith("automatic")
        )
        for key, value in economics.items():
            if use_current_crop_defaults and key in crop_sensitive_keys:
                continue
            if key in {"fertilizer_prices", "labor_costs", "disease_control_costs"} and isinstance(value, dict):
                nested = dict(merged.get(key, {}))
                nested.update(value)
                merged[key] = nested
            else:
                merged[key] = value
    # A generic default economics_config can be created before crop selection.
    # Once the crop is known, the explicit session/config horizon should win so
    # perennial crops such as cocoa do not remain stuck on a one-year default.
    if config and config.get("economic_horizon_years") not in (None, ""):
        merged["economic_horizon_years"] = config.get("economic_horizon_years")
    elif _is_perennial(crop_params) and str(merged.get("commodity_crop")) in {"Unknown crop", ""}:
        merged["economic_horizon_years"] = _default_horizon_years(crop_params)
    for numeric in ["sale_price_per_t", "price_confidence", "economic_horizon_years", "postharvest_loss_pct", "risk_discount_pct", "transport_cost_per_t", "default_fertilizer_price_per_kg", "irrigation_cost_per_m3", "energy_cost_per_kwh", "irrigation_labor_cost_per_event"]:
        merged[numeric] = _safe_float(merged.get(numeric), default_economics_config(config, crop_params).get(numeric, 0.0))
    merged["economic_horizon_years"] = _economic_horizon_years(merged, crop_params)
    return merged


def auto_update_market_reference(economics: Dict[str, object], config: Dict[str, object] | None = None, crop_params: Dict[str, object] | None = None) -> Dict[str, object]:
    """Refresh editable market defaults from location and crop context.

    The function is intentionally offline and deterministic.  It prepares a good
    starting point for non-expert users and leaves real market/API connectors for a
    later dedicated data-service layer.
    """
    refreshed = normalize_economics_config(economics, config, crop_params)
    context = infer_market_context(config)
    crop = _crop_name(crop_params, config)
    refreshed["country"] = context["country"]
    refreshed["market_region"] = context["market_region"]
    refreshed["currency"] = context["currency"]
    refreshed["commodity_crop"] = crop
    if context["country"] == "Cameroon":
        refreshed["sale_price_per_t"] = CAMEROON_PRICE_REFERENCES.get(crop, refreshed.get("sale_price_per_t", 180000.0))
        refreshed["price_source"] = "automatic Cameroon/Central Africa prior"
        refreshed["price_confidence"] = 0.50 if crop == "Cocoa" else (0.55 if crop in CAMEROON_PRICE_REFERENCES else 0.40)
    else:
        refreshed["price_source"] = "automatic local prior"
        refreshed["price_confidence"] = min(_safe_float(refreshed.get("price_confidence"), 0.45), 0.45)
    if crop == "Cocoa":
        refreshed["price_source_detail"] = CROP_SPECIFIC_DEFAULTS["Cocoa"]["price_source_detail"]
    else:
        refreshed["price_source_detail"] = "Automatic reference is a planning prior; confirm with current farm-gate or cooperative market prices before financial decisions."
    refreshed["last_updated"] = str(date.today())
    return refreshed


def apply_price_source_choice(economics: Dict[str, object], price_source: str, config: Dict[str, object] | None = None, crop_params: Dict[str, object] | None = None) -> Dict[str, object]:
    """Apply the user's selected price source to the editable economics profile.

    Price source is not just a label. Automatic sources refresh the regional prior
    price and confidence. Quote/statistical sources preserve the user's current
    price but update confidence and guidance text so downstream recommendations
    know whether the price is a rough prior or a stronger local observation.
    """
    selected = str(price_source or "manual")
    if selected not in ECONOMIC_PRICE_SOURCE_OPTIONS:
        selected = "manual"
    current = normalize_economics_config(economics, config, crop_params)
    if selected.startswith("automatic"):
        refreshed = auto_update_market_reference(current, config, crop_params)
        # Keep the exact source selected in the UI so the widget remains stable
        # across reruns. The price itself still comes from the location-aware
        # automatic refresh.
        refreshed["price_source"] = selected
        refreshed["last_updated"] = str(date.today())
        return refreshed

    profile = PRICE_SOURCE_PROFILES.get(selected, PRICE_SOURCE_PROFILES["manual"])
    current["price_source"] = selected
    current["price_confidence"] = profile["confidence"]
    current["price_source_detail"] = profile["detail"]
    current["last_updated"] = str(date.today())
    return current


def _schedule_within_horizon(schedule: Iterable[Dict[str, object]], config: Dict[str, object], crop_params: Dict[str, object] | None, horizon_years: int) -> List[Dict[str, object]]:
    """Keep management events that fall inside the chosen economic horizon."""
    events = list(schedule or [])
    if not _is_perennial(crop_params):
        return events
    start = _parse_date(config.get("planting_date"))
    if start is None:
        return events
    cutoff = start + timedelta(days=max(1, horizon_years) * 365)
    kept = []
    for event in events:
        event_date = _parse_date(event.get("date"))
        if event_date is None or event_date < cutoff:
            kept.append(event)
    return kept


def schedule_irrigation_water_m3(schedule: Iterable[Dict[str, object]], area_ha: float) -> float:
    return sum(max(0.0, _safe_float(event.get("amount"), 0.0)) * 10.0 * area_ha for event in schedule or [])


def schedule_fertilizer_kg(schedule: Iterable[Dict[str, object]], area_ha: float) -> float:
    return sum(max(0.0, _safe_float(event.get("amount"), 0.0)) * area_ha for event in schedule or [])


def _labor_cost_per_day_ha(economics: Dict[str, object], key: str, area_ha: float, days: float = 1.0) -> float:
    labor = economics.get("labor_costs", {}) or {}
    return max(0.0, _safe_float(labor.get(key), 0.0)) * max(0.0, area_ha) * max(0.0, days)


def fertilizer_cost(schedule: Iterable[Dict[str, object]], area_ha: float, economics: Dict[str, object]) -> float:
    prices = economics.get("fertilizer_prices", {}) or {}
    default_price = _safe_float(economics.get("default_fertilizer_price_per_kg"), 0.0)
    events = list(schedule or [])
    product_total = 0.0
    for event in events:
        product = str(event.get("product") or "")
        kg = max(0.0, _safe_float(event.get("amount"), 0.0)) * area_ha
        product_total += kg * _safe_float(prices.get(product), default_price)
    # One labour day per fertilization date is a simple, auditable approximation.
    event_days = len({str(event.get("date", idx)) for idx, event in enumerate(events)})
    labour_total = _labor_cost_per_day_ha(economics, "fertilizer_application_day", area_ha, event_days)
    return product_total + labour_total


def irrigation_cost(schedule: Iterable[Dict[str, object]], area_ha: float, economics: Dict[str, object]) -> float:
    events = list(schedule or [])
    water_m3 = schedule_irrigation_water_m3(events, area_ha)
    event_count = len(events)
    return water_m3 * _safe_float(economics.get("irrigation_cost_per_m3"), 0.0) + event_count * _safe_float(economics.get("irrigation_labor_cost_per_event"), 0.0)


def disease_action_cost(config: Dict[str, object], area_ha: float, economics: Dict[str, object], crop_params: Dict[str, object] | None = None) -> float:
    """Estimate disease-management cost from mapped foci and selected disease.

    Labour entries are interpreted as per workday per hectare.  The function does
    not force roguing or pruning: if their default cost is zero, scouting and spray
    service can still be evaluated without pretending that plant removal happened.
    """
    spots = list(config.get("disease_spots", []) or [])
    disease_costs = economics.get("disease_control_costs", {}) or {}
    if not spots and not config.get("selected_disease_id"):
        return 0.0
    scouting = _labor_cost_per_day_ha(economics, "scouting_day", area_ha, 1.0)
    if spots:
        operation_key = "pruning_day" if _is_perennial(crop_params) else "roguing_day"
        operation = _labor_cost_per_day_ha(economics, operation_key, area_ha, 1.0)
    else:
        operation = _labor_cost_per_day_ha(economics, "spraying_day", area_ha, 1.0)
    service = _safe_float(disease_costs.get("spray_service_per_ha"), 0.0) * max(0.0, area_ha) * (0.25 if spots else 1.0)
    # Replacement is charged only when a removal/pruning operation is actually
    # costed.  A disease focus can require scouting or targeted spraying without
    # implying that all marked plants are destroyed.
    replacement = 0.0
    if spots and operation > 0.0:
        replacement = sum(max(0.0, _safe_float(s.get("plants"), 1.0)) for s in spots) * _safe_float(disease_costs.get("plant_replacement_cost"), 0.0)
    return scouting + operation + service + replacement


def annual_harvest_yields_t_ha(history: List[Dict[str, object]], crop_params: Dict[str, object] | None, horizon_years: int) -> List[float]:
    """Return annual harvested yield equivalents in t/ha.

    For annual crops this returns the final yield.  For perennials it groups the
    simulated series by year since simulation start and takes the annual peak of
    the disease-adjusted Yield field.  The simulation resets standing fruit at the
    beginning of each production year, so these peaks approximate repeated harvest
    opportunities over the economic horizon.
    """
    if not history:
        return []
    if not _is_perennial(crop_params):
        final = history[-1]
        return [max(0.0, _safe_float(final.get("Yield", final.get("Fruit_Biomass", 0.0)), 0.0))]
    start = _parse_date(history[0].get("Date"))
    buckets: Dict[int, float] = {}
    for row in history:
        row_date = _parse_date(row.get("Date"))
        if start is None or row_date is None:
            year_index = 1
        else:
            year_index = int(max(0, (row_date - start).days) // 365) + 1
        if year_index < 1 or year_index > horizon_years:
            continue
        yld = max(0.0, _safe_float(row.get("Yield", row.get("Fruit_Biomass", 0.0)), 0.0))
        buckets[year_index] = max(buckets.get(year_index, 0.0), yld)
    return [buckets.get(year, 0.0) for year in range(1, horizon_years + 1)]


def production_tonnes(result: Dict[str, object] | None, config: Dict[str, object], horizon_years: int | None = None) -> float:
    if not result:
        return 0.0
    history = result.get("history", []) or []
    if not history:
        return 0.0
    crop_params = result.get("crop_params", {}) or {}
    economics = normalize_economics_config(config.get("economics_config"), config, crop_params)
    horizon = horizon_years or _economic_horizon_years(economics, crop_params)
    area = max(0.0, _safe_float(config.get("area_ha"), 1.0))
    return max(0.0, sum(annual_harvest_yields_t_ha(history, crop_params, horizon)) * area)


def _scenario_production_tonnes(scenario: Dict[str, object], area_ha: float, crop_params: Dict[str, object], horizon_years: int, fallback_tonnes: float) -> float:
    if not scenario or not scenario.get("available"):
        return fallback_tonnes
    if _is_perennial(crop_params):
        yearly = scenario.get("annual_yields_t_ha") or []
        if yearly:
            return max(0.0, sum(_safe_float(v, 0.0) for v in yearly[:horizon_years]) * area_ha)
        if scenario.get("horizon_yield_t_ha") is not None:
            return max(0.0, _safe_float(scenario.get("horizon_yield_t_ha"), 0.0) * area_ha)
    return max(0.0, _safe_float(scenario.get("final_yield"), 0.0) * area_ha)


def revenue(production_t: float, economics: Dict[str, object]) -> float:
    loss_factor = max(0.0, 1.0 - _safe_float(economics.get("postharvest_loss_pct"), 0.0) / 100.0)
    sale_price = max(0.0, _safe_float(economics.get("sale_price_per_t"), 0.0))
    transport = max(0.0, _safe_float(economics.get("transport_cost_per_t"), 0.0)) * max(0.0, production_t)
    return max(0.0, production_t * sale_price * loss_factor - transport)


def _stress_weights(history: List[Dict[str, object]]) -> Dict[str, float]:
    if not history:
        return {"irrigation": 0.34, "fertilization": 0.33, "disease_control": 0.33}
    water = max(_safe_float(row.get("Avg_Stress"), 0.0) for row in history)
    nutrients = max(max(_safe_float(row.get("Avg_N_Stress"), 0.0), _safe_float(row.get("Avg_P_Stress"), 0.0), _safe_float(row.get("Avg_K_Stress"), 0.0)) for row in history)
    disease = max(_safe_float(row.get("Incidence"), 0.0) for row in history)
    raw = {"irrigation": max(0.05, water), "fertilization": max(0.05, nutrients), "disease_control": max(0.05, disease)}
    total = sum(raw.values()) or 1.0
    return {key: value / total for key, value in raw.items()}


def _action_row(action_type: str, title: str, cost: float, gross_benefit: float, production_gain_t: float, confidence: str, timing: str = "") -> Dict[str, object]:
    net = gross_benefit - cost
    roi = (net / cost) if cost > 0 else (float("inf") if gross_benefit > 0 else 0.0)
    return {
        "type": action_type,
        "title": title,
        "timing": timing,
        "cost": round(cost, 2),
        "gross_benefit": round(gross_benefit, 2),
        "net_benefit": round(net, 2),
        "production_gain_t": round(production_gain_t, 3),
        "roi": round(roi, 2) if roi != float("inf") else 999.0,
        "economically_selected": net >= 0.0,
        "confidence": confidence,
    }


def _summary_per_ha(summary: Dict[str, object], area_ha: float) -> Dict[str, object]:
    """Add per-hectare companions for all monetary and production outputs.

    The recommendation UI now distinguishes total net return from incremental
    gain versus the baseline.  Older keys such as agronomic_net_gain are kept for
    compatibility, but they now carry total net return; explicit *_incremental_*
    keys carry the change versus no action.
    """
    area = max(1e-9, area_ha)
    per_ha_keys = [
        "baseline_production_t", "baseline_revenue", "baseline_cost", "baseline_net_gain", "baseline_net_return",
        "agronomic_production_t", "agronomic_revenue", "agronomic_gross_gain", "agronomic_cost", "agronomic_net_gain", "agronomic_net_return", "agronomic_incremental_net_gain",
        "economic_production_t", "economic_revenue", "economic_gross_gain", "economic_cost", "economic_net_gain", "economic_net_return", "economic_incremental_net_gain",
    ]
    for key in per_ha_keys:
        if key in summary:
            summary[f"{key}_per_ha"] = round(_safe_float(summary.get(key), 0.0) / area, 3 if key.endswith("production_t") else 2)
    return summary


def _candidate(strategy: str, production_t: float, revenue_value: float, cost: float, selected_action_types: Iterable[str]) -> Dict[str, object]:
    """Represent one economically comparable strategy.

    All candidates are evaluated on the same total-net-return basis:
    net return = expected revenue - intervention cost.  This prevents the economic
    optimum from being penalised by a different formula than the agronomic plan.
    """
    return {
        "strategy": strategy,
        "production_t": max(0.0, _safe_float(production_t, 0.0)),
        "revenue": max(0.0, _safe_float(revenue_value, 0.0)),
        "cost": max(0.0, _safe_float(cost, 0.0)),
        "selected_action_types": set(selected_action_types or []),
    }


def _finalize_candidate(candidate: Dict[str, object]) -> Dict[str, object]:
    candidate = dict(candidate)
    candidate["net_return"] = _safe_float(candidate.get("revenue"), 0.0) - _safe_float(candidate.get("cost"), 0.0)
    return candidate


def _best_economic_candidate(candidates: Iterable[Dict[str, object]]) -> Dict[str, object]:
    """Pick the candidate with the highest expected total net return.

    Ties prefer the lower-cost option.  Because the full agronomic plan is one of
    the candidates, the selected economic optimum can never be lower than the
    agronomic optimum under the same expected-value assumptions.
    """
    finalized = [_finalize_candidate(candidate) for candidate in candidates]
    return max(finalized, key=lambda c: (_safe_float(c.get("net_return"), 0.0), -_safe_float(c.get("cost"), 0.0)))


def _retag_actions_for_strategy(actions: List[Dict[str, object]], selected_types: Iterable[str]) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    """Return actions with their final economic keep/drop status.

    Individual action rows keep their own cost/benefit estimates, but the final
    economic decision follows the selected strategy candidate, not a second hidden
    rule in the UI.
    """
    selected_types = set(selected_types or [])
    tagged: List[Dict[str, object]] = []
    selected: List[Dict[str, object]] = []
    for action in actions or []:
        row = dict(action)
        row["economically_selected"] = row.get("type") in selected_types
        tagged.append(row)
        if row["economically_selected"]:
            selected.append(row)
    return tagged, selected


def build_single_field_economics(config: Dict[str, object], result: Dict[str, object], opt_irr_schedule: List[Dict[str, object]] | None = None, opt_fert_schedule: List[Dict[str, object]] | None = None, scenario_summary: Dict[str, object] | None = None) -> Dict[str, object]:
    """Compare no action, agronomic optimum and true economic optimum.

    The economic optimum is not a separate display formula.  It is the candidate
    with the highest expected total net return among no action, the complete
    agronomic plan and the cost-filtered intervention subset.
    """
    crop_params = result.get("crop_params", {}) if result else {}
    economics = normalize_economics_config(config.get("economics_config"), config, crop_params)
    horizon_years = _economic_horizon_years(economics, crop_params)
    area = max(0.0, _safe_float(config.get("area_ha"), 1.0))

    baseline_t = production_tonnes(result, config, horizon_years)
    baseline_revenue = revenue(baseline_t, economics)
    optimized = (scenario_summary or {}).get("optimized", {}) if scenario_summary else {}
    none = (scenario_summary or {}).get("none", {}) if scenario_summary else {}
    if none.get("available"):
        baseline_t = _scenario_production_tonnes(none, area, crop_params, horizon_years, baseline_t)
        baseline_revenue = revenue(baseline_t, economics)

    agronomic_t = _scenario_production_tonnes(optimized, area, crop_params, horizon_years, baseline_t)
    agronomic_revenue = revenue(agronomic_t, economics)
    gross_gain = max(0.0, agronomic_revenue - baseline_revenue)
    production_gain_t = max(0.0, agronomic_t - baseline_t)

    weights = _stress_weights(result.get("history", []) if result else [])
    opt_irr_horizon = _schedule_within_horizon(opt_irr_schedule or [], config, crop_params, horizon_years)
    opt_fert_horizon = _schedule_within_horizon(opt_fert_schedule or [], config, crop_params, horizon_years)
    irr_cost = irrigation_cost(opt_irr_horizon, area, economics)
    fert_cost = fertilizer_cost(opt_fert_horizon, area, economics)
    disease_cost = disease_action_cost(config, area, economics, crop_params)

    actions: List[Dict[str, object]] = []
    if opt_irr_horizon:
        first_date = str((opt_irr_horizon or [{}])[0].get("date", ""))
        actions.append(_action_row("irrigation", "Optimized irrigation calendar", irr_cost, gross_gain * weights["irrigation"], production_gain_t * weights["irrigation"], "medium", first_date))
    if opt_fert_horizon:
        first_date = str((opt_fert_horizon or [{}])[0].get("date", ""))
        actions.append(_action_row("fertilization", "Optimized fertilization calendar", fert_cost, gross_gain * weights["fertilization"], production_gain_t * weights["fertilization"], "medium-high", first_date))
    if config.get("selected_disease_id") or config.get("disease_spots"):
        actions.append(_action_row("disease_control", "Validated disease management", disease_cost, gross_gain * weights["disease_control"], production_gain_t * weights["disease_control"], "field validation required"))

    baseline_cost = 0.0
    baseline_net = baseline_revenue - baseline_cost
    agronomic_cost = irr_cost + fert_cost + disease_cost
    agronomic_net = agronomic_revenue - agronomic_cost

    positive_actions = [action for action in actions if _safe_float(action.get("net_benefit"), 0.0) >= 0.0]
    subset_cost = sum(_safe_float(action.get("cost"), 0.0) for action in positive_actions)
    subset_gross_gain = sum(_safe_float(action.get("gross_benefit"), 0.0) for action in positive_actions)
    subset_gain_t = sum(_safe_float(action.get("production_gain_t"), 0.0) for action in positive_actions)
    subset_revenue = baseline_revenue + max(0.0, subset_gross_gain)
    subset_t = baseline_t + max(0.0, subset_gain_t)
    subset_types = {str(action.get("type")) for action in positive_actions}

    candidates = [
        _candidate("baseline", baseline_t, baseline_revenue, baseline_cost, []),
        _candidate("agronomic_full", agronomic_t, agronomic_revenue, agronomic_cost, [action.get("type") for action in actions]),
        _candidate("positive_action_subset", subset_t, subset_revenue, subset_cost, subset_types),
    ]
    economic = _best_economic_candidate(candidates)
    actions, selected_actions = _retag_actions_for_strategy(actions, economic.get("selected_action_types", set()))

    summary = {
        "area_ha": round(area, 3),
        "economic_horizon_years": horizon_years,
        "baseline_production_t": round(baseline_t, 3),
        "baseline_revenue": round(baseline_revenue, 2),
        "baseline_cost": round(baseline_cost, 2),
        "baseline_net_gain": round(baseline_net, 2),
        "baseline_net_return": round(baseline_net, 2),
        "agronomic_production_t": round(agronomic_t, 3),
        "agronomic_revenue": round(agronomic_revenue, 2),
        "agronomic_gross_gain": round(gross_gain, 2),
        "agronomic_cost": round(agronomic_cost, 2),
        "agronomic_net_gain": round(agronomic_net, 2),
        "agronomic_net_return": round(agronomic_net, 2),
        "agronomic_incremental_net_gain": round(agronomic_net - baseline_net, 2),
        "economic_strategy": economic.get("strategy"),
        "economic_production_t": round(_safe_float(economic.get("production_t"), 0.0), 3),
        "economic_revenue": round(_safe_float(economic.get("revenue"), 0.0), 2),
        "economic_gross_gain": round(max(0.0, _safe_float(economic.get("revenue"), 0.0) - baseline_revenue), 2),
        "economic_cost": round(_safe_float(economic.get("cost"), 0.0), 2),
        "economic_net_gain": round(_safe_float(economic.get("net_return"), 0.0), 2),
        "economic_net_return": round(_safe_float(economic.get("net_return"), 0.0), 2),
        "economic_incremental_net_gain": round(_safe_float(economic.get("net_return"), 0.0) - baseline_net, 2),
        "economic_selected_action_count": len(selected_actions),
        "price_confidence": economics.get("price_confidence", 0.0),
    }
    summary = _summary_per_ha(summary, area)

    return {
        "currency": economics.get("currency", "XAF"),
        "economics": economics,
        "summary": summary,
        "actions": actions,
        "selected_actions": selected_actions,
        "notes": [
            "Economic optimum uses editable prices and costs; verify local market price before investment.",
            "For perennial crops, revenue is summed over the selected economic horizon using annual harvest peaks.",
            "Economic optimum is selected by highest expected total net return among no action, full agronomic management and the profitable action subset.",
        ],
    }


def build_cooperative_economics(config: Dict[str, object], cooperative_result: Dict[str, object], opt_plan: Dict[str, object]) -> Dict[str, object]:
    """Economic comparison for cooperative mode using the same candidate rule."""
    crop_params = cooperative_result.get("crop_params", {}) if cooperative_result else {}
    economics = normalize_economics_config(config.get("economics_config"), config, crop_params)
    horizon_years = _economic_horizon_years(economics, crop_params)
    summary = opt_plan.get("summary", {}) if opt_plan else {}
    area = max(0.0, _safe_float(cooperative_result.get("total_area_ha", config.get("area_ha", 1.0)), 1.0))
    baseline_t = _safe_float(summary.get("baseline_production_t"), production_tonnes(cooperative_result, config, horizon_years))
    gain_t = max(0.0, _safe_float(summary.get("production_gain_t"), 0.0))
    baseline_revenue = revenue(baseline_t, economics)
    agronomic_t = baseline_t + gain_t
    agronomic_revenue = revenue(agronomic_t, economics)
    gross_gain = max(0.0, agronomic_revenue - baseline_revenue)

    water_cost = _safe_float(summary.get("water_m3"), 0.0) * _safe_float(economics.get("irrigation_cost_per_m3"), 0.0)
    fert_cost = _safe_float(summary.get("fertilizer_kg"), 0.0) * _safe_float(economics.get("default_fertilizer_price_per_kg"), 0.0)
    labour_cost = _labor_cost_per_day_ha(economics, "fertilizer_application_day", area, max(1.0, _safe_float(summary.get("optimized_plot_count"), 0.0) * 0.25))

    actions = [
        _action_row("cooperative_irrigation", "Cooperative optimized irrigation", water_cost, gross_gain * 0.40, gain_t * 0.40, "medium"),
        _action_row("cooperative_fertilization", "Cooperative optimized fertilization", fert_cost, gross_gain * 0.45, gain_t * 0.45, "medium-high"),
        _action_row("cooperative_labour", "Shared cooperative implementation", labour_cost, gross_gain * 0.15, gain_t * 0.15, "medium"),
    ]

    baseline_cost = 0.0
    baseline_net = baseline_revenue - baseline_cost
    agronomic_cost = water_cost + fert_cost + labour_cost
    agronomic_net = agronomic_revenue - agronomic_cost

    positive_actions = [action for action in actions if _safe_float(action.get("net_benefit"), 0.0) >= 0.0]
    subset_cost = sum(_safe_float(action.get("cost"), 0.0) for action in positive_actions)
    subset_gross_gain = sum(_safe_float(action.get("gross_benefit"), 0.0) for action in positive_actions)
    subset_gain_t = sum(_safe_float(action.get("production_gain_t"), 0.0) for action in positive_actions)
    subset_revenue = baseline_revenue + max(0.0, subset_gross_gain)
    subset_t = baseline_t + max(0.0, subset_gain_t)
    subset_types = {str(action.get("type")) for action in positive_actions}

    candidates = [
        _candidate("baseline", baseline_t, baseline_revenue, baseline_cost, []),
        _candidate("agronomic_full", agronomic_t, agronomic_revenue, agronomic_cost, [action.get("type") for action in actions]),
        _candidate("positive_action_subset", subset_t, subset_revenue, subset_cost, subset_types),
    ]
    economic = _best_economic_candidate(candidates)
    actions, selected_actions = _retag_actions_for_strategy(actions, economic.get("selected_action_types", set()))

    econ_summary = {
        "area_ha": round(area, 3),
        "economic_horizon_years": horizon_years,
        "baseline_production_t": round(baseline_t, 3),
        "baseline_revenue": round(baseline_revenue, 2),
        "baseline_cost": round(baseline_cost, 2),
        "baseline_net_gain": round(baseline_net, 2),
        "baseline_net_return": round(baseline_net, 2),
        "agronomic_production_t": round(agronomic_t, 3),
        "agronomic_revenue": round(agronomic_revenue, 2),
        "agronomic_gross_gain": round(gross_gain, 2),
        "agronomic_cost": round(agronomic_cost, 2),
        "agronomic_net_gain": round(agronomic_net, 2),
        "agronomic_net_return": round(agronomic_net, 2),
        "agronomic_incremental_net_gain": round(agronomic_net - baseline_net, 2),
        "economic_strategy": economic.get("strategy"),
        "economic_production_t": round(_safe_float(economic.get("production_t"), 0.0), 3),
        "economic_revenue": round(_safe_float(economic.get("revenue"), 0.0), 2),
        "economic_gross_gain": round(max(0.0, _safe_float(economic.get("revenue"), 0.0) - baseline_revenue), 2),
        "economic_cost": round(_safe_float(economic.get("cost"), 0.0), 2),
        "economic_net_gain": round(_safe_float(economic.get("net_return"), 0.0), 2),
        "economic_net_return": round(_safe_float(economic.get("net_return"), 0.0), 2),
        "economic_incremental_net_gain": round(_safe_float(economic.get("net_return"), 0.0) - baseline_net, 2),
        "economic_selected_action_count": len(selected_actions),
        "price_confidence": economics.get("price_confidence", 0.0),
    }
    econ_summary = _summary_per_ha(econ_summary, area)

    return {
        "currency": economics.get("currency", "XAF"),
        "economics": economics,
        "summary": econ_summary,
        "actions": actions,
        "selected_actions": selected_actions,
        "notes": [
            "Cooperative economic optimum uses the same total-net-return rule as single-field mode.",
            "Use parcel-level prices and labour records for stronger cooperative financial planning.",
        ],
    }
