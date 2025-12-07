# src/models/state_manager.py
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
        # CHANGE: Add default initial soil water (0.8 = 80% of Field Capacity)
        # This prevents the simulation from starting in a "Bone Dry" state if user ignores it.
        'initial_soil_water': 0.8,
        
        # Nutrients (mg/kg / ppm)
        'initial_nitrogen': 10.0,
        'initial_phosphorus': 20.0,
        'initial_potassium': 100.0,
        
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
        
        # 3. Knowledge Base
        # We ensure the DBs are loaded into session state.
        # If files don't exist, _ensure_knowledge_base will create them once.
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
            st.session_state['fert_schedule'] = pd.DataFrame({
                'date': [d1, d2], 
                'product': ["NPK 15-15-15 Compound", "Urea (Granular)"],
                'amount': [0.0, 0.0]
            })
            
        if st.session_state['irr_schedule'] is None:
            st.session_state['irr_schedule'] = pd.DataFrame({'date': [d1, d2], 'amount': [0.0, 0.0]})

    @staticmethod
    def _ensure_knowledge_base():
        if not os.path.exists("src/data"): os.makedirs("src/data")

        # --- 1. CROPS DB ---
        crops_path = "src/data/crops_db.csv"
        
        # UPDATED: Added Per_Tree_Wood_Capacity_kg, p_factor, end_of_early, end_of_mature
        if not os.path.exists(crops_path):
            data = [
                ["C_CAS_01","Cassava","TME 419 (Improved)","Annual",365,0,18,26,35,2.4,5,0.8,0.8,2,100,0.2,10000,150,40,0.0,0.0,0.0,0.50,0,0],
                ["C_CAS_02","Cassava","Local White (Landrace)","Annual",365,0,18,26,35,2,4.5,0.7,0.8,2,100,1,10000,150,40,0.0,0.0,0.0,0.50,0,0],
                ["C_MAI_01","Maize","Pioneer P1197 (Hybrid)","Annual",120,1600,8,30,35,3.9,6.5,0.52,1.2,1.5,180,0.3,60000,50,50,0.0,0.0,0.0,0.55,0,0],
                ["C_MAI_02","Maize","Local Open Pollinated","Annual",130,1700,8,30,36,3.2,5,0.4,1.15,1.1,160,0.9,55000,50,50,0.0,0.0,0.0,0.55,0,0],
                ["C_COT_01","Cotton","DeltaPine (Bt)","Annual",150,2200,12,28,38,1.7,3.5,0.35,1.15,1.8,150,0.4,80000,20,60,0.0,0.0,0.0,0.65,0,0],
                ["C_COT_02","Cotton","Conventional Local","Annual",160,2300,12,28,38,1.5,3,0.3,1.15,1.6,140,0.9,70000,20,60,0.0,0.0,0.0,0.65,0,0],
                ["C_COC_01","Cocoa","Forastero (Amelonado)","Perennial",365,0,20,25,32,1.5,5,0.15,1.1,2,120,0.6,1100,100,120,0.20,0.30,25.0,0.65,2,4],
                ["C_COC_02","Cocoa","Trinitario (Hybrid)","Perennial",365,0,20,25,32,1.6,5.5,0.18,1.1,2,130,0.4,1100,100,120,0.20,0.30,28.0,0.65,2,4],
                ["C_WHT_01","Wheat","Winter Red (Intensive)","Annual",240,2000,0,20,30,2.8,6,0.48,1.15,1.5,150,0.4,3000000,30,50,0.0,0.0,0.0,0.55,0,0],
                ["C_RIC_01","Rice","IR64 (Indica)","Annual",115,1500,10,30,38,2.2,6,0.5,1.2,0.8,120,0.5,250000,60,80,0.0,0.0,0.0,0.20,0,0],
                ["C_SOY_01","Soybean","Roundup Ready","Annual",110,1400,10,28,35,1.8,4.5,0.38,1.1,1.2,50,0.3,300000,40,40,0.0,0.0,0.0,0.50,0,0],
                ["C_COF_01","Coffee","Arabica (Typica)","Perennial",365,0,15,20,25,1.2,4,0.3,0.95,1.5,100,0.8,1600,40,120,0.15,0.25,15.0,0.60,2,4],
                ["C_COF_02","Coffee","Robusta (Nganda)","Perennial",365,0,20,26,34,1.4,4.5,0.35,1,2,120,0.3,1100,40,120,0.15,0.25,18.0,0.60,2,4]
            ]
            cols = ["Crop_ID","Crop_Name","Variety","Type","Cycle_Days","GDD_Maturity",
                    "T_Base","T_Opt","T_Max","RUE_g_MJ","Max_LAI","Harvest_Index","Kc_Mid",
                    "Root_Depth_Max_m","Critical_Soil_N_kg_ha","Resistance_Score", "Default_Density", 
                    "Harvest_Rain_Limit_mm", "Max_Irr_Event_mm", "Pruning_Biomass_Removal_Pct", 
                    "Pruning_LAI_Removal_Pct", "Per_Tree_Wood_Capacity_kg", "p_factor", 
                    "end_of_early_stage", "end_of_maturation_stage"] 
            pd.DataFrame(data, columns=cols).to_csv(crops_path, index=False)
            
        st.session_state['df_crops'] = pd.read_csv(crops_path)
        
        # UPDATED: Added Per_Tree_Wood_Capacity_kg (Last Column)
        if not os.path.exists(crops_path):
            data = [
                ["C_CAS_01","Cassava","TME 419 (Improved)","Annual",365,0,18,26,35,2.4,5,0.8,0.8,2,100,0.2,10000,150,40,0.0,0.0,0.0],
                ["C_CAS_02","Cassava","Local White (Landrace)","Annual",365,0,18,26,35,2,4.5,0.7,0.8,2,100,1,10000,150,40,0.0,0.0,0.0],
                ["C_MAI_01","Maize","Pioneer P1197 (Hybrid)","Annual",120,1600,8,30,35,3.9,6.5,0.52,1.2,1.5,180,0.3,60000,50,50,0.0,0.0,0.0],
                ["C_MAI_02","Maize","Local Open Pollinated","Annual",130,1700,8,30,36,3.2,5,0.4,1.15,1.1,160,0.9,55000,50,50,0.0,0.0,0.0],
                ["C_COT_01","Cotton","DeltaPine (Bt)","Annual",150,2200,12,28,38,1.7,3.5,0.35,1.15,1.8,150,0.4,80000,20,60,0.0,0.0,0.0],
                ["C_COT_02","Cotton","Conventional Local","Annual",160,2300,12,28,38,1.5,3,0.3,1.15,1.6,140,0.9,70000,20,60,0.0,0.0,0.0],
                ["C_COC_01","Cocoa","Forastero (Amelonado)","Perennial",365,0,20,25,32,1.5,5,0.15,1.1,2,120,0.6,1100,100,120,0.20,0.30,25.0],
                ["C_COC_02","Cocoa","Trinitario (Hybrid)","Perennial",365,0,20,25,32,1.6,5.5,0.18,1.1,2,130,0.4,1100,100,120,0.20,0.30,28.0],
                ["C_WHT_01","Wheat","Winter Red (Intensive)","Annual",240,2000,0,20,30,2.8,6,0.48,1.15,1.5,150,0.4,3000000,30,50,0.0,0.0,0.0],
                ["C_RIC_01","Rice","IR64 (Indica)","Annual",115,1500,10,30,38,2.2,6,0.5,1.2,0.8,120,0.5,250000,60,80,0.0,0.0,0.0],
                ["C_SOY_01","Soybean","Roundup Ready","Annual",110,1400,10,28,35,1.8,4.5,0.38,1.1,1.2,50,0.3,300000,40,40,0.0,0.0,0.0],
                ["C_COF_01","Coffee","Arabica (Typica)","Perennial",365,0,15,20,25,1.2,4,0.3,0.95,1.5,100,0.8,1600,40,120,0.15,0.25,15.0],
                ["C_COF_02","Coffee","Robusta (Nganda)","Perennial",365,0,20,26,34,1.4,4.5,0.35,1,2,120,0.3,1100,40,120,0.15,0.25,18.0]
            ]
            cols = ["Crop_ID","Crop_Name","Variety","Type","Cycle_Days","GDD_Maturity",
                    "T_Base","T_Opt","T_Max","RUE_g_MJ","Max_LAI","Harvest_Index","Kc_Mid",
                    "Root_Depth_Max_m","Critical_Soil_N_kg_ha","Resistance_Score", "Default_Density", 
                    "Harvest_Rain_Limit_mm", "Max_Irr_Event_mm", "Pruning_Biomass_Removal_Pct", 
                    "Pruning_LAI_Removal_Pct", "Per_Tree_Wood_Capacity_kg"] 
            pd.DataFrame(data, columns=cols).to_csv(crops_path, index=False)
            
        st.session_state['df_crops'] = pd.read_csv(crops_path)

        # --- 2. DISEASES DB ---
        dis_path = "src/data/diseases_db.csv"
        
        # UPDATED: Added Pruning_Hygiene_Factor and Daily_Recovery_Rate
        if not os.path.exists(dis_path):
            data = [
                ["D_CAS_01","Cassava","Cassava Mosaic Disease (CMD)","Viral","Whitefly",28.0,60.0,0.12,50.0,0.60,"**Immediate Action:** Rogue (uproot and burn) all symptomatic plants immediately to reduce inoculum.\n**Resistant Varieties:** Deploy TME 419, TME 204, or TMS-IBA varieties which show high field resistance.\n**Vector Control:** Monitor Bemisia tabaci populations; avoid planting new fields downwind of old infected fields.",0.2,0.000],
                ["D_CAS_02","Cassava","Cassava Brown Streak (CBSD)","Viral","Whitefly",26.0,70.0,0.15,40.0,0.10,"**Quarantine:** Strictly prohibit movement of cassava stems from infected zones (hotspots).\n**Sanitation:** Use only certified virus-free cuttings. Sterilize farm tools with bleach solution between plants.\n**Harvest:** Harvest early (at 9-10 months) to reduce severity of root necrosis.",0.2,0.000],
                ["D_CAS_03","Cassava","Cassava Anthracnose (CAD)","Fungal","Wind/Rain",25.0,85.0,0.06,100.0,0.75,"**Cultural:** Increase plant spacing to reduce canopy humidity. Weed frequently to reduce competition and micro-climate humidity.\n**Chemical:** Apply copper-based fungicides if cankers appear on young stems.\n**Nutritional:** Ensure adequate Potassium (K) fertilization to strengthen cell walls against fungal penetration.",1.5,0.010],
                ["D_CAS_04","Cassava","Cassava Bacterial Blight (CBB)","Bacterial","Rain/Splash",26.0,80.0,0.09,30.0,0.40,"**Sanitation:** Use clean planting material; do not take cuttings from infected fields.\n**Rotation:** Rotate field with maize or legumes for one season to break the bacterial cycle.\n**Pruning:** Prune infected leaves and burn them outside the field boundaries.",1.2,0.005],
                ["D_MAI_01","Maize","Maize Streak Virus (MSV)","Viral","Leafhopper",25.0,50.0,0.18,80.0,0.40,"**Seed Treatment:** Mandatory seed dressing with Imidacloprid or Thiamethoxam before planting to protect seedlings.\n**Weed Control:** Remove grassy weeds (alternative hosts) 2 weeks before planting.\n**Timing:** Plant early with the first rains to avoid peak Cicadulina leafhopper migration.",0.1,0.000],
                ["D_MAI_02","Maize","Northern Corn Leaf Blight","Fungal","Wind",20.0,90.0,0.07,200.0,0.65,"**Chemical:** Apply Azoxystrobin or Propiconazole at VT (tasseling) stage if lesions cover >5% of the ear leaf.\n**Rotation:** Rotate with non-grass crops (soybean, sunflower) for 2 years to break the fungal lifecycle.\n**Residue:** Plow down infected residue deep into soil to accelerate decomposition.",1.0,0.015],
                ["D_MAI_03","Maize","Gray Leaf Spot (GLS)","Fungal","Wind",25.0,95.0,0.06,150.0,0.70,"**Genetic:** Plant hybrids with rated resistance to GLS (e.g., P30Y87 series).\n**Fungicide:** Spray Pyraclostrobin at R1 stage if humidity remains >90% for 12+ hours.\n**Tillage:** Conventional tillage significantly reduces inoculum compared to no-till in high-risk zones.",1.0,0.015],
                ["D_MAI_04","Maize","Maize Lethal Necrosis (MLN)","Viral","Thrips/Beetles",24.0,60.0,0.16,60.0,0.05,"**Emergency:** If detected, destroy the entire crop in the affected patch immediately.\n**Vector:** Aggressively control thrips and beetles during the first 6 weeks.\n**Crop Break:** Implement a strictly maize-free window of at least 2 months between seasons.",0.0,0.000],
                ["D_MAI_05","Maize","Southern Corn Rust","Fungal","Wind",27.0,90.0,0.08,500.0,0.60,"**Scouting:** Monitor weekly during warm, humid weather. This rust spreads explosively.\n**Fungicide:** Apply Tebuconazole immediately if pustules are found on upper leaves.\n**Timing:** Early planting often escapes the peak spore load arriving from tropical zones.",1.0,0.020],
                ["D_COT_01","Cotton","Cotton Leaf Curl (CLCuD)","Viral","Whitefly",30.0,60.0,0.20,50.0,0.50,"**Varietal:** Use CLCuD-resistant cultivars (e.g., specific Bt hybrids validated for your region).\n**Sanitation:** Eradicate alternative hosts like Okra and Abutilon weeds near fields.\n**Chemical:** Systemic insecticides (Acetamiprid) for whitefly control during early vegetative stages.",0.5,0.000],
                ["D_COT_02","Cotton","Bacterial Blight","Bacterial","Rain/Wind",30.0,85.0,0.08,30.0,0.50,"**Seed Hygiene:** Use acid-delinted seed only to eliminate seed-borne bacteria.\n**Chemical:** Preventative Copper Oxychloride sprays at the 2-leaf stage if weather is wet.\n**Water:** Avoid overhead sprinkler irrigation; use furrow or drip to minimize leaf wetness duration.",1.1,0.008],
                ["D_COC_01","Cocoa","Black Pod (Phytophthora)","Fungal","Rain/Splash",24.0,95.0,0.09,20.0,0.20,"**Pruning:** Aggressive canopy pruning to allow 30% light penetration and air circulation.\n**Harvest:** Frequent harvest (weekly) of ripe pods. Remove and bury all black pods away from the plantation.\n**Chemical:** Copper Hydroxide sprays every 3 weeks during peak rains; switch to Metalaxyl for curative action.",2.0,0.015],
                ["D_COC_02","Cocoa","Swollen Shoot Virus (CSSV)","Viral","Mealybug",26.0,60.0,0.05,15.0,0.00,"**Eradication:** 'Cordon Sanitaire'—cut out infected trees plus a ring of contact trees (10m radius).\n**Barriers:** Plant barrier crops (Citrus, Oil Palm) to block mealybug movement between blocks.\n**Vector:** Treat attendant ants which farm the mealybugs using baits.",0.1,0.000],
                ["D_COC_03","Cocoa","Witches' Broom","Fungal","Wind",25.0,85.0,0.07,100.0,0.30,"**Phytosanitation:** Prune all 'broom' vegetative growths and burn them.\n**Genetic:** Graft resistant Scavina clones.\n**Fungicide:** Protect developing pods with copper sprays during the first 3 months of formation.",1.8,0.010],
                ["D_WHT_01","Wheat","Yellow Rust (Stripe Rust)","Fungal","Wind",15.0,90.0,0.10,800.0,0.60,"**Scouting:** Monitor weekly. Threshold: 1 stripe per m². Pathogen travels long distances via wind.\n**Fungicide:** Immediate application of Tebuconazole or Epoxiconazole upon detection.\n**Genetic:** Deploy 'Slow Rusting' adult plant resistance genes (e.g., Yr18) for durable protection.",1.0,0.025],
                ["D_WHT_02","Wheat","Septoria Tritici Blotch","Fungal","Wind/Rain",18.0,85.0,0.07,100.0,0.70,"**Timing:** Critical protection window is Leaf 2 and Flag Leaf emergence (GS 39).\n**Chemical:** Chlorothalonil (preventative) + Azole (curative) tank mix.\n**Cultural:** Avoid very early sowing which exposes seedlings to high septoria spore loads from residue.",1.0,0.020],
                ["D_WHT_03","Wheat","Fusarium Head Blight (FHB)","Fungal","Rain/Wind",25.0,85.0,0.06,150.0,0.50,"**Timing:** Fungicide application (Metconazole) must occur exactly at flowering (Feekes 10.5.1).\n**Rotation:** Do not plant wheat directly into corn residue.\n**Varietal:** Select varieties with moderate resistance (Fhb1 gene).",1.0,0.015],
                ["D_WHT_04","Wheat","Stem Rust (Ug99 Lineage)","Fungal","Wind",20.0,70.0,0.11,1000.0,0.10,"**Bio-security:** This is a critical quarantine pathogen. Report immediately to authorities.\n**Fungicide:** High-dose strobilurin/triazole mix required.\n**Genetic:** Only varieties with Sr31/Sr33 resistance genes remain effective.",1.0,0.020],
                ["D_RIC_01","Rice","Rice Blast (Magnaporthe)","Fungal","Wind",25.0,90.0,0.09,300.0,0.40,"**Nutrition:** Avoid excessive Nitrogen fertilization; split N applications into 3 doses.\n**Water:** Maintain flood depth; draining fields exacerbates blast severity.\n**Seed:** Treat seeds with Tricyclazole. Spray Isoprothiolane at panicle initiation if lesions appear.",1.0,0.020],
                ["D_RIC_02","Rice","Bacterial Leaf Blight","Bacterial","Rain/Wind",28.0,80.0,0.12,50.0,0.50,"**Nutrient:** Balance Nitrogen with Potash (K) and Zinc to harden leaves.\n**Water:** Drain field immediately if severe infection occurs to stop water-borne spread.\n**Biological:** Use Pseudomonas fluorescens based bio-control agents at seedling stage.",1.0,0.010],
                ["D_RIC_03","Rice","Rice Tungro Disease","Viral","Leafhopper",28.0,70.0,0.14,100.0,0.30,"**Sync Planting:** Ensure community-wide synchronous planting to break the vector cycle.\n**Vector:** Apply granular insecticides (Cartap) in the nursery box.\n**Fallow:** Plow down stubble immediately after harvest.",0.5,0.000],
                ["D_RIC_04","Rice","Sheath Blight","Fungal","Water/Contact",30.0,90.0,0.06,10.0,0.60,"**Spacing:** Plant less densely to lower humidity in the canopy.\n**Nutrition:** Avoid high N rates which produce lush, susceptible foliage.\n**Chemical:** Apply Azoxystrobin at booting stage if sclerotia are visible at water line.",1.2,0.015],
                ["D_SOY_01","Soybean","Asian Soybean Rust","Fungal","Wind",22.0,95.0,0.11,1500.0,0.25,"**Surveillance:** Monitor sentinel plots. This pathogen moves thousands of km by wind.\n**Chemical:** Prophylactic fungicide (Strobilurin) at flowering (R1) if rust is reported in the region.\n**Curative:** Triazole application within 5 days of infection detection.",1.0,0.025],
                ["D_SOY_02","Soybean","Soybean Mosaic Virus","Viral","Aphids",22.0,60.0,0.13,50.0,0.65,"**Seed:** Use only certified virus-free seed (primary source of infection).\n**Planting:** Plant early to establish canopy before aphid flights peak.\n**Weeds:** Control Desmodium and other legume weeds nearby.",0.3,0.000],
                ["D_SOY_03","Soybean","Frogeye Leaf Spot","Fungal","Wind",25.0,80.0,0.07,100.0,0.75,"**Residue:** Tillage reduces surface inoculum.\n**Chemical:** Foliar fungicides at R3 (pod set) stage provide best economic return.\n**Genetic:** Use varieties with the Rcs3 resistance gene.",1.0,0.020],
                ["D_COF_01","Coffee","Coffee Leaf Rust (Hemileia)","Fungal","Wind",22.0,80.0,0.05,50.0,0.50,"**Resistant Vars:** Renovate plantations with Catimor or Ruiru 11 varieties.\n**Chemical:** Copper sprays before the onset of rains (April/Oct) to coat leaves before spores land.\n**Nutrition:** High plant vigor reduces susceptibility; ensure adequate foliar nutrition.",1.5,0.015],
                ["D_COF_02","Coffee","Coffee Berry Disease","Fungal","Rain/Wind",18.0,95.0,0.06,30.0,0.30,"**Chemical:** Tank mix Copper + Chlorothalonil during berry expansion stage (4-6 weeks after flowering).\n**Canopy:** Open pruning to facilitate spray penetration to the berries and reduce humidity.",1.8,0.015],
                ["D_COF_03","Coffee","Coffee Bacterial Blight","Bacterial","Rain/Wind",22.0,90.0,0.09,40.0,0.40,"**Windbreaks:** Install windbreaks (e.g., Grevillea) to reduce wind-driven rain damage which facilitates entry.\n**Chemical:** Copper sprays help, but cultural control is key.\n**Pruning:** Prune affected branches 30cm below the lesion.",1.3,0.005]
            ]
            cols = ["Disease_ID","Target_Crop_Name","Disease_Name","Type","Vector_Type",
                    "Opt_Temp","Opt_Humidity","Beta_Infection","Dispersal_Sigma_m",
                    "Yield_Retained_Infected","Control_Methods","Pruning_Hygiene_Factor","Daily_Recovery_Rate"]
            pd.DataFrame(data, columns=cols).to_csv(dis_path, index=False)
            
        st.session_state['df_diseases'] = pd.read_csv(dis_path)

    @staticmethod
    def save_config_to_json():
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
            'initial_phosphorus': st.session_state.get('initial_phosphorus', 20.0),
            'initial_potassium': st.session_state.get('initial_potassium', 100.0),
            'use_expert_soil': st.session_state['use_expert_soil'],
            
            'soil_layers': st.session_state['soil_layers'].to_dict('records') if st.session_state['soil_layers'] is not None else [],
            'fert_schedule': st.session_state['fert_schedule'].astype(str).to_dict('records') if st.session_state['fert_schedule'] is not None else [],
            'irr_schedule': st.session_state['irr_schedule'].astype(str).to_dict('records') if st.session_state['irr_schedule'] is not None else []
        }
        return json.dumps(config, indent=4)

    @staticmethod
    def load_config_from_json(json_file):
        try:
            data = json.load(json_file)
            st.session_state['field_coords'] = data.get('field_coords', [])
            st.session_state['center_lat'] = data.get('center_lat', 9.30)
            st.session_state['center_lon'] = data.get('center_lon', 13.40)
            st.session_state['area_ha'] = data.get('area_ha', 1.0)
            
            st.session_state['selected_crop_id'] = data.get('selected_crop_id')
            if data.get('planting_date'): st.session_state['planting_date'] = date.fromisoformat(data['planting_date'])
            st.session_state['planting_density'] = data.get('planting_density', 10000)
            st.session_state['sowing_depth'] = data.get('sowing_depth', 5)
            
            st.session_state['selected_disease_id'] = data.get('selected_disease_id')
            st.session_state['disease_spots'] = data.get('disease_spots', [])
            if data.get('detection_date'): st.session_state['detection_date'] = date.fromisoformat(data['detection_date'])
            st.session_state['insect_pressure'] = data.get('insect_pressure', 1.0)
            
            st.session_state['soil_type'] = data.get('soil_type', 'loam')
            st.session_state['initial_nitrogen'] = data.get('initial_nitrogen', 10.0)
            st.session_state['initial_phosphorus'] = data.get('initial_phosphorus', 20.0)
            st.session_state['initial_potassium'] = data.get('initial_potassium', 100.0)
            st.session_state['use_expert_soil'] = data.get('use_expert_soil', False)
            
            if data.get('soil_layers'): st.session_state['soil_layers'] = pd.DataFrame(data['soil_layers'])
            if data.get('fert_schedule'):
                df = pd.DataFrame(data['fert_schedule'])
                if not df.empty and 'date' in df.columns: df['date'] = pd.to_datetime(df['date']).dt.date
                st.session_state['fert_schedule'] = df
            if data.get('irr_schedule'):
                df = pd.DataFrame(data['irr_schedule'])
                if not df.empty and 'date' in df.columns: df['date'] = pd.to_datetime(df['date']).dt.date
                st.session_state['irr_schedule'] = df
                
            return True
        except Exception as e:
            st.error(f"Corrupt file: {e}")
            return False