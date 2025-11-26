#app.py
import streamlit as st
import hydralit_components as hc
from src.models.state_manager import StateManager
from pages.main import setup_page
from pages.main import dashboard
from pages.main import report 

# 1. App Config
st.set_page_config(
    page_title="AEF Crop Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 2. Initialize State Manager
# This handles all data loading and defaults automatically
if 'step' not in st.session_state:
    StateManager.initialize()

# 3. Navigation Definition
menu_data = [
    {'icon': "fa fa-map-marker", 'label': "Site Setup"},
    {'icon': "fas fa-satellite", 'label': "Intelligence Dashboard"},
    {'icon': "fa fa-file-pdf", 'label': "Report"},
]

over_theme = {'txc_inactive': '#FFFFFF', 'menu_background': '#2C3E50'}

# --- PROGRAMMATIC NAVIGATION LOGIC ---
# Check if a specific target tab was requested (e.g., from Step 5 in Setup)
nav_index = 0 # Default to 0 ("Site Setup")

if st.session_state.get('nav_target'):
    try:
        # Find the index of the requested label (e.g., "Intelligence Dashboard" -> 1)
        target_label = st.session_state['nav_target']
        nav_index = [m['label'] for m in menu_data].index(target_label)
        
        # CRITICAL: Reset target to None so we don't keep jumping back on every reload
        st.session_state['nav_target'] = None 
    except ValueError:
        pass # Target not found, stay on default

# Render Navigation Bar
menu_id = hc.nav_bar(
    menu_definition=menu_data,
    override_theme=over_theme,
    sticky_nav=True,
    sticky_mode='pinned',
    hide_streamlit_markers=False,
    first_select=nav_index # <--- Apply the calculated index here
)

# 4. Routing Logic
if menu_id == "Site Setup":
    setup_page.app()

elif menu_id == "Intelligence Dashboard":
    if not st.session_state.get('setup_complete'):
        st.warning("⚠️ Please complete the configuration in 'Site Setup' first.")
    else:
        dashboard.app()

elif menu_id == "Report":
    # Check for simulation results before showing report
    if 'sim_results' not in st.session_state:
        st.warning("⚠️ No intelligence generated yet. Please run the simulation in the Dashboard tab.")
    else:
        report.app()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Powered by **AlphaEarth Foundations**")