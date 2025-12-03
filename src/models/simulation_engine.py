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
from src.models.fertilizer_service import FertilizerService

class SimulationEngine:
    def __init__(self):
        self.weather_service = WeatherService()
        self.physics = PhysicsEngine()
        self.fert_service = FertilizerService()

    def _prepare_physics(self, config):
        """
        Initializes Weather, Soil State (Water + NPK), and Management Schedules.
        Correctly scales soil bucket to CROP ROOT DEPTH.
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
        
        if isinstance(soil_layers, list) and len(soil_layers) > 0:
             total_fc_pct = np.mean([l['field_capacity'] for l in soil_layers])
             total_wp_pct = np.mean([l['wilting_point'] for l in soil_layers])
        elif isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11

        # FIX: Use Crop Specific Root Depth (mm)
        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        
        # Initial water is fraction of this specific root zone
        init_water = config['initial_soil_water'] * fc_mm 
        if init_water < wp_mm: init_water = wp_mm

        # 3. Initialize State
        conv_factor = 4.0 
        
        soil_state = {
            'water_mm': init_water,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        # 4. Parse Management
        fert_df = pd.DataFrame(config['fert_schedule'])
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}

        if not fert_df.empty:
            if 'product' in fert_df.columns:
                for _, row in fert_df.iterrows():
                    d = pd.to_datetime(row['date']).date()
                    prod_name = row['product']
                    amount = float(row['amount'])
                    prod_info = next((p for p in self.fert_service.products if p['name'] == prod_name), None)
                    if prod_info:
                        fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                        fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                        fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)
            else:
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
        biomass_perfect_cum = 0.0 # Accumulator for genetic potential
        
        # --- CRITICAL: Initialize Plant State for new Physics Logic ---
        plant_state = {
            'lai': 0.0, 
            'stunting_factor': 1.0, 
            'cum_dd': 0.0
        }

        for t, row in weather.iterrows():
            # Pass plant_state to allow dynamic LAI feedback
            bio = self.physics.stics_lite_step(t, row, crop_p, soil_state, plant_state, mgmt)
            
            biomass_cum += bio['d_biomass_t_ha']
            
            # Accumulate perfect (no-stress) biomass for benchmarking
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

        I_grid = np.zeros((N, N))
        
        try:
            detect_date = pd.to_datetime(config['detection_date']).date()
        except:
            detect_date = bio_history[0]['weather_row']['DATE'].date()

        kernel = np.array([[0.05, 0.2, 0.05], [0.2, 0.5, 0.2], [0.05, 0.2, 0.05]])
        beta = dis_p['Beta_Infection'] if dis_p is not None else 0
        if dis_p is not None: beta *= crop_p['Resistance_Score']

        history_realization = []
        n_valid = len(valid_points)
        
        for bio in bio_history:
            biomass_val = bio['cumulative_biomass'] 
            weather_row = bio['weather_row']
            curr_date = weather_row['DATE'].date()
            
            env_risk = 0
            if dis_p is not None:
                t_score = np.exp(-((weather_row['TMIN'] + weather_row['TMAX'])/2 - dis_p['Opt_Temp'])**2 / 50)
                h_score = 1.0 if weather_row['HUMIDITY'] > dis_p['Opt_Humidity'] else weather_row['HUMIDITY']/100
                env_risk = t_score * h_score

            if curr_date < detect_date:
                pass 
            elif curr_date == detect_date:
                I_grid = np.maximum(I_grid, I_grid_init)
            else:
                if dis_p is not None:
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
            if dis_p is not None and np.mean(inf_values) > 0:
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
            'Biomass_Potential': [b['cumulative_perfect'] for b in bio_history] 
        }
        return {
            'ensemble_stats': stats,
            'triangulation': triang,
            'field_poly': field_poly,
            'crop_params': crop_p
        }

    def optimize_irrigation_schedule(self, config):
        """
        Reactive Optimization with constraints.
        Constraints:
        1. Soil Capacity (90% FC)
        2. System Limit (Max_Irr_Event_mm)
        3. Cycle Time (4-day min interval)
        """
        # 1. Run baseline to get weather and determine soil properties
        crop_p, weather, base_hist = self._prepare_physics(config)
        
        # CONSTRAINT A: Max System Capacity per Event
        max_irr_limit = float(crop_p.get('Max_Irr_Event_mm', 40.0))
        
        # CONSTRAINT B: Minimum Return Interval (Days)
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
        
        # UPDATED: Use Crop Root Depth
        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        taw = fc_mm - wp_mm
        
        conv_factor = 4.0
        soil_state = {
            'water_mm': config['initial_soil_water'] * fc_mm,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }
        
        user_irr_dates = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        fert_df = pd.DataFrame(config['fert_schedule'])
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}
        if not fert_df.empty:
            if 'product' in fert_df.columns:
                for _, row in fert_df.iterrows():
                    d = pd.to_datetime(row['date']).date()
                    prod_name = row['product']
                    amount = float(row['amount'])
                    prod_info = next((p for p in self.fert_service.products if p['name'] == prod_name), None)
                    if prod_info:
                        fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                        fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                        fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)
        
        new_irrigation_log = []
        last_auto_irr_day = -999 
        
        # --- CRITICAL: Reset Plant State for Optimization Run ---
        plant_state = {'lai': 0.0, 'stunting_factor': 1.0, 'cum_dd': 0.0}

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
                    if actual_app > 10: 
                        added_water = actual_app
                        new_irrigation_log.append({
                            'date': curr_date,
                            'amount': round(added_water, 1),
                            'reason': 'Stress Mitigation'
                        })
                        last_auto_irr_day = t
            
            mgmt_step = {
                'fert_n': fert_n_map, 'fert_p': fert_p_map, 'fert_k': fert_k_map, 'irr': user_irr_dates.copy() 
            }
            total_irrigation = user_input + added_water
            mgmt_step['irr'][curr_date] = total_irrigation
            
            # Pass plant_state
            self.physics.stics_lite_step(t, row, crop_p, soil_state, plant_state, mgmt_step)

        df_log = pd.DataFrame(new_irrigation_log)
        if df_log.empty:
            return [], soil_state['water_mm']
            
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
        """
        Simulates crop growth to identify N-P-K hunger gaps.
        """
        crop_p, weather, base_hist = self._prepare_physics(config)
        
        soil_layers = config['soil_layers']
        if isinstance(soil_layers, pd.DataFrame) and not soil_layers.empty:
             total_fc_pct = soil_layers['field_capacity'].mean()
             total_wp_pct = soil_layers['wilting_point'].mean()
        else:
             total_fc_pct = 0.27
             total_wp_pct = 0.11
        
        # UPDATED: Root Depth
        root_depth_m = float(crop_p.get('Root_Depth_Max_m', 1.0))
        root_depth_mm = root_depth_m * 1000.0
        
        fc_mm = total_fc_pct * root_depth_mm
        wp_mm = total_wp_pct * root_depth_mm
        conv_factor = 4.0
        
        soil_state = {
            'water_mm': config['initial_soil_water'] * fc_mm,
            'n_kg': config['initial_nitrogen'] * conv_factor,
            'p_kg': config.get('initial_phosphorus', 20.0) * conv_factor,
            'k_kg': config.get('initial_potassium', 100.0) * conv_factor,
            'field_capacity_mm': fc_mm,
            'wilting_point_mm': wp_mm
        }

        irr_map = {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        fert_df = pd.DataFrame(config['fert_schedule'])
        fert_n_map, fert_p_map, fert_k_map = {}, {}, {}
        if not fert_df.empty and 'product' in fert_df.columns:
            for _, row in fert_df.iterrows():
                d = pd.to_datetime(row['date']).date()
                prod_name = row['product']
                amount = float(row['amount'])
                prod_info = next((p for p in self.fert_service.products if p['name'] == prod_name), None)
                if prod_info:
                    fert_n_map[d] = fert_n_map.get(d, 0) + (amount * prod_info['N'] / 100.0)
                    fert_p_map[d] = fert_p_map.get(d, 0) + (amount * prod_info['P'] / 100.0)
                    fert_k_map[d] = fert_k_map.get(d, 0) + (amount * prod_info['K'] / 100.0)

        rec_log = []
        last_fert_day = -45
        min_interval_days = 45
        
        # --- CRITICAL: Reset Plant State ---
        plant_state = {'lai': 0.0, 'stunting_factor': 1.0, 'cum_dd': 0.0}

        for i, (t, row) in enumerate(weather.iterrows()):
            curr_date = row['DATE'].date()
            mgmt_step = {
                'fert_n': fert_n_map, 'fert_p': fert_p_map, 'fert_k': fert_k_map,
                'irr': irr_map
            }
            
            stress_n = soil_state['n_kg'] < 15.0
            stress_p = soil_state['p_kg'] < 8.0
            stress_k = soil_state['k_kg'] < 12.0
            
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
            
            # Pass plant_state
            self.physics.stics_lite_step(i, row, crop_p, soil_state, plant_state, mgmt_step)

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