# src/utils/preassessment_pdf.py
"""Readable PDF dossier for the pre-planting assessment mode."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, Iterable, Sequence

from fpdf import FPDF

from src.utils.i18n import tr


LOGO_PATH = Path(__file__).resolve().parents[1] / "images" / "logo" / "logo_company" / "logo_scale.png"


def _safe_pdf_text(value) -> str:
    """Classic pyfpdf writes latin-1, so sanitize user/report strings."""
    text = "" if value is None else str(value)
    replacements = {
        "œ": "oe", "Œ": "OE", "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", "•": "-", "≥": ">=", "≤": "<=",
        "é": "e", "è": "e", "ê": "e", "à": "a", "ù": "u", "ç": "c",
        "É": "E", "À": "A", "Ç": "C",
    }
    replacements[chr(0x202F)] = " "
    replacements[chr(0x00A0)] = " "
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class PreAssessmentPDF(FPDF):
    """Small branded PDF wrapper with guarded logo rendering."""

    def __init__(self):
        super().__init__()
        self.logo_path = str(LOGO_PATH) if LOGO_PATH.exists() else ""
        self.set_margins(12, 22, 12)
        self.set_auto_page_break(auto=True, margin=16)

    def cell(self, w, h=0, txt="", border=0, ln=0, align="", fill=False, link=""):
        return super().cell(w, h, _safe_pdf_text(txt), border, ln, align, fill, link)

    def multi_cell(self, w, h, txt="", border=0, align="J", fill=False):
        return super().multi_cell(w, h, _safe_pdf_text(txt), border, align, fill)

    def header(self):
        if self.logo_path:
            try:
                self.image(self.logo_path, x=12, y=7, w=22)
            except Exception:
                pass
        self.set_xy(38, 8)
        self.set_font("Arial", "B", 12)
        self.cell(0, 6, tr("Pre-planting assessment report"), 0, 1, "L")
        self.set_x(38)
        self.set_font("Arial", "", 8)
        self.cell(0, 5, f"AEF Crop Intelligence - Scale AG - {date.today()}", 0, 1, "L")
        self.ln(7)

    def footer(self):
        self.set_y(-14)
        self.set_font("Arial", "I", 8)
        self.cell(0, 6, f"Scale AG | AEF Crop Intelligence | {tr('Page')} {self.page_no()}", 0, 0, "R")


def _section(pdf: FPDF, title: str):
    pdf.set_fill_color(230, 240, 255)
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 8, title, 0, 1, "L", True)
    pdf.ln(2)


def _p(pdf: FPDF, text: str, size: int = 9):
    pdf.set_font("Arial", "", size)
    pdf.multi_cell(0, 5, text)
    pdf.ln(1)


def _fit(value, max_len=34):
    text = _safe_pdf_text(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def _table(pdf: FPDF, headers: Sequence[str], widths: Sequence[float], rows: Iterable[Sequence[object]]):
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(238, 242, 246)
    for h, w in zip(headers, widths):
        pdf.cell(w, 6, _fit(tr(h), 24), 1, 0, "C", True)
    pdf.ln(6)
    pdf.set_font("Arial", "", 8)
    for row in rows:
        if pdf.get_y() > 268:
            pdf.add_page()
        for value, w in zip(row, widths):
            pdf.cell(w, 6, _fit(value, 32), 1, 0, "L")
        pdf.ln(6)
    pdf.ln(3)


def _display_text(value) -> str:
    """Translate stable and common dynamic engine text before writing PDFs."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith("Mean temperature "):
        if " °C versus crop optimum " in text:
            left, right = text.replace(".", "").split(" °C versus crop optimum ", 1)
            return f"{tr('Mean temperature')} {left.replace('Mean temperature ', '')} °C {tr('versus crop optimum')} {right} °C."
        if " C versus crop optimum " in text:
            left, right = text.replace(".", "").split(" C versus crop optimum ", 1)
            return f"{tr('Mean temperature')} {left.replace('Mean temperature ', '')} °C {tr('versus crop optimum')} {right} °C."
    if text.startswith("Forecast rain ") and "; estimated crop water demand " in text and "; deficit " in text:
        clean = text.replace(".", "")
        rain, rest = clean.replace("Forecast rain ", "").split(" mm; estimated crop water demand ", 1)
        demand, deficit = rest.split(" mm; deficit ", 1)
        return f"{tr('Forecast rain')} {rain} mm; {tr('estimated crop water demand')} {demand} mm; {tr('deficit')} {deficit} mm."
    if text.startswith("Regional literature prior adjusted by forecast humidity/rainfall; top risk "):
        risk = text.replace("Regional literature prior adjusted by forecast humidity/rainfall; top risk ", "")
        return f"{tr('Regional literature prior adjusted by forecast humidity/rainfall; top risk')} {risk}"
    return tr(text)


def _recommendation_label(code: str) -> str:
    if code == "plant":
        return tr("Recommended to plant")
    if code == "plant_with_caution":
        return tr("Possible with caution")
    return tr("Do not prioritize planting")


def _final_recommendation_text(result: Dict[str, object]) -> str:
    """Return a plain-language final recommendation for the PDF dossier."""
    best = result.get("best", {}) or {}
    score = float(best.get("score", 0.0) or 0.0)
    decision = _recommendation_label(str(result.get("recommendation")))
    date_text = str(best.get("planting_date", ""))
    risks = result.get("disease_risks", []) or []
    top_risk = risks[0].get("disease_name") if risks else tr("no dominant disease prior")
    soil = result.get("soil_summary", {}) or {}
    if score >= 70:
        posture = tr("the site is currently suitable enough to proceed, provided local validation confirms the assumptions")
    elif score >= 55:
        posture = tr("the site can be considered, but only with caution and local validation before investment")
    else:
        posture = tr("the site should not be prioritized for this variety under the current assumptions")
    return tr(
        "Recommendation: {decision}. With a suitability score of {score:.1f}/100, {posture}. The best planting date candidate is {date} using the explicit format YYYY-MM-DD. The main disease-pressure signal is {risk}, and the soil screening score is {soil_score}/100. Before committing, validate the parcel boundary on the satellite map, confirm soil data locally, and use early field surveillance to reduce uncertainty.",
        decision=decision, score=score, posture=posture, date=date_text, risk=top_risk, soil_score=soil.get("score", "n/a")
    )


def build_preassessment_pdf(result: Dict[str, object]) -> bytes:
    """Build a farmer-readable one-cycle pre-assessment PDF."""
    pdf = PreAssessmentPDF()
    pdf.add_page()
    crop = result.get("crop", {}) or {}
    best = result.get("best", {}) or {}

    _section(pdf, tr("Decision summary"))
    _p(pdf, f"{tr('Field')}: {result.get('field_name')} | {tr('Area')}: {result.get('area_ha')} ha | {tr('Region')}: {result.get('region')}")
    _p(pdf, f"{tr('Crop variety')}: {crop.get('Crop_Name')} - {crop.get('Variety')}")
    _p(pdf, f"{tr('Suitability score')}: {best.get('score')}/100 | {tr('Recommendation')}: {_recommendation_label(str(result.get('recommendation')))}")
    _p(pdf, f"{tr('Best planting date (YYYY-MM-DD)')}: {best.get('planting_date')} | {tr('Assessed cycle')}: {result.get('cycle_days_assessed')} {tr('days')}")
    if result.get("perennial_one_cycle_only"):
        _p(pdf, tr("Perennial crop: only one production cycle is assessed in pre-evaluation mode."))

    _section(pdf, tr("Scoring details"))
    component_rows = [[_display_text(c.get("name", "")), c.get("score"), f"{float(c.get('weight', 0))*100:.0f}%", _display_text(c.get("explanation", ""))] for c in best.get("components", [])]
    _table(pdf, ["Component", "Score", "Weight", "Explanation"], [34, 18, 18, 114], component_rows)

    _section(pdf, tr("Planting date candidates"))
    date_rows = [[c.get("planting_date"), c.get("score"), c.get("climate_water", {}).get("rain_mm"), c.get("climate_water", {}).get("deficit_mm"), c.get("disease", {}).get("mean_risk")] for c in result.get("candidate_dates", [])[:12]]
    _p(pdf, tr("All dates use the ISO format YYYY-MM-DD: year-month-day."))
    _table(pdf, ["Planting date (YYYY-MM-DD)", "Score", "Rain mm", "Deficit mm", "Disease risk"], [42, 20, 30, 32, 30], date_rows)

    _section(pdf, tr("Irrigation calendar"))
    irr_rows = [[e.get("date"), e.get("amount_mm"), e.get("water_volume_m3"), _display_text(e.get("reason"))] for e in result.get("irrigation_calendar", [])]
    _table(pdf, ["Date", "Amount mm", "Water m3", "Reason"], [30, 28, 30, 96], irr_rows or [[tr("No event"), "0", "0", tr("Rainfall is expected to cover most water demand for the selected cycle.")]])

    _section(pdf, tr("Fertilization calendar"))
    fert_rows = [[e.get("date"), _display_text(e.get("product")), e.get("rate_kg_ha"), e.get("total_kg"), _display_text(e.get("rationale"))] for e in result.get("fertilization_calendar", [])]
    _table(pdf, ["Date", "Product", "Rate kg/ha", "Total kg", "Rationale"], [26, 46, 26, 26, 60], fert_rows)

    _section(pdf, tr("Disease pressure literature priors"))
    risk_rows = [[r.get("disease_name"), r.get("risk"), r.get("region_scope"), r.get("evidence_level")] for r in result.get("disease_risks", [])]
    _table(pdf, ["Disease", "Risk", "Region", "Evidence"], [62, 20, 72, 30], risk_rows or [[tr("No crop-specific disease prior"), "", "", ""]])
    _p(pdf, tr("Disease pressure is a literature prior adjusted by forecast weather. It must be checked with local surveillance before investment."))

    _section(pdf, tr("Caution"))
    _p(pdf, tr(str(result.get("caution", "Pre-assessment is a planning aid before planting."))))

    _section(pdf, tr("Final recommendation"))
    _p(pdf, _final_recommendation_text(result), size=10)
    return pdf.output(dest="S").encode("latin-1")
