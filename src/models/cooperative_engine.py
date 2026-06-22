# src/models/cooperative_engine.py
"""Cooperative-mode simulation helpers.

The cooperative workflow treats each farmer plot as a local patch and then links
patches through a light metapopulation disease layer.  Crop phenology, soil water,
nutrients and within-plot disease dynamics still come from SimulationEngine; this
adapter only prepares per-plot configurations and aggregates results.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd

from src.models.simulation_engine import SimulationEngine


LatLon = Tuple[float, float]


def polygon_area_ha(coords: Iterable[LatLon]) -> float:
    """Approximate polygon area in hectares for small agricultural plots."""
    pts = list(coords or [])
    if len(pts) < 3:
        return 0.0
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    lat0 = sum(p[0] for p in pts[:-1]) / max(1, len(pts) - 1)
    meters_per_lat = 111_320.0
    meters_per_lon = 111_320.0 * math.cos(math.radians(lat0))
    xy = [(lon * meters_per_lon, lat * meters_per_lat) for lat, lon in pts]
    area = 0.0
    for i in range(len(xy) - 1):
        area += xy[i][0] * xy[i + 1][1] - xy[i + 1][0] * xy[i][1]
    return abs(area) / 20_000.0


def polygon_centroid(coords: Iterable[LatLon]) -> LatLon:
    """Return a stable centroid fallback even for partially edited polygons."""
    pts = list(coords or [])
    if not pts:
        return (0.0, 0.0)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def point_in_polygon(lat: float, lon: float, coords: Iterable[LatLon]) -> bool:
    """Ray-casting point-in-polygon test using lat/lon pairs."""
    pts = list(coords or [])
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        yi, xi = pts[i]
        yj, xj = pts[j]
        crosses = (xi > lon) != (xj > lon)
        if crosses:
            y_at_lon = (yj - yi) * (lon - xi) / ((xj - xi) + 1e-12) + yi
            if lat < y_at_lon:
                inside = not inside
        j = i
    return inside


def distance_m(a: LatLon, b: LatLon) -> float:
    """Fast local distance approximation in metres."""
    lat = math.radians((a[0] + b[0]) / 2.0)
    dlat = (a[0] - b[0]) * 111_320.0
    dlon = (a[1] - b[1]) * 111_320.0 * math.cos(lat)
    return math.hypot(dlat, dlon)


class CooperativeSimulationEngine:
    """Run and aggregate plot-level simulations for cooperative perimeters."""

    def __init__(self):
        self.single_engine = SimulationEngine()


    def _economic_horizon_years(self, config: Dict, crop_params: Dict) -> int:
        """Return the chosen economic horizon for plot-level optimization summaries."""
        if str(crop_params.get('Type', 'Annual')) != 'Perennial':
            return 1
        econ = config.get('economics_config', {}) or {}
        raw = econ.get('economic_horizon_years', config.get('economic_horizon_years', 20))
        try:
            return max(1, min(20, int(float(raw))))
        except Exception:
            return 20

    def _harvest_equivalent_yield_t_ha(self, history: List[Dict], crop_params: Dict, horizon_years: int) -> float:
        """Convert daily yield traces into harvested yield over the report horizon.

        Annual crops use the final yield.  Perennial crops use annual peak yields,
        because standing fruit is reset between harvest years and the last day alone
        is not the economic production of a long-horizon plantation.
        """
        if not history:
            return 0.0
        if str(crop_params.get('Type', 'Annual')) != 'Perennial':
            last = history[-1]
            return float(last.get('Yield', last.get('Fruit_Biomass', 0.0)) or 0.0)
        dates = pd.to_datetime([row.get('Date') for row in history])
        start = dates.min() if len(dates) else None
        buckets: Dict[int, float] = {}
        for row, row_date in zip(history, dates):
            if start is None or pd.isna(row_date):
                year_index = 1
            else:
                year_index = int(max(0, (row_date - start).days) // 365) + 1
            if 1 <= year_index <= horizon_years:
                yld = float(row.get('Yield', row.get('Fruit_Biomass', 0.0)) or 0.0)
                buckets[year_index] = max(buckets.get(year_index, 0.0), yld)
        return float(sum(buckets.get(year, 0.0) for year in range(1, horizon_years + 1)))

    def _parcel_config(self, base_config: Dict, parcel: Dict) -> Dict:
        """Create an isolated SimulationEngine config for one cooperative plot."""
        cfg = deepcopy(base_config)
        coords = parcel.get('coords', [])
        cfg['field_coords'] = coords
        cfg['area_ha'] = float(parcel.get('area_ha') or polygon_area_ha(coords) or 0.1)
        cfg['field_name'] = parcel.get('name') or parcel.get('id') or 'Cooperative parcel'

        # Crop settings may be shared by default, but selected fields can override
        # planting date, density and initial nutrients in cooperative mode.
        for key in ['selected_crop_id', 'planting_density', 'sowing_depth', 'selected_disease_id', 'insect_pressure']:
            if parcel.get(key) not in (None, ''):
                cfg[key] = parcel[key]
        if parcel.get('planting_date'):
            cfg['planting_date'] = pd.to_datetime(parcel['planting_date']).date()
        for key in ['initial_nitrogen', 'initial_phosphorus', 'initial_potassium', 'years_without_fertilizer']:
            if parcel.get(key) not in (None, ''):
                cfg[key] = float(parcel[key])

        # Cooperative mode removes scheduled irrigation/fertilisation at setup.
        # The optimized scenario can still be generated later by the engine.
        cfg['irr_schedule'] = []
        cfg['fert_schedule'] = []

        # Disease observations are attached only to the plot containing the marker.
        plot_spots = []
        for spot in base_config.get('disease_spots', []) or []:
            if point_in_polygon(float(spot.get('lat', 0.0)), float(spot.get('lon', 0.0)), coords):
                plot_spots.append(spot)
        cfg['disease_spots'] = plot_spots
        return cfg

    def _apply_metapopulation_coupling(self, parcel_results: List[Dict], config: Dict) -> List[Dict]:
        """Add a distance-weighted inter-plot infection pressure layer.

        The local model computes within-plot dynamics.  Between plots, infected
        plots contribute a kernel-weighted pressure to other plots.  This is a
        patch-network analogue of Levins/Hanski metapopulation thinking and keeps
        the computation light enough for dashboards.
        """
        if len(parcel_results) < 2:
            return parcel_results
        centroids = [r['centroid'] for r in parcel_results]
        areas = np.array([max(0.01, r['area_ha']) for r in parcel_results], dtype=float)
        insect_pressure = float(config.get('insect_pressure', 1.0) or 1.0)
        perimeter_area_ha = float(config.get('cooperative_perimeter_area_ha', 0.0) or 0.0)
        cultivated_area_ha = float(config.get('cooperative_cultivated_area_ha', 0.0) or 0.0) or float(areas.sum())
        cultivated_fraction = float(config.get('cooperative_cultivated_fraction', 0.0) or 0.0)
        if cultivated_fraction <= 0.0 and perimeter_area_ha > 0:
            cultivated_fraction = min(1.0, cultivated_area_ha / max(perimeter_area_ha, 1e-6))
        # Large non-cultivated gaps lower the metapopulation coupling strength.
        # We keep a floor because vectors, workers, tools, wind or water can still
        # move inoculum across gaps, but the old row-normalized kernel erased the
        # absolute distance effect entirely.
        gap_factor = float(np.clip(0.25 + 0.75 * max(0.0, min(1.0, cultivated_fraction)), 0.25, 1.0))
        coupling_rate = float(config.get('cooperative_coupling_rate', 0.045)) * max(0.25, insect_pressure) * gap_factor
        distance_scale_m = float(config.get('cooperative_dispersal_scale_m', 650.0))

        distances = np.zeros((len(parcel_results), len(parcel_results)), dtype=float)
        for i, ci in enumerate(centroids):
            for j, cj in enumerate(centroids):
                if i != j:
                    distances[i, j] = distance_m(ci, cj)
        kernel = np.exp(-distances / max(1.0, distance_scale_m))
        np.fill_diagonal(kernel, 0.0)
        # Do not row-normalize the kernel.  Absolute distance must matter: a plot
        # separated by a wide non-cultivated gap should exert less pressure than
        # a neighbouring plot, even if it is the only infected source.

        max_len = max(len(r['history']) for r in parcel_results)
        for t in range(max_len):
            incidence = np.array([
                float(r['history'][min(t, len(r['history']) - 1)].get('Incidence', 0.0))
                for r in parcel_results
            ], dtype=float)
            source_strength = incidence * areas / max(areas.sum(), 1e-6)
            external = kernel.dot(source_strength) * coupling_rate
            for i, r in enumerate(parcel_results):
                day = r['history'][min(t, len(r['history']) - 1)]
                local_i = float(day.get('Incidence', 0.0))
                meta_i = 1.0 - (1.0 - local_i) * (1.0 - min(0.35, external[i]))
                delta = max(0.0, meta_i - local_i)
                day['Local_Incidence'] = local_i
                day['Metapopulation_Pressure'] = float(external[i])
                day['Metapopulation_Gap_Factor'] = gap_factor
                day['Cooperative_Cultivated_Fraction'] = cultivated_fraction
                day['Incidence'] = float(np.clip(meta_i, 0.0, 1.0))
                # Conservative yield penalty from imported disease pressure.  The
                # crop disease row controls detailed local losses; this only avoids
                # ignoring landscape pressure in cooperative mode.
                if delta > 0 and 'Yield' in day:
                    day['Yield'] = max(0.0, float(day['Yield']) * (1.0 - 0.25 * delta))
        return parcel_results

    def build_optimized_management_plan(self, config: Dict, baseline_result: Dict | None = None, max_plots: int = 60) -> Dict:
        """Optimize irrigation and fertilization for cooperative report parcels.

        Cooperative setup intentionally disables manual calendars.  The report,
        however, must still compare the current no-action trajectory with a
        feasible optimized-management trajectory.  We therefore optimize each
        selected parcel with the single-field engine, then aggregate gains and
        resource needs.  For very large cooperatives the method prioritizes the
        plots with the highest disease or water/nutrient stress, keeping the PDF
        responsive while documenting any skipped plots.
        """
        parcels = [p for p in config.get('cooperative_parcels', []) if p.get('active', True) and p.get('coords')]
        if not parcels:
            return {'rows': [], 'summary': {}, 'skipped_plot_count': 0}

        baseline_by_id: Dict[str, Dict] = {}
        if baseline_result:
            for result in baseline_result.get('parcel_results', []) or []:
                baseline_by_id[result.get('id')] = result

        def risk_key(parcel: Dict) -> float:
            result = baseline_by_id.get(parcel.get('id'))
            if not result or not result.get('history'):
                return 0.0
            last = result['history'][-1]
            return (
                float(last.get('Incidence', 0.0) or 0.0) * 2.0
                + float(last.get('Avg_Stress', 0.0) or 0.0)
                + float(last.get('Avg_N_Stress', 0.0) or 0.0) * 0.6
            )

        max_plots = max(1, int(max_plots or 60))
        ranked_parcels = sorted(parcels, key=risk_key, reverse=True)
        selected = ranked_parcels[:max_plots]
        rows: List[Dict] = []
        totals = {
            'baseline_production_t': 0.0,
            'optimized_production_t': 0.0,
            'production_gain_t': 0.0,
            'water_m3': 0.0,
            'fertilizer_kg': 0.0,
        }

        for index, parcel in enumerate(selected, start=1):
            cfg = self._parcel_config(config, parcel)
            baseline = baseline_by_id.get(parcel.get('id'))
            if baseline and baseline.get('history'):
                baseline_history = baseline['history']
            else:
                baseline_run = self.single_engine.run_simulation(cfg)
                baseline_history = baseline_run['history'] if baseline_run and baseline_run.get('history') else []

            opt_irr_schedule, _ = self.single_engine.optimize_irrigation_schedule(cfg)
            opt_fert_schedule = self.single_engine.optimize_fertilization_schedule(cfg)
            optimized_cfg = deepcopy(cfg)
            optimized_cfg['irr_schedule'] = opt_irr_schedule
            optimized_cfg['fert_schedule'] = opt_fert_schedule
            optimized_run = self.single_engine.run_simulation(optimized_cfg)
            optimized_history = optimized_run['history'] if optimized_run and optimized_run.get('history') else []

            area = float(cfg.get('area_ha', 0.0) or 0.0)
            crop_params = (optimized_run or {}).get('crop_params') or (baseline or {}).get('crop_params') or {}
            horizon_years = self._economic_horizon_years(config, crop_params)
            baseline_yield = self._harvest_equivalent_yield_t_ha(baseline_history, crop_params, horizon_years)
            optimized_yield = self._harvest_equivalent_yield_t_ha(optimized_history, crop_params, horizon_years)
            baseline_production = baseline_yield * area
            optimized_production = optimized_yield * area
            water_m3 = sum(float(e.get('amount', 0.0) or 0.0) * area * 10.0 for e in opt_irr_schedule or [])
            fertilizer_kg = sum(float(e.get('amount', 0.0) or 0.0) * area for e in opt_fert_schedule or [])

            rows.append({
                'id': parcel.get('id', 'P{:03d}'.format(index)),
                'name': parcel.get('name', 'Parcel {}'.format(index)),
                'area_ha': area,
                'baseline_yield_t_ha': baseline_yield,
                'optimized_yield_t_ha': optimized_yield,
                'yield_gain_t_ha': optimized_yield - baseline_yield,
                'production_gain_t': optimized_production - baseline_production,
                'irrigation_events': len(opt_irr_schedule or []),
                'fertilizer_events': len(opt_fert_schedule or []),
                'water_m3': water_m3,
                'fertilizer_kg': fertilizer_kg,
                # Keep the full optimized calendars so the Recommendations page can
                # show concrete dates and quantities, not just event counts.  Dates
                # are kept as Python date objects; Streamlit displays them directly
                # and JSON export converts them with default=str.
                'irrigation_schedule': opt_irr_schedule or [],
                'fertilization_schedule': opt_fert_schedule or [],
            })
            totals['baseline_production_t'] += baseline_production
            totals['optimized_production_t'] += optimized_production
            totals['production_gain_t'] += optimized_production - baseline_production
            totals['water_m3'] += water_m3
            totals['fertilizer_kg'] += fertilizer_kg

        skipped = max(0, len(parcels) - len(selected))
        totals = {k: round(v, 2) for k, v in totals.items()}
        totals['optimized_plot_count'] = len(selected)
        totals['total_active_plot_count'] = len(parcels)
        return {
            'rows': rows,
            'summary': totals,
            'skipped_plot_count': skipped,
            'scope_note': 'Optimized all active plots.' if skipped == 0 else 'Optimized highest-risk plots first; remaining plots keep the no-action baseline in this report run.',
        }

    def run_cooperative_simulation(self, config: Dict) -> Dict:
        """Run per-plot simulations and return cooperative aggregate outputs."""
        parcels = [p for p in config.get('cooperative_parcels', []) if p.get('active', True) and p.get('coords')]
        if not parcels:
            return None

        parcel_results = []
        for index, parcel in enumerate(parcels, start=1):
            cfg = self._parcel_config(config, parcel)
            result = self.single_engine.run_simulation(cfg)
            if result is None:
                continue
            coords = cfg['field_coords']
            parcel_results.append({
                'id': parcel.get('id', f'P{index:03d}'),
                'name': parcel.get('name', f'Parcel {index}'),
                'area_ha': cfg['area_ha'],
                'coords': coords,
                'centroid': polygon_centroid(coords),
                'config': cfg,
                'history': result['history'],
                'crop_params': result.get('crop_params', {}),
                'growth_model': result.get('growth_model', {}),
                'disease_model': result.get('disease_model', {}),
            })
        if not parcel_results:
            return None

        parcel_results = self._apply_metapopulation_coupling(parcel_results, config)
        dates = [d['Date'] for d in parcel_results[0]['history']]
        aggregate_history = []
        total_area = sum(r['area_ha'] for r in parcel_results)
        for t, d in enumerate(dates):
            weights = np.array([r['area_ha'] for r in parcel_results], dtype=float)
            rows = [r['history'][min(t, len(r['history']) - 1)] for r in parcel_results]
            def wmean(key: str) -> float:
                vals = np.array([float(row.get(key, 0.0) or 0.0) for row in rows], dtype=float)
                return float(np.average(vals, weights=weights)) if weights.sum() else float(vals.mean())
            yield_vals = np.array([float(row.get('Yield', 0.0) or 0.0) for row in rows], dtype=float)
            aggregate_history.append({
                'Date': d,
                'Yield': wmean('Yield'),
                'Total_Production': float(np.sum(yield_vals * weights)),
                'Incidence': wmean('Incidence'),
                'Local_Incidence': wmean('Local_Incidence'),
                'Metapopulation_Pressure': wmean('Metapopulation_Pressure'),
                'Metapopulation_Gap_Factor': wmean('Metapopulation_Gap_Factor'),
                'Cooperative_Cultivated_Fraction': wmean('Cooperative_Cultivated_Fraction'),
                'Avg_Stress': wmean('Avg_Stress'),
                'Avg_N_Stress': wmean('Avg_N_Stress'),
                'Avg_P_Stress': wmean('Avg_P_Stress'),
                'Avg_K_Stress': wmean('Avg_K_Stress'),
                'LAI': wmean('LAI'),
                'Biomass': wmean('Biomass'),
            })

        perimeter_area_ha = float(config.get('cooperative_perimeter_area_ha', 0.0) or 0.0)
        cultivated_fraction = min(1.0, total_area / max(perimeter_area_ha, 1e-6)) if perimeter_area_ha > 0 else 0.0
        unassigned_area_ha = max(0.0, perimeter_area_ha - total_area) if perimeter_area_ha > 0 else 0.0

        return {
            'mode': 'cooperative',
            'history': aggregate_history,
            'parcel_results': parcel_results,
            'parcel_count': len(parcel_results),
            'total_area_ha': total_area,
            'perimeter_area_ha': perimeter_area_ha,
            'unassigned_area_ha': unassigned_area_ha,
            'cultivated_fraction': cultivated_fraction,
            'crop_params': parcel_results[0].get('crop_params', {}),
            'growth_model': parcel_results[0].get('growth_model', {}),
            'disease_model': {'family': 'cooperative_metapopulation', 'model_name': 'Distance-kernel metapopulation coupling'},
            'field_poly': config.get('cooperative_perimeter_coords', []),
            'manual_schedules_disabled': True,
        }
