# src/models/state_manager.py
import json
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from src.models.economic_engine import default_economics_config, normalize_economics_config


class StateManager:
    """
    Centralized manager for Streamlit session state.

    The field geometry, soil provenance and adaptive calibration metadata are
    persisted here so the dashboard, report generator and rollback workflow all
    work from the same configuration object.
    """

    DEFAULTS = {
        # Global operating mode. None keeps the user on the first-run mode selector.
        'app_mode': None,
        'app_mode_locked': False,
        'interface_level': 'guided',

        # Step 1: field geography.
        'step': 1,
        'setup_complete': False,
        'field_name': 'My Field',
        'center_lat': 9.30,
        'center_lon': 13.40,
        'field_coords': [],
        'area_ha': 1.0,
        'field_design_metadata': {},
        'place_search_results': [],

        # Cooperative mode keeps one perimeter and many small editable parcels.
        'cooperative_name': 'My Cooperative',
        'cooperative_perimeter_coords': [],
        'cooperative_parcels': [],
        'cooperative_perimeter_area_ha': 100.0,
        'cooperative_target_parcel_area_ha': 1.5,
        'cooperative_crop_mode': 'shared',
        'cooperative_management_mode': 'per_parcel',
        'cooperative_detection_confidence': 0.0,
        'cooperative_detection_notes': '',
        'focused_cooperative_plot_id': None,
        'cooperative_report_water_limit_m3': 0.0,
        'cooperative_report_fertilizer_limit_kg': 0.0,
        'cooperative_report_labour_days': 0.0,
        'report_detail_level': 'balanced',

        # Step 2: crop system.
        'selected_crop_id': None,
        'planting_date': date.today(),
        'planting_density': 10000,
        'sowing_depth': 5,
        'initial_plant_age_years': 0.0,
        'history_years': 0,
        # Perennial context is optional but important: it lets reports explain
        # age, pruning and low-pressure seasons instead of assuming a new stand.
        'perennial_last_pruning_date': None,
        'perennial_next_pruning_date': None,
        'perennial_dormancy_start_month': 0,
        'perennial_dormancy_end_month': 0,
        'perennial_historical_yield_t_ha': 0.0,

        # Step 3: disease surveillance.
        'selected_disease_id': None,
        'disease_spots': [],
        'detection_date': date.today(),
        'insect_pressure': 1.0,
        'satellite_anomaly_date': None,

        # Step 4: soil and management.
        'soil_type': 'loam',
        'use_expert_soil': False,
        'initial_soil_water': 0.8,
        'soil_data_source': 'manual',
        'soil_confidence': 1.0,
        'soil_detection_notes': '',
        'initial_nitrogen': 10.0,
        'initial_phosphorus': 20.0,
        'initial_potassium': 100.0,
        'soil_layers': None,
        'fert_schedule': None,
        'irr_schedule': None,
        'water_source_type': 'unknown',
        'available_water_m3_day': 0.0,
        'irrigation_efficiency': 0.70,
        'irrigation_method': 'unspecified',
        'fertilizer_budget_per_ha': 0.0,
        'fertilizer_availability_note': '',

        # Step 5: economic assumptions.  Kept as one nested dictionary so users
        # can export/import a reusable economics profile without scattering
        # prices across unrelated session keys.
        'economics_config': default_economics_config(),
        'economic_horizon_years': 20,

        # Adaptive surveillance.
        'surveillance_logs': [],
        'calibrated_params': {},
    }

    @staticmethod
    def initialize():
        for key, value in StateManager.DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = value

        StateManager._initialize_complex_state()

        if 'df_diseases' not in st.session_state or 'df_crops' not in st.session_state:
            StateManager._ensure_knowledge_base()

    @staticmethod
    def _initialize_complex_state():
        if st.session_state['soil_layers'] is None:
            st.session_state['soil_layers'] = pd.DataFrame([{
                'depth_top': 0.0,
                'depth_bottom': 1.5,
                'texture': 'loam',
                'field_capacity': 0.27,
                'wilting_point': 0.11,
            }])

        d1 = st.session_state['planting_date'] + timedelta(days=20)
        d2 = st.session_state['planting_date'] + timedelta(days=45)

        if st.session_state['fert_schedule'] is None:
            st.session_state['fert_schedule'] = pd.DataFrame({
                'date': [d1, d2],
                'product': ['NPK 15-15-15 Compound', 'Urea (Granular)'],
                'amount': [0.0, 0.0],
            })

        if st.session_state['irr_schedule'] is None:
            st.session_state['irr_schedule'] = pd.DataFrame({
                'date': [d1, d2],
                'amount': [0.0, 0.0],
            })

    @staticmethod
    def _ensure_knowledge_base():
        """Load reviewed crop and disease CSV files as the source of truth."""
        if not os.path.exists('src/data'):
            os.makedirs('src/data')

        crops_path = 'src/data/crops_db.csv'
        diseases_path = 'src/data/diseases_db.csv'
        missing = [p for p in (crops_path, diseases_path) if not os.path.exists(p)]
        if missing:
            raise FileNotFoundError(
                'Missing AEF knowledge-base CSV file(s): ' + ', '.join(missing)
            )

        st.session_state['df_crops'] = pd.read_csv(crops_path)
        st.session_state['df_diseases'] = pd.read_csv(diseases_path)

    @staticmethod
    def save_config_to_json():
        config = {
            'app_mode': st.session_state.get('app_mode'),
            'app_mode_locked': st.session_state.get('app_mode_locked', False),
            'interface_level': st.session_state.get('interface_level', 'guided'),
            'field_name': st.session_state['field_name'],
            'center_lat': st.session_state['center_lat'],
            'center_lon': st.session_state['center_lon'],
            'field_coords': st.session_state['field_coords'],
            'area_ha': st.session_state['area_ha'],
            'field_design_metadata': st.session_state.get('field_design_metadata', {}),
            'cooperative_name': st.session_state.get('cooperative_name', 'My Cooperative'),
            'cooperative_perimeter_coords': st.session_state.get('cooperative_perimeter_coords', []),
            'cooperative_parcels': st.session_state.get('cooperative_parcels', []),
            'cooperative_perimeter_area_ha': st.session_state.get('cooperative_perimeter_area_ha', 100.0),
            'cooperative_target_parcel_area_ha': st.session_state.get('cooperative_target_parcel_area_ha', 1.5),
            'cooperative_crop_mode': st.session_state.get('cooperative_crop_mode', 'shared'),
            'cooperative_management_mode': st.session_state.get('cooperative_management_mode', 'per_parcel'),
            'cooperative_detection_confidence': st.session_state.get('cooperative_detection_confidence', 0.0),
            'cooperative_detection_notes': st.session_state.get('cooperative_detection_notes', ''),
            'focused_cooperative_plot_id': st.session_state.get('focused_cooperative_plot_id'),
            'cooperative_report_water_limit_m3': st.session_state.get('cooperative_report_water_limit_m3', 0.0),
            'cooperative_report_fertilizer_limit_kg': st.session_state.get('cooperative_report_fertilizer_limit_kg', 0.0),
            'cooperative_report_labour_days': st.session_state.get('cooperative_report_labour_days', 0.0),
            'report_detail_level': st.session_state.get('report_detail_level', 'balanced'),

            'selected_crop_id': st.session_state['selected_crop_id'],
            'planting_date': str(st.session_state['planting_date']),
            'planting_density': st.session_state['planting_density'],
            'sowing_depth': st.session_state['sowing_depth'],
            'initial_plant_age_years': st.session_state.get('initial_plant_age_years', 0.0),
            'history_years': st.session_state.get('history_years', 0),
            'perennial_last_pruning_date': str(st.session_state.get('perennial_last_pruning_date')) if st.session_state.get('perennial_last_pruning_date') else None,
            'perennial_next_pruning_date': str(st.session_state.get('perennial_next_pruning_date')) if st.session_state.get('perennial_next_pruning_date') else None,
            'perennial_dormancy_start_month': st.session_state.get('perennial_dormancy_start_month', 0),
            'perennial_dormancy_end_month': st.session_state.get('perennial_dormancy_end_month', 0),
            'perennial_historical_yield_t_ha': st.session_state.get('perennial_historical_yield_t_ha', 0.0),

            'selected_disease_id': st.session_state['selected_disease_id'],
            'disease_spots': st.session_state['disease_spots'],
            'detection_date': str(st.session_state['detection_date']),
            'insect_pressure': st.session_state['insect_pressure'],
            'satellite_anomaly_date': str(st.session_state.get('satellite_anomaly_date')) if st.session_state.get('satellite_anomaly_date') else None,

            'soil_type': st.session_state['soil_type'],
            'initial_nitrogen': st.session_state['initial_nitrogen'],
            'initial_phosphorus': st.session_state.get('initial_phosphorus', 20.0),
            'initial_potassium': st.session_state.get('initial_potassium', 100.0),
            'use_expert_soil': st.session_state['use_expert_soil'],
            'soil_data_source': st.session_state.get('soil_data_source', 'manual'),
            'soil_confidence': st.session_state.get('soil_confidence', 1.0),
            'soil_detection_notes': st.session_state.get('soil_detection_notes', ''),
            'water_source_type': st.session_state.get('water_source_type', 'unknown'),
            'available_water_m3_day': st.session_state.get('available_water_m3_day', 0.0),
            'irrigation_efficiency': st.session_state.get('irrigation_efficiency', 0.70),
            'irrigation_method': st.session_state.get('irrigation_method', 'unspecified'),
            'fertilizer_budget_per_ha': st.session_state.get('fertilizer_budget_per_ha', 0.0),
            'fertilizer_availability_note': st.session_state.get('fertilizer_availability_note', ''),
            'economic_horizon_years': st.session_state.get('economic_horizon_years', 20),
            'economics_config': normalize_economics_config(st.session_state.get('economics_config', {}), {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys() if key != 'economics_config'}),

            'soil_layers': st.session_state['soil_layers'].to_dict('records') if st.session_state['soil_layers'] is not None else [],
            'fert_schedule': st.session_state['fert_schedule'].astype(str).to_dict('records') if st.session_state['fert_schedule'] is not None else [],
            'irr_schedule': st.session_state['irr_schedule'].astype(str).to_dict('records') if st.session_state['irr_schedule'] is not None else [],

            'surveillance_logs': st.session_state.get('surveillance_logs', []),
            'calibrated_params': st.session_state.get('calibrated_params', {}),
        }
        return json.dumps(config, indent=4)

    @staticmethod
    def load_config_from_json(json_file):
        try:
            data = json.load(json_file)
            st.session_state['app_mode'] = data.get('app_mode', st.session_state.get('app_mode'))
            st.session_state['app_mode_locked'] = data.get('app_mode_locked', bool(st.session_state.get('app_mode')))
            st.session_state['interface_level'] = data.get('interface_level', 'guided')
            st.session_state['field_coords'] = data.get('field_coords', [])
            st.session_state['center_lat'] = data.get('center_lat', 9.30)
            st.session_state['center_lon'] = data.get('center_lon', 13.40)
            st.session_state['area_ha'] = data.get('area_ha', 1.0)
            st.session_state['field_design_metadata'] = data.get('field_design_metadata', {})
            st.session_state['cooperative_name'] = data.get('cooperative_name', st.session_state.get('cooperative_name', 'My Cooperative'))
            st.session_state['cooperative_perimeter_coords'] = data.get('cooperative_perimeter_coords', [])
            st.session_state['cooperative_parcels'] = data.get('cooperative_parcels', [])
            st.session_state['cooperative_perimeter_area_ha'] = data.get('cooperative_perimeter_area_ha', 100.0)
            st.session_state['cooperative_target_parcel_area_ha'] = data.get('cooperative_target_parcel_area_ha', 1.5)
            st.session_state['cooperative_crop_mode'] = data.get('cooperative_crop_mode', 'shared')
            st.session_state['cooperative_management_mode'] = data.get('cooperative_management_mode', 'per_parcel')
            st.session_state['cooperative_detection_confidence'] = data.get('cooperative_detection_confidence', 0.0)
            st.session_state['cooperative_detection_notes'] = data.get('cooperative_detection_notes', '')
            st.session_state['focused_cooperative_plot_id'] = data.get('focused_cooperative_plot_id')
            st.session_state['cooperative_report_water_limit_m3'] = data.get('cooperative_report_water_limit_m3', 0.0)
            st.session_state['cooperative_report_fertilizer_limit_kg'] = data.get('cooperative_report_fertilizer_limit_kg', 0.0)
            st.session_state['cooperative_report_labour_days'] = data.get('cooperative_report_labour_days', 0.0)
            st.session_state['report_detail_level'] = data.get('report_detail_level', 'balanced')

            st.session_state['selected_crop_id'] = data.get('selected_crop_id')
            if data.get('planting_date'):
                st.session_state['planting_date'] = date.fromisoformat(data['planting_date'])
            st.session_state['planting_density'] = data.get('planting_density', 10000)
            st.session_state['sowing_depth'] = data.get('sowing_depth', 5)
            st.session_state['initial_plant_age_years'] = data.get('initial_plant_age_years', 0.0)
            st.session_state['history_years'] = data.get('history_years', 0)
            st.session_state['perennial_last_pruning_date'] = date.fromisoformat(str(data['perennial_last_pruning_date'])[:10]) if data.get('perennial_last_pruning_date') else None
            st.session_state['perennial_next_pruning_date'] = date.fromisoformat(str(data['perennial_next_pruning_date'])[:10]) if data.get('perennial_next_pruning_date') else None
            st.session_state['perennial_dormancy_start_month'] = data.get('perennial_dormancy_start_month', 0)
            st.session_state['perennial_dormancy_end_month'] = data.get('perennial_dormancy_end_month', 0)
            st.session_state['perennial_historical_yield_t_ha'] = data.get('perennial_historical_yield_t_ha', 0.0)

            st.session_state['selected_disease_id'] = data.get('selected_disease_id')
            st.session_state['disease_spots'] = data.get('disease_spots', [])
            if data.get('detection_date'):
                st.session_state['detection_date'] = date.fromisoformat(data['detection_date'])
            st.session_state['insect_pressure'] = data.get('insect_pressure', 1.0)
            st.session_state['satellite_anomaly_date'] = date.fromisoformat(str(data['satellite_anomaly_date'])[:10]) if data.get('satellite_anomaly_date') else None

            st.session_state['soil_type'] = data.get('soil_type', 'loam')
            st.session_state['initial_nitrogen'] = data.get('initial_nitrogen', 10.0)
            st.session_state['initial_phosphorus'] = data.get('initial_phosphorus', 20.0)
            st.session_state['initial_potassium'] = data.get('initial_potassium', 100.0)
            st.session_state['use_expert_soil'] = data.get('use_expert_soil', False)
            st.session_state['soil_data_source'] = data.get('soil_data_source', 'manual')
            st.session_state['soil_confidence'] = data.get('soil_confidence', 1.0)
            st.session_state['soil_detection_notes'] = data.get('soil_detection_notes', '')
            st.session_state['water_source_type'] = data.get('water_source_type', 'unknown')
            st.session_state['available_water_m3_day'] = data.get('available_water_m3_day', 0.0)
            st.session_state['irrigation_efficiency'] = data.get('irrigation_efficiency', 0.70)
            st.session_state['irrigation_method'] = data.get('irrigation_method', 'unspecified')
            st.session_state['fertilizer_budget_per_ha'] = data.get('fertilizer_budget_per_ha', 0.0)
            st.session_state['fertilizer_availability_note'] = data.get('fertilizer_availability_note', '')
            st.session_state['economic_horizon_years'] = data.get('economic_horizon_years', st.session_state.get('economic_horizon_years', 20))
            st.session_state['economics_config'] = normalize_economics_config(data.get('economics_config', st.session_state.get('economics_config', {})), data)

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

            st.session_state['surveillance_logs'] = data.get('surveillance_logs', [])
            st.session_state['calibrated_params'] = data.get('calibrated_params', {})
            return True
        except Exception as e:
            st.error(f"Corrupt file: {e}")
            return False

    @staticmethod
    def save_economics_to_json():
        """Export only economic assumptions for reuse across fields."""
        context = {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys() if key != 'economics_config'}
        economics = normalize_economics_config(st.session_state.get('economics_config', {}), context)
        return json.dumps(economics, indent=4)

    @staticmethod
    def load_economics_from_json(json_file):
        """Load a standalone economics profile without touching agronomy."""
        try:
            data = json.load(json_file)
            context = {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys() if key != 'economics_config'}
            st.session_state['economics_config'] = normalize_economics_config(data, context)
            return True
        except Exception as e:
            st.error(f"Corrupt economics file: {e}")
            return False
