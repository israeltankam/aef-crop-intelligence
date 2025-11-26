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
        # Ensure EE is initialized (re-use credentials if possible)
        self._ensure_ee_init()

    def _ensure_ee_init(self):
        """Auth check specific to the engine."""
        if not st.session_state.get('ee_initialized', False):
            try:
                if 'gcp_service_account' in st.secrets:
                    service_account_info = st.secrets["gcp_service_account"]
                    scopes = ['https://www.googleapis.com/auth/earthengine']
                    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                    ee.Initialize(credentials=creds)
                    st.session_state['ee_initialized'] = True
            except:
                pass # Fail silently, will fallback to synthetic

    def _generate_synthetic_weather(self, start_date, duration, lat):
        """Fallback: Generates synthetic weather (Original Sine Wave Logic)."""
        dates = [datetime.combine(start_date + timedelta(days=i), datetime.min.time()) for i in range(duration)]
        doy = np.array([d.timetuple().tm_yday for d in dates])
        
        t_avg = 25 + 5 * np.sin((doy - 60) * 2 * np.pi / 365)
        t_min = t_avg - 7 + np.random.normal(0, 1, duration)
        t_max = t_avg + 7 + np.random.normal(0, 2, duration)
        rain = (np.random.rand(duration) < 0.3) * np.random.gamma(10, 2, duration)
        rad = 20 - (rain > 0) * 8 + np.random.normal(0, 2, duration)
        rad = np.clip(rad, 5, 30)
        hum = 60 + (rain > 0) * 20 + np.random.normal(0, 5, duration)
        
        return pd.DataFrame({
            'DATE': pd.to_datetime(dates),
            'TMIN': t_min, 'TMAX': t_max,
            'RAIN': rain, 'RADIATION': rad,
            'HUMIDITY': np.clip(hum, 20, 100)
        })

    def fetch_weather_climatology_ee(self, lat, lon, start_date, duration):
        """
        AlphaEarth Power: Fetches 10-year average climatology for the requested date range.
        Sources: CHIRPS (Rain), ERA5-Land (Temp/Rad).
        """
        if not st.session_state.get('ee_initialized'):
            return None

        try:
            # 1. Define Location and Time Window
            point = ee.Geometry.Point([lon, lat])
            
            # We calculate "Typical Weather" by averaging the last 10 years
            # for these specific days of the year.
            # To do this efficiently in GEE, we'll just grab the last 365 days of "Typical Year" data 
            # pre-calculated or fetch raw and aggregate.
            
            # Simpler approach for robustness: Fetch last 5 years of raw daily data, 
            # aggregate locally in Pandas to get "Mean Day".
            
            # We fetch 3 years back to build a robust mean
            hist_start = start_date.replace(year=start_date.year - 4)
            hist_end = start_date.replace(year=start_date.year - 1)
            
            # 2. ERA5-Land (Temp & Rad)
            # Scaling: Temp (K->C), Rad (J/m2 -> MJ/m2)
            era5 = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")\
                .filterDate(str(hist_start), str(hist_end))\
                .filterBounds(point)\
                .select(['temperature_2m_min', 'temperature_2m_max', 'surface_solar_radiation_downwards_sum'])
            
            def get_era5_vals(img):
                d = img.date().format('MM-dd')
                vals = img.reduceRegion(reducer=ee.Reducer.first(), geometry=point, scale=11000).getInfo()
                return {
                    'doy': d,
                    'tmin': vals.get('temperature_2m_min'),
                    'tmax': vals.get('temperature_2m_max'),
                    'rad': vals.get('surface_solar_radiation_downwards_sum')
                }
            
            era5_data = era5.map(lambda img: ee.Feature(None, get_era5_vals(img))).reduceColumns(ee.Reducer.toList(2), ['doy', 'tmin']).getInfo() # Simplification for snippet
            # Note: Doing full mapped fetches can be slow. Let's use getRegion for speed.
            
            # FAST METHOD: getRegion
            # ERA5
            era5_raw = era5.getRegion(point, 11000).getInfo()
            # Header: [id, lon, lat, time, tmin, tmax, rad]
            header = era5_raw[0]
            data = era5_raw[1:]
            df_era = pd.DataFrame(data, columns=header)
            
            # Convert Types & Units
            df_era['date'] = pd.to_datetime(df_era['time'], unit='ms')
            df_era['TMIN'] = df_era['temperature_2m_min'] - 273.15
            df_era['TMAX'] = df_era['temperature_2m_max'] - 273.15
            df_era['RADIATION'] = df_era['surface_solar_radiation_downwards_sum'] / 1e6 # J to MJ
            df_era['MM-DD'] = df_era['date'].dt.strftime('%m-%d')
            
            # 3. CHIRPS (Rain)
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
            
            # 4. Aggregate to Climatology (Group by Day of Year)
            # We average 3 years of data to create a "Typical" profile
            clim_era = df_era.groupby('MM-DD')[['TMIN', 'TMAX', 'RADIATION']].mean()
            clim_rain = df_chirps.groupby('MM-DD')[['RAIN']].mean() # Mean rain is often too smooth (drizzle every day). 
            # Better to take 75th percentile or mean, but for STICS-lite mean is safer than zeros.
            
            climatology = clim_era.join(clim_rain).fillna(0)
            
            # 5. Project into requested simulation window
            sim_dates = [start_date + timedelta(days=i) for i in range(duration)]
            sim_df_list = []
            
            for d in sim_dates:
                key = d.strftime('%m-%d')
                if key in climatology.index:
                    row = climatology.loc[key]
                    sim_df_list.append({
                        'DATE': pd.Timestamp(d),
                        'TMIN': row['TMIN'],
                        'TMAX': row['TMAX'],
                        'RAIN': row['RAIN'],
                        'RADIATION': row['RADIATION'],
                        'HUMIDITY': 60 + (row['RAIN'] > 0)*20 # Crude approximation
                    })
                else:
                    # Leap year edge case or missing data
                    sim_df_list.append({
                        'DATE': pd.Timestamp(d),
                        'TMIN': 25, 'TMAX': 30, 'RAIN': 0, 'RADIATION': 20, 'HUMIDITY': 50
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
        
        # 1. Thermal Time
        dTT = max(0, t_avg - crop['T_Base'])
        if t_avg > crop['T_Max']: dTT = 0 
        
        # 2. Soil Water Balance (Bucket)
        # Penman-Monteith approx
        pet = 0.0023 * (t_avg + 17.8) * (tmax - tmin)**0.5 * rad
        
        curr_date = weather_row['DATE'].date()
        irr_amount = mgmt_events['irr'].get(curr_date, 0.0)
        fert_amount = mgmt_events['fert'].get(curr_date, 0.0)
        
        soil_state['water_mm'] += (rain + irr_amount)
        soil_state['nitrogen_kg'] += fert_amount
        
        field_cap = soil_state['field_capacity_mm']
        curr_water = soil_state['water_mm']
        
        # Water Stress Factor (0-1, where 1 is no stress)
        sw_fac = 1.0
        if curr_water < (field_cap * 0.5):
            sw_fac = max(0, curr_water / (field_cap * 0.5))
            
        eta = pet * sw_fac
        soil_state['water_mm'] = max(0, soil_state['water_mm'] - eta)
        if soil_state['water_mm'] > field_cap: soil_state['water_mm'] = field_cap
            
        # 3. Nitrogen Stress
        n_fac = 1.0
        if soil_state['nitrogen_kg'] < 20: 
            n_fac = max(0, soil_state['nitrogen_kg'] / 20.0)
            
        # 4. Biomass Calculation
        cycle = crop['Cycle_Days']
        progress = day_idx / cycle
        lai = 0
        if progress < 0.15: lai = 0.5
        elif progress < 0.5: lai = crop['Max_LAI'] * (progress/0.5)
        elif progress < 0.8: lai = crop['Max_LAI']
        else: lai = crop['Max_LAI'] * (1 - (progress-0.8)*5)
        
        # Light Interception
        ipar = rad * (1 - np.exp(-0.7 * lai))
        
        # Daily Biomass (g/m2)
        d_bio_g_m2 = crop['RUE_g_MJ'] * ipar * sw_fac * n_fac
        
        # N Uptake
        n_demand = (d_bio_g_m2) * 0.025 # 2.5% N
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

    def run_simulation(self, config):
        # --- SETUP ---
        df_c = st.session_state['df_crops']
        df_d = st.session_state['df_diseases']
        
        crop_id = config['selected_crop_id']
        dis_id = config['selected_disease_id']
        
        crop_p = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
        
        dis_p = None
        if dis_id:
            dis_rows = df_d[df_d['Disease_ID'] == dis_id]
            if not dis_rows.empty:
                dis_p = dis_rows.iloc[0]
        
        # Vector Logic
        insect_factor = 1.0
        if dis_p is not None:
            v_type = str(dis_p['Vector_Type']).lower()
            if not any(x in v_type for x in ['wind', 'rain', 'splash', 'soil']):
                insect_factor = config['insect_pressure']
        
        # --- SPATIAL MESH ---
        field_poly = np.array([list(p) for p in config['field_coords']])
        path = Path(field_poly)
        min_x, min_y = np.min(field_poly, axis=0)
        max_x, max_y = np.max(field_poly, axis=0)
        
        N = 40 # Resolution
        x = np.linspace(min_x, max_x, N)
        y = np.linspace(min_y, max_y, N)
        xv, yv = np.meshgrid(x, y)
        points = np.vstack((xv.flatten(), yv.flatten())).T
        
        mask = path.contains_points(points).reshape(N, N)
        valid_points = points[mask.flatten()]
        
        if len(valid_points) < 3: return None
        tri = Delaunay(valid_points)
        triang = Triangulation(valid_points[:,0], valid_points[:,1], tri.simplices)
        
        # --- INITIAL STATES ---
        n_valid = len(valid_points)
        biomass_grid = np.zeros(n_valid)
        I_grid = np.zeros((N, N))
        
        if config['disease_spots']:
            for spot in config['disease_spots']:
                dist = (xv - spot['lat'])**2 + (yv - spot['lon'])**2
                iy, ix = np.unravel_index(np.argmin(dist), (N, N))
                
                if mask[iy, ix]: 
                    count = spot.get('plants', 1)
                    # 1 plant = 5% severity. 20 plants = 100% saturation.
                    severity = min(1.0, 0.05 * count)
                    I_grid[iy, ix] = max(I_grid[iy, ix], severity)
        
        soil_state = {
            'water_mm': config['initial_soil_water'] * config['soil_water_holding_cap'],
            'nitrogen_kg': config['initial_nitrogen'],
            'field_capacity_mm': config['soil_water_holding_cap']
        }
        
        mgmt = {
            'fert': {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['fert_schedule']},
            'irr': {pd.to_datetime(r['date']).date(): float(r['amount']) for r in config['irr_schedule']}
        }
        
        cycle = int(crop_p['Cycle_Days'])
        
        # --- WEATHER: ALPHAEARTH INTEGRATION ---
        # Try fetching satellite data first
        weather = self.fetch_weather_climatology_ee(
            config['center_lat'], 
            config['center_lon'], 
            config['planting_date'], 
            cycle
        )
        
        if weather is None or weather.empty:
            # Fallback to synthetic if EE fails or is offline
            # st.toast("Using synthetic weather (Offline Mode)", icon="⚠️") # Optional warning
            weather = self._generate_synthetic_weather(config['planting_date'], cycle, config['center_lat'])
        
        history = []
        kernel = np.array([[0.05, 0.2, 0.05], [0.2, 0.5, 0.2], [0.05, 0.2, 0.05]])
        beta = dis_p['Beta_Infection'] if dis_p is not None else 0
        if dis_p is not None: beta *= crop_p['Resistance_Score']
            
        # --- TIME LOOP ---
        for t, row in weather.iterrows():
            # 1. Bio Step
            bio = self._stics_lite_step(t, row, crop_p, soil_state, mgmt)
            biomass_grid += bio['d_biomass_t_ha']
            
            # 2. Spatial Step
            env_risk = 0
            if dis_p is not None:
                t_score = np.exp(-((row['TMIN'] + row['TMAX'])/2 - dis_p['Opt_Temp'])**2 / 50)
                h_score = 1.0 if row['HUMIDITY'] > dis_p['Opt_Humidity'] else row['HUMIDITY']/100
                env_risk = t_score * h_score
                
                pressure = convolve2d(I_grid, kernel, mode='same')
                growth = beta * insect_factor * env_risk * pressure * (1 - I_grid)
                jumps = (np.random.rand(N, N) < 0.0005) * (I_grid.sum() > 0) * 0.1
                
                I_grid = np.clip(I_grid + growth + jumps, 0, 1)
                I_grid = I_grid * mask
            
            # 3. Yield Calc
            inf_values = I_grid[mask]
            damage_factor = np.ones(n_valid)
            
            if dis_p is not None:
                retained = dis_p.get('Yield_Retained_Infected', 0.5)
                damage_factor = (1 - inf_values) + (inf_values * retained)
            
            yield_grid = crop_p['Harvest_Index'] * biomass_grid * damage_factor
            
            # 4. Record
            history.append({
                'Date': row['DATE'],
                'LAI': bio['lai'],
                'SWC': bio['swc'],
                'Nmin': bio['nmin'],
                'ETa': bio['eta'],
                'Biomass': np.mean(biomass_grid),
                'Yield': np.mean(yield_grid),
                'Incidence': np.mean(inf_values) if dis_p is not None else 0,
                'Avg_Stress': 1 - bio['sw_fac'], 
                'Avg_N_Stress': 1 - bio['n_fac'],
                'Grid_Incidence': inf_values.copy(), 
                'Grid_Yield': yield_grid.copy(),
                'Env_Favorability': env_risk if dis_p is not None else 0
            })
            
        return {
            'history': history,
            'triangulation': triang,
            'grid_points': valid_points,
            'crop_params': crop_p,
            'field_poly': field_poly 
        }