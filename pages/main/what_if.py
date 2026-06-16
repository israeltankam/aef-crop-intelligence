# pages/main/what_if.py
"""Interactive What-if scenario testing for AEF Crop Intelligence.

The page starts from the same optimized calendars used by Recommendations, then
lets the user remove or edit events before running a fast deterministic scenario.
It deliberately avoids ensemble inference here: the goal is an ergonomic decision
sandbox, while heavier uncertainty runs remain in the report workflow.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from typing import Dict, Iterable, List, Tuple

from fpdf import FPDF
import pandas as pd
import streamlit as st

from src.models.state_manager import StateManager
from src.models.simulation_engine import SimulationEngine
from src.models.cooperative_engine import CooperativeSimulationEngine
from src.models.economic_engine import (
    disease_action_cost,
    fertilizer_cost,
    irrigation_cost,
    normalize_economics_config,
    production_tonnes,
    revenue,
)
from src.utils.i18n import tr


IRRIGATION_COLUMNS = ["apply", "plot_id", "plot_name", "date", "amount_mm", "reason"]
FERTILIZATION_COLUMNS = ["apply", "plot_id", "plot_name", "date", "product", "amount_kg_ha", "rationale"]


def _config_from_state() -> Dict[str, object]:
    """Collect the active digital-twin configuration from Streamlit state.

    This mirrors the Recommendations page on purpose: What-if scenarios should be
    a scenario layer on top of the same configured field, not a separate setup
    workflow with subtly different defaults.
    """
    config = {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys() if key in st.session_state}

    def schedule_records(value):
        return value.to_dict("records") if value is not None and not getattr(value, "empty", True) else []

    config["fert_schedule"] = schedule_records(st.session_state.get("fert_schedule"))
    config["irr_schedule"] = schedule_records(st.session_state.get("irr_schedule"))
    if st.session_state.get("soil_layers") is not None:
        config["soil_layers"] = st.session_state["soil_layers"].to_dict("records")
    else:
        config["soil_layers"] = []
    config["initial_soil_water"] = st.session_state.get("initial_soil_water", 0.5)
    config["planting_date"] = st.session_state.get("planting_date", date.today())
    return config


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _money(value, currency: str) -> str:
    return f"{_safe_float(value):,.0f} {currency}".replace(",", " ")


def _parse_date(value):
    try:
        parsed = pd.to_datetime(value)
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _horizon_years(config: Dict[str, object], crop_params: Dict[str, object]) -> int:
    """Return the user-visible economic horizon for scenario summaries."""
    if str(crop_params.get("Type", "Annual")) != "Perennial":
        return 1
    economics = config.get("economics_config", {}) or {}
    raw = economics.get("economic_horizon_years", config.get("economic_horizon_years", 20))
    return max(1, min(20, int(_safe_float(raw, 20.0))))


def _within_horizon(event: Dict[str, object], config: Dict[str, object], crop_params: Dict[str, object]) -> bool:
    """Keep long perennial calendars aligned with the selected report horizon."""
    if str(crop_params.get("Type", "Annual")) != "Perennial":
        return True
    start = _parse_date(config.get("planting_date"))
    event_date = _parse_date(event.get("date"))
    if start is None or event_date is None:
        return True
    return event_date < start + timedelta(days=_horizon_years(config, crop_params) * 365)


def _empty_irrigation_df() -> pd.DataFrame:
    return pd.DataFrame(columns=IRRIGATION_COLUMNS)


def _empty_fertilization_df() -> pd.DataFrame:
    return pd.DataFrame(columns=FERTILIZATION_COLUMNS)


def _schedule_signature(config: Dict[str, object], result: Dict[str, object], max_plots: int) -> Dict[str, object]:
    """Small cache key so optimal calendars are refreshed only when needed."""
    economics = config.get("economics_config", {}) or {}
    return {
        "mode": result.get("mode", "single"),
        "crop": config.get("selected_crop_id"),
        "planting_date": str(config.get("planting_date")),
        "horizon": int(economics.get("economic_horizon_years", config.get("economic_horizon_years", 1)) or 1),
        "max_plots": int(max_plots),
        "spots": len(config.get("disease_spots", []) or []),
    }


def _optimal_inputs(config: Dict[str, object], result: Dict[str, object], max_plots: int = 60) -> Dict[str, object]:
    """Build editable starting calendars from the current optimized management."""
    crop_params = result.get("crop_params", {}) or {}
    if result.get("mode") == "cooperative":
        coop_engine = CooperativeSimulationEngine()
        opt_plan = coop_engine.build_optimized_management_plan(config, result, max_plots=max_plots)
        irrigation_rows: List[Dict[str, object]] = []
        fertilization_rows: List[Dict[str, object]] = []
        for plot in opt_plan.get("rows", []) or []:
            for event in plot.get("irrigation_schedule", []) or []:
                if not _within_horizon(event, config, crop_params):
                    continue
                irrigation_rows.append({
                    "apply": True,
                    "plot_id": plot.get("id", ""),
                    "plot_name": plot.get("name", plot.get("id", "")),
                    "date": _parse_date(event.get("date")) or event.get("date"),
                    "amount_mm": round(_safe_float(event.get("amount")), 2),
                    "reason": str(event.get("reason") or event.get("feasibility_note") or "Stress Mitigation"),
                })
            for event in plot.get("fertilization_schedule", []) or []:
                if not _within_horizon(event, config, crop_params):
                    continue
                fertilization_rows.append({
                    "apply": True,
                    "plot_id": plot.get("id", ""),
                    "plot_name": plot.get("name", plot.get("id", "")),
                    "date": _parse_date(event.get("date")) or event.get("date"),
                    "product": str(event.get("product") or ""),
                    "amount_kg_ha": round(_safe_float(event.get("amount")), 2),
                    "rationale": str(event.get("rationale") or "Nutrient stress mitigation"),
                })
        return {
            "mode": "cooperative",
            "opt_plan": opt_plan,
            "irrigation": pd.DataFrame(irrigation_rows, columns=IRRIGATION_COLUMNS) if irrigation_rows else _empty_irrigation_df(),
            "fertilization": pd.DataFrame(fertilization_rows, columns=FERTILIZATION_COLUMNS) if fertilization_rows else _empty_fertilization_df(),
        }

    engine = SimulationEngine()
    opt_irrigation, _ = engine.optimize_irrigation_schedule(config)
    opt_fertilization = engine.optimize_fertilization_schedule(config)
    irrigation_rows = []
    for event in opt_irrigation or []:
        if _within_horizon(event, config, crop_params):
            irrigation_rows.append({
                "apply": True,
                "plot_id": "single",
                "plot_name": config.get("field_name", "Field"),
                "date": _parse_date(event.get("date")) or event.get("date"),
                "amount_mm": round(_safe_float(event.get("amount")), 2),
                "reason": str(event.get("reason") or event.get("feasibility_note") or "Stress Mitigation"),
            })
    fertilization_rows = []
    for event in opt_fertilization or []:
        if _within_horizon(event, config, crop_params):
            fertilization_rows.append({
                "apply": True,
                "plot_id": "single",
                "plot_name": config.get("field_name", "Field"),
                "date": _parse_date(event.get("date")) or event.get("date"),
                "product": str(event.get("product") or ""),
                "amount_kg_ha": round(_safe_float(event.get("amount")), 2),
                "rationale": str(event.get("rationale") or "Nutrient stress mitigation"),
            })
    return {
        "mode": "single",
        "opt_plan": None,
        "irrigation": pd.DataFrame(irrigation_rows, columns=IRRIGATION_COLUMNS) if irrigation_rows else _empty_irrigation_df(),
        "fertilization": pd.DataFrame(fertilization_rows, columns=FERTILIZATION_COLUMNS) if fertilization_rows else _empty_fertilization_df(),
    }


def _editor_column_config(economics: Dict[str, object], product_values: Iterable[str] | None = None) -> Tuple[Dict[str, object], Dict[str, object]]:
    """Centralise labels so the data editors stay fully internationalised."""
    fertilizer_options = sorted(set((economics.get("fertilizer_prices", {}) or {}).keys()) | {str(p) for p in (product_values or []) if str(p).strip()})
    irrigation_config = {
        "apply": st.column_config.CheckboxColumn(tr("Apply"), help=tr("Uncheck to remove this event from the scenario.")),
        "plot_id": None,
        "plot_name": st.column_config.TextColumn(tr("Plot name")),
        "date": st.column_config.DateColumn(tr("Date")),
        "amount_mm": st.column_config.NumberColumn(tr("Amount (mm)"), min_value=0.0, step=1.0),
        "reason": st.column_config.TextColumn(tr("Notes")),
    }
    fertilization_config = {
        "apply": st.column_config.CheckboxColumn(tr("Apply"), help=tr("Uncheck to remove this event from the scenario.")),
        "plot_id": None,
        "plot_name": st.column_config.TextColumn(tr("Plot name")),
        "date": st.column_config.DateColumn(tr("Date")),
        "product": st.column_config.SelectboxColumn(tr("Product"), options=fertilizer_options) if fertilizer_options else st.column_config.TextColumn(tr("Product")),
        "amount_kg_ha": st.column_config.NumberColumn(tr("Rate (kg/ha)"), min_value=0.0, step=5.0),
        "rationale": st.column_config.TextColumn(tr("Rationale")),
    }
    return irrigation_config, fertilization_config


def _clean_irrigation_events(df: pd.DataFrame, cooperative: bool = False) -> List[Dict[str, object]]:
    """Convert the editable table back to SimulationEngine irrigation events."""
    if df is None or df.empty:
        return []
    events: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        if row.get("apply") is False:
            continue
        amount = _safe_float(row.get("amount_mm"), 0.0)
        event_date = _parse_date(row.get("date"))
        if amount <= 0 or event_date is None:
            continue
        event = {"date": str(event_date), "amount": amount, "reason": str(row.get("reason") or "What-if scenario")}
        if cooperative:
            event["plot_id"] = str(row.get("plot_id") or "")
            event["plot_name"] = str(row.get("plot_name") or event["plot_id"])
        events.append(event)
    return events


def _clean_fertilization_events(df: pd.DataFrame, cooperative: bool = False) -> List[Dict[str, object]]:
    """Convert the editable table back to SimulationEngine fertilization events."""
    if df is None or df.empty:
        return []
    events: List[Dict[str, object]] = []
    for _, row in df.iterrows():
        if row.get("apply") is False:
            continue
        amount = _safe_float(row.get("amount_kg_ha"), 0.0)
        event_date = _parse_date(row.get("date"))
        product = str(row.get("product") or "").strip()
        if amount <= 0 or event_date is None or not product:
            continue
        event = {"date": str(event_date), "product": product, "amount": amount, "rationale": str(row.get("rationale") or "What-if scenario")}
        if cooperative:
            event["plot_id"] = str(row.get("plot_id") or "")
            event["plot_name"] = str(row.get("plot_name") or event["plot_id"])
        events.append(event)
    return events


def _group_events_by_plot(events: Iterable[Dict[str, object]]) -> Dict[str, List[Dict[str, object]]]:
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for event in events or []:
        plot_id = str(event.get("plot_id") or "")
        stripped = {k: v for k, v in event.items() if k not in {"plot_id", "plot_name"}}
        grouped.setdefault(plot_id, []).append(stripped)
    return grouped


def _scenario_config(base_config: Dict[str, object], irrigation_events, fertilization_events, disease_control: bool) -> Dict[str, object]:
    cfg = deepcopy(base_config)
    cfg["irr_schedule"] = list(irrigation_events or [])
    cfg["fert_schedule"] = list(fertilization_events or [])
    has_disease_target = bool(cfg.get("selected_disease_id")) or bool(cfg.get("disease_spots"))
    cfg["disease_control_strategy"] = "optimized" if disease_control and has_disease_target else "none"
    return cfg


def _scenario_cost(config: Dict[str, object], result: Dict[str, object], irrigation_events, fertilization_events, disease_control: bool) -> float:
    economics = config.get("economics_config", {}) or {}
    crop_params = result.get("crop_params", {}) if result else {}
    area = max(0.0, _safe_float(config.get("area_ha"), 1.0))
    disease_cost = disease_action_cost(config, area, economics, crop_params) if disease_control else 0.0
    return irrigation_cost(irrigation_events, area, economics) + fertilizer_cost(fertilization_events, area, economics) + disease_cost


def _summary_row(label: str, run_result: Dict[str, object], config: Dict[str, object], cost: float, baseline_net: float | None = None) -> Dict[str, object]:
    economics = config.get("economics_config", {}) or {}
    currency = economics.get("currency", "XAF")
    crop_params = run_result.get("crop_params", {}) if run_result else {}
    horizon = _horizon_years(config, crop_params)
    area = max(0.01, _safe_float(config.get("area_ha"), 1.0))
    production = production_tonnes(run_result, config, horizon)
    gross = revenue(production, economics)
    net = gross - max(0.0, cost)
    history = run_result.get("history", []) if run_result else []
    final_incidence = _safe_float(history[-1].get("Incidence"), 0.0) if history else 0.0
    row = {
        "scenario": label,
        "production_t": production,
        "production_t_ha": production / area,
        "revenue": gross,
        "cost": cost,
        "net_return": net,
        "net_delta": 0.0 if baseline_net is None else net - baseline_net,
        "final_incidence": final_incidence,
        "horizon_years": horizon,
        "currency": currency,
    }
    return row


def _display_summary(summary: List[Dict[str, object]], currency: str) -> pd.DataFrame:
    rows = []
    for row in summary:
        rows.append({
            tr("Scenario"): tr(row["scenario"]),
            tr("Production"): f"{row['production_t']:.2f} t",
            tr("Production/ha"): f"{row['production_t_ha']:.2f} t/ha",
            tr("Revenue"): _money(row["revenue"], currency),
            tr("Cost"): _money(row["cost"], currency),
            tr("Net return"): _money(row["net_return"], currency),
            tr("Net gain vs no action"): _money(row["net_delta"], currency),
            tr("Final disease incidence"): f"{row['final_incidence'] * 100:.1f}%",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    return df


def _run_single_scenario(config: Dict[str, object], result: Dict[str, object], irrigation_events, fertilization_events, disease_control: bool) -> Dict[str, object]:
    """Run no-action, optimized and user-edited scenarios for one field."""
    engine = SimulationEngine()
    optimal_inputs = st.session_state.get("what_if_optimal_inputs", {})
    optimal_irrigation = _clean_irrigation_events(optimal_inputs.get("irrigation", _empty_irrigation_df()))
    optimal_fertilization = _clean_fertilization_events(optimal_inputs.get("fertilization", _empty_fertilization_df()))

    no_action_cfg = _scenario_config(config, [], [], False)
    optimal_cfg = _scenario_config(config, optimal_irrigation, optimal_fertilization, True)
    edited_cfg = _scenario_config(config, irrigation_events, fertilization_events, disease_control)

    no_action_run = engine.run_simulation(no_action_cfg)
    optimal_run = engine.run_simulation(optimal_cfg)
    edited_run = engine.run_simulation(edited_cfg)
    if no_action_run is None or optimal_run is None or edited_run is None:
        raise RuntimeError("Scenario simulation failed")

    no_action = _summary_row("No action", no_action_run, no_action_cfg, 0.0)
    optimal_cost = _scenario_cost(optimal_cfg, optimal_run, optimal_irrigation, optimal_fertilization, True)
    optimal = _summary_row("Optimized management", optimal_run, optimal_cfg, optimal_cost, no_action["net_return"])
    edited_cost = _scenario_cost(edited_cfg, edited_run, irrigation_events, fertilization_events, disease_control)
    edited = _summary_row("Edited what-if scenario", edited_run, edited_cfg, edited_cost, no_action["net_return"])
    return {"summary": [no_action, optimal, edited], "scenario_config": edited_cfg, "mode": "single"}


def _baseline_cooperative_production(result: Dict[str, object], config: Dict[str, object], coop_engine: CooperativeSimulationEngine) -> float:
    total = 0.0
    for parcel in result.get("parcel_results", []) or []:
        crop_params = parcel.get("crop_params", result.get("crop_params", {})) or {}
        horizon = _horizon_years(config, crop_params)
        total += coop_engine._harvest_equivalent_yield_t_ha(parcel.get("history", []), crop_params, horizon) * _safe_float(parcel.get("area_ha"), 0.0)
    return total


def _cooperative_summary_row(label: str, production: float, total_area: float, economics: Dict[str, object], cost: float, final_incidence: float, baseline_net: float | None = None) -> Dict[str, object]:
    gross = revenue(production, economics)
    net = gross - max(0.0, cost)
    return {
        "scenario": label,
        "production_t": production,
        "production_t_ha": production / max(0.01, total_area),
        "revenue": gross,
        "cost": cost,
        "net_return": net,
        "net_delta": 0.0 if baseline_net is None else net - baseline_net,
        "final_incidence": final_incidence,
        "horizon_years": int(economics.get("economic_horizon_years", 1) or 1),
        "currency": economics.get("currency", "XAF"),
    }


def _run_cooperative_scenario(config: Dict[str, object], result: Dict[str, object], irrigation_events, fertilization_events, disease_control: bool) -> Dict[str, object]:
    """Run edited schedules on optimized cooperative plots and keep others baseline.

    The dashboard may contain many small plots. To keep What-if interactive, the
    scenario re-simulates only the plots that were selected for optimized planning;
    untouched plots retain their current no-action baseline. This mirrors the
    cooperative Recommendations scope note and avoids surprising long runtimes.
    """
    coop_engine = CooperativeSimulationEngine()
    optimal_inputs = st.session_state.get("what_if_optimal_inputs", {})
    opt_plan = optimal_inputs.get("opt_plan", {}) or {}
    selected_rows = opt_plan.get("rows", []) or []
    selected_ids = {str(row.get("id")) for row in selected_rows}
    parcels = {str(p.get("id")): p for p in config.get("cooperative_parcels", []) if p.get("active", True) and p.get("coords")}
    baseline_by_id = {str(p.get("id")): p for p in result.get("parcel_results", []) or []}
    crop_params = result.get("crop_params", {}) or {}
    economics = config.get("economics_config", {}) or {}
    total_area = max(0.01, _safe_float(result.get("total_area_ha"), config.get("area_ha", 1.0)))
    baseline_total = _baseline_cooperative_production(result, config, coop_engine)
    baseline_incidence = _safe_float((result.get("history", []) or [{}])[-1].get("Incidence"), 0.0)

    grouped_irrigation = _group_events_by_plot(irrigation_events)
    grouped_fertilization = _group_events_by_plot(fertilization_events)
    optimal_irrigation = _clean_irrigation_events(optimal_inputs.get("irrigation", _empty_irrigation_df()), cooperative=True)
    optimal_fertilization = _clean_fertilization_events(optimal_inputs.get("fertilization", _empty_fertilization_df()), cooperative=True)

    baseline_selected = 0.0
    optimal_selected = 0.0
    scenario_selected = 0.0
    scenario_incidence_weighted = 0.0
    selected_area = 0.0
    scenario_cost = 0.0

    for plan_row in selected_rows:
        plot_id = str(plan_row.get("id"))
        parcel = parcels.get(plot_id)
        if parcel is None:
            continue
        base_parcel = baseline_by_id.get(plot_id, {})
        area = _safe_float(plan_row.get("area_ha"), base_parcel.get("area_ha", 0.0))
        baseline_selected += _safe_float(plan_row.get("baseline_yield_t_ha"), 0.0) * area
        optimal_selected += _safe_float(plan_row.get("optimized_yield_t_ha"), 0.0) * area

        parcel_cfg = coop_engine._parcel_config(config, parcel)
        parcel_irrigation = grouped_irrigation.get(plot_id, [])
        parcel_fertilization = grouped_fertilization.get(plot_id, [])
        parcel_cfg = _scenario_config(parcel_cfg, parcel_irrigation, parcel_fertilization, disease_control)
        run = coop_engine.single_engine.run_simulation(parcel_cfg)
        if run and run.get("history"):
            scenario_selected += production_tonnes(run, parcel_cfg, _horizon_years(parcel_cfg, run.get("crop_params", crop_params)))
            scenario_incidence_weighted += _safe_float(run["history"][-1].get("Incidence"), 0.0) * area
        else:
            scenario_selected += _safe_float(plan_row.get("baseline_yield_t_ha"), 0.0) * area
        selected_area += area
        scenario_cost += _scenario_cost(parcel_cfg, run or {"crop_params": crop_params}, parcel_irrigation, parcel_fertilization, disease_control)

    optimal_cost = 0.0
    for plot_id in selected_ids:
        parcel = parcels.get(plot_id)
        if parcel is None:
            continue
        parcel_cfg = coop_engine._parcel_config(config, parcel)
        opt_irr = [e for e in optimal_irrigation if str(e.get("plot_id")) == plot_id]
        opt_fert = [e for e in optimal_fertilization if str(e.get("plot_id")) == plot_id]
        optimal_cost += _scenario_cost(parcel_cfg, {"crop_params": crop_params}, _group_events_by_plot(opt_irr).get(plot_id, []), _group_events_by_plot(opt_fert).get(plot_id, []), True)

    optimal_total = baseline_total - baseline_selected + optimal_selected
    scenario_total = baseline_total - baseline_selected + scenario_selected
    no_action = _cooperative_summary_row("No action", baseline_total, total_area, economics, 0.0, baseline_incidence)
    optimal = _cooperative_summary_row("Optimized management", optimal_total, total_area, economics, optimal_cost, baseline_incidence, no_action["net_return"])
    scenario_incidence = scenario_incidence_weighted / max(0.01, selected_area) if selected_area else baseline_incidence
    edited = _cooperative_summary_row("Edited what-if scenario", scenario_total, total_area, economics, scenario_cost, scenario_incidence, no_action["net_return"])
    return {"summary": [no_action, optimal, edited], "mode": "cooperative", "scope_note": opt_plan.get("scope_note", "")}


def _safe_pdf_text(value) -> str:
    """Make text safe for pyfpdf's latin-1 output backend."""
    text = str(value)
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u0153": "oe",
        "\u0152": "OE",
        "\u2026": "...",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


def _scenario_pdf(summary: List[Dict[str, object]], irrigation_events, fertilization_events, disease_control: bool, currency: str) -> bytes:
    """Create a concise PDF scenario report without adding new dependencies."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 9, _safe_pdf_text(tr("What-if scenario report")), ln=1)
    pdf.set_font("Arial", "", 10)
    pdf.multi_cell(0, 6, _safe_pdf_text(tr("This report compares no action, optimized management and the edited scenario using the current deterministic digital twin.")))
    pdf.ln(2)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, _safe_pdf_text(tr("Scenario outcomes")), ln=1)
    pdf.set_font("Arial", "", 9)
    for row in summary:
        line = (
            f"{tr(row['scenario'])}: {row['production_t']:.2f} t | "
            f"{tr('Net return')}: {_money(row['net_return'], currency)} | "
            f"{tr('Net gain vs no action')}: {_money(row['net_delta'], currency)} | "
            f"{tr('Final disease incidence')}: {row['final_incidence'] * 100:.1f}%"
        )
        pdf.multi_cell(0, 5, _safe_pdf_text(line))
    pdf.ln(2)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, _safe_pdf_text(tr("Edited scenario inputs")), ln=1)
    pdf.set_font("Arial", "", 9)
    pdf.multi_cell(0, 5, _safe_pdf_text(f"{tr('Disease control')}: {tr('Applied') if disease_control else tr('Removed')}"))
    pdf.multi_cell(0, 5, _safe_pdf_text(f"{tr('Irrigation events')}: {len(irrigation_events or [])}"))
    for event in list(irrigation_events or [])[:45]:
        pdf.multi_cell(0, 5, _safe_pdf_text(f"- {event.get('plot_name', '')} {event.get('date')}: {event.get('amount')} mm"))
    pdf.multi_cell(0, 5, _safe_pdf_text(f"{tr('Fertilization events')}: {len(fertilization_events or [])}"))
    for event in list(fertilization_events or [])[:45]:
        pdf.multi_cell(0, 5, _safe_pdf_text(f"- {event.get('plot_name', '')} {event.get('date')}: {event.get('product')} {event.get('amount')} kg/ha"))
    pdf.ln(2)
    pdf.set_font("Arial", "I", 8)
    pdf.multi_cell(0, 5, _safe_pdf_text(tr("The scenario report is a decision-support comparison, not a guarantee. Adaptive field observations should be used to reduce uncertainty.")))
    return pdf.output(dest="S").encode("latin-1")


def _render_editors(optimal_inputs: Dict[str, object], economics: Dict[str, object]) -> Tuple[pd.DataFrame, pd.DataFrame, bool]:
    """Show ergonomic editors for calendars and disease-control inclusion."""
    fert_source = optimal_inputs.get("fertilization", _empty_fertilization_df())
    product_values = fert_source["product"].dropna().tolist() if "product" in fert_source else []
    irrigation_config, fertilization_config = _editor_column_config(economics, product_values)
    cooperative = optimal_inputs.get("mode") == "cooperative"
    disabled_cols = ["plot_id", "plot_name"] if cooperative else ["plot_id", "plot_name"]
    st.markdown("### " + tr("Edit the scenario"))
    st.caption(tr("Start from the optimized plan, then uncheck, delete or edit events before running the scenario."))
    irr_df = st.data_editor(
        optimal_inputs.get("irrigation", _empty_irrigation_df()),
        key="what_if_irrigation_editor",
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config=irrigation_config,
        disabled=disabled_cols,
    )
    fert_df = st.data_editor(
        optimal_inputs.get("fertilization", _empty_fertilization_df()),
        key="what_if_fertilization_editor",
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config=fertilization_config,
        disabled=disabled_cols,
    )
    disease_default = bool(st.session_state.get("selected_disease_id")) or bool(st.session_state.get("disease_spots"))
    disease_control = st.checkbox(tr("Apply optimized disease control in this scenario"), value=disease_default, help=tr("Uncheck to test the scenario without the disease-control action."))
    return irr_df, fert_df, disease_control


def app():
    st.title("🧪 " + tr("What-if scenarios"))
    st.caption(tr("Edit optimized calendars and immediately compare yield and economic return against no action."))
    if "sim_results" not in st.session_state:
        st.warning(tr("Run the dashboard simulation before opening scenario testing."))
        return

    result = st.session_state["sim_results"]
    config = _config_from_state()
    crop_params = result.get("crop_params", {}) or {}
    config["economics_config"] = normalize_economics_config(st.session_state.get("economics_config", {}), config, crop_params)

    st.markdown("### " + tr("Scenario setup"))
    st.caption(tr("Set the horizon first, then generate the optimized starting plan. Nothing is calculated automatically when this page opens."))
    if str(crop_params.get("Type", "Annual")) == "Perennial":
        current_horizon = int(_safe_float(config["economics_config"].get("economic_horizon_years", st.session_state.get("economic_horizon_years", 20)), 20.0))
        horizon_years = st.number_input(tr("Economic analysis horizon (years)"), min_value=1, max_value=20, value=max(1, min(20, current_horizon)), step=1, key="what_if_economic_horizon_years")
    else:
        horizon_years = 1
        st.caption(tr("Annual crop scenario horizon follows the simulated crop cycle."))
    config["economics_config"]["economic_horizon_years"] = int(horizon_years)
    st.session_state["economic_horizon_years"] = int(horizon_years)
    st.session_state["economics_config"] = config["economics_config"]
    currency = config["economics_config"].get("currency", "XAF")

    if result.get("mode") == "cooperative":
        parcels = result.get("parcel_results", []) or []
        max_plots = st.number_input(tr("Maximum plots optimized for scenario testing"), min_value=1, max_value=max(1, len(parcels)), value=min(max(1, len(parcels)), 30), step=1)
    else:
        max_plots = 1

    signature = _schedule_signature(config, result, int(max_plots))
    prepare_clicked = st.button("🔄 " + tr("Generate optimized starting plan"), type="primary", use_container_width=True)
    if prepare_clicked:
        with st.spinner(tr("Preparing optimized calendars for scenario editing...")):
            st.session_state["what_if_optimal_inputs"] = _optimal_inputs(config, result, int(max_plots))
            st.session_state["what_if_signature"] = signature
            st.session_state.pop("what_if_last_result", None)

    has_current_inputs = "what_if_optimal_inputs" in st.session_state and st.session_state.get("what_if_signature") == signature
    if not has_current_inputs:
        if "what_if_optimal_inputs" in st.session_state:
            st.warning(tr("Scenario settings changed. Generate the optimized starting plan again before editing."))
        else:
            st.info(tr("Configure the horizon and click Generate optimized starting plan to begin scenario testing."))
        return

    optimal_inputs = st.session_state.get("what_if_optimal_inputs", {})
    irr_df, fert_df, disease_control = _render_editors(optimal_inputs, config["economics_config"])
    cooperative = result.get("mode") == "cooperative"
    irrigation_events = _clean_irrigation_events(irr_df, cooperative=cooperative)
    fertilization_events = _clean_fertilization_events(fert_df, cooperative=cooperative)

    c1, c2, c3 = st.columns(3)
    c1.metric(tr("Irrigation events"), len(irrigation_events))
    c2.metric(tr("Fertilization events"), len(fertilization_events))
    c3.metric(tr("Disease control"), tr("Applied") if disease_control else tr("Removed"))

    if st.button("▶ " + tr("Run what-if scenario"), type="primary", use_container_width=True):
        with st.spinner(tr("Simulating the edited scenario and economic return...")):
            try:
                if cooperative:
                    scenario = _run_cooperative_scenario(config, result, irrigation_events, fertilization_events, disease_control)
                else:
                    scenario = _run_single_scenario(config, result, irrigation_events, fertilization_events, disease_control)
                st.session_state["what_if_last_result"] = scenario
            except Exception as exc:
                st.error(tr("Scenario simulation failed. Please check edited dates, quantities and field configuration."))
                st.caption(str(exc))
                return

    scenario = st.session_state.get("what_if_last_result")
    if scenario:
        st.markdown("### " + tr("Scenario outcomes"))
        summary_df = _display_summary(scenario.get("summary", []), currency)
        if scenario.get("scope_note"):
            st.caption(tr(str(scenario.get("scope_note"))))
        payload = {
            "summary": scenario.get("summary", []),
            "irrigation_events": irrigation_events,
            "fertilization_events": fertilization_events,
            "disease_control": disease_control,
        }
        st.download_button(
            "💾 " + tr("Download scenario JSON"),
            data=json.dumps(payload, indent=2, default=str),
            file_name="aef_what_if_scenario.json",
            mime="application/json",
            use_container_width=True,
        )
        pdf_bytes = _scenario_pdf(scenario.get("summary", []), irrigation_events, fertilization_events, disease_control, currency)
        st.download_button(
            "📄 " + tr("Download scenario PDF"),
            data=pdf_bytes,
            file_name="aef_what_if_scenario.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.caption(tr("The scenario report is a decision-support comparison, not a guarantee. Adaptive field observations should be used to reduce uncertainty."))
