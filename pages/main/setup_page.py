#pages\main\setup_page.py
import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from geopy.geocoders import Nominatim
from src.models.state_manager import StateManager
from datetime import date
import json
import ee
from google.oauth2.service_account import Credentials

# --- CONSTANTS (From Grainly) ---
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

# --- HELPER: EARTH ENGINE SETUP ---
def initialize_ee():
    """Initializes Earth Engine using Service Account with explicit Scopes."""
    if st.session_state.get('ee_initialized', False):
        return True

    try:
        service_account_info = st.secrets["gcp_service_account"]
        scopes = ['https://www.googleapis.com/auth/earthengine']
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        ee.Initialize(credentials=creds)
        st.session_state['ee_initialized'] = True
        return True
    except Exception as e:
        st.error("🛑 Earth Engine Authentication Failed")
        st.exception(e) 
        st.stop()
        return False

# --- HELPER: GEOSPATIAL MATH ---
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

# --- NEW: LAND COVER VALIDATOR ---
def validate_land_cover_ee(polygon_coords_latlon):
    if not initialize_ee(): return True, "Offline mode", {}
    
    ee_coords = [[p[1], p[0]] for p in polygon_coords_latlon]
    if ee_coords[0] != ee_coords[-1]: ee_coords.append(ee_coords[0])
    geom = ee.Geometry.Polygon([ee_coords])
    
    img = ee.ImageCollection("ESA/WorldCover/v100").filterBounds(geom).mosaic().select("Map").clip(geom)
    
    try:
        stats = img.reduceRegion(reducer=ee.Reducer.frequencyHistogram(), geometry=geom, scale=10, maxPixels=1e9)
        hist = stats.get('Map').getInfo()
        if not hist: return True, "No Data", {}

        total_pixels = sum(hist.values())
        class_names = {'10':'Trees','20':'Shrubland','30':'Grassland','40':'Cropland','50':'Urban/Street','60':'Bare/Dirt','70':'Snow/Ice','80':'Water','90':'Wetland','95':'Mangrove'}
        breakdown = {class_names.get(k, k): v for k, v in hist.items()}
        
        urban_count = hist.get('50', 0)
        if (urban_count / total_pixels) > 0.01: return False, f"Detected Street/Building ({urban_count} pixels).", breakdown
        water_count = hist.get('80', 0) + hist.get('90', 0) + hist.get('95', 0)
        if (water_count / total_pixels) > 0.05: return False, "Area contains water or wetland.", breakdown
            
        return True, "Land valid", breakdown
    except Exception as e:
        return True, "Validation skipped (Error)", {}

# --- NEW: AUTO SOIL RETRIEVAL ---
def get_auto_soil_profile(coords):
    """
    Fetches dominant soil texture and Organic Carbon from OpenLandMap.
    """
    if not initialize_ee(): return None, "Offline"

    try:
        ee_coords = [[p[1], p[0]] for p in coords]
        geom = ee.Geometry.Polygon([ee_coords])
        
        # 1. Texture Class (USDA)
        # Band b0 is surface (0cm)
        tex_img = ee.Image("OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02").select('b0').clip(geom)
        tex_stats = tex_img.reduceRegion(reducer=ee.Reducer.mode(), geometry=geom, scale=250)
        tex_class_id = tex_stats.get('b0').getInfo()
        
        # Map USDA ID to strings in _SOIL_TABLE
        # 1:Cl, 2:SiCl, 3:SaCl, 4:ClLo, 5:SiClLo, 6:SaClLo, 7:Lo, 8:SiLo, 9:SaLo, 10:Si, 11:LoSa, 12:Sa
        usda_map = {
            1: 'clay', 2: 'silty clay', 3: 'sandy clay', 4: 'clay loam', 
            5: 'silty clay loam', 6: 'sandy clay loam', 7: 'loam', 8: 'silt loam', 
            9: 'sandy loam', 10: 'silt', 11: 'loamy sand', 12: 'sand'
        }
        detected_texture = usda_map.get(tex_class_id, 'loam') # Default fallback

        # 2. Organic Carbon (g/kg)
        oc_img = ee.Image("OpenLandMap/SOL/SOL_ORGANIC-CARBON_USDA-6A1C_M/v02").select('b0').clip(geom)
        oc_stats = oc_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=250)
        organic_carbon = oc_stats.get('b0').getInfo() # g/kg (e.g. 15 g/kg = 1.5%)
        
        return detected_texture, organic_carbon

    except Exception as e:
        print(f"Soil Auto-Detect Error: {e}")
        return None, str(e)

# --- MAIN PAGE LOGIC ---
def app():
    if 'step' not in st.session_state: StateManager.initialize()
    st.title("🛠️ Digital Twin Configuration")

    # Navigation
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
        
        with st.expander("📂 Load Saved Configuration (.json)", expanded=False):
            uploaded_file = st.file_uploader("Drop your field_config.json here", type="json")
            if uploaded_file is not None:
                if StateManager.load_config_from_json(uploaded_file):
                    st.success("Configuration loaded!")
                    if st.button("🚀 Jump to Review"): st.session_state['step'] = 5; st.rerun()
        
        c1, c2 = st.columns([3, 1])
        with c1: search = st.text_input("Search Location", "Garoua, Cameroon")
        with c2:
            st.write("")
            if st.button("🔍 Locate"):
                try:
                    geolocator = Nominatim(user_agent="aef_app_v2")
                    loc = geolocator.geocode(search)
                    if loc:
                        st.session_state['center_lat'] = loc.latitude
                        st.session_state['center_lon'] = loc.longitude
                        st.rerun()
                except: st.error("Location not found.")

        if st.session_state['field_coords']:
            area = st.session_state.get('area_ha', 0.0)
            c_msg, c_next, c_reset = st.columns([2, 1, 1])
            with c_msg: st.success(f"✅ Boundary Captured. **Area: {area} ha**")
            with c_next: 
                if st.button("Next Step ➡️", type="primary", use_container_width=True): st.session_state['step'] = 2; st.rerun()
            with c_reset:
                if st.button("🔄 Redraw", type="secondary", use_container_width=True):
                    st.session_state['field_coords'] = []; st.session_state['area_ha'] = 0.0; st.rerun()
        else: st.info("👆 Use the polygon tool on the left of the map to draw your field.")

        m = folium.Map(location=[st.session_state['center_lat'], st.session_state['center_lon']], zoom_start=16, max_zoom=20)
        if not st.session_state['field_coords']:
            Draw(export=False, position='topleft', draw_options={'polyline':False,'rectangle':False,'circle':False,'marker':False,'circlemarker':False,'polygon':True}, edit_options={'edit': False}).add_to(m)
        else:
            folium.Polygon(locations=st.session_state['field_coords'], color="blue", fill=True, fill_opacity=0.3).add_to(m)

        output = st_folium(m, height=500, width=800, key="map_step_1")

        if output['all_drawings'] and not st.session_state['field_coords']:
            last_draw = output['all_drawings'][-1]
            if last_draw['geometry']['type'] == 'Polygon':
                raw = last_draw['geometry']['coordinates'][0]
                coords = [[p[1], p[0]] for p in raw]
                with st.spinner("🛰️ Validating land cover with AlphaEarth..."):
                    is_valid, reason, breakdown = validate_land_cover_ee(coords)
                if breakdown:
                    sorted_bd = dict(sorted(breakdown.items(), key=lambda item: item[1], reverse=True))
                    st.info(f"**Satellite Analysis:** {sorted_bd}")
                if is_valid:
                    st.session_state['field_coords'] = coords
                    st.session_state['area_ha'] = calculate_area_ha(coords)
                    st.rerun()
                else: st.error(f"🚫 Invalid Field: {reason}")

        if st.session_state['field_coords']:
            st.divider()
            c_back, c_next = st.columns([1, 6])
            with c_next:
                if st.button("Next ➡️"): st.session_state['step'] = 2; st.rerun()

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
            
            # Get the specific row for this variety
            row = varieties[varieties['Variety'] == selected_var].iloc[0]
            new_crop_id = row['Crop_ID']
            
            # --- AUTO-UPDATE DENSITY LOGIC ---
            # If the user switched crops, update the density to the new crop's default
            if st.session_state.get('selected_crop_id') != new_crop_id:
                st.session_state['selected_crop_id'] = new_crop_id
                # Check if 'Default_Density' column exists (backward compatibility)
                if 'Default_Density' in row:
                    st.session_state['planting_density'] = int(row['Default_Density'])
                    # Rerun to visually update the number_input below immediately
                    st.rerun()
            
        with c_date:
            st.session_state['planting_date'] = st.date_input(
                "Planting Date", value=st.session_state['planting_date']
            )
            
            # This input now defaults to the updated session_state['planting_density']
            st.session_state['planting_density'] = st.number_input(
                "Planting Density (plants/ha)", 
                value=int(st.session_state.get('planting_density', 10000)),
                step=100
            )

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
        rel_d = df_d[df_d['Target_Crop_Name'] == c_row['Crop_Name']]
        
        c_dis, c_date = st.columns([2, 1])
        selected_d_type = ""

        with c_dis:
            if rel_d.empty: 
                st.warning("No specific diseases.")
                st.session_state['selected_disease_id'] = None
            else:
                d_name = st.selectbox("Select Threat", rel_d['Disease_Name'].unique())
                dis_row = rel_d[rel_d['Disease_Name'] == d_name].iloc[0]
                st.session_state['selected_disease_id'] = dis_row['Disease_ID']
                selected_d_type = dis_row['Type']

        with c_date:
            st.session_state['detection_date'] = st.date_input("Detection Date", value=st.session_state['detection_date'])
            
            # --- CONDITIONAL SLIDER LOGIC (MODIFIED HERE) ---
            if 'fungal' in str(selected_d_type).lower() or 'bacterial' in str(selected_d_type).lower():
                st.info(f"💨 **Wind/Rain Driven:** {selected_d_type}")
                st.caption("Spread is modeled using Wind Field vectors from Earth Engine.")
                st.session_state['insect_pressure'] = 1.0 # Default for non-vector
            else:
                st.info(f"🦟 **Vector Driven:** {selected_d_type}")
                st.session_state['insect_pressure'] = st.slider(
                    "Vector Pressure (Observed)", 0.0, 5.0, 
                    st.session_state.get('insect_pressure', 1.0),
                    help="Relative abundance of the vector (e.g., Whitefly count)."
                )
        
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
    # STEP 4: SOIL & MANAGEMENT (UPDATED WITH NPK)
    # ==========================================================================
    elif st.session_state['step'] == 4:
        st.subheader("🪨 Step 4: Soil & Management Operations")
        
        # --- 1. SOIL PROFILE SECTION ---
        st.markdown("##### Soil Profile")
        
        # Auto-Detect Button
        if st.button("🛰️ Auto-Detect Soil Profile (AlphaEarth)", help="Fetches texture and carbon from OpenLandMap"):
            with st.spinner("Scanning soil data..."):
                tex, carbon = get_auto_soil_profile(st.session_state['field_coords'])
                if tex:
                    st.session_state['soil_type'] = tex
                    # Estimating N from Organic Carbon (Simple heuristic)
                    est_n = min(150.0, max(40.0, carbon * 5.0))
                    st.session_state['initial_nitrogen'] = est_n
                    
                    # Assume P and K scale somewhat with fertility/carbon for defaults (very rough heuristic)
                    st.session_state['initial_phosphorus'] = max(10.0, carbon * 2.0)
                    st.session_state['initial_potassium'] = max(50.0, carbon * 8.0)
                    
                    st.success(f"Detected: **{tex.title()}** | Organic Carbon: **{carbon:.1f} g/kg**")
                    import time; time.sleep(1.5); st.rerun()
                else:
                    st.error(f"Detection failed: {carbon}")

        c_soil_cfg, c_soil_info = st.columns([1, 1])
        
        with c_soil_cfg:
            # Expert Mode Toggle
            expert_mode = st.toggle("Expert Mode (Edit Layers)", value=st.session_state.get('use_expert_soil', False))
            st.session_state['use_expert_soil'] = expert_mode

            if not expert_mode:
                # STANDARD MODE: Simple Dropdown
                soils = list(_SOIL_TABLE.keys())
                curr_soil = st.session_state.get('soil_type', 'loam').lower()
                if curr_soil not in soils: curr_soil = 'loam'
                
                selected_soil = st.selectbox(
                    "Soil Texture Class", 
                    options=[s.title() for s in soils], 
                    index=soils.index(curr_soil)
                )
                st.session_state['soil_type'] = selected_soil.lower()
                
                props = _SOIL_TABLE[st.session_state['soil_type']]
                st.session_state['soil_layers'] = pd.DataFrame([{
                    'depth_top': 0.0, 
                    'depth_bottom': 1.5, 
                    'texture': st.session_state['soil_type'],
                    'field_capacity': props['field_capacity'], 
                    'wilting_point': props['wilting_point'] 
                }])
            
            # NUTRIENT INPUTS (UPDATED FOR NPK)
            st.markdown("###### Initial Soil Nutrient Status (kg/ha)")
            c_n, c_p, c_k = st.columns(3)
            with c_n:
                st.session_state['initial_nitrogen'] = st.number_input(
                    "Nitrogen (N)", 
                    value=float(st.session_state.get('initial_nitrogen', 70.0)), 
                    step=5.0, help="Available Nitrate-N"
                )
            with c_p:
                st.session_state['initial_phosphorus'] = st.number_input(
                    "Phosphorus (P)", 
                    value=float(st.session_state.get('initial_phosphorus', 30.0)), 
                    step=5.0, help="Available P (Olsen/Bray)"
                )
            with c_k:
                st.session_state['initial_potassium'] = st.number_input(
                    "Potassium (K)", 
                    value=float(st.session_state.get('initial_potassium', 100.0)), 
                    step=5.0, help="Exchangeable K"
                )

        with c_soil_info:
            if expert_mode:
                st.info("🔧 **Expert Mode Active**")
                st.caption("Define custom soil horizons below.")
            else:
                props = _SOIL_TABLE[st.session_state['soil_type']]
                st.info(f"**Standard Properties ({st.session_state['soil_type'].title()})**")
                st.write(f"- Field Capacity: **{props['field_capacity']*100:.0f}%**")
                st.write(f"- Wilting Point: **{props['wilting_point']*100:.0f}%**")
                st.caption("Values derived from USDA texture class averages.")

        # EXPERT EDITOR (Only if toggled)
        if expert_mode:
            st.markdown("###### Custom Soil Layers")
            edited_layers = st.data_editor(
                st.session_state['soil_layers'],
                num_rows="dynamic",
                key="editor_layers",
                use_container_width=True
            )
            st.session_state['soil_layers'] = edited_layers

        st.divider()

        # --- 2. MANAGEMENT SCHEDULES ---
        c_fert, c_irr = st.columns(2)
        with c_fert:
            st.markdown("##### 🧪 Fertilizer Schedule (NPK)")
            df_fert = st.session_state['fert_schedule']
            if not df_fert.empty: df_fert['date'] = pd.to_datetime(df_fert['date']).dt.date
            
            # Updated Column Config for N, P, K
            st.session_state['fert_schedule'] = st.data_editor(
                df_fert, 
                num_rows="dynamic", 
                column_config={
                    "date": st.column_config.DateColumn("Date"), 
                    "amount_n": st.column_config.NumberColumn("N (kg/ha)", min_value=0, max_value=500),
                    "amount_p": st.column_config.NumberColumn("P (kg/ha)", min_value=0, max_value=500),
                    "amount_k": st.column_config.NumberColumn("K (kg/ha)", min_value=0, max_value=500)
                }, 
                key="editor_fert"
            )
            st.caption("Enter amounts for Nitrogen, Phosphorus, and Potassium separately.")
            
        with c_irr:
            st.markdown("##### 💧 Irrigation Schedule")
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