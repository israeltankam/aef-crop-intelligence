#pages\main\dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation
from datetime import date, timedelta
from src.models.state_manager import StateManager
from src.models.simulation_engine import SimulationEngine
import ee
from google.oauth2.service_account import Credentials

# --- HELPER: SENTINEL-2 NDVI FETCH ---
def fetch_sentinel_ndvi(coords, start_date, end_date):
    """
    Fetches Sentinel-2 time series for the field polygon.
    Returns DataFrame: [Date, NDVI]
    """
    # 1. Initialize EE
    if not st.session_state.get('ee_initialized'):
        try:
            if 'gcp_service_account' in st.secrets:
                service_account_info = st.secrets["gcp_service_account"]
                scopes = ['https://www.googleapis.com/auth/earthengine']
                creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                ee.Initialize(credentials=creds)
                st.session_state['ee_initialized'] = True
        except:
            return None

    try:
        # 2. Geometry
        ee_coords = [[p[1], p[0]] for p in coords]
        geom = ee.Geometry.Polygon([ee_coords])
        
        # 3. Collection (Sentinel-2 Surface Reflectance)
        def mask_s2_clouds(image):
            qa = image.select('QA60')
            cloud_bit_mask = 1 << 10
            cirrus_bit_mask = 1 << 11
            mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
            return image.updateMask(mask).divide(10000)

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
            .filterDate(str(start_date), str(end_date))\
            .filterBounds(geom)\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
            .map(mask_s2_clouds)
        
        # 4. Reduction Function
        def get_ndvi(image):
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            stats = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=20)
            return ee.Feature(None, {
                'date': image.date().format('YYYY-MM-dd'),
                'ndvi': stats.get('NDVI')
            })
            
        # 5. Execute
        count = s2.size().getInfo()
        if count == 0: return pd.DataFrame(columns=['Date', 'NDVI'])
        
        ndvi_series = s2.map(get_ndvi).reduceColumns(ee.Reducer.toList(2), ['date', 'ndvi']).getInfo()['list']
        
        df = pd.DataFrame(ndvi_series, columns=['Date', 'NDVI'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.dropna()
        return df.sort_values('Date')

    except Exception as e:
        print(f"Sentinel Error: {e}")
        return None

# --- MAIN DASHBOARD ---
def app():
    # Ensure state
    if 'step' not in st.session_state: StateManager.initialize()
    
    st.title("🛰️ Intelligence Dashboard")
    
    if not st.session_state.get('setup_complete'):
        st.error("Please complete the Setup Wizard first.")
        return

    # --- 1. SIMULATION MANAGEMENT ---
    should_run = 'sim_results' not in st.session_state
    
    # Validate cache keys
    if not should_run:
        try:
            # Check if new NPK keys exist in history
            if 'N_kg' not in st.session_state['sim_results']['history'][0]:
                should_run = True
        except:
            should_run = True

    if should_run:
        with st.spinner("Running Bio-Physical Digital Twin..."):
            engine = SimulationEngine()
            config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
            
            # Schedules
            get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
            config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
            config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
            
            # Simulation Constants
            config['soil_water_holding_cap'] = st.session_state.get('soil_water_holding_cap', 150.0)
            config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
            config['initial_nitrogen'] = st.session_state.get('initial_nitrogen', 100.0)
            config['initial_phosphorus'] = st.session_state.get('initial_phosphorus', 30.0)
            config['initial_potassium'] = st.session_state.get('initial_potassium', 100.0)
            
            config['insect_pressure'] = st.session_state.get('insect_pressure', 1.0)
            config['planting_date'] = st.session_state.get('planting_date', date.today())
            
            # Ensure complex soil layers are passed
            if st.session_state.get('soil_layers') is not None:
                config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
            else:
                config['soil_layers'] = []
            
            st.session_state['sim_results'] = engine.run_simulation(config)
            if st.session_state['sim_results'] is None:
                st.error("Simulation failed. Check geometry.")
                return
            st.rerun()

    res = st.session_state['sim_results']
    history = res['history']
    
    # --- 2. TIMELINE CONTROLLER ---
    st.subheader("📅 Seasonal Timeline")
    dates = [pd.to_datetime(h['Date']).date() for h in history]
    
    today = date.today()
    default_date = max(dates) if today > max(dates) else today
    if default_date < min(dates): default_date = min(dates)
    
    selected_date = st.slider("View State At:", min_value=dates[0], max_value=dates[-1], value=default_date, format="DD MMM")
    
    idx = next(i for i, d in enumerate(dates) if d >= selected_date)
    day_data = history[idx]
    
    # --- 3. METRICS ---
    # Get Area (default to 1.0 if missing)
    area = st.session_state.get('area_ha', 1.0)
    
    # Calculate Total Production
    yield_tha = day_data['Yield']
    total_tonnes = yield_tha * area

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Simulated Date", selected_date.strftime("%Y-%m-%d"))
    c2.metric("Avg Yield Potential", f"{yield_tha:.1f} t/ha", f"{total_tonnes:.1f} tonnes total")
    c3.metric("Infection", f"{day_data['Incidence']*100:.1f}%", delta="Risk" if day_data['Incidence']>0 else "Clean", delta_color="inverse")
    c4.metric("Water Stress", f"{day_data['Avg_Stress']*100:.0f}%")
    
    st.divider()
    
    # --- 4. SPATIAL MAP ---
    st.subheader("🗺️ Spatial Epidemiology & Yield")
    
    col_controls, col_map = st.columns([1, 3])
    
    with col_controls:
        map_mode = st.radio("Select Layer:", ["Disease Severity", "Yield Potential"], horizontal=False)
        st.caption(f"Visualizing **{map_mode}** on **{selected_date}**.")
        st.info("Red zones indicate high stress or infection. Green zones indicate healthy biomass.")
        
    with col_map:
        fig, ax = plt.subplots(figsize=(10, 7))
        triang_source = res['triangulation']
        
        x_plot = triang_source.y  # Longitude
        y_plot = triang_source.x  # Latitude
        triang_plot = Triangulation(x_plot, y_plot, triang_source.triangles)
        
        if map_mode == "Disease Severity":
            vals = day_data['Grid_Incidence']
            cmap = 'Reds'
            title = "Infection (0=Healthy, 1=Severe)"
            vmax = 1.0
        else:
            vals = day_data['Grid_Yield']
            cmap = 'Greens'
            title = f"Yield Accumulation (t/ha)"
            max_yield_hist = np.max([h['Grid_Yield'].max() for h in history])
            vmax = max(1.0, max_yield_hist)
        
        trip = ax.tripcolor(triang_plot, vals, cmap=cmap, shading='gouraud', vmin=0, vmax=vmax)
        cbar = fig.colorbar(trip, ax=ax, fraction=0.03, pad=0.04)
        cbar.set_label(title)
        
        if 'field_poly' in res:
            poly = res['field_poly']
            poly_plot = np.vstack([poly, poly[0]])
            ax.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5, label="Boundary")
        
        spots = st.session_state.get('disease_spots', [])
        if spots:
            sdf = pd.DataFrame(spots)
            ax.scatter(sdf['lon'], sdf['lat'], c='blue', marker='x', s=80, label="Observed Foci", zorder=5)
            ax.legend(loc='upper right', fontsize='small')
            
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        ax.axis('equal')
        ax.grid(True, linestyle='--', alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)
    
    st.divider()
    
    # --- 5. DAILY DYNAMICS ---
    st.subheader("📈 Daily Dynamics")
    df_plot = pd.DataFrame(history)
    df_plot['Date'] = pd.to_datetime(df_plot['Date'])
    
    rule = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(selected_date)]})).mark_rule(color='black').encode(x='Date:T')
    
    tabs = st.tabs(["LAI & Biomass", "Soil Nutrients", "Disease Incidence", "Nutrient Stress", "🛰️ Reality Check (NDVI)"])
    
    # --- TAB 1: LAI & BIOMASS ---
    with tabs[0]:
        df_bio = df_plot[['Date', 'LAI', 'Biomass']].copy()
        base = alt.Chart(df_bio).encode(x='Date:T')
        
        line_lai = base.transform_calculate(Metric="'Leaf Area Index'").mark_line().encode(
            y=alt.Y('LAI:Q', title='LAI', axis=alt.Axis(titleColor='#2ecc71')),
            color=alt.Color('Metric:N', scale=alt.Scale(domain=['Leaf Area Index', 'Biomass'], range=['#2ecc71', '#8B4513']), legend=alt.Legend(title="Metrics"))
        )
        line_bio = base.transform_calculate(Metric="'Biomass'").mark_line().encode(
            y=alt.Y('Biomass:Q', title='Biomass (t/ha)', axis=alt.Axis(titleColor='#8B4513')),
            color=alt.Color('Metric:N')
        )
        c = alt.layer(line_lai, line_bio).resolve_scale(y='independent').properties(height=350)
        st.altair_chart((c + rule).interactive(), use_container_width=True)
        
    # --- TAB 2: SOIL WATER & NUTRIENTS (FIXED) ---
    with tabs[1]:
        # Using N_kg, P_kg, K_kg instead of Nmin
        df_soil = df_plot[['Date', 'SWC', 'N_kg', 'P_kg', 'K_kg']].copy()
        
        # Melt for multi-line chart
        df_soil_melt = df_soil.melt('Date', var_name='Parameter', value_name='Value')
        
        base = alt.Chart(df_soil_melt).encode(x='Date:T')
        
        lines = base.mark_line().encode(
            y=alt.Y('Value:Q', title='Amount (mm or kg/ha)'),
            color=alt.Color('Parameter:N', 
                            scale=alt.Scale(
                                domain=['SWC', 'N_kg', 'P_kg', 'K_kg'], 
                                range=['#3498db', '#e67e22', '#9b59b6', '#f1c40f']
                            ),
                            legend=alt.Legend(title="Soil Status")
            ),
            tooltip=['Date', 'Parameter', 'Value']
        )
        
        st.altair_chart((lines + rule).interactive(), use_container_width=True)

    # --- TAB 3: DISEASE ---
    with tabs[2]:
        base = alt.Chart(df_plot).encode(x='Date:T')
        
        area_inc = base.transform_calculate(Metric="'Infection Severity'").mark_area(opacity=0.4).encode(
            y=alt.Y('Incidence:Q', title='Incidence (0-1)', axis=alt.Axis(titleColor='red')),
            color=alt.Color('Metric:N', scale=alt.Scale(domain=['Infection Severity', 'Env. Risk Score'], range=['red', 'purple']), legend=alt.Legend(title="Epidemiology"))
        )
        line_env = base.transform_calculate(Metric="'Env. Risk Score'").mark_line(strokeDash=[5,5]).encode(
            y=alt.Y('Env_Favorability:Q', title='Env. Risk (0-1)', axis=alt.Axis(titleColor='purple')),
            color=alt.Color('Metric:N')
        )
        c = alt.layer(area_inc, line_env).resolve_scale(y='independent').properties(height=350)
        st.altair_chart((c + rule).interactive(), use_container_width=True)

    # --- TAB 4: DAILY STRESS (UPDATED NPK) ---
    with tabs[3]:
        # Melt water plus N, P, K stresses
        df_stress = df_plot.melt(
            'Date', 
            value_vars=['Avg_Stress', 'Avg_N_Stress', 'Avg_P_Stress', 'Avg_K_Stress'], 
            var_name='Stress Type', 
            value_name='Index'
        )
        
        df_stress['Stress Type'] = df_stress['Stress Type'].replace({
            'Avg_Stress': 'Water', 
            'Avg_N_Stress': 'Nitrogen (N)',
            'Avg_P_Stress': 'Phosphorus (P)',
            'Avg_K_Stress': 'Potassium (K)'
        })
        
        c = alt.Chart(df_stress).mark_area(opacity=0.5).encode(
            x='Date:T',
            y=alt.Y('Index:Q', title='Stress Index (0=None, 1=Severe)'),
            color=alt.Color('Stress Type:N', scale=alt.Scale(scheme='category10')),
            tooltip=['Date', 'Stress Type', 'Index']
        ).properties(height=350)
        
        st.altair_chart((c + rule).interactive(), use_container_width=True)

    # --- TAB 5: REALITY CHECK (NDVI) ---
    with tabs[4]:
        st.caption("Validating Digital Twin against Sentinel-2 Satellite observations (Cloud-free days only).")
        
        if 'ndvi_data' not in st.session_state:
            with st.spinner("Fetching Sentinel-2 data from AlphaEarth..."):
                start = df_plot['Date'].min().date()
                end = df_plot['Date'].max().date()
                coords = st.session_state['field_coords']
                if end > date.today(): end = date.today()
                st.session_state['ndvi_data'] = fetch_sentinel_ndvi(coords, start, end)
        
        df_ndvi = st.session_state.get('ndvi_data')
        
        if df_ndvi is not None and not df_ndvi.empty:
            base_model = alt.Chart(df_plot).encode(x='Date:T')
            line_lai_model = base_model.mark_line(color='green', strokeDash=[5,5]).encode(
                y=alt.Y('LAI:Q', title='Modelled LAI (Greenness)', axis=alt.Axis(titleColor='green'))
            )
            base_sat = alt.Chart(df_ndvi).encode(x='Date:T')
            point_ndvi = base_sat.mark_point(color='blue', filled=True, size=60).encode(
                y=alt.Y('NDVI:Q', title='Satellite NDVI (Observed)', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(titleColor='blue')),
                tooltip=['Date', 'NDVI']
            )
            c_check = alt.layer(line_lai_model, point_ndvi).resolve_scale(y='independent').properties(height=350)
            st.altair_chart(c_check.interactive(), use_container_width=True)
            st.info("Interpretation: The Dotted Green Line is what the math predicts. The Blue Dots are what the satellite sees. If dots are much lower than the line, check for unmodelled stress (pests/disease).")
        else:
            st.warning("No clear satellite imagery found for this period (Cloud cover or date range issue).")
            st.dataframe(df_plot[['Date', 'LAI']].head())

    # --- STRESS SUMMARY ---
    st.subheader("🧭 Stress Summary")
    n_days = len(df_plot)
    w_days = (df_plot['Avg_Stress'] > 0.5).sum()
    n_days_stress = (df_plot['Avg_N_Stress'] > 0.5).sum()
    
    c1, c2 = st.columns(2)
    c1.info(f"**Water Stress:** {w_days} days ({w_days/n_days*100:.1f}%) > 0.5")
    c2.warning(f"**Nitrogen Stress:** {n_days_stress} days ({n_days_stress/n_days*100:.1f}%) > 0.5")
    
    # --- RAW DATA ---
    with st.expander("📋 View Raw Daily Data"):
        st.dataframe(df_plot.drop(columns=['Grid_Incidence', 'Grid_Yield']))
    
    if st.button("🔄 Rerun Simulation"):
        if 'sim_results' in st.session_state: del st.session_state['sim_results']
        if 'ndvi_data' in st.session_state: del st.session_state['ndvi_data']
        st.rerun()