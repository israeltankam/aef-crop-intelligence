# app.py
import os
import streamlit as st
import hydralit_components as hc
from src.models.state_manager import StateManager
from src.utils.access_control import check_access
from src.utils.i18n import t, language_selector
from pages.main import setup_page
from pages.main import dashboard
from pages.main import report
from pages.main import recommendations
from pages.main import what_if
from pages.main import preassessment
from pages.main import surveillance # NEW IMPORT


COMPANY_LOGO_PATH = os.path.join('src', 'images', 'logo', 'logo_company', 'logo_scale.png')


def render_company_logo(width=110):
    """Show the Scale AG logo discreetly when the local asset is available."""
    if os.path.exists(COMPANY_LOGO_PATH):
        st.image(COMPANY_LOGO_PATH, width=width)


def render_mode_selector():
    """First-run selector between operational and pre-planting workflows."""
    language_selector(location="main", key="aef_language_selector_mode")
    st.title(t("mode.title"))
    st.caption(t("mode.caption"))
    col_single, col_coop, col_pre = st.columns(3)
    with col_single:
        st.subheader(t("mode.single.title"))
        st.write(t("mode.single.body"))
    with col_coop:
        st.subheader(t("mode.cooperative.title"))
        st.write(t("mode.cooperative.body"))
    with col_pre:
        st.subheader(t("mode.preassessment.title"))
        st.write(t("mode.preassessment.body"))
    mode_labels = {
        "single": t("mode.single.option"),
        "cooperative": t("mode.cooperative.option"),
        "preassessment": t("mode.preassessment.option"),
    }
    choice = st.radio(
        t("mode.choose"),
        ["single", "cooperative", "preassessment"],
        format_func=lambda x: mode_labels.get(x, x),
        horizontal=True,
        key="aef_initial_mode_choice",
    )
    if st.button(t("mode.continue"), type="primary"):
        st.session_state["app_mode"] = choice
        st.session_state["app_mode_locked"] = True
        st.session_state["setup_complete"] = False
        st.session_state.pop("sim_results", None)
        st.session_state.pop("sim_uncertainty", None)
        st.session_state.pop("preassessment_result", None)
        st.rerun()


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
        language_selector(location="main", key="aef_language_selector_login")
        render_company_logo(width=150)
        st.title("🔐 " + t("login.title"))
        st.markdown(t("login.welcome"))
        st.info(t("login.info"))
        
        # Login Form
        with st.form("login_form"):
            code_input = st.text_input(t("login.input"), type="password")
            submitted = st.form_submit_button(t("login.button"))
            
            if submitted:
                if check_access(code_input, key=ACCESS_KEY_SECRET):
                    st.session_state['access_granted'] = True
                    st.success(t("login.success"))
                    st.rerun()
                else:
                    st.error(t("login.error"))
                    st.markdown(t("login.no_code"))
    
    # Stop execution here if not authenticated
    st.stop()

# --- MAIN APP LOGIC (Only runs if access_granted is True) ---

# 2. Initialize State Manager
if 'step' not in st.session_state:
    StateManager.initialize()

if not st.session_state.get("app_mode"):
    render_mode_selector()
    st.stop()

# 3. Language and Navigation Definition
language_selector(location="sidebar", key="aef_language_selector_sidebar")
with st.sidebar:
    render_company_logo(width=92)
active_mode_label = {"single": t("mode.single.option"), "cooperative": t("mode.cooperative.option"), "preassessment": t("mode.preassessment.option")}.get(st.session_state.get("app_mode"), t("mode.single.option"))
st.sidebar.caption(t("mode.active") + ": " + active_mode_label)
if st.sidebar.button(t("mode.change")):
    st.session_state["app_mode"] = None
    st.session_state["setup_complete"] = False
    st.session_state.pop("sim_results", None)
    st.session_state.pop("sim_uncertainty", None)
    st.rerun()
site_setup_label = t("nav.site_setup")
dashboard_label = t("nav.dashboard")
surveillance_label = t("nav.surveillance")
recommendations_label = t("nav.recommendations")
what_if_label = t("nav.what_if")
report_label = t("nav.report")
preassessment_label = t("nav.preassessment")
if st.session_state.get("app_mode") == "preassessment":
    menu_data = [
        {'icon': "fa fa-search-location", 'label': preassessment_label},
    ]
else:
    menu_data = [
        {'icon': "fa fa-map-marker", 'label': site_setup_label},
        {'icon': "fas fa-satellite", 'label': dashboard_label},
        {'icon': "fa fa-chart-line", 'label': surveillance_label},
        {'icon': "fa fa-compass", 'label': recommendations_label},
        {'icon': "fa fa-flask", 'label': what_if_label},
        {'icon': "fa fa-file-pdf", 'label': report_label},
    ]

over_theme = {'txc_inactive': '#FFFFFF', 'menu_background': '#2C3E50'}

# --- PROGRAMMATIC NAVIGATION LOGIC ---
nav_index = 0 

if st.session_state.get('nav_target'):
    try:
        target_label = st.session_state['nav_target']
        legacy_targets = {
            "Site Setup": site_setup_label,
            "Intelligence Dashboard": dashboard_label,
            "Adaptive Surveillance": surveillance_label,
            "Recommendations": recommendations_label,
            "What-if scenarios": what_if_label,
            "Report": report_label,
        }
        target_label = legacy_targets.get(target_label, target_label)
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
if menu_id == preassessment_label:
    preassessment.app()

elif menu_id == site_setup_label:
    setup_page.app()

elif menu_id == dashboard_label:
    if not st.session_state.get('setup_complete'):
        st.warning("⚠️ " + t("guard.setup_first"))
    else:
        dashboard.app()

elif menu_id == surveillance_label:
    if not st.session_state.get('setup_complete'):
        st.warning("⚠️ " + t("guard.setup_first"))
    else:
        surveillance.app()

elif menu_id == recommendations_label:
    if 'sim_results' not in st.session_state:
        st.warning("⚠️ " + t("guard.no_results"))
    else:
        recommendations.app()

elif menu_id == what_if_label:
    if 'sim_results' not in st.session_state:
        st.warning("⚠️ " + t("guard.no_results"))
    else:
        what_if.app()

elif menu_id == report_label:
    if 'sim_results' not in st.session_state:
        st.warning("⚠️ " + t("guard.no_results"))
    else:
        report.app()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("Powered by **AlphaEarth Foundations**")