#src\models\simulation_engine.py
import numpy as np
import pandas as pd
import streamlit as st
from datetime import date, timedelta, datetime
from scipy.signal import convolve2d
from scipy.spatial import Delaunay
from matplotlib.tri import Triangulation
from matplotlib.path import Path
import ee
from google.oauth2.service_account import Credentials

class SimulationEngine:
    def __init__(self):
        self._ensure_ee_init()

    def _ensure_ee_init(self):
        if not st.session_state.get('ee_initialized', False):
            try:
                if 'gcp_service_account' in st.secrets:
                    service_account_info = st.secrets["gcp_service_account"]
                    scopes = ['https://www.googleapis.com/auth/earthengine']
                    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                    ee.Initialize(credentials=creds)
                    st.session_state['ee_initialized'] = True
            except:
                pass 

    def _generate_synthetic_weather(self, start_date, duration, lat):
        """Fallback: Generates synthetic weather including wind speed."""
        dates = [datetime.combine(start_date + timedelta(days=i), datetime.min.time()) for i in range(duration)]
        doy = np.array([d.timetuple().tm_yday for d in dates])
        
        t_avg = 25 + 5 * np.sin((doy - 60) * 2 * np.pi / 365)
        t_min = t_avg - 7 + np.random.normal(0, 1, duration)
        t_max = t_avg + 7 + np.random.normal(0, 2, duration)
        rain = (np.random.rand(duration) < 0.3) * np.random.gamma(10, 2, duration)
        rad = 20 - (rain > 0) * 8 + np.random.normal(0, 2, duration)
        rad = np.clip(rad, 5, 30)
        hum = 60 + (rain > 0) * 20 + np.random.normal(0, 5, duration)
        
        # Synthetic Wind Speed (m/s)
        # Gamma distribution for wind (skewed towards lower speeds with occasional gusts)
        wind = np.random.gamma(3, 1.5, duration) 
        
        return pd.DataFrame({
            'DATE': pd.to_datetime(dates),
            'TMIN': t_min, 'TMAX': t_max,
            'RAIN': rain, 'RADIATION': rad,
            'HUMIDITY': np.clip(hum, 20, 100),
            'WIND_SPEED': wind
        })

    def fetch_weather_climatology_ee(self, lat, lon, start_date, duration):
        """
        Fetches 10-year average climatology including WIND SPEED (ERA5).
        """
        if not st.session_state.get('ee_initialized'):
            return None

        try:
            point = ee.Geometry.Point([lon, lat])
            
            # Fetch 3 years back
            hist_start = start_date.replace(year=start_date.year - 4)
            hist_end = start_date.replace(year=start_date.year - 1)
            
            # ERA5-Land: Temp, Rad, AND Wind Components
            # u_component_of_wind_10m, v_component_of_wind_10m
            era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")\
                .filterDate(str(hist_start), str(hist_end))\
                .filterBounds(point)\
                .select(['temperature_2m_min', 'temperature_2m_max', 
                         'surface_solar_radiation_downwards_sum',
                         'u_component_of_wind_10m', 'v_component_of_wind_10m'])
            
            era5_raw = era5.getRegion(point, 11000).getInfo()
            header = era5_raw[0]
            data = era5_raw[1:]
            df_era = pd.DataFrame(data, columns=header)
            
            df_era['date'] = pd.to_datetime(df_era['time'], unit='ms')
            df_era['TMIN'] = df_era['temperature_2m_min'] - 273.15
            df_era['TMAX'] = df_era['temperature_2m_max'] - 273.15
            df_era['RADIATION'] = df_era['surface_solar_radiation_downwards_sum'] / 1e6
            
            # Calculate Wind Speed Magnitude
            # Speed = sqrt(u^2 + v^2)
            df_era['WIND_SPEED'] = np.sqrt(
                df_era['u_component_of_wind_10m']**2 + 
                df_era['v_component_of_wind_10m']**2
            )
            
            df_era['MM-DD'] = df_era['date'].dt.strftime('%m-%d')
            
            # CHIRPS (Rain)
            chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")\
                .filterDate(str(hist_start), str(hist_end))\
                .filterBounds(point)
                
            chirps_raw = chirps.getRegion(point, 5000).getInfo()
            header_c = chirps_raw[0]
            data_c = chirps_raw[1:]
            df_chirps = pd.DataFrame(data_c, columns=header_c)
            
            df_chirps['date'] = pd.to_datetime(df_chirps['time'], unit='ms')
            df_chirps['RAIN'] = df_chirps['precipitation']
            df_chirps['MM-DD'] = df_chirps['date'].dt.strftime('%m-%d')
            
            # Aggregate to Climatology
            clim_era = df_era.groupby('MM-DD')[['TMIN', 'TMAX', 'RADIATION', 'WIND_SPEED']].mean()
            clim_rain = df_chirps.groupby('MM-DD')[['RAIN']].mean()
            climatology = clim_era.join(clim_rain).fillna(0)
            
            sim_dates = [start_date + timedelta(days=i) for i in range(duration)]
            sim_df_list = []
            
            for d in sim_dates:
                key = d.strftime('%m-%d')
                if key in climatology.index:
                    row = climatology.loc[key]
                    sim_df_list.append({
                        'DATE': pd.Timestamp(d),
                        'TMIN': row['TMIN'], 'TMAX': row['TMAX'],
                        'RAIN': row['RAIN'], 'RADIATION': row['RADIATION'],
                        'WIND_SPEED': row['WIND_SPEED'],
                        'HUMIDITY': 60 + (row['RAIN'] > 0)*20
                    })
                else:
                    sim_df_list.append({
                        'DATE': pd.Timestamp(d),
                        'TMIN': 25, 'TMAX': 30, 'RAIN': 0, 'RADIATION': 20, 
                        'WIND_SPEED': 2.5, 'HUMIDITY': 50
                    })
            
            return pd.DataFrame(sim_df_list)

        except Exception as e:
            print(f"EE Weather Fetch Error: {e}")
            return None

    def _stics_lite_step(self, day_idx, weather_row, crop, soil_state, mgmt_events):
        """Calculates daily biomass growth and stress (STICS-lite)."""
        tmin, tmax = weather_row['TMIN'], weather_row['TMAX']
        rad = weather_row['RADIATION']
        rain = weather_row['RAIN']
        t_avg = (tmin + tmax) / 2
        
        dTT = max(0, t_avg - crop['T_Base'])
        if t_avg > crop['T_Max']: dTT = 0 
        
        pet = 0.0023 * (t_avg + 17.8) * (tmax - tmin)**0.5 * rad
        
        curr_date = weather_row['DATE'].date()
        irr_amount = mgmt_events['irr'].get(curr_date, 0.0)
        fert_amount = mgmt_events['fert'].get(curr_date, 0.0)
        
        soil_state['water_mm'] += (rain + irr_amount)
        soil_state['nitrogen_kg'] += fert_amount
        
        field_cap = soil_state['field_capacity_mm']
        curr_water = soil_state['water_mm']
        
        sw_fac = 1.0
        if curr_water < (field_cap * 0.5):
            sw_fac = max(0, curr_water / (field_cap * 0.5))
            
        eta = pet * sw_fac
        soil_state['water_mm'] = max(0, soil_state['water_mm'] - eta)
        if soil_state['water_mm'] > field_cap: soil_state['water_mm'] = field_cap
            
        n_fac = 1.0
        if soil_state['nitrogen_kg'] < 20: 
            n_fac = max(0, soil_state['nitrogen_kg'] / 20.0)
            
        cycle = crop['Cycle_Days']
        progress = day_idx / cycle
        lai = 0
        if progress < 0.15: lai = 0.5
        elif progress < 0.5: lai = crop['Max_LAI'] * (progress/0.5)
        elif progress < 0.8: lai = crop['Max_LAI']
        else: lai = crop['Max_LAI'] * (1 - (progress-0.8)*5)
        
        ipar = rad * (1 - np.exp(-0.7 * lai))
        d_bio_g_m2 = crop['RUE_g_MJ'] * ipar * sw_fac * n_fac
        
        n_demand = (d_bio_g_m2) * 0.025
        n_uptake = min(soil_state['nitrogen_kg'], n_demand)
        soil_state['nitrogen_kg'] -= n_uptake
        soil_state['nitrogen_kg'] = max(0, soil_state['nitrogen_kg'])
        
        return {
            'd_biomass_t_ha': d_bio_g_m2 * 0.01, 
            'sw_fac': sw_fac, 
            'n_fac': n_fac,
            'lai': lai,
            'eta': eta,
            'swc': soil_state['water_mm'],
            'nmin': soil_state['nitrogen_kg']
        }

    def _prepare_physics(self, config):
        df_c = st.session_state['df_crops']
        crop_p = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
        cycle = int(crop_p['Cycle_Days'])

        weather = self.fetch_weather_climatology_ee(
            config['center_lat'], config['center_lon'], config['planting_date'], cycle
        )
        if weather is None or weather.empty:
            weather = self._generate_synthetic_weather(config['planting_date'], cycle, config['center_lat'])

        soil_state = {
            'water_mm': config['initial_soil_water'] * config['soil_water_holding_cap'],
            'nitrogen_kg': config['initial_nitrogen'],
            'field_capacity_mm': config['soil_water_holding_cap']
        }
        mgmt = {
            'fert': {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['fert_schedule']},
            'irr': {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        }

        bio_history = []
        biomass_cum = 0.0
        for t, row in weather.iterrows():
            bio = self._stics_lite_step(t, row, crop_p, soil_state, mgmt)
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
        x = np.linspace(min_x, max_x, N)
        y = np.linspace(min_y, max_y, N)
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
        """
        Modified to handle FUNGAL (Wind) vs VIRAL (Vector) spread logic.
        """
        df_d = st.session_state['df_diseases']
        dis_id = config['selected_disease_id']
        
        dis_p = None
        if dis_id:
            dis_rows = df_d[df_d['Disease_ID'] == dis_id]
            if not dis_rows.empty: dis_p = dis_rows.iloc[0]

        # Determine Logic Type
        is_fungal = False
        if dis_p is not None:
            if 'fungal' in str(dis_p['Type']).lower() or 'bacterial' in str(dis_p['Type']).lower():
                is_fungal = True

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
                # 1. Environmental Risk (Temp + Humidity)
                t_score = np.exp(-((weather_row['TMIN'] + weather_row['TMAX'])/2 - dis_p['Opt_Temp'])**2 / 50)
                h_score = 1.0 if weather_row['HUMIDITY'] > dis_p['Opt_Humidity'] else weather_row['HUMIDITY']/100
                env_risk = t_score * h_score
                
                # 2. Transmission Factor (Wind vs Vector)
                if is_fungal:
                    # Fungal: Driven by Wind Speed
                    # Normalize: Assume 5 m/s is "standard" breeze. Higher wind = further/faster spread.
                    wind_speed = weather_row.get('WIND_SPEED', 2.0)
                    spread_driver = (wind_speed / 5.0) 
                else:
                    # Viral: Driven by Vector Pressure (User Input)
                    spread_driver = config['insect_pressure']
                
                pressure = convolve2d(I_grid, kernel, mode='same')
                
                # Growth = Beta * Env * Driver * Neighbors * Susceptible
                growth = beta * spread_driver * env_risk * pressure * (1 - I_grid)
                
                # Jumps (Long distance dispersal)
                # Fungi jump more with high wind
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
                'Nmin': bio['nmin'],
                'ETa': bio['eta'],
                'Biomass': biomass_val,
                'Yield': np.mean(yield_grid),
                'Incidence': np.mean(inf_values) if dis_p is not None else 0,
                'Avg_Stress': 1 - bio['sw_fac'], 
                'Avg_N_Stress': 1 - bio['n_fac'],
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