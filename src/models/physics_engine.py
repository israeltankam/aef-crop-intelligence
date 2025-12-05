# src/models/physics_engine.py
import numpy as np

class PhysicsEngine:
    @staticmethod
    def stics_lite_step(day_idx, weather_row, crop, soil_state, plant_state, mgmt_events):
        """
        Dual-Mode Physics Engine (Annual vs Perennial).
        Includes Pruning Logic reading from Crop parameters.
        """

        # --- INPUTS ---
        tmin, tmax = weather_row['TMIN'], weather_row['TMAX']
        rad_global = weather_row['RADIATION']
        rain = weather_row['RAIN']
        t_avg = (tmin + tmax) / 2.0

        # Update Chronological Age
        plant_state['age_days'] = plant_state.get('age_days', 0) + 1
        age_years = plant_state['age_days'] / 365.0

        # --- 0. MANAGEMENT EVENTS (PRUNING) ---
        curr_date = weather_row['DATE'].date()
        is_pruning_day = mgmt_events.get('pruning', False)
        
        # Track recovery
        if 'days_since_pruning' in plant_state:
            plant_state['days_since_pruning'] += 1
        
        if is_pruning_day:
            plant_state['days_since_pruning'] = 0
            # DYNAMIC LAI REDUCTION: Read from crop param, default to 0 if missing
            lai_removal_pct = float(crop.get('Pruning_LAI_Removal_Pct', 0.0))
            plant_state['lai'] = plant_state.get('lai', 0) * (1.0 - lai_removal_pct)
            
        # --- 1. PHENOLOGY ---
        is_perennial = crop['Type'] == 'Perennial'
        
        dTT = max(0.0, t_avg - crop.get('T_Base', crop['T_Base']))
        if 'T_Max' in crop and t_avg > crop['T_Max']:
            dTT = 0.0
        
        plant_state['cum_dd'] = plant_state.get('cum_dd', 0.0) + dTT
        
        if is_perennial:
            progress = 0.5 
        else:
            if 'Cycle_DD' in crop and crop['Cycle_DD'] > 0:
                progress = min(1.0, plant_state['cum_dd'] / float(crop['Cycle_DD']))
            else:
                progress = min(1.0, day_idx / float(max(1, crop['Cycle_Days'])))

        # --- 2. WATER BALANCE ---
        fc_mm = soil_state['field_capacity_mm']
        wp_mm = soil_state['wilting_point_mm']
        taw = max(1e-6, fc_mm - wp_mm)

        irr_amount = mgmt_events.get('irr', {}).get(curr_date, 0.0)

        soil_state['water_mm'] = soil_state.get('water_mm', fc_mm/2.0) + rain + irr_amount
        if soil_state['water_mm'] > fc_mm:
            soil_state['water_mm'] = fc_mm 
        
        ra_approx = rad_global / 0.75 
        et0 = 0.0023 * (t_avg + 17.8) * (max(0.1, (tmax - tmin)) ** 0.5) * ra_approx

        kc_ini, kc_mid, kc_end = 0.35, crop['Kc_Mid'], 0.6
        if is_perennial:
            if age_years < 2:
                kc = kc_ini + (kc_mid - kc_ini) * (age_years / 2.0)
            else:
                kc = kc_mid
        else:
            if progress < 0.15:
                kc = kc_ini
            elif progress < 0.45:
                kc = kc_ini + ((progress - 0.15) / 0.3) * (kc_mid - kc_ini)
            elif progress < 0.75:
                kc = kc_mid
            else:
                kc = kc_mid + ((progress - 0.75) / 0.25) * (kc_end - kc_mid)

        current_depletion = max(0.0, fc_mm - soil_state['water_mm'])
        p_factor = crop.get('p_factor', 0.5)
        raw = taw * p_factor
        if current_depletion <= raw:
            ks = 1.0
        else:
            buffer = taw - raw
            ks = max(0.0, (taw - current_depletion) / max(1e-6, buffer))

        eta = et0 * kc * ks
        soil_state['water_mm'] = max(wp_mm, soil_state['water_mm'] - eta)

        # --- 3. NUTRIENT BALANCE ---
        fert_n = mgmt_events.get('fert_n', {}).get(curr_date, 0.0)
        fert_p = mgmt_events.get('fert_p', {}).get(curr_date, 0.0)
        fert_k = mgmt_events.get('fert_k', {}).get(curr_date, 0.0)

        base_min_n = crop.get('base_min_n', 0.15)
        base_min_p = crop.get('base_min_p', 0.02)
        base_min_k = crop.get('base_min_k', 0.05)
        q10 = crop.get('min_q10', 2.0)
        temp_factor = q10 ** ((t_avg - 15.0) / 10.0)
        moisture_factor = np.clip((soil_state['water_mm'] - wp_mm) / max(1.0, taw), 0.0, 1.0)

        soil_state['n_kg'] = soil_state.get('n_kg', 0.0) + fert_n + (base_min_n * temp_factor * moisture_factor)
        soil_state['p_kg'] = soil_state.get('p_kg', 0.0) + fert_p + (base_min_p * temp_factor * moisture_factor)
        soil_state['k_kg'] = soil_state.get('k_kg', 0.0) + fert_k + (base_min_k * temp_factor * moisture_factor)

        root_depth = crop.get('Root_Depth_Max_m', 1.0)
        saturation_n = crop.get('sat_n_kg_ha', 50.0) * (root_depth / 0.3)
        saturation_p = crop.get('sat_p_kg_ha', 15.0) * (root_depth / 0.3)
        saturation_k = crop.get('sat_k_kg_ha', 40.0) * (root_depth / 0.3)

        n_fac = np.clip(soil_state['n_kg'] / max(1e-6, saturation_n), 0.0, 1.0)
        p_fac = np.clip(soil_state['p_kg'] / max(1e-6, saturation_p), 0.0, 1.0)
        k_fac = np.clip(soil_state['k_kg'] / max(1e-6, saturation_k), 0.0, 1.0)

        nutrient_stress = min(n_fac, p_fac, k_fac)

        # --- 4. BIOMASS & LAI ---
        prev_stunting = plant_state.get('stunting_factor', 1.0)
        stunting_decay = crop.get('stunting_memory_alpha', 0.02)
        current_stunting = prev_stunting * (1.0 - stunting_decay) + nutrient_stress * stunting_decay
        plant_state['stunting_factor'] = np.clip(current_stunting, 0.01, 1.0)

        max_lai = crop['Max_LAI']
        if is_perennial:
            baseline_lai = 2.0 if age_years > 3 else (age_years / 3.0) * 2.0
            seasonal_flux = 1.0 * np.sin(2 * np.pi * (weather_row['DATE'].dayofyear - 100) / 365)
            
            # Pruning recovery logic
            recovery_factor = 1.0
            if plant_state.get('days_since_pruning', 999) < 60:
                 # Reduced LAI slowly growing back
                 recovery_factor = 0.7 + (0.3 * (plant_state['days_since_pruning'] / 60.0))
            
            lai_pot = (baseline_lai + max(0, seasonal_flux)) * recovery_factor
            lai_pot = min(lai_pot, max_lai)
        else:
            if progress < 0.15:
                lai_pot = max_lai * (progress / 0.15) * 0.3
            elif progress < 0.5:
                lai_pot = 0.3 * max_lai + (max_lai * 0.7) * ((progress - 0.15) / 0.35)
            elif progress < 0.8:
                lai_pot = max_lai
            else:
                lai_pot = max_lai * (1.0 - (progress - 0.8) / 0.2)
        
        lai_pot = max(0.0, lai_pot)
        # Apply stunting
        lai = lai_pot * plant_state['stunting_factor']
        
        # If pruning happened TODAY, override the calculated LAI with the cut value (handled above)
        if is_pruning_day:
            lai = min(lai, plant_state['lai']) 
            
        plant_state['lai'] = lai

        par = rad_global * 0.5
        k_ext = 0.7
        f_ipar = (1.0 - np.exp(-k_ext * lai))
        
        rue_actual = crop['RUE_g_MJ'] * ks
        d_bio_g_m2 = rue_actual * par * f_ipar
        d_bio_t_ha = d_bio_g_m2 * 0.01
        
        d_bio_perfect_t_ha = (crop['RUE_g_MJ'] * par * (1.0 - np.exp(-k_ext * lai_pot))) * 0.01

        # --- 5. PARTITIONING ---
        d_wood_t_ha = 0.0
        d_fruit_t_ha = 0.0
        
        if is_perennial:
            if age_years < 2:
                partition_fruit = 0.1
            elif age_years < 4:
                partition_fruit = 0.4
            else:
                partition_fruit = 0.6
                
            # PRUNING BONUS: Boost efficiency/partitioning for 60 days
            if plant_state.get('days_since_pruning', 999) < 60:
                partition_fruit = min(0.9, partition_fruit * 1.2) 

            d_fruit_t_ha = d_bio_t_ha * partition_fruit
            d_wood_t_ha = d_bio_t_ha * (1 - partition_fruit)
            
            # PHYSICAL PRUNING REMOVAL
            if is_pruning_day:
                current_wood = plant_state.get('wood_biomass', 10.0) 
                # DYNAMIC BIOMASS REDUCTION: Read from crop param
                bio_removal_pct = float(crop.get('Pruning_Biomass_Removal_Pct', 0.0))
                removal = current_wood * bio_removal_pct
                d_wood_t_ha -= removal 
                
        else:
            pass

        # --- 6. UPTAKE ---
        n_demand = d_bio_t_ha * 1000.0 * 0.020
        p_demand = d_bio_t_ha * 1000.0 * 0.003
        k_demand = d_bio_t_ha * 1000.0 * 0.015

        actual_n = min(n_demand, soil_state['n_kg'])
        actual_p = min(p_demand, soil_state['p_kg'])
        actual_k = min(k_demand, soil_state['k_kg'])
        
        supply_ratio = 1.0
        if n_demand > 0: supply_ratio = min(supply_ratio, actual_n/n_demand)
        if p_demand > 0: supply_ratio = min(supply_ratio, actual_p/p_demand)
        if k_demand > 0: supply_ratio = min(supply_ratio, actual_k/k_demand)
        
        final_bio = d_bio_t_ha * supply_ratio
        
        # Don't scale the negative removal by supply ratio
        if d_wood_t_ha < 0:
            final_wood = d_wood_t_ha 
        else:
            final_wood = d_wood_t_ha * supply_ratio
            
        final_fruit = d_fruit_t_ha * supply_ratio

        soil_state['n_kg'] = max(0, soil_state['n_kg'] - actual_n)
        soil_state['p_kg'] = max(0, soil_state['p_kg'] - actual_p)
        soil_state['k_kg'] = max(0, soil_state['k_kg'] - actual_k)

        return {
            'd_biomass_t_ha': final_bio,
            'd_biomass_perfect_t_ha': d_bio_perfect_t_ha,
            'd_wood_t_ha': final_wood,
            'd_fruit_t_ha': final_fruit,
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
            'k_kg': soil_state['k_kg']
        }