# src/models/calibration_engine.py

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, minimize
from src.models.simulation_engine import SimulationEngine
import streamlit as st

class CalibrationEngine:
    def __init__(self):
        self.sim_engine = SimulationEngine()

    def calibrate_model(self, surveillance_data, config, crop_type='Annual'):
        """
        Bayesian-style Calibration Engine.
        Uses Differential Evolution (Global Search) + L-BFGS-B (Local Polish).
        Calculates Parameter Uncertainty (Hessian Inverse).
        """
        # 1. Parse & Validate Data
        df = pd.DataFrame(surveillance_data)
        if df.empty: return None, "No observational data found."

        # Segregate Data Streams
        obs_yield = df[df['Type'] == 'Yield (t/ha)']
        obs_biomass = df[df['Type'] == 'Biomass (t/ha)']
        obs_n = df[df['Type'] == 'Soil N (mg/kg)']
        obs_disease = df[df['Type'] == 'Disease Incidence (%)']
        
        # Check sufficiency
        total_points = len(obs_yield) + len(obs_biomass) + len(obs_n) + len(obs_disease)
        if total_points == 0:
            return None, "No valid calibration targets found."

        # 2. Setup Priors & Sigmas (Assumed Noise)
        # We use Inverse Variance Weighting: Cost ~ (Sim - Obs)^2 / (2 * Sigma^2)
        # Sigma represents our "trust" in the measurement accuracy.
        SIGMA_YIELD = 0.5   # +/- 0.5 t/ha uncertainty
        SIGMA_BIO = 1.0     # +/- 1.0 t/ha uncertainty
        SIGMA_N = 5.0       # +/- 5.0 mg/kg uncertainty
        SIGMA_DIS = 5.0     # +/- 5% incidence uncertainty
        
        # Regularization Strength (Lambda)
        # Penalizes deviation from the biological default (1.0).
        # Helps prevent overfitting when data is sparse.
        LAMBDA_REG = 0.5 if total_points < 5 else 0.1

        # 3. Define Parameter Space
        df_c = st.session_state['df_crops']
        base_crop = df_c[df_c['Crop_ID'] == config['selected_crop_id']].iloc[0]
        
        has_disease_data = not obs_disease.empty
        base_beta = 0.0
        if config['selected_disease_id']:
            df_d = st.session_state['df_diseases']
            dis_row = df_d[df_d['Disease_ID'] == config['selected_disease_id']]
            if not dis_row.empty:
                base_beta = float(dis_row.iloc[0]['Beta_Infection'])

        # Multipliers: [RUE, HI, N_init, Beta]
        # Bounds allow for wider exploration than before
        bounds = [(0.4, 1.8), (0.4, 1.6), (0.1, 3.0)]
        if has_disease_data and base_beta > 0:
            bounds.append((0.1, 8.0)) # Allow wider range for disease spread
        else:
            bounds.append((1.0, 1.0)) # Lock if no data

        # 4. Objective Function (Negative Log Posterior)
        def objective(params):
            rue_mult, hi_mult, n_mult, beta_mult = params
            
            # A. Prior Penalty (Regularization) -> Keeps params near 1.0
            # J_prior = sum((param - 1.0)^2)
            j_prior = np.sum((np.array(params) - 1.0)**2) * LAMBDA_REG

            # B. Simulation
            temp_config = config.copy()
            temp_config['calibrated_params'] = {
                'RUE_g_MJ': float(base_crop['RUE_g_MJ']) * rue_mult,
                'Harvest_Index': float(base_crop['Harvest_Index']) * hi_mult,
                'initial_nitrogen': config['initial_nitrogen'] * n_mult
            }
            if has_disease_data and base_beta > 0:
                 temp_config['calibrated_params']['Beta_Infection'] = base_beta * beta_mult
            
            # Special Handling for Perennials
            if crop_type == 'Perennial':
                 temp_config['calibrated_params']['Per_Tree_Wood_Capacity_kg'] = float(base_crop.get('Per_Tree_Wood_Capacity_kg', 25.0)) * hi_mult

            res = self.sim_engine.run_simulation(temp_config)
            if res is None: return 1e9
            
            hist = pd.DataFrame(res['history'])
            hist['Date'] = pd.to_datetime(hist['Date']).dt.date
            
            # C. Likelihood (Data Fit)
            j_lik = 0.0
            
            # Yield
            for _, row in obs_yield.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Yield'] if crop_type == 'Annual' else sim_row.iloc[0]['Fruit_Biomass']
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * SIGMA_YIELD**2)

            # Biomass
            for _, row in obs_biomass.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Wood_Biomass'] if crop_type == 'Perennial' else sim_row.iloc[0]['Biomass']
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * SIGMA_BIO**2)

            # Nitrogen
            for _, row in obs_n.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['N_kg'] / 4.0 
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * SIGMA_N**2)

            # Disease
            for _, row in obs_disease.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Incidence'] * 100.0
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * SIGMA_DIS**2)

            return j_lik + j_prior

        # 5. Global Optimization (Differential Evolution)
        # Robust against local minima
        result_global = differential_evolution(
            objective, 
            bounds, 
            strategy='best1bin', 
            maxiter=20, 
            popsize=10, 
            tol=0.01,
            seed=42
        )

        # 6. Local Polish & Uncertainty Estimation (Hessian)
        # We run BFGS starting from the global optimum to get the Inverse Hessian
        result_local = minimize(
            objective, 
            result_global.x, 
            method='L-BFGS-B', 
            bounds=bounds
        )

        # 7. Extract Results & Confidence
        best_params = result_local.x
        
        # Approximate Standard Errors from Hessian (if available)
        # Hessian ~ 1 / Variance
        uncertainties = [0.0] * 4
        try:
            # L-BFGS-B approximates Hessian; dense Hessian usually returned by 'BFGS' but we used bounds.
            # We estimate uncertainty heuristically based on objective curvature if Hessian is unavailable.
            # Ideally we would use numdifftools, but for now we assume 10% if calc fails.
            if hasattr(result_local, 'hess_inv'):
                cov = result_local.hess_inv.todense() if hasattr(result_local.hess_inv, 'todense') else result_local.hess_inv
                uncertainties = np.sqrt(np.diag(cov))
        except:
            uncertainties = [0.1] * 4 # Fallback

        # Map back to physical values
        final_dict = {
            'RUE_g_MJ': float(base_crop['RUE_g_MJ']) * best_params[0],
            'Harvest_Index': float(base_crop['Harvest_Index']) * best_params[1],
            'initial_nitrogen': config['initial_nitrogen'] * best_params[2],
            # Meta-data for UI
            'uncertainty': {
                'RUE_mult_std': float(uncertainties[0]),
                'HI_mult_std': float(uncertainties[1]),
                'N_mult_std': float(uncertainties[2])
            }
        }
        
        if crop_type == 'Perennial':
             final_dict['Per_Tree_Wood_Capacity_kg'] = float(base_crop.get('Per_Tree_Wood_Capacity_kg', 25.0)) * best_params[1]

        if has_disease_data and base_beta > 0:
            final_dict['Beta_Infection'] = base_beta * best_params[3]
            final_dict['uncertainty']['Beta_std'] = float(uncertainties[3])

        # Formatting Output Message
        msg = f"Calibration Converged (Cost: {result_local.fun:.2f}). "
        msg += f"RUE: x{best_params[0]:.2f} (±{uncertainties[0]:.2f}), "
        msg += f"HI: x{best_params[1]:.2f}"

        return final_dict, msg