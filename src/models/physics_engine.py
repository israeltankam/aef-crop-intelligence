# src/models/physics_engine.py
import numpy as np

class PhysicsEngine:
    @staticmethod
    def stics_lite_step(day_idx, weather_row, crop, soil_state, plant_state, mgmt_events):
        """
        Revised lite step with:
         - explicit unit assumption: soil_state['n_kg'] is kg/ha (document and keep)
         - water stress affects RUE (instant)
         - nutrient stress affects canopy expansion (slow memory) and reduces realised growth
         - mineralization scaled with temperature (Q10) and moisture
         - phenology via cumulative degree-days if available (fallback to day fraction)
        """

        # --- INPUTS / UNITS ---
        # weather_row: keys TMIN, TMAX, RADIATION (MJ/m2/day), RAIN (mm), DATE
        # soil_state['n_kg'], 'p_kg', 'k_kg' are in kg/ha
        # soil_state['water_mm'] is mm in root zone
        # crop keys: RUE_g_MJ, Max_LAI, Kc_Mid, Root_Depth_Max_m (m), Cycle_DD (optional), Cycle_Days, T_Base, T_Max
        # plant_state persists: cum_dd, stunting_factor, lai (optional)
        tmin, tmax = weather_row['TMIN'], weather_row['TMAX']
        rad_global = weather_row['RADIATION']
        rain = weather_row['RAIN']
        t_avg = (tmin + tmax) / 2.0

        # --- 1. PHENOLOGY: prefer thermal time if crop provides Cycle_DD ---
        dTT = max(0.0, t_avg - crop.get('T_Base', crop['T_Base']))
        if 'T_Max' in crop and t_avg > crop['T_Max']:
            dTT = 0.0
        plant_state['cum_dd'] = plant_state.get('cum_dd', 0.0) + dTT
        if 'Cycle_DD' in crop and crop['Cycle_DD'] > 0:
            progress = min(1.0, plant_state['cum_dd'] / float(crop['Cycle_DD']))
        else:
            progress = min(1.0, day_idx / float(max(1, crop['Cycle_Days'])))

        # --- 2. SIMPLE WATER BALANCE & PET (fix ET0 bug) ---
        fc_mm = soil_state['field_capacity_mm']
        wp_mm = soil_state['wilting_point_mm']
        taw = max(1e-6, fc_mm - wp_mm)

        curr_date = weather_row['DATE'].date()
        irr_amount = mgmt_events.get('irr', {}).get(curr_date, 0.0)

        # add rainfall and irrigation; handle runoff/percolation as excess beyond FC
        soil_state['water_mm'] = soil_state.get('water_mm', fc_mm/2.0) + rain + irr_amount
        if soil_state['water_mm'] > fc_mm:
            # percolation = soil_state['water_mm'] - fc_mm
            # simple percolation (lost from root zone)
            soil_state['water_mm'] = fc_mm
        
        # Hargreaves ET0
        # Check if Ra is available, otherwise approximate
        ra_approx = rad_global / 0.75  # assume transmissivity ~0.75
        et0 = 0.0023 * (t_avg + 17.8) * (max(0.1, (tmax - tmin)) ** 0.5) * ra_approx  # mm/day approx

        # crop Kc curve (unchanged structure)
        kc_ini, kc_mid, kc_end = 0.35, crop['Kc_Mid'], 0.6
        if progress < 0.15:
            kc = kc_ini
        elif progress < 0.45:
            kc = kc_ini + ((progress - 0.15) / 0.3) * (kc_mid - kc_ini)
        elif progress < 0.75:
            kc = kc_mid
        else:
            kc = kc_mid + ((progress - 0.75) / 0.25) * (kc_end - kc_mid)

        # Water stress factor ks: same formulation but ensure bounded 0..1
        current_depletion = max(0.0, fc_mm - soil_state['water_mm'])
        p_factor = crop.get('p_factor', 0.5)  # allow crop override
        raw = taw * p_factor
        if current_depletion <= raw:
            ks = 1.0
        else:
            buffer = taw - raw
            ks = max(0.0, (taw - current_depletion) / max(1e-6, buffer))

        # actual evapotranspiration (mm/day)
        eta = et0 * kc * ks
        soil_state['water_mm'] = max(wp_mm, soil_state['water_mm'] - eta)

        # --- 3. NUTRIENT BALANCE with temperature/moisture-dependent mineralization ---
        fert_n = mgmt_events.get('fert_n', {}).get(curr_date, 0.0)
        fert_p = mgmt_events.get('fert_p', {}).get(curr_date, 0.0)
        fert_k = mgmt_events.get('fert_k', {}).get(curr_date, 0.0)

        # base mineralization rates (kg/ha/day) at Tref=15C for a typical soil
        base_min_n = crop.get('base_min_n', 0.15)
        base_min_p = crop.get('base_min_p', 0.02)
        base_min_k = crop.get('base_min_k', 0.05)
        # Q10 temperature sensitivity
        q10 = crop.get('min_q10', 2.0)
        temp_factor = q10 ** ((t_avg - 15.0) / 10.0)  # simple Q10
        moisture_factor = np.clip((soil_state['water_mm'] - wp_mm) / max(1.0, taw), 0.0, 1.0)

        mineralization_n = base_min_n * temp_factor * moisture_factor
        mineralization_p = base_min_p * temp_factor * moisture_factor
        mineralization_k = base_min_k * temp_factor * moisture_factor

        soil_state['n_kg'] = soil_state.get('n_kg', 0.0) + fert_n + mineralization_n
        soil_state['p_kg'] = soil_state.get('p_kg', 0.0) + fert_p + mineralization_p
        soil_state['k_kg'] = soil_state.get('k_kg', 0.0) + fert_k + mineralization_k

        # --- 4. SATURATION THRESHOLDS SCALED BY ROOT DEPTH (avoid single hardcoded value) ---
        root_depth = crop.get('Root_Depth_Max_m', 0.3)
        # base saturation values refer to a 0.3 m root zone by convention
        base_sat_n = crop.get('sat_n_kg_ha', 50.0)
        base_sat_p = crop.get('sat_p_kg_ha', 15.0)
        base_sat_k = crop.get('sat_k_kg_ha', 40.0)

        saturation_n = base_sat_n * (root_depth / 0.3)
        saturation_p = base_sat_p * (root_depth / 0.3)
        saturation_k = base_sat_k * (root_depth / 0.3)

        # nutrient "availability factor" (0..1) based on mass in root zone
        n_fac = np.clip(soil_state['n_kg'] / max(1e-6, saturation_n), 0.0, 1.0)
        p_fac = np.clip(soil_state['p_kg'] / max(1e-6, saturation_p), 0.0, 1.0)
        k_fac = np.clip(soil_state['k_kg'] / max(1e-6, saturation_k), 0.0, 1.0)

        nutrient_stress = min(n_fac, p_fac, k_fac)  # 1 = no nutrient limitation

        # --- 5. BIOMASS & LAI: separate water vs nutrient roles (avoid double-counting) ---
        # Water stress -> physiological reduction of RUE (instantaneous).
        # Nutrient stress -> slow structural limitation of canopy (stunting memory).
        # NOTE: we do NOT multiply both directly into RUE and LAI simultaneously (that would double-count).
        prev_stunting = plant_state.get('stunting_factor', 1.0)
        # slow memory: stunting decays slowly toward current nutrient_stress (use small weight)
        stunting_decay = crop.get('stunting_memory_alpha', 0.02)
        current_stunting = prev_stunting * (1.0 - stunting_decay) + nutrient_stress * stunting_decay
        plant_state['stunting_factor'] = np.clip(current_stunting, 0.01, 1.0)

        # Potential LAI curve (unchanged shape), then apply stunting (nutrient-driven)
        max_lai = crop['Max_LAI']
        if progress < 0.15:
            lai_pot = max_lai * (progress / 0.15) * 0.3
        elif progress < 0.5:
            lai_pot = 0.3 * max_lai + (max_lai * 0.7) * ((progress - 0.15) / 0.35)
        elif progress < 0.8:
            lai_pot = max_lai
        else:
            lai_pot = max_lai * (1.0 - (progress - 0.8) / 0.2)
        lai_pot = max(0.0, lai_pot)

        lai = lai_pot * plant_state['stunting_factor']
        plant_state['lai'] = lai

        # Light interception
        par = rad_global * 0.5
        k_ext = 0.7
        f_ipar = (1.0 - np.exp(-k_ext * lai))

        # RUE: scale only with water physiological stress (ks), not nutrient_stress again
        rue_actual = crop['RUE_g_MJ'] * ks
        d_bio_g_m2 = rue_actual * par * f_ipar
        d_bio_perfect_g_m2 = crop['RUE_g_MJ'] * par * (1.0 - np.exp(-k_ext * lai_pot))

        # convert g/m2 to t/ha
        d_bio_t_ha = d_bio_g_m2 * 0.01
        d_bio_perfect_t_ha = d_bio_perfect_g_m2 * 0.01

        # --- 6. NUTRIENT DEMAND / UPTAKE and coupling to realised growth ---
        # demand per kg N/P/K per kg biomass produced (using same coefficients)
        n_demand = d_bio_t_ha * 1000.0 * 0.020
        p_demand = d_bio_t_ha * 1000.0 * 0.003
        k_demand = d_bio_t_ha * 1000.0 * 0.015

        actual_n_uptake = min(n_demand, soil_state['n_kg'])
        actual_p_uptake = min(p_demand, soil_state['p_kg'])
        actual_k_uptake = min(k_demand, soil_state['k_kg'])

        # compute limiting supply ratio (0..1)
        def safe_ratio(actual, demand):
            return 1.0 if demand <= 0.0 else np.clip(actual / float(demand), 0.0, 1.0)

        n_ratio = safe_ratio(actual_n_uptake, n_demand)
        p_ratio = safe_ratio(actual_p_uptake, p_demand)
        k_ratio = safe_ratio(actual_k_uptake, k_demand)
        nutrient_supply_ratio = min(n_ratio, p_ratio, k_ratio)

        # If supply ratio < 1, reduce realised biomass accordingly and consume only what was actually taken
        realised_d_bio_t_ha = d_bio_t_ha * nutrient_supply_ratio

        # subtract uptake from soil pools (use actual uptake amounts)
        soil_state['n_kg'] = max(0.0, soil_state['n_kg'] - actual_n_uptake)
        soil_state['p_kg'] = max(0.0, soil_state['p_kg'] - actual_p_uptake)
        soil_state['k_kg'] = max(0.0, soil_state['k_kg'] - actual_k_uptake)

        return {
            'd_biomass_t_ha': realised_d_bio_t_ha,
            'd_biomass_perfect_t_ha': d_bio_perfect_t_ha,
            'sw_fac': ks,
            'n_fac': n_fac,
            'p_fac': p_fac,
            'k_fac': k_fac,
            'lai': lai,
            'eta': eta,
            'et0': et0,
            'kc': kc,
            'swc': soil_state['water_mm'],
            'n_kg': soil_state['n_kg'],
            'p_kg': soil_state['p_kg'],
            'k_kg': soil_state['k_kg'],
            'nutrient_supply_ratio': nutrient_supply_ratio
        }