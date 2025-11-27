# src/models/physics_engine.py
import numpy as np

class PhysicsEngine:
    @staticmethod
    def stics_lite_step(day_idx, weather_row, crop, soil_state, mgmt_events):
        """
        Calculates daily biomass growth and stress (FAO-56 Water + NPK Nutrient Limited).
        """
        tmin, tmax = weather_row['TMIN'], weather_row['TMAX']
        rad = weather_row['RADIATION']
        rain = weather_row['RAIN']
        t_avg = (tmin + tmax) / 2
        
        # 1. Thermal Time
        dTT = max(0, t_avg - crop['T_Base'])
        if t_avg > crop['T_Max']: dTT = 0 
        
        # 2. Reference ET
        et0 = 0.0023 * (t_avg + 17.8) * ((tmax - tmin)**0.5) * rad
        
        # 3. Dynamic Kc
        cycle = crop['Cycle_Days']
        progress = day_idx / cycle
        
        kc_ini = 0.35
        kc_mid = crop['Kc_Mid']
        kc_end = 0.6
        
        if progress < 0.15: kc = kc_ini
        elif progress < 0.45: kc = kc_ini + ((progress - 0.15) / 0.3) * (kc_mid - kc_ini)
        elif progress < 0.75: kc = kc_mid
        else: kc = kc_mid + ((progress - 0.75) / 0.25) * (kc_end - kc_mid)
            
        # 4. Water Balance
        curr_date = weather_row['DATE'].date()
        irr_amount = mgmt_events['irr'].get(curr_date, 0.0)
        
        # Fertilizer Input (NPK)
        fert_n = mgmt_events['fert_n'].get(curr_date, 0.0)
        fert_p = mgmt_events['fert_p'].get(curr_date, 0.0)
        fert_k = mgmt_events['fert_k'].get(curr_date, 0.0)
        
        soil_state['water_mm'] += (rain + irr_amount)
        soil_state['n_kg'] += fert_n
        soil_state['p_kg'] += fert_p
        soil_state['k_kg'] += fert_k
        
        fc_mm = soil_state['field_capacity_mm'] 
        wp_mm = soil_state['wilting_point_mm']
        taw = fc_mm - wp_mm
        
        p_factor = 0.5 
        raw = taw * p_factor
        current_depletion = fc_mm - soil_state['water_mm']
        
        # Water Stress Factor (Ks)
        ks = 1.0
        if current_depletion > raw:
            buffer_zone = (taw - raw)
            if buffer_zone > 0:
                ks = max(0, (taw - current_depletion) / buffer_zone)
            else:
                ks = 0
        
        eta = et0 * kc * ks
        soil_state['water_mm'] = max(wp_mm, soil_state['water_mm'] - eta)
        if soil_state['water_mm'] > fc_mm:
            soil_state['water_mm'] = fc_mm
            
        # 5. Nutrient Stress (NPK - Liebig's Law)
        # Thresholds (Simplified for Lite model)
        # Nitrogen: Critical ~ 20 kg/ha available
        n_fac = min(1.0, soil_state['n_kg'] / 20.0)
        
        # Phosphorus: Critical ~ 10 kg/ha available (P is less mobile/abundant usually)
        p_fac = min(1.0, soil_state['p_kg'] / 10.0)
        
        # Potassium: Critical ~ 15 kg/ha available
        k_fac = min(1.0, soil_state['k_kg'] / 15.0)
        
        # Liebig's Law of the Minimum
        nutrient_stress_index = min(n_fac, p_fac, k_fac)
            
        # 6. Biomass
        lai = 0
        if progress < 0.15: lai = 0.5
        elif progress < 0.5: lai = crop['Max_LAI'] * (progress/0.5)
        elif progress < 0.8: lai = crop['Max_LAI']
        else: lai = crop['Max_LAI'] * (1 - (progress-0.8)*5)
        
        ipar = rad * (1 - np.exp(-0.7 * lai))
        
        # Combined Stress: Water * Nutrients
        d_bio_g_m2 = crop['RUE_g_MJ'] * ipar * ks * nutrient_stress_index
        
        # 7. Nutrient Uptake (Depletion)
        # N: ~2.5% of biomass, P: ~0.4%, K: ~2.0%
        n_demand = d_bio_g_m2 * 0.025
        p_demand = d_bio_g_m2 * 0.004
        k_demand = d_bio_g_m2 * 0.020
        
        soil_state['n_kg'] = max(0, soil_state['n_kg'] - n_demand)
        soil_state['p_kg'] = max(0, soil_state['p_kg'] - p_demand)
        soil_state['k_kg'] = max(0, soil_state['k_kg'] - k_demand)
        
        return {
            'd_biomass_t_ha': d_bio_g_m2 * 0.01, 
            'sw_fac': ks,
            'n_fac': n_fac,
            'p_fac': p_fac,
            'k_fac': k_fac,
            'lai': lai,
            'eta': eta,
            'et0': et0,
            'kc': kc,
            'swc': soil_state['water_mm'],
            'depletion': current_depletion,
            'raw': raw,
            'n_kg': soil_state['n_kg'],
            'p_kg': soil_state['p_kg'],
            'k_kg': soil_state['k_kg']
        }