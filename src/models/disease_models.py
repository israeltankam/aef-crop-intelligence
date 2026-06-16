# src/models/disease_models.py
"""
Disease model families for AEF Crop Intelligence.

The previous implementation used one cumulative reaction-diffusion-like grid.
That was too aggressive for perennial crops and too concentric for real disease
spread.  This module keeps the grid output expected by the dashboard, but it
moves the epidemiology into a specialised stochastic tau-leaping engine.

Design choices:
- families are selected from pathogen type and vector information;
- latent/infectious/resolved pressure are separated internally;
- stochastic long-distance jumps avoid perfect circular fronts;
- interventions are modelled only as counterfactual scenarios for the dossier;
- all defaults are conservative placeholders to be reviewed against literature
  and disease-specific CSV parameters during pilot validation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd
from scipy.signal import convolve2d


@dataclass
class DiseaseModelChoice:
    family: str
    model_name: str
    evidence_level: str
    assumptions: str
    params: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class DiseaseModelSelector:
    """Choose a disease model family from the disease CSV row."""

    def select(self, disease_row: Optional[object], crop: Dict[str, object], config: Dict[str, object]) -> DiseaseModelChoice:
        if disease_row is None:
            return DiseaseModelChoice(
                family="none",
                model_name="No active disease model",
                evidence_level="not_applicable",
                assumptions="No disease target was selected.",
                params={},
            )

        row = self._as_dict(disease_row)
        dtype = str(row.get("Type", "Unknown")).lower()
        vector = str(row.get("Vector_Type", "")).lower()
        is_perennial = str(crop.get("Type", "Annual")) == "Perennial"

        base_beta = float(row.get("Beta_Infection", 0.0) or 0.0) * float(crop.get("Resistance_Score", 1.0) or 1.0)
        recovery = float(row.get("Daily_Recovery_Rate", 0.0) or 0.0)

        if "viral" in dtype or any(v in vector for v in ["whitefly", "leafhopper", "aphid", "mealybug", "thrip"]):
            params = {
                "beta": base_beta,
                "latent_days": 10.0,
                "infectious_decay": max(recovery, 0.0002),
                "reservoir_decay": 0.0005 if is_perennial else 0.002,
                "reservoir_return": 0.85,
                "long_jump_rate": 0.08,
                "jump_seed_strength": 0.055,
                "jump_event_floor": 0.08,
                "sporulation": 0.00,
                "chronicity": 0.95,
            }
            return DiseaseModelChoice(
                family="viral_vector",
                model_name="Vector-borne chronic tau-leaping model",
                evidence_level="pilot_prior",
                assumptions="Infected plants remain important reservoirs; vector pressure controls secondary spread; natural recovery is limited.",
                params=params,
            )

        if "bacterial" in dtype:
            params = {
                "beta": base_beta,
                "latent_days": 4.0,
                "infectious_decay": max(recovery, 0.006),
                "reservoir_decay": 0.01,
                "reservoir_return": 0.40,
                "long_jump_rate": 0.025,
                "jump_seed_strength": 0.035,
                "jump_event_floor": 0.04,
                "sporulation": 0.015,
                "chronicity": 0.25,
            }
            return DiseaseModelChoice(
                family="bacterial_splash",
                model_name="Rain-splash bacterial tau-leaping model",
                evidence_level="pilot_prior",
                assumptions="Rain and local splash dominate spread, with occasional weather-driven jumps.",
                params=params,
            )

        if "soil" in dtype or "root" in dtype:
            params = {
                "beta": base_beta * 0.55,
                "latent_days": 18.0,
                "infectious_decay": max(recovery, 0.001),
                "reservoir_decay": 0.0003,
                "reservoir_return": 0.95,
                "long_jump_rate": 0.005,
                "jump_seed_strength": 0.015,
                "jump_event_floor": 0.015,
                "sporulation": 0.004,
                "chronicity": 0.80,
            }
            return DiseaseModelChoice(
                family="soil_reservoir",
                model_name="Persistent soil-reservoir tau-leaping model",
                evidence_level="pilot_prior",
                assumptions="The soil or residues act as a slow persistent reservoir; spatial jumps are rare.",
                params=params,
            )

        params = {
            "beta": base_beta,
            "latent_days": 6.0,
            "infectious_decay": max(recovery, 0.008),
            "reservoir_decay": 0.006 if is_perennial else 0.015,
            "reservoir_return": 0.55,
            "long_jump_rate": 0.020,
            "jump_seed_strength": 0.030,
            "jump_event_floor": 0.030,
            "sporulation": 0.020,
            "chronicity": 0.35,
        }
        return DiseaseModelChoice(
            family="fungal_airborne",
            model_name="Fungal/bacterial canopy tau-leaping model",
            evidence_level="pilot_prior",
            assumptions="Humidity, temperature, wind/rain and residual inoculum drive local plus jump dispersal.",
            params=params,
        )

    @staticmethod
    def _as_dict(row: object) -> Dict[str, object]:
        if hasattr(row, "to_dict"):
            return row.to_dict()
        return dict(row)


class TauLeapingDiseaseEngine:
    """Run a daily stochastic disease simulation while preserving dashboard outputs."""

    def __init__(self) -> None:
        self.selector = DiseaseModelSelector()
        self.kernel = np.array(
            [[0.05, 0.18, 0.05], [0.18, 0.48, 0.18], [0.05, 0.18, 0.05]],
            dtype=float,
        )

    def run(self, config, crop_p, disease_row, bio_history, n_grid, mask, valid_points, initial_grid, stochastic_mode=False):
        choice = self.selector.select(disease_row, crop_p, config)
        disease_dict = disease_row.to_dict() if hasattr(disease_row, "to_dict") else (dict(disease_row) if disease_row is not None else None)
        seed = self._seed(config, stochastic_mode)
        rng = np.random.default_rng(seed)

        latent = np.zeros((n_grid, n_grid), dtype=float)
        infectious = np.zeros((n_grid, n_grid), dtype=float)
        resolved = np.zeros((n_grid, n_grid), dtype=float)
        reservoir = np.zeros((n_grid, n_grid), dtype=float)

        try:
            detect_date = pd.to_datetime(config.get("detection_date")).date()
        except Exception:
            detect_date = bio_history[0]["weather_row"]["DATE"].date()

        n_valid = max(1, len(valid_points))
        strategy = str(config.get("disease_control_strategy", "none"))
        control = self._control_profile(strategy, choice.family)
        removed_yield_fraction = 0.0
        roguing_applied = False
        roguing_inoculum_benefit = 0.0
        roguing_yield_cost = 0.0
        roguing_effective_efficiency = 0.0
        history = []

        for bio in bio_history:
            weather_row = bio["weather_row"]
            curr_date = weather_row["DATE"].date()
            env_risk = self._environment_risk(weather_row, disease_dict, choice.family)

            if disease_dict is not None:
                if curr_date == detect_date:
                    seeded = np.clip(initial_grid.astype(float), 0.0, 1.0) * mask
                    # Roguing is a counterfactual intervention, not an automatic rule.
                    # The engine first estimates how much inoculum would be removed,
                    # then compares that epidemiological gain with the productive stand
                    # loss.  Perennial crops receive a stricter margin because cutting a
                    # tree or severe pruning can depress yield beyond the current season.
                    roguing_decision = self._roguing_balance(
                        seeded=seeded,
                        mask=mask,
                        control=control,
                        crop_p=crop_p,
                        params=choice.params,
                        env_risk=env_risk,
                    )
                    roguing_applied = roguing_decision["applied"]
                    roguing_inoculum_benefit = roguing_decision["inoculum_benefit"]
                    roguing_yield_cost = roguing_decision["yield_cost"]
                    roguing_effective_efficiency = roguing_decision["effective_efficiency"]
                    removed_yield_fraction = roguing_decision["yield_penalty"]
                    rogued = seeded * roguing_effective_efficiency
                    infectious = np.maximum(infectious, seeded - rogued)
                    resolved = np.maximum(resolved, rogued * 0.25)
                    reservoir = np.maximum(reservoir, rogued * 0.10)
                elif curr_date > detect_date:
                    latent, infectious, resolved, reservoir = self._tau_step(
                        latent=latent,
                        infectious=infectious,
                        resolved=resolved,
                        reservoir=reservoir,
                        mask=mask,
                        params=choice.params,
                        env_risk=env_risk,
                        weather_row=weather_row,
                        config=config,
                        control=control,
                        rng=rng,
                        stochastic_mode=stochastic_mode,
                    )

            inf_values = infectious[mask]
            yield_base = self._yield_base(crop_p, bio)
            damage_factor = np.ones(n_valid)
            if disease_dict is not None and inf_values.size:
                retained = float(disease_dict.get("Yield_Retained_Infected", 0.5) or 0.5)
                damage_factor = (1.0 - inf_values) + (inf_values * retained)

            yield_grid = yield_base * damage_factor * (1.0 - removed_yield_fraction)
            history.append(
                {
                    "Date": weather_row["DATE"],
                    "LAI": bio["lai"],
                    "SWC": bio["swc"],
                    "N_kg": bio.get("n_kg", 0),
                    "P_kg": bio.get("p_kg", 0),
                    "K_kg": bio.get("k_kg", 0),
                    "ETa": bio["eta"],
                    "Biomass": bio["cumulative_biomass"],
                    "Wood_Biomass": bio.get("Wood_Biomass", 0),
                    "Fruit_Biomass": bio.get("Fruit_Biomass", 0),
                    "Yield": float(np.mean(yield_grid)) if len(yield_grid) else 0.0,
                    "Incidence": float(np.mean(inf_values)) if disease_dict is not None and inf_values.size else 0.0,
                    "Avg_Stress": 1 - bio["sw_fac"],
                    "Avg_N_Stress": 1 - bio.get("n_fac", 1),
                    "Avg_P_Stress": 1 - bio.get("p_fac", 1),
                    "Avg_K_Stress": 1 - bio.get("k_fac", 1),
                    "Grid_Incidence": inf_values.copy(),
                    "Grid_Yield": yield_grid.copy(),
                    "Env_Favorability": env_risk,
                    "Disease_Model": choice.model_name,
                    "Disease_Family": choice.family,
                    "Disease_Control_Strategy": strategy,
                    "Roguing_Applied": roguing_applied,
                    "Roguing_Effective_Efficiency": roguing_effective_efficiency,
                    "Roguing_Inoculum_Benefit": roguing_inoculum_benefit,
                    "Roguing_Yield_Cost": roguing_yield_cost,
                    "Roguing_Yield_Penalty": removed_yield_fraction,
                }
            )
        return history, choice.to_dict()

    def _tau_step(self, latent, infectious, resolved, reservoir, mask, params, env_risk, weather_row, config, control, rng, stochastic_mode):
        beta = params["beta"] * control["beta_multiplier"]
        driver = self._spread_driver(weather_row, config, params)
        susceptible = np.clip(1.0 - latent - infectious - resolved, 0.0, 1.0)
        pressure = convolve2d(infectious + 0.35 * reservoir, self.kernel, mode="same", boundary="symm")

        expected_exposure = beta * driver * env_risk * pressure * susceptible
        new_latent = self._fractional_poisson(expected_exposure, rng, stochastic_mode)

        latent_days = max(1.0, params["latent_days"])
        expected_activation = latent / latent_days
        new_infectious = self._fractional_poisson(expected_activation, rng, stochastic_mode)

        decay = (params["infectious_decay"] + control["recovery_bonus"]) * (1.0 + 2.0 * (1.0 - env_risk))
        leaving_infectious = np.clip(infectious * decay, 0.0, infectious)

        reservoir = reservoir * (1.0 - params["reservoir_decay"] * control["reservoir_cleanup"])
        reservoir = reservoir + leaving_infectious * params["reservoir_return"] + infectious * params["sporulation"] * env_risk

        latent = latent + new_latent - new_infectious
        infectious = infectious + new_infectious - leaving_infectious
        resolved = resolved + leaving_infectious * (1.0 - params["chronicity"])

        latent = self._seed_long_distance(latent, infectious, susceptible, params, env_risk, control, config, rng, stochastic_mode)
        latent = np.clip(latent, 0.0, 1.0) * mask
        infectious = np.clip(infectious, 0.0, 1.0) * mask
        resolved = np.clip(resolved, 0.0, 1.0) * mask
        reservoir = np.clip(reservoir, 0.0, 1.0) * mask
        return latent, infectious, resolved, reservoir

    @staticmethod
    def _fractional_poisson(expected, rng, stochastic_mode):
        expected = np.clip(expected, 0.0, 1.0)
        if not stochastic_mode:
            return expected
        # A virtual cell population keeps proportions smooth while allowing
        # stochasticity.  It is a light tau-leaping approximation, not an exact
        # plant-by-plant Gillespie simulation.
        virtual_population = 120.0
        events = rng.poisson(expected * virtual_population)
        return np.clip(events / virtual_population, 0.0, 1.0)

    def _seed_long_distance(self, latent, infectious, susceptible, params, env_risk, control, config, rng, stochastic_mode):
        """Seed occasional non-local infection jumps.

        Local convolution still handles neighbourhood spread, but real epidemics,
        especially vector-borne ones, also jump when insects, workers, rain splash
        or equipment move inoculum away from the initial focus.  The event count is
        stochastic in ensemble mode and thresholded in deterministic mode so the
        front is not forced to remain a perfect concentric circle.
        """
        total_pressure = float(np.sum(infectious))
        infected_cells = int(np.count_nonzero(infectious > 0.02))
        if total_pressure <= 0.0 or infected_cells <= 0:
            return latent

        jump_rate = float(params.get("long_jump_rate", 0.0)) * control["jump_multiplier"]
        seed_strength = float(params.get("jump_seed_strength", 0.03))
        event_floor = float(params.get("jump_event_floor", 0.03))
        driver = float(config.get("insect_pressure", 1.0) or 1.0)
        jump_pressure = (total_pressure + 0.45 * infected_cells) * max(0.05, env_risk) * max(0.25, driver)
        expected_jumps = jump_pressure * jump_rate

        if stochastic_mode:
            n_jumps = int(rng.poisson(expected_jumps))
            if n_jumps == 0 and expected_jumps > 0.0 and rng.random() < min(0.65, expected_jumps + event_floor):
                n_jumps = 1
        else:
            n_jumps = int(np.ceil(expected_jumps)) if expected_jumps >= event_floor else 0
        if n_jumps <= 0:
            return latent

        candidates = np.argwhere(susceptible > 0.05)
        sources = np.argwhere(infectious > 0.02)
        if len(candidates) == 0 or len(sources) == 0:
            return latent

        max_jumps = min(n_jumps, len(candidates), 12)
        chosen = candidates[rng.integers(0, len(candidates), size=max_jumps)]
        source = sources[rng.integers(0, len(sources))]
        for r, c in chosen:
            # A tiny distance weighting favours jumps that are truly away from the
            # focus while still allowing nearby secondary foci.
            dist = float(np.hypot(r - source[0], c - source[1]))
            distance_bonus = 1.0 + min(1.5, dist / max(1.0, latent.shape[0]))
            latent[r, c] = min(1.0, latent[r, c] + seed_strength * distance_bonus)
        return latent

    @staticmethod
    def _spread_driver(weather_row, config, params):
        wind = float(weather_row.get("WIND_SPEED", 2.0) or 2.0)
        rain = float(weather_row.get("RAIN", 0.0) or 0.0)
        insect = float(config.get("insect_pressure", 1.0) or 1.0)
        return max(0.05, 0.35 * wind / 5.0 + 0.25 * min(1.0, rain / 20.0) + 0.40 * insect)

    @staticmethod
    def _environment_risk(weather_row, disease_row, family):
        if disease_row is None:
            return 0.0
        tmean = (float(weather_row["TMIN"]) + float(weather_row["TMAX"])) / 2.0
        humidity = float(weather_row.get("HUMIDITY", 60.0) or 60.0)
        rain = float(weather_row.get("RAIN", 0.0) or 0.0)
        opt_temp = float(disease_row.get("Opt_Temp", 25.0) or 25.0)
        opt_humidity = float(disease_row.get("Opt_Humidity", 80.0) or 80.0)
        temp_score = np.exp(-((tmean - opt_temp) ** 2) / 48.0)
        humidity_score = min(1.0, humidity / max(1.0, opt_humidity))
        rain_bonus = 1.0 + 0.20 * min(1.0, rain / 15.0)
        if family == "viral_vector":
            rain_bonus = 1.0
        return float(np.clip(temp_score * humidity_score * rain_bonus, 0.0, 1.0))

    @staticmethod
    def _roguing_balance(seeded, mask, control, crop_p, params, env_risk):
        """Return a cautious roguing decision for a management scenario.

        The calculation deliberately stays light enough for Streamlit, but it
        keeps the agronomic trade-off explicit: removing a focus can lower
        inoculum pressure, while also removing productive plants or canopy.  A
        recommendation is therefore applied only when the estimated inoculum
        benefit exceeds the yield cost by a crop-type-specific margin.
        """
        requested_efficiency = float(control.get("roguing_efficiency", 0.0) or 0.0)
        default_result = {
            "applied": False,
            "effective_efficiency": 0.0,
            "inoculum_benefit": 0.0,
            "yield_cost": 0.0,
            "yield_penalty": 0.0,
        }
        if requested_efficiency <= 0.0 or not np.any(mask):
            return default_result

        seeded_values = seeded[mask]
        if seeded_values.size == 0 or float(np.mean(seeded_values)) <= 0.0:
            return default_result

        rogued = np.clip(seeded * requested_efficiency, 0.0, 1.0)
        rogued_mean = float(np.mean(rogued[mask]))
        focus_share = float(np.mean(seeded_values > 0.0))
        is_perennial = str(crop_p.get("Type", "")).lower() == "perennial"

        # Inoculum benefit is stronger when the pathogen has high spread
        # potential and when the detected focus is localized.  This prevents the
        # model from recommending broad removal once disease is already diffuse.
        spread_potential = 1.0 + float(params.get("beta", 0.0)) + float(params.get("jump_rate", 0.0)) + float(params.get("sporulation", 0.0))
        localization_bonus = 1.0 + max(0.0, 0.18 - focus_share)
        future_loss_multiplier = 3.2 if is_perennial else 1.6
        inoculum_benefit = rogued_mean * spread_potential * float(control.get("roguing_benefit_weight", 1.0)) * localization_bonus * float(env_risk) * future_loss_multiplier

        # Yield cost is a stand/canopy loss.  It is intentionally harsher for
        # perennials because tree removal or severe pruning can affect several
        # following harvests.  The cap avoids impossible losses from a small
        # detected focus while still carrying the penalty into all later days.
        stand_loss_multiplier = 2.5 if is_perennial else 1.45
        durable_cost = float(control.get("perennial_roguing_cost", 1.0)) if is_perennial else 1.0
        yield_cost = rogued_mean * stand_loss_multiplier * durable_cost
        yield_penalty_cap = 0.30 if is_perennial else 0.18
        yield_penalty = min(yield_penalty_cap, yield_cost)

        required_margin = float(control.get("perennial_roguing_margin", 1.35) if is_perennial else control.get("annual_roguing_margin", 1.05))
        if inoculum_benefit <= yield_cost * required_margin:
            return {**default_result, "inoculum_benefit": inoculum_benefit, "yield_cost": yield_cost}

        return {
            "applied": True,
            "effective_efficiency": requested_efficiency,
            "inoculum_benefit": inoculum_benefit,
            "yield_cost": yield_cost,
            "yield_penalty": yield_penalty,
        }

    @staticmethod
    def _yield_base(crop_p, bio):
        if crop_p["Type"] == "Perennial":
            return float(bio.get("Fruit_Biomass", 0.0))
        return float(bio["cumulative_biomass"] * float(crop_p.get("Harvest_Index", 0.5)))

    @staticmethod
    def _control_profile(strategy, family):
        profiles = {
            "none": {
                "beta_multiplier": 1.0,
                "jump_multiplier": 1.0,
                "recovery_bonus": 0.0,
                "reservoir_cleanup": 1.0,
                "roguing_efficiency": 0.0,
                "roguing_benefit_weight": 1.0,
            },
            "minimum": {
                "beta_multiplier": 0.82,
                "jump_multiplier": 0.90,
                "recovery_bonus": 0.001,
                "reservoir_cleanup": 1.10,
                "roguing_efficiency": 0.12,
                "roguing_benefit_weight": 0.90,
                "annual_roguing_margin": 1.10,
                "perennial_roguing_margin": 1.50,
                "perennial_roguing_cost": 1.25,
            },
            "intermediate": {
                "beta_multiplier": 0.68,
                "jump_multiplier": 0.78,
                "recovery_bonus": 0.0025,
                "reservoir_cleanup": 1.22,
                "roguing_efficiency": 0.28,
                "roguing_benefit_weight": 1.05,
                "annual_roguing_margin": 1.05,
                "perennial_roguing_margin": 1.40,
                "perennial_roguing_cost": 1.35,
            },
            "optimized": {
                "beta_multiplier": 0.55,
                "jump_multiplier": 0.65,
                "recovery_bonus": 0.004,
                "reservoir_cleanup": 1.35,
                "roguing_efficiency": 0.45,
                "roguing_benefit_weight": 1.18,
                "annual_roguing_margin": 1.00,
                "perennial_roguing_margin": 1.30,
                "perennial_roguing_cost": 1.45,
            },
        }
        profile = profiles.get(strategy, profiles["none"]).copy()
        if family == "viral_vector" and strategy != "none":
            profile["recovery_bonus"] *= 0.25
            viral_efficiency = {"minimum": 0.30, "intermediate": 0.48, "optimized": 0.62}.get(strategy, profile["roguing_efficiency"])
            profile["roguing_efficiency"] = max(profile["roguing_efficiency"], viral_efficiency)
        return profile

    @staticmethod
    def _seed(config, stochastic_mode):
        base = int(config.get("random_seed", 20250610) or 20250610)
        run_idx = int(config.get("_ensemble_run_index", 0) or 0)
        if stochastic_mode:
            return base + (run_idx * 7919)
        return base
