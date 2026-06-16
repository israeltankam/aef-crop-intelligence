# src/models/adaptive_calibration.py
"""
Lightweight adaptive calibration helpers.

The full research target is a hierarchical Bayesian state-space model with
particle MCMC.  That is too heavy for every Streamlit click, so this module
provides a light operational layer: it summarises uncertainty and recommends the
next useful field measurement.  Heavy PMMH/Particle Gibbs can later run as an
optional pilot/validation job using the same state variables.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, Iterable, List

import pandas as pd


@dataclass
class MeasurementAdvice:
    date: str
    measurement_type: str
    reason: str
    expected_value: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "date": self.date,
            "measurement_type": self.measurement_type,
            "reason": self.reason,
            "expected_value": self.expected_value,
        }


class ActiveLearningAdvisor:
    """Choose the next measurement with a simple information-gain proxy."""

    def suggest_next_measurement(self, history: Iterable[Dict[str, object]], observations: List[Dict[str, object]]) -> MeasurementAdvice | None:
        df = pd.DataFrame(list(history))
        if df.empty or "Date" not in df:
            return None
        df["Date"] = pd.to_datetime(df["Date"])

        # Candidate 1: disease acceleration.  Disease observations are most
        # valuable near the steep part of the curve, where beta and control
        # efficacy are easiest to identify.
        if "Incidence" in df:
            incidence = df["Incidence"].astype(float)
            slope = incidence.diff().abs().fillna(0.0)
            idx = int(slope.idxmax()) if not slope.empty else int(df.index[-1])
            if incidence.iloc[idx] > 0.01:
                d = df.loc[idx, "Date"].date() + timedelta(days=3)
                return MeasurementAdvice(str(d), "Disease Incidence (%)", "Disease is changing quickly; one field check will reduce spread-rate uncertainty.", float(incidence.iloc[idx] * 100.0))

        # Candidate 2: nutrient stress peak.  Soil tests around the peak help
        # separate true nutrient limitation from model parameter error.
        nutrient_cols = [c for c in ["Avg_N_Stress", "Avg_P_Stress", "Avg_K_Stress"] if c in df]
        if nutrient_cols:
            stress = df[nutrient_cols].max(axis=1)
            idx = int(stress.idxmax())
            if stress.iloc[idx] > 0.25:
                return MeasurementAdvice(str(df.loc[idx, "Date"].date()), "Soil N (mg/kg)", "Nutrient stress is high; a soil measurement will improve fertilizer calibration.", float(stress.iloc[idx]))

        # Candidate 3: yield/biomass near the end of the season or annual cycle.
        idx = int(df.index[-1])
        metric = "Yield (t/ha)" if "Yield" in df else "Biomass (t/ha)"
        value = float(df.loc[idx, "Yield"] if metric.startswith("Yield") else df.loc[idx, "Biomass"])
        return MeasurementAdvice(str(df.loc[idx, "Date"].date()), metric, "End-of-cycle production data anchors the whole simulation.", value)
