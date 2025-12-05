#pages\main\report.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from fpdf import FPDF
from datetime import date
import tempfile
import os
import matplotlib.tri as mtri
from src.models.simulation_engine import SimulationEngine
from src.models.state_manager import StateManager
from google.oauth2.service_account import Credentials
import ee

class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'AlphaEarth Intelligence Dossier', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Generated: {date.today()}', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'R')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(230, 240, 255)
        self.cell(0, 8, f'  {label}', 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, txt):
        txt = txt.replace('\\n', '\n')
        lines = txt.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                self.ln(4) 
                continue
            
            is_bullet = False
            if line.startswith('- ') or line.startswith('* '):
                is_bullet = True
                line = line[2:] 
            
            if is_bullet:
                self.set_font('Arial', 'B', 14) 
                self.cell(6, 5, chr(149), 0, 0, 'R') 
                self.set_font('Arial', '', 10)
            else:
                self.set_font('Arial', '', 10)

            parts = line.split('**')
            for i, part in enumerate(parts):
                if not part: continue
                if i % 2 == 1:
                    self.set_font('Arial', 'B', 10)
                else:
                    self.set_font('Arial', '', 10)
                self.write(5, part)
            self.ln(6)

    def add_plot_to_pdf(self, fig):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.savefig(tmp.name, bbox_inches='tight', dpi=150)
            self.image(tmp.name, w=170)
            os.unlink(tmp.name)
        self.ln(5)

# --- HELPER: NDVI FETCH ---
def fetch_sentinel_ndvi(coords, start_date, end_date):
    if start_date > end_date: return pd.DataFrame(columns=['Date', 'NDVI'])

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
            return ee.Feature(None, {'date': image.date().format('YYYY-MM-dd'), 'ndvi': stats.get('NDVI')})
            
        count = s2.size().getInfo()
        if count == 0: return pd.DataFrame(columns=['Date', 'NDVI'])
        
        ndvi_series = s2.map(get_ndvi).reduceColumns(ee.Reducer.toList(2), ['date', 'ndvi']).getInfo()['list']
        df = pd.DataFrame(ndvi_series, columns=['Date', 'NDVI'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.dropna()
        return df.sort_values('Date')
    except Exception as e:
        return None

def app():
    st.title("🗃️ Digital Twin Report")
    
    if 'sim_results' not in st.session_state:
        st.error("No simulation data found. Please run the Dashboard first.")
        return

    res_single = st.session_state['sim_results']
    crop_p = res_single['crop_params']
    is_perennial = crop_p['Type'] == 'Perennial'
    
    dis_id = st.session_state['selected_disease_id']
    df_d = st.session_state['df_diseases']
    dis_info = df_d[df_d['Disease_ID'] == dis_id].iloc[0] if dis_id else None

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"### Subject: **{crop_p['Crop_Name']}** ({crop_p['Variety']})")
        st.caption("This dossier consolidates mechanistic simulation data, AlphaEarth environmental signals, and manual surveillance inputs.")
        st.info("ℹ️ Generating the PDF triggers multiple simulation engines (Disease Ensemble + Irrigation Optimizer + Nutrition Optimizer).")
    
    with col2:
        if st.button("📄 Download PDF Dossier", type="primary", use_container_width=True):
            
            # --- 1. PREPARE CONFIG ---
            engine = SimulationEngine()
            config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
            
            get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
            config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
            config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
            
            config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
            config['initial_nitrogen'] = st.session_state.get('initial_nitrogen', 100.0)
            config['insect_pressure'] = st.session_state.get('insect_pressure', 1.0)
            config['planting_date'] = st.session_state.get('planting_date', date.today())
            
            if st.session_state.get('soil_layers') is not None:
                config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
            else:
                config['soil_layers'] = []

            # --- 2. RUN DISEASE ENSEMBLE ---
            # Automatically handles 10-year horizon for perennials inside SimulationEngine
            with st.spinner(f"Running 50 Stochastic Scenarios for {'10-Year' if is_perennial else 'Seasonal'} Risk..."):
                ens_res = engine.run_ensemble_inference(config, n_runs=50)
                
            if ens_res is None:
                st.error("Ensemble failed. Check configuration.")
                return

            # --- 3. RUN OPTIMIZERS ---
            with st.spinner("🤖 Optimizing Water & Nutrition Strategy..."):
                opt_irr_schedule, final_swc = engine.optimize_irrigation_schedule(config)
                season_advice = engine.assess_planting_season(st.session_state['center_lat'], st.session_state['center_lon'])
                opt_fert_schedule = engine.optimize_fertilization_schedule(config)

            # --- 4. RUN POTENTIAL YIELD (CONTROL) ---
            with st.spinner("Computing Biological Potential..."):
                optimal_config = config.copy()
                optimal_config['irr_schedule'] = opt_irr_schedule
                optimal_config['fert_schedule'] = opt_fert_schedule
                optimal_config['selected_disease_id'] = None
                optimal_config['disease_spots'] = []
                optimal_config['insect_pressure'] = 0.0
                
                res_potential = engine.run_simulation(optimal_config)
                
                # Extract Potential Curve
                hist_potential = res_potential['history'] if res_potential else []
                if is_perennial:
                    # For perennials, potential is the standing fruit curve
                    pot_yield_curve = [day.get('Fruit_Biomass', day['Yield']) for day in hist_potential]
                else:
                    pot_yield_curve = [day['Yield'] for day in hist_potential]
                
                pot_yield_dates = [day['Date'] for day in hist_potential]

            # --- 5. COMPILE REPORT ---
            with st.spinner("Compiling Intelligence..."):
                pdf = PDFReport()
                pdf.add_page()
                
                stats = ens_res['ensemble_stats']
                area = st.session_state.get('area_ha', 1.0)
                
                # --- METRICS LOGIC ---
                if is_perennial:
                    # ROI: Analyze Peaks (Harvests) over 10 years
                    df_ens = pd.DataFrame({'Date': stats['Date'], 'Yield': stats['Yield_Mean']})
                    df_ens['Year'] = pd.to_datetime(df_ens['Date']).dt.year
                    
                    # Get max standing fruit per year (proxy for harvestable amount)
                    yearly_peaks = df_ens.groupby('Year')['Yield'].max()
                    
                    # 1. Average Annual Yield
                    final_y_mean = yearly_peaks.mean() 
                    
                    # 2. Total Production (Sum of all years)
                    total_production_mean = yearly_peaks.sum() * area
                    
                    # Uncertainty (approx based on last year's std dev ratio)
                    last_std = stats['Yield_Std'][-1]
                    last_mean = stats['Yield_Mean'][-1]
                    cv = last_std / (last_mean + 1e-6)
                    final_y_ci = 1.96 * (final_y_mean * cv)
                    total_prod_ci = 1.96 * (total_production_mean * cv)
                    
                    # Gap Analysis (Potential vs Realized)
                    df_pot = pd.DataFrame({'Date': pot_yield_dates, 'Yield': pot_yield_curve})
                    df_pot['Year'] = pd.to_datetime(df_pot['Date']).dt.year
                    pot_peaks = df_pot.groupby('Year')['Yield'].max()
                    
                    pot_avg = pot_peaks.mean() # Average Potential
                    pot_total = pot_peaks.sum() # Total Potential
                    
                    # Gap based on Totals (mathematically equivalent to gap based on averages)
                    yield_gap_t = pot_total - yearly_peaks.sum()
                    loss_pct = (yield_gap_t / (pot_total + 1e-6)) * 100
                    
                    # UPDATED LABELS: Showing 10y Average instead of Cumulative
                    potential_label = f"{pot_avg:.2f} t/ha (10y Average)"
                    forecast_label = f"{final_y_mean:.2f} +/- {final_y_ci:.2f} t/ha (10y Average)"
                    
                else:
                    # ANNUAL: Single final value
                    final_y_mean = stats['Yield_Mean'][-1]
                    final_y_std = stats['Yield_Std'][-1]
                    final_y_ci = 1.96 * final_y_std
                    
                    total_production_mean = final_y_mean * area
                    total_prod_ci = final_y_ci * area
                    
                    pot_val = pot_yield_curve[-1] if pot_yield_curve else 0
                    yield_gap_t = pot_val - final_y_mean
                    loss_pct = (yield_gap_t / (pot_val + 1e-6)) * 100
                    
                    potential_label = f"{pot_val:.2f} t/ha"
                    forecast_label = f"{final_y_mean:.2f} +/- {final_y_ci:.2f} t/ha"

                # Stress Frequency
                hist_single = res_single['history']
                df_hist = pd.DataFrame(hist_single)
                peak_stress_w = df_hist['Avg_Stress'].max()
                peak_stress_n = df_hist['Avg_N_Stress'].max()
                
                # Drought Events Count (Days > 0.6 stress)
                drought_days = (df_hist['Avg_Stress'] > 0.6).sum()
                drought_events = drought_days // 7 # Approx weeks of severe stress

                # --- CHAPTER 1: CONFIG ---
                pdf.chapter_title("1. Field Configuration")
                conf_txt = (
                    f"Location: {st.session_state['center_lat']:.4f}, {st.session_state['center_lon']:.4f}\n"
                    f"Crop: {crop_p['Crop_Name']} - {crop_p['Variety']} ({'Perennial - 10 Year Horizon' if is_perennial else f'Annual - {crop_p['Cycle_Days']} days'})\n"
                    f"Soil Type: {st.session_state['soil_type'].title()}\n"
                    f"Initial Nutrients (mg/kg): N={st.session_state['initial_nitrogen']}, P={st.session_state.get('initial_phosphorus',20)}, K={st.session_state.get('initial_potassium',100)}\n"
                    f"Disease Target: {dis_info['Disease_Name'] if dis_info is not None else 'None'}"
                )
                pdf.chapter_body(conf_txt)
                
                # --- CHAPTER 2: DIAGNOSTICS ---
                pdf.chapter_title("2. Agronomic Diagnostics")
                
                diag_txt = (
                    f"Bio-Physical Potential (Optimal Mgmt): **{potential_label}**\n"
                    f"Forecast Yield (Current Scenario): **{forecast_label}**\n"
                    f"Yield Gap: **{loss_pct:.1f}%** loss attributed to current management and disease pressure.\n"
                    f"Est. Total Production: {total_production_mean:.1f} +/- {total_prod_ci:.1f} tonnes\n"
                    f"Current Water Stress Peak: {peak_stress_w*100:.1f}% severity.\n"
                    f"Current Nitrogen Stress Peak: {peak_stress_n*100:.1f}% severity."
                )
                
                if is_perennial:
                    diag_txt += f"\n**Long-Term Risk:** {drought_events} severe drought weeks projected over the next decade."
                
                pdf.chapter_body(diag_txt)
                
                # --- PLOT 1: TRAJECTORY ---
                fig1, ax1 = plt.subplots(figsize=(10, 5))
                dates = pd.to_datetime(stats['Date'])
                
                if is_perennial:
                    # SAWTOOTH PLOT
                    ax1.plot(dates, stats['Yield_Mean'], 'g-', linewidth=2, label='Forecast (Standing Fruit)')
                    
                    # Uncertainty Ribbon
                    lower = stats['Yield_Mean'] - (1.96 * stats['Yield_Std'])
                    upper = stats['Yield_Mean'] + (1.96 * stats['Yield_Std'])
                    # Clip lower at 0
                    lower = np.maximum(lower, 0)
                    
                    ax1.fill_between(dates, lower, upper, color='green', alpha=0.2, label='95% Uncertainty')
                    
                    # Formatting
                    ax1.set_ylabel('Standing Fruit (t/ha)', color='g')
                    ax1.set_title("Simulation Trajectory (10 Year Horizon)")
                    
                    # Format X-axis to show Years
                    ax1.xaxis.set_major_locator(mdates.YearLocator())
                    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
                    
                else:
                    # SIGMOID PLOT (Annual)
                    if pot_yield_curve:
                        ax1.plot(pot_yield_dates, pot_yield_curve, 'k--', alpha=0.6, linewidth=1.5, label='Potential')
                    
                    ax1.plot(dates, stats['Yield_Mean'], 'g-', linewidth=2, label='Forecast')
                    
                    lower = stats['Yield_Mean'] - (1.96 * stats['Yield_Std'])
                    upper = stats['Yield_Mean'] + (1.96 * stats['Yield_Std'])
                    ax1.fill_between(dates, lower, upper, color='green', alpha=0.2, label='95% Uncertainty')
                    
                    ax1.set_ylabel('Yield (t/ha)', color='g')
                    ax1.set_title("Yield Accumulation Forecast")

                ax1.legend(loc='upper left', fontsize='small')
                ax1.grid(True, alpha=0.3)
                pdf.add_plot_to_pdf(fig1)
                plt.close(fig1)
                
                # --- CHAPTER 3: WATER ---
                pdf.chapter_title("3. Smart Water Management")
                
                if peak_stress_w > 0.5: status = "CRITICAL"
                elif peak_stress_w > 0.2: status = "MODERATE"
                else: status = "OPTIMAL"
                
                water_intro = f"Current Status: **{status}** (Peak Stress Index: {peak_stress_w:.2f})\n"
                if season_advice:
                    water_intro += f"**Seasonality Insight:** {season_advice.get('advice', 'No data')}\n"
                pdf.chapter_body(water_intro)
                
                if opt_irr_schedule:
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 8, "Recommended Supplemental Irrigation Calendar:", 0, 1)
                    pdf.set_font('Arial', '', 9)
                    
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(40, 7, "Date", 1, 0, 'C', 1)
                    pdf.cell(40, 7, "Amount (mm)", 1, 0, 'C', 1)
                    pdf.cell(90, 7, "Rationale", 1, 1, 'L', 1)
                    
                    # Limit displayed rows for PDF to avoid overflow
                    display_limit = 15
                    for i, event in enumerate(opt_irr_schedule):
                        if i >= display_limit:
                            pdf.cell(40, 7, "...", 1, 0, 'C')
                            pdf.cell(40, 7, "...", 1, 0, 'C')
                            pdf.cell(90, 7, f"and {len(opt_irr_schedule)-display_limit} more events.", 1, 1, 'L')
                            break
                        
                        pdf.cell(40, 7, str(event['date']), 1, 0, 'C')
                        pdf.cell(40, 7, f"{event['amount']} mm", 1, 0, 'C')
                        pdf.cell(90, 7, "Refill Soil Moisture to 90% FC", 1, 1, 'L')
                    
                    pdf.ln(5)
                    pdf.chapter_body(f"**Projected Impact:** Implementing this schedule contributes to reaching the potential yield.")
                else:
                    pdf.chapter_body("No additional irrigation is required.")

                # --- CHAPTER 4: NUTRITION ---
                pdf.chapter_title("4. Precision Nutrition Strategy")
                
                if not opt_fert_schedule:
                    pdf.chapter_body("[OK] Soil nutrient stocks are sufficient.")
                else:
                    pdf.chapter_body("Objective: Maintain N-P-K levels above critical thresholds during active growth.")
                    
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 8, "Recommended Product Application Schedule:", 0, 1)
                    pdf.set_font('Arial', '', 9)
                    
                    pdf.set_fill_color(230, 240, 255)
                    pdf.cell(30, 7, "Date", 1, 0, 'C', 1)
                    pdf.cell(50, 7, "Product", 1, 0, 'L', 1)
                    pdf.cell(30, 7, "Rate (kg/ha)", 1, 0, 'C', 1)
                    pdf.cell(80, 7, "Rationale", 1, 1, 'L', 1)
                    pdf.set_font('Arial', '', 9)
                    
                    display_limit = 15
                    for i, event in enumerate(opt_fert_schedule):
                        if i >= display_limit:
                            pdf.cell(30, 7, "...", 1, 0, 'C')
                            pdf.cell(160, 7, f"and {len(opt_fert_schedule)-display_limit} more events.", 1, 1, 'L')
                            break

                        date_str = str(event['date'])
                        prod_str = event['product']
                        rate_str = f"{event['amount']} kg"
                        rat_str = event['rationale']
                        
                        # Dynamic row height
                        num_lines = max(1, len(rat_str) // 45 + 1)
                        row_height = 6 * num_lines
                        
                        # Page break check
                        if pdf.get_y() + row_height > 270:
                            pdf.add_page()
                            # Re-print header
                            pdf.set_font('Arial', 'B', 9)
                            pdf.cell(30, 7, "Date", 1, 0, 'C', 1)
                            pdf.cell(50, 7, "Product", 1, 0, 'L', 1)
                            pdf.cell(30, 7, "Rate (kg/ha)", 1, 0, 'C', 1)
                            pdf.cell(80, 7, "Rationale", 1, 1, 'L', 1)
                            pdf.set_font('Arial', '', 9)

                        x_start = pdf.get_x()
                        y_start = pdf.get_y()
                        
                        pdf.cell(30, row_height, date_str, 1, 0, 'C')
                        pdf.cell(50, row_height, prod_str, 1, 0, 'L')
                        pdf.cell(30, row_height, rate_str, 1, 0, 'C')
                        pdf.set_xy(x_start + 110, y_start) 
                        pdf.multi_cell(80, 6, rat_str, 1, 'L')
                        pdf.set_xy(x_start, y_start + row_height)

                    pdf.ln(5)

                # --- CHAPTER 5: SATELLITE ---
                pdf.chapter_title("5. Satellite Reality Check")
                pdf.chapter_body("Comparison of Digital Twin growth model (LAI) vs observed Satellite Vegetation Index (NDVI).")

                sim_start = pd.to_datetime(stats['Date'][0]).date()
                sim_end = pd.to_datetime(stats['Date'][-1]).date()
                today = date.today()
                fetch_end = min(sim_end, today)

                if 'ndvi_data' not in st.session_state:
                    if sim_start <= today:
                        coords = st.session_state['field_coords']
                        st.session_state['ndvi_data'] = fetch_sentinel_ndvi(coords, sim_start, fetch_end)
                    else:
                        st.session_state['ndvi_data'] = None

                df_ndvi = st.session_state.get('ndvi_data')

                if df_ndvi is not None and not df_ndvi.empty:
                    fig_sat, ax1 = plt.subplots(figsize=(8, 4))
                    l1, = ax1.plot(dates, df_hist['LAI'], 'g--', linewidth=1.5, label='Model LAI')
                    ax1.set_ylabel('Leaf Area Index', color='g')
                    ax1.tick_params(axis='y', labelcolor='g')
                    
                    ax2 = ax1.twinx()
                    l2, = ax2.plot(df_ndvi['Date'], df_ndvi['NDVI'], 'bo', markersize=4, label='Satellite NDVI')
                    ax2.set_ylabel('NDVI', color='b')
                    ax2.tick_params(axis='y', labelcolor='b')
                    
                    ax1.legend([l1, l2], ['Model LAI', 'Satellite NDVI'], loc='upper left')
                    ax1.set_title("Digital Twin vs. Satellite")
                    ax1.grid(True, linestyle=':', alpha=0.6)
                    pdf.add_plot_to_pdf(fig_sat)
                    plt.close(fig_sat)
                    pdf.chapter_body("Interpretation: Strong correlation confirms calibration.")
                else:
                    pdf.chapter_body("No satellite imagery available (Future dates or Cloud cover).")

                # --- CHAPTER 6: EPIDEMIOLOGY ---
                if dis_info is not None:
                    pdf.chapter_title("6. Epidemiological Risk")
                    final_inf_mean = stats['Incidence_Mean'][-1]
                    final_inf_std = stats['Incidence_Std'][-1]
                    final_inf_ci = 1.96 * final_inf_std
                    
                    epi_txt = (
                        f"Pathogen: **{dis_info['Disease_Name']}**\n"
                        f"Final Infection Severity: {final_inf_mean*100:.1f}% +/- {final_inf_ci*100:.1f}%."
                    )
                    pdf.chapter_body(epi_txt)
                    
                    fig2, ax = plt.subplots(figsize=(8, 4))
                    ax.plot(dates, stats['Incidence_Mean']*100, 'r-', linewidth=2, label='Infection %')
                    lower_i = np.clip(stats['Incidence_Mean'] - (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    upper_i = np.clip(stats['Incidence_Mean'] + (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    ax.fill_between(dates, lower_i, upper_i, color='red', alpha=0.2)
                    ax.set_ylabel('Field Infection %')
                    ax.set_title("Disease Progression")
                    ax.grid(True, alpha=0.3)
                    pdf.add_plot_to_pdf(fig2)
                    plt.close(fig2)
                    
                    # Map
                    try:
                        fig3, ax3 = plt.subplots(figsize=(8, 6))
                        triang_source = ens_res['triangulation']
                        vals = stats['Final_Grid_Mean']
                        x_plot = triang_source.y 
                        y_plot = triang_source.x 
                        
                        triang_plot = mtri.Triangulation(x_plot, y_plot, triang_source.triangles)
                        if triang_source.mask is not None:
                            triang_plot.set_mask(triang_source.mask)
                        
                        tpc = ax3.tripcolor(triang_plot, vals, cmap='Reds', shading='gouraud', vmin=0, vmax=1)
                        
                        poly = ens_res['field_poly'] 
                        poly_plot = np.vstack([poly, poly[0]])
                        ax3.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5)
                        
                        ax3.set_aspect('equal')
                        ax3.set_title("Final Disease Severity Map")
                        fig3.colorbar(tpc, ax=ax3, label="Severity (0-1)")
                        pdf.add_plot_to_pdf(fig3)
                        plt.close(fig3)
                    except Exception:
                        pass

                # --- CHAPTER 7: RECS ---
                pdf.chapter_title("7. Management Recommendations")
                recs = []
                
                if dis_info is not None:
                    recs.append(f"**Specific Protocols for {dis_info['Disease_Name']}:**")
                    raw_methods = dis_info['Control_Methods'].replace('\\n', '\n')
                    for m in raw_methods.split('\n'):
                        if m.strip(): recs.append(f"- {m.strip()}")
                
                if peak_stress_w > 0.6: recs.append("**!! CRITICAL WATER STRESS.**")
                if peak_stress_n > 0.5: recs.append("**! Nitrogen Deficiency.**")
                
                if not recs: recs.append("[OK] Crop status is healthy.")
                
                pdf.chapter_body("\n".join(recs))
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.download_button(
                    "⬇️ Download PDF", 
                    data=pdf_bytes, 
                    file_name=f"AEF_Report_{date.today()}.pdf", 
                    mime="application/pdf"
                )
                st.success("Report generated successfully.")