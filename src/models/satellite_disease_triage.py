# src/models/satellite_disease_triage.py
"""
Lightweight satellite disease triage.

Sentinel-2 canopy anomalies rarely identify a pathogen by themselves.  This
module therefore ranks plausible diseases instead of pretending certainty.  The
score combines crop compatibility, season, spectral pattern and disease family.
It is intentionally light: no large ML model is loaded at app startup.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List

import pandas as pd


@dataclass
class DiseaseCandidate:
    disease_id: str
    disease_name: str
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class SatelliteDiseaseTriage:
    """Rank likely diseases from an uncertain canopy anomaly."""

    def rank_candidates(self, crop_name: str, diseases_df: pd.DataFrame, detection_date, spectral_signature: Dict[str, float] | None = None) -> List[DiseaseCandidate]:
        if diseases_df is None or diseases_df.empty:
            return []
        rel = diseases_df[diseases_df["Target_Crop_Name"].astype(str).str.lower() == str(crop_name).lower()].copy()
        if rel.empty:
            return []

        month = pd.to_datetime(detection_date).month if detection_date is not None else 6
        signature = spectral_signature or {}
        wet_thin_canopy = signature.get("wet_thin_canopy", 0.5)
        candidates: List[DiseaseCandidate] = []

        for _, row in rel.iterrows():
            dtype = str(row.get("Type", "")).lower()
            vector = str(row.get("Vector_Type", "")).lower()
            score = 0.35  # crop match already established
            reasons = ["crop-compatible"]

            if "fungal" in dtype or "bacterial" in dtype:
                score += 0.20 * wet_thin_canopy
                reasons.append("wet/thin canopy signature fits fungal or bacterial stress")
            if any(v in vector for v in ["whitefly", "leafhopper", "aphid", "mealybug", "thrip"]):
                score += 0.10
                reasons.append("vector-borne disease remains plausible from canopy anomaly")
            if month in [3, 4, 5, 9, 10, 11]:
                score += 0.10
                reasons.append("season often coincides with humid transition periods")
            if float(row.get("Opt_Humidity", 0) or 0) >= 80:
                score += 0.08 * wet_thin_canopy
                reasons.append("high-humidity pathogen profile")

            score = max(0.05, min(0.95, score))
            candidates.append(
                DiseaseCandidate(
                    disease_id=str(row["Disease_ID"]),
                    disease_name=str(row["Disease_Name"]),
                    confidence=round(score, 3),
                    reason="; ".join(reasons),
                )
            )

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates[:3]
