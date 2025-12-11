# src/models/disease_service.py
import ee
import pandas as pd
import numpy as np
from datetime import date, timedelta
import streamlit as st
from google.oauth2.service_account import Credentials
from scipy.optimize import curve_fit

class DiseaseService:
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
            except Exception as e:
                print(f"EE Init Failed: {e}")

    def analyze_field_health(self, coords, planting_date, planting_density):
        """
        Main pipeline:
        1. Fetch Sentinel-2 Time Series (Planting -> Now).
        2. Calculate LAI & NDMI.
        3. Identify Disease Pixels (Low LAI + High NDMI).
        4. Calculate realistic infected plant count based on Density.
        5. Return exact date of detection and precise centroid.
        """
        if not st.session_state.get('ee_initialized'):
            return False, "Earth Engine not initialized.", None, None, None

        try:
            # 1. Geometry & Time
            ee_coords = [[p[1], p[0]] for p in coords]
            geom = ee.Geometry.Polygon([ee_coords])
            start_date = str(planting_date)
            end_date = str(date.today())

            # 2. Sentinel-2 Collection
            def mask_clouds_and_calc_indices(img):
                orig = img
                qa = img.select('QA60')
                cloud_mask = 1 << 10
                cirrus_mask = 1 << 11
                mask = qa.bitwiseAnd(cloud_mask).eq(0).And(qa.bitwiseAnd(cirrus_mask).eq(0))
                
                processed = img.updateMask(mask).divide(10000)
                
                ndvi = processed.normalizedDifference(['B8', 'B4']).rename('NDVI')
                lai_raw = ndvi.subtract(0.57).divide(ee.Image(1).subtract(ndvi))
                lai = lai_raw.max(0).rename('LAI')
                ndmi = processed.normalizedDifference(['B8', 'B11']).rename('NDMI')

                return processed.addBands([lai, ndmi]).copyProperties(orig, ["system:time_start"])

            collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
                .filterBounds(geom)\
                .filterDate(start_date, end_date)\
                .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))\
                .map(mask_clouds_and_calc_indices)\
                .select(['LAI', 'NDMI'])

            count = collection.size().getInfo()
            if count == 0:
                return False, "No cloud-free satellite imagery found since planting.", None, None, None

            # 3. Classification Logic
            # Disease = Low LAI (<1.5) + High NDMI (>0.05) (Wet but thin)
            
            def extract_stats(img):
                date_str = img.date().format('YYYY-MM-dd')
                
                lai = img.select('LAI')
                ndmi = img.select('NDMI')
                
                # Disease Mask (1 where disease, 0 elsewhere)
                disease_mask = lai.lt(1.5).And(ndmi.gt(0.05)).selfMask()
                
                # A. Count Disease Pixels
                stats = disease_mask.reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=geom,
                    scale=10, # Sentinel-2 pixels are 10m
                    maxPixels=1e9
                )
                
                # B. Find Centroid of Disease (Weighted by location)
                # We add lat/lon bands, mask them by disease, and reduce to mean
                pixel_coords = ee.Image.pixelLonLat().updateMask(disease_mask)
                coords_stats = pixel_coords.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=geom,
                    scale=10,
                    maxPixels=1e9
                )
                
                # Total valid pixels in field (for incidence calc)
                total_stats = lai.reduceRegion(
                    reducer=ee.Reducer.count(),
                    geometry=geom,
                    scale=10,
                    maxPixels=1e9
                )

                return ee.Feature(None, {
                    'date': date_str,
                    'disease_pixel_count': stats.get('LAI'), 
                    'total_pixels': total_stats.get('LAI'),
                    'avg_lon': coords_stats.get('longitude'),
                    'avg_lat': coords_stats.get('latitude')
                })

            time_series = collection.map(extract_stats).getInfo()
            
            # 4. Process Time Series locally
            data = []
            features = time_series['features']
            
            for f in features:
                props = f['properties']
                d_pixels = props.get('disease_pixel_count') or 0
                t_pixels = props.get('total_pixels') or 1
                
                if t_pixels > 0:
                    pct = d_pixels / t_pixels
                    
                    # Ensure coordinates are valid
                    c_lon = props.get('avg_lon')
                    c_lat = props.get('avg_lat')
                    
                    centroid = [c_lon, c_lat] if (c_lon and c_lat) else None

                    data.append({
                        'date': pd.to_datetime(props['date']).date(),
                        'incidence': pct,
                        'pixel_count': d_pixels,
                        'centroid': centroid 
                    })
            
            if not data:
                return False, "Data extraction failed.", None, None, None

            df = pd.DataFrame(data).sort_values('date')

            # 5. Logic: Find the *peak* or *latest* significant detection
            # We look for the latest date with significant incidence (>5%)
            significant_days = df[df['incidence'] > 0.05]
            
            if significant_days.empty:
                return True, "Crop appears healthy (Disease likelihood < 5%).", None, [], None

            # Use the latest significant day for the "Detection"
            detection_event = significant_days.iloc[-1]
            detection_date = detection_event['date']
            
            # Parameter Estimation using the whole history up to that point
            est_beta, est_sigma = self._estimate_gibson_parameters(df, coords)
            
            generic_disease = {
                'Disease_ID': 'D_GEN_01',
                'Target_Crop_Name': 'Unknown',
                'Disease_Name': 'Unidentified Satellite Anomaly',
                'Type': 'Unknown (Modeled)',
                'Vector_Type': 'Unknown',
                'Opt_Temp': 25.0,
                'Opt_Humidity': 80.0,
                'Beta_Infection': round(est_beta, 3),
                'Dispersal_Sigma_m': round(est_sigma, 1),
                'Yield_Retained_Infected': 0.5,
                'Control_Methods': "**Surveillance:** Ground-truth required.\n**Sanitation:** Remove symptomatic plants.\n**Nutrition:** Boost Potassium and Silicon.",
                'Pruning_Hygiene_Factor': 0.5,
                'Daily_Recovery_Rate': 0.01
            }

            # 6. Realistic Spot Generation
            spots = []
            if detection_event['centroid']:
                c_lon, c_lat = detection_event['centroid']
                
                # Math:
                # 1 Sentinel Pixel = 10m x 10m = 100 m2
                # Infected Area (ha) = Pixels * 100 / 10,000
                # Plants = Infected Area (ha) * Density (plants/ha)
                
                infected_area_ha = detection_event['pixel_count'] * (100.0 / 10000.0)
                estimated_plants = int(infected_area_ha * planting_density)
                estimated_plants = max(1, estimated_plants) # At least 1

                spots.append({
                    'lat': c_lat,
                    'lon': c_lon,
                    'plants': estimated_plants,
                    'date': str(detection_date)
                })

            return True, "Disease Signature Detected", generic_disease, spots, detection_date

        except Exception as e:
            return False, f"Analysis Error: {str(e)}", None, None, None

    def _estimate_gibson_parameters(self, df, field_coords):
        # ... (Same as before, simplified for brevity) ...
        df = df[df['incidence'] > 0].copy()
        if len(df) < 3: return 0.1, 20.0

        df['days'] = (pd.to_datetime(df['date']) - pd.to_datetime(df['date'].iloc[0])).dt.days
        x_data = df['days'].values
        y_data = df['incidence'].values

        def logistic(t, beta, K):
            return K / (1 + np.exp(-beta * t))

        try:
            popt, _ = curve_fit(logistic, x_data, y_data, p0=[0.1, 1.0], bounds=(0, [1.0, 1.0]), maxfev=1000)
            beta_est = popt[0]
        except:
            beta_est = 0.1 

        centroids = [c for c in df['centroid'].tolist() if c] 
        if len(centroids) > 1:
            centroids = np.array(centroids)
            diffs = np.diff(centroids, axis=0) * 111000.0
            dists = np.sqrt(np.sum(diffs**2, axis=1))
            avg_jump = np.mean(dists)
            sigma_est = max(5.0, avg_jump)
        else:
            sigma_est = 20.0

        return beta_est, sigma_est