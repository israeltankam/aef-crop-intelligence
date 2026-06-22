# pages/main/preassessment.py
"""Pre-planting assessment page.

This page is intentionally self-contained: unlike the operational single-field
workflow, it evaluates whether a crop variety should be planted before the crop
exists.  It therefore produces a planning dossier directly from location, soil,
crop variety, climate forecast and literature-prior disease pressure.
"""
from __future__ import annotations

from datetime import date, timedelta
import json

import folium
import pandas as pd
import streamlit as st
from folium.plugins import Draw
from streamlit_folium import st_folium

from pages.main.setup_page import calculate_area_ha, generate_square_polygon, get_auto_soil_profile, optimize_field_location
from src.models.preassessment_engine import PreAssessmentEngine
from src.models.economic_engine import normalize_economics_config
from src.utils.i18n import tr
from src.utils.preassessment_pdf import build_preassessment_pdf


_SOIL_OPTIONS = [
    'sand', 'loamy sand', 'sandy loam', 'loam', 'silt loam', 'silt',
    'sandy clay loam', 'clay loam', 'silty clay loam', 'sandy clay',
    'silty clay', 'clay'
]


def _polygon_centroid(coords):
    # Polygons are stored as [lat, lon] pairs throughout the setup workflow.
    # This helper keeps map centering stable even when the user redraws an
    # irregular polygon rather than accepting the generated square fallback.
    pts = list(coords or [])
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not pts:
        return st.session_state.get('center_lat', 4.0), st.session_state.get('center_lon', 11.0)
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _last_polygon(output):
    # Streamlit-folium returns GeoJSON as [lon, lat].  The rest of AEF expects
    # [lat, lon], so we convert immediately to avoid subtle area/centroid bugs.
    drawing = (output or {}).get('last_active_drawing')
    if not drawing or drawing.get('geometry', {}).get('type') != 'Polygon':
        return None
    coords = drawing['geometry'].get('coordinates', [[]])[0]
    return [[lat, lon] for lon, lat in coords]


def _render_map(coords, key):
    """Render the candidate field map and let the user draw a replacement polygon.

    The pre-assessment mode keeps the same visual convention as setup: satellite
    imagery is available for inspection, while the user can still replace the
    automatic geometry with a hand-drawn polygon when the parcel is known.
    """
    center = _polygon_centroid(coords) if coords else (st.session_state.get('center_lat', 4.0), st.session_state.get('center_lon', 11.0))
    m = folium.Map(location=center, zoom_start=16, tiles='OpenStreetMap')
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery', name='Satellite', overlay=False, control=True,
    ).add_to(m)
    if coords:
        folium.Polygon(locations=coords, color='#24765c', weight=3, fill=True, fill_opacity=0.18, popup=tr('Candidate field')).add_to(m)
    Draw(export=False, draw_options={'polyline': False, 'rectangle': False, 'circle': False, 'marker': False, 'circlemarker': False, 'polygon': True}).add_to(m)
    folium.LayerControl().add_to(m)
    return st_folium(m, height=500, width=None, key=key)


def _crop_selector(df_crops: pd.DataFrame):
    # The new mode reuses the curated crop/variety CSV instead of creating a
    # second variety database.  That keeps scientific parameters consistent
    # across single-field, cooperative, and pre-assessment workflows.
    crop_names = sorted(df_crops['Crop_Name'].dropna().unique())
    crop_name = st.selectbox(tr('Select Crop Species'), crop_names, key='preassessment_crop_name')
    varieties = df_crops[df_crops['Crop_Name'] == crop_name]
    variety_names = varieties['Variety'].tolist()
    variety = st.selectbox(tr('Select Variety'), variety_names, key='preassessment_variety')
    crop_row = varieties[varieties['Variety'] == variety].iloc[0].to_dict()
    st.caption(f"{tr('Crop type')}: {tr(str(crop_row.get('Type', 'Annual')))} | {tr('Assessed cycle')}: {int(float(crop_row.get('Cycle_Days', 120)))} {tr('days')}")
    if str(crop_row.get('Type', 'Annual')) == 'Perennial':
        st.info(tr('Perennial crop: pre-evaluation assesses one production cycle only.'))
    return crop_row


def _preassessment_config():
    # Build a compact configuration object for the engine.  It deliberately
    # mirrors the operational setup fields so users do not learn a different
    # soil/location vocabulary just because the field is not planted yet.
    coords = st.session_state.get('preassessment_field_coords') or []
    area = calculate_area_ha(coords) if coords else float(st.session_state.get('preassessment_area_ha', 1.0) or 1.0)
    return {
        'field_name': st.session_state.get('preassessment_field_name', 'Pre-assessment field'),
        'center_lat': float(st.session_state.get('center_lat', 4.0)),
        'center_lon': float(st.session_state.get('center_lon', 11.0)),
        'field_coords': coords,
        'area_ha': area,
        'soil_type': st.session_state.get('soil_type', 'loam'),
        'soil_confidence': float(st.session_state.get('soil_confidence', 0.65) or 0.65),
        'initial_nitrogen': float(st.session_state.get('initial_nitrogen', 10.0) or 10.0),
        'initial_phosphorus': float(st.session_state.get('initial_phosphorus', 20.0) or 20.0),
        'initial_potassium': float(st.session_state.get('initial_potassium', 100.0) or 100.0),
        'preassessment_window_start': st.session_state.get('preassessment_window_start', date.today() + timedelta(days=14)),
        'economics_config': normalize_economics_config(st.session_state.get('economics_config', {})),
    }


def _translate_engine_text(value):
    """Translate common dynamic sentences produced by the pre-assessment engine."""
    text = str(value or '')
    if text.startswith('Mean temperature '):
        if ' °C versus crop optimum ' in text:
            left, right = text.replace('.', '').split(' °C versus crop optimum ', 1)
            return f"{tr('Mean temperature')} {left.replace('Mean temperature ', '')} °C {tr('versus crop optimum')} {right} °C."
        if ' C versus crop optimum ' in text:
            left, right = text.replace('.', '').split(' C versus crop optimum ', 1)
            return f"{tr('Mean temperature')} {left.replace('Mean temperature ', '')} °C {tr('versus crop optimum')} {right} °C."
    if text.startswith('Forecast rain ') and '; estimated crop water demand ' in text and '; deficit ' in text:
        clean = text.replace('.', '')
        rain, rest = clean.replace('Forecast rain ', '').split(' mm; estimated crop water demand ', 1)
        demand, deficit = rest.split(' mm; deficit ', 1)
        return f"{tr('Forecast rain')} {rain} mm; {tr('estimated crop water demand')} {demand} mm; {tr('deficit')} {deficit} mm."
    if text.startswith('Regional literature prior adjusted by forecast humidity/rainfall; top risk '):
        risk = text.replace('Regional literature prior adjusted by forecast humidity/rainfall; top risk ', '')
        return f"{tr('Regional literature prior adjusted by forecast humidity/rainfall; top risk')} {risk}"
    return tr(text)


def _localize_rows(rows):
    # Engine outputs are stored in stable English keys for JSON portability.
    # Before displaying them, translate fixed labels and common rationale text
    # so the French/English toggle remains respected in the farmer-facing UI.
    localized = []
    for row in rows or []:
        item = dict(row)
        for key in ['name', 'explanation', 'reason', 'product', 'rationale']:
            if key in item:
                item[key] = _translate_engine_text(item.get(key, ''))
        localized.append(item)
    return localized


def _format_iso_date(value):
    """Return an explicit ISO date string so users never guess day/month order."""
    text = str(value or '')
    return f"{text} ({tr('YYYY-MM-DD: year-month-day')})" if text else ''


def _recommendation_paragraph(result):
    """Build the final farmer-facing recommendation paragraph in rich Markdown."""
    best = result.get('best', {}) or {}
    score = float(best.get('score', 0.0) or 0.0)
    decision = tr(str(result.get('recommendation', 'do_not_prioritize')))
    date_text = str(best.get('planting_date', ''))
    top_risks = result.get('disease_risks', []) or []
    top_risk = top_risks[0].get('disease_name') if top_risks else tr('no dominant disease prior')
    soil = result.get('soil_summary', {}) or {}
    if score >= 70:
        posture = tr('the site is currently suitable enough to proceed, provided local validation confirms the assumptions')
    elif score >= 55:
        posture = tr('the site can be considered, but only with caution and local validation before investment')
    else:
        posture = tr('the site should not be prioritized for this variety under the current assumptions')
    return tr(
        '**Recommendation:** {decision}. With a suitability score of **{score:.1f}/100**, {posture}. The best planting date candidate is **{date}** using the explicit format **YYYY-MM-DD**. The main disease-pressure signal is **{risk}**, and the soil screening score is **{soil_score}/100**. Before committing, validate the parcel boundary on the satellite map, confirm soil data locally, and use early field surveillance to reduce uncertainty.',
        decision=decision, score=score, posture=posture, date=date_text, risk=top_risk, soil_score=soil.get('score', 'n/a')
    )


def _render_result(result):
    # Results are intentionally grouped like a dossier: score first, then why,
    # then calendars, then disease priors, then the downloadable report.
    best = result.get('best', {})
    st.markdown('### ' + tr('Pre-assessment result'))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(tr('Suitability score'), f"{best.get('score', 0):.1f}/100")
    c2.metric(tr('Best planting date (YYYY-MM-DD)'), str(best.get('planting_date')))
    c3.metric(tr('Assessed cycle'), f"{result.get('cycle_days_assessed')} {tr('days')}")
    c4.metric(tr('Recommendation'), tr(str(result.get('recommendation'))))

    component_rows = pd.DataFrame(_localize_rows(best.get('components', [])))
    if not component_rows.empty:
        component_rows['weight'] = (component_rows['weight'].astype(float) * 100).round(0).astype(int).astype(str) + '%'
        st.dataframe(component_rows.rename(columns={'name': tr('Component'), 'score': tr('Score'), 'weight': tr('Weight'), 'explanation': tr('Explanation')}), use_container_width=True, hide_index=True)

    st.markdown('#### ' + tr('Planting date candidates'))
    st.caption(tr('All dates use the ISO format YYYY-MM-DD: year-month-day.'))
    candidate_rows = []
    for item in result.get('candidate_dates', [])[:12]:
        cw = item.get('climate_water', {})
        disease = item.get('disease', {})
        candidate_rows.append({
            tr('Planting date (YYYY-MM-DD)'): item.get('planting_date'),
            tr('Score'): item.get('score'),
            tr('Rain mm'): cw.get('rain_mm'),
            tr('Deficit mm'): cw.get('deficit_mm'),
            tr('Disease risk'): disease.get('mean_risk'),
        })
    st.dataframe(pd.DataFrame(candidate_rows), use_container_width=True, hide_index=True)

    tab_irr, tab_fert, tab_disease, tab_pdf = st.tabs(['💧 ' + tr('Irrigation calendar'), '🧪 ' + tr('Fertilization calendar'), '🦠 ' + tr('Disease pressure'), '📄 PDF'])
    with tab_irr:
        st.dataframe(pd.DataFrame(_localize_rows(result.get('irrigation_calendar', []))), use_container_width=True, hide_index=True)
    with tab_fert:
        st.dataframe(pd.DataFrame(_localize_rows(result.get('fertilization_calendar', []))), use_container_width=True, hide_index=True)
    with tab_disease:
        st.caption(tr('Disease pressure is a literature prior adjusted by forecast weather. It must be checked with local surveillance before investment.'))
        st.dataframe(pd.DataFrame(result.get('disease_risks', [])), use_container_width=True, hide_index=True)
    with tab_pdf:
        if st.button('📄 ' + tr('Prepare pre-assessment PDF'), type='primary', use_container_width=True):
            with st.spinner(tr('Preparing the pre-assessment PDF...')):
                st.session_state['preassessment_pdf_bytes'] = build_preassessment_pdf(result)
        if st.session_state.get('preassessment_pdf_bytes'):
            st.download_button('📄 ' + tr('Download pre-assessment PDF'), data=st.session_state['preassessment_pdf_bytes'], file_name='aef_preassessment_report.pdf', mime='application/pdf', use_container_width=True)
        st.download_button('💾 ' + tr('Download pre-assessment JSON'), data=json.dumps(result, indent=2, default=str), file_name='aef_preassessment.json', mime='application/json', use_container_width=True)

    st.markdown('#### ' + tr('Final recommendation'))
    st.markdown(_recommendation_paragraph(result))


def app():
    # Public Streamlit entry point.  The button-based run is important: the
    # optimization should never start on page load, because users often need to
    # adjust field geometry, crop variety, and soil assumptions first.
    st.title('🔎 ' + tr('Pre-planting assessment'))
    st.caption(tr('Evaluate whether a crop variety is suitable before planting, using one forecast cycle, soil priors, climate and disease-pressure literature.'))
    if 'df_crops' not in st.session_state:
        st.warning(tr('Crop database is not loaded yet. Return to setup initialization.'))
        return

    st.markdown('### 1. ' + tr('Candidate field'))
    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state['preassessment_field_name'] = st.text_input(tr('Field name'), st.session_state.get('preassessment_field_name', 'Pre-assessment field'))
        st.session_state['center_lat'] = st.number_input(tr('Latitude'), value=float(st.session_state.get('center_lat', 4.0)), format='%.6f')
    with c2:
        st.session_state['center_lon'] = st.number_input(tr('Longitude'), value=float(st.session_state.get('center_lon', 11.0)), format='%.6f')
        st.session_state['preassessment_area_ha'] = st.number_input(tr('Candidate area (ha)'), min_value=0.05, max_value=50000.0, value=float(st.session_state.get('preassessment_area_ha', 1.0) or 1.0), step=0.1)
    with c3:
        st.session_state['preassessment_window_start'] = st.date_input(tr('Earliest acceptable planting date'), value=st.session_state.get('preassessment_window_start', date.today() + timedelta(days=14)))
        # The generated polygon is a convenience starting point; the map below
        # remains editable for users who know the true candidate boundary.
        if st.button(tr('Generate candidate parcel'), use_container_width=True):
            st.session_state['preassessment_field_coords'] = generate_square_polygon(st.session_state['center_lat'], st.session_state['center_lon'], st.session_state['preassessment_area_ha'])
            st.rerun()
    # Satellite-based geometry optimization can take time, so it is explicit
    # and wrapped in a spinner rather than hidden inside page rendering.
    if st.button('🛰️ ' + tr('Optimize candidate parcel against satellite land cover'), use_container_width=True):
        with st.spinner(tr('Searching for the most plausible cultivable parcel around the selected center...')):
            poly, level, color, msg, metadata = optimize_field_location(st.session_state['center_lat'], st.session_state['center_lon'], st.session_state.get('preassessment_area_ha', 1.0))
            st.session_state['preassessment_field_metadata'] = metadata
            if not metadata.get('auto_boundary_accepted', False):
                st.error(tr('No reliable cultivable candidate parcel was found around this center. The automatic boundary was not applied because the best candidate still contains too much built-up, water, wetland, or unknown cover. Please move the center or draw the parcel manually on the satellite map.'))
                st.caption(tr('Rejected candidate details: built-up {built:.1f}%, water/wetland {water:.1f}%, plausible field cover {field:.1f}%, center shift {shift:.0f} m.', built=float(metadata.get('built_up_pct', 0.0)), water=float(metadata.get('water_or_wetland_pct', 0.0)), field=float(metadata.get('plausible_field_pct', 0.0)), shift=float(metadata.get('center_shift_m', 0.0))))
            else:
                st.session_state['preassessment_field_coords'] = poly
                st.success(tr('Candidate parcel optimized.'))
                st.caption(tr(msg))
                st.caption(tr('Accepted candidate details: plausible field cover {field:.1f}%, built-up {built:.1f}%, water/wetland {water:.1f}%, center shift {shift:.0f} m. Please validate the boundary visually.', field=float(metadata.get('plausible_field_pct', 0.0)), built=float(metadata.get('built_up_pct', 0.0)), water=float(metadata.get('water_or_wetland_pct', 0.0)), shift=float(metadata.get('center_shift_m', 0.0))))
    map_out = _render_map(st.session_state.get('preassessment_field_coords', []), 'preassessment_map')
    drawn = _last_polygon(map_out)
    if drawn:
        st.session_state['preassessment_field_coords'] = drawn
        st.session_state['preassessment_area_ha'] = calculate_area_ha(drawn)
        st.success(tr('Candidate field updated from map drawing.'))
        st.rerun()

    st.markdown('### 2. ' + tr('Crop variety'))
    crop_row = _crop_selector(st.session_state['df_crops'])

    st.markdown('### 3. ' + tr('Soil starting point'))
    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.session_state['soil_type'] = st.selectbox(tr('Soil Type'), _SOIL_OPTIONS, index=_SOIL_OPTIONS.index(st.session_state.get('soil_type', 'loam')) if st.session_state.get('soil_type', 'loam') in _SOIL_OPTIONS else 3)
    with s2:
        st.session_state['initial_nitrogen'] = st.number_input(tr('Initial Nitrogen (kg/ha)'), min_value=0.0, max_value=500.0, value=float(st.session_state.get('initial_nitrogen', 10.0) or 10.0), step=5.0)
    with s3:
        st.session_state['initial_phosphorus'] = st.number_input(tr('Initial Phosphorus (kg/ha)'), min_value=0.0, max_value=500.0, value=float(st.session_state.get('initial_phosphorus', 20.0) or 20.0), step=5.0)
    with s4:
        st.session_state['initial_potassium'] = st.number_input(tr('Initial Potassium (kg/ha)'), min_value=0.0, max_value=800.0, value=float(st.session_state.get('initial_potassium', 100.0) or 100.0), step=10.0)
    # Automatic soil detection is useful for non-experts, but the fields remain
    # editable because manual/local laboratory data should override gridded data.
    if st.button('🪨 ' + tr('Auto-detect soil for candidate parcel'), disabled=not bool(st.session_state.get('preassessment_field_coords')), use_container_width=True):
        with st.spinner(tr('Estimating soil properties from gridded soil data...')):
            ok, profile, message = get_auto_soil_profile(st.session_state['preassessment_field_coords'])
            if ok:
                st.session_state['soil_type'] = profile.get('texture', st.session_state.get('soil_type', 'loam'))
                st.session_state['soil_confidence'] = profile.get('confidence', 0.62)
                st.session_state['initial_nitrogen'] = round(float(profile.get('n_available', st.session_state.get('initial_nitrogen', 10.0))), 1)
                st.success(tr('Automatic soil estimate applied.'))
            else:
                st.warning(tr(message))

    st.markdown('### 4. ' + tr('Run pre-assessment'))
    st.info(tr('For perennial crops, this mode evaluates only one production cycle and does not project multi-year revenue.'))
    if st.button('🔎 ' + tr('Run pre-planting assessment'), type='primary', use_container_width=True, disabled=not bool(st.session_state.get('preassessment_field_coords'))):
        with st.spinner(tr('Evaluating climate, soil, disease pressure, planting dates and management calendars...')):
            config = _preassessment_config()
            engine = PreAssessmentEngine()
            result = engine.evaluate(config, crop_row, st.session_state.get('df_diseases'))
            st.session_state['preassessment_result'] = result
            st.session_state.pop('preassessment_pdf_bytes', None)
            st.success(tr('Pre-assessment completed.'))

    if st.session_state.get('preassessment_result'):
        _render_result(st.session_state['preassessment_result'])
