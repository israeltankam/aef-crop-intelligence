# pages/main/recommendations.py
import json
import streamlit as st
import pandas as pd
from datetime import date, timedelta

from src.models.state_manager import StateManager
from src.models.simulation_engine import SimulationEngine
from src.models.cooperative_engine import CooperativeSimulationEngine
from src.models.economic_engine import build_single_field_economics, build_cooperative_economics, normalize_economics_config
from src.models.cooperative_constraints import evaluate_shared_resource_constraints
from src.utils.i18n import tr


def _config_from_state():
    """Collect the same serialisable configuration used by dashboard/report runs."""
    config = {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys() if key in st.session_state}
    get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
    config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
    config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
    if st.session_state.get('soil_layers') is not None:
        config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
    else:
        config['soil_layers'] = []
    config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
    config['planting_date'] = st.session_state.get('planting_date', date.today())
    return config


def _safe_float(value, default=0.0):
    """Convert loose UI/model values to float without breaking the page."""
    try:
        if value is None or value == '':
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _money(value, currency):
    return f"{float(value or 0.0):,.0f} {currency}".replace(',', ' ')


def _parse_date(value):
    """Return a date object for model events coming as date, Timestamp or text."""
    try:
        parsed = pd.to_datetime(value)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _schedule_within_selected_horizon(schedule, config, result):
    """Limit perennial calendars to the horizon selected on the Recommendations page.

    The optimization engines may prepare long-horizon calendars for perennial crops.
    The user-facing table should match the economic horizon currently reviewed, so
    a 5-year cocoa analysis does not silently show a 20-year intervention calendar.
    Annual crops keep their complete simulated calendar.
    """
    events = list(schedule or [])
    crop_params = result.get('crop_params', {}) if result else {}
    if str(crop_params.get('Type', 'Annual')) != 'Perennial':
        return events
    start = _parse_date(config.get('planting_date'))
    if start is None:
        return events
    horizon_years = int(_safe_float(config.get('economics_config', {}).get('economic_horizon_years'), 20.0))
    cutoff = start + timedelta(days=max(1, horizon_years) * 365)
    return [event for event in events if (_parse_date(event.get('date')) is None or _parse_date(event.get('date')) < cutoff)]


def _summary_rows(plan):
    """Build the decision table with total net return and incremental gain separated."""
    currency = plan.get('currency', 'XAF')
    s = plan.get('summary', {})
    return pd.DataFrame([
        {
            tr('Scenario'): tr('Baseline / no action'),
            tr('Production'): f"{s.get('baseline_production_t', 0.0):.2f} t",
            tr('Production/ha'): f"{s.get('baseline_production_t_per_ha', 0.0):.2f} t/ha",
            tr('Revenue/ha'): _money(s.get('baseline_revenue_per_ha', 0.0), currency),
            tr('Cost/ha'): _money(s.get('baseline_cost_per_ha', 0.0), currency),
            tr('Net return/ha'): _money(s.get('baseline_net_return_per_ha', s.get('baseline_net_gain_per_ha', 0.0)), currency),
            tr('Net return'): _money(s.get('baseline_net_return', s.get('baseline_net_gain', 0.0)), currency),
            tr('Net gain vs baseline'): _money(0, currency),
        },
        {
            tr('Scenario'): tr('Agronomic optimum'),
            tr('Production'): f"{s.get('agronomic_production_t', 0.0):.2f} t",
            tr('Production/ha'): f"{s.get('agronomic_production_t_per_ha', 0.0):.2f} t/ha",
            tr('Revenue/ha'): _money(s.get('agronomic_revenue_per_ha', 0.0), currency),
            tr('Cost/ha'): _money(s.get('agronomic_cost_per_ha', 0.0), currency),
            tr('Net return/ha'): _money(s.get('agronomic_net_return_per_ha', s.get('agronomic_net_gain_per_ha', 0.0)), currency),
            tr('Net return'): _money(s.get('agronomic_net_return', s.get('agronomic_net_gain', 0.0)), currency),
            tr('Net gain vs baseline'): _money(s.get('agronomic_incremental_net_gain', 0.0), currency),
        },
        {
            tr('Scenario'): tr('Economic optimum'),
            tr('Production'): f"{s.get('economic_production_t', 0.0):.2f} t",
            tr('Production/ha'): f"{s.get('economic_production_t_per_ha', 0.0):.2f} t/ha",
            tr('Revenue/ha'): _money(s.get('economic_revenue_per_ha', 0.0), currency),
            tr('Cost/ha'): _money(s.get('economic_cost_per_ha', 0.0), currency),
            tr('Net return/ha'): _money(s.get('economic_net_return_per_ha', s.get('economic_net_gain_per_ha', 0.0)), currency),
            tr('Net return'): _money(s.get('economic_net_return', s.get('economic_net_gain', 0.0)), currency),
            tr('Net gain vs baseline'): _money(s.get('economic_incremental_net_gain', 0.0), currency),
        },
    ])

def _actions_frame(actions, currency):
    rows = []
    for action in actions or []:
        rows.append({
            tr('Action'): tr(str(action.get('title', ''))),
            tr('Type'): tr(str(action.get('type', ''))),
            tr('Timing'): str(action.get('timing', '')),
            tr('Cost'): _money(action.get('cost', 0.0), currency),
            tr('Gross benefit'): _money(action.get('gross_benefit', 0.0), currency),
            tr('Net benefit'): _money(action.get('net_benefit', 0.0), currency),
            tr('Production gain'): f"{float(action.get('production_gain_t', 0.0) or 0.0):.2f} t",
            tr('ROI'): f"{float(action.get('roi', 0.0) or 0.0):.2f}",
            tr('Economic decision'): tr('Keep') if action.get('economically_selected') else tr('Agronomic only'),
            tr('Confidence'): tr(str(action.get('confidence', ''))),
        })
    return pd.DataFrame(rows)


def _action_for_types(plan, action_types):
    """Find the economic action row matching one or several engine action types."""
    if isinstance(action_types, str):
        action_types = {action_types}
    else:
        action_types = set(action_types or [])
    for action in plan.get('actions', []) or []:
        if action.get('type') in action_types:
            return action
    return {}


def _is_action_economically_selected(plan, action_types):
    return bool(_action_for_types(plan, action_types).get('economically_selected'))


def _render_economic_status(plan, action_types):
    """Explain why a full calendar appears in the economic tab.

    The economic tab should not hide agronomic schedules, because users still need
    the operational calendar to understand what was rejected or retained.  This
    status line prevents confusion between "not selected economically" and "not
    recommended agronomically".
    """
    if _is_action_economically_selected(plan, action_types):
        st.success(tr('Economic decision for this calendar') + ': ' + tr('Kept in economic optimum'))
    else:
        st.warning(tr('Economic decision for this calendar') + ': ' + tr('Agronomic calendar only under current prices'))
        st.caption(tr('The full agronomic calendar is shown below even when it is not economically selected.'))


def _irrigation_schedule_frame(schedule, area_ha, economics, currency):
    """Build a field-level irrigation table from optimized model events."""
    cost_per_m3 = _safe_float(economics.get('irrigation_cost_per_m3'), 0.0)
    labour_per_event = _safe_float(economics.get('irrigation_labor_cost_per_event'), 0.0)
    rows = []
    for event in schedule or []:
        amount_mm = _safe_float(event.get('amount'), 0.0)
        water_m3 = amount_mm * max(0.0, area_ha) * 10.0
        rows.append({
            tr('Date'): str(event.get('date', '')),
            tr('Amount (mm)'): round(amount_mm, 1),
            tr('Water volume (m3)'): round(water_m3, 1),
            tr('Estimated cost'): _money(water_m3 * cost_per_m3 + labour_per_event, currency),
            tr('Notes'): tr(str(event.get('reason') or event.get('feasibility_note') or 'Stress Mitigation')),
        })
    return pd.DataFrame(rows)


def _fertilization_schedule_frame(schedule, area_ha, economics, currency):
    """Build a field-level fertilization table with product totals and costs."""
    fertilizer_prices = economics.get('fertilizer_prices', {}) or {}
    default_price = _safe_float(economics.get('default_fertilizer_price_per_kg'), 0.0)
    labour_per_day_ha = _safe_float((economics.get('labor_costs', {}) or {}).get('fertilizer_application_day'), 0.0)
    rows = []
    for event in schedule or []:
        product = str(event.get('product') or tr('Unspecified product'))
        rate = _safe_float(event.get('amount'), 0.0)
        total_product = rate * max(0.0, area_ha)
        unit_price = _safe_float(fertilizer_prices.get(product), default_price)
        rows.append({
            tr('Date'): str(event.get('date', '')),
            tr('Product'): product,
            tr('Rate (kg/ha)'): round(rate, 1),
            tr('Total product (kg)'): round(total_product, 1),
            tr('Estimated cost'): _money(total_product * unit_price + labour_per_day_ha * max(0.0, area_ha), currency),
            tr('Rationale'): tr(str(event.get('rationale') or 'Nutrient stress mitigation')),
        })
    return pd.DataFrame(rows)


def _cooperative_irrigation_schedule_frame(opt_plan, config, result, economics, currency):
    """Flatten plot-level irrigation calendars for cooperative recommendations."""
    rows = []
    cost_per_m3 = _safe_float(economics.get('irrigation_cost_per_m3'), 0.0)
    labour_per_event = _safe_float(economics.get('irrigation_labor_cost_per_event'), 0.0)
    for plot in (opt_plan or {}).get('rows', []) or []:
        area = _safe_float(plot.get('area_ha'), 0.0)
        for event in _schedule_within_selected_horizon(plot.get('irrigation_schedule', []), config, result):
            amount_mm = _safe_float(event.get('amount'), 0.0)
            water_m3 = amount_mm * area * 10.0
            rows.append({
                tr('Plot name'): plot.get('name') or plot.get('id'),
                tr('Area (ha)'): round(area, 2),
                tr('Date'): str(event.get('date', '')),
                tr('Amount (mm)'): round(amount_mm, 1),
                tr('Water volume (m3)'): round(water_m3, 1),
                tr('Estimated cost'): _money(water_m3 * cost_per_m3 + labour_per_event, currency),
                tr('Notes'): tr(str(event.get('reason') or event.get('feasibility_note') or 'Stress Mitigation')),
            })
    return pd.DataFrame(rows)


def _cooperative_fertilization_schedule_frame(opt_plan, config, result, economics, currency):
    """Flatten plot-level fertilization calendars for cooperative recommendations."""
    fertilizer_prices = economics.get('fertilizer_prices', {}) or {}
    default_price = _safe_float(economics.get('default_fertilizer_price_per_kg'), 0.0)
    labour_per_day_ha = _safe_float((economics.get('labor_costs', {}) or {}).get('fertilizer_application_day'), 0.0)
    rows = []
    for plot in (opt_plan or {}).get('rows', []) or []:
        area = _safe_float(plot.get('area_ha'), 0.0)
        for event in _schedule_within_selected_horizon(plot.get('fertilization_schedule', []), config, result):
            product = str(event.get('product') or tr('Unspecified product'))
            rate = _safe_float(event.get('amount'), 0.0)
            total_product = rate * area
            unit_price = _safe_float(fertilizer_prices.get(product), default_price)
            rows.append({
                tr('Plot name'): plot.get('name') or plot.get('id'),
                tr('Area (ha)'): round(area, 2),
                tr('Date'): str(event.get('date', '')),
                tr('Product'): product,
                tr('Rate (kg/ha)'): round(rate, 1),
                tr('Total product (kg)'): round(total_product, 1),
                tr('Estimated cost'): _money(total_product * unit_price + labour_per_day_ha * area, currency),
                tr('Rationale'): tr(str(event.get('rationale') or 'Nutrient stress mitigation')),
            })
    return pd.DataFrame(rows)


def _display_calendar(df, empty_message):
    if df.empty:
        st.info(tr(empty_message))
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_irrigation_calendar(plan, config, result, economic=False):
    st.subheader(tr('Irrigation calendar'))
    if economic:
        action_types = {'cooperative_irrigation'} if result.get('mode') == 'cooperative' else {'irrigation'}
        _render_economic_status(plan, action_types)
    economics = plan.get('economics', {})
    currency = plan.get('currency', 'XAF')
    if result.get('mode') == 'cooperative':
        df = _cooperative_irrigation_schedule_frame(plan.get('opt_plan', {}), config, result, economics, currency)
    else:
        area = _safe_float(config.get('area_ha'), _safe_float(plan.get('summary', {}).get('area_ha'), 1.0))
        schedule = _schedule_within_selected_horizon(plan.get('opt_irr_schedule', []), config, result)
        df = _irrigation_schedule_frame(schedule, area, economics, currency)
    _display_calendar(df, 'No optimized irrigation event is currently recommended for the selected horizon.')


def _render_fertilization_calendar(plan, config, result, economic=False):
    st.subheader(tr('Fertilization calendar'))
    if economic:
        action_types = {'cooperative_fertilization'} if result.get('mode') == 'cooperative' else {'fertilization'}
        _render_economic_status(plan, action_types)
    economics = plan.get('economics', {})
    currency = plan.get('currency', 'XAF')
    if result.get('mode') == 'cooperative':
        df = _cooperative_fertilization_schedule_frame(plan.get('opt_plan', {}), config, result, economics, currency)
    else:
        area = _safe_float(config.get('area_ha'), _safe_float(plan.get('summary', {}).get('area_ha'), 1.0))
        schedule = _schedule_within_selected_horizon(plan.get('opt_fert_schedule', []), config, result)
        df = _fertilization_schedule_frame(schedule, area, economics, currency)
    _display_calendar(df, 'No optimized fertilization event is currently recommended for the selected horizon.')


def _selected_disease_row(config):
    """Return the configured disease metadata when the disease table is loaded."""
    disease_id = config.get('selected_disease_id')
    df = st.session_state.get('df_diseases')
    if not disease_id or df is None or getattr(df, 'empty', True):
        return {}
    try:
        match = df[df['Disease_ID'] == disease_id]
        if match.empty:
            return {}
        return match.iloc[0].to_dict()
    except Exception:
        return {}


def _render_disease_control_details(plan, config, result, economic=False):
    st.subheader(tr('Disease control recommendations'))
    spots = list(config.get('disease_spots', []) or [])
    disease_row = _selected_disease_row(config)
    disease_id = config.get('selected_disease_id')
    if economic:
        if result.get('mode') == 'cooperative':
            st.caption(tr('Cooperative disease control is shown for field validation; the current cooperative economic plan prices shared irrigation, fertilization and labour actions.'))
        else:
            _render_economic_status(plan, {'disease_control'})
    if not disease_id and not spots:
        st.info(tr('No disease target is configured. Keep routine scouting.'))
        return

    action = _action_for_types(plan, {'disease_control'})
    overview = [{
        tr('Selected disease'): disease_row.get('Disease_Name') or disease_id or tr('Automatic detection pending validation'),
        tr('Disease type'): tr(str(disease_row.get('Type') or 'Unknown')),
        tr('Detection date'): str(config.get('detection_date') or tr('Not specified')),
        tr('Mapped disease foci'): len(spots),
        tr('Affected plants'): int(sum(_safe_float(spot.get('plants'), 1.0) for spot in spots)) if spots else 0,
        tr('Estimated cost'): _money(action.get('cost', 0.0), plan.get('currency', 'XAF')) if action else tr('Not priced in this scenario'),
        tr('Economic decision'): tr('Keep') if action.get('economically_selected') else tr('Agronomic only'),
    }]
    st.dataframe(pd.DataFrame(overview), use_container_width=True, hide_index=True)

    methods = str(disease_row.get('Control_Methods') or '').replace('\\n', '\n').split('\n')
    methods = [m.strip() for m in methods if m.strip()]
    if methods:
        st.caption(tr('Control protocols'))
        st.dataframe(pd.DataFrame([{tr('Recommended control step'): tr(method)} for method in methods]), use_container_width=True, hide_index=True)
    else:
        st.caption(tr('Confirm the disease identity in the field before choosing chemical, biological, pruning or roguing interventions.'))

    optimized = (plan.get('scenario_summary', {}) or {}).get('optimized', {})
    if optimized:
        st.caption(tr('Scenario roguing/pruning balance'))
        balance = [{
            tr('Applied probability'): f"{_safe_float(optimized.get('roguing_applied_probability'), 0.0) * 100:.0f}%",
            tr('Yield penalty'): f"{_safe_float(optimized.get('roguing_yield_penalty'), 0.0):.3f} t/ha",
            tr('Inoculum benefit score'): f"{_safe_float(optimized.get('roguing_inoculum_benefit'), 0.0):.3f}",
            tr('Yield cost score'): f"{_safe_float(optimized.get('roguing_yield_cost'), 0.0):.3f}",
        }]
        st.dataframe(pd.DataFrame(balance), use_container_width=True, hide_index=True)
    st.caption(tr('Disease control remains field-validation-first.'))


def _render_recommendation_details(plan, config, result, economic=False):
    st.markdown('### ' + tr('Detailed operational calendars'))
    st.caption(tr('Calendars are displayed for the selected horizon and remain visible even when current prices make an action agronomic-only.'))
    _render_irrigation_calendar(plan, config, result, economic=economic)
    _render_fertilization_calendar(plan, config, result, economic=economic)
    _render_disease_control_details(plan, config, result, economic=economic)


def _compute_recommendations(result, config, max_plots=60):
    """Run the lightweight recommendation workflow with visible spinners."""
    if result.get('mode') == 'cooperative':
        coop_engine = CooperativeSimulationEngine()
        opt_plan = coop_engine.build_optimized_management_plan(config, result, max_plots=int(max_plots))
        plan = build_cooperative_economics(config, result, opt_plan)
        plan['resource_check'] = evaluate_shared_resource_constraints(opt_plan.get('summary', {}), config)
        plan['opt_plan'] = opt_plan
        return plan

    engine = SimulationEngine()
    opt_irr_schedule, _ = engine.optimize_irrigation_schedule(config)
    opt_fert_schedule = engine.optimize_fertilization_schedule(config)
    scenario_summary = engine.run_counterfactual_scenarios(config, n_runs=10)
    plan = build_single_field_economics(config, result, opt_irr_schedule, opt_fert_schedule, scenario_summary)
    plan['opt_irr_schedule'] = opt_irr_schedule
    plan['opt_fert_schedule'] = opt_fert_schedule
    plan['scenario_summary'] = scenario_summary
    return plan


def _render_plan(plan, config, result):
    currency = plan.get('currency', 'XAF')
    summary = plan.get('summary', {})
    economics = plan.get('economics', {})
    st.info(
        f"{tr('Market price used')}: **{float(economics.get('sale_price_per_t', 0.0) or 0.0):,.0f} {currency}/t** | "
        f"{tr('Price source')}: {tr(str(economics.get('price_source', 'manual')))} | "
        f"{tr('Confidence:')} {float(economics.get('price_confidence', 0.0) or 0.0)*100:.0f}%"
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(tr('Horizon'), f"{int(summary.get('economic_horizon_years', 1) or 1)} {tr('years')}")
    c2.metric(tr('Baseline production'), f"{summary.get('baseline_production_t_per_ha', 0.0):.2f} t/ha")
    c3.metric(tr('Agronomic net return/ha'), _money(summary.get('agronomic_net_return_per_ha', summary.get('agronomic_net_gain_per_ha', 0.0)), currency))
    c4.metric(tr('Economic net return/ha'), _money(summary.get('economic_net_return_per_ha', summary.get('economic_net_gain_per_ha', 0.0)), currency))
    c5.metric(tr('Selected economic actions'), int(summary.get('economic_selected_action_count', len(plan.get('selected_actions', []))) or 0))

    tab_summary, tab_agro, tab_econ, tab_actions = st.tabs([tr('Decision summary'), tr('Agronomic optimum'), tr('Economic optimum'), tr('Action list')])
    with tab_summary:
        st.dataframe(_summary_rows(plan), use_container_width=True, hide_index=True)
        for note in plan.get('notes', []):
            st.caption(tr(note))
    with tab_agro:
        st.write(tr('This view keeps actions that maximize stress reduction and production, even when cost is high.'))
        st.dataframe(_actions_frame(plan.get('actions', []), currency), use_container_width=True, hide_index=True)
        _render_recommendation_details(plan, config, result, economic=False)
    with tab_econ:
        st.write(tr('This view shows the strategy with the highest expected total net return among no action, the full agronomic plan and the profitable action subset.'))
        selected = plan.get('selected_actions') or [a for a in plan.get('actions', []) if a.get('economically_selected')]
        if selected:
            st.dataframe(_actions_frame(selected, currency), use_container_width=True, hide_index=True)
        else:
            st.warning(tr('No intervention is economically justified under the current assumptions. Check local prices or keep agronomic actions only if risk reduction is the priority.'))
        _render_recommendation_details(plan, config, result, economic=True)
    with tab_actions:
        st.dataframe(_actions_frame(plan.get('actions', []), currency), use_container_width=True, hide_index=True)
        st.download_button('💾 ' + tr('Download recommendations JSON'), data=json.dumps(plan, indent=2, default=str), file_name='aef_recommendations.json', mime='application/json', use_container_width=True)


def app():
    st.title('🧭 ' + tr('Recommendations'))
    st.caption(tr('Compare no action, the agronomic optimum and the cost-balanced economic optimum.'))
    if 'sim_results' not in st.session_state:
        st.warning(tr('Run the dashboard simulation before opening recommendations.'))
        return

    result = st.session_state['sim_results']
    config = _config_from_state()
    crop_params = result.get('crop_params', {})
    config['economics_config'] = normalize_economics_config(st.session_state.get('economics_config', {}), config, crop_params)

    st.markdown('### ' + tr('Optimization setup'))
    st.caption(tr('Set the economic horizon first, then run the optimization. Nothing is calculated automatically when this page opens.'))
    if str(crop_params.get('Type', 'Annual')) == 'Perennial':
        current_horizon = int(float(config['economics_config'].get('economic_horizon_years', st.session_state.get('economic_horizon_years', 20)) or 20))
        horizon_years = st.number_input(tr('Economic analysis horizon (years)'), min_value=1, max_value=20, value=max(1, min(20, current_horizon)), step=1, key='recommendations_economic_horizon_years')
        st.caption(tr('For perennial crops, revenue is summed over annual harvest peaks within this horizon.'))
    else:
        horizon_years = 1
        st.caption(tr('Annual crop recommendation horizon follows the simulated crop cycle.'))
    config['economics_config']['economic_horizon_years'] = int(horizon_years)
    st.session_state['economic_horizon_years'] = int(horizon_years)
    st.session_state['economics_config'] = config['economics_config']

    if result.get('mode') == 'cooperative':
        parcels = result.get('parcel_results', [])
        max_plots = st.number_input(tr('Maximum plots optimized for recommendations'), min_value=1, max_value=max(1, len(parcels)), value=min(max(1, len(parcels)), 60), step=1)
    else:
        max_plots = 1

    cache_key = 'recommendation_plan'
    cache_signature = {
        'mode': result.get('mode', 'single'),
        'crop': config.get('selected_crop_id'),
        'disease': config.get('selected_disease_id'),
        'spot_count': len(config.get('disease_spots', []) or []),
        'horizon': int(config['economics_config'].get('economic_horizon_years', 1)),
        'max_plots': int(max_plots),
        'economics': json.dumps(config.get('economics_config', {}), sort_keys=True, default=str),
    }
    run_requested = st.button('🔄 ' + tr('Run recommendation optimization'), type='primary', use_container_width=True)
    if run_requested:
        with st.spinner(tr('Calculating agronomic and economic recommendations...')):
            st.session_state[cache_key] = _compute_recommendations(result, config, max_plots=max_plots)
            st.session_state['recommendation_plan_signature'] = cache_signature

    has_current_plan = cache_key in st.session_state and st.session_state.get('recommendation_plan_signature') == cache_signature
    if has_current_plan:
        _render_plan(st.session_state[cache_key], config, result)
    elif cache_key in st.session_state:
        st.warning(tr('Recommendation settings changed. Run the optimization again before using the results.'))
    else:
        st.info(tr('Configure the horizon and click Run recommendation optimization to generate recommendations.'))
