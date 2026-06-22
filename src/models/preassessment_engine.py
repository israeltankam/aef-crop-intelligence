# src/models/preassessment_engine.py
"""Pre-planting suitability assessment for AEF Crop Intelligence.

The pre-assessment mode answers a different question from the operational digital
 twin: "Should I plant this crop variety here, and if yes, when and with which
initial irrigation/fertilization plan?"  It therefore uses a one-cycle forecast,
transparent component scores, and literature-prior disease pressure instead of
observed disease foci.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import math

import pandas as pd

from src.models.weather_service import WeatherService


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "disease_pressure_literature.csv"


@dataclass
class ComponentScore:
    """Small explainable score block used in the PDF and UI."""

    name: str
    score: float
    weight: float
    explanation: str

    def to_dict(self) -> Dict[str, object]:
        return {"name": self.name, "score": round(self.score, 1), "weight": self.weight, "explanation": self.explanation}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _parse_date(value, default=None):
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return default or date.today()


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(value)))


def _normalize_temperature_series(tmin: pd.Series, tmax: pd.Series) -> Tuple[pd.Series, pd.Series, str]:
    """Normalize weather temperatures to Celsius before scoring.

    AEF can receive climate data from Earth Engine, Open-Meteo, or fallbacks.
    Most sources are Celsius after conversion, but raw Kelvin or occasional
    tenths-of-degree values can leak through.  This guard prevents impossible
    displays such as 274 C and, more importantly, prevents a wrong climate score.
    """
    tmin = pd.to_numeric(tmin, errors='coerce')
    tmax = pd.to_numeric(tmax, errors='coerce')
    combined = pd.concat([tmin, tmax]).dropna()
    if combined.empty:
        return tmin, tmax, 'unknown'
    median_value = float(combined.median())
    spread = float((tmax.median() - tmin.median())) if not tmax.dropna().empty and not tmin.dropna().empty else 0.0
    if median_value > 180.0:
        # Kelvin has realistic daily spreads in the original unit; tenths of a
        # degree usually show very large TMAX-TMIN spreads.
        if spread > 35.0:
            return tmin / 10.0, tmax / 10.0, 'tenths_celsius'
        return tmin - 273.15, tmax - 273.15, 'kelvin'
    if median_value > 70.0:
        return tmin / 10.0, tmax / 10.0, 'tenths_celsius'
    return tmin, tmax, 'celsius'


def _month_starts(start: date, count: int = 12) -> List[date]:
    """Return candidate planting dates spaced monthly from the user's window."""
    dates = []
    y, m = start.year, start.month
    for i in range(count):
        mm = m + i
        yy = y + (mm - 1) // 12
        mon = ((mm - 1) % 12) + 1
        day = min(start.day, 28)
        dates.append(date(yy, mon, day))
    return dates


def _infer_region(lat: float, lon: float) -> str:
    """Very light regional label used only for reporting disease priors."""
    if lat < -35 or lat > 25:
        return "Outside core Sub-Saharan Africa prior"
    if lon < -5:
        return "West Africa"
    if lon < 12:
        return "West/Central Africa"
    if lon < 30:
        return "Central Africa"
    if lon < 45:
        return "East Africa"
    return "Southern/Eastern Africa"


def _soil_texture_score(soil_type: str) -> Tuple[float, str]:
    texture = str(soil_type or "loam").lower()
    if any(k in texture for k in ["loam", "silt loam", "clay loam"]):
        return 86.0, "Balanced texture for water and nutrient retention."
    if "sand" in texture:
        return 58.0, "Sandy texture can drain quickly; irrigation and organic matter management become more important."
    if "clay" in texture:
        return 68.0, "Clay-rich texture can store water but may create aeration or drainage constraints."
    return 70.0, "Texture suitability is estimated from a generic soil prior."


def _weather_slice(weather: pd.DataFrame, start: date, days: int) -> pd.DataFrame:
    if weather is None or weather.empty:
        return pd.DataFrame()
    df = weather.copy()
    df["DATE"] = pd.to_datetime(df["DATE"]).dt.date
    if "TMIN" in df.columns and "TMAX" in df.columns:
        df["TMIN"], df["TMAX"], temp_unit = _normalize_temperature_series(df["TMIN"], df["TMAX"])
        df["TEMP_UNIT_NORMALIZED_FROM"] = temp_unit
    end = start + timedelta(days=days)
    return df[(df["DATE"] >= start) & (df["DATE"] < end)].copy()


def _daily_reference_et_mm(row) -> float:
    """Small Hargreaves-like ET proxy from existing weather columns.

    We avoid adding a dependency for Penman-Monteith.  This is a suitability-mode
    approximation, not a final irrigation design.  The resulting calendars are
    practical starting plans that should be refined after planting.
    """
    tmin = _safe_float(row.get("TMIN"), 20.0)
    tmax = _safe_float(row.get("TMAX"), 30.0)
    rad = _safe_float(row.get("RADIATION"), 18.0)
    return max(1.5, min(8.5, 0.0023 * (0.5 * (tmin + tmax) + 17.8) * math.sqrt(max(0.1, tmax - tmin)) * max(5.0, rad)))


class PreAssessmentEngine:
    """One-cycle pre-planting assessment engine.

    The engine is deliberately transparent.  It does not claim to certify a
    site; it ranks plausible planting windows with a documented screening
    score so the user can decide whether the project deserves investment,
    field scouting, and laboratory soil confirmation.
    """

    def __init__(self):
        self.weather_service = WeatherService()

    def load_disease_pressure(self) -> pd.DataFrame:
        # The disease-pressure table is a literature-prior layer, not an
        # observation layer.  It gives the pre-planting mode a cautious
        # regional baseline before any real disease scouting exists.
        if DATA_PATH.exists():
            return pd.read_csv(DATA_PATH)
        return pd.DataFrame()

    def _water_and_climate_scores(self, crop: Dict[str, object], weather: pd.DataFrame) -> Dict[str, float]:
        # This block compares the forecast growing window with crop thermal
        # limits and an ET/rainfall water balance.  It is intentionally light:
        # pre-evaluation must stay fast and explainable, then detailed
        # operational modelling can take over after planting.
        if weather is None or weather.empty:
            return {"climate_score": 45.0, "water_score": 45.0, "rain_mm": 0.0, "et_mm": 0.0, "deficit_mm": 0.0, "mean_temp": 0.0}
        tbase = _safe_float(crop.get("T_Base"), 10.0)
        topt = _safe_float(crop.get("T_Opt"), 28.0)
        tmax = _safe_float(crop.get("T_Max"), 38.0)
        kc = _safe_float(crop.get("Kc_Mid"), 1.05)
        tmin_series, tmax_series, _ = _normalize_temperature_series(weather["TMIN"], weather["TMAX"])
        tmean = ((tmin_series.astype(float) + tmax_series.astype(float)) / 2.0).mean()
        heat_bad_days = int((((tmax_series.astype(float) > tmax) | (tmin_series.astype(float) < tbase))).sum())
        # Penalize mean temperature away from the crop optimum and days beyond
        # the documented crop thermal envelope.  The caps prevent one noisy
        # weather feature from erasing all other evidence.
        temp_score = 100.0 - min(65.0, abs(tmean - topt) * 7.0) - min(25.0, heat_bad_days / max(1, len(weather)) * 100.0)
        et = sum(_daily_reference_et_mm(row) * kc for _, row in weather.iterrows())
        rain = float(weather["RAIN"].astype(float).sum())
        deficit = max(0.0, et - rain)
        excess = max(0.0, rain - et * 1.35)
        # Both drought deficit and strong excess rainfall matter.  Deficit is
        # weighted more because irrigation can be planned explicitly, while
        # waterlogging/drainage risk remains harder to correct after planting.
        water_score = 100.0 - min(70.0, deficit / max(1.0, et) * 100.0) - min(25.0, excess / max(1.0, et) * 35.0)
        climate_score = _clamp(0.65 * temp_score + 0.35 * water_score)
        return {
            "climate_score": round(climate_score, 1),
            "water_score": round(_clamp(water_score), 1),
            "rain_mm": round(rain, 1),
            "et_mm": round(et, 1),
            "deficit_mm": round(deficit, 1),
            "mean_temp": round(float(tmean), 1),
        }

    def _soil_score(self, config: Dict[str, object], crop: Dict[str, object]) -> Dict[str, object]:
        # Soil information may come from manual entry or automatic detection.
        # The confidence term keeps automatic soil estimates useful for novice
        # users without pretending they are equivalent to a laboratory test.
        texture_score, texture_note = _soil_texture_score(config.get("soil_type", "loam"))
        n_req = _safe_float(crop.get("Critical_Soil_N_kg_ha"), 100.0)
        n = _safe_float(config.get("initial_nitrogen"), 10.0)
        p = _safe_float(config.get("initial_phosphorus"), 20.0)
        k = _safe_float(config.get("initial_potassium"), 100.0)
        # Nutrients are screened against broad agronomic thresholds.  The goal
        # is to identify obvious constraints and plan a starting calendar, not
        # to replace crop- and soil-specific fertilizer trials.
        nutrient_score = _clamp((min(1.0, n / max(1.0, n_req)) * 45.0) + (min(1.0, p / 25.0) * 25.0) + (min(1.0, k / 120.0) * 30.0))
        confidence = _safe_float(config.get("soil_confidence"), 0.65)
        score = _clamp(0.45 * texture_score + 0.45 * nutrient_score + 10.0 * confidence)
        return {
            "score": round(score, 1),
            "texture_note": texture_note,
            "nutrient_score": round(nutrient_score, 1),
            "soil_confidence": round(confidence, 2),
            "n_gap": round(max(0.0, n_req - n), 1),
        }

    def _disease_pressure(self, crop: Dict[str, object], diseases: pd.DataFrame, cycle_weather: pd.DataFrame, region: str) -> Dict[str, object]:
        # Before planting, AEF has no local lesion map or confirmed pathogen.
        # This function therefore starts from published regional pressure and
        # adjusts it with forecast humidity, rainfall frequency, temperature,
        # and the variety resistance score when available.
        crop_name = str(crop.get("Crop_Name", ""))
        pressure = self.load_disease_pressure()
        if pressure.empty:
            return {"score": 65.0, "mean_risk": 0.35, "top_risks": [], "region": region}
        subset = pressure[pressure["Target_Crop_Name"].astype(str).str.lower() == crop_name.lower()].copy()
        if subset.empty:
            return {"score": 72.0, "mean_risk": 0.28, "top_risks": [], "region": region}
        if cycle_weather is None or cycle_weather.empty:
            humidity = 65.0
            rain_days = 0.25
            mean_temp = _safe_float(crop.get("T_Opt"), 28.0)
        else:
            humidity = float(cycle_weather.get("HUMIDITY", pd.Series([65])).astype(float).mean())
            rain_days = float((cycle_weather["RAIN"].astype(float) > 1.0).mean())
            tmin_series, tmax_series, _ = _normalize_temperature_series(cycle_weather["TMIN"], cycle_weather["TMAX"])
            mean_temp = float(((tmin_series.astype(float) + tmax_series.astype(float)) / 2.0).mean())
        # Higher Resistance_Score values in the existing crop table are treated
        # as a susceptibility proxy here because many legacy CSV entries used a
        # generic vigour/resistance multiplier.  This keeps behaviour stable
        # until variety-specific disease resistance traits are fully curated.
        susceptibility = _safe_float(crop.get("Resistance_Score"), 0.55)
        risks = []
        for _, row in subset.iterrows():
            base = _safe_float(row.get("Baseline_Pressure_0_1"), 0.45)
            humid_boost = 1.0 + max(0.0, humidity - 70.0) / 100.0 + rain_days * 0.35
            opt_temp = _safe_float(row.get("Opt_Temp"), mean_temp)
            temp_factor = max(0.70, 1.0 - abs(mean_temp - opt_temp) / 18.0)
            # The risk is bounded away from 0 and 1.  This is essential for a
            # prudent diagnostic tool: unknown future epidemics must never be
            # presented as impossible or certain before field surveillance.
            risk = max(0.02, min(0.95, base * humid_boost * temp_factor * (0.70 + susceptibility * 0.60)))
            risks.append({
                "disease_id": row.get("Disease_ID"),
                "disease_name": row.get("Disease_Name"),
                "risk": round(risk, 2),
                "baseline_pressure": base,
                "region_scope": row.get("Countries_or_Zones", "Sub-Saharan Africa"),
                "peak_season": row.get("Peak_Season", "humid periods"),
                "evidence_level": row.get("Evidence_Level", "medium-low"),
                "source": row.get("Literature_Source", "literature prior"),
            })
        risks.sort(key=lambda x: x["risk"], reverse=True)
        mean_risk = sum(r["risk"] for r in risks[:3]) / max(1, min(3, len(risks)))
        return {"score": round(_clamp(100.0 - mean_risk * 100.0), 1), "mean_risk": round(mean_risk, 2), "top_risks": risks[:5], "region": region}

    def _irrigation_calendar(self, best_date: date, weather: pd.DataFrame, crop: Dict[str, object], area_ha: float) -> List[Dict[str, object]]:
        # Calendar events are generated only when accumulated deficit becomes
        # operationally meaningful.  This avoids daily micro-irrigation advice
        # that would be precise-looking but difficult for most farms to follow.
        kc = _safe_float(crop.get("Kc_Mid"), 1.05)
        events = []
        accumulated = 0.0
        for _, row in weather.iterrows():
            et = _daily_reference_et_mm(row) * kc
            rain = _safe_float(row.get("RAIN"), 0.0)
            accumulated = max(0.0, accumulated + et - rain)
            if accumulated >= 35.0:
                # Cap each event to a practical field application range.  Very
                # large deficits are better handled as repeated events after
                # checking pump capacity, soil infiltration, and labour access.
                amount = round(min(45.0, max(18.0, accumulated)), 1)
                events.append({
                    "date": pd.to_datetime(row.get("DATE")).date().isoformat(),
                    "amount_mm": amount,
                    "water_volume_m3": round(amount * area_ha * 10.0, 1),
                    "reason": "Pre-planting forecasted soil-water deficit refill",
                })
                accumulated = 0.0
            if len(events) >= 12:
                break
        return events

    def _fertilization_calendar(self, best_date: date, crop: Dict[str, object], config: Dict[str, object], area_ha: float) -> List[Dict[str, object]]:
        # The default plan uses a common blended fertilizer as a readable proxy.
        # Expert users can translate the same nutrient gaps into local products
        # later; the PDF exposes rates per hectare and totals for that reason.
        n_req = _safe_float(crop.get("Critical_Soil_N_kg_ha"), 100.0)
        n_gap = max(0.0, n_req - _safe_float(config.get("initial_nitrogen"), 10.0))
        p_gap = max(0.0, 25.0 - _safe_float(config.get("initial_phosphorus"), 20.0))
        k_gap = max(0.0, 120.0 - _safe_float(config.get("initial_potassium"), 100.0))
        total_npk = max(0.0, n_gap / 0.15) if n_gap else 0.0
        if p_gap > 0:
            total_npk = max(total_npk, p_gap / 0.15)
        if k_gap > 0:
            total_npk = max(total_npk, k_gap / 0.15)
        if total_npk <= 0:
            return [{"date": best_date.isoformat(), "product": "No basal fertilizer required from current priors", "rate_kg_ha": 0.0, "total_kg": 0.0, "rationale": "Initial nutrients are above the screening thresholds; verify with a soil test."}]
        # Split applications reduce early loss risk and make the advice easier
        # to adapt after emergence.  The late split is skipped for short cycles.
        splits = [(0, 0.45, "Basal placement before/at planting"), (35, 0.35, "Early vegetative top-dress"), (70, 0.20, "Demand-based correction if crop remains vigorous")]
        cycle_days = int(_safe_float(crop.get("Cycle_Days"), 120))
        events = []
        for offset, frac, rationale in splits:
            if offset > cycle_days * 0.75:
                continue
            rate = round(total_npk * frac, 1)
            events.append({"date": (best_date + timedelta(days=offset)).isoformat(), "product": "NPK 15-15-15 or locally equivalent blend", "rate_kg_ha": rate, "total_kg": round(rate * area_ha, 1), "rationale": rationale})
        return events

    def evaluate(self, config: Dict[str, object], crop: Dict[str, object], diseases: pd.DataFrame | None = None) -> Dict[str, object]:
        # Public entry point used by the Streamlit page.  It evaluates several
        # plausible monthly planting starts and returns the best one with all
        # intermediate evidence so the user can audit the recommendation.
        lat = _safe_float(config.get("center_lat"), 4.0)
        lon = _safe_float(config.get("center_lon"), 11.0)
        area_ha = max(0.05, _safe_float(config.get("area_ha"), 1.0))
        cycle_days = int(max(60, _safe_float(crop.get("Cycle_Days"), 120)))
        if str(crop.get("Type", "Annual")) == "Perennial":
            # For perennials, pre-evaluation is limited to one establishment or
            # production cycle as requested.  Long-horizon economics remain in
            # the operational recommendation/report modules after planting.
            cycle_days = min(cycle_days, 365)
        window_start = _parse_date(config.get("preassessment_window_start"), date.today() + timedelta(days=14))
        candidate_dates = _month_starts(window_start, 12)
        total_days = max(365 + cycle_days + 45, 430)
        weather = self.weather_service.get_weather_projections(lat, lon, window_start, total_days)
        region = _infer_region(lat, lon)

        soil = self._soil_score(config, crop)
        candidates = []
        for planting_date in candidate_dates:
            # Each candidate is scored independently over the same biological
            # cycle length, which lets the user compare calendar timing rather
            # than mixing timing with different forecast horizons.
            cycle_weather = _weather_slice(weather, planting_date, cycle_days)
            climate_water = self._water_and_climate_scores(crop, cycle_weather)
            disease = self._disease_pressure(crop, diseases if diseases is not None else pd.DataFrame(), cycle_weather, region)
            # Planting-window score favours lower early-cycle water deficit and avoids
            # heavy disease pressure at establishment.
            establishment = _weather_slice(weather, planting_date, min(45, cycle_days))
            early = self._water_and_climate_scores(crop, establishment)
            planting_score = _clamp(0.65 * early["climate_score"] + 0.35 * disease["score"])
            # Data confidence is explicit in the final score.  A field with
            # automatic soil priors and weak climate availability should be
            # recommended more cautiously even if the raw agronomy looks good.
            data_quality = _clamp(55.0 + soil["soil_confidence"] * 25.0 + (20.0 if weather is not None and not weather.empty else 0.0))
            components = [
                ComponentScore("Climate fit", climate_water["climate_score"], 0.25, f"Mean temperature {climate_water['mean_temp']} °C versus crop optimum {_safe_float(crop.get('T_Opt'), 28.0):.1f} °C."),
                ComponentScore("Water feasibility", climate_water["water_score"], 0.20, f"Forecast rain {climate_water['rain_mm']} mm; estimated crop water demand {climate_water['et_mm']} mm; deficit {climate_water['deficit_mm']} mm."),
                ComponentScore("Soil and nutrients", soil["score"], 0.20, soil["texture_note"]),
                ComponentScore("Disease pressure", disease["score"], 0.20, f"Regional literature prior adjusted by forecast humidity/rainfall; top risk {disease['top_risks'][0]['disease_name'] if disease['top_risks'] else 'not specified'}."),
                ComponentScore("Planting window", planting_score, 0.10, "Early-cycle climate and disease pressure around establishment."),
                ComponentScore("Data confidence", data_quality, 0.05, "Higher when soil confidence and climate data availability are stronger."),
            ]
            total = sum(c.score * c.weight for c in components)
            candidates.append({
                "planting_date": planting_date.isoformat(),
                "score": round(total, 1),
                "components": [c.to_dict() for c in components],
                "climate_water": climate_water,
                "disease": disease,
            })
        candidates.sort(key=lambda x: x["score"], reverse=True)
        best = candidates[0]
        best_date = _parse_date(best["planting_date"])
        best_weather = _weather_slice(weather, best_date, cycle_days)
        # Calendars are generated only for the selected window.  The runner
        # still returns all candidate scores so the UI/PDF can explain why this
        # window was preferred over the alternatives.
        irrigation = self._irrigation_calendar(best_date, best_weather, crop, area_ha)
        fertilization = self._fertilization_calendar(best_date, crop, config, area_ha)
        recommendation = "plant" if best["score"] >= 70 else ("plant_with_caution" if best["score"] >= 55 else "do_not_prioritize")
        return {
            "mode": "preassessment",
            "field_name": config.get("field_name", "Pre-assessment field"),
            "area_ha": round(area_ha, 3),
            "lat": lat,
            "lon": lon,
            "region": region,
            "crop": dict(crop),
            "cycle_days_assessed": cycle_days,
            "perennial_one_cycle_only": str(crop.get("Type", "Annual")) == "Perennial",
            "candidate_dates": candidates,
            "best": best,
            "recommendation": recommendation,
            "irrigation_calendar": irrigation,
            "fertilization_calendar": fertilization,
            "disease_risks": best["disease"]["top_risks"],
            "soil_summary": soil,
            "generated_at": date.today().isoformat(),
            "caution": "Pre-assessment is a planning aid before planting; confirm soil tests, local disease surveillance and input availability before investment.",
        }
