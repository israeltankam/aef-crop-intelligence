# src/models/weather_service.py
import numpy as np
import pandas as pd
import streamlit as st
import ee
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

class WeatherService:
    """
    Advanced Weather Service providing Long-Term Climate Projections.
    Strategy:
    1. Earth Engine (NEX-GDDP-CMIP6 for Future / ERA5 for Past)
    2. Open-Meteo Climate API (Fallback)
    3. Stochastic ARIMA-Proxy Generator (Offline Fallback)
    """

    def __init__(self):
        self._ensure_ee_init()

    def _ensure_ee_init(self):
        """Attempts to initialize Earth Engine if not already done."""
        if not st.session_state.get('ee_initialized', False):
            try:
                if 'gcp_service_account' in st.secrets:
                    service_account_info = st.secrets["gcp_service_account"]
                    scopes = ['https://www.googleapis.com/auth/earthengine']
                    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                    ee.Initialize(credentials=creds)
                    st.session_state['ee_initialized'] = True
            except Exception:
                pass # Fail silently, methods will handle the fallback

    def get_weather_projections(self, lat, lon, start_date, duration_days):
        """
        Main entry point. Automatically routes to the best available source.
        Returns DataFrame with columns: [DATE, TMIN, TMAX, RAIN, RADIATION, WIND_SPEED, HUMIDITY]
        """
        end_date = start_date + timedelta(days=duration_days)
        
        # 1. Attempt Earth Engine (The Gold Standard)
        if st.session_state.get('ee_initialized', False):
            try:
                df = self._fetch_ee_cmip6(lat, lon, start_date, end_date)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                print(f"EE Climate Failed: {e}. Falling back...")

        # 2. Attempt Open-Meteo API (The Web Standard)
        try:
            df = self._fetch_open_meteo(lat, lon, start_date, end_date)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            print(f"Open-Meteo Failed: {e}. Falling back...")

        # 3. Fallback to Stochastic ARIMA (The Mathematical Standard)
        print("Using Stochastic Fallback.")
        return self._generate_stochastic_arima(lat, start_date, duration_days)

    # --- TIER 1: EARTH ENGINE (CMIP6 / ERA5) ---
    def _fetch_ee_cmip6(self, lat, lon, start_date, end_date):
        """
        Fetches NEX-GDDP-CMIP6 data (Daily).
        Scenario: SSP245 (Middle of the road).
        Model: ACCESS-CM2 (Robust performance).
        """
        point = ee.Geometry.Point([lon, lat])
        
        # Check if requested range is in the 'future' relative to the dataset's typical availability
        # NEX-GDDP-CMIP6 runs from 2015 to 2100.
        # If the user asks for 2023-2024, this is perfect.
        
        # Dataset: NASA/NEX-GDDP-CMIP6
        dataset = ee.ImageCollection("NASA/NEX-GDDP-CMIP6")\
            .filterBounds(point)\
            .filterDate(str(start_date), str(end_date))\
            .filter(ee.Filter.eq('scenario', 'ssp245'))\
            .filter(ee.Filter.eq('model', 'ACCESS-CM2'))\
            .select(['tasmin', 'tasmax', 'pr', 'rsds', 'sfcWind'])

        # Check if data exists
        if dataset.size().getInfo() == 0:
            return None

        def extract_daily(img):
            # Reducer to get value at point
            stats = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=25000)
            
            # Conversions:
            # tasmin/tasmax: Kelvin -> Celsius
            # pr: kg m-2 s-1 -> mm/day (multiply by 86400)
            # rsds: W m-2 -> MJ m-2 day-1 (multiply by 0.0864)
            # sfcWind: m s-1 (keep)
            
            return ee.Feature(None, {
                'date': img.date().format('YYYY-MM-dd'),
                'TMIN': ee.Number(stats.get('tasmin')).subtract(273.15),
                'TMAX': ee.Number(stats.get('tasmax')).subtract(273.15),
                'RAIN': ee.Number(stats.get('pr')).multiply(86400),
                'RADIATION': ee.Number(stats.get('rsds')).multiply(0.0864),
                'WIND_SPEED': stats.get('sfcWind')
            })

        data_list = dataset.map(extract_daily).reduceColumns(ee.Reducer.toList(6), ['date', 'TMIN', 'TMAX', 'RAIN', 'RADIATION', 'WIND_SPEED']).getInfo()['list']
        
        df = pd.DataFrame(data_list, columns=['DATE', 'TMIN', 'TMAX', 'RAIN', 'RADIATION', 'WIND_SPEED'])
        df['DATE'] = pd.to_datetime(df['DATE'])
        
        # Heuristic for Humidity (CMIP6 often lacks relative humidity directly in this collection)
        # Simple estimation based on Rain and T gap
        df['HUMIDITY'] = 60 + (df['RAIN'] > 1) * 20 + (30 - (df['TMAX'] - df['TMIN'])) 
        df['HUMIDITY'] = df['HUMIDITY'].clip(20, 100)
        
        return df.sort_values('DATE')

    # --- TIER 2: OPEN-METEO API ---
    def _fetch_open_meteo(self, lat, lon, start_date, end_date):
        """
        Uses Open-Meteo Climate API (EC_Earth3P_HR).
        """
        url = "https://climate-api.open-meteo.com/v1/climate"
        
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "models": "EC_Earth3P_HR", # High Res Model
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,shortwave_radiation_sum,windspeed_10m_max,relative_humidity_2m_mean",
            "timezone": "auto"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'daily' not in data:
            return None
            
        daily = data['daily']
        df = pd.DataFrame({
            'DATE': pd.to_datetime(daily['time']),
            'TMIN': daily['temperature_2m_min'],
            'TMAX': daily['temperature_2m_max'],
            'RAIN': daily['precipitation_sum'],
            'RADIATION': daily['shortwave_radiation_sum'], # MJ/m2 comes directly? Usually W/m2 or MJ check units
            'WIND_SPEED': daily['windspeed_10m_max'],
            'HUMIDITY': daily['relative_humidity_2m_mean']
        })
        
        # Open-Meteo Radiation is usually MJ/m2 in 'daily' aggregation, but check if W/m2
        # If values are huge (e.g. > 1000), it's Wh/m2 or similar. 
        # Standard daily sum is MJ/m2.
        
        return df

    # --- TIER 3: STOCHASTIC ARIMA-PROXY ---
    def _generate_stochastic_arima(self, lat, start_date, duration):
        """
        Generates data using a synthetic ARIMA process with widening uncertainty (Noise scaling).
        Used when API/EE fails.
        """
        dates = [start_date + timedelta(days=i) for i in range(duration)]
        doy = np.array([d.timetuple().tm_yday for d in dates])
        t_years = np.arange(duration) / 365.0 # Time in years
        
        # 1. Base Climatology (Sine Waves based on Latitude)
        # Northern Hemisphere logic; invert for Southern
        is_north = lat > 0
        phase = 0 if is_north else np.pi
        
        # Base Temperature
        avg_temp = 25 - (abs(lat) / 5) # Cooler at poles
        seasonal_amp = 5 + (abs(lat) / 10)
        t_mean = avg_temp + seasonal_amp * np.sin(2 * np.pi * (doy - 100) / 365 + phase)
        
        # 2. ARIMA Noise Process (Auto-Regressive)
        # X_t = phi * X_{t-1} + epsilon
        phi = 0.8 # Persistence
        noise_scale = 2.0 # Base noise
        
        # Growing uncertainty factor: Noise increases with sqrt(time)
        uncertainty_factor = 1.0 + 0.5 * np.sqrt(t_years)
        
        residuals = np.zeros(duration)
        rain_prob_base = np.zeros(duration)
        
        # Iterate to build AR(1) series
        rng = np.random.default_rng(seed=42)
        epsilons = rng.normal(0, noise_scale, duration)
        
        for t in range(1, duration):
            residuals[t] = phi * residuals[t-1] + (epsilons[t] * uncertainty_factor[t])
            
        # Apply to Temperature
        t_final_mean = t_mean + residuals
        t_min = t_final_mean - 6
        t_max = t_final_mean + 6
        
        # 3. Rainfall (Markov Chain + LogNormal Amount)
        # Prob of rain depends on season (simple ITCZ proxy)
        rain_season = np.sin(2 * np.pi * (doy - 150) / 365 + phase) # Peak in summer
        p_rain = 0.3 + 0.2 * rain_season
        p_rain = np.clip(p_rain, 0.05, 0.8)
        
        is_raining = (rng.random(duration) < p_rain)
        rain_amounts = rng.gamma(shape=2.0, scale=10.0, size=duration) * is_raining
        
        # 4. Derived Variables
        rad = 22 * (1 - 0.6 * is_raining) + rng.normal(0, 2, duration)
        rad = np.clip(rad, 5, 32)
        
        hum = 60 + (is_raining * 25) + rng.normal(0, 5, duration)
        hum = np.clip(hum, 20, 100)
        
        wind = rng.gamma(shape=2.5, scale=1.5, size=duration)
        
        return pd.DataFrame({
            'DATE': pd.to_datetime(dates),
            'TMIN': t_min,
            'TMAX': t_max,
            'RAIN': rain_amounts,
            'RADIATION': rad,
            'WIND_SPEED': wind,
            'HUMIDITY': hum
        })