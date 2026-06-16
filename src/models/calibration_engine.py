# src/models/calibration_engine.py

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution, minimize
from src.models.simulation_engine import SimulationEngine
import streamlit as st

class CalibrationEngine:
    def __init__(self):
        self.sim_engine = SimulationEngine()


    def _normalize_observations(self, surveillance_data):
        """Convert all surveillance log shapes into calibration-ready rows.

        The single-field page historically stores observations as rows with
        Date/Type/Value.  The cooperative workflow stores richer entries with
        scope, plot_id and typed fields such as incidence_pct or soil_n.  Keeping
        this normalizer inside the calibration engine prevents every UI page from
        duplicating conversion logic and makes the adaptive loop tolerant of old
        saved projects, edited tables and cooperative plot observations.
        """
        normalized = []

        def add_row(date_value, obs_type, value, source=None):
            if date_value is None or value is None:
                return
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return
            confidence = 1.0
            if isinstance(source, dict):
                try:
                    confidence = float(source.get('confidence', 1.0))
                except (TypeError, ValueError):
                    confidence = 1.0
                if not np.isfinite(confidence):
                    confidence = 1.0
            normalized.append({
                'Date': str(date_value),
                'Type': obs_type,
                'Value': numeric_value,
                'confidence': confidence,
                'mode': source.get('mode') if isinstance(source, dict) else None,
                'scope': source.get('scope') if isinstance(source, dict) else None,
                'plot_id': source.get('plot_id') if isinstance(source, dict) else None,
            })

        def visit(item):
            if item is None:
                return
            if isinstance(item, list):
                for child in item:
                    visit(child)
                return
            if not isinstance(item, dict):
                return

            # Existing single-field table format.
            if {'Date', 'Type', 'Value'}.issubset(item.keys()):
                add_row(item.get('Date'), item.get('Type'), item.get('Value'), item)
                return

            # Cooperative and future API formats may use lowercase date keys and
            # explicit value fields.  We flatten each observed signal into its own
            # likelihood contribution while preserving confidence and plot scope.
            obs_date = item.get('date') or item.get('Date')
            if 'incidence_pct' in item:
                add_row(obs_date, 'Disease Incidence (%)', item.get('incidence_pct'), item)
            if 'soil_n' in item:
                add_row(obs_date, 'Soil N (mg/kg)', item.get('soil_n'), item)
            if 'soil_p' in item:
                add_row(obs_date, 'Soil P (ppm)', item.get('soil_p'), item)
            if 'soil_k' in item:
                add_row(obs_date, 'Soil K (ppm)', item.get('soil_k'), item)
            if 'yield_t_ha' in item:
                add_row(obs_date, 'Yield (t/ha)', item.get('yield_t_ha'), item)
            if 'biomass_t_ha' in item:
                add_row(obs_date, 'Biomass (t/ha)', item.get('biomass_t_ha'), item)
            if isinstance(item.get('observations'), list):
                visit(item.get('observations'))

        visit(surveillance_data)
        return normalized

    def _observation_sigma(self, base_sigma, row):
        """Inflate observation noise when a field measurement is less reliable.

        A farmer-estimated cooperative-wide observation should not pull the model
        as strongly as a measured plot-level value.  Confidence therefore changes
        likelihood weight through sigma instead of being ignored.
        """
        try:
            confidence = float(row.get('confidence', 1.0))
        except Exception:
            confidence = 1.0
        if not np.isfinite(confidence):
            confidence = 1.0
        confidence = float(np.clip(confidence, 0.2, 1.0))
        scope_penalty = 1.20 if row.get('scope') == 'cooperative' else 1.0
        return float(base_sigma) * scope_penalty / confidence

    def calibrate_model(self, surveillance_data, config, crop_type='Annual'):
        """
        Bayesian-style Calibration Engine.
        Uses Differential Evolution (Global Search) + L-BFGS-B (Local Polish).
        Calculates Parameter Uncertainty (Hessian Inverse).
        """
        # 1. Parse & Validate Data
        df = pd.DataFrame(self._normalize_observations(surveillance_data))
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
                    sigma = self._observation_sigma(SIGMA_YIELD, row)
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * sigma**2)

            # Biomass
            for _, row in obs_biomass.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Wood_Biomass'] if crop_type == 'Perennial' else sim_row.iloc[0]['Biomass']
                    sigma = self._observation_sigma(SIGMA_BIO, row)
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * sigma**2)

            # Nitrogen
            for _, row in obs_n.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['N_kg'] / 4.0 
                    sigma = self._observation_sigma(SIGMA_N, row)
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * sigma**2)

            # Disease
            for _, row in obs_disease.iterrows():
                d = pd.to_datetime(row['Date']).date()
                sim_row = hist[hist['Date'] == d]
                if not sim_row.empty:
                    sim_val = sim_row.iloc[0]['Incidence'] * 100.0
                    sigma = self._observation_sigma(SIGMA_DIS, row)
                    j_lik += ((sim_val - float(row['Value'])) ** 2) / (2 * sigma**2)

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
        uncertainty_floor = np.array([0.08, 0.08, 0.10, 0.20])
        uncertainties = uncertainty_floor.copy()
        try:
            # L-BFGS-B approximates Hessian; dense Hessian usually returned by 'BFGS' but we used bounds.
            # We estimate uncertainty heuristically based on objective curvature if Hessian is unavailable.
            # Ideally we would use numdifftools, but for now we assume 10% if calc fails.
            if hasattr(result_local, 'hess_inv'):
                cov = result_local.hess_inv.todense() if hasattr(result_local.hess_inv, 'todense') else result_local.hess_inv
                uncertainties = np.maximum(np.nan_to_num(np.sqrt(np.diag(cov)), nan=0.0, posinf=1.0, neginf=0.0), uncertainty_floor[:len(np.diag(cov))])
        except:
            uncertainties = uncertainty_floor.copy() # Conservative fallback; never report zero uncertainty.

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