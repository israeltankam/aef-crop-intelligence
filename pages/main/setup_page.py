# pages/main/setup_page.py
import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from geopy.geocoders import Nominatim
from geopy.point import Point
import math
from src.models.state_manager import StateManager
from src.models.fertilizer_service import FertilizerService
from src.models.disease_service import DiseaseService # NEW IMPORT
from datetime import date, timedelta
import json
import ee
from google.oauth2.service_account import Credentials
import geocoder

# --- CONSTANTS ---
_SOIL_TABLE = {
    'sand':            {'field_capacity': 0.10, 'wilting_point': 0.03},
    'loamy sand':      {'field_capacity': 0.13, 'wilting_point': 0.05},
    'sandy loam':      {'field_capacity': 0.18, 'wilting_point': 0.07},
    'loam':            {'field_capacity': 0.27, 'wilting_point': 0.11},
    'silt loam':       {'field_capacity': 0.36, 'wilting_point': 0.20},
    'silt':            {'field_capacity': 0.45, 'wilting_point': 0.30},
    'sandy clay loam': {'field_capacity': 0.20, 'wilting_point': 0.10},
    'clay loam':       {'field_capacity': 0.35, 'wilting_point': 0.18},
    'silty clay loam': {'field_capacity': 0.38, 'wilting_point': 0.23},
    'sandy clay':      {'field_capacity': 0.23, 'wilting_point': 0.13},
    'silty clay':      {'field_capacity': 0.41, 'wilting_point': 0.26},
    'clay':            {'field_capacity': 0.47, 'wilting_point': 0.27}
}

def initialize_ee():
    if st.session_state.get('ee_initialized', False): return True
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/earthengine']
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        ee.Initialize(credentials=creds)
        st.session_state['ee_initialized'] = True
        return True
    except Exception as e:
        st.error("🛑 Earth Engine Authentication Failed")
        return False

def is_point_in_polygon(point, polygon_coords):
    x, y = point[0], point[1] 
    n = len(polygon_coords)
    inside = False
    p1x, p1y = polygon_coords[0]
    for i in range(n + 1):
        p2x, p2y = polygon_coords[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def get_bounds(coords):
    lats = [p[0] for p in coords]
    lons = [p[1] for p in coords]
    return [[min(lats), min(lons)], [max(lats), max(lons)]]

def calculate_area_ha(coords):
    if not coords or len(coords) < 3: return 0.0
    pts = np.array(coords)
    lats, lons = pts[:, 0], pts[:, 1]
    mean_lat = np.mean(lats)
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111132.0 * np.cos(np.radians(mean_lat))
    y = (lats - lats[0]) * m_per_deg_lat
    x = (lons - lons[0]) * m_per_deg_lon
    area_m2 = 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))
    return round(area_m2 / 10000.0, 2)

# --- GEOMETRY HELPERS ---
def generate_square_polygon(lat, lon, area_ha):
    area_m2 = area_ha * 10000.0
    side_length_m = math.sqrt(area_m2)
    half_side = side_length_m / 2.0
    m_per_deg_lat = 111132.0
    m_per_deg_lon = 111132.0 * math.cos(math.radians(lat))
    delta_lat = half_side / m_per_deg_lat
    delta_lon = half_side / m_per_deg_lon
    p1 = [lat - delta_lat, lon - delta_lon] 
    p2 = [lat - delta_lat, lon + delta_lon] 
    p3 = [lat + delta_lat, lon + delta_lon] 
    p4 = [lat + delta_lat, lon - delta_lon] 
    p5 = [lat - delta_lat, lon - delta_lon] 
    return [p1, p2, p3, p4, p5]

def get_land_cover_stats(polygon_coords_latlon):
    if not initialize_ee(): return None
    ee_coords = [[p[1], p[0]] for p in polygon_coords_latlon]
    if ee_coords[0] != ee_coords[-1]: ee_coords.append(ee_coords[0])
    geom = ee.Geometry.Polygon([ee_coords])
    try:
        img = ee.ImageCollection("ESA/WorldCover/v100").filterBounds(geom).mosaic().select("Map").clip(geom)
        stats = img.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=geom, scale=10, maxPixels=1e9)
        hist = stats.get('Map').getInfo()
        return hist
    except:
        return None

def analyze_risk_level(hist):
    if not hist: return "UNKNOWN", "gray", "No satellite data available."
    total_pixels = sum(hist.values())
    if total_pixels == 0: return "UNKNOWN", "gray", "Empty region."
    urban_pixels = hist.get('50', 0)
    water_pixels = hist.get('80', 0) + hist.get('90', 0) + hist.get('95', 0)
    urban_pct = (urban_pixels / total_pixels) * 100
    water_pct = (water_pixels / total_pixels) * 100
    if urban_pct > 5.0:
        return "CRITICAL", "red", f"High urban density detected ({urban_pct:.1f}%). Likely a building."
    if water_pct > 10.0:
        return "CRITICAL", "red", f"Deep water detected ({water_pct:.1f}%)."
    if urban_pixels > 0:
        return "WARNING", "orange", f"Potential structure or road detected ({urban_pixels} pixels)."
    if water_pct > 0:
        return "WARNING", "orange", f"Minor water/wetland features detected ({water_pct:.1f}%)."
    return "SAFE", "green", "Area is composed of vegetation/soil."

def optimize_field_location(center_lat, center_lon, area_ha):
    area_m2 = area_ha * 10000.0
    side_len_deg = math.sqrt(area_m2) / 111132.0 
    shift = side_len_deg * 0.5 
    offsets = [(0,0), (shift, 0), (-shift, 0), (0, shift), (0, -shift), (shift, shift), (shift, -shift), (-shift, shift), (-shift, -shift)]
    candidates = []
    for d_lat, d_lon in offsets:
        test_lat = center_lat + d_lat
        test_lon = center_lon + d_lon
        poly = generate_square_polygon(test_lat, test_lon, area_ha)
        hist = get_land_cover_stats(poly)
        level, color, msg = analyze_risk_level(hist)
        score = 0 if level == "SAFE" else (1 if level == "WARNING" else (2 if level == "CRITICAL" else 3))
        urban_count = hist.get('50', 0) if hist else 9999
        candidates.append({'poly': poly, 'level': level, 'color': color, 'msg': msg, 'score': score, 'urban': urban_count})
    candidates.sort(key=lambda x: (x['score'], x['urban']))
    best = candidates[0]
    return best['poly'], best['level'], best['color'], best['msg']

def get_auto_soil_profile(coords):
    if not initialize_ee(): 
        return False, {}, "Earth Engine API is offline or not authenticated."
    try:
        ee_coords = [[p[1], p[0]] for p in coords]
        geom = ee.Geometry.Polygon([ee_coords])
        tex_img = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").select('b0').clip(geom)
        tex_stats = tex_img.reduceRegion(reducer=ee.Reducer.mode(), geometry=geom, scale=250, maxPixels=1e9)
        tex_class_id = tex_stats.get('b0').getInfo()
        if tex_class_id is None:
            return False, {}, "Region outside of Soil Dataset coverage (No Texture Data)."
        usda_map = {1:'clay',2:'silty clay',3:'sandy clay',4:'clay loam',5:'silty clay loam',6:'sandy clay loam',7:'loam',8:'silt loam',9:'sandy loam',10:'silt',11:'loamy sand',12:'sand'}
        detected_texture = usda_map.get(tex_class_id, 'loam') 
        oc_img = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select('b0').clip(geom)
        oc_raw = oc_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=250).get('b0').getInfo()
        organic_carbon_g_kg = (oc_raw * 5.0) if oc_raw is not None else 5.0
        clay_img = ee.Image("OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02").select('b0').clip(geom)
        clay_content = clay_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=250).get('b0').getInfo() or 20.0
        total_n_mg_kg = (organic_carbon_g_kg * 1000.0) / 10.0
        if 'sand' in detected_texture: availability_factor = 0.015
        elif 'clay' in detected_texture: availability_factor = 0.025
        else: availability_factor = 0.02 
        available_n = total_n_mg_kg * availability_factor
        available_n = max(15.0, available_n)
        return True, {'texture': detected_texture, 'carbon': organic_carbon_g_kg, 'clay': clay_content, 'n_total': total_n_mg_kg, 'n_available': available_n}, "Success"
    except Exception as e:
        return False, {}, f"Earth Engine Error: {str(e)}"

def get_default_location():
    try:
        g = geocoder.ip('me')
        if g.latlng: return g.latlng[0], g.latlng[1]
    except: pass
    return 4.0, 11.5

def app():
    if 'step' not in st.session_state: StateManager.initialize()
    st.title("🛠️ Digital Twin Configuration")

    steps = {1: "1. Geography", 2: "2. Crop", 3: "3. Disease", 4: "4. Management", 5: "5. Launch"}
    can_navigate = st.session_state.get('field_coords') is not None and len(st.session_state['field_coords']) > 0
    cols = st.columns(5)
    for i, (step_num, step_label) in enumerate(steps.items()):
        with cols[i]:
            if step_num == st.session_state['step']:
                st.button(f"🟦 {step_label}", key=f"nav_{step_num}")
            else:
                if st.button(f"{step_label}", key=f"nav_{step_num}", disabled=not can_navigate):
                    st.session_state['step'] = step_num
                    st.rerun()
    st.progress(st.session_state['step'] / 5)
    st.divider()

    # ==========================================================================
    # STEP 1: GEOGRAPHY
    # ==========================================================================
    if st.session_state['step'] == 1:
        st.subheader("🌍 Step 1: Define Field Geography")
        if 'center_lat' not in st.session_state or st.session_state['center_lat'] == 9.30: 
             lat, lon = get_default_location()
             if lat != 4.0 and lon != 11.5: 
                 st.session_state['center_lat'] = lat
                 st.session_state['center_lon'] = lon
        tab_auto, tab_manual, tab_upload = st.tabs(["✨ Assisted Setup", "✍️ Manual Draw", "📂 Load Config"])
        with tab_auto:
            st.info("💡 **Pro Tip:** Use this **Assisted Setup** to find your location and generate a safe baseline shape.")
            c_input, c_area = st.columns([2, 1])
            with c_input:
                coord_str = st.text_input("Center Coordinate", value="", placeholder="e.g., 4°34′ N 11°07′ E  OR  4.56, 11.12")
            with c_area:
                area_input = st.number_input("Field Area (hectares)", min_value=0.1, max_value=1000.0, value=1.0, step=0.1)
            if st.button("Generate Smart Field", type="primary"):
                if coord_str:
                    try:
                        p = Point(coord_str)
                        lat, lon = p.latitude, p.longitude
                        st.session_state['center_lat'] = lat
                        st.session_state['center_lon'] = lon
                        with st.spinner("🛰️ Scanning surrounding area for optimal placement..."):
                            poly, level, color, msg = optimize_field_location(lat, lon, area_input)
                        if level == "CRITICAL": st.error(f"🛑 **Blocking Issue:** {msg}")
                        elif level == "WARNING":
                             st.warning(f"⚠️ **Note:** {msg}")
                             st.success("We found the best possible spot nearby. You can adjust it below.")
                        else: st.success(f"✅ **Perfect Match:** {msg}")
                        st.session_state['field_coords'] = poly
                        st.session_state['area_ha'] = area_input
                        st.session_state['last_validation'] = msg
                        st.rerun()
                    except Exception as e: st.error(f"Could not parse coordinates: {e}")
                else: st.warning("Please enter coordinates.")
        with tab_manual:
            st.info("Use the Polygon tool (pentagon icon) to draw your field.")
            c1, c2 = st.columns([3, 1])
            with c1: search = st.text_input("Search Location", key="search_manual")
            with c2:
                st.write("")
                if st.button("🔍 Locate", key="btn_locate"):
                     try:
                        geolocator = Nominatim(user_agent="aef_app_v2")
                        if not search: lat, lon = st.session_state['center_lat'], st.session_state['center_lon']
                        else:
                            loc = geolocator.geocode(search)
                            if loc:
                                 st.session_state['center_lat'] = loc.latitude
                                 st.session_state['center_lon'] = loc.longitude
                                 st.rerun()
                     except: st.error("Location not found.")
        with tab_upload:
            uploaded_file = st.file_uploader("Drop your field_config.json here", type="json")
            if uploaded_file is not None:
                if StateManager.load_config_from_json(uploaded_file):
                    st.success("Configuration loaded!")
                    if st.button("🚀 Jump to Review"): st.session_state['step'] = 5; st.rerun()
        st.divider()
        if st.session_state['field_coords']:
            st.markdown("##### 📐 Fine-Tune Position")
            if 'last_validation' in st.session_state: st.caption(f"Current Status: {st.session_state['last_validation']}")
            c_nudge, c_info = st.columns([2, 2])
            with c_nudge:
                col_l, col_u, col_d, col_r = st.columns(4)
                shift_amt = 0.00005 
                if col_l.button("⬅️"): 
                    st.session_state['field_coords'] = [[p[0], p[1] - shift_amt] for p in st.session_state['field_coords']]; st.rerun()
                if col_u.button("⬆️"):
                    st.session_state['field_coords'] = [[p[0] + shift_amt, p[1]] for p in st.session_state['field_coords']]; st.rerun()
                if col_d.button("⬇️"):
                    st.session_state['field_coords'] = [[p[0] - shift_amt, p[1]] for p in st.session_state['field_coords']]; st.rerun()
                if col_r.button("➡️"):
                    st.session_state['field_coords'] = [[p[0], p[1] + shift_amt] for p in st.session_state['field_coords']]; st.rerun()
            with c_info:
                 area = st.session_state.get('area_ha', 0.0)
                 st.metric("Area", f"{area} ha")
        m = folium.Map(location=[st.session_state['center_lat'], st.session_state['center_lon']], zoom_start=17, max_zoom=20)
        folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Esri Satellite', overlay=False, control=True).add_to(m)
        if st.session_state['field_coords']:
            folium.Polygon(locations=st.session_state['field_coords'], color="#00FF00", weight=3, fill=True, fill_opacity=0.2, popup="Field Boundary").add_to(m)
        Draw(export=False, position='topleft', draw_options={'polyline':False,'rectangle':False,'circle':False,'marker':False,'circlemarker':False,'polygon':True}, edit_options={'edit': True}).add_to(m)
        folium.LayerControl().add_to(m)
        output = st_folium(m, height=500, width=800, key="map_step_1")
        if output['all_drawings']:
            last_draw = output['all_drawings'][-1]
            if last_draw['geometry']['type'] == 'Polygon':
                raw = last_draw['geometry']['coordinates'][0]
                coords = [[p[1], p[0]] for p in raw] 
                current = st.session_state.get('field_coords', [])
                if not current or (coords != current):
                    hist = get_land_cover_stats(coords)
                    level, color, msg = analyze_risk_level(hist)
                    if level == "CRITICAL": st.error(f"🛑 {msg}")
                    elif level == "WARNING": st.warning(f"⚠️ {msg}")
                    else: st.success(f"✅ {msg}")
                    st.session_state['field_coords'] = coords
                    st.session_state['area_ha'] = calculate_area_ha(coords)
                    st.session_state['last_validation'] = msg
                    st.rerun()
        if st.session_state['field_coords']:
            st.divider()
            c_back, c_next = st.columns([1, 6])
            with c_next:
                if st.button("Next Step ➡️"): st.session_state['step'] = 2; st.rerun()
            with c_back:
                 if st.button("🗑️ Clear"): st.session_state['field_coords'] = []; st.session_state['area_ha'] = 0.0; st.rerun()

    # ==========================================================================
    # STEP 2: CROP SELECTION
    # ==========================================================================
    elif st.session_state['step'] == 2:
        st.subheader("🌱 Step 2: Crop System")
        df_crops = st.session_state['df_crops']
        crops = df_crops['Crop_Name'].unique()
        c_sel, c_date = st.columns(2)
        with c_sel:
            curr_id = st.session_state.get('selected_crop_id')
            default_idx = 0
            if curr_id:
                curr_name = df_crops[df_crops['Crop_ID'] == curr_id].iloc[0]['Crop_Name']
                if curr_name in crops: default_idx = list(crops).index(curr_name)
            selected_crop_name = st.selectbox("Select Crop Species", crops, index=default_idx)
            varieties = df_crops[df_crops['Crop_Name'] == selected_crop_name]
            selected_var = st.selectbox("Select Variety", varieties['Variety'].unique())
            row = varieties[varieties['Variety'] == selected_var].iloc[0]
            new_crop_id = row['Crop_ID']
            if st.session_state.get('selected_crop_id') != new_crop_id:
                st.session_state['selected_crop_id'] = new_crop_id
                if 'Default_Density' in row: st.session_state['planting_density'] = int(row['Default_Density'])
                st.rerun()
        with c_date:
            st.session_state['planting_date'] = st.date_input("Planting Date", value=st.session_state['planting_date'])
            st.session_state['planting_density'] = st.number_input("Planting Density (plants/ha)", value=int(st.session_state.get('planting_density', 10000)), step=100)
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ Back"): st.session_state['step'] = 1; st.rerun()
        if c_next.button("Next ➡️"): st.session_state['step'] = 3; st.rerun()

    # ==========================================================================
    # STEP 3: DISEASE
    # ==========================================================================
    elif st.session_state['step'] == 3:
        st.subheader("🦠 Step 3: Disease Surveillance")
        c_id = st.session_state['selected_crop_id']
        c_row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
        df_d = st.session_state['df_diseases']
        
        # --- SATELLITE AUTO-DETECT SECTION ---
        st.markdown("##### 🛰️ Automated Surveillance")
        if st.button("📡 Auto-Detect via Satellite (LAI/NDMI Analysis)", type="primary", use_container_width=True):
            with st.spinner("Analyzing spectral signatures (Sentinel-2) for canopy stress patterns..."):
                ds = DiseaseService()
                planting = st.session_state['planting_date']
                density = st.session_state.get('planting_density', 1000)
                
                # Updated call signature to accept density and return date
                success, msg, disease_profile, spots, detected_date = ds.analyze_field_health(
                    st.session_state['field_coords'], 
                    planting,
                    density
                )
                
                if success:
                    if disease_profile:
                        # Case 1: Disease Found
                        st.session_state['disease_spots'] = spots
                        
                        if disease_profile['Disease_ID'] not in df_d['Disease_ID'].values:
                            new_row = pd.DataFrame([disease_profile])
                            st.session_state['df_diseases'] = pd.concat([df_d, new_row], ignore_index=True)
                        
                        st.session_state['selected_disease_id'] = disease_profile['Disease_ID']
                        
                        # CRITICAL FIX: Use the historical date returned by satellite analysis
                        st.session_state['detection_date'] = detected_date 
                        
                        st.success(f"⚠️ **{msg}**: {disease_profile['Disease_Name']}")
                        st.info(f"**Historical Detection:** Anomaly identified on {detected_date}")
                        st.caption(f"**Inferred Parameters:** Beta={disease_profile['Beta_Infection']}, Dispersal={disease_profile['Dispersal_Sigma_m']}m")
                        st.rerun() # Rerun to refresh the map and date input below
                    else:
                        st.session_state['selected_disease_id'] = None
                        st.session_state['disease_spots'] = []
                        st.success(f"✅ {msg}")
                else:
                    st.error(f"Detection Failed: {msg}")
                
        st.caption("Algorithm uses LAI vs NDMI correlation to distinguish disease from water stress.")
        st.divider()

        # --- MANUAL OVERRIDE SECTION ---
        st.markdown("##### ✍️ Manual Configuration / Verification")
        
        # Refresh df_d in case auto-detect added something
        df_d = st.session_state['df_diseases']
        rel_d = df_d[df_d['Target_Crop_Name'] == c_row['Crop_Name']]
        # Include Generic if present
        if not df_d[df_d['Disease_ID'] == 'D_GEN_01'].empty:
             rel_d = pd.concat([rel_d, df_d[df_d['Disease_ID'] == 'D_GEN_01']])

        c_dis, c_date = st.columns([2, 1])
        selected_d_type = ""

        with c_dis:
            if rel_d.empty: 
                st.warning("No specific diseases found for this crop.")
                st.session_state['selected_disease_id'] = None
            else:
                curr_dis_id = st.session_state.get('selected_disease_id')
                # Find index
                dis_names = rel_d['Disease_Name'].unique()
                idx = 0
                if curr_dis_id:
                    row = rel_d[rel_d['Disease_ID'] == curr_dis_id]
                    if not row.empty:
                        nm = row.iloc[0]['Disease_Name']
                        if nm in dis_names:
                             idx = list(dis_names).index(nm)

                d_name = st.selectbox("Identified Threat", dis_names, index=idx)
                dis_row = rel_d[rel_d['Disease_Name'] == d_name].iloc[0]
                st.session_state['selected_disease_id'] = dis_row['Disease_ID']
                selected_d_type = dis_row['Type']

        with c_date:
            st.session_state['detection_date'] = st.date_input("Detection Date", value=st.session_state['detection_date'])
            if 'fungal' in str(selected_d_type).lower() or 'bacterial' in str(selected_d_type).lower():
                st.info(f"💨 **Wind/Rain:** {selected_d_type}")
                st.session_state['insect_pressure'] = 1.0 
            elif 'unknown' in str(selected_d_type).lower():
                st.warning(f"❓ **Modeled:** {selected_d_type}")
                st.session_state['insect_pressure'] = 1.0
            else:
                st.info(f"🦟 **Vector:** {selected_d_type}")
                st.session_state['insect_pressure'] = st.slider("Vector Pressure", 0.0, 5.0, st.session_state.get('insect_pressure', 1.0))
        
        st.divider()
        col_map, col_list = st.columns([2, 1])
        with col_map:
            st.markdown("#### 📍 Field Map")
            coords = st.session_state['field_coords']
            bounds = get_bounds(coords)
            center = [(bounds[0][0]+bounds[1][0])/2, (bounds[0][1]+bounds[1][1])/2]
            m = folium.Map(location=center, zoom_start=18)
            m.fit_bounds(bounds)
            folium.Polygon(locations=coords, color="blue", weight=3, fill=False).add_to(m)
            for spot in st.session_state['disease_spots']:
                r = 2 + (spot.get('plants', 1) * 0.5)
                folium.CircleMarker(location=[spot['lat'], spot['lon']], radius=r, color='crimson', fill=True, fill_opacity=0.9).add_to(m)
            Draw(export=False, position='topleft', draw_options={'polyline':False,'polygon':False,'rectangle':False,'circle':False,'circlemarker':False,'marker':True}, edit_options={'edit': False}).add_to(m)
            out = st_folium(m, height=450, width=None, key="map_step_3")
            if out['last_active_drawing']:
                draw = out['last_active_drawing']
                if draw['geometry']['type'] == 'Point':
                    lon, lat = draw['geometry']['coordinates']
                    if is_point_in_polygon([lat, lon], coords):
                        if not any(abs(s['lat']-lat)<1e-5 for s in st.session_state['disease_spots']):
                            st.session_state['disease_spots'].append({'lat': lat, 'lon': lon, 'plants': 1, 'date': str(st.session_state['detection_date'])})
                            st.rerun()
                    else: st.toast("⚠️ Outside boundary", icon="🚫")
        with col_list:
            st.markdown("#### 📝 Infection Log")
            spots = st.session_state['disease_spots']
            if spots:
                edf = st.data_editor(pd.DataFrame(spots), num_rows="dynamic", column_config={"plants": st.column_config.NumberColumn("Count", min_value=1), "lat": st.column_config.NumberColumn(disabled=True), "lon": st.column_config.NumberColumn(disabled=True), "date": st.column_config.TextColumn(disabled=True)}, hide_index=True, key="editor_spots")
                if edf.to_dict('records') != spots:
                    st.session_state['disease_spots'] = edf.to_dict('records')
                    st.rerun()
            else: st.info("No spots marked.")
        
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ Back"): st.session_state['step'] = 2; st.rerun()
        if c_next.button("Next ➡️"): st.session_state['step'] = 4; st.rerun()

    # ==========================================================================
    # STEP 4: SOIL & MANAGEMENT
    # ==========================================================================
    elif st.session_state['step'] == 4:
        st.subheader("🪨 Step 4: Soil & Management Operations")
        c_id = st.session_state.get('selected_crop_id')
        row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
        is_perennial = row['Type'] == 'Perennial'
        st.markdown("##### Soil Profile & Nutrient Intelligence")
        status_container = st.container()
        c_auto, c_hist = st.columns([1, 2])
        with c_auto:
            if st.button("🛰️ Auto-Detect Soil (AlphaEarth)", help="Derives soil physics and nutrients from OpenLandMap (0-30cm)."):
                with st.spinner("Analyzing soil geostatistics (Texture, Carbon, C:N Ratio)..."):
                    success, data, error_msg = get_auto_soil_profile(st.session_state['field_coords'])
                    if success:
                        st.session_state['soil_type'] = data['texture']
                        years_farming = st.session_state.get('history_years', 0)
                        base_n = data['n_available']
                        base_p = max(8.0, (15.0 + (data['carbon'] * 0.3)) - (data['clay'] * 0.15))
                        base_k = max(60.0, 50.0 + (data['clay'] * 2.0))
                        final_n = base_n * ((1 - 0.05) ** years_farming)
                        final_p = base_p * ((1 - 0.02) ** years_farming)
                        final_k = base_k * ((1 - 0.03) ** years_farming)
                        st.session_state['initial_nitrogen'] = round(final_n, 1)
                        st.session_state['initial_phosphorus'] = round(final_p, 1)
                        st.session_state['initial_potassium'] = round(final_k, 1)
                        status_container.success(f"✅ **Analysis Successful**\n\n**Texture:** {data['texture'].upper()}\n**Organic Carbon:** {data['carbon']:.1f} g/kg\n**Total Nitrogen (Est):** {data['n_total']:.0f} mg/kg\n**Available N (Start):** {final_n:.1f} mg/kg")
                        import time; time.sleep(2.0); st.rerun()
                    else: status_container.error(f"❌ **Detection Failed:** {error_msg}")
        with c_hist:
            st.session_state['history_years'] = st.slider("📉 Land Use History (Years farmed without fertilizer)", 0, 20, 0, help="Reduces initial nutrient levels to account for soil mining.")
        st.divider()
        c_soil_cfg, c_soil_info = st.columns([1, 1])
        with c_soil_cfg:
            expert_mode = st.toggle("Expert Mode (Edit Soil Physics)", value=st.session_state.get('use_expert_soil', False))
            st.session_state['use_expert_soil'] = expert_mode
            if not expert_mode:
                soils = list(_SOIL_TABLE.keys())
                curr_soil = st.session_state.get('soil_type', 'loam').lower()
                if curr_soil not in soils: curr_soil = 'loam'
                selected_soil = st.selectbox("Soil Texture Class", options=[s.title() for s in soils], index=soils.index(curr_soil))
                st.session_state['soil_type'] = selected_soil.lower()
                props = _SOIL_TABLE[st.session_state['soil_type']]
                st.session_state['soil_layers'] = pd.DataFrame([{'depth_top': 0.0, 'depth_bottom': 1.5, 'texture': st.session_state['soil_type'], 'field_capacity': props['field_capacity'], 'wilting_point': props['wilting_point']}])
            st.markdown("###### Initial Available Nutrients (mg/kg)")
            c_n, c_p, c_k = st.columns(3)
            with c_n: st.session_state['initial_nitrogen'] = st.number_input("Nitrogen (N-NO3)", value=float(st.session_state.get('initial_nitrogen', 15.0)), step=1.0, help="Available Nitrogen. <10 is critical deficiency.")
            with c_p: st.session_state['initial_phosphorus'] = st.number_input("Phosphorus (P)", value=float(st.session_state.get('initial_phosphorus', 20.0)), step=1.0)
            with c_k: st.session_state['initial_potassium'] = st.number_input("Potassium (K)", value=float(st.session_state.get('initial_potassium', 100.0)), step=5.0)
        with c_soil_info:
            if expert_mode: st.info("🔧 **Expert Mode Active**: Define horizons manually.")
            else:
                props = _SOIL_TABLE[st.session_state['soil_type']]
                whc = (props['field_capacity'] - props['wilting_point']) * 100
                st.info(f"**Properties ({st.session_state['soil_type'].title()})**")
                st.write(f"Field Capacity: **{props['field_capacity']*100:.0f}%**")
                st.write(f"Wilting Point: **{props['wilting_point']*100:.0f}%**")
                st.metric("Water Holding Capacity", f"{whc:.1f}%")
        if expert_mode:
            st.session_state['soil_layers'] = st.data_editor(st.session_state['soil_layers'], num_rows="dynamic", key="editor_layers", use_container_width=True)
        st.divider()
        c_fert, c_irr = st.columns(2)
        fert_service = FertilizerService()
        product_names = [p['name'] for p in fert_service.products]
        with c_fert:
            st.markdown("##### 🧪 Fertilizer & Operations")
            if is_perennial: st.info("📅 **Recurring Schedule (10 years)**")
            else: st.caption("Add fertilization events.")
            df_fert = st.session_state['fert_schedule']
            if df_fert.empty: df_fert = pd.DataFrame({"date": [date.today() + timedelta(days=30)], "product": ["NPK 15-15-15 Compound"], "amount": [100.0]})
            if 'date' in df_fert.columns: df_fert['date'] = pd.to_datetime(df_fert['date']).dt.date
            edited_fert = st.data_editor(df_fert, num_rows="dynamic", column_config={"date": st.column_config.DateColumn("Date"), "product": st.column_config.SelectboxColumn("Product", options=product_names, width="medium"), "amount": st.column_config.NumberColumn("Amount (kg/ha)", min_value=0, max_value=1000, step=50)}, key="editor_fert")
            st.session_state['fert_schedule'] = edited_fert
        with c_irr:
            st.markdown("##### 💧 Irrigation Schedule")
            if is_perennial: st.info("📅 **Recurring Schedule**")
            else: st.caption("Inputs in **mm** (1 mm = 10,000 L/ha).")
            df_irr = st.session_state['irr_schedule']
            if not df_irr.empty: df_irr['date'] = pd.to_datetime(df_irr['date']).dt.date
            st.session_state['irr_schedule'] = st.data_editor(df_irr, num_rows="dynamic", column_config={"date": st.column_config.DateColumn("Date"), "amount": st.column_config.NumberColumn("Amount (mm)")}, key="editor_irr")
        st.divider()
        c_back, c_next = st.columns([1, 6])
        if c_back.button("⬅️ Back"): st.session_state['step'] = 3; st.rerun()
        if c_next.button("Next: Review ➡️"): st.session_state['step'] = 5; st.rerun()

    # ==========================================================================
    # STEP 5: LAUNCH
    # ==========================================================================
    elif st.session_state['step'] == 5:
        st.subheader("🚀 Step 5: Review & Launch")
        c_sum1, c_sum2 = st.columns(2)
        with c_sum1:
            c_id = st.session_state.get('selected_crop_id')
            row = st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == c_id].iloc[0]
            st.success(f"**Crop:** {row['Crop_Name']} ({row['Variety']})")
            st.info(f"**Planting:** {st.session_state['planting_date']}")
        with c_sum2:
            st.info(f"**Field Area:** {st.session_state.get('area_ha', 0)} ha")
            st.info(f"**Disease Spots:** {len(st.session_state['disease_spots'])}")
        c_save, c_run = st.columns(2)
        with c_save:
            st.download_button("💾 Save Config", data=StateManager.save_config_to_json(), file_name="field_config.json", mime="application/json", use_container_width=True)
        with c_run:
            if st.button("🔥 Initialize Digital Twin", type="primary", use_container_width=True):
                st.session_state['setup_complete'] = True
                st.session_state['nav_target'] = "Intelligence Dashboard"
                if 'sim_results' in st.session_state: del st.session_state['sim_results']
                st.rerun()
        if st.button("⬅️ Back to Edit"): st.session_state['step'] = 4; st.rerun()