#src/models/state_manager.py
import streamlit as st
import pandas as pd
import json
import os
from datetime import date, timedelta

class StateManager:
    """
    Centralized manager for Streamlit Session State.
    Handles initialization, persistence, and JSON serialization.
    """
    
    # Base defaults
    DEFAULTS = {
        'step': 1,
        'setup_complete': False,
        
        # --- Step 1: Field ---
        'field_name': 'My Field',
        'center_lat': 9.30,
        'center_lon': 13.40,
        'field_coords': [],
        'area_ha': 1.0,
        
        # --- Step 2: Crop ---
        'selected_crop_id': None,
        'planting_date': date.today(),
        'planting_density': 10000, 
        'sowing_depth': 5,
        
        # --- Step 3: Disease ---
        'selected_disease_id': None,
        'disease_spots': [],
        'detection_date': date.today(),
        'insect_pressure': 1.0, 
        
        # --- Step 4: Soil ---
        'soil_type': 'loam',
        'use_expert_soil': False,
        'initial_nitrogen': 70.0,
        'soil_layers': None, 
        'fert_schedule': None, 
        'irr_schedule': None   
    }

    @staticmethod
    def initialize():
        # 1. Primitives
        for key, value in StateManager.DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = value
        
        # 2. Complex State
        StateManager._initialize_complex_state()
        
        # 3. Knowledge Base (Crucial Fix: ensure DF exists even if 'step' is set)
        if 'df_diseases' not in st.session_state or 'df_crops' not in st.session_state:
            StateManager._ensure_knowledge_base()

    @staticmethod
    def _initialize_complex_state():
        if st.session_state['soil_layers'] is None:
            st.session_state['soil_layers'] = pd.DataFrame([{
                'depth_top': 0.0, 'depth_bottom': 1.5, 'texture': 'loam',
                'field_capacity': 0.27, 'wilting_point': 0.11 
            }])

        d1 = st.session_state['planting_date'] + timedelta(days=20)
        d2 = st.session_state['planting_date'] + timedelta(days=45)
        
        if st.session_state['fert_schedule'] is None:
            st.session_state['fert_schedule'] = pd.DataFrame({'date': [d1, d2], 'amount': [0.0, 0.0]})
            
        if st.session_state['irr_schedule'] is None:
            st.session_state['irr_schedule'] = pd.DataFrame({'date': [d1, d2], 'amount': [0.0, 0.0]})

    @staticmethod
    def _ensure_knowledge_base():
        """Generates the databases ONLY if they are missing."""
        if not os.path.exists("src/data"): os.makedirs("src/data")

        # --- 1. CROPS DB ---
        crops_path = "src/data/crops_db.csv"
        
        # Only write if file doesn't exist
        if not os.path.exists(crops_path):
            data = [
                ["C_CAS_01","Cassava","TME 419 (Improved)","Perennial",365,0,18.0,26.0,35.0,1.8,4.5,0.65,1.1,1.5,100,0.2, 10000],
                ["C_CAS_02","Cassava","Local White (Landrace)","Perennial",365,0,18.0,26.0,35.0,1.6,4.0,0.60,1.1,1.5,100,1.0, 10000],
                ["C_MAI_01","Maize","Pioneer P1197 (Hybrid)","Annual",120,1600,8.0,30.0,35.0,3.9,6.5,0.52,1.2,1.5,180,0.3, 60000],
                ["C_MAI_02","Maize","Local Open Pollinated","Annual",130,1700,8.0,30.0,36.0,3.2,5.0,0.40,1.15,1.1,160,0.9, 55000],
                ["C_COT_01","Cotton","DeltaPine (Bt)","Annual",150,2200,12.0,28.0,38.0,2.4,3.5,0.42,1.2,1.8,150,0.4, 80000],
                ["C_COT_02","Cotton","Conventional Local","Annual",160,2300,12.0,28.0,38.0,2.1,3.0,0.35,1.2,1.6,140,0.9, 70000],
                ["C_COC_01","Cocoa","Forastero (Amelonado)","Perennial",365,0,20.0,25.0,32.0,1.5,5.0,0.35,1.1,2.0,120,0.6, 1100],
                ["C_COC_02","Cocoa","Trinitario (Hybrid)","Perennial",365,0,20.0,25.0,32.0,1.6,5.5,0.38,1.1,2.0,130,0.4, 1100],
                ["C_WHT_01","Wheat","Winter Red (Intensive)","Annual",240,2000,0.0,20.0,30.0,2.8,6.0,0.48,1.15,1.5,150,0.4, 3000000],
                ["C_RIC_01","Rice","IR64 (Indica)","Annual",115,1500,10.0,30.0,38.0,2.2,6.0,0.50,1.2,0.8,120,0.5, 250000],
                ["C_SOY_01","Soybean","Roundup Ready","Annual",110,1400,10.0,28.0,35.0,1.8,4.5,0.38,1.1,1.2,50,0.3, 300000],
                ["C_COF_01","Coffee","Arabica (Typica)","Perennial",365,0,15.0,20.0,25.0,1.2,4.0,0.30,0.95,1.5,100,0.8, 1600],
                ["C_COF_02","Coffee","Robusta (Nganda)","Perennial",365,0,20.0,26.0,34.0,1.4,4.5,0.35,1.0,2.0,120,0.3, 1100]
            ]
            cols = ["Crop_ID","Crop_Name","Variety","Type","Cycle_Days","GDD_Maturity",
                    "T_Base","T_Opt","T_Max","RUE_g_MJ","Max_LAI","Harvest_Index","Kc_Mid",
                    "Root_Depth_Max_m","Critical_Soil_N_kg_ha","Resistance_Score", "Default_Density"]
            pd.DataFrame(data, columns=cols).to_csv(crops_path, index=False)
            
        st.session_state['df_crops'] = pd.read_csv(crops_path)

        # --- 2. DISEASES DB ---
        dis_path = "src/data/diseases_db.csv"
        
        # Only write if file doesn't exist. This prevents the PermissionError.
        if not os.path.exists(dis_path):
             # Fallback data if user hasn't pasted the CSV yet
            data = [
                 ["D_CAS_01","Cassava","Cassava Mosaic Disease (CMD)","Viral","Whitefly",28.0,60.0,0.12,50.0,0.60,"Rogue infected plants."]
            ]
            cols = ["Disease_ID","Target_Crop_Name","Disease_Name","Type","Vector_Type",
                    "Opt_Temp","Opt_Humidity","Beta_Infection","Dispersal_Sigma_m",
                    "Yield_Retained_Infected","Control_Methods"]
            pd.DataFrame(data, columns=cols).to_csv(dis_path, index=False)
            
        st.session_state['df_diseases'] = pd.read_csv(dis_path)

    @staticmethod
    def save_config_to_json():
        """Exports current configuration to a JSON string."""
        config = {
            'field_name': st.session_state['field_name'],
            'center_lat': st.session_state['center_lat'],
            'center_lon': st.session_state['center_lon'],
            'field_coords': st.session_state['field_coords'],
            'area_ha': st.session_state['area_ha'],
            
            'selected_crop_id': st.session_state['selected_crop_id'],
            'planting_date': str(st.session_state['planting_date']),
            'planting_density': st.session_state['planting_density'],
            'sowing_depth': st.session_state['sowing_depth'],
            
            'selected_disease_id': st.session_state['selected_disease_id'],
            'disease_spots': st.session_state['disease_spots'],
            'detection_date': str(st.session_state['detection_date']),
            'insect_pressure': st.session_state['insect_pressure'],
            
            'soil_type': st.session_state['soil_type'],
            'initial_nitrogen': st.session_state['initial_nitrogen'],
            'use_expert_soil': st.session_state['use_expert_soil'],
            
            'soil_layers': st.session_state['soil_layers'].to_dict('records') if st.session_state['soil_layers'] is not None else [],
            'fert_schedule': st.session_state['fert_schedule'].astype(str).to_dict('records') if st.session_state['fert_schedule'] is not None else [],
            'irr_schedule': st.session_state['irr_schedule'].astype(str).to_dict('records') if st.session_state['irr_schedule'] is not None else []
        }
        return json.dumps(config, indent=4)

    @staticmethod
    def load_config_from_json(json_file):
        """Loads configuration from a JSON file object."""
        try:
            data = json.load(json_file)
            
            st.session_state['field_coords'] = data.get('field_coords', [])
            st.session_state['center_lat'] = data.get('center_lat', 9.30)
            st.session_state['center_lon'] = data.get('center_lon', 13.40)
            st.session_state['area_ha'] = data.get('area_ha', 1.0)
            
            st.session_state['selected_crop_id'] = data.get('selected_crop_id')
            if data.get('planting_date'):
                st.session_state['planting_date'] = date.fromisoformat(data['planting_date'])
            st.session_state['planting_density'] = data.get('planting_density', 10000)
            st.session_state['sowing_depth'] = data.get('sowing_depth', 5)
            
            st.session_state['selected_disease_id'] = data.get('selected_disease_id')
            st.session_state['disease_spots'] = data.get('disease_spots', [])
            if data.get('detection_date'):
                st.session_state['detection_date'] = date.fromisoformat(data['detection_date'])
            st.session_state['insect_pressure'] = data.get('insect_pressure', 1.0)
            
            st.session_state['soil_type'] = data.get('soil_type', 'loam')
            st.session_state['initial_nitrogen'] = data.get('initial_nitrogen', 70.0)
            st.session_state['use_expert_soil'] = data.get('use_expert_soil', False)
            
            if data.get('soil_layers'):
                st.session_state['soil_layers'] = pd.DataFrame(data['soil_layers'])
            
            if data.get('fert_schedule'):
                df = pd.DataFrame(data['fert_schedule'])
                if not df.empty and 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date']).dt.date
                st.session_state['fert_schedule'] = df
                
            if data.get('irr_schedule'):
                df = pd.DataFrame(data['irr_schedule'])
                if not df.empty and 'date' in df.columns:
                    df['date'] = pd.to_datetime(df['date']).dt.date
                st.session_state['irr_schedule'] = df
                
            return True
        except Exception as e:
            st.error(f"Corrupt file: {e}")
            return False