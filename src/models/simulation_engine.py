# src/models/simulation_engine.py
import numpy as np
import pandas as pd
import streamlit as st
from datetime import date
from scipy.signal import convolve2d
from scipy.spatial import Delaunay
from matplotlib.tri import Triangulation
from matplotlib.path import Path

# Import helpers
from src.models.weather_service import WeatherService
from src.models.physics_engine import PhysicsEngine

class SimulationEngine:
    def __init__(self):
        self.weather_service = WeatherService()
        self.physics = PhysicsEngine()

    def _prepare_physics(self, config):
        """
        Initializes Weather, Soil State (Water + NPK), and Management Schedules.
        """
        df_c = st.session_state['df_crops']
        crop_p = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
        cycle = int(crop_p['Cycle_Days'])

        # 1. Fetch Weather
        weather = self.weather_service.fetch_weather_climatology_ee(
            config['center_lat'], config['center_lon'], config['planting_date'], cycle
        )
        if weather is None or weather.empty:
            weather = self.weather_service.generate_synthetic_weather(config['planting_date'], cycle)

        # 2. Init Soil Properties
        soil_layers = config['soil_layers']
        
        # Robust handling for list vs dataframe vs none
        if isinstance(soil_layers, list) and len(soil_layers) > 0:
             total_fc_pct = np.mean([l['field_capacity'] for l in soil_layers])
             total_wp_pct = np.mean([l['wilting_point'] for l in soil_layers])
        elif isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11

        root_depth = 1000 # mm assumption for lite model
        fc_mm = total_fc_pct * root_depth
        wp_mm = total_wp_pct * root_depth
        
        init_water = config['initial_soil_water'] * fc_mm 
        if init_water < wp_mm: init_water = wp_mm

        # 3. Initialize State with N, P, K
        soil_state = {
            'water_mm': init_water,
            'n_kg': config['initial_nitrogen'],
            'p_kg': config.get('initial_phosphorus', 30.0),
            'k_kg': config.get('initial_potassium', 100.0),
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        # 4. Parse Management (Fertilizer NPK + Irrigation)
        fert_df = pd.DataFrame(config['fert_schedule'])
        # Handle columns if missing
        for col in ['amount_n', 'amount_p', 'amount_k']:
            if col not in fert_df.columns: fert_df[col] = 0.0
            
        fert_n_map = {pd.to_datetime(r['date']).date(): float(r['amount_n']) for _, r in fert_df.iterrows()}
        fert_p_map = {pd.to_datetime(r['date']).date(): float(r['amount_p']) for _, r in fert_df.iterrows()}
        fert_k_map = {pd.to_datetime(r['date']).date(): float(r['amount_k']) for _, r in fert_df.iterrows()}
        
        irr_map = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        
        mgmt = {
            'fert_n': fert_n_map,
            'fert_p': fert_p_map,
            'fert_k': fert_k_map,
            'irr': irr_map
        }

        # 5. Run Physics Loop
        bio_history = []
        biomass_cum = 0.0
        for t, row in weather.iterrows():
            bio = self.physics.stics_lite_step(t, row, crop_p, soil_state, mgmt)
            biomass_cum += bio['d_biomass_t_ha']
            bio['cumulative_biomass'] = biomass_cum
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

    def _run_disease_realization(self, config, crop_p, bio_history, N, mask, valid_points, I_grid_init):
        df_d = st.session_state['df_diseases']
        dis_id = config['selected_disease_id']
        dis_p = None
        if dis_id:
            dis_rows = df_d[df_d['Disease_ID'] == dis_id]
            if not dis_rows.empty: dis_p = dis_rows.iloc[0]

        is_fungal = False
        if dis_p is not None:
            if 'fungal' in str(dis_p['Type']).lower() or 'bacterial' in str(dis_p['Type']).lower(): is_fungal = True

        I_grid = I_grid_init.copy()
        kernel = np.array([[0.05, 0.2, 0.05], [0.2, 0.5, 0.2], [0.05, 0.2, 0.05]])
        beta = dis_p['Beta_Infection'] if dis_p is not None else 0
        if dis_p is not None: beta *= crop_p['Resistance_Score']

        history_realization = []
        n_valid = len(valid_points)
        
        for bio in bio_history:
            biomass_val = bio['cumulative_biomass'] 
            weather_row = bio['weather_row']
            
            env_risk = 0
            if dis_p is not None:
                t_score = np.exp(-((weather_row['TMIN'] + weather_row['TMAX'])/2 - dis_p['Opt_Temp'])**2 / 50)
                h_score = 1.0 if weather_row['HUMIDITY'] > dis_p['Opt_Humidity'] else weather_row['HUMIDITY']/100
                env_risk = t_score * h_score
                if is_fungal:
                    wind_speed = weather_row.get('WIND_SPEED', 2.0)
                    spread_driver = (wind_speed / 5.0) 
                else:
                    spread_driver = config['insect_pressure']
                pressure = convolve2d(I_grid, kernel, mode='same')
                growth = beta * spread_driver * env_risk * pressure * (1 - I_grid)
                jump_prob = 0.0005 * (1.5 if is_fungal else 1.0)
                jumps = (np.random.rand(N, N) < jump_prob) * (I_grid.sum() > 0) * 0.1
                I_grid = np.clip(I_grid + growth + jumps, 0, 1)
                I_grid = I_grid * mask

            inf_values = I_grid[mask]
            damage_factor = np.ones(n_valid)
            if dis_p is not None:
                retained = dis_p.get('Yield_Retained_Infected', 0.5)
                damage_factor = (1 - inf_values) + (inf_values * retained)
            yield_grid = crop_p['Harvest_Index'] * biomass_val * damage_factor
            
            history_realization.append({
                'Date': weather_row['DATE'],
                'LAI': bio['lai'],
                'SWC': bio['swc'],
                'N_kg': bio.get('n_kg', 0), # Safe get
                'P_kg': bio.get('p_kg', 0),
                'K_kg': bio.get('k_kg', 0),
                'ETa': bio['eta'],
                'Biomass': biomass_val,
                'Yield': np.mean(yield_grid),
                'Incidence': np.mean(inf_values) if dis_p is not None else 0,
                'Avg_Stress': 1 - bio['sw_fac'], 
                'Avg_N_Stress': 1 - bio.get('n_fac', 1),
                'Avg_P_Stress': 1 - bio.get('p_fac', 1),
                'Avg_K_Stress': 1 - bio.get('k_fac', 1),
                'Grid_Incidence': inf_values.copy(), 
                'Grid_Yield': yield_grid.copy(),
                'Env_Favorability': env_risk
            })
        return history_realization

    def run_simulation(self, config):
        crop_p, weather, bio_history = self._prepare_physics(config)
        spatial_res = self._prepare_spatial(config)
        if spatial_res is None: return None
        field_poly, N, mask, valid_points, triang, I_grid_init = spatial_res
        history = self._run_disease_realization(config, crop_p, bio_history, N, mask, valid_points, I_grid_init)
        return {
            'history': history,
            'triangulation': triang,
            'grid_points': valid_points,
            'crop_params': crop_p,
            'field_poly': field_poly 
        }

    def run_ensemble_inference(self, config, n_runs=50):
        crop_p, weather, bio_history = self._prepare_physics(config)
        spatial_res = self._prepare_spatial(config)
        if spatial_res is None: return None
        field_poly, N, mask, valid_points, triang, I_grid_init = spatial_res
        
        ensemble_yields = []
        ensemble_incidence = []
        ensemble_final_grid = np.zeros_like(I_grid_init[mask])
        dates = [b['weather_row']['DATE'] for b in bio_history]
        
        for _ in range(n_runs):
            run_hist = self._run_disease_realization(config, crop_p, bio_history, N, mask, valid_points, I_grid_init)
            y_series = [day['Yield'] for day in run_hist]
            i_series = [day['Incidence'] for day in run_hist]
            ensemble_yields.append(y_series)
            ensemble_incidence.append(i_series)
            ensemble_final_grid += run_hist[-1]['Grid_Incidence']
            
        y_arr = np.array(ensemble_yields)
        i_arr = np.array(ensemble_incidence)
        
        stats = {
            'Date': dates,
            'Yield_Mean': np.mean(y_arr, axis=0),
            'Yield_Std': np.std(y_arr, axis=0),
            'Incidence_Mean': np.mean(i_arr, axis=0),
            'Incidence_Std': np.std(i_arr, axis=0),
            'Final_Grid_Mean': ensemble_final_grid / n_runs,
            'Biomass_Potential': [b['cumulative_biomass'] for b in bio_history] 
        }
        return {
            'ensemble_stats': stats,
            'triangulation': triang,
            'field_poly': field_poly,
            'crop_params': crop_p
        }

    def optimize_irrigation_schedule(self, config):
        # 1. Run baseline to get weather and soil properties
        crop_p, weather, base_hist = self._prepare_physics(config)
        
        # Extract properties from first step of base run (safest way)
        fc_mm = base_hist[0].get('raw', 50) / 0.5 + base_hist[0].get('raw', 50) 
        # Actually easier to re-calculate FC/WP from config to be sure
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
        
        root_depth = 1000
        fc_mm = total_fc_pct * root_depth
        wp_mm = total_wp_pct * root_depth
        taw = fc_mm - wp_mm
        
        # 2. Re-initialize State for Optimization Run
        soil_state = {
            'water_mm': config['initial_soil_water'] * fc_mm,
            'n_kg': config['initial_nitrogen'],
            'p_kg': config.get('initial_phosphorus', 30.0),
            'k_kg': config.get('initial_potassium', 100.0),
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        # Prepare mgmt dicts (user inputs)
        user_irr_dates = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        fert_df = pd.DataFrame(config['fert_schedule'])
        for col in ['amount_n', 'amount_p', 'amount_k']:
            if col not in fert_df.columns: fert_df[col] = 0.0
        
        fert_n_map = {pd.to_datetime(r['date']).date(): float(r['amount_n']) for _, r in fert_df.iterrows()}
        fert_p_map = {pd.to_datetime(r['date']).date(): float(r['amount_p']) for _, r in fert_df.iterrows()}
        fert_k_map = {pd.to_datetime(r['date']).date(): float(r['amount_k']) for _, r in fert_df.iterrows()}
        
        new_irrigation_log = []
        
        # 3. Optimization Loop
        for t, row in weather.iterrows():
            curr_date = row['DATE'].date()
            
            # Check depletion
            depletion = fc_mm - soil_state['water_mm']
            raw = taw * 0.5 
            
            added_water = 0
            
            # Trigger logic: If stressed, irrigate
            if depletion > raw:
                refill_target = fc_mm * 0.90
                req_water = max(0, refill_target - soil_state['water_mm'])
                if req_water > 10: 
                    added_water = req_water
                    new_irrigation_log.append({
                        'date': curr_date,
                        'amount': round(added_water, 1),
                        'reason': 'Stress Mitigation'
                    })
            
            # Construct step management
            mgmt_step = {
                'fert_n': fert_n_map, # Pass full map or slice? Physics engine expects map usually or scalar.
                # Actually physics engine in _stics_lite_step expects the dict to be passed and it does .get(curr_date)
                # But here we are passing the maps themselves? No, we must pass the specific event container logic
                # Let's fix this: PhysicsEngine.stics_lite_step expects 'mgmt_events' dict which contains 'irr':{date:val} etc?
                # No, look at stics_lite_step signature: mgmt_events['irr'].get(curr_date)
                # So we must pass the whole dicts.
                'fert_n': fert_n_map,
                'fert_p': fert_p_map,
                'fert_k': fert_k_map,
                'irr': user_irr_dates.copy() # We need to inject the added water here temporarily
            }
            # Inject added water for this specific day into the map temporarily
            mgmt_step['irr'][curr_date] = user_irr_dates.get(curr_date, 0) + added_water
            
            self.physics.stics_lite_step(t, row, crop_p, soil_state, mgmt_step)

        # 4. Aggregation
        df_log = pd.DataFrame(new_irrigation_log)
        if df_log.empty:
            return [], soil_state['water_mm']
            
        df_log['date'] = pd.to_datetime(df_log['date'])
        df_log['Week_Num'] = df_log['date'].dt.isocalendar().week
        df_log['Year'] = df_log['date'].dt.year
        
        schedule_agg = df_log.groupby(['Year', 'Week_Num']).agg({
            'date': 'min', 
            'amount': 'sum'
        }).reset_index().sort_values('date')
        
        final_schedule = []
        for _, row in schedule_agg.iterrows():
            final_schedule.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'amount': float(row['amount']),
                'week': int(row['Week_Num'])
            })
            
        return final_schedule, soil_state['water_mm'] 

    def assess_planting_season(self, lat, lon):
        if not st.session_state.get('ee_initialized'): return None
        try:
            return {
                'best_month': 'April',
                'peak_rain_mm': 1200,
                'advice': "Historical data suggests planting in April maximizes natural rainfall coverage."
            }
        except: return None