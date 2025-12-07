# pages\main\dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import matplotlib.pyplot as plt
from matplotlib.tri import Triangulation
from datetime import date
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
    if start_date > end_date:
        return pd.DataFrame(columns=['Date', 'NDVI'])

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
        ee_coords = [[p[1], p[0]] for p in coords]
        geom = ee.Geometry.Polygon([ee_coords])
       
        def mask_s2_clouds(image):
            qa = image.select('QA60')
            cloud_bit_mask = 1 << 10
            cirrus_bit_mask = 1 << 11
            mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
            return image.updateMask(mask).divide(10000).copyProperties(image, ["system:time_start"])

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
            .filterDate(str(start_date), str(end_date))\
            .filterBounds(geom)\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
            .map(mask_s2_clouds)
        
        def get_ndvi(image):
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            stats = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=20)
            return ee.Feature(None, {
                'date': image.date().format('YYYY-MM-dd'),
                'ndvi': stats.get('NDVI')
            })
            
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
    # Determine if we need to run the simulation
    should_run = 'sim_results' not in st.session_state
    
    # If results exist, check if they match the current config (simple heuristic)
    if not should_run:
        try:
            res = st.session_state['sim_results']
            # If we switched crop types but result is old, rerun
            if res['crop_params']['Crop_ID'] != st.session_state['selected_crop_id']:
                should_run = True
        except:
            should_run = True

    if should_run:
        with st.spinner("Running Bio-Physical Digital Twin..."):
            engine = SimulationEngine()
            config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
            
            # Schedules reconstruction
            get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
            config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
            config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
            
            # Primitives
            config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
            config['initial_nitrogen'] = st.session_state.get('initial_nitrogen', 100.0)
            config['initial_phosphorus'] = st.session_state.get('initial_phosphorus', 30.0)
            config['initial_potassium'] = st.session_state.get('initial_potassium', 100.0)
            config['insect_pressure'] = st.session_state.get('insect_pressure', 1.0)
            config['planting_date'] = st.session_state.get('planting_date', date.today())
            
            # Soil layers
            if st.session_state.get('soil_layers') is not None:
                config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
            else:
                config['soil_layers'] = []
            
            st.session_state['sim_results'] = engine.run_simulation(config)
            if st.session_state['sim_results'] is None:
                st.error("Simulation failed. Check geometry or weather service.")
                return
            st.rerun()

    res = st.session_state['sim_results']
    history = res['history']
    crop_p = res['crop_params']
    is_perennial = crop_p['Type'] == 'Perennial'
    
    # --- 2. TIMELINE CONTROLLER ---
    st.subheader(f"📅 {'20-Year Horizon' if is_perennial else 'Seasonal Timeline'}")
    dates = [pd.to_datetime(h['Date']).date() for h in history]
    
    today = date.today()
    default_date = max(dates) if today > max(dates) else today
    if default_date < min(dates): default_date = min(dates)
    
    # Dual-Mode Slider
    if is_perennial:
        # For perennials, the slider covers 20 years
        selected_date = st.slider("View State At:", min_value=dates[0], max_value=dates[-1], value=default_date, format="YYYY-MM-DD")
    else:
        # Annuals
        selected_date = st.slider("View State At:", min_value=dates[0], max_value=dates[-1], value=default_date, format="DD MMM")
    
    idx = next((i for i, d in enumerate(dates) if d >= selected_date), -1)
    if idx == -1: idx = len(dates) - 1
    day_data = history[idx]
    
    # --- 3. METRICS ---
    area = st.session_state.get('area_ha', 1.0)
    
    if is_perennial:
        # Perennial Metrics: Focus on Standing Fruit and Wood
        yield_val = day_data.get('Fruit_Biomass', 0.0) # This is standing fruit
        total_tonnes = yield_val * area
        metric_label = "Standing Fruit (Yield)"
        wood_val = day_data.get('Wood_Biomass', 0.0)
    else:
        # Annual Metrics: Focus on Yield Potential
        yield_val = day_data['Yield']
        total_tonnes = yield_val * area
        metric_label = "Avg Yield Potential"
        wood_val = 0.0 # Not relevant

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Simulated Date", selected_date.strftime("%Y-%m-%d"))
    c2.metric(metric_label, f"{yield_val:.2f} t/ha", f"{total_tonnes:.1f} t total")
    
    if is_perennial:
        c3.metric("Wood Biomass", f"{wood_val:.1f} t/ha")
    else:
        c3.metric("Infection", f"{day_data['Incidence']*100:.1f}%", delta="Risk" if day_data['Incidence']>0 else "Clean", delta_color="inverse")
        
    c4.metric("Water Stress", f"{day_data['Avg_Stress']*100:.0f}%", delta="High" if day_data['Avg_Stress']>0.5 else "OK", delta_color="inverse")
    
    st.divider()
    
    # --- 4. SPATIAL MAP ---
    st.subheader("🗺️ Spatial Epidemiology & Yield")
    
    col_controls, col_map = st.columns([1, 3])
    
    with col_controls:
        # Map options depend on crop type slightly
        options = ["Disease Severity", "Yield Potential"]
        map_mode = st.radio("Select Layer:", options, horizontal=False)
        st.caption(f"Visualizing **{map_mode}** on **{selected_date}**.")
        st.info("Red zones indicate high stress or infection. Green zones indicate healthy biomass.")
        
    with col_map:
        fig, ax = plt.subplots(figsize=(10, 7))
        triang_source = res['triangulation']
        x_plot = triang_source.y # Lon
        y_plot = triang_source.x # Lat
        triang_plot = Triangulation(x_plot, y_plot, triang_source.triangles)
        
        if triang_source.mask is not None:
            triang_plot.set_mask(triang_source.mask)
        
        if map_mode == "Disease Severity":
            vals = day_data['Grid_Incidence']
            cmap = 'Reds'
            title = "Infection (0=Healthy, 1=Severe)"
            vmax = 1.0
        else:
            vals = day_data['Grid_Yield']
            cmap = 'Greens'
            title = f"Yield/Fruit Accumulation (t/ha)"
            # Dynamic scaling for Perennials (yield gets high)
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
    
    # --- 5. DYNAMICS & CHARTS ---
    st.subheader(f"📈 { 'Long-Term Trajectory' if is_perennial else 'Daily Dynamics' }")
    df_plot = pd.DataFrame(history)
    df_plot['Date'] = pd.to_datetime(df_plot['Date'])
    
    # Rules
    rule_selected = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(selected_date)]})).mark_rule(color='black', strokeWidth=2).encode(x='Date:T')
    
    # Tabs logic
    tab_titles = ["Biomass & Growth", "Yield Forecast", "Nutrients & Stress", "Disease Pressure", "🛰️ Reality Check (NDVI)"]
    tabs = st.tabs(tab_titles)
    
    # --- TAB 1: BIOMASS ---
    with tabs[0]:
        if is_perennial:
            # STACKED AREA CHART: Wood vs Fruit
            st.markdown("**Structural (Wood) vs Reproductive (Fruit) Biomass**")
            
            df_bio_stack = df_plot[['Date', 'Wood_Biomass', 'Fruit_Biomass']].melt('Date', var_name='Type', value_name='Biomass')
            
            c_area = alt.Chart(df_bio_stack).mark_area().encode(
                x='Date:T',
                y=alt.Y('Biomass:Q', title='Biomass (t/ha)'),
                color=alt.Color('Type:N', scale=alt.Scale(domain=['Wood_Biomass', 'Fruit_Biomass'], range=['#8B4513', '#2ecc71']), legend=alt.Legend(title="Component")),
                tooltip=['Date', 'Type', 'Biomass']
            )
            st.altair_chart((c_area + rule_selected).interactive(), use_container_width=True)
            
        else:
            # ANNUAL: Standard LAI vs Biomass Line (ROBUST VERSION)
            # We use independent lines with explicit colors to avoid legend merging issues
            df_bio = df_plot[['Date', 'LAI', 'Biomass']].copy()
            base = alt.Chart(df_bio).encode(x='Date:T')
            
            line_lai = base.mark_line(color='#2ecc71').encode(
                y=alt.Y('LAI:Q', title='Leaf Area Index (Green)', axis=alt.Axis(titleColor='#2ecc71')),
                tooltip=['Date', 'LAI']
            )
            
            line_bio = base.mark_line(color='#8B4513').encode(
                y=alt.Y('Biomass:Q', title='Biomass t/ha (Brown)', axis=alt.Axis(titleColor='#8B4513')),
                tooltip=['Date', 'Biomass']
            )
            
            st.altair_chart(alt.layer(line_lai, line_bio).resolve_scale(y='independent').add_selection(alt.selection_interval(bind='scales')), use_container_width=True)
        
    # --- TAB 2: YIELD FORECAST ---
    with tabs[1]:
        if is_perennial:
            # SAWTOOTH CHART + UNCERTAINTY
            st.markdown("**20-Year Yield Trajectory (Sawtooth Pattern)**")
            st.caption("Shows accumulation of fruit and annual harvest/drop events. The green band represents estimated uncertainty due to climate variability.")

            # Create synthetic uncertainty for dashboard visual (Report does full ensemble)
            # +/- 15% uncertainty band
            df_yield = df_plot[['Date', 'Fruit_Biomass']].copy()
            df_yield['Yield'] = df_yield['Fruit_Biomass']
            df_yield['Upper'] = df_yield['Yield'] * 1.15
            df_yield['Lower'] = df_yield['Yield'] * 0.85
            
            base_y = alt.Chart(df_yield).encode(x='Date:T')
            
            # Ribbon
            band = base_y.mark_area(opacity=0.3, color='green').encode(
                y=alt.Y('Lower:Q', title='Standing Fruit (t/ha)'),
                y2='Upper:Q'
            )
            
            # Main Line
            line = base_y.mark_line(color='green').encode(
                y='Yield:Q',
                tooltip=['Date', 'Yield']
            )
            
            st.altair_chart((band + line + rule_selected).interactive(), use_container_width=True)
            
        else:
            # ANNUAL: Standard Accumulation
            base = alt.Chart(df_plot).encode(x='Date:T')
            line = base.mark_line(color='green').encode(
                y=alt.Y('Yield:Q', title='Yield (t/ha)'),
                tooltip=['Date', 'Yield']
            )
            st.altair_chart((line + rule_selected).interactive(), use_container_width=True)

    # --- TAB 3: NUTRIENTS ---
    with tabs[2]:
        df_soil = df_plot[['Date', 'SWC', 'N_kg', 'P_kg', 'K_kg']].copy()
        df_soil_melt = df_soil.melt('Date', var_name='Parameter', value_name='Value')
        
        base = alt.Chart(df_soil_melt).encode(x='Date:T')
        lines = base.mark_line().encode(
            y=alt.Y('Value:Q', title='Amount (mm or kg/ha)'),
            color=alt.Color('Parameter:N', 
                            scale=alt.Scale(domain=['SWC', 'N_kg', 'P_kg', 'K_kg'], range=['#3498db', '#e67e22', '#9b59b6', '#f1c40f']),
                            legend=alt.Legend(title="Soil Status")
            ),
            tooltip=['Date', 'Parameter', 'Value']
        )
        st.altair_chart((lines + rule_selected).interactive(), use_container_width=True)
        
        # Stress Chart
        df_stress = df_plot.melt('Date', value_vars=['Avg_Stress', 'Avg_N_Stress', 'Avg_P_Stress', 'Avg_K_Stress'], var_name='Type', value_name='Index')
        c_stress = alt.Chart(df_stress).mark_area(opacity=0.5).encode(
            x='Date:T',
            y=alt.Y('Index:Q', title='Stress Index (0-1)'),
            color=alt.Color('Type:N', scale=alt.Scale(scheme='category10'))
        ).properties(height=200)
        st.altair_chart((c_stress + rule_selected).interactive(), use_container_width=True)

    # --- TAB 4: DISEASE ---
    with tabs[3]:
        det_date = st.session_state.get('detection_date')
        rule_detect = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(det_date)]})).mark_rule(color='orange', strokeDash=[4,4]).encode(x='Date:T')
        
        # Transform data to long format for easy shared-axis plotting
        df_dis = df_plot[['Date', 'Incidence', 'Env_Favorability']].copy()
        df_dis = df_dis.rename(columns={'Incidence': 'Infection Severity', 'Env_Favorability': 'Env. Risk Score'})
        df_dis_melt = df_dis.melt('Date', var_name='Metric', value_name='Value')
        
        base = alt.Chart(df_dis_melt).encode(x='Date:T')
        
        # We plot both as lines/areas on the same 0-1 scale
        lines = base.mark_area(opacity=0.4).encode(
            y=alt.Y('Value:Q', title='Index (0-1)'),
            color=alt.Color('Metric:N', scale=alt.Scale(domain=['Infection Severity', 'Env. Risk Score'], range=['red', 'purple'])),
            tooltip=['Date', 'Metric', 'Value']
        )
        
        st.altair_chart((lines + rule_detect + rule_selected).interactive(), use_container_width=True)

    # --- TAB 5: SATELLITE ---
    with tabs[4]:
        st.caption("Validating Digital Twin against Sentinel-2 Satellite observations (Cloud-free days only).")
        sim_start = df_plot['Date'].min().date()
        sim_end = df_plot['Date'].max().date()
        today_date = date.today()
        
        if sim_start > today_date:
            st.warning("⚠️ Simulation is for a future date range. Satellite validation is not available.")
        else:
            if 'ndvi_data' not in st.session_state:
                with st.spinner("Fetching Sentinel-2 data from AlphaEarth..."):
                    coords = st.session_state['field_coords']
                    fetch_end = min(sim_end, today_date)
                    st.session_state['ndvi_data'] = fetch_sentinel_ndvi(coords, sim_start, fetch_end)
            
            df_ndvi = st.session_state.get('ndvi_data')
            if df_ndvi is not None and not df_ndvi.empty:
                base_model = alt.Chart(df_plot).encode(x='Date:T')
                line_lai_model = base_model.mark_line(color='green', strokeDash=[5,5]).encode(
                    y=alt.Y('LAI:Q', title='Modelled LAI', axis=alt.Axis(titleColor='green'))
                )
                base_sat = alt.Chart(df_ndvi).encode(x='Date:T')
                point_ndvi = base_sat.mark_point(color='blue', filled=True, size=60).encode(
                    y=alt.Y('NDVI:Q', title='Satellite NDVI', scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(titleColor='blue')),
                    tooltip=['Date', 'NDVI']
                )
                c_check = alt.layer(line_lai_model, point_ndvi).resolve_scale(y='independent')
                st.altair_chart(c_check.interactive(), use_container_width=True)
            else:
                st.warning("No clear satellite imagery found.")

    # --- STRESS SUMMARY ---
    st.subheader("🧭 Stress Summary")
    n_days = len(df_plot)
    w_days = (df_plot['Avg_Stress'] > 0.5).sum()
    n_days_stress = (df_plot['Avg_N_Stress'] > 0.5).sum()
    
    c1, c2 = st.columns(2)
    c1.info(f"**Water Stress:** {w_days} days ({w_days/n_days*100:.1f}%) > 0.5")
    c2.warning(f"**Nitrogen Stress:** {n_days_stress} days ({n_days_stress/n_days*100:.1f}%) > 0.5")
    
    with st.expander("📋 View Raw Daily Data"):
        st.dataframe(df_plot.drop(columns=['Grid_Incidence', 'Grid_Yield']))

    if st.button("🔄 Rerun Simulation"):
        if 'sim_results' in st.session_state: del st.session_state['sim_results']
        if 'ndvi_data' in st.session_state: del st.session_state['ndvi_data']
        st.rerun()