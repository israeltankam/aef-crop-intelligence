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
        self.set_font('Arial', '', 10)
        self.multi_cell(0, 5, txt)
        self.ln()

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

    # Load Context
    res = st.session_state['sim_results']
    history = res['history']
    crop_p = res['crop_params']
    
    # Prepare Data
    df_hist = pd.DataFrame([{
        'Date': h['Date'], 
        'Biomass': h['Biomass'],
        'Yield': h['Yield'],
        'LAI': h['LAI'],
        'Infection': h['Incidence'],
        'Stress_W': h['Avg_Stress'],
        'Stress_N': h['Avg_N_Stress']
    } for h in history])
    
    final_yield = df_hist.iloc[-1]['Yield']
    potential_yield_no_stress = df_hist.iloc[-1]['Biomass'] * crop_p['Harvest_Index']
    final_infection = df_hist.iloc[-1]['Infection']
    peak_stress_w = df_hist['Stress_W'].max()
    peak_stress_n = df_hist['Stress_N'].max()
    
    # Disease Info
    dis_id = st.session_state['selected_disease_id']
    df_d = st.session_state['df_diseases']
    dis_info = df_d[df_d['Disease_ID'] == dis_id].iloc[0] if dis_id else None

    # --- UI ---
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"### Subject: **{crop_p['Crop_Name']}** ({crop_p['Variety']})")
        st.caption("This dossier consolidates mechanistic simulation data, AlphaEarth environmental signals, and manual surveillance inputs.")
    
    with col2:
        if st.button("📄 Download PDF Dossier", type="primary", use_container_width=True):
            with st.spinner("Compiling Intelligence..."):
                pdf = PDFReport()
                pdf.add_page()
                
                # 1. CONFIGURATION
                pdf.chapter_title("1. Field Configuration")
                conf_txt = (
                    f"Location: {st.session_state['center_lat']:.4f}, {st.session_state['center_lon']:.4f}\n"
                    f"Crop: {crop_p['Crop_Name']} - {crop_p['Variety']} (Cycle: {crop_p['Cycle_Days']} days)\n"
                    f"Soil Profile: {st.session_state['soil_type'].title()}, Initial N: {st.session_state['initial_nitrogen']} kg/ha\n"
                    f"Disease Target: {dis_info['Disease_Name'] if dis_info is not None else 'None'}"
                )
                pdf.chapter_body(conf_txt)
                
                # 2. AGRONOMIC DIAGNOSTICS
                pdf.chapter_title("2. Agronomic Diagnostics")
                
                area = st.session_state.get('area_ha', 1.0)
                total_prod = final_yield * area
                loss_pct = (1 - (final_yield / (potential_yield_no_stress + 1e-6))) * 100
                
                diag_txt = (
                    f"Final Yield Forecast: {final_yield:.2f} t/ha\n"
                    f"Est. Total Production: {total_prod:.1f} tonnes (on {area} ha)\n"
                    f"Yield Gap (Loss): {loss_pct:.1f}% compared to biological potential.\n"
                    f"Water Stress Peak: {peak_stress_w*100:.1f}% severity.\n"
                    f"Nitrogen Stress Peak: {peak_stress_n*100:.1f}% severity.\n"
                    f"Final Infection Severity: {final_infection*100:.1f}% area affected."
                )
                pdf.chapter_body(diag_txt)
                
                # PLOT 1: Yield
                fig1, ax1 = plt.subplots(figsize=(8, 4))
                ax1.plot(df_hist['Date'], df_hist['Yield'], 'g-', linewidth=2, label='Realized Yield')
                ax1.plot(df_hist['Date'], df_hist['Biomass'] * crop_p['Harvest_Index'], 'g--', alpha=0.5, label='Potential (No Stress)')
                ax1.set_ylabel('Yield (t/ha)', color='g')
                ax1.legend(loc='upper left')
                ax1.grid(True, alpha=0.3)
                ax1.set_title("Yield Accumulation vs Potential")
                pdf.add_plot_to_pdf(fig1)
                plt.close(fig1)
                
                # 3. SATELLITE VALIDATION (AlphaEarth)
                if 'ndvi_data' in st.session_state and st.session_state['ndvi_data'] is not None:
                    pdf.chapter_title("3. Satellite Reality Check (Sentinel-2)")
                    pdf.chapter_body("Comparison of Digital Twin growth model (LAI) vs observed Satellite Vegetation Index (NDVI). Discrepancies indicate unmodelled stress.")
                    
                    df_ndvi = st.session_state['ndvi_data']
                    
                    fig_sat, ax_sat = plt.subplots(figsize=(8, 4))
                    # Plot Model LAI on primary axis
                    l1, = ax_sat.plot(df_hist['Date'], df_hist['LAI'], 'g--', label='Model LAI')
                    ax_sat.set_ylabel('Leaf Area Index', color='g')
                    
                    # Plot Satellite NDVI on secondary axis
                    ax_sat2 = ax_sat.twinx()
                    l2, = ax_sat2.plot(df_ndvi['Date'], df_ndvi['NDVI'], 'bo', label='Satellite NDVI')
                    ax_sat2.set_ylabel('NDVI (Observed)', color='b')
                    ax_sat2.set_ylim(0, 1)
                    
                    # Combined legend
                    plt.legend([l1, l2], ['Model LAI', 'Satellite NDVI'], loc='upper left')
                    ax_sat.set_title("Model Predictions vs Satellite Observations")
                    pdf.add_plot_to_pdf(fig_sat)
                    plt.close(fig_sat)

                # 4. EPIDEMIOLOGY
                if dis_info is not None:
                    pdf.chapter_title("4. Epidemiological Risk Assessment")
                    epi_txt = (
                        f"Pathogen: {dis_info['Disease_Name']}\n"
                        f"Projected Impact: {final_infection*100:.1f}% of field infected by harvest."
                    )
                    pdf.chapter_body(epi_txt)
                    
                    # PLOT 2: Disease
                    fig2, ax = plt.subplots(figsize=(8, 4))
                    ax.plot(df_hist['Date'], df_hist['Infection']*100, 'r-', linewidth=2, label='Infection %')
                    ax.fill_between(df_hist['Date'], 0, df_hist['Infection']*100, color='red', alpha=0.2)
                    ax.set_ylabel('Field Infection %')
                    ax.set_title(f"{dis_info['Disease_Name']} Progression")
                    ax.grid(True, alpha=0.3)
                    pdf.add_plot_to_pdf(fig2)
                    plt.close(fig2)
                    
                    # PLOT 3: Final Disease Distribution Map (Fixed)
                    try:
                        fig3, ax3 = plt.subplots(figsize=(8, 6))
                        
                        # 1. Get Data from Simulation
                        triang_source = res['triangulation']
                        vals = res['history'][-1]['Grid_Incidence']
                        
                        # 2. Correct Coordinate Orientation
                        # Engine uses [Lat, Lon], we need to plot [Lon, Lat] (x, y)
                        x_plot = triang_source.y  # Longitude
                        y_plot = triang_source.x  # Latitude
                        triang_plot = mtri.Triangulation(x_plot, y_plot, triang_source.triangles)
                        
                        # 3. Plot Heatmap
                        tpc = ax3.tripcolor(triang_plot, vals, cmap='Reds', shading='gouraud', vmin=0, vmax=1)
                        
                        # 4. Add Boundary
                        poly = res['field_poly'] # [Lat, Lon]
                        poly_plot = np.vstack([poly, poly[0]])
                        # Plot Lon on X, Lat on Y
                        ax3.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5)
                        
                        # 5. Style
                        ax3.set_aspect('equal')
                        ax3.set_title("Final Disease Distribution Map")
                        ax3.set_xlabel("Longitude")
                        ax3.set_ylabel("Latitude")
                        fig3.colorbar(tpc, ax=ax3, label="Severity (0-1)")
                        ax3.grid(True, linestyle='--', alpha=0.3)
                        
                        pdf.add_plot_to_pdf(fig3)
                        plt.close(fig3)
                    except Exception as e:
                        pdf.chapter_body(f"[Map generation error: {str(e)}]")

                # 5. RECOMMENDATIONS
                pdf.chapter_title("5. Management Recommendations")
                recs = []
                
                if dis_info is not None:
                    recs.append(f"**Disease Control:** {dis_info['Control_Methods']}")
                    if final_infection > 0.3:
                        recs.append("!! ALERT: Infection is widespread. Immediate intervention required.")
                    elif final_infection > 0.05:
                        recs.append("! WARNING: Infection detected. Scout the red zones shown in the map.")
                
                if peak_stress_w > 0.6:
                    recs.append("!! CRITICAL WATER STRESS. Yield penalty severe. Review irrigation.")
                elif peak_stress_w > 0.3:
                    recs.append("! Moderate water stress. Consider increasing irrigation.")
                
                if peak_stress_n > 0.5:
                    recs.append("! Nitrogen deficiency. Apply side-dressing of N fertilizer.")

                if not recs:
                    recs.append("✅ Crop status is healthy. Continue current management.")

                pdf.chapter_body("\n\n".join(recs))
                
                # Output
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.download_button(
                    "⬇️ Download PDF", 
                    data=pdf_bytes, 
                    file_name=f"AEF_Report_{date.today()}.pdf", 
                    mime="application/pdf"
                )
                st.success("Report generated successfully.")