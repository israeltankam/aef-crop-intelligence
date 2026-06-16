# src/models/growth_model_selector.py
"""
Scientific growth-model selector.

The selector chooses the most defensible scientific model family for the current
use case, while making the runtime status explicit.  At this stage the deployed
engine remains AEF-lite: a lightweight internal surrogate inspired by the chosen
model family.  This prevents the UI and report from overclaiming that full
STICS, AquaCrop, APSIM, CROPWAT or DSSAT adapters are already running.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass
class GrowthModelChoice:
    """Small serialisable record stored in simulation outputs and reports."""

    model_id: str
    label: str
    role: str
    confidence: float
    reason: str
    requirements: List[str]
    fallback_used: bool = False
    adapter_status: str = "native_or_external"
    scientific_caveat: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class GrowthModelSelector:
    """Select the scientific family from crop type, objective, and data quality."""

    def select(self, config: Dict[str, object], crop: Dict[str, object]) -> GrowthModelChoice:
        crop_type = str(crop.get("Type", "Annual"))
        crop_name = str(crop.get("Crop_Name", "")).lower()
        objective = str(config.get("decision_objective", "balanced")).lower()
        soil_source = str(config.get("soil_data_source", "manual" if config.get("use_expert_soil") else "auto"))
        has_manual_soil = soil_source == "manual" or bool(config.get("use_expert_soil"))

        # Soil entered by an expert is treated as high confidence.  Auto soil is
        # retained for non-experts, but it lowers confidence because gridded soil
        # products are coarser than field or laboratory measurements.
        data_quality = 0.92 if has_manual_soil else 0.76

        if "irrig" in objective or "water" in objective:
            return GrowthModelChoice(
                model_id="aquacrop_cropwat_family",
                label="AEF-lite water surrogate (AquaCrop/CROPWAT decision family)",
                role="Water-limited growth and irrigation scheduling, using internal lightweight equations",
                confidence=0.86 * data_quality,
                reason="The decision target is dominated by water stress and irrigation timing.",
                requirements=["daily weather", "soil water holding capacity", "crop calendar", "management schedule"],
                fallback_used=True,
                adapter_status="surrogate_internal",
                scientific_caveat="AquaCrop/CROPWAT are selected as the scientific decision family, but the deployed runtime uses AEF-lite until external adapters are installed.",
            )

        if crop_type == "Perennial":
            return GrowthModelChoice(
                model_id="stics_apsim_perennial_family",
                label="AEF-lite perennial surrogate (STICS/APSIM decision family)",
                role="Long-horizon perennial growth, pruning, water and nutrient stress, using internal lightweight equations",
                confidence=0.82 * data_quality,
                reason="Perennial crops require age structure, pruning response, dormancy/low-pressure seasons, and long-term soil feedbacks.",
                requirements=["tree age", "pruning schedule", "daily weather", "soil profile", "phenological calendar"],
                fallback_used=True,
                adapter_status="surrogate_internal",
                scientific_caveat="STICS/APSIM are selected as the scientific decision family, but the deployed runtime uses AEF-lite until external adapters and local cultivar calibration are available.",
            )

        if crop_name in {"maize", "wheat", "rice", "soybean", "cotton", "cassava"}:
            return GrowthModelChoice(
                model_id="dssat_apsim_annual_family",
                label="AEF-lite annual surrogate (DSSAT/APSIM decision family)",
                role="Annual crop yield, water, nitrogen and management scenarios, using internal lightweight equations",
                confidence=0.88 * data_quality,
                reason="The crop is covered by well-used annual-crop modelling families with calibration workflows.",
                requirements=["cultivar parameters", "soil profile", "daily weather", "planting date", "fertilization and irrigation"],
                fallback_used=True,
                adapter_status="surrogate_internal",
                scientific_caveat="DSSAT/APSIM are selected as the scientific decision family, but the deployed runtime uses AEF-lite until full model adapters are installed.",
            )

        return GrowthModelChoice(
            model_id="aef_lite_fallback",
            label="AEF-lite fallback",
            role="Last-resort internal approximation when no validated adapter is available",
            confidence=0.45 * data_quality,
            reason="No validated adapter was selected for this crop and objective.",
            requirements=["basic crop parameters", "weather", "soil water capacity"],
            fallback_used=True,
            adapter_status="surrogate_internal",
            scientific_caveat="No validated external adapter is active; this is a last-resort internal approximation.",
        )
