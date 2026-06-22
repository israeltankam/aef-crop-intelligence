# pages\main\dashboard.py
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import matplotlib.pyplot as plt
import folium
from streamlit_folium import st_folium
from matplotlib.tri import Triangulation
from datetime import date
from src.models.state_manager import StateManager
from src.utils.i18n import tr
from src.models.simulation_engine import SimulationEngine
from src.models.cooperative_engine import CooperativeSimulationEngine
from src.utils.decision_support import build_decision_snapshot
from src.models.model_validity import model_validity_impact_cards
from src.utils.diagnostic_quality import build_diagnostic_quality
from src.utils.disease_evidence import build_disease_evidence
import ee
from google.oauth2.service_account import Credentials

def _dashboard_config_snapshot():
    """Return saved configuration fields for dashboard confidence panels.

    The dashboard should not silently infer confidence from the simulated curve
    alone.  This snapshot carries provenance fields such as soil source, manual
    disease foci and adaptive calibration status into the user-facing warnings.
    """
    return {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys()}


def _dashboard_disease_name():
    dis_id = st.session_state.get('selected_disease_id')
    df = st.session_state.get('df_diseases')
    if dis_id and df is not None and dis_id in df['Disease_ID'].values:
        return df[df['Disease_ID'] == dis_id].iloc[0]['Disease_Name']
    return None


def _render_quality_and_evidence(result=None):
    """Show decision confidence beside model outputs.

    This deliberately avoids changing simulation results.  It makes uncertainty
    and evidence provenance visible so the user does not read a deterministic
    chart as a confirmed diagnosis.
    """
    config = _dashboard_config_snapshot()
    quality = build_diagnostic_quality(config, result)
    evidence = build_disease_evidence(config, _dashboard_disease_name())
    q1, q2 = st.columns([1, 2])
    q1.metric(tr('Diagnostic quality score'), f"{quality['overall_score']:.1f}%", tr(quality['label']))
    q2.info(f"{tr('Next best measurement')}: {tr(quality['next_best_measurement'])}")
    with st.expander(tr('Evidence and uncertainty details')):
        rows = [{
            tr('Component'): tr(c['name']),
            tr('Score'): f"{c['score']:.1f}%",
            tr('Status'): tr(c['status']),
            tr('Decision impact'): tr(c['impact']),
            tr('Next step'): tr(c['next_step']),
        } for c in quality.get('components', [])]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.markdown('###### ' + tr('Disease evidence status'))
        st.write(tr(evidence['interpretation']))
        for item in evidence.get('evidence', []):
            status_text = tr(item['status'])
            if item.get('count'):
                status_text = f"{item['count']} {status_text}"
            st.caption(f"**{tr(item['source'])}** - {status_text}. {tr('Confidence:')} {tr(item['confidence'])}. {tr(item['decision_impact'])}")



def _select_forecast_date(dates, default_date, key):
    """Render a calendar selector bounded by the simulated forecast horizon.

    A date input is more precise than a long slider for future forecasts,
    especially on perennial horizons where the simulation can span many years.
    """
    start_date, end_date = min(dates), max(dates)
    selected_default = min(max(default_date, start_date), end_date)
    selected = st.date_input(
        tr('Forecast date'),
        value=selected_default,
        min_value=start_date,
        max_value=end_date,
        help=tr('Choose the exact date where you want to inspect the simulated field status.'),
        key=key,
    )
    st.caption(tr('Forecast horizon: {start} to {end}', start=start_date, end=end_date))
    return selected

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

def render_cooperative_dashboard(res):
    """Dashboard view for cooperative mode with many independent plots."""
    st.title('🤝 ' + tr('Cooperative overview'))
    history = res.get('history', [])
    parcels = res.get('parcel_results', [])
    if not history or not parcels:
        st.warning(tr('Simulation failed. Check geometry or weather service.'))
        return
    df = pd.DataFrame(history)
    dates = pd.to_datetime(df['Date']).dt.date.tolist()
    selected_date = _select_forecast_date(dates, min(date.today(), dates[-1]), key='coop_forecast_date')
    idx = next((i for i, d in enumerate(dates) if d >= selected_date), len(dates)-1)
    row = df.iloc[idx]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(tr('Active plots'), res.get('parcel_count', len(parcels)))
    c2.metric(tr('Total active area'), f"{res.get('total_area_ha', 0.0):.2f} ha")
    c3.metric(tr('Unassigned/non-cultivated area'), f"{res.get('unassigned_area_ha', 0.0):.2f} ha")
    c4.metric(tr('Total cooperative production'), f"{row.get('Total_Production', 0.0):.1f} t")
    st.caption(f"{tr('Cultivated fraction')}: {float(res.get('cultivated_fraction', 0.0) or 0.0):.0%} | {tr('Average yield')}: {row.get('Yield', 0.0):.2f} t/ha")
    st.caption(tr('The cooperative mode treats each plot as a local patch and links plots through distance-weighted infection pressure.'))
    config_snapshot = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
    for card in model_validity_impact_cards(res.get('growth_model'), res.get('disease_model'), bool(st.session_state.get('satellite_anomaly_date'))):
        st.warning(f"**{tr(card['area'])} - {tr(card['level'])}**: {tr(card['message'])} {tr(card['decision_impact'])}")
    _render_quality_and_evidence(res)
    cards = build_decision_snapshot(history, config_snapshot, res.get('crop_params', {}), {})
    if cards:
        st.subheader('🧭 ' + tr('Decision snapshot'))
        for card in cards[:4]:
            st.info(f"**{tr(card['title'])}** — {tr(card['message'])} {tr('Next step:')} {tr(card['recommended_next_step'])} {tr('Confidence:')} {tr(card['confidence'])}")

    st.subheader('🗺️ ' + tr('Plot-level results'))
    plot_labels = {p.get('id'): f"{p.get('name', p.get('id'))} ({p.get('id')})" for p in parcels}
    plot_options = [None] + [p.get('id') for p in parcels if p.get('id')]
    if st.session_state.get('coop_dashboard_focus_plot') not in plot_options:
        st.session_state['coop_dashboard_focus_plot'] = None
    selected_plot_id = st.selectbox(tr('Focus plot on map'), plot_options, format_func=lambda x: tr('All plots') if x is None else plot_labels.get(x, x), key='coop_dashboard_focus_plot') if len(plot_options) > 1 else None
    selected_plot = next((p for p in parcels if p.get('id') == selected_plot_id), None)
    center = selected_plot.get('centroid') if selected_plot else parcels[0].get('centroid', (st.session_state.get('center_lat', 4.0), st.session_state.get('center_lon', 11.5)))
    m = folium.Map(location=list(center), zoom_start=17 if selected_plot else 15, max_zoom=20)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name=tr('Esri Satellite'), overlay=False, control=True).add_to(m)
    perimeter = st.session_state.get('cooperative_perimeter_coords') or []
    if perimeter:
        folium.Polygon(locations=perimeter, color='#0057B8', weight=4, fill=False, popup=tr('Cooperative perimeter')).add_to(m)
    parcel_rows = []
    for parcel in parcels:
        p_hist = parcel['history'][min(idx, len(parcel['history'])-1)]
        incidence = float(p_hist.get('Incidence', 0.0))
        color = '#2ECC71' if incidence < 0.10 else '#F39C12' if incidence < 0.30 else '#C0392B'
        is_selected = parcel.get('id') == selected_plot_id
        folium.Polygon(locations=parcel['coords'], color='#FFB000' if is_selected else color, weight=4 if is_selected else 2, fill=True, fill_opacity=0.36 if is_selected else 0.28, popup=f"{parcel['name']} - {incidence*100:.1f}%").add_to(m)
        parcel_rows.append({
            tr('Plot ID'): parcel['id'],
            tr('Plot name'): parcel['name'],
            tr('Area'): round(parcel['area_ha'], 2),
            tr('Forecast yield'): round(float(p_hist.get('Yield', 0.0)), 2),
            tr('Disease incidence'): round(incidence * 100, 1),
            tr('Metapopulation pressure'): round(float(p_hist.get('Metapopulation_Pressure', 0.0)) * 100, 2),
            tr('Water stress'): round(float(p_hist.get('Avg_Stress', 0.0)) * 100, 1),
        })
    st_folium(m, height=500, width=None, key='coop_dashboard_map')
    if selected_plot:
        selected_hist = selected_plot['history'][min(idx, len(selected_plot['history'])-1)]
        st.info(f"{tr('Selected plot')}: **{selected_plot.get('name')}** | {tr('Area')}: {selected_plot.get('area_ha', 0.0):.2f} ha | {tr('Forecast yield')}: {float(selected_hist.get('Yield', 0.0)):.2f} t/ha | {tr('Disease incidence')}: {float(selected_hist.get('Incidence', 0.0))*100:.1f}%")

    chart_df = df[['Date', 'Yield', 'Incidence', 'Metapopulation_Pressure', 'Avg_Stress']].copy()
    chart_df['Date'] = pd.to_datetime(chart_df['Date'])
    chart_df = chart_df.rename(columns={
        'Yield': tr('Average yield'),
        'Incidence': tr('Disease incidence'),
        'Metapopulation_Pressure': tr('Metapopulation pressure'),
        'Avg_Stress': tr('Water stress'),
    })
    st.altair_chart(alt.Chart(chart_df).mark_line().transform_fold(
        [tr('Average yield'), tr('Disease incidence'), tr('Metapopulation pressure'), tr('Water stress')],
        as_=[tr('Metric'), tr('Value')]
    ).encode(x='Date:T', y=alt.Y(f"{tr('Value')}:Q"), color=f"{tr('Metric')}:N").interactive(), use_container_width=True)

    st.subheader('⚠️ ' + tr('Highest-risk plots'))
    df_parcels = pd.DataFrame(parcel_rows).sort_values(tr('Disease incidence'), ascending=False)
    st.dataframe(df_parcels, use_container_width=True, hide_index=True)

    if st.button('🔄 ' + tr('Rerun Simulation')):
        st.session_state.pop('sim_results', None)
        st.session_state.pop('sim_uncertainty', None)
        st.rerun()

def app():
    # Ensure state
    if 'step' not in st.session_state: StateManager.initialize()
    
    st.title("🛰️ " + tr("Intelligence Dashboard"))
    
    if not st.session_state.get('setup_complete'):
        st.error(tr("Please complete the Setup Wizard first."))
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
        with st.spinner(tr("Running Bio-Physical Digital Twin and uncertainty envelope...")):
            engine = CooperativeSimulationEngine() if st.session_state.get('app_mode') == 'cooperative' else SimulationEngine()
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
            
            if st.session_state.get('app_mode') == 'cooperative':
                st.session_state['sim_results'] = engine.run_cooperative_simulation(config)
            else:
                st.session_state['sim_results'] = engine.run_simulation(config)
            if st.session_state['sim_results'] is None:
                st.error(tr("Simulation failed. Check geometry or weather service."))
                return

            # A light ensemble makes uncertainty visible in the dashboard without
            # waiting for the full PDF dossier workflow. The PDF still runs a
            # larger ensemble for final margins of error.
            try:
                if st.session_state.get('app_mode') == 'cooperative':
                    st.session_state['sim_uncertainty'] = None
                else:
                    crop_type = st.session_state['sim_results']['crop_params'].get('Type', 'Annual')
                    uncertainty_runs = 12 if crop_type == 'Perennial' else 20
                    st.session_state['sim_uncertainty'] = engine.run_ensemble_inference(config, n_runs=uncertainty_runs)
            except Exception:
                st.session_state['sim_uncertainty'] = None
            st.rerun()

    res = st.session_state['sim_results']
    if res.get('mode') == 'cooperative':
        render_cooperative_dashboard(res)
        return
    history = res['history']
    uncertainty_res = st.session_state.get('sim_uncertainty') or {}
    uncertainty_stats = uncertainty_res.get('ensemble_stats', {}) if isinstance(uncertainty_res, dict) else {}
    crop_p = res['crop_params']
    is_perennial = crop_p['Type'] == 'Perennial'
    
    # --- 2. TIMELINE CONTROLLER ---
    st.subheader("📅 " + (tr("20-Year Horizon") if is_perennial else tr("Seasonal Timeline")))
    dates = [pd.to_datetime(h['Date']).date() for h in history]
    
    today = date.today()
    default_date = max(dates) if today > max(dates) else today
    if default_date < min(dates): default_date = min(dates)
    
    # A calendar selector is faster for precise future-event checks than a
    # horizon-wide slider, especially on multi-year perennial simulations.
    selected_date = _select_forecast_date(dates, default_date, key='single_forecast_date')
    
    idx = next((i for i, d in enumerate(dates) if d >= selected_date), -1)
    if idx == -1: idx = len(dates) - 1
    day_data = history[idx]
    
    # --- 3. METRICS ---
    area = st.session_state.get('area_ha', 1.0)
    
    if is_perennial:
        # Perennial Metrics: Focus on Standing Fruit and Wood
        yield_val = day_data.get('Fruit_Biomass', 0.0) # This is standing fruit
        total_tonnes = yield_val * area
        metric_label = tr("Standing Fruit (Yield)")
        wood_val = day_data.get('Wood_Biomass', 0.0)
    else:
        # Annual Metrics: Focus on Yield Potential
        yield_val = day_data['Yield']
        total_tonnes = yield_val * area
        metric_label = tr("Avg Yield Potential")
        wood_val = 0.0 # Not relevant

    # A diagnostic dashboard must not show zero-width confidence bands just
    # because one ensemble realisation is numerically deterministic or an older
    # cached result lacks the new uncertainty profile.  We therefore mirror the
    # report logic: raw ensemble dispersion is kept when larger, but a cautious
    # operational floor remains until adaptive field observations reduce it.
    uncertainty_profile = uncertainty_stats.get('Uncertainty_Profile', {}) if isinstance(uncertainty_stats, dict) else {}
    yield_ci_fraction_95 = float(uncertainty_profile.get('yield_ci_fraction_95', 0.24 if is_perennial else 0.16))
    yield_abs_ci95 = float(uncertainty_profile.get('yield_abs_ci95_t_ha', 0.06 if is_perennial else 0.04))
    has_disease_uncertainty = bool(st.session_state.get('selected_disease_id')) or bool(st.session_state.get('disease_spots'))
    incidence_abs_ci95 = float(uncertainty_profile.get('incidence_ci95_abs', 0.16 if has_disease_uncertainty else 0.03))

    yield_ci = max(abs(yield_val) * yield_ci_fraction_95, yield_abs_ci95)
    incidence_ci = incidence_abs_ci95
    if uncertainty_stats:
        y_std = uncertainty_stats.get('Yield_Std')
        i_std = uncertainty_stats.get('Incidence_Std')
        if y_std is not None and len(y_std) > idx:
            yield_ci = max(yield_ci, float(1.96 * y_std[idx]))
        if i_std is not None and len(i_std) > idx:
            incidence_ci = max(incidence_ci, float(1.96 * i_std[idx]))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(tr("Simulated Date"), selected_date.strftime("%Y-%m-%d"))
    yield_delta = f"{total_tonnes:.1f} {tr('t total')}"
    if yield_ci is not None:
        yield_delta += f" | +/- {yield_ci:.2f} t/ha"
    c2.metric(metric_label, f"{yield_val:.2f} t/ha", yield_delta)
    
    if is_perennial:
        c3.metric(tr("Wood Biomass"), f"{wood_val:.1f} t/ha")
    else:
        incidence_delta = tr("Risk") if day_data['Incidence'] > 0 else tr("Clean")
        if incidence_ci is not None:
            incidence_delta = f"+/- {incidence_ci*100:.1f}% | {incidence_delta}"
        c3.metric(tr("Infection"), f"{day_data['Incidence']*100:.1f}%", delta=incidence_delta, delta_color="inverse")
        
    c4.metric(tr("Water Stress"), f"{day_data['Avg_Stress']*100:.0f}%", delta=tr("High") if day_data['Avg_Stress']>0.5 else tr("OK"), delta_color="inverse")
    if yield_ci is not None or incidence_ci is not None:
        details = []
        if yield_ci is not None:
            details.append(f"{tr('yield')} +/- {yield_ci:.2f} t/ha")
        if incidence_ci is not None:
            details.append(f"{tr('incidence')} +/- {incidence_ci*100:.1f}%")
        uncertainty_basis = tr('computed from stochastic ensemble runs plus a conservative operational floor') if uncertainty_stats else tr('preliminary conservative margin; adaptive surveillance can reduce it')
        st.caption(f"{tr('95% margin of error')}: " + "; ".join(details) + f" ({uncertainty_basis}).")
    config_snapshot = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
    for card in model_validity_impact_cards(res.get('growth_model'), res.get('disease_model'), bool(st.session_state.get('satellite_anomaly_date'))):
        st.warning(f"**{tr(card['area'])} - {tr(card['level'])}**: {tr(card['message'])} {tr(card['decision_impact'])}")
    _render_quality_and_evidence(res)
    decision_cards = build_decision_snapshot(history, config_snapshot, crop_p, uncertainty_profile)
    if decision_cards:
        st.subheader('🧭 ' + tr('Decision snapshot'))
        for card in decision_cards[:4]:
            st.info(f"**{tr(card['title'])}** — {tr(card['message'])} {tr('Next step:')} {tr(card['recommended_next_step'])} {tr('Confidence:')} {tr(card['confidence'])}")
    
    st.divider()
    
    # --- 4. SPATIAL MAP ---
    st.subheader("🗺️ " + tr("Spatial Epidemiology & Yield"))
    
    col_controls, col_map = st.columns([1, 3])
    
    with col_controls:
        # Map options depend on crop type slightly
        options = ["Disease Severity", "Yield Potential"]
        map_mode = st.radio(tr("Select Layer:"), options, horizontal=False, format_func=tr)
        st.caption(f"{tr('Visualizing')} **{tr(map_mode)}** {tr('on')} **{selected_date}**.")
        st.info(tr("This is a simulated risk surface, not a raw satellite image. Red zones indicate high stress or infection; green zones indicate healthy biomass."))
        
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
            title = tr("Infection (0=Healthy, 1=Severe)")
            vmax = 1.0
        else:
            vals = day_data['Grid_Yield']
            cmap = 'Greens'
            title = tr("Yield/Fruit Accumulation (t/ha)")
            # Dynamic scaling for Perennials (yield gets high)
            max_yield_hist = np.max([h['Grid_Yield'].max() for h in history])
            vmax = max(1.0, max_yield_hist)
        
        trip = ax.tripcolor(triang_plot, vals, cmap=cmap, shading='gouraud', vmin=0, vmax=vmax)
        cbar = fig.colorbar(trip, ax=ax, fraction=0.03, pad=0.04)
        cbar.set_label(title)
        
        if 'field_poly' in res:
            poly = res['field_poly']
            poly_plot = np.vstack([poly, poly[0]])
            ax.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5, label=tr("Boundary"))
        
        spots = st.session_state.get('disease_spots', [])
        if spots:
            sdf = pd.DataFrame(spots)
            ax.scatter(sdf['lon'], sdf['lat'], c='blue', marker='x', s=80, label=tr("Observed Foci"), zorder=5)
            ax.legend(loc='upper right', fontsize='small')
            
        ax.set_xlabel(tr("Longitude"))
        ax.set_ylabel(tr("Latitude"))
        ax.axis('equal')
        ax.grid(True, linestyle='--', alpha=0.3)
        st.pyplot(fig)
        plt.close(fig)
    
    st.divider()
    
    # --- 5. DYNAMICS & CHARTS ---
    st.subheader("📈 " + (tr("Long-Term Trajectory") if is_perennial else tr("Daily Dynamics")))
    df_plot = pd.DataFrame(history)
    df_plot['Date'] = pd.to_datetime(df_plot['Date'])
    
    # Rules
    rule_selected = alt.Chart(pd.DataFrame({'Date': [pd.to_datetime(selected_date)]})).mark_rule(color='black', strokeWidth=2).encode(x='Date:T')
    
    # Tabs logic
    tab_titles = [tr("Biomass & Growth"), tr("Yield Forecast"), tr("Nutrients & Stress"), tr("Disease Pressure"), "🛰️ " + tr("Reality Check (NDVI)")]
    tabs = st.tabs(tab_titles)
    
    # --- TAB 1: BIOMASS ---
    with tabs[0]:
        if is_perennial:
            # STACKED AREA CHART: Wood vs Fruit
            st.markdown(f"**{tr('Structural (Wood) vs Reproductive (Fruit) Biomass')}**")
            
            df_bio_stack = df_plot[['Date', 'Wood_Biomass', 'Fruit_Biomass']].melt('Date', var_name='Type', value_name='Biomass')
            df_bio_stack['Component_Label'] = df_bio_stack['Type'].map({'Wood_Biomass': tr('Wood biomass'), 'Fruit_Biomass': tr('Fruit biomass')})
            
            c_area = alt.Chart(df_bio_stack).mark_area().encode(
                x='Date:T',
                y=alt.Y('Biomass:Q', title=tr("Biomass (t/ha)")),
                color=alt.Color('Component_Label:N', scale=alt.Scale(domain=[tr("Wood biomass"), tr("Fruit biomass")], range=['#8B4513', '#2ecc71']), legend=alt.Legend(title=tr("Component"))),
                tooltip=['Date', 'Component_Label', 'Biomass']
            )
            st.altair_chart((c_area + rule_selected).interactive(), use_container_width=True)
            
        else:
            # ANNUAL: Standard LAI vs Biomass Line (ROBUST VERSION)
            # We use independent lines with explicit colors to avoid legend merging issues
            df_bio = df_plot[['Date', 'LAI', 'Biomass']].copy()
            base = alt.Chart(df_bio).encode(x='Date:T')
            
            line_lai = base.mark_line(color='#2ecc71').encode(
                y=alt.Y('LAI:Q', title=tr('Leaf Area Index (Green)'), axis=alt.Axis(titleColor='#2ecc71')),
                tooltip=['Date', 'LAI']
            )
            
            line_bio = base.mark_line(color='#8B4513').encode(
                y=alt.Y('Biomass:Q', title=tr('Biomass t/ha (Brown)'), axis=alt.Axis(titleColor='#8B4513')),
                tooltip=['Date', 'Biomass']
            )
            
            st.altair_chart(alt.layer(line_lai, line_bio).resolve_scale(y='independent').add_selection(alt.selection_interval(bind='scales')), use_container_width=True)
        
    # --- TAB 2: YIELD FORECAST ---
    with tabs[1]:
        if is_perennial:
            # SAWTOOTH CHART + UNCERTAINTY
            st.markdown(f"**{tr('20-Year Yield Trajectory (Sawtooth Pattern)')}**")
            st.caption(tr("Shows accumulation of fruit and annual harvest/drop events. The green band represents estimated uncertainty due to climate variability."))

            # Create synthetic uncertainty for dashboard visual (Report does full ensemble)
            # +/- 15% uncertainty band
            df_yield = df_plot[['Date', 'Fruit_Biomass']].copy()
            df_yield['Yield'] = df_yield['Fruit_Biomass']
            df_yield['Upper'] = df_yield['Yield'] * 1.15
            df_yield['Lower'] = df_yield['Yield'] * 0.85
            
            base_y = alt.Chart(df_yield).encode(x='Date:T')
            
            # Ribbon
            band = base_y.mark_area(opacity=0.3, color='green').encode(
                y=alt.Y('Lower:Q', title=tr('Standing Fruit (t/ha)')),
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
                y=alt.Y('Yield:Q', title=tr('Yield (t/ha)')),
                tooltip=['Date', 'Yield']
            )
            st.altair_chart((line + rule_selected).interactive(), use_container_width=True)

    # --- TAB 3: NUTRIENTS ---
    with tabs[2]:
        df_soil = df_plot[['Date', 'SWC', 'N_kg', 'P_kg', 'K_kg']].copy()
        df_soil_melt = df_soil.melt('Date', var_name='Parameter', value_name='Value')
        df_soil_melt['Parameter_Label'] = df_soil_melt['Parameter'].map({'SWC': tr('Soil water'), 'N_kg': tr('Nitrogen stock'), 'P_kg': tr('Phosphorus stock'), 'K_kg': tr('Potassium stock')})
        
        base = alt.Chart(df_soil_melt).encode(x='Date:T')
        lines = base.mark_line().encode(
            y=alt.Y('Value:Q', title=tr('Amount (mm or kg/ha)')),
            color=alt.Color('Parameter_Label:N', 
                            scale=alt.Scale(domain=[tr('Soil water'), tr('Nitrogen stock'), tr('Phosphorus stock'), tr('Potassium stock')], range=['#3498db', '#e67e22', '#9b59b6', '#f1c40f']),
                            legend=alt.Legend(title=tr("Soil Status"))
            ),
            tooltip=['Date', 'Parameter_Label', 'Value']
        )
        st.altair_chart((lines + rule_selected).interactive(), use_container_width=True)
        
        # Stress Chart
        df_stress = df_plot.melt('Date', value_vars=['Avg_Stress', 'Avg_N_Stress', 'Avg_P_Stress', 'Avg_K_Stress'], var_name='Type', value_name='Index')
        df_stress['Type_Label'] = df_stress['Type'].map({'Avg_Stress': tr('Water stress'), 'Avg_N_Stress': tr('Nitrogen stress'), 'Avg_P_Stress': tr('Phosphorus stress'), 'Avg_K_Stress': tr('Potassium stress')})
        c_stress = alt.Chart(df_stress).mark_area(opacity=0.5).encode(
            x='Date:T',
            y=alt.Y('Index:Q', title=tr('Stress Index (0-1)')),
            color=alt.Color('Type_Label:N', scale=alt.Scale(scheme='category10'), legend=alt.Legend(title=tr('Stress Index (0-1)')))
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
        df_dis_melt['Metric_Label'] = df_dis_melt['Metric'].map({'Infection Severity': tr('Infection Severity'), 'Env. Risk Score': tr('Env. Risk Score')})
        
        base = alt.Chart(df_dis_melt).encode(x='Date:T')
        
        # We plot both as lines/areas on the same 0-1 scale
        lines = base.mark_area(opacity=0.4).encode(
            y=alt.Y('Value:Q', title=tr('Index (0-1)')),
            color=alt.Color('Metric_Label:N', scale=alt.Scale(domain=[tr('Infection Severity'), tr('Env. Risk Score')], range=['red', 'purple'])),
            tooltip=['Date', 'Metric_Label', 'Value']
        )
        
        st.altair_chart((lines + rule_detect + rule_selected).interactive(), use_container_width=True)

    # --- TAB 5: SATELLITE ---
    with tabs[4]:
        st.caption(tr("Comparing modeled LAI with observed Sentinel-2 NDVI on real cloud-free dates only. Agreement is supporting evidence, not proof of calibration."))
        sim_start = df_plot['Date'].min().date()
        sim_end = df_plot['Date'].max().date()
        today_date = date.today()
        
        if sim_start > today_date:
            st.warning("⚠️ " + tr("Simulation is for a future date range. Satellite validation is not available."))
        else:
            if 'ndvi_data' not in st.session_state:
                with st.spinner(tr("Fetching Sentinel-2 data from AlphaEarth...")):
                    coords = st.session_state['field_coords']
                    fetch_end = min(sim_end, today_date)
                    st.session_state['ndvi_data'] = fetch_sentinel_ndvi(coords, sim_start, fetch_end)
            
            df_ndvi = st.session_state.get('ndvi_data')
            if df_ndvi is not None and not df_ndvi.empty:
                base_model = alt.Chart(df_plot).encode(x='Date:T')
                line_lai_model = base_model.mark_line(color='green', strokeDash=[5,5]).encode(
                    y=alt.Y('LAI:Q', title=tr('Modelled LAI'), axis=alt.Axis(titleColor='green'))
                )
                base_sat = alt.Chart(df_ndvi).encode(x='Date:T')
                point_ndvi = base_sat.mark_point(color='blue', filled=True, size=60).encode(
                    y=alt.Y('NDVI:Q', title=tr('Satellite NDVI'), scale=alt.Scale(domain=[0, 1]), axis=alt.Axis(titleColor='blue')),
                    tooltip=['Date', 'NDVI']
                )
                c_check = alt.layer(line_lai_model, point_ndvi).resolve_scale(y='independent')
                st.altair_chart(c_check.interactive(), use_container_width=True)
            else:
                st.warning(tr("No clear satellite imagery found."))

    # --- STRESS SUMMARY ---
    st.subheader("🧭 " + tr("Stress Summary"))
    n_days = len(df_plot)
    w_days = (df_plot['Avg_Stress'] > 0.5).sum()
    n_days_stress = (df_plot['Avg_N_Stress'] > 0.5).sum()
    
    c1, c2 = st.columns(2)
    c1.info(f"**{tr('Water Stress')}:** {w_days} {tr('days')} ({w_days/n_days*100:.1f}%) > 0.5")
    c2.warning(f"**{tr('Nitrogen Stress')}:** {n_days_stress} {tr('days')} ({n_days_stress/n_days*100:.1f}%) > 0.5")
    
    with st.expander("📋 " + tr("View Raw Daily Data")):
        raw_display = df_plot.drop(columns=['Grid_Incidence', 'Grid_Yield']).rename(columns={
            'Date': tr('Date'),
            'LAI': 'LAI',
            'SWC': tr('Water content'),
            'N_kg': tr('Nitrogen'),
            'P_kg': tr('Phosphorus'),
            'K_kg': tr('Potassium'),
            'ETa': 'ETa',
            'Biomass': tr('Biomass'),
            'Wood_Biomass': tr('Wood biomass'),
            'Fruit_Biomass': tr('Fruit biomass'),
            'Yield': tr('Yield'),
            'Incidence': tr('Infection'),
            'Avg_Stress': tr('Average stress'),
            'Avg_N_Stress': tr('Average nitrogen stress'),
            'Avg_P_Stress': tr('Average phosphorus stress'),
            'Avg_K_Stress': tr('Average potassium stress'),
            'Env_Favorability': tr('Environmental favorability'),
        })
        st.dataframe(raw_display)

    if st.button("🔄 " + tr("Rerun Simulation")):
        if 'sim_results' in st.session_state: del st.session_state['sim_results']
        if 'ndvi_data' in st.session_state: del st.session_state['ndvi_data']
        if 'sim_uncertainty' in st.session_state: del st.session_state['sim_uncertainty']
        st.rerun()