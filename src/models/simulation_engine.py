# src/models/simulation_engine.py
import numpy as np
import pandas as pd
import streamlit as st
import ee 
from datetime import date, timedelta
from scipy.signal import convolve2d
from scipy.spatial import Delaunay
from matplotlib.tri import Triangulation
from matplotlib.path import Path

# Import helpers
from src.models.weather_service import WeatherService
from src.models.physics_engine import PhysicsEngine
from src.models.fertilizer_service import FertilizerService
from src.models.disease_models import TauLeapingDiseaseEngine
from src.models.growth_model_selector import GrowthModelSelector
from src.models.operational_constraints import max_irrigation_mm_per_event

class SimulationEngine:
    def __init__(self):
        self.weather_service = WeatherService()
        self.physics = PhysicsEngine()
        self.fert_service = FertilizerService()
        self.disease_engine = TauLeapingDiseaseEngine()
        self.growth_selector = GrowthModelSelector()


    def _operational_uncertainty_profile(self, config, crop_p):
        """Return a cautious uncertainty floor for operational decision support.

        The stochastic ensemble captures random disease spread, but it does not yet
        sample every uncertain input: soil estimates, cultivar parameters, weather
        downscaling, automatic disease identity and missing field calibration.  A
        diagnostic tool should therefore avoid zero-width confidence bands.  The
        floor below is intentionally conservative and is reduced only when the
        adaptive surveillance loop has real observations or calibrated parameters.
        """
        is_perennial = str(crop_p.get('Type', 'Annual')) == 'Perennial'
        soil_source = str(config.get('soil_data_source', 'manual') or 'manual')
        try:
            soil_confidence = float(config.get('soil_confidence', 1.0))
        except Exception:
            soil_confidence = 0.75
        soil_confidence = float(np.clip(soil_confidence, 0.35, 1.0))

        observations = config.get('surveillance_logs', []) or []
        observation_count = len(observations) if isinstance(observations, list) else 0
        has_calibration = bool(config.get('calibrated_params'))
        has_disease = bool(config.get('selected_disease_id')) or bool(config.get('disease_spots'))

        base_yield_ci = 0.22 if is_perennial else 0.16
        soil_penalty = (1.0 - soil_confidence) * 0.30
        if soil_source != 'manual':
            soil_penalty += 0.04
        calibration_credit = min(0.10, observation_count * 0.015)
        if has_calibration:
            calibration_credit += 0.05

        min_yield_ci = 0.12 if is_perennial else 0.08
        yield_ci_fraction_95 = float(np.clip(base_yield_ci + soil_penalty - calibration_credit, min_yield_ci, 0.50))
        yield_abs_ci95_t_ha = 0.06 if is_perennial else 0.04

        base_incidence_ci = 0.16 if has_disease else 0.03
        disease_penalty = 0.04 if has_disease and observation_count == 0 else 0.0
        incidence_ci95_abs = float(np.clip(base_incidence_ci + disease_penalty - calibration_credit * 0.5, 0.02 if not has_disease else 0.06, 0.35))

        return {
            'yield_ci_fraction_95': yield_ci_fraction_95,
            'yield_abs_ci95_t_ha': yield_abs_ci95_t_ha,
            'incidence_ci95_abs': incidence_ci95_abs,
            'soil_source': soil_source,
            'soil_confidence': soil_confidence,
            'adaptive_observation_count': observation_count,
            'has_calibration': has_calibration,
            'basis': 'stochastic ensemble plus conservative operational uncertainty floor'
        }

    def _expand_schedule_for_perennials(self, schedule_list, years=20):
        if not schedule_list: return []
        expanded = []
        for i in range(years):
            offset_year = i
            for event in schedule_list:
                try:
                    orig_date = pd.to_datetime(event['date'])
                    new_date = orig_date.replace(year=orig_date.year + offset_year).date()
                    new_event = event.copy()
                    new_event['date'] = new_date
                    expanded.append(new_event)
                except ValueError:
                    continue
        return expanded

    def _prepare_physics(self, config):
        """
        Initializes Weather, Soil State, and Management Schedules.
        Handles Perennial (20-yr) vs Annual (Cycle) logic.
        Calculates DYNAMIC WOOD CAPACITY based on Density.
        
        NEW: Injects Calibrated Parameters from config['calibrated_params']
        """
        df_c = st.session_state['df_crops']
        # Convert Series to dict to allow injection of new keys (Max_Wood_Capacity)
        crop_p = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0].to_dict()
        
        # --- OVERRIDE WITH CALIBRATED PARAMS ---
        if 'calibrated_params' in config and config['calibrated_params']:
            cal = config['calibrated_params']
            for k, v in cal.items():
                if k in crop_p or k in ['RUE_g_MJ', 'Max_LAI', 'Harvest_Index', 'Per_Tree_Wood_Capacity_kg']:
                    crop_p[k] = v
        
        # --- DYNAMIC CAPACITY LOGIC ---
        # Read per-tree capacity (kg) from DB (default to 0 if missing)
        per_tree_kg = float(crop_p.get('Per_Tree_Wood_Capacity_kg', 0.0))
        
        # Read user density (plants/ha)
        density = float(config.get('planting_density', 1000.0))
        
        # Calculate Max Wood in t/ha
        # formula: (kg_per_tree * trees_per_ha) / 1000 = tonnes_per_ha
        max_wood_t_ha = (per_tree_kg * density) / 1000.0
        
        # Inject into crop parameters
        crop_p['Max_Wood_Capacity'] = max_wood_t_ha

        # --- 1. HORIZON LOGIC ---
        is_perennial = crop_p['Type'] == 'Perennial'
        initial_age_years = max(0.0, float(config.get('initial_plant_age_years', 0.0) or 0.0)) if is_perennial else 0.0
        
        if is_perennial:
            duration_days = 7300 # 20 Years
        else:
            duration_days = int(crop_p['Cycle_Days'])

        # --- 2. WEATHER ---
        weather = self.weather_service.get_weather_projections(
            config['center_lat'], config['center_lon'], config['planting_date'], duration_days
        )
        
        if weather is None or weather.empty:
            st.error("Critical Failure: Unable to generate climate data from any source.")
            return None

        # --- 3. SOIL INIT ---
        soil_layers = config['soil_layers']
        
        if isinstance(soil_layers, list) and len(soil_layers) > 0:
             total_fc_pct = np.mean([l['field_capacity'] for l in soil_layers])
             total_wp_pct = np.mean([l['wilting_point'] for l in soil_layers])
        elif isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11

        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        
        init_water_frac = config.get('initial_soil_water', 0.8)
        init_water = init_water_frac * fc_mm 
        if init_water < wp_mm: init_water = wp_mm

        conv_factor = 4.0 
        
        # Initial Nutrients (Potentially overridden by calibration, handled in config passing)
        soil_state = {
            'water_mm': init_water,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        # --- 4. MANAGEMENT SCHEDULES ---
        raw_fert = config['fert_schedule']
        raw_irr = config['irr_schedule']

        if is_perennial:
            raw_fert = self._expand_schedule_for_perennials(raw_fert, years=20)
            raw_irr = self._expand_schedule_for_perennials(raw_irr, years=20)

        fert_df = pd.DataFrame(raw_fert)
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}
        pruning_days = set() 

        if not fert_df.empty:
            if 'product' in fert_df.columns:
                for _, row in fert_df.iterrows():
                    d = pd.to_datetime(row['date']).date()
                    prod_name = row['product']
                    if 'Canopy Pruning' in prod_name:
                        pruning_days.add(d)
                        continue 
                    amount = float(row['amount'])
                    prod_info = next((p for p in self.fert_service.products if p['name'] == prod_name), None)
                    if prod_info and prod_info['type'] != 'Operation':
                        fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                        fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                        fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)
            else:
                for col in ['amount_n', 'amount_p', 'amount_k']:
                    if col not in fert_df.columns: fert_df[col] = 0.0
                fert_n_map = {pd.to_datetime(r['date']).date(): float(r['amount_n']) for _, r in fert_df.iterrows()}
                fert_p_map = {pd.to_datetime(r['date']).date(): float(r['amount_p']) for _, r in fert_df.iterrows()}
                fert_k_map = {pd.to_datetime(r['date']).date(): float(r['amount_k']) for _, r in fert_df.iterrows()}
        
        irr_map = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in raw_irr}
        
        mgmt = {
            'fert_n': fert_n_map,
            'fert_p': fert_p_map,
            'fert_k': fert_k_map,
            'irr': irr_map
        }

        # --- 5. RUN PHYSICS LOOP ---
        bio_history = []
        biomass_cum = 0.0      
        biomass_perfect_cum = 0.0  
        wood_cum = 0.0
        standing_fruit = 0.0
        
        # Perennial fields are often already productive when the app is launched.
        # Starting every perennial simulation from age zero would understate wood
        # biomass and distort early yield.  We initialise age and structural wood
        # from the user-supplied current plantation age while keeping annual crops
        # unchanged.
        initial_wood = 0.0
        if is_perennial and initial_age_years > 0:
            capacity = float(crop_p.get('Max_Wood_Capacity', 35.0) or 35.0)
            initial_wood = capacity * (1.0 - np.exp(-initial_age_years / 4.0))
            initial_wood = float(np.clip(initial_wood, 0.0, capacity))
        wood_cum = initial_wood
        plant_state = {
            'lai': 0.0,
            'stunting_factor': 1.0,
            'cum_dd': 0.0,
            'age_days': int(initial_age_years * 365.0),
            'wood_biomass': initial_wood
        }

        lat = config.get('center_lat', 0.0)

        for t, row in weather.iterrows():
            curr_date = row['DATE'].date()
            mgmt['pruning'] = curr_date in pruning_days
            plant_state['wood_biomass'] = wood_cum

            # Physics Step (Dict is mutable, so crop_p carries Max_Wood_Capacity)
            bio = self.physics.stics_lite_step(t, row, crop_p, soil_state, plant_state, mgmt, lat_deg=lat)
            
            if is_perennial:
                wood_cum += bio['d_wood_t_ha']
                if wood_cum < 0: wood_cum = 0.0 
                
                standing_fruit += bio['d_fruit_t_ha']
                
                if curr_date.month == 1 and curr_date.day == 1 and plant_state['age_days'] > 365:
                     standing_fruit = 0.0 
                
                biomass_cum = wood_cum + standing_fruit
                bio['Wood_Biomass'] = wood_cum
                bio['Fruit_Biomass'] = standing_fruit
                
            else:
                biomass_cum += bio['d_biomass_t_ha']
                bio['Wood_Biomass'] = biomass_cum * (1 - crop_p['Harvest_Index']) 
                bio['Fruit_Biomass'] = biomass_cum * crop_p['Harvest_Index']

            d_perfect = bio.get('d_biomass_perfect_t_ha', bio['d_biomass_t_ha'])
            biomass_perfect_cum += d_perfect
            
            bio['cumulative_biomass'] = biomass_cum
            bio['cumulative_perfect'] = biomass_perfect_cum
            bio['weather_row'] = row
            
            bio_history.append(bio)
            
        return crop_p, weather, bio_history

    def _prepare_spatial(self, config):
        field_poly = np.array([list(p) for p in config['field_coords']])
        path = Path(field_poly)
        min_x, min_y = np.min(field_poly, axis=0)
        max_x, max_y = np.max(field_poly, axis=0)
        
        N = 40 
        x = np.linspace(min_x, max_x, N); y = np.linspace(min_y, max_y, N)
        xv, yv = np.meshgrid(x, y)
        points = np.vstack((xv.flatten(), yv.flatten())).T
        mask = path.contains_points(points).reshape(N, N)
        valid_points = points[mask.flatten()]
        
        if len(valid_points) < 3: return None
        
        tri = Delaunay(valid_points)
        triang = Triangulation(valid_points[:,0], valid_points[:,1], tri.simplices)
        
        tri_centers = np.mean(valid_points[tri.simplices], axis=1)
        mask_tri = ~path.contains_points(tri_centers)
        triang.set_mask(mask_tri)
        
        I_grid_init = np.zeros((N, N))
        if config['disease_spots']:
            for spot in config['disease_spots']:
                dist = (xv - spot['lat'])**2 + (yv - spot['lon'])**2
                iy, ix = np.unravel_index(np.argmin(dist), (N, N))
                if mask[iy, ix]: 
                    count = spot.get('plants', 1)
                    severity = min(1.0, 0.05 * count)
                    I_grid_init[iy, ix] = max(I_grid_init[iy, ix], severity)
        
        return field_poly, N, mask, valid_points, triang, I_grid_init

    def _run_disease_realization(self, config, crop_p, bio_history, N, mask, valid_points, I_grid_init, stochastic_mode=False):
        """Run the selected disease model and keep the historical output schema.

        The dashboard and report expect daily dictionaries containing Yield,
        Incidence, Grid_Incidence and stress metrics.  The actual epidemiology
        now lives in TauLeapingDiseaseEngine so disease families can evolve
        independently from the Streamlit pages.
        """
        df_d = st.session_state['df_diseases']
        dis_id = config['selected_disease_id']
        dis_p = None
        if dis_id:
            dis_rows = df_d[df_d['Disease_ID'] == dis_id]
            if not dis_rows.empty:
                dis_p = dis_rows.iloc[0]

        history, model_choice = self.disease_engine.run(
            config=config,
            crop_p=crop_p,
            disease_row=dis_p,
            bio_history=bio_history,
            n_grid=N,
            mask=mask,
            valid_points=valid_points,
            initial_grid=I_grid_init,
            stochastic_mode=stochastic_mode,
        )
        config['_last_disease_model_choice'] = model_choice
        return history

    def run_simulation(self, config):
        res_physics = self._prepare_physics(config)
        if res_physics is None: return None
        crop_p, weather, bio_history = res_physics
        
        spatial_res = self._prepare_spatial(config)
        if spatial_res is None: return None
        field_poly, N, mask, valid_points, triang, I_grid_init = spatial_res
        
        growth_choice = self.growth_selector.select(config, crop_p)
        history = self._run_disease_realization(config, crop_p, bio_history, N, mask, valid_points, I_grid_init)
        return {
            'history': history,
            'triangulation': triang,
            'grid_points': valid_points,
            'crop_params': crop_p,
            'field_poly': field_poly,
            'growth_model': growth_choice.to_dict(),
            'disease_model': config.get('_last_disease_model_choice', {})
        }

    def run_ensemble_inference(self, config, n_runs=50):
        res_physics = self._prepare_physics(config)
        if res_physics is None: return None
        crop_p, weather, bio_history = res_physics
        
        spatial_res = self._prepare_spatial(config)
        if spatial_res is None: return None
        field_poly, N, mask, valid_points, triang, I_grid_init = spatial_res
        
        ensemble_yields = []
        ensemble_incidence = []
        ensemble_roguing_applied = []
        ensemble_roguing_penalty = []
        ensemble_roguing_benefit = []
        ensemble_roguing_cost = []
        ensemble_final_grid = np.zeros_like(I_grid_init[mask])
        dates = [b['weather_row']['DATE'] for b in bio_history]
        
        last_disease_model_choice = {}
        for run_idx in range(n_runs):
            run_config = config.copy()
            run_config['_ensemble_run_index'] = run_idx
            run_hist = self._run_disease_realization(run_config, crop_p, bio_history, N, mask, valid_points, I_grid_init, stochastic_mode=True)
            last_disease_model_choice = run_config.get('_last_disease_model_choice', last_disease_model_choice)
            y_series = [day['Yield'] for day in run_hist]
            i_series = [day['Incidence'] for day in run_hist]
            ensemble_yields.append(y_series)
            ensemble_incidence.append(i_series)
            ensemble_roguing_applied.append(float(any(day.get('Roguing_Applied', False) for day in run_hist)))
            ensemble_roguing_penalty.append(max(float(day.get('Roguing_Yield_Penalty', 0.0) or 0.0) for day in run_hist))
            ensemble_roguing_benefit.append(max(float(day.get('Roguing_Inoculum_Benefit', 0.0) or 0.0) for day in run_hist))
            ensemble_roguing_cost.append(max(float(day.get('Roguing_Yield_Cost', 0.0) or 0.0) for day in run_hist))
            ensemble_final_grid += run_hist[-1]['Grid_Incidence']
            
        y_arr = np.array(ensemble_yields)
        i_arr = np.array(ensemble_incidence)
        y_mean = np.mean(y_arr, axis=0)
        i_mean = np.mean(i_arr, axis=0)
        raw_y_std = np.std(y_arr, axis=0)
        raw_i_std = np.std(i_arr, axis=0)
        uncertainty_profile = self._operational_uncertainty_profile(config, crop_p)
        yield_ci_floor = np.maximum(
            y_mean * uncertainty_profile['yield_ci_fraction_95'],
            uncertainty_profile['yield_abs_ci95_t_ha']
        )
        incidence_ci_floor = np.full_like(i_mean, uncertainty_profile['incidence_ci95_abs'], dtype=float)
        y_std = np.maximum(raw_y_std, yield_ci_floor / 1.96)
        i_std = np.maximum(raw_i_std, incidence_ci_floor / 1.96)
        
        stats = {
            'Date': dates,
            'Yield_Mean': y_mean,
            'Yield_Std': y_std,
            'Yield_Std_Raw': raw_y_std,
            'Incidence_Mean': i_mean,
            'Incidence_Std': i_std,
            'Incidence_Std_Raw': raw_i_std,
            'Uncertainty_Profile': uncertainty_profile,
            'Roguing_Applied_Probability': float(np.mean(ensemble_roguing_applied)) if ensemble_roguing_applied else 0.0,
            'Roguing_Yield_Penalty_Mean': float(np.mean(ensemble_roguing_penalty)) if ensemble_roguing_penalty else 0.0,
            'Roguing_Inoculum_Benefit_Mean': float(np.mean(ensemble_roguing_benefit)) if ensemble_roguing_benefit else 0.0,
            'Roguing_Yield_Cost_Mean': float(np.mean(ensemble_roguing_cost)) if ensemble_roguing_cost else 0.0,
            'Final_Grid_Mean': ensemble_final_grid / n_runs,
            'Biomass_Potential': [b['cumulative_perfect'] for b in bio_history] 
        }
        growth_choice = self.growth_selector.select(config, crop_p)
        return {
            'ensemble_stats': stats,
            'triangulation': triang,
            'field_poly': field_poly,
            'crop_params': crop_p,
            'growth_model': growth_choice.to_dict(),
            'disease_model': last_disease_model_choice
        }

    def _scenario_harvest_summary(self, stats, crop_p):
        """Summarise scenario yield over the economically relevant harvest horizon.

        Annual crops use the final simulated yield.  Perennial crops can have many
        harvest opportunities inside the 20-year simulation, so downstream
        economics needs the annual peak yield list rather than only the last day.
        """
        dates = pd.to_datetime(stats.get('Date', []))
        yields = np.asarray(stats.get('Yield_Mean', []), dtype=float)
        if len(yields) == 0:
            return {'annual_yields_t_ha': [], 'horizon_yield_t_ha': 0.0}
        if str(crop_p.get('Type', 'Annual')) != 'Perennial':
            final_yield = float(yields[-1])
            return {'annual_yields_t_ha': [final_yield], 'horizon_yield_t_ha': final_yield}
        if len(dates) != len(yields):
            annual = [float(np.max(yields))]
            return {'annual_yields_t_ha': annual, 'horizon_yield_t_ha': float(sum(annual))}
        start = dates.min()
        buckets = {}
        for d, y in zip(dates, yields):
            year_index = int(max(0, (d - start).days) // 365) + 1
            if 1 <= year_index <= 20:
                buckets[year_index] = max(float(y), buckets.get(year_index, 0.0))
        annual = [float(buckets.get(year, 0.0)) for year in range(1, 21)]
        return {'annual_yields_t_ha': annual, 'horizon_yield_t_ha': float(sum(annual))}

    def run_counterfactual_scenarios(self, config, n_runs=20):
        """Compare no action with optimized management for the PDF workflow.

        Scenario ensembles are one of the most expensive report-generation steps.
        Keeping only the baseline and optimized management paths preserves the
        decision contrast while avoiding the extra minimum/intermediate ensemble
        runs that made small fields wait too long.
        """
        scenarios = {}
        scenario_defs = [
            ('none', 'No action'),
            ('optimized', 'Optimized Management'),
        ]

        opt_irr, _ = self.optimize_irrigation_schedule(config)
        opt_fert = self.optimize_fertilization_schedule(config)

        for strategy, label in scenario_defs:
            scenario_config = config.copy()
            scenario_config['disease_control_strategy'] = strategy
            if strategy == 'optimized':
                scenario_config['irr_schedule'] = opt_irr
                scenario_config['fert_schedule'] = opt_fert

            ens = self.run_ensemble_inference(scenario_config, n_runs=n_runs)
            if ens is None:
                scenarios[strategy] = {'label': label, 'available': False}
                continue
            stats = ens['ensemble_stats']
            final_yield = float(stats['Yield_Mean'][-1]) if len(stats['Yield_Mean']) else 0.0
            final_incidence = float(stats['Incidence_Mean'][-1]) if len(stats['Incidence_Mean']) else 0.0
            harvest_summary = self._scenario_harvest_summary(stats, ens.get('crop_params', {}))
            scenarios[strategy] = {
                'label': label,
                'available': True,
                'final_yield': final_yield,
                'annual_yields_t_ha': harvest_summary['annual_yields_t_ha'],
                'horizon_yield_t_ha': harvest_summary['horizon_yield_t_ha'],
                'final_incidence': final_incidence,
                'yield_std': float(stats['Yield_Std'][-1]) if len(stats['Yield_Std']) else 0.0,
                'roguing_applied_probability': float(stats.get('Roguing_Applied_Probability', 0.0)),
                'roguing_yield_penalty': float(stats.get('Roguing_Yield_Penalty_Mean', 0.0)),
                'roguing_inoculum_benefit': float(stats.get('Roguing_Inoculum_Benefit_Mean', 0.0)),
                'roguing_yield_cost': float(stats.get('Roguing_Yield_Cost_Mean', 0.0)),
                'growth_model': ens.get('growth_model', {}),
                'disease_model': ens.get('disease_model', {}),
            }
        return scenarios

    # ... (Optimization methods remain the same, just ensured they use the new _prepare_physics) ...
    def optimize_irrigation_schedule(self, config):
        res_physics = self._prepare_physics(config)
        if res_physics is None: return [], 0.0
        crop_p, weather, base_hist = res_physics
        
        max_irr_limit = float(crop_p.get('Max_Irr_Event_mm', 40.0))
        feasible_mm, feasibility_note = max_irrigation_mm_per_event(config, config.get('area_ha', 1.0))
        if feasible_mm != float('inf'):
            max_irr_limit = min(max_irr_limit, feasible_mm)
        if crop_p['Type'] == 'Perennial':
            min_interval_days = 60 
        else:
            min_interval_days = 4 

        soil_layers = config['soil_layers']
        if isinstance(soil_layers, list) and len(soil_layers) > 0:
             total_fc_pct = np.mean([l['field_capacity'] for l in soil_layers])
             total_wp_pct = np.mean([l['wilting_point'] for l in soil_layers])
        elif isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11
        
        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        taw = fc_mm - wp_mm
        conv_factor = 4.0
        init_water_frac = config.get('initial_soil_water', 0.8)
        soil_state = {
            'water_mm': init_water_frac * fc_mm,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        raw_irr = config['irr_schedule']
        if crop_p['Type'] == 'Perennial':
            raw_irr = self._expand_schedule_for_perennials(raw_irr, years=20)
        user_irr_dates = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in raw_irr}
        
        raw_fert = config['fert_schedule']
        if crop_p['Type'] == 'Perennial':
            raw_fert = self._expand_schedule_for_perennials(raw_fert, years=20)
        
        fert_df = pd.DataFrame(raw_fert)
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}
        pruning_days = set()

        if not fert_df.empty and 'product' in fert_df.columns:
            for _, row in fert_df.iterrows():
                d = pd.to_datetime(row['date']).date()
                if 'Canopy Pruning' in row['product']:
                    pruning_days.add(d)
                    continue
                prod_info = next((p for p in self.fert_service.products if p['name'] == row['product']), None)
                if prod_info and prod_info['type'] != 'Operation':
                    amount = float(row['amount'])
                    fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                    fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                    fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)
        
        new_irrigation_log = []
        last_auto_irr_day = -999 
        opt_initial_age = max(0.0, float(config.get('initial_plant_age_years', 0.0) or 0.0)) if crop_p['Type'] == 'Perennial' else 0.0
        opt_capacity = float(crop_p.get('Max_Wood_Capacity', 35.0) or 35.0)
        wood_cum = float(np.clip(opt_capacity * (1.0 - np.exp(-opt_initial_age / 4.0)), 0.0, opt_capacity)) if opt_initial_age > 0 else 0.0
        plant_state = {'lai': 0.0, 'stunting_factor': 1.0, 'cum_dd': 0.0, 'age_days': int(opt_initial_age * 365.0), 'wood_biomass': wood_cum} 
        lat = config.get('center_lat', 0.0)

        for t, row in weather.iterrows():
            curr_date = row['DATE'].date()
            user_input = user_irr_dates.get(curr_date, 0.0)
            rain_input = row['RAIN']
            
            projected_water_mm = soil_state['water_mm'] + user_input + rain_input
            depletion = fc_mm - projected_water_mm
            p = 0.5 
            raw = taw * p 
            
            added_water = 0
            if depletion > raw:
                days_since_last = t - last_auto_irr_day
                if days_since_last >= min_interval_days:
                    refill_target = fc_mm * 0.90
                    req_water = max(0, refill_target - projected_water_mm)
                    actual_app = min(req_water, max_irr_limit)
                    if actual_app > 2.0: 
                        added_water = actual_app
                        new_irrigation_log.append({
                            'date': curr_date,
                            'amount': round(added_water, 1),
                            'reason': 'Stress Mitigation',
                            'feasibility_note': feasibility_note
                        })
                        last_auto_irr_day = t
            
            mgmt_step = {
                'fert_n': fert_n_map, 'fert_p': fert_p_map, 'fert_k': fert_k_map, 
                'irr': user_irr_dates.copy(),
                'pruning': curr_date in pruning_days
            }
            mgmt_step['irr'][curr_date] = user_input + added_water
            
            plant_state['wood_biomass'] = wood_cum
            bio = self.physics.stics_lite_step(t, row, crop_p, soil_state, plant_state, mgmt_step, lat_deg=lat)
            
            if crop_p['Type'] == 'Perennial':
                wood_cum += bio['d_wood_t_ha']
                if wood_cum < 0: wood_cum = 0

        df_log = pd.DataFrame(new_irrigation_log)
        if df_log.empty: return [], soil_state['water_mm']
            
        df_log['date'] = pd.to_datetime(df_log['date'])
        df_log['Week_Num'] = df_log['date'].dt.isocalendar().week
        df_log['Year'] = df_log['date'].dt.year
        
        schedule_agg = df_log.groupby(['Year', 'Week_Num']).agg({
            'date': 'min', 'amount': 'sum'
        }).reset_index().sort_values('date')
        
        final_schedule = []
        for _, row in schedule_agg.iterrows():
            final_schedule.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'amount': float(row['amount']),
                'week': int(row['Week_Num'])
            })
            
        return final_schedule, soil_state['water_mm'] 

    def optimize_fertilization_schedule(self, config):
        res_physics = self._prepare_physics(config)
        if res_physics is None: return []
        crop_p, weather, base_hist = res_physics
        
        soil_layers = config['soil_layers']
        if isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11
        
        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        conv_factor = 4.0
        
        init_water_frac = config.get('initial_soil_water', 0.8)
        soil_state = {
            'water_mm': init_water_frac * fc_mm,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }

        raw_irr = config['irr_schedule']
        if crop_p['Type'] == 'Perennial':
            raw_irr = self._expand_schedule_for_perennials(raw_irr, years=20)
        irr_map = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in raw_irr}

        raw_fert = config['fert_schedule']
        if crop_p['Type'] == 'Perennial':
            raw_fert = self._expand_schedule_for_perennials(raw_fert, years=20)

        fert_df = pd.DataFrame(raw_fert)
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}
        pruning_days = set()

        if not fert_df.empty and 'product' in fert_df.columns:
            for _, row in fert_df.iterrows():
                d = pd.to_datetime(row['date']).date()
                if 'Canopy Pruning' in row['product']:
                    pruning_days.add(d)
                    continue
                prod_info = next((p for p in self.fert_service.products if p['name'] == row['product']), None)
                if prod_info and prod_info['type'] != 'Operation':
                    amount = float(row['amount'])
                    fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                    fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                    fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)

        rec_log = []
        last_fert_day = -45
        min_interval_days = 45
        plant_state = {'lai': 0.0, 'stunting_factor': 1.0, 'cum_dd': 0.0, 'age_days': 0, 'wood_biomass': 0.0}
        wood_cum = 0.0
        lat = config.get('center_lat', 0.0)

        for i, (t, row) in enumerate(weather.iterrows()):
            curr_date = row['DATE'].date()
            mgmt_step = {
                'fert_n': fert_n_map, 'fert_p': fert_p_map, 'fert_k': fert_k_map,
                'irr': irr_map,
                'pruning': curr_date in pruning_days
            }
            
            stress_n = soil_state['n_kg'] < 15.0
            stress_p = soil_state['p_kg'] < 8.0
            stress_k = soil_state['k_kg'] < 12.0
            
            if crop_p['Type'] == 'Perennial':
                is_active_growth = True
            else:
                progress = i / int(crop_p['Cycle_Days'])
                is_active_growth = 0.15 < progress < 0.85 
            
            if is_active_growth and (stress_n or stress_p or stress_k):
                def_n = max(0, 40.0 - soil_state['n_kg'])
                def_p = max(0, 20.0 - soil_state['p_kg'])
                def_k = max(0, 30.0 - soil_state['k_kg'])
                
                if (i - last_fert_day) >= min_interval_days:
                    product_name, amount_kg_ha, rationale = self.fert_service.recommend_product(def_n, def_p, def_k)
                    if product_name and amount_kg_ha > 10: 
                        rec_log.append({
                            'date': curr_date,
                            'product': product_name,
                            'amount': amount_kg_ha,
                            'rationale': rationale
                        })
                        prod_info = next(p for p in self.fert_service.products if p['name'] == product_name)
                        soil_state['n_kg'] += amount_kg_ha * (prod_info['N'] / 100)
                        soil_state['p_kg'] += amount_kg_ha * (prod_info['P'] / 100)
                        soil_state['k_kg'] += amount_kg_ha * (prod_info['K'] / 100)
                        last_fert_day = i
            
            plant_state['wood_biomass'] = wood_cum
            bio = self.physics.stics_lite_step(i, row, crop_p, soil_state, plant_state, mgmt_step, lat_deg=lat)
            
            if crop_p['Type'] == 'Perennial':
                wood_cum += bio['d_wood_t_ha']
                if wood_cum < 0: wood_cum = 0

        if not rec_log: return []
        return rec_log

    def assess_planting_season(self, lat, lon):
        if not st.session_state.get('ee_initialized'): return None
        try:
            df_c = st.session_state.get('df_crops')
            if df_c is None: return None
            crop_id = st.session_state.get('selected_crop_id')
            if not crop_id: return None
            
            crop = df_c[df_c['Crop_ID'] == crop_id].iloc[0]
            cycle_months = int(crop['Cycle_Days'] / 30)
            harvest_limit = crop.get('Harvest_Rain_Limit_mm', 50.0) 
            
            point = ee.Geometry.Point([lon, lat])
            wc = ee.ImageCollection('WORLDCLIM/V1/MONTHLY').select('prec')
            months_img = wc.toBands()
            stats = months_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=5000).getInfo()
            
            rain_data = []
            sorted_keys = sorted(stats.keys()) 
            for k in sorted_keys: rain_data.append(stats[k])
                
            if len(rain_data) != 12: return None
            rain_extended = rain_data + rain_data 
            
            best_score = -float('inf')
            best_month_idx = 0
            best_harvest_rain = 0
            
            for start_m in range(12):
                end_m = start_m + cycle_months
                veg_rain = sum(rain_extended[start_m : end_m])
                harvest_rain = rain_extended[end_m]
                penalty = 0
                if harvest_rain > harvest_limit: penalty = (harvest_rain - harvest_limit) * 10
                score = veg_rain - penalty
                if score > best_score:
                    best_score = score
                    best_month_idx = start_m
                    best_harvest_rain = harvest_rain

            month_names = ["January", "February", "March", "April", "May", "June", 
                           "July", "August", "September", "October", "November", "December"]
            rec_month = month_names[best_month_idx]
            harvest_month = month_names[(best_month_idx + cycle_months) % 12]
            status = "Safe" if best_harvest_rain <= harvest_limit else "Risk (Wet Harvest)"
                
            advice = (
                f"Optimal Planting: **{rec_month}** (Harvest in {harvest_month}).\n"
                f"Rationale: Maximizes vegetative rainfall while targeting a harvest month with "
                f"**{int(best_harvest_rain)}mm** rain (Limit: {int(harvest_limit)}mm).\n"
                f"Status: {status}."
            )
            return {
                'best_month': rec_month,
                'peak_rain_mm': int(best_score),
                'advice': advice
            }
        except Exception as e:
            print(f"Seasonality Error: {e}")
            return None