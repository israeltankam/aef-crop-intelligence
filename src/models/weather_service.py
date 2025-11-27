# src/models/weather_service.py
import numpy as np
import pandas as pd
import streamlit as st
import ee
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

class WeatherService:
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

    def generate_synthetic_weather(self, start_date, duration):
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
        wind = np.random.gamma(3, 1.5, duration) 
        
        return pd.DataFrame({
            'DATE': pd.to_datetime(dates),
            'TMIN': t_min, 'TMAX': t_max,
            'RAIN': rain, 'RADIATION': rad,
            'HUMIDITY': np.clip(hum, 20, 100),
            'WIND_SPEED': wind
        })

    def fetch_weather_climatology_ee(self, lat, lon, start_date, duration):
        """Fetches 10-year average climatology including WIND SPEED (ERA5)."""
        if not st.session_state.get('ee_initialized'):
            return None

        try:
            point = ee.Geometry.Point([lon, lat])
            
            # Fetch 3 years back
            hist_start = start_date.replace(year=start_date.year - 4)
            hist_end = start_date.replace(year=start_date.year - 1)
            
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
            df_era['WIND_SPEED'] = np.sqrt(
                df_era['u_component_of_wind_10m']**2 + 
                df_era['v_component_of_wind_10m']**2
            )
            df_era['MM-DD'] = df_era['date'].dt.strftime('%m-%d')
            
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