# src/models/simulation_engine.py
import numpy as np
import pandas as pd
import streamlit as st
from datetime import date
from scipy.signal import convolve2d
from scipy.spatial import Delaunay
from matplotlib.tri import Triangulation
from matplotlib.path import Path
import ee

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
        CONVERTS mg/kg inputs to kg/ha for the internal physics engine.
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

        # 3. Initialize State with N, P, K (CONVERSION HERE)
        # Unit Conversion: mg/kg (ppm) -> kg/ha
        # We use a conservative factor of 4.0 (assuming 1.3 bulk density, ~30cm topsoil effective zone)
        conv_factor = 4.0 
        
        soil_state = {
            'water_mm': init_water,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
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
                'N_kg': bio.get('n_kg', 0),
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

    # --- IRRIGATION OPTIMIZER ---
    def optimize_irrigation_schedule(self, config):
        """
        Reactive Optimization: Detects daily stress (Depletion > RAW) and prescribes irrigation.
        Ignores stress if user has ALREADY scheduled irrigation for that day.
        """
        # 1. Run baseline to get weather and determine soil properties
        crop_p, weather, base_hist = self._prepare_physics(config)
        
        soil_layers = config['soil_layers']
        # Handle formats
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
        
        # 2. Re-initialize Soil State (Correctly including NPK)
        conv_factor = 4.0
        soil_state = {
            'water_mm': config['initial_soil_water'] * fc_mm,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        # Prepare Inputs
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
            
            # --- CRITICAL FIX: Look ahead at today's scheduled inputs ---
            # Get what the user (or rain) is already providing today
            user_input = user_irr_dates.get(curr_date, 0.0)
            rain_input = row['RAIN']
            
            # Calculate what the water level WOULD be after these inputs
            projected_water_mm = soil_state['water_mm'] + user_input + rain_input
            
            # Check depletion based on the PROJECTED water level
            depletion = fc_mm - projected_water_mm
            raw = taw * 0.5 # p = 0.5
            
            added_water = 0
            
            # Trigger ONLY if still stressed *after* user inputs
            if depletion > raw:
                # Target: Refill to 90% Field Capacity
                refill_target = fc_mm * 0.90
                # Calculate strictly the deficit remaining
                req_water = max(0, refill_target - projected_water_mm)
                
                # Minimum viable application threshold
                if req_water > 10: 
                    added_water = req_water
                    new_irrigation_log.append({
                        'date': curr_date,
                        'amount': round(added_water, 1),
                        'reason': 'Stress Mitigation'
                    })
            
            # Construct MGMT Step (User Inputs + Added Optimization Water)
            mgmt_step = {
                'fert_n': fert_n_map,
                'fert_p': fert_p_map,
                'fert_k': fert_k_map,
                'irr': user_irr_dates.copy() 
            }
            
            # Inject the total water (User + Optimizer) for the physics step
            total_irrigation = user_input + added_water
            mgmt_step['irr'][curr_date] = total_irrigation
            
            # Run Physics Step to advance state correctly
            self.physics.stics_lite_step(t, row, crop_p, soil_state, mgmt_step)

        # 4. Aggregate Results
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

    # --- UPDATED: SEASONALITY ANALYZER (Rain-Window Matching) ---
    def assess_planting_season(self, lat, lon):
        """
        Finds the optimal planting month by balancing:
        1. High rainfall during vegetative growth.
        2. Low rainfall during harvest (quality preservation).
        """
        if not st.session_state.get('ee_initialized'):
            return None
            
        try:
            # 1. Get Crop Constraints
            df_c = st.session_state.get('df_crops')
            if df_c is None: return None
            
            # Use currently selected crop
            crop_id = st.session_state.get('selected_crop_id')
            if not crop_id: return None
            
            crop = df_c[df_c['Crop_ID'] == crop_id].iloc[0]
            cycle_months = int(crop['Cycle_Days'] / 30)
            harvest_limit = crop.get('Harvest_Rain_Limit_mm', 50.0) # Default 50mm if missing
            
            # 2. Get Climatology (WorldClim)
            point = ee.Geometry.Point([lon, lat])
            wc = ee.ImageCollection('WORLDCLIM/V1/MONTHLY').select('prec')
            months_img = wc.toBands()
            stats = months_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=5000).getInfo()
            
            # Extract and sort data (WorldClim keys are 01_prec, 02_prec...)
            rain_data = []
            # Robust extraction assuming keys contain '01', '02', etc.
            # Create a sorted list of values based on key string analysis
            sorted_keys = sorted(stats.keys()) 
            # Note: sorting works if keys are '01_prec', '02_prec'. 
            # If WorldClim V1 uses 'prec_01', it also works.
            for k in sorted_keys:
                rain_data.append(stats[k])
                
            if len(rain_data) != 12: return None
            
            # Extend array for circular year (Jan-Dec-Jan...)
            # We add enough months to cover a crop cycle starting in Dec
            rain_extended = rain_data + rain_data 
            
            # 3. Optimization Loop
            best_score = -float('inf')
            best_month_idx = 0
            best_harvest_rain = 0
            
            # Check every possible start month (0 to 11)
            for start_m in range(12):
                # Define Cycle Window
                end_m = start_m + cycle_months
                
                # Vegetative Phase (Start to End-1)
                veg_rain = sum(rain_extended[start_m : end_m])
                
                # Harvest Month (The last month of the cycle)
                harvest_rain = rain_extended[end_m]
                
                # Scoring Logic:
                # Reward: Vegetative Rain
                # Penalty: Harvest Rain (Exponential penalty if above limit)
                
                # Binary Constraint: If harvest rain > limit, this window is RISKY.
                # However, we prefer the "Least Risky" valid window.
                
                penalty = 0
                if harvest_rain > harvest_limit:
                    penalty = (harvest_rain - harvest_limit) * 10 # Heavy penalty per mm excess
                
                score = veg_rain - penalty
                
                if score > best_score:
                    best_score = score
                    best_month_idx = start_m
                    best_harvest_rain = harvest_rain

            # 4. Result Formatting
            month_names = ["January", "February", "March", "April", "May", "June", 
                           "July", "August", "September", "October", "November", "December"]
            
            rec_month = month_names[best_month_idx]
            harvest_month = month_names[(best_month_idx + cycle_months) % 12]
            
            status = "Safe"
            if best_harvest_rain > harvest_limit:
                status = "Risk (Wet Harvest)"
                
            advice = (
                f"Optimal Planting: **{rec_month}** (Harvest in {harvest_month}).\n"
                f"Rationale: Maximizes vegetative rainfall while targeting a harvest month with "
                f"**{int(best_harvest_rain)}mm** rain (Limit: {int(harvest_limit)}mm). "
                f"Status: {status}."
            )
            
            return {
                'best_month': rec_month,
                'peak_rain_mm': int(best_score), # Abstract score
                'advice': advice
            }
            
        except Exception as e:
            print(f"Seasonality Error: {e}")
            return None