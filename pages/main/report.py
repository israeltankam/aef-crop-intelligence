#pages\main\report.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
from datetime import date
import tempfile
import os
import matplotlib.tri as mtri
from src.models.simulation_engine import SimulationEngine
from src.models.state_manager import StateManager

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
        """
        Robust text renderer that handles:
        - Literal newline characters (\\n) cleaning
        - **Bold** markdown parsing
        - Bullet points
        """
        # 1. Clean literal newlines often found in CSV imports
        txt = txt.replace('\\n', '\n')
        
        # 2. Split into logical lines to preserve structure
        lines = txt.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                self.ln(4) # Space for empty paragraphs
                continue
            
            # Detect Bullet Points
            is_bullet = False
            if line.startswith('- ') or line.startswith('* '):
                is_bullet = True
                line = line[2:] # Remove the marker
            
            # Start line
            if is_bullet:
                self.set_font('Arial', 'B', 14) # Larger font for bullet symbol
                self.cell(6, 5, chr(149), 0, 0, 'R') # Unicode bullet
                # Reset standard font for text
                self.set_font('Arial', '', 10)
            else:
                self.set_font('Arial', '', 10)

            # 3. Parse **Bold** Markers
            # Split by '**'. 
            # Parts at indices 0, 2, 4... are Normal.
            # Parts at indices 1, 3, 5... are Bold.
            parts = line.split('**')
            
            for i, part in enumerate(parts):
                if not part: continue
                
                if i % 2 == 1:
                    self.set_font('Arial', 'B', 10)
                else:
                    self.set_font('Arial', '', 10)
                
                # Use write() to handle automatic text wrapping within the line
                self.write(5, part)
                
            # Line break after processing the full line/paragraph
            self.ln(6)

    def add_plot_to_pdf(self, fig):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.savefig(tmp.name, bbox_inches='tight', dpi=150)
            self.image(tmp.name, w=170)
            os.unlink(tmp.name)
        self.ln(5)

def app():
    st.title("🗃️ Digital Twin Report")
    
    if 'sim_results' not in st.session_state:
        st.error("No simulation data found. Run the Dashboard first.")
        return

    res_single = st.session_state['sim_results']
    crop_p = res_single['crop_params']
    
    dis_id = st.session_state['selected_disease_id']
    df_d = st.session_state['df_diseases']
    dis_info = df_d[df_d['Disease_ID'] == dis_id].iloc[0] if dis_id else None

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"### Subject: **{crop_p['Crop_Name']}** ({crop_p['Variety']})")
        st.caption("This dossier consolidates mechanistic simulation data, AlphaEarth environmental signals, and manual surveillance inputs.")
        st.info("ℹ️ Generating the PDF will take some time to quantify risk uncertainty.")
    
    with col2:
        if st.button("📄 Download PDF Dossier", type="primary", use_container_width=True):
            with st.spinner("Running 50 Stochastic Scenarios for Risk Quantification..."):
                engine = SimulationEngine()
                config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
                get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
                config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
                config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
                config['soil_water_holding_cap'] = st.session_state.get('soil_water_holding_cap', 150.0)
                config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
                config['initial_nitrogen'] = st.session_state.get('initial_nitrogen', 100.0)
                config['insect_pressure'] = st.session_state.get('insect_pressure', 1.0)
                config['planting_date'] = st.session_state.get('planting_date', date.today())
                ens_res = engine.run_ensemble_inference(config, n_runs=50)
                
            if ens_res is None: st.error("Ensemble failed. Check configuration."); return

            with st.spinner("Compiling Intelligence..."):
                pdf = PDFReport()
                pdf.add_page()
                stats = ens_res['ensemble_stats']
                final_y_mean = stats['Yield_Mean'][-1]
                final_y_std = stats['Yield_Std'][-1]
                final_y_ci = 1.96 * final_y_std
                pot_yield = stats['Biomass_Potential'][-1] * crop_p['Harvest_Index']
                final_inf_mean = stats['Incidence_Mean'][-1]
                final_inf_std = stats['Incidence_Std'][-1]
                final_inf_ci = 1.96 * final_inf_std
                area = st.session_state.get('area_ha', 1.0)
                total_prod_mean = final_y_mean * area
                total_prod_ci = final_y_ci * area
                hist_single = res_single['history']
                df_hist = pd.DataFrame(hist_single)
                peak_stress_w = df_hist['Avg_Stress'].max()
                peak_stress_n = df_hist['Avg_N_Stress'].max()

                # 1. CONFIGURATION
                pdf.chapter_title("1. Field Configuration")
                conf_txt = (f"Location: {st.session_state['center_lat']:.4f}, {st.session_state['center_lon']:.4f}\n"
                            f"Crop: {crop_p['Crop_Name']} - {crop_p['Variety']} (Cycle: {crop_p['Cycle_Days']} days)\n"
                            f"Soil Profile: {st.session_state['soil_type'].title()}, Initial N: {st.session_state['initial_nitrogen']} kg/ha\n"
                            f"Disease Target: {dis_info['Disease_Name'] if dis_info is not None else 'None'}")
                pdf.chapter_body(conf_txt)
                
                # 2. AGRONOMIC DIAGNOSTICS
                pdf.chapter_title("2. Agronomic Diagnostics (Probabilistic)")
                loss_pct = (1 - (final_y_mean / (pot_yield + 1e-6))) * 100
                diag_txt = (f"Final Yield Forecast: {final_y_mean:.2f} +/- {final_y_ci:.2f} t/ha (95% CI)\n"
                            f"Est. Total Production: {total_prod_mean:.1f} +/- {total_prod_ci:.1f} tonnes\n"
                            f"Yield Gap (Loss): ~{loss_pct:.1f}% compared to biological potential.\n"
                            f"Water Stress Peak: {peak_stress_w*100:.1f}% severity.\n"
                            f"Nitrogen Stress Peak: {peak_stress_n*100:.1f}% severity.\n"
                            f"Modeling Basis: Monte Carlo Ensemble (N=50) for disease diffusion.")
                pdf.chapter_body(diag_txt)
                
                # PLOT 1: Yield Ensemble
                fig1, ax1 = plt.subplots(figsize=(8, 4))
                dates = pd.to_datetime(stats['Date'])
                ax1.plot(dates, np.array(stats['Biomass_Potential']) * crop_p['Harvest_Index'], 'k--', alpha=0.5, label='Potential (No Disease)')
                ax1.plot(dates, stats['Yield_Mean'], 'g-', linewidth=2, label='Forecast Yield (Mean)')
                lower = stats['Yield_Mean'] - (1.96 * stats['Yield_Std'])
                upper = stats['Yield_Mean'] + (1.96 * stats['Yield_Std'])
                ax1.fill_between(dates, lower, upper, color='green', alpha=0.2, label='95% Confidence')
                ax1.set_ylabel('Yield (t/ha)', color='g')
                ax1.legend(loc='upper left')
                ax1.grid(True, alpha=0.3)
                ax1.set_title("Yield Forecast with Uncertainty")
                pdf.add_plot_to_pdf(fig1)
                plt.close(fig1)
                
                # 3. SATELLITE VALIDATION
                if 'ndvi_data' in st.session_state and st.session_state['ndvi_data'] is not None:
                    pdf.chapter_title("3. Satellite Reality Check (Sentinel-2)")
                    pdf.chapter_body("Comparison of Digital Twin growth model (LAI) vs observed Satellite Vegetation Index (NDVI).")
                    df_ndvi = st.session_state['ndvi_data']
                    fig_sat, ax_sat = plt.subplots(figsize=(8, 4))
                    l1, = ax_sat.plot(dates, df_hist['LAI'], 'g--', label='Model LAI')
                    ax_sat.set_ylabel('Leaf Area Index', color='g')
                    ax_sat2 = ax_sat.twinx()
                    l2, = ax_sat2.plot(df_ndvi['Date'], df_ndvi['NDVI'], 'bo', label='Satellite NDVI')
                    ax_sat2.set_ylabel('NDVI (Observed)', color='b')
                    ax_sat2.set_ylim(0, 1)
                    plt.legend([l1, l2], ['Model LAI', 'Satellite NDVI'], loc='upper left')
                    ax_sat.set_title("Model Predictions vs Satellite Observations")
                    pdf.add_plot_to_pdf(fig_sat)
                    plt.close(fig_sat)

                # 4. EPIDEMIOLOGY
                if dis_info is not None:
                    pdf.chapter_title("4. Epidemiological Risk Assessment")
                    epi_txt = (f"Pathogen: {dis_info['Disease_Name']} ({dis_info['Type']})\n"
                               f"Final Infection Severity: {final_inf_mean*100:.1f} +/- {final_inf_ci*100:.1f}% area affected.\n"
                               f"Projected Impact: {final_inf_mean*100:.1f}% +/- {final_inf_ci*100:.1f}% of field infected by harvest.")
                    pdf.chapter_body(epi_txt)
                    
                    fig2, ax = plt.subplots(figsize=(8, 4))
                    ax.plot(dates, stats['Incidence_Mean']*100, 'r-', linewidth=2, label='Infection % (Mean)')
                    lower_i = np.clip(stats['Incidence_Mean'] - (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    upper_i = np.clip(stats['Incidence_Mean'] + (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    ax.fill_between(dates, lower_i, upper_i, color='red', alpha=0.2, label='95% Confidence')
                    ax.set_ylabel('Field Infection %')
                    ax.set_title(f"{dis_info['Disease_Name']} Progression Risk")
                    ax.grid(True, alpha=0.3)
                    ax.legend()
                    pdf.add_plot_to_pdf(fig2)
                    plt.close(fig2)
                    
                    try:
                        fig3, ax3 = plt.subplots(figsize=(8, 6))
                        triang_source = ens_res['triangulation']
                        vals = stats['Final_Grid_Mean']
                        x_plot = triang_source.y
                        y_plot = triang_source.x
                        triang_plot = mtri.Triangulation(x_plot, y_plot, triang_source.triangles)
                        tpc = ax3.tripcolor(triang_plot, vals, cmap='Reds', shading='gouraud', vmin=0, vmax=1)
                        poly = ens_res['field_poly']
                        poly_plot = np.vstack([poly, poly[0]])
                        ax3.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5)
                        ax3.set_aspect('equal')
                        ax3.set_title("Mean Disease Severity Probability Map (N=50)")
                        ax3.set_xlabel("Longitude")
                        ax3.set_ylabel("Latitude")
                        fig3.colorbar(tpc, ax=ax3, label="Avg. Severity (0-1)")
                        ax3.grid(True, linestyle='--', alpha=0.3)
                        pdf.add_plot_to_pdf(fig3)
                        plt.close(fig3)
                    except Exception as e:
                        pdf.chapter_body(f"[Map generation error: {str(e)}]")

                # 5. RECOMMENDATIONS (Enriched)
                pdf.chapter_title("5. Management Recommendations")
                recs = []
                
                if dis_info is not None:
                    # Header for protocols
                    recs.append(f"**Specific Protocols for {dis_info['Disease_Name']}:**")
                    
                    # Process lines from DB
                    # The replace('\\n', '\n') ensures raw strings from CSV are split correctly
                    raw_methods = dis_info['Control_Methods'].replace('\\n', '\n')
                    methods = raw_methods.split('\n')
                    
                    for m in methods:
                        m = m.strip()
                        if m:
                            recs.append(f"- {m}")
                    
                    if final_inf_mean > 0.3:
                        recs.append("\n**!! ALERT:** High probability of widespread infection. Immediate intervention based on the protocols above is required.")
                    elif final_inf_mean > 0.05:
                        recs.append("\n**! WARNING:** Infection detected. Scout the high-probability zones shown in the map.")
                
                if peak_stress_w > 0.6: recs.append("**!! CRITICAL WATER STRESS.** Yield penalty severe. Review irrigation.")
                elif peak_stress_w > 0.3: recs.append("**! Moderate water stress.** Consider increasing irrigation.")
                if peak_stress_n > 0.5: recs.append("**! Nitrogen deficiency.** Apply side-dressing of N fertilizer.")
                if not recs: recs.append("✅ Crop status is healthy based on current simulation parameters.")

                # Join with newlines for the custom parser
                pdf.chapter_body("\n".join(recs))
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name=f"AEF_Report_{date.today()}.pdf", mime="application/pdf")
                st.success("Report generated successfully.")