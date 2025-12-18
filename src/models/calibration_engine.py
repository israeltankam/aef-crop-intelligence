# src/models/calibration_engine.py

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from src.models.simulation_engine import SimulationEngine
import streamlit as st

class CalibrationEngine:
    def __init__(self):
        self.sim_engine = SimulationEngine()

    def calibrate_model(self, surveillance_data, config, crop_type='Annual'):
        """
        Adjusts internal parameters (RUE, Harvest Index, Beta Infection, etc.) to minimize
        error between Simulation and Observed Data.
        """
        # 1. Parse Data
        df = pd.DataFrame(surveillance_data)
        if df.empty: return None, "No data."

        # Filter valid observations
        obs_yield = df[df['Type'] == 'Yield (t/ha)']
        obs_biomass = df[df['Type'] == 'Biomass (t/ha)']
        obs_n = df[df['Type'] == 'Soil N (mg/kg)']
        obs_disease = df[df['Type'] == 'Disease Incidence (%)']
        
        if obs_yield.empty and obs_biomass.empty and obs_n.empty and obs_disease.empty:
            return None, "Insufficient valid data for calibration."

        # 2. Define Tunable Parameters & Bounds
        df_c = st.session_state['df_crops']
        base_crop = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
        
        # Base Disease Params
        has_disease_data = not obs_disease.empty
        base_beta = 0.0
        if config['selected_disease_id']:
            df_d = st.session_state['df_diseases']
            dis_row = df_d[df_d['Disease_ID'] == config['selected_disease_id']]
            if not dis_row.empty:
                base_beta = float(dis_row.iloc[0]['Beta_Infection'])

        # Params Vector: [RUE_mult, HI_mult, N_mult, Beta_mult]
        # We use multipliers to keep optimization stable around 1.0
        initial_guess = [1.0, 1.0, 1.0, 1.0]
        bounds = [(0.5, 1.5), (0.5, 1.5), (0.5, 2.0), (0.1, 5.0)] 
        
        # If no disease data or no disease selected, lock Beta multiplier to 1.0 (bounds very tight)
        if not has_disease_data or base_beta == 0:
            bounds[3] = (1.0, 1.0)

        # 3. Objective Function
        def objective(params):
            rue_mult, hi_mult, n_mult, beta_mult = params
            
            # Construct temporary config
            temp_config = config.copy()
            temp_config['calibrated_params'] = {
                'RUE_g_MJ': float(base_crop['RUE_g_MJ']) * rue_mult,
                'Harvest_Index': float(base_crop['Harvest_Index']) * hi_mult,
                'initial_nitrogen': config['initial_nitrogen'] * n_mult
            }
            
            # Inject Disease Override if applicable
            if has_disease_data and base_beta > 0:
                 temp_config['calibrated_params']['Beta_Infection'] = base_beta * beta_mult

            # Special handling for Perennials
            if crop_type == 'Perennial':
                 temp_config['calibrated_params']['Per_Tree_Wood_Capacity_kg'] = float(base_crop.get('Per_Tree_Wood_Capacity_kg', 25.0)) * hi_mult

            # Run Sim (Fast)
            res = self.sim_engine.run_simulation(temp_config)
            if res is None: return 1e6
            
            hist = pd.DataFrame(res['history'])
            hist['Date'] = pd.to_datetime(hist['Date']).dt.date
            
            error = 0.0
            
            # Compare Yield
            for _, row in obs_yield.iterrows():
                d = pd.to_datetime(row['Date']).date()
                val = float(row['Value'])
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Yield'] if crop_type == 'Annual' else sim_row.iloc[0]['Fruit_Biomass']
                    error += ((sim_val - val) ** 2) * 5.0 # High weight
            
            # Compare Biomass
            for _, row in obs_biomass.iterrows():
                d = pd.to_datetime(row['Date']).date()
                val = float(row['Value'])
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Wood_Biomass'] if crop_type == 'Perennial' else sim_row.iloc[0]['Biomass']
                    error += ((sim_val - val) ** 2)
            
            # Compare Nitrogen
            for _, row in obs_n.iterrows():
                d = pd.to_datetime(row['Date']).date()
                val = float(row['Value'])
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['N_kg'] / 4.0 
                    error += ((sim_val - val) ** 2)

            # Compare Disease Incidence
            for _, row in obs_disease.iterrows():
                d = pd.to_datetime(row['Date']).date()
                val_pct = float(row['Value']) # User inputs % (0-100)
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val_pct = sim_row.iloc[0]['Incidence'] * 100.0 # Model is 0-1
                    # Heavy weight on disease curve fitting
                    error += ((sim_val_pct - val_pct) ** 2) * 10.0

            return error

        # 4. Optimization
        result = minimize(objective, initial_guess, bounds=bounds, method='L-BFGS-B')
        
        # 5. Extract Final Params
        rue_mult, hi_mult, n_mult, beta_mult = result.x
        
        final_params = {
            'RUE_g_MJ': float(base_crop['RUE_g_MJ']) * rue_mult,
            'Harvest_Index': float(base_crop['Harvest_Index']) * hi_mult,
            'initial_nitrogen': config['initial_nitrogen'] * n_mult
        }
        
        if crop_type == 'Perennial':
             final_params['Per_Tree_Wood_Capacity_kg'] = float(base_crop.get('Per_Tree_Wood_Capacity_kg', 25.0)) * hi_mult
             
        if has_disease_data and base_beta > 0:
            final_params['Beta_Infection'] = base_beta * beta_mult

        msg_parts = [f"RUE x{rue_mult:.2f}", f"HI x{hi_mult:.2f}", f"N x{n_mult:.2f}"]
        if has_disease_data and base_beta > 0:
            msg_parts.append(f"Spread x{beta_mult:.2f}")

        msg = f"Calibration Complete. {' | '.join(msg_parts)}"
        return final_params, msg
