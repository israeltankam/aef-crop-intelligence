# src/utils/recommendation_pdf.py
"""Readable recommendation PDF builder for AEF Crop Intelligence.

The Recommendations page and the final dossier both need the same farmer-facing
presentation: decision summary, economic assumptions, full operational calendars
and disease-control notes.  Keeping the PDF layout here avoids divergent report
logic and makes future recommendation changes easier to propagate.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from fpdf import FPDF

from src.utils.i18n import tr


LOGO_PATH = Path(__file__).resolve().parents[1] / "images" / "logo" / "logo_company" / "logo_scale.png"


def _safe_float(value, default: float = 0.0) -> float:
    """Convert loose model/UI values to a float without breaking PDF generation."""
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _money(value, currency: str) -> str:
    return f"{_safe_float(value):,.0f} {currency}".replace(",", " ")


def _parse_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def _is_perennial(result: Dict[str, object] | None) -> bool:
    crop_params = (result or {}).get("crop_params", {}) or {}
    return str(crop_params.get("Type", "Annual")) == "Perennial"


def _horizon_label(plan: Dict[str, object], result: Dict[str, object] | None) -> str:
    """Return the user-facing horizon rule.

    Annual crops are not user-configurable: the horizon is the simulated crop
    cycle from planting to expected harvest.  Perennials keep the selected
    economic horizon because several harvest periods can occur.
    """
    if not _is_perennial(result):
        crop_params = (result or {}).get("crop_params", {}) or {}
        cycle_days = int(_safe_float(crop_params.get("Cycle_Days"), 0.0))
        return tr("Crop cycle to expected harvest") + (f" ({cycle_days} {tr('days')})" if cycle_days else "")
    summary = plan.get("summary", {}) if plan else {}
    years = int(_safe_float(summary.get("economic_horizon_years", 1), 1.0))
    return f"{years} {tr('years')}"


def _within_selected_horizon(event: Dict[str, object], config: Dict[str, object], result: Dict[str, object] | None, horizon_years: int) -> bool:
    """Keep perennial events inside the economic horizon; annuals keep all events."""
    if not _is_perennial(result):
        return True
    start = _parse_date(config.get("planting_date"))
    event_date = _parse_date(event.get("date"))
    if start is None or event_date is None:
        return True
    return event_date < start + timedelta(days=max(1, horizon_years) * 365)


def _safe_pdf_text(value) -> str:
    """Sanitize strings for the classic pyfpdf latin-1 output backend."""
    text = "" if value is None else str(value)
    replacements = {
        "œ": "oe", "Œ": "OE", "æ": "ae", "Æ": "AE",
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "‑": "-", "−": "-", "…": "...",
        "•": "-", "✓": "OK", "✅": "OK", "⚠️": "!", "⚠": "!",
        "🛰️": "[sat]", "🧭": "[rec]", "🧪": "[what-if]", "🗃️": "[report]",
        "🤝": "[coop]", "🔐": "[login]", "📄": "[pdf]", "💾": "[json]",
        "→": "->", "←": "<-", "≥": ">=", "≤": "<=", "≈": "~",
    }
    replacements[chr(0x202F)] = " "
    replacements[chr(0x00A0)] = " "
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class BrandedRecommendationPDF(FPDF):
    """Small branded PDF wrapper with safe text and a Scale logo header."""

    def __init__(self, title: str):
        super().__init__()
        self.document_title = title
        self.logo_path = str(LOGO_PATH) if LOGO_PATH.exists() else ""
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(12, 22, 12)

    def _txt(self, value) -> str:
        return _safe_pdf_text(value)

    def cell(self, w, h=0, txt="", border=0, ln=0, align="", fill=False, link=""):
        return super().cell(w, h, self._txt(txt), border, ln, align, fill, link)

    def write(self, h, txt="", link=""):
        return super().write(h, self._txt(txt), link)

    def multi_cell(self, w, h, txt="", border=0, align="J", fill=False):
        return super().multi_cell(w, h, self._txt(txt), border, align, fill)

    def header(self):
        # The logo is intentionally non-fatal: old pyfpdf can reject some PNG
        # variants.  A failed logo must not block an agronomic dossier.
        if self.logo_path:
            try:
                self.image(self.logo_path, x=12, y=7, w=22)
            except Exception:
                pass
        self.set_xy(38, 8)
        self.set_font("Arial", "B", 11)
        self.cell(0, 6, self.document_title, 0, 1, "L")
        self.set_x(38)
        self.set_font("Arial", "", 8)
        self.cell(0, 5, f"AEF Crop Intelligence - Scale AG - {date.today()}", 0, 1, "L")
        self.ln(7)

    def footer(self):
        self.set_y(-14)
        self.set_font("Arial", "I", 8)
        self.cell(0, 6, f"Scale AG | AEF Crop Intelligence | {tr('Page')} {self.page_no()}", 0, 0, "R")


def _ensure_space(pdf: FPDF, height: float):
    if pdf.get_y() + height > 275:
        pdf.add_page()


def _fit(pdf: FPDF, value, width: float) -> str:
    text = _safe_pdf_text(value)
    if pdf.get_string_width(text) <= max(1.0, width - 2):
        return text
    while len(text) > 4 and pdf.get_string_width(text + "...") > max(1.0, width - 2):
        text = text[:-1]
    return text + "..."


def _section_title(pdf: FPDF, title: str):
    _ensure_space(pdf, 12)
    pdf.set_fill_color(230, 240, 255)
    pdf.set_text_color(20, 45, 75)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, title, 0, 1, "L", True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)


def _paragraph(pdf: FPDF, text: str, font_size: int = 9):
    pdf.set_font("Arial", "", font_size)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1)


def _key_value_lines(pdf: FPDF, rows: Sequence[tuple[str, str]]):
    pdf.set_font("Arial", "", 9)
    for key, value in rows:
        _ensure_space(pdf, 6)
        pdf.set_font("Arial", "B", 9)
        pdf.cell(48, 5, f"{key}:", 0, 0, "L")
        pdf.set_font("Arial", "", 9)
        pdf.multi_cell(0, 5, str(value))
    pdf.ln(2)


def _table(pdf: FPDF, headers: Sequence[str], widths: Sequence[float], rows: Iterable[Sequence[object]], aligns: Sequence[str] | None = None, row_height: float = 6.0):
    """Draw compact tables with fixed widths so values cannot spill off-page."""
    aligns = aligns or ["L"] * len(widths)
    _ensure_space(pdf, row_height * 2)
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(238, 242, 246)
    for header, width, align in zip(headers, widths, aligns):
        pdf.cell(width, row_height, _fit(pdf, tr(header), width), 1, 0, align, True)
    pdf.ln(row_height)
    pdf.set_font("Arial", "", 8)
    for row in rows:
        _ensure_space(pdf, row_height)
        for value, width, align in zip(row, widths, aligns):
            pdf.cell(width, row_height, _fit(pdf, value, width), 1, 0, align)
        pdf.ln(row_height)
    pdf.ln(3)


def _decision_rows(plan: Dict[str, object]) -> List[List[object]]:
    currency = plan.get("currency", "XAF")
    s = plan.get("summary", {}) or {}
    return [
        [tr("Baseline / no action"), f"{_safe_float(s.get('baseline_production_t')):.2f} t", f"{_safe_float(s.get('baseline_production_t_per_ha')):.2f} t/ha", _money(s.get("baseline_cost_per_ha"), currency), _money(s.get("baseline_net_return_per_ha", s.get("baseline_net_gain_per_ha")), currency), _money(0, currency)],
        [tr("Agronomic optimum"), f"{_safe_float(s.get('agronomic_production_t')):.2f} t", f"{_safe_float(s.get('agronomic_production_t_per_ha')):.2f} t/ha", _money(s.get("agronomic_cost_per_ha"), currency), _money(s.get("agronomic_net_return_per_ha", s.get("agronomic_net_gain_per_ha")), currency), _money(s.get("agronomic_incremental_net_gain"), currency)],
        [tr("Economic optimum"), f"{_safe_float(s.get('economic_production_t')):.2f} t", f"{_safe_float(s.get('economic_production_t_per_ha')):.2f} t/ha", _money(s.get("economic_cost_per_ha"), currency), _money(s.get("economic_net_return_per_ha", s.get("economic_net_gain_per_ha")), currency), _money(s.get("economic_incremental_net_gain"), currency)],
    ]


def _action_rows(actions: Iterable[Dict[str, object]], currency: str) -> List[List[object]]:
    rows = []
    for action in actions or []:
        rows.append([
            tr(str(action.get("title", ""))),
            tr(str(action.get("type", ""))),
            str(action.get("timing", "")),
            _money(action.get("cost"), currency),
            _money(action.get("gross_benefit"), currency),
            f"{_safe_float(action.get('economic_scale'), 1.0 if action.get('economically_selected') else 0.0) * 100:.0f}%",
            tr("Keep") if action.get("economically_selected") else tr("Agronomic only"),
        ])
    return rows


def _single_irrigation_rows(plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object]) -> List[List[object]]:
    economics = plan.get("economics", {}) or {}
    currency = plan.get("currency", economics.get("currency", "XAF"))
    area = max(0.0, _safe_float(config.get("area_ha"), _safe_float(plan.get("summary", {}).get("area_ha"), 1.0)))
    horizon = int(_safe_float(plan.get("summary", {}).get("economic_horizon_years"), 1.0))
    rows = []
    for event in plan.get("opt_irr_schedule", []) or []:
        if not _within_selected_horizon(event, config, result, horizon):
            continue
        amount_mm = _safe_float(event.get("amount"))
        water_m3 = amount_mm * area * 10.0
        cost = water_m3 * _safe_float(economics.get("irrigation_cost_per_m3")) + _safe_float(economics.get("irrigation_labor_cost_per_event"))
        rows.append([str(event.get("date", "")), f"{amount_mm:.1f} mm", f"{water_m3:.1f} m3", _money(cost, currency), tr(str(event.get("reason") or event.get("feasibility_note") or "Stress Mitigation"))])
    return rows


def _single_fertilization_rows(plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object]) -> List[List[object]]:
    economics = plan.get("economics", {}) or {}
    prices = economics.get("fertilizer_prices", {}) or {}
    currency = plan.get("currency", economics.get("currency", "XAF"))
    area = max(0.0, _safe_float(config.get("area_ha"), _safe_float(plan.get("summary", {}).get("area_ha"), 1.0)))
    default_price = _safe_float(economics.get("default_fertilizer_price_per_kg"))
    labour = _safe_float((economics.get("labor_costs", {}) or {}).get("fertilizer_application_day")) * area
    horizon = int(_safe_float(plan.get("summary", {}).get("economic_horizon_years"), 1.0))
    rows = []
    for event in plan.get("opt_fert_schedule", []) or []:
        if not _within_selected_horizon(event, config, result, horizon):
            continue
        product = str(event.get("product") or tr("Unspecified product"))
        rate = _safe_float(event.get("amount"))
        total = rate * area
        cost = total * _safe_float(prices.get(product), default_price) + labour
        rows.append([str(event.get("date", "")), product, f"{rate:.1f} kg/ha", f"{total:.1f} kg", _money(cost, currency), tr(str(event.get("rationale") or "Nutrient stress mitigation"))])
    return rows


def _cooperative_irrigation_rows(plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object]) -> List[List[object]]:
    economics = plan.get("economics", {}) or {}
    currency = plan.get("currency", economics.get("currency", "XAF"))
    cost_per_m3 = _safe_float(economics.get("irrigation_cost_per_m3"))
    labour = _safe_float(economics.get("irrigation_labor_cost_per_event"))
    horizon = int(_safe_float(plan.get("summary", {}).get("economic_horizon_years"), 1.0))
    rows = []
    for plot in (plan.get("opt_plan", {}) or {}).get("rows", []) or []:
        area = _safe_float(plot.get("area_ha"))
        for event in plot.get("irrigation_schedule", []) or []:
            if not _within_selected_horizon(event, config, result, horizon):
                continue
            amount_mm = _safe_float(event.get("amount"))
            water_m3 = amount_mm * area * 10.0
            rows.append([plot.get("name") or plot.get("id"), f"{area:.2f}", str(event.get("date", "")), f"{amount_mm:.1f} mm", f"{water_m3:.1f}", _money(water_m3 * cost_per_m3 + labour, currency), tr(str(event.get("reason") or event.get("feasibility_note") or "Stress Mitigation"))])
    return rows


def _cooperative_fertilization_rows(plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object]) -> List[List[object]]:
    economics = plan.get("economics", {}) or {}
    prices = economics.get("fertilizer_prices", {}) or {}
    currency = plan.get("currency", economics.get("currency", "XAF"))
    default_price = _safe_float(economics.get("default_fertilizer_price_per_kg"))
    labour_per_day_ha = _safe_float((economics.get("labor_costs", {}) or {}).get("fertilizer_application_day"))
    horizon = int(_safe_float(plan.get("summary", {}).get("economic_horizon_years"), 1.0))
    rows = []
    for plot in (plan.get("opt_plan", {}) or {}).get("rows", []) or []:
        area = _safe_float(plot.get("area_ha"))
        for event in plot.get("fertilization_schedule", []) or []:
            if not _within_selected_horizon(event, config, result, horizon):
                continue
            product = str(event.get("product") or tr("Unspecified product"))
            rate = _safe_float(event.get("amount"))
            total = rate * area
            cost = total * _safe_float(prices.get(product), default_price) + labour_per_day_ha * area
            rows.append([plot.get("name") or plot.get("id"), f"{area:.2f}", str(event.get("date", "")), product, f"{rate:.1f}", f"{total:.1f}", _money(cost, currency), tr(str(event.get("rationale") or "Nutrient stress mitigation"))])
    return rows


def _disease_rows(plan: Dict[str, object], config: Dict[str, object]) -> List[List[object]]:
    action = next((a for a in plan.get("actions", []) or [] if str(a.get("type")) == "disease_control"), {})
    spots = list(config.get("disease_spots", []) or [])
    return [[
        str(config.get("selected_disease_id") or tr("Automatic detection pending validation")),
        str(config.get("detection_date") or tr("Not specified")),
        len(spots),
        int(sum(_safe_float(spot.get("plants"), 1.0) for spot in spots)) if spots else 0,
        tr("Keep") if action.get("economically_selected") else tr("Agronomic only"),
        f"{_safe_float(action.get('economic_scale'), 0.0) * 100:.0f}%",
    ]]


def append_recommendation_pdf_sections(pdf: FPDF, plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object] | None, title_prefix: str = ""):
    """Append the full recommendations dossier to an existing PDF object."""
    currency = plan.get("currency", "XAF")
    economics = plan.get("economics", {}) or {}
    summary = plan.get("summary", {}) or {}
    is_cooperative = (result or {}).get("mode") == "cooperative"

    _section_title(pdf, title_prefix + tr("Readable recommendations dossier"))
    _paragraph(pdf, tr("This section is designed for field use. It separates the agronomic optimum from the economic optimum and keeps the full operational calendars visible."))
    _key_value_lines(pdf, [
        (tr("Horizon"), _horizon_label(plan, result)),
        (tr("Market price used"), f"{_money(economics.get('sale_price_per_t'), currency)} / t"),
        (tr("Price source"), tr(str(economics.get("price_source", "manual")))),
        (tr("Price confidence"), f"{_safe_float(economics.get('price_confidence')) * 100:.0f}%"),
    ])

    _section_title(pdf, title_prefix + tr("Decision summary"))
    _table(
        pdf,
        ["Scenario", "Production", "Production/ha", "Cost/ha", "Net return/ha", "Net gain vs baseline"],
        [34, 25, 27, 30, 34, 34],
        _decision_rows(plan),
        ["L", "C", "C", "C", "C", "C"],
    )

    _section_title(pdf, title_prefix + tr("Action list"))
    action_rows = _action_rows(plan.get("actions", []), currency)
    if action_rows:
        _table(pdf, ["Action", "Type", "Timing", "Cost", "Gross benefit", "Economic scale", "Economic decision"], [38, 22, 20, 26, 28, 20, 30], action_rows, ["L", "L", "L", "C", "C", "C", "C"])
    else:
        _paragraph(pdf, tr("No intervention is economically justified under the current assumptions. Check local prices or keep agronomic actions only if risk reduction is the priority."))

    _section_title(pdf, title_prefix + tr("Irrigation calendar"))
    irrigation_rows = _cooperative_irrigation_rows(plan, config, result) if is_cooperative else _single_irrigation_rows(plan, config, result)
    if irrigation_rows:
        if is_cooperative:
            _table(pdf, ["Plot name", "Area (ha)", "Date", "Amount (mm)", "Water volume (m3)", "Estimated cost", "Notes"], [26, 15, 22, 21, 25, 28, 47], irrigation_rows, ["L", "C", "C", "C", "C", "C", "L"])
        else:
            _table(pdf, ["Date", "Amount (mm)", "Water volume (m3)", "Estimated cost", "Notes"], [24, 26, 30, 32, 72], irrigation_rows, ["C", "C", "C", "C", "L"])
    else:
        _paragraph(pdf, tr("No optimized irrigation event is currently recommended for the selected horizon."))

    _section_title(pdf, title_prefix + tr("Fertilization calendar"))
    fertilizer_rows = _cooperative_fertilization_rows(plan, config, result) if is_cooperative else _single_fertilization_rows(plan, config, result)
    if fertilizer_rows:
        if is_cooperative:
            _table(pdf, ["Plot name", "Area (ha)", "Date", "Product", "Rate (kg/ha)", "Total product (kg)", "Estimated cost", "Rationale"], [22, 14, 20, 28, 20, 22, 26, 32], fertilizer_rows, ["L", "C", "C", "L", "C", "C", "C", "L"])
        else:
            _table(pdf, ["Date", "Product", "Rate (kg/ha)", "Total product (kg)", "Estimated cost", "Rationale"], [22, 36, 25, 30, 30, 41], fertilizer_rows, ["C", "L", "C", "C", "C", "L"])
    else:
        _paragraph(pdf, tr("No optimized fertilization event is currently recommended for the selected horizon."))

    _section_title(pdf, title_prefix + tr("Disease control recommendations"))
    if config.get("selected_disease_id") or config.get("disease_spots"):
        _table(pdf, ["Selected disease", "Detection date", "Mapped disease foci", "Affected plants", "Economic decision", "Economic scale"], [40, 27, 28, 25, 32, 25], _disease_rows(plan, config), ["L", "C", "C", "C", "C", "C"])
        _paragraph(pdf, tr("Confirm the disease identity in the field before choosing chemical, biological, pruning or roguing interventions."))
        _paragraph(pdf, tr("Roguing / pruning decision rule: removal is never automatic. Compare the expected inoculum reduction with the yield loss from removing productive plants or canopy."))
    else:
        _paragraph(pdf, tr("No disease target is configured. Keep routine scouting."))

    _section_title(pdf, title_prefix + tr("Operational caution"))
    _paragraph(pdf, tr("These recommendations support decisions; they are not guarantees. Use adaptive surveillance and field observations to reduce uncertainty before costly interventions."))


def build_recommendations_pdf(plan: Dict[str, object], config: Dict[str, object], result: Dict[str, object] | None) -> bytes:
    """Return a farmer-readable PDF for the Recommendations page."""
    pdf = BrandedRecommendationPDF(tr("Recommendations report"))
    pdf.add_page()
    append_recommendation_pdf_sections(pdf, plan, config, result)
    return pdf.output(dest="S").encode("latin-1")
