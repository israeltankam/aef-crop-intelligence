# pages\main\surveillance.py
import streamlit as st
import pandas as pd
import json
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
from datetime import date
import altair as alt
from src.models.state_manager import StateManager
from src.utils.i18n import tr
from src.models.calibration_engine import CalibrationEngine
from src.models.adaptive_calibration import ActiveLearningAdvisor

# --- HELPER FUNCTIONS ---
def is_point_in_polygon(point, polygon_coords):
    """
    Ray-casting algorithm to check if point (lat, lon) is inside polygon.
    """
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

# --- MAIN APP ---

def render_cooperative_surveillance():
    """Adaptive surveillance workflow adapted to cooperative plot networks."""
    st.title('🤝 ' + tr('Cooperative adaptive surveillance'))
    if 'surveillance_logs' not in st.session_state:
        st.session_state['surveillance_logs'] = []
    parcels = [p for p in st.session_state.get('cooperative_parcels', []) if p.get('active', True)]
    if not parcels:
        st.warning(tr('Please complete the configuration in Site Setup first.'))
        return
    scope = st.radio(tr('Observation scope'), ['cooperative', 'plot'], format_func=lambda x: tr('Whole cooperative perimeter') if x == 'cooperative' else tr('One plot'), horizontal=True)
    plot_id = None
    if scope == 'plot':
        plot_options = [p['id'] for p in parcels]
        plot_id = st.selectbox(tr('Plot'), plot_options, format_func=lambda pid: next((p.get('name', pid) for p in parcels if p['id'] == pid), pid))
    c1, c2, c3 = st.columns(3)
    with c1:
        obs_date = st.date_input(tr('Date of Observation'), date.today(), key='coop_obs_date')
    with c2:
        category = st.selectbox(tr('Measurement Category'), [tr('Disease Status'), tr('Soil Nutrients'), tr('Yield / Biomass')], key='coop_obs_category')
    with c3:
        confidence = st.slider(tr('confidence'), 0.1, 1.0, 0.8, 0.05, key='coop_obs_confidence')
    values = {}
    if category == tr('Disease Status'):
        values['incidence_pct'] = st.number_input(tr('Disease Incidence (%)'), min_value=0.0, max_value=100.0, value=0.0, step=1.0, key='coop_obs_inc')
    elif category == tr('Soil Nutrients'):
        values['soil_n'] = st.number_input(tr('Soil N (mg/kg)'), min_value=0.0, value=10.0, step=1.0, key='coop_obs_n')
        values['soil_p'] = st.number_input(tr('Soil P (ppm)'), min_value=0.0, value=20.0, step=1.0, key='coop_obs_p')
        values['soil_k'] = st.number_input(tr('Soil K (ppm)'), min_value=0.0, value=100.0, step=5.0, key='coop_obs_k')
    else:
        values['yield_t_ha'] = st.number_input(tr('Yield (t/ha)'), min_value=0.0, value=0.0, step=0.1, key='coop_obs_yield')
    if st.button(tr('Save Observation'), type='primary'):
        st.session_state['surveillance_logs'].append({
            'mode': 'cooperative',
            'scope': scope,
            'plot_id': plot_id,
            'date': str(obs_date),
            'category': category,
            'confidence': confidence,
            **values,
        })
        st.success(tr('Observation Logged.'))
    st.divider()
    logs = [l for l in st.session_state.get('surveillance_logs', []) if l.get('mode') == 'cooperative' or 'mode' not in l]
    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True, hide_index=True)
    else:
        st.info(tr('No observations recorded yet.'))
    if st.session_state.get('sim_results') and st.session_state['sim_results'].get('mode') == 'cooperative':
        res = st.session_state['sim_results']
        risk_rows = []
        for parcel in res.get('parcel_results', []):
            last = parcel['history'][-1]
            risk_rows.append({
                tr('Plot ID'): parcel['id'],
                tr('Plot name'): parcel['name'],
                tr('Disease incidence'): float(last.get('Incidence', 0.0)) * 100,
                tr('Metapopulation pressure'): float(last.get('Metapopulation_Pressure', 0.0)) * 100,
                tr('Water stress'): float(last.get('Avg_Stress', 0.0)) * 100,
            })
        if risk_rows:
            df_risk = pd.DataFrame(risk_rows).sort_values(tr('Disease incidence'), ascending=False)
            top = df_risk.iloc[0]
            st.info(f"{tr('Suggested next field check:')} {top[tr('Plot name')]} - {tr('Disease incidence')} {top[tr('Disease incidence')]:.1f}%")
            st.dataframe(df_risk, use_container_width=True, hide_index=True)

def app():
    if st.session_state.get('app_mode') == 'cooperative':
        render_cooperative_surveillance()
        return
    st.title("📈 " + tr("Adaptive Surveillance & Calibration"))
    
    st.markdown(f"**{tr('Fine-Tune your Digital Twin.')}**\n\n{tr('Enter real-world field measurements below.')}")
    
    # Initialize Log State
    if 'surveillance_logs' not in st.session_state:
        st.session_state['surveillance_logs'] = []

    # ==========================================================================
    # 0. DATA I/O (LOAD / SAVE)
    # ==========================================================================
    with st.expander("📂 " + tr("Manage Log Data (Load/Save)"), expanded=False):
        c_down, c_up = st.columns(2)
        
        # SAVE
        with c_down:
            st.markdown("#### 💾 " + tr("Save Logs"))
            logs_json = json.dumps(st.session_state['surveillance_logs'], indent=4)
            st.download_button(
                label=tr("Download Logs as JSON"),
                data=logs_json,
                file_name=f"surveillance_logs_{date.today()}.json",
                mime="application/json",
                help=tr("Save your current observations to a file so you can reload them later.")
            )

        # LOAD
        with c_up:
            st.markdown("#### 📂 " + tr("Load Logs"))
            uploaded_file = st.file_uploader(tr("Upload JSON Log File"), type=["json"])
            if uploaded_file is not None:
                try:
                    data = json.load(uploaded_file)
                    if isinstance(data, list):
                        if st.button("⚠️ " + tr("Overwrite Current Logs")):
                            st.session_state['surveillance_logs'] = data
                            st.success(tr("Loaded {n} observations.", n=len(data)))
                            st.rerun()
                    else:
                        st.error(tr("Invalid JSON format. Expected a list of records."))
                except Exception as e:
                    st.error(f"{tr('Error reading file:')} {e}")

    st.divider()

    # ==========================================================================
    # 1. INPUT SECTION
    # ==========================================================================
    st.subheader("📝 " + tr("Field Observations Log"))
    
    current_logs = st.session_state['surveillance_logs']
    
    with st.expander(tr("Add New Measurement"), expanded=True):
        c_date, c_type = st.columns([1, 2])
        with c_date:
            m_date = st.date_input(tr("Date of Observation"), value=date.today())
        with c_type:
            m_category = st.selectbox(tr("Measurement Category"), [
                "Yield / Biomass", 
                "Soil Nutrients", 
                "Disease Status"
            ], format_func=tr)

        # --- DYNAMIC INPUT UI BASED ON CATEGORY ---
        if m_category == "Disease Status":
            # Toggle for Direct vs Spot-Based
            input_mode = st.radio(tr("Input Method"), ["From Field Spots (Map)", "Direct Incidence (%)"], horizontal=True, format_func=tr)
            
            if input_mode == "Direct Incidence (%)":
                m_val = st.number_input(tr("Field Incidence (%)"), min_value=0.0, max_value=100.0, step=0.1)
                log_type = "Disease Incidence (%)"
                
            else: # Spot-Based (MAP)
                st.markdown("##### 📍 " + tr("Interactive Spot Locator"))
                st.caption(tr("Click on the map to place infected spots. The system will calculate incidence based on area."))
                
                # Context
                area = st.session_state.get('area_ha', 1.0)
                density = st.session_state.get('planting_density', 10000)
                total_plants = area * density
                
                if 'temp_spots' not in st.session_state: st.session_state['temp_spots'] = []

                # --- MAP LOGIC ---
                coords = st.session_state.get('field_coords', [])
                if coords:
                    bounds = get_bounds(coords)
                    center = [(bounds[0][0]+bounds[1][0])/2, (bounds[0][1]+bounds[1][1])/2]
                    
                    m = folium.Map(location=center, zoom_start=17, max_zoom=20)
                    if bounds: m.fit_bounds(bounds)
                    
                    # Field Boundary
                    folium.Polygon(locations=coords, color="blue", weight=2, fill=True, fill_opacity=0.1).add_to(m)
                    
                    # Existing Temp Spots
                    for i, spot in enumerate(st.session_state['temp_spots']):
                        folium.Marker(
                            location=[spot['lat'], spot['lon']],
                            icon=folium.Icon(color='red', icon='virus', prefix='fa'),
                            tooltip=f"Spot #{i+1} ({spot['count']} plants)"
                        ).add_to(m)
                    
                    # Draw Control
                    Draw(
                        export=False, 
                        position='topleft',
                        draw_options={
                            'polyline': False,
                            'polygon': False,
                            'rectangle': False,
                            'circle': False,
                            'circlemarker': False,
                            'marker': True
                        },
                        edit_options={'edit': False}
                    ).add_to(m)
                    
                    output = st_folium(m, height=400, width=None, key="surveillance_map")
                    
                    # Handle Click
                    if output['last_active_drawing']:
                        draw = output['last_active_drawing']
                        if draw['geometry']['type'] == 'Point':
                            lon, lat = draw['geometry']['coordinates']
                            
                            # Check if inside field
                            if is_point_in_polygon([lat, lon], coords):
                                # Avoid duplicate clicks (simple debounce)
                                if not any(abs(s['lat'] - lat) < 1e-5 and abs(s['lon'] - lon) < 1e-5 for s in st.session_state['temp_spots']):
                                    # Default count 5 (cluster), user can edit below
                                    st.session_state['temp_spots'].append({'lat': lat, 'lon': lon, 'count': 5}) 
                                    st.rerun()
                            else:
                                st.toast("⚠️ Point outside field boundary.", icon="🚫")
                else:
                    st.warning(tr("No field boundary defined. Please go to Site Setup."))

                # --- SPOT TABLE & CALC ---
                if st.session_state['temp_spots']:
                    st.info(tr("Edit plant counts for detected spots below:"))
                    
                    # Editable Table for Counts
                    df_spots = pd.DataFrame(st.session_state['temp_spots'])
                    edited_spots = st.data_editor(
                        df_spots, 
                        column_config={
                            "lat": st.column_config.NumberColumn(disabled=True),
                            "lon": st.column_config.NumberColumn(disabled=True),
                            "count": st.column_config.NumberColumn("Infected Plants", min_value=1, step=1)
                        },
                        use_container_width=True,
                        num_rows="dynamic",
                        key="spot_editor"
                    )
                    
                    # Update State from Editor
                    st.session_state['temp_spots'] = edited_spots.to_dict('records')
                    
                    # Calculate Incidence
                    total_infected = sum([s['count'] for s in st.session_state['temp_spots']])
                    calc_incidence = (total_infected / total_plants) * 100.0
                    
                    c_met1, c_met2, c_btn = st.columns([1, 1, 1])
                    c_met1.metric("Total Infected Plants", f"{total_infected}")
                    c_met2.metric("Calculated Incidence", f"{calc_incidence:.4f}%")
                    
                    m_val = calc_incidence
                    log_type = "Disease Incidence (%)"
                    
                    if c_btn.button("🗑️ Clear All Spots"):
                        st.session_state['temp_spots'] = []
                        st.rerun()
                else:
                    st.caption(tr("No spots marked yet."))
                    m_val = 0.0
                    log_type = "Disease Incidence (%)"

        elif m_category == "Soil Nutrients":
            log_type = st.selectbox(tr("Nutrient"), ["Soil N (mg/kg)", "Soil P (ppm)", "Soil K (ppm)"], format_func=tr)
            m_val = st.number_input(tr("Concentration"), min_value=0.0, step=0.1)
            
        else: # Yield / Biomass
            log_type = st.selectbox(tr("Metric"), ["Yield (t/ha)", "Biomass (t/ha)"], format_func=tr)
            m_val = st.number_input(tr("Value (t/ha)"), min_value=0.0, step=0.1)

        # SAVE BUTTON
        st.write("")
        if st.button("💾 " + tr("Save Observation"), type="primary"):
            if m_val is not None:
                st.session_state['surveillance_logs'].append({
                    'Date': str(m_date),
                    'Type': log_type,
                    'Value': m_val
                })
                # Clear temp spots if used
                if 'temp_spots' in st.session_state: st.session_state['temp_spots'] = []
                st.success(tr("Observation Logged."))
                st.rerun()

    # Editable Log Table
    if current_logs:
        df_logs = pd.DataFrame(current_logs)
        edited_df = st.data_editor(df_logs, num_rows="dynamic", use_container_width=True, key="main_log_editor")
        st.session_state['surveillance_logs'] = edited_df.to_dict('records')
    else:
        st.info(tr("No observations recorded yet."))

    st.divider()

    # ==========================================================================
    # 2. CALIBRATION CONTROL
    # ==========================================================================
    st.subheader("⚙️ " + tr("Engine Calibration"))
    
    c_cal, c_info = st.columns([1, 2])
    
    with c_cal:
        st.markdown(tr("Run the calibration loop to minimize errors."))
        # Only enable if logs exist
        if st.button("🚀 " + tr("Run Calibration Loop"), type="primary", disabled=len(current_logs) < 1):
            with st.spinner(tr("Running optimization (Differential Evolution + Hessian)...")):
                cal_engine = CalibrationEngine()
                
                # Reconstruct Config
                config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
                get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
                config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
                config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
                if st.session_state.get('soil_layers') is not None:
                    config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
                else:
                    config['soil_layers'] = []
                
                # Check Crop Type
                df_c = st.session_state['df_crops']
                crop_row = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
                crop_type = crop_row['Type']
                
                # Execute
                new_params, msg = cal_engine.calibrate_model(st.session_state['surveillance_logs'], config, crop_type)
                
                if new_params:
                    st.session_state['calibrated_params'] = new_params
                    st.session_state['sim_results'] = None # Force re-run of dashboard
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
    
    with c_info:
        params = st.session_state.get('calibrated_params', {})
        if params:
            st.markdown("##### 🧬 " + tr("Calibrated Genotype"))
            
            # Extract Uncertainties if present
            unc = params.get('uncertainty', {})
            
            # Metrics Display
            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                base_rue = float(st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == st.session_state['selected_crop_id']].iloc[0]['RUE_g_MJ'])
                mult_rue = params['RUE_g_MJ'] / base_rue
                std_rue = unc.get('RUE_mult_std', 0.0)
                st.metric(tr("RUE (Photosynthesis)"), f"{params['RUE_g_MJ']:.2f} g/MJ", f"x{mult_rue:.2f} ±{std_rue:.2f}")

            with c_p2:
                base_hi = float(st.session_state['df_crops'][st.session_state['df_crops']['Crop_ID'] == st.session_state['selected_crop_id']].iloc[0]['Harvest_Index'])
                mult_hi = params['Harvest_Index'] / base_hi
                std_hi = unc.get('HI_mult_std', 0.0)
                st.metric(tr("Harvest Index"), f"{params['Harvest_Index']:.2f}", f"x{mult_hi:.2f} ±{std_hi:.2f}")

            with c_p3:
                # Disease Beta
                if 'Beta_Infection' in params:
                    base_beta = 0.0
                    if st.session_state['selected_disease_id']:
                         base_beta = float(st.session_state['df_diseases'][st.session_state['df_diseases']['Disease_ID'] == st.session_state['selected_disease_id']].iloc[0]['Beta_Infection'])
                    
                    if base_beta > 0:
                        mult_beta = params['Beta_Infection'] / base_beta
                        std_beta = unc.get('Beta_std', 0.0)
                        st.metric(tr("Spread Rate (Beta)"), f"{params['Beta_Infection']:.3f}", f"x{mult_beta:.2f} ±{std_beta:.2f}")

            if st.button("❌ " + tr("Reset Calibration")):
                st.session_state['calibrated_params'] = {}
                st.rerun()
        else:
            st.warning("⚠️ " + tr("Model is running on Generic Defaults (Uncalibrated)"))

    st.divider()

    # ==========================================================================
    # 3. VALIDATION CHART
    # ==========================================================================
    if st.session_state.get('sim_results') and current_logs:
        advisor = ActiveLearningAdvisor()
        advice = advisor.suggest_next_measurement(st.session_state['sim_results']['history'], current_logs)
        if advice:
            st.info(f"{tr('Suggested next field check:')} {advice.measurement_type} {tr('around')} {advice.date}. {advice.reason}")
        st.subheader("📊 " + tr("Validation: Observed vs Modeled"))
        
        hist = pd.DataFrame(st.session_state['sim_results']['history'])
        hist['Date'] = pd.to_datetime(hist['Date']).dt.date
        
        # Prepare Obs Data
        df_obs = pd.DataFrame(current_logs)
        df_obs['Date'] = pd.to_datetime(df_obs['Date']).dt.date
        
        # Chart Logic - Yield
        target_types = ['Yield (t/ha)', 'Biomass (t/ha)']
        df_obs_bio = df_obs[df_obs['Type'].isin(target_types)].copy()
        
        if not df_obs_bio.empty:
            base = alt.Chart(hist).encode(x='Date:T')
            line = base.mark_line(color='green').encode(
                y=alt.Y('Yield:Q', title='Modeled Yield (t/ha)'),
                tooltip=['Date', 'Yield']
            )
            points = alt.Chart(df_obs_bio).mark_point(color='red', size=100, filled=True).encode(
                x='Date:T',
                y=alt.Y('Value:Q'),
                tooltip=['Date', 'Value', 'Type']
            )
            st.altair_chart((line + points).interactive(), use_container_width=True)
            
        # Chart Logic - Disease
        df_obs_dis = df_obs[df_obs['Type'] == 'Disease Incidence (%)'].copy()
        if not df_obs_dis.empty:
            st.markdown("#### 🦠 " + tr("Disease Progression Fit"))
            base_d = alt.Chart(hist).encode(x='Date:T')
            # Model incidence is 0-1, User input is 0-100. Normalize model to 100 for display
            hist['Incidence_Pct'] = hist['Incidence'] * 100.0
            
            line_d = base_d.mark_line(color='purple').encode(
                y=alt.Y('Incidence_Pct:Q', title='Modeled Incidence (%)'),
                tooltip=['Date', 'Incidence_Pct']
            )
            points_d = alt.Chart(df_obs_dis).mark_point(color='orange', size=100, filled=True).encode(
                x='Date:T',
                y=alt.Y('Value:Q'),
                tooltip=['Date', 'Value']
            )
            st.altair_chart((line_d + points_d).interactive(), use_container_width=True)