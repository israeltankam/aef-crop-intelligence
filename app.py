# app.py
import streamlit as st
import hydralit_components as hc
from src.models.state_manager import StateManager
from src.utils.access_control import check_access
from pages.main import setup_page
from pages.main import dashboard
from pages.main import report
from pages.main import surveillance # NEW IMPORT

# 1. App Config
st.set_page_config(
    page_title="AEF Crop Intelligence",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- AUTHENTICATION WALL ---
ACCESS_KEY_SECRET = "default_secret" 

if 'access_granted' not in st.session_state:
    st.session_state['access_granted'] = False

if not st.session_state['access_granted']:
    # Centered Login Screen
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        # st.image("src/images/logo/logo.png", width=200) 
        st.title("🔐 Access Restricted")
        st.markdown("Welcome to **AEF Crop Intelligence** (Alpha Version).")
        st.info("This application is currently in closed testing. Please enter your access code to continue.")
        
        # Login Form
        with st.form("login_form"):
            code_input = st.text_input("Enter Access Code:", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                if check_access(code_input, key=ACCESS_KEY_SECRET):
                    st.session_state['access_granted'] = True
                    st.success("Access Granted! Loading...")
                    st.rerun()
                else:
                    st.error("Invalid Access Code.")
                    st.markdown("Don't have a code? Request one at [israeltankam@gmail.com](mailto:israeltankam@gmail.com)")
    
    # Stop execution here if not authenticated
    st.stop()

# --- MAIN APP LOGIC (Only runs if access_granted is True) ---

# 2. Initialize State Manager
if 'step' not in st.session_state:
    StateManager.initialize()

# 3. Navigation Definition
menu_data = [
    {'icon': "fa fa-map-marker", 'label': "Site Setup"},
    {'icon': "fas fa-satellite", 'label': "Intelligence Dashboard"},
    {'icon': "fa fa-chart-line", 'label': "Adaptive Surveillance"}, # NEW TAB
    {'icon': "fa fa-file-pdf", 'label': "Report"},
]

over_theme = {'txc_inactive': '#FFFFFF', 'menu_background': '#2C3E50'}

# --- PROGRAMMATIC NAVIGATION LOGIC ---
nav_index = 0 

if st.session_state.get('nav_target'):
    try:
        target_label = st.session_state['nav_target']
        nav_index = [m['label'] for m in menu_data].index(target_label)
        st.session_state['nav_target'] = None 
    except ValueError:
        pass 

# Render Navigation Bar
menu_id = hc.nav_bar(
    menu_definition=menu_data,
    override_theme=over_theme,
    sticky_nav=True,
    sticky_mode='pinned',
    hide_streamlit_markers=False,
    first_select=nav_index 
)

# 4. Routing Logic
if menu_id == "Site Setup":
    setup_page.app()

elif menu_id == "Intelligence Dashboard":
    if not st.session_state.get('setup_complete'):
        st.warning("⚠️ Please complete the configuration in 'Site Setup' first.")
    else:
        dashboard.app()

elif menu_id == "Adaptive Surveillance":
    if not st.session_state.get('setup_complete'):
        st.warning("⚠️ Please complete the configuration in 'Site Setup' first.")
    else:
        surveillance.app()

elif menu_id == "Report":
    if 'sim_results' not in st.session_state:
        st.warning("⚠️ No intelligence generated yet. Please run the simulation in the Dashboard tab.")
    else:
        report.app()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Powered by **AlphaEarth Foundations**")