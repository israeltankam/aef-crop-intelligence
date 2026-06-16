# pages\main\report.py
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from fpdf import FPDF
from datetime import date
import tempfile
import os
import matplotlib.tri as mtri
import re
from src.models.simulation_engine import SimulationEngine
from src.models.cooperative_engine import CooperativeSimulationEngine
from src.models.state_manager import StateManager
from src.utils.i18n import t, tr, get_language
from src.utils.decision_support import build_decision_snapshot
from src.models.model_validity import model_validity_impact_cards
from src.models.operational_constraints import annotate_irrigation_schedule, fertilizer_totals_by_product
from src.models.cooperative_constraints import evaluate_shared_resource_constraints
from src.models.economic_engine import build_single_field_economics, build_cooperative_economics
from src.utils.diagnostic_quality import build_diagnostic_quality
from src.utils.disease_evidence import build_disease_evidence
from google.oauth2.service_account import Credentials
import ee


REPORT_FR_SENTENCES = {
    "Remove symptomatic plants only when clustered incidence and expected inoculum reduction exceed stand-loss penalty.": "Supprimer les plants symptomatiques seulement lorsque l'incidence est groupée et que la réduction attendue de l'inoculum dépasse la perte de peuplement.",
    "Plant certified virus-free cuttings of resistant or tolerant cultivars such as TME 419.": "Planter des boutures certifiées sans virus de cultivars résistants ou tolérants, par exemple TME 419.",
    "Manage Bemisia tabaci pressure and avoid stem movement from infected fields.": "Gérer la pression de Bemisia tabaci et éviter le déplacement de tiges depuis des parcelles infectées.",
    "Use certified virus-free cuttings and restrict stem movement from hotspots.": "Utiliser des boutures certifiées sans virus et limiter les mouvements de tiges depuis les zones à forte pression.",
    "Prioritize tolerant cultivars and early harvest where root necrosis risk is high.": "Privilégier les cultivars tolérants et une récolte précoce lorsque le risque de nécrose racinaire est élevé.",
    "Rogue heavily symptomatic plants only when stand-loss penalty is lower than expected inoculum reduction.": "Éliminer les plants très symptomatiques seulement lorsque la perte de peuplement est inférieure à la réduction attendue de l'inoculum.",
    "Increase spacing and reduce humid canopy periods.": "Augmenter l'espacement et réduire les périodes d'humidité dans la canopée.",
    "Remove severely cankered stems and sanitize tools.": "Retirer les tiges fortement chancrées et désinfecter les outils.",
    "Use copper-based fungicide only when field scouting confirms progressive lesions.": "Utiliser un fongicide cuprique seulement lorsque la prospection confirme des lésions progressives.",
    "Use healthy planting material and rotate away from infected residue.": "Utiliser du matériel de plantation sain et pratiquer une rotation éloignée des résidus infectés.",
    "Avoid field operations when foliage is wet.": "Éviter les opérations au champ lorsque le feuillage est humide.",
    "Remove highly infected plants when disease foci are localized.": "Retirer les plants fortement infectés lorsque les foyers sont localisés.",
    "Plant resistant varieties and avoid late planting in high leafhopper periods.": "Planter des variétés résistantes et éviter les semis tardifs pendant les périodes de forte pression de cicadelles.",
    "Destroy volunteer cereals and grassy reservoirs around the field.": "Détruire les céréales spontanées et les réservoirs graminéens autour de la parcelle.",
    "Use vector control only when scouting confirms high pressure early in crop growth.": "Utiliser la lutte contre les vecteurs seulement lorsque la prospection confirme une forte pression en début de croissance.",
    "Use tolerant hybrids and residue management where maize follows maize.": "Utiliser des hybrides tolérants et gérer les résidus lorsque le maïs suit le maïs.",
    "Apply fungicide only when lesions appear before tasseling and weather remains wet.": "Appliquer un fongicide seulement si les lésions apparaissent avant la panicule et que le temps reste humide.",
    "Balance nitrogen to avoid dense over-humid canopies.": "Équilibrer l'azote pour éviter des canopées trop denses et humides.",
    "Rotate crops and manage infected residue in conservation systems.": "Pratiquer la rotation des cultures et gérer les résidus infectés dans les systèmes de conservation.",
    "Use resistant hybrids when available.": "Utiliser des hybrides résistants lorsqu'ils sont disponibles.",
    "Time fungicide to protect upper leaves if disease develops before silking.": "Positionner le fongicide pour protéger les feuilles supérieures si la maladie se développe avant la floraison femelle.",
    "Use certified clean seed and avoid planting into known MLN hotspots.": "Utiliser des semences certifiées saines et éviter les semis dans les zones connues à forte pression MLN.",
    "Control volunteer maize and synchronize planting windows.": "Contrôler les repousses de maïs et synchroniser les fenêtres de semis.",
    "Use vector management only as part of an integrated package.": "N'utiliser la gestion des vecteurs que dans le cadre d'une stratégie intégrée.",
    "Use tolerant hybrids and monitor regional rust alerts.": "Utiliser des hybrides tolérants et suivre les alertes régionales de rouille.",
    "Apply fungicide if rust arrives before grain fill and humid weather persists.": "Appliquer un fongicide si la rouille arrive avant le remplissage des grains et que le temps humide persiste.",
    "Prioritize early warning because wind dispersal can jump beyond field scale.": "Prioriser l'alerte précoce, car la dispersion par le vent peut dépasser l'échelle de la parcelle.",
    "Use resistant varieties and clean seed systems.": "Utiliser des variétés résistantes et des systèmes de semences saines.",
    "Manage whitefly pressure early, especially near alternate hosts.": "Gérer tôt la pression des aleurodes, surtout près des hôtes alternatifs.",
    "Avoid unnecessary late nitrogen that prolongs tender growth attractive to vectors.": "Éviter les apports tardifs inutiles d'azote qui prolongent une croissance tendre attractive pour les vecteurs.",
    "Use resistant cultivars and acid-delinted clean seed.": "Utiliser des cultivars résistants et des semences saines délintage acide.",
    "Avoid working fields when canopy is wet.": "Éviter les interventions lorsque la canopée est humide.",
    "Destroy infected residue where disease pressure was high.": "Détruire les résidus infectés lorsque la pression de maladie a été forte.",
    "Harvest and remove infected pods frequently to reduce sporulation.": "Récolter et retirer fréquemment les cabosses infectées afin de réduire la sporulation.",
    "Improve pruning and shade management to reduce persistent wetness.": "Améliorer la taille et la gestion de l'ombrage pour réduire l'humidité persistante.",
    "Use targeted copper/fungicide protection in peak rainfall periods.": "Utiliser une protection ciblée au cuivre ou fongicide pendant les périodes de pluies maximales.",
    "Confirm suspected cases before tree removal because roguing permanently removes productive trees.": "Confirmer les cas suspects avant l'abattage, car le roguing supprime définitivement des arbres productifs.",
    "Remove infected trees and nearby high-risk contacts only under official control guidance.": "Retirer les arbres infectés et les contacts proches à haut risque uniquement selon les consignes officielles de lutte.",
    "Use resistant/tolerant planting material and manage mealybug/ant complexes.": "Utiliser du matériel végétal résistant ou tolérant et gérer les complexes cochenilles/fourmis.",
    "Prune infected brooms during dry periods and remove inoculum from the plot.": "Tailler les balais infectés pendant les périodes sèches et retirer l'inoculum de la parcelle.",
    "Improve canopy aeration and sanitation.": "Améliorer l'aération de la canopée et l'assainissement.",
    "Use resistant material where available.": "Utiliser du matériel résistant lorsqu'il est disponible.",
    "Use resistant wheat varieties and monitor regional rust races.": "Utiliser des variétés de blé résistantes et surveiller les races régionales de rouille.",
    "Protect upper leaves with fungicide if rust appears before heading.": "Protéger les feuilles supérieures avec un fongicide si la rouille apparaît avant l'épiaison.",
    "Avoid excessive nitrogen that increases canopy susceptibility.": "Éviter l'excès d'azote qui accroît la sensibilité de la canopée.",
    "Use resistant varieties and residue/rotation management.": "Utiliser des variétés résistantes et gérer les résidus et la rotation.",
    "Apply fungicide to protect flag leaf when risk is high.": "Appliquer un fongicide pour protéger la feuille drapeau lorsque le risque est élevé.",
    "Avoid very dense canopies that retain leaf wetness.": "Éviter les canopées très denses qui maintiennent l'humidité foliaire.",
    "Avoid flowering during wet, warm windows where sowing-date optimization can help.": "Éviter la floraison pendant les fenêtres chaudes et humides lorsque l'optimisation de la date de semis peut aider.",
    "Use tolerant varieties and rotate away from maize/wheat residue where possible.": "Utiliser des variétés tolérantes et éviter les précédents maïs/blé lorsque c'est possible.",
    "Apply flowering-stage fungicide only when risk forecast is high.": "Appliquer un fongicide au stade floraison seulement lorsque la prévision de risque est élevée.",
    "Use varieties with effective stem-rust resistance genes for the region.": "Utiliser des variétés portant des gènes efficaces de résistance à la rouille noire pour la région.",
    "Monitor national rust surveillance alerts and act early.": "Suivre les alertes nationales de surveillance des rouilles et agir tôt.",
    "Apply fungicide only when early infection risk and crop value justify treatment.": "Appliquer un fongicide seulement lorsque le risque d'infection précoce et la valeur de la culture justifient le traitement.",
    "Use resistant varieties and balanced nitrogen.": "Utiliser des variétés résistantes et une fertilisation azotée équilibrée.",
    "Maintain water management that avoids drought stress in susceptible stages.": "Maintenir une gestion de l'eau qui évite le stress hydrique aux stades sensibles.",
    "Use fungicide only for high-risk leaf or neck blast windows.": "Utiliser un fongicide seulement pendant les fenêtres à haut risque de pyriculariose foliaire ou du cou.",
    "Use resistant varieties and clean seed.": "Utiliser des variétés résistantes et des semences saines.",
    "Avoid clipping seedlings and operations that wound wet leaves.": "Éviter la coupe des plantules et les opérations qui blessent les feuilles humides.",
    "Optimize nitrogen to avoid excessive susceptibility.": "Optimiser l'azote pour éviter une sensibilité excessive.",
    "Use resistant varieties and synchronize planting to reduce vector carryover.": "Utiliser des variétés résistantes et synchroniser les semis pour réduire le relais des vecteurs.",
    "Remove volunteer rice and grassy hosts.": "Retirer les repousses de riz et les hôtes graminéens.",
    "Use vector control only when early leafhopper pressure is documented.": "Utiliser la lutte contre les vecteurs seulement lorsque la pression précoce de cicadelles est documentée.",
    "Avoid excessive nitrogen and overly dense stands.": "Éviter l'excès d'azote et les peuplements trop denses.",
    "Use water and canopy management to reduce humid contact spread.": "Utiliser la gestion de l'eau et de la canopée pour réduire la propagation par contact humide.",
    "Apply fungicide only where lower-sheath lesions progress before heading.": "Appliquer un fongicide seulement là où les lésions des gaines inférieures progressent avant l'épiaison.",
    "Use resistant or tolerant varieties where available and monitor regional spore alerts.": "Utiliser des variétés résistantes ou tolérantes lorsqu'elles sont disponibles et suivre les alertes régionales de spores.",
    "Apply fungicide protectively when rust is detected nearby and canopy remains wet.": "Appliquer un fongicide en protection lorsque la rouille est détectée à proximité et que la canopée reste humide.",
    "Avoid late-season canopy humidity when management allows.": "Éviter l'humidité de canopée en fin de saison lorsque la gestion le permet.",
    "Use virus-free seed and resistant varieties.": "Utiliser des semences sans virus et des variétés résistantes.",
    "Manage aphid pressure early and remove volunteer soybean.": "Gérer tôt la pression des pucerons et retirer les repousses de soja.",
    "Avoid seed production from symptomatic fields.": "Éviter la production de semences à partir de parcelles symptomatiques.",
    "Use resistant varieties and rotate away from soybean residue.": "Utiliser des variétés résistantes et éviter les résidus de soja dans la rotation.",
    "Use fungicide only when susceptible variety and wet weather create high risk.": "Utiliser un fongicide seulement lorsqu'une variété sensible et un temps humide créent un risque élevé.",
    "Avoid saving seed from infected fields.": "Éviter de conserver des semences provenant de parcelles infectées.",
    "Use resistant cultivars where available and manage shade to avoid persistent leaf wetness.": "Utiliser des cultivars résistants lorsqu'ils sont disponibles et gérer l'ombrage pour éviter l'humidité foliaire persistante.",
    "Apply fungicide or biocontrol only when rust risk is high and economic threshold is met.": "Appliquer un fongicide ou un biocontrôle seulement lorsque le risque de rouille est élevé et que le seuil économique est atteint.",
    "Use pruning to remove heavily affected canopy while accounting for lost productive leaf area.": "Utiliser la taille pour retirer la canopée fortement atteinte tout en tenant compte de la perte de surface foliaire productive.",
    "Use resistant cultivars and prune to improve aeration.": "Utiliser des cultivars résistants et tailler pour améliorer l'aération.",
    "Remove infected berries where feasible.": "Retirer les baies infectées lorsque c'est faisable.",
    "Protect susceptible berry stages during cool wet periods.": "Protéger les stades sensibles des baies pendant les périodes fraîches et humides.",
    "Avoid pruning or harvesting during wet conditions.": "Éviter la taille ou la récolte en conditions humides.",
    "Use windbreaks where wind-driven rain is recurrent.": "Utiliser des brise-vent là où les pluies battantes sont récurrentes.",
    "Remove severely affected shoots while accounting for canopy loss.": "Retirer les pousses sévèrement atteintes tout en tenant compte de la perte de canopée."
}

REPORT_FR_SENTENCES.update({
    "Roguing / pruning decision rule: removal is never automatic. The scenario engine compares the expected gain from lower inoculum with the yield loss caused by removing productive plants or canopy. For annual crops, removal is considered only when the focus is localized and the epidemiological gain exceeds stand loss. For perennial crops, tree removal or severe pruning carries a durable yield cost and is recommended only with a stricter benefit margin and field confirmation.": "Règle de décision roguing/taille : la suppression n'est jamais automatique. Le moteur de scénarios compare le gain attendu lié à la baisse de l'inoculum avec la perte de rendement causée par la suppression de plantes productives ou de canopée. Pour les annuelles, la suppression n'est envisagée que si le foyer est localisé et que le gain épidémiologique dépasse la perte de peuplement. Pour les vivaces, l'abattage d'arbres ou la taille sévère entraîne un coût durable de rendement et n'est recommandé qu'avec une marge de bénéfice plus stricte et une confirmation au champ.",
    "**Roguing / pruning decision rule:** removal is never automatic. The scenario engine compares the expected gain from lower inoculum with the yield loss caused by removing productive plants or canopy. For annual crops, removal is considered only when the focus is localized and the epidemiological gain exceeds stand loss. For perennial crops, tree removal or severe pruning carries a durable yield cost and is recommended only with a stricter benefit margin and field confirmation.": "**Règle de décision roguing/taille :** la suppression n'est jamais automatique. Le moteur de scénarios compare le gain attendu lié à la baisse de l'inoculum avec la perte de rendement causée par la suppression de plantes productives ou de canopée. Pour les annuelles, la suppression n'est envisagée que si le foyer est localisé et que le gain épidémiologique dépasse la perte de peuplement. Pour les vivaces, l'abattage d'arbres ou la taille sévère entraîne un coût durable de rendement et n'est recommandé qu'avec une marge de bénéfice plus stricte et une confirmation au champ."
})


def _translate_months_for_report(text):
    for month in ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]:
        text = re.sub(rf"\b{month}\b", tr(month), text)
    return text


def _translate_report_generated_text(value):
    """Translate model-generated PDF prose without changing internal model values."""
    if value is None:
        return ""
    text = str(value)
    if get_language() != "fr":
        return text

    for source, translated in REPORT_FR_SENTENCES.items():
        text = text.replace(source, translated)

    dynamic_patterns = [
        (r"High Nitrogen demand \((\d+)kg/ha deficit\) for vegetative growth\.", r"Forte demande en azote (\1 kg/ha de déficit) pour la croissance végétative."),
        (r"Phosphorus boost \((\d+)kg/ha deficit\) for root/fruit support\.", r"Renfort en phosphore (\1 kg/ha de déficit) pour soutenir racines et fruits."),
        (r"Potassium correction \((\d+)kg/ha deficit\) for stress tolerance\.", r"Correction potassique (\1 kg/ha de déficit) pour la tolérance au stress."),
        (r"Balanced nutrition required to maintain soil fertility\.", r"Nutrition équilibrée requise pour maintenir la fertilité du sol."),
        (r"No suitable fertilizer product matched the current deficit vector\.", r"Aucun engrais disponible ne correspond correctement au profil de déficit actuel."),
        (r"Product profile matches the N-P-K deficit pattern at about (\d+)%; dose is set by the limiting nutrient and should be checked against local availability\.", r"Le profil du produit correspond au déficit N-P-K à environ \1 %; la dose est fixée par le nutriment limitant et doit être vérifiée selon la disponibilité locale."),
        (r"Optimal Planting: \*\*(.*?)\*\* \(Harvest in (.*?)\)\.", lambda m: f"{tr('Optimal Planting')}: **{_translate_months_for_report(m.group(1))}** ({tr('Harvest in')} {_translate_months_for_report(m.group(2))})."),
        (r"Rationale: Maximizes vegetative rainfall while targeting a harvest month with \*\*(\d+)mm\*\* rain \(Limit: (\d+)mm\)\.", lambda m: f"{tr('Rationale')}: {tr('Maximizes vegetative rainfall while targeting a harvest month with')} **{m.group(1)} mm** {tr('rain')} ({tr('Limit')}: {m.group(2)} mm)."),
        (r"Status: Safe\.", lambda m: f"{tr('Status')}: {tr('Safe')}."),
        (r"Status: Risk \(Wet Harvest\)\.", lambda m: f"{tr('Status')}: {tr('Risk (Wet Harvest)')}."),
    ]
    for pattern, replacement in dynamic_patterns:
        text = re.sub(pattern, replacement, text)
    return _translate_months_for_report(text)


def _translate_product_name(name):
    """Translate generic product descriptors while preserving NPK formulas."""
    if name is None:
        return ""
    text = tr(str(name))
    if get_language() == "fr":
        text = text.replace("(Soluble)", "(soluble)")
        text = text.replace("(Compound)", "(composé)")
        text = text.replace("(Blended)", "(mélangé)")
        text = text.replace("(Granular)", "(granulé)")
    return text


def _fmt_label(label, value):
    return f"{tr(label)}: {value}"


def _report_config_snapshot():
    """Build a serialisable configuration snapshot for report caveats.

    PDF generation can be launched long after setup.  Pulling the same saved
    fields used by the JSON export keeps uncertainty, disease evidence and
    cooperative feasibility messages consistent across dashboard and dossier.
    """
    return {key: st.session_state.get(key) for key in StateManager.DEFAULTS.keys()}


def _report_disease_name():
    dis_id = st.session_state.get('selected_disease_id')
    df = st.session_state.get('df_diseases')
    if dis_id and df is not None and dis_id in df['Disease_ID'].values:
        return df[df['Disease_ID'] == dis_id].iloc[0]['Disease_Name']
    return None


def _resource_feasibility_text(resource_check):
    limits_known = any(float(resource_check.get(k, 0.0) or 0.0) > 0 for k in ['water_limit_m3', 'fertilizer_limit_kg', 'labour_limit_days'])
    if not limits_known:
        return tr('Shared resource limits were not supplied; cooperative feasibility remains unverified.')
    if resource_check.get('resource_feasible'):
        return tr('Supplied shared resource limits are consistent with the optimized cooperative plan.')
    return tr('The optimized cooperative plan exceeds at least one supplied shared resource limit; treat the constrained gain as the safer planning figure.')


def _money(value, currency):
    """Format money in a compact, PDF-safe way.

    The economics module can use XAF, USD or EUR.  The report keeps formatting
    simple because pyfpdf does not handle all currency symbols reliably; ISO codes
    are clearer and safer for bilingual dossiers.
    """
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{amount:,.0f} {currency}"


def _economic_summary_lines(economic_plan):
    """Return concise prose explaining economic assumptions and caution level."""
    summary = economic_plan.get('summary', {}) if economic_plan else {}
    economics = economic_plan.get('economics', {}) if economic_plan else {}
    currency = economic_plan.get('currency', economics.get('currency', 'XAF'))
    confidence_pct = float(summary.get('price_confidence', economics.get('price_confidence', 0.0)) or 0.0) * 100
    return [
        f"{tr('Economic analysis horizon')}: {int(summary.get('economic_horizon_years', economics.get('economic_horizon_years', 1)) or 1)} {tr('years')}",
        f"{tr('Market price used')}: {_money(economics.get('sale_price_per_t', 0.0), currency)} / t ({tr(str(economics.get('price_source', 'manual')))}, {confidence_pct:.0f}% {tr('confidence')})",
        f"{tr('Agronomic optimum net return')}: {_money(summary.get('agronomic_net_return', summary.get('agronomic_net_gain', 0.0)), currency)} ({_money(summary.get('agronomic_net_return_per_ha', summary.get('agronomic_net_gain_per_ha', 0.0)), currency)}/ha)",
        f"{tr('Economic optimum net return')}: {_money(summary.get('economic_net_return', summary.get('economic_net_gain', 0.0)), currency)} ({_money(summary.get('economic_net_return_per_ha', summary.get('economic_net_gain_per_ha', 0.0)), currency)}/ha)",
        tr('Economic optimum is selected by highest expected total net return among no action, full agronomic management and the profitable action subset.'),
    ]


def _add_economic_summary_table(pdf, economic_plan):
    """Add the no-action / agronomic / economic comparison table to the PDF.

    This table is intentionally small: the full cost editor lives in setup and the
    interactive recommendation page.  The dossier should make the decision logic
    auditable without turning the PDF into an accounting spreadsheet.
    """
    summary = economic_plan.get('summary', {}) if economic_plan else {}
    currency = economic_plan.get('currency', 'XAF') if economic_plan else 'XAF'
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(42, 7, tr('Strategy'), 1, 0, 'L', 1)
    pdf.cell(30, 7, tr('Production'), 1, 0, 'C', 1)
    pdf.cell(31, 7, tr('Production/ha'), 1, 0, 'C', 1)
    pdf.cell(36, 7, tr('Cost/ha'), 1, 0, 'C', 1)
    pdf.cell(42, 7, tr('Net return/ha'), 1, 1, 'C', 1)
    pdf.set_font('Arial', '', 8)
    rows = [
        (tr('No action baseline'), summary.get('baseline_production_t', 0.0), summary.get('baseline_production_t_per_ha', 0.0), summary.get('baseline_cost_per_ha', 0.0), _money(summary.get('baseline_net_return_per_ha', summary.get('baseline_net_gain_per_ha', 0.0)), currency)),
        (tr('Agronomic optimum'), summary.get('agronomic_production_t', 0.0), summary.get('agronomic_production_t_per_ha', 0.0), summary.get('agronomic_cost_per_ha', 0.0), _money(summary.get('agronomic_net_return_per_ha', summary.get('agronomic_net_gain_per_ha', 0.0)), currency)),
        (tr('Economic optimum'), summary.get('economic_production_t', 0.0), summary.get('economic_production_t_per_ha', 0.0), summary.get('economic_cost_per_ha', 0.0), _money(summary.get('economic_net_return_per_ha', summary.get('economic_net_gain_per_ha', 0.0)), currency)),
    ]
    for label, production_t, production_t_ha, cost_value_ha, net_value_ha in rows:
        pdf.cell(42, 7, str(label)[:24], 1, 0, 'L')
        pdf.cell(30, 7, f"{float(production_t or 0.0):.2f} t", 1, 0, 'C')
        pdf.cell(31, 7, f"{float(production_t_ha or 0.0):.2f} t/ha", 1, 0, 'C')
        pdf.cell(36, 7, _money(cost_value_ha, currency), 1, 0, 'C')
        pdf.cell(42, 7, str(net_value_ha)[:24], 1, 1, 'C')
    pdf.ln(4)


def _add_economic_action_table(pdf, economic_plan):
    """List intervention families retained or deferred by the economic screen."""
    actions = economic_plan.get('actions', []) if economic_plan else []
    currency = economic_plan.get('currency', 'XAF') if economic_plan else 'XAF'
    if not actions:
        pdf.chapter_body(tr('No economic action could be evaluated from the available recommendation schedules.'))
        return
    pdf.set_font('Arial', 'B', 8)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(62, 7, tr('Action'), 1, 0, 'L', 1)
    pdf.cell(34, 7, tr('Cost'), 1, 0, 'C', 1)
    pdf.cell(34, 7, tr('Gross benefit'), 1, 0, 'C', 1)
    pdf.cell(22, 7, tr('ROI'), 1, 0, 'C', 1)
    pdf.cell(32, 7, tr('Economic decision'), 1, 1, 'C', 1)
    pdf.set_font('Arial', '', 8)
    for action in actions[:10]:
        decision = tr('Keep') if action.get('economically_selected') else tr('Defer')
        pdf.cell(62, 7, tr(str(action.get('title', '')))[:36], 1, 0, 'L')
        pdf.cell(34, 7, _money(action.get('cost', 0.0), currency), 1, 0, 'C')
        pdf.cell(34, 7, _money(action.get('gross_benefit', 0.0), currency), 1, 0, 'C')
        pdf.cell(22, 7, f"{float(action.get('roi', 0.0) or 0.0):.2f}", 1, 0, 'C')
        pdf.cell(32, 7, decision, 1, 1, 'C')
    pdf.ln(4)


class PDFReport(FPDF):
    @staticmethod
    def _safe_pdf_text(value):
        """Return text that pyfpdf can encode with its latin-1 backend.

        The current dependency is the classic fpdf package, whose page buffer is
        encoded as latin-1 during output(). French UI strings can contain glyphs
        outside latin-1, such as oe ligatures, typographic apostrophes, en dashes
        and narrow no-break spaces. Sanitising at the PDF boundary keeps the app
        translated without changing agronomic content or simulation logic.
        """
        if value is None:
            return ""
        text = str(value)
        replacements = {
            "œ": "oe",
            "Œ": "OE",
            "æ": "ae",
            "Æ": "AE",
            "’": "'",
            "‘": "'",
            "´": "'",
            "`": "'",
            "“": "\"",
            "”": "\"",
            "–": "-",
            "—": "-",
            "‑": "-",
            "−": "-",
            "…": "...",
            "•": "-",
            "✓": "OK",
            "✅": "OK",
            "⚠️": "!",
            "⚠": "!",
            "🛑": "!",
            "→": "->",
            "←": "<-",
            "≥": ">=",
            "≤": "<=",
            "≈": "~",
        }
        replacements[chr(0x202F)] = " "
        replacements[chr(0x00A0)] = " "
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text.encode("latin-1", "replace").decode("latin-1")

    def cell(self, w, h=0, txt="", border=0, ln=0, align="", fill=False, link=""):
        return super().cell(w, h, self._safe_pdf_text(txt), border, ln, align, fill, link)

    def write(self, h, txt="", link=""):
        return super().write(h, self._safe_pdf_text(txt), link)

    def multi_cell(self, w, h, txt="", border=0, align="J", fill=False):
        return super().multi_cell(w, h, self._safe_pdf_text(txt), border, align, fill)

    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, tr('AlphaEarth Intelligence Dossier'), 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f"{tr('Generated')}: {date.today()}", 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f"{tr('Page')} {self.page_no()}", 0, 0, 'R')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(230, 240, 255)
        self.cell(0, 8, f'  {label}', 0, 1, 'L', 1)
        self.ln(4)

    def chapter_body(self, txt):
        txt = txt.replace('\\n', '\n')
        lines = txt.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                self.ln(4) 
                continue
            
            is_bullet = False
            if line.startswith('- ') or line.startswith('* '):
                is_bullet = True
                line = line[2:] 
            
            if is_bullet:
                self.set_font('Arial', 'B', 14) 
                self.cell(6, 5, chr(149), 0, 0, 'R') 
                self.set_font('Arial', '', 10)
            else:
                self.set_font('Arial', '', 10)

            parts = line.split('**')
            for i, part in enumerate(parts):
                if not part: continue
                if i % 2 == 1:
                    self.set_font('Arial', 'B', 10)
                else:
                    self.set_font('Arial', '', 10)
                self.write(5, part)
            self.ln(6)

    def add_plot_to_pdf(self, fig):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            fig.savefig(tmp.name, bbox_inches='tight', dpi=150)
            self.image(tmp.name, w=170)
            os.unlink(tmp.name)
        self.ln(5)

# --- HELPER: NDVI FETCH ---
def fetch_sentinel_ndvi(coords, start_date, end_date):
    if start_date > end_date: return pd.DataFrame(columns=['Date', 'NDVI'])

    if not st.session_state.get('ee_initialized'):
        try:
            if 'gcp_service_account' in st.secrets:
                service_account_info = st.secrets["gcp_service_account"]
                scopes = ['https://www.googleapis.com/auth/earthengine']
                creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
                ee.Initialize(credentials=creds)
                st.session_state['ee_initialized'] = True
        except:
            return None

    try:
        ee_coords = [[p[1], p[0]] for p in coords]
        geom = ee.Geometry.Polygon([ee_coords])
        
        def mask_s2_clouds(image):
            qa = image.select('QA60')
            cloud_bit_mask = 1 << 10
            cirrus_bit_mask = 1 << 11
            mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
            return image.updateMask(mask).divide(10000).copyProperties(image, ["system:time_start"])

        s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')\
            .filterDate(str(start_date), str(end_date))\
            .filterBounds(geom)\
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))\
            .map(mask_s2_clouds)
        
        def get_ndvi(image):
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            stats = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=geom, scale=20)
            return ee.Feature(None, {'date': image.date().format('YYYY-MM-dd'), 'ndvi': stats.get('NDVI')})
            
        count = s2.size().getInfo()
        if count == 0: return pd.DataFrame(columns=['Date', 'NDVI'])
        
        ndvi_series = s2.map(get_ndvi).reduceColumns(ee.Reducer.toList(2), ['date', 'ndvi']).getInfo()['list']
        df = pd.DataFrame(ndvi_series, columns=['Date', 'NDVI'])
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.dropna()
        return df.sort_values('Date')
    except Exception as e:
        return None


def render_cooperative_report(res_single):
    """Generate an optimized PDF dossier for cooperative mode."""
    st.title('🤝 ' + tr('Cooperative report'))
    st.caption(tr('The cooperative mode treats each plot as a local patch and links plots through distance-weighted infection pressure.'))
    parcels = res_single.get('parcel_results', [])
    detail_options = ['quick', 'balanced', 'complete']
    detail_labels = {'quick': tr('Quick'), 'balanced': tr('Balanced'), 'complete': tr('Complete')}
    current_detail = st.session_state.get('report_detail_level', 'balanced')
    if current_detail not in detail_options:
        current_detail = 'balanced'
    detail_level = st.radio(tr('Report detail level'), detail_options, index=detail_options.index(current_detail), horizontal=True, format_func=lambda x: detail_labels[x], key='coop_report_detail_level')
    st.session_state['report_detail_level'] = detail_level
    if parcels:
        detail_limit = {'quick': min(20, len(parcels)), 'balanced': min(60, len(parcels)), 'complete': len(parcels)}[detail_level]
        default_limit = max(1, detail_limit)
    else:
        default_limit = 1
    max_opt_plots = st.number_input(
        tr('Maximum plots optimized in this report'),
        min_value=1,
        max_value=max(1, len(parcels)),
        value=default_limit,
        step=1,
        help=tr('For very large cooperatives, optimize the highest-risk plots first to keep the report responsive.')
    ) if parcels else 1
    estimated_seconds = max(8, int(float(max_opt_plots) * 2.5)) if parcels else 8
    st.caption(tr('Estimated generation time: about {seconds} seconds depending on plot count and weather cache.', seconds=estimated_seconds))
    st.caption(tr('The PDF compares the current no-action trajectory with optimized irrigation and fertilization by plot.'))
    crop_params = res_single.get('crop_params', {}) if isinstance(res_single, dict) else {}
    if str(crop_params.get('Type', 'Annual')) == 'Perennial':
        coop_horizon_years = st.number_input(tr('Economic analysis horizon (years)'), min_value=1, max_value=20, value=int(st.session_state.get('economic_horizon_years', 20) or 20), step=1, key='coop_report_economic_horizon_years')
        st.caption(tr('For perennial crops, revenue is summed over annual harvest peaks within this horizon.'))
        st.session_state['economic_horizon_years'] = int(coop_horizon_years)
    else:
        coop_horizon_years = 1

    if st.button('📄 ' + tr('Download PDF Dossier'), type='primary'):
        config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
        config['cooperative_parcels'] = st.session_state.get('cooperative_parcels', [])
        config['cooperative_perimeter_coords'] = st.session_state.get('cooperative_perimeter_coords', [])
        config['economic_horizon_years'] = int(coop_horizon_years)
        if not isinstance(config.get('economics_config'), dict):
            config['economics_config'] = {}
        config['economics_config']['economic_horizon_years'] = int(coop_horizon_years)
        get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
        config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
        config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
        if st.session_state.get('soil_layers') is not None:
            config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
        else:
            config['soil_layers'] = []

        with st.spinner(tr('Optimizing cooperative irrigation and fertilization plot by plot...')):
            coop_engine = CooperativeSimulationEngine()
            opt_plan = coop_engine.build_optimized_management_plan(config, res_single, max_plots=int(max_opt_plots))

        with st.spinner(t('report.spinner.economics')):
            economic_plan = build_cooperative_economics(config, res_single, opt_plan)

        pdf = PDFReport()
        pdf.add_page()
        history = res_single.get('history', [])
        parcels = res_single.get('parcel_results', [])
        df = pd.DataFrame(history)
        final = df.iloc[-1] if not df.empty else {}
        opt_summary = opt_plan.get('summary', {})
        opt_rows = opt_plan.get('rows', [])
        resource_check = evaluate_shared_resource_constraints(opt_summary, config)
        constrained_gain_t = float(opt_summary.get('production_gain_t', 0.0) or 0.0) * float(resource_check.get('resource_factor', 1.0) or 1.0)
        diagnostic_quality = build_diagnostic_quality(config, res_single)
        disease_evidence = build_disease_evidence(config, _report_disease_name())

        pdf.chapter_title('0. ' + tr('Executive decision summary'))
        exec_lines = [
            f"{tr('Diagnostic quality score')}: {diagnostic_quality['overall_score']:.1f}% - {tr(diagnostic_quality['label'])}",
            f"{tr('Next best measurement')}: {tr(diagnostic_quality['next_best_measurement'])}",
            f"{tr('Disease evidence status')}: {tr(disease_evidence['interpretation'])}",
            f"{tr('Resource feasibility')}: {_resource_feasibility_text(resource_check)}",
        ]
        exec_lines.extend(_economic_summary_lines(economic_plan))
        for card in model_validity_impact_cards(res_single.get('growth_model'), res_single.get('disease_model'), bool(st.session_state.get('satellite_anomaly_date'))):
            exec_lines.append(f"- {tr(card['area'])} - {tr(card['level'])}: {tr(card['decision_impact'])}")
        pdf.chapter_body(chr(10).join(exec_lines))

        pdf.chapter_title('1. ' + tr('Cooperative perimeter summary'))
        summary_lines = [
            f"{tr('Cooperative name')}: {st.session_state.get('cooperative_name', '')}",
            f"{tr('Active plots')}: {res_single.get('parcel_count', len(parcels))}",
            f"{tr('Total active area')}: {res_single.get('total_area_ha', 0.0):.2f} ha",
            f"{tr('Average yield')}: {float(final.get('Yield', 0.0)):.2f} t/ha",
            f"{tr('Total cooperative production')}: {float(final.get('Total_Production', 0.0)):.1f} t",
            f"{tr('Disease incidence')}: {float(final.get('Incidence', 0.0))*100:.1f}%",
        ]
        pdf.chapter_body(chr(10).join(summary_lines))

        pdf.chapter_title('2. ' + tr('Optimized management comparison'))
        optimization_lines = [
            f"{tr('Optimized plots')}: {opt_summary.get('optimized_plot_count', 0)} / {opt_summary.get('total_active_plot_count', len(parcels))}",
            f"{tr('Baseline production')}: {opt_summary.get('baseline_production_t', 0.0):.2f} t",
            f"{tr('Optimized production')}: {opt_summary.get('optimized_production_t', 0.0):.2f} t",
            f"{tr('Expected production gain')}: {opt_summary.get('production_gain_t', 0.0):.2f} t",
            f"{tr('Conservative gain after shared-resource check')}: {constrained_gain_t:.2f} t",
            f"{tr('Optimized irrigation water')}: {opt_summary.get('water_m3', 0.0):.0f} m3",
            f"{tr('Optimized fertilizer product')}: {opt_summary.get('fertilizer_kg', 0.0):.0f} kg",
            f"{tr('Resource feasibility')}: {_resource_feasibility_text(resource_check)}",
            tr(opt_plan.get('scope_note', '')),
        ]
        for constraint in resource_check.get('constraints', []):
            optimization_lines.append('- ' + tr(constraint))
        pdf.chapter_body(chr(10).join(optimization_lines))

        pdf.chapter_title('3. ' + tr('Agronomic and economic optimization'))
        pdf.chapter_body(chr(10).join(_economic_summary_lines(economic_plan)))
        _add_economic_summary_table(pdf, economic_plan)
        _add_economic_action_table(pdf, economic_plan)

        if opt_rows:
            top_gain = sorted(opt_rows, key=lambda row: row.get('production_gain_t', 0.0), reverse=True)[:20]
            pdf.set_font('Arial', 'B', 8)
            pdf.cell(45, 7, tr('Plot name'), 1, 0, 'L', 1)
            pdf.cell(22, 7, tr('Area'), 1, 0, 'C', 1)
            pdf.cell(28, 7, tr('No action'), 1, 0, 'C', 1)
            pdf.cell(28, 7, tr('Optimized'), 1, 0, 'C', 1)
            pdf.cell(28, 7, tr('Gain'), 1, 0, 'C', 1)
            pdf.cell(20, 7, tr('Irr.'), 1, 0, 'C', 1)
            pdf.cell(20, 7, tr('Fert.'), 1, 1, 'C', 1)
            pdf.set_font('Arial', '', 8)
            for row in top_gain:
                pdf.cell(45, 7, str(row.get('name', ''))[:24], 1, 0, 'L')
                pdf.cell(22, 7, f"{row.get('area_ha', 0.0):.2f}", 1, 0, 'C')
                pdf.cell(28, 7, f"{row.get('baseline_yield_t_ha', 0.0):.2f}", 1, 0, 'C')
                pdf.cell(28, 7, f"{row.get('optimized_yield_t_ha', 0.0):.2f}", 1, 0, 'C')
                pdf.cell(28, 7, f"{row.get('production_gain_t', 0.0):.2f} t", 1, 0, 'C')
                pdf.cell(20, 7, str(row.get('irrigation_events', 0)), 1, 0, 'C')
                pdf.cell(20, 7, str(row.get('fertilizer_events', 0)), 1, 1, 'C')

        pdf.chapter_title('4. ' + tr('Metapopulation disease model'))
        evidence_lines = [tr('The cooperative mode treats each plot as a local patch and links plots through distance-weighted infection pressure.')]
        for item in disease_evidence.get('evidence', []):
            status_text = tr(item['status'])
            if item.get('count'):
                status_text = f"{item['count']} {status_text}"
            evidence_lines.append(f"- {tr(item['source'])}: {status_text}. {tr(item['decision_impact'])}")
        pdf.chapter_body(chr(10).join(evidence_lines))
        if history:
            fig, ax = plt.subplots(figsize=(8, 4))
            dates = pd.to_datetime(df['Date'])
            ax.plot(dates, df['Incidence'] * 100, label=tr('Disease incidence'), color='crimson')
            ax.plot(dates, df['Metapopulation_Pressure'] * 100, label=tr('Metapopulation pressure'), color='orange')
            ax.set_ylabel('%')
            ax.legend()
            ax.grid(True, alpha=0.3)
            pdf.add_plot_to_pdf(fig)
            plt.close(fig)

        pdf.chapter_title('5. ' + tr('Highest-risk plots'))
        if parcels:
            rows = []
            for parcel in parcels:
                last = parcel['history'][-1]
                rows.append((parcel['name'], parcel['area_ha'], float(last.get('Incidence', 0.0)) * 100, float(last.get('Metapopulation_Pressure', 0.0)) * 100, float(last.get('Yield', 0.0))))
            rows = sorted(rows, key=lambda r: r[2], reverse=True)[:20]
            pdf.set_font('Arial', 'B', 9)
            pdf.cell(55, 7, tr('Plot name'), 1, 0, 'L', 1)
            pdf.cell(25, 7, tr('Area'), 1, 0, 'C', 1)
            pdf.cell(35, 7, tr('Disease incidence'), 1, 0, 'C', 1)
            pdf.cell(35, 7, tr('Metapopulation pressure'), 1, 0, 'C', 1)
            pdf.cell(30, 7, tr('Forecast yield'), 1, 1, 'C', 1)
            pdf.set_font('Arial', '', 8)
            for name, area, inc, pressure, yld in rows:
                pdf.cell(55, 7, str(name)[:28], 1, 0, 'L')
                pdf.cell(25, 7, f"{area:.2f}", 1, 0, 'C')
                pdf.cell(35, 7, f"{inc:.1f}%", 1, 0, 'C')
                pdf.cell(35, 7, f"{pressure:.1f}%", 1, 0, 'C')
                pdf.cell(30, 7, f"{yld:.2f}", 1, 1, 'C')

        pdf.chapter_title('6. ' + tr('Management Recommendations'))
        recommendation_lines = [tr('Suggested next field check:') + ' ' + tr('Highest-risk plots')]
        if opt_plan.get('skipped_plot_count', 0):
            recommendation_lines.append(tr('Some plots were not optimized in this report run; increase the plot limit if you need a full cooperative optimization.'))
        recommendation_lines.append(tr('Use the optimized scenario as a planning baseline, then validate disease foci and water/fertilizer feasibility before costly action.'))
        pdf.chapter_body(chr(10).join(recommendation_lines))
        pdf_bytes = pdf.output(dest='S').encode('latin-1')
        st.download_button(label=tr('Download PDF'), data=pdf_bytes, file_name=f"AEF_Cooperative_Report_{date.today()}.pdf", mime='application/pdf')

def app():
    st.title("🗃️ " + t("report.title"))
    
    if 'sim_results' not in st.session_state:
        st.error(tr("No simulation data found. Please run the Dashboard first."))
        return

    res_single = st.session_state['sim_results']
    if isinstance(res_single, dict) and res_single.get('mode') == 'cooperative':
        render_cooperative_report(res_single)
        return
    crop_p = res_single['crop_params']
    is_perennial = crop_p['Type'] == 'Perennial'
    
    dis_id = st.session_state['selected_disease_id']
    df_d = st.session_state['df_diseases']
    dis_info = df_d[df_d['Disease_ID'] == dis_id].iloc[0] if dis_id else None

    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"### {tr('Subject')}: **{crop_p['Crop_Name']}** ({crop_p['Variety']})")
        st.caption(t("report.caption"))
        st.info("ℹ️ " + tr("Generating the PDF triggers multiple simulation engines (Disease Ensemble + Irrigation Optimizer + Nutrition Optimizer)."))
        if is_perennial:
            report_horizon_years = st.number_input(tr('Economic analysis horizon (years)'), min_value=1, max_value=20, value=int(st.session_state.get('economic_horizon_years', 20) or 20), step=1, key='single_report_economic_horizon_years')
            st.caption(tr('For perennial crops, revenue is summed over annual harvest peaks within this horizon.'))
            st.session_state['economic_horizon_years'] = int(report_horizon_years)
        else:
            report_horizon_years = 1
    
    with col2:
        if st.button("📄 " + tr("Download PDF Dossier"), type="primary", use_container_width=True):
            
            # --- 1. PREPARE CONFIG ---
            engine = SimulationEngine()
            config = {k: st.session_state[k] for k in StateManager.DEFAULTS.keys() if k in st.session_state}
            
            get_sched = lambda x: x.to_dict('records') if x is not None and not x.empty else []
            config['fert_schedule'] = get_sched(st.session_state.get('fert_schedule'))
            config['irr_schedule'] = get_sched(st.session_state.get('irr_schedule'))
            
            config['initial_soil_water'] = st.session_state.get('initial_soil_water', 0.5)
            config['initial_nitrogen'] = st.session_state.get('initial_nitrogen', 100.0)
            config['insect_pressure'] = st.session_state.get('insect_pressure', 1.0)
            config['planting_date'] = st.session_state.get('planting_date', date.today())
            config['economic_horizon_years'] = int(report_horizon_years)
            if not isinstance(config.get('economics_config'), dict):
                config['economics_config'] = {}
            config['economics_config']['economic_horizon_years'] = int(report_horizon_years)
            
            if st.session_state.get('soil_layers') is not None:
                config['soil_layers'] = st.session_state['soil_layers'].to_dict('records')
            else:
                config['soil_layers'] = []

            # --- 2. RUN DISEASE ENSEMBLE ---
            with st.spinner(t("report.spinner.ensemble")):
                ens_res = engine.run_ensemble_inference(config, n_runs=50)
                
            if ens_res is None:
                st.error(tr("Ensemble failed. Check configuration."))
                return

            # --- 3. RUN OPTIMIZERS ---
            with st.spinner(t("report.spinner.optimizers")):
                opt_irr_schedule, final_swc = engine.optimize_irrigation_schedule(config)
                season_advice = engine.assess_planting_season(st.session_state['center_lat'], st.session_state['center_lon'])
                opt_fert_schedule = engine.optimize_fertilization_schedule(config)
                opt_irr_schedule, irrigation_feasibility_warnings = annotate_irrigation_schedule(opt_irr_schedule, config, st.session_state.get('area_ha', 1.0))
                fertilizer_product_totals = fertilizer_totals_by_product(opt_fert_schedule, st.session_state.get('area_ha', 1.0))

            # --- 4. RUN COUNTERFACTUAL SCENARIOS ---
            with st.spinner(t("report.spinner.scenarios")):
                scenario_summary = engine.run_counterfactual_scenarios(config, n_runs=20)

            # --- 5. RUN POTENTIAL YIELD (CONTROL) ---
            with st.spinner(t("report.spinner.potential")):
                optimal_config = config.copy()
                optimal_config['irr_schedule'] = opt_irr_schedule
                optimal_config['fert_schedule'] = opt_fert_schedule
                optimal_config['selected_disease_id'] = None
                optimal_config['disease_spots'] = []
                optimal_config['insect_pressure'] = 0.0
                
                res_potential = engine.run_simulation(optimal_config)
                
                # Extract Potential Curve
                hist_potential = res_potential['history'] if res_potential else []
                if is_perennial:
                    pot_yield_curve = [day.get('Fruit_Biomass', day['Yield']) for day in hist_potential]
                else:
                    pot_yield_curve = [day['Yield'] for day in hist_potential]
                
                pot_yield_dates = [day['Date'] for day in hist_potential]

            # --- 6. BUILD ECONOMIC COMPARISON ---
            with st.spinner(t('report.spinner.economics')):
                economic_plan = build_single_field_economics(config, res_single, opt_irr_schedule, opt_fert_schedule, scenario_summary)

            # --- 7. COMPILE REPORT ---
            with st.spinner(t("report.spinner.compile")):
                pdf = PDFReport()
                pdf.add_page()
                
                stats = ens_res['ensemble_stats']
                uncertainty_profile = stats.get('Uncertainty_Profile', {}) if isinstance(stats, dict) else {}
                yield_ci_fraction_95 = float(uncertainty_profile.get('yield_ci_fraction_95', 0.18 if not is_perennial else 0.24))
                yield_abs_ci95 = float(uncertainty_profile.get('yield_abs_ci95_t_ha', 0.04))
                incidence_abs_ci95 = float(uncertainty_profile.get('incidence_ci95_abs', 0.08 if dis_info is not None else 0.02))
                area = st.session_state.get('area_ha', 1.0)
                
                # --- METRICS LOGIC ---
                if is_perennial:
                    # ROI: Analyze Peaks (Harvests) over 20 years
                    df_ens = pd.DataFrame({'Date': stats['Date'], 'Yield': stats['Yield_Mean']})
                    df_ens['Year'] = pd.to_datetime(df_ens['Date']).dt.year
                    
                    yearly_peaks = df_ens.groupby('Year')['Yield'].max()
                    
                    # 1. Average Annual Yield
                    final_y_mean = yearly_peaks.mean() 
                    
                    # 2. Total Production
                    total_production_mean = yearly_peaks.sum() * area
                    
                    # Uncertainty on the annual harvest peaks, not on an arbitrary final day.
                    df_ens['Yield_Std'] = stats['Yield_Std']
                    peak_idx = df_ens.groupby('Year')['Yield'].idxmax()
                    peak_std = df_ens.loc[peak_idx, 'Yield_Std'] if len(peak_idx) else pd.Series(dtype=float)
                    final_y_ci = max(1.96 * float(peak_std.mean() if not peak_std.empty else 0.0), final_y_mean * yield_ci_fraction_95, yield_abs_ci95)
                    total_prod_ci = max(1.96 * float(peak_std.sum() if not peak_std.empty else 0.0) * area, total_production_mean * yield_ci_fraction_95, yield_abs_ci95 * area)
                    
                    # Gap Analysis
                    df_pot = pd.DataFrame({'Date': pot_yield_dates, 'Yield': pot_yield_curve})
                    df_pot['Year'] = pd.to_datetime(df_pot['Date']).dt.year
                    pot_peaks = df_pot.groupby('Year')['Yield'].max()
                    
                    pot_avg = pot_peaks.mean() 
                    pot_total = pot_peaks.sum()
                    
                    # Gap based on Totals
                    yield_gap_t = pot_total - yearly_peaks.sum()
                    loss_pct = (yield_gap_t / (pot_total + 1e-6)) * 100
                    
                    # Calculate true 20-year average for potential
                    # Use mean() of peaks, not the sum or the raw curve average
                    final_pot_avg = pot_peaks.mean()

                    # UPDATED LABELS: Showing 20y Average
                    potential_label = f"{final_pot_avg:.2f} t/ha ({tr('20y Average')})"
                    forecast_label = f"{final_y_mean:.2f} +/- {final_y_ci:.2f} t/ha ({tr('20y Average')})"
                    
                else:
                    final_y_mean = stats['Yield_Mean'][-1]
                    final_y_std = stats['Yield_Std'][-1]
                    final_y_ci = max(1.96 * final_y_std, final_y_mean * yield_ci_fraction_95, yield_abs_ci95)
                    
                    total_production_mean = final_y_mean * area
                    total_prod_ci = max(final_y_ci * area, total_production_mean * yield_ci_fraction_95, yield_abs_ci95 * area)
                    
                    pot_val = pot_yield_curve[-1] if pot_yield_curve else 0
                    yield_gap_t = pot_val - final_y_mean
                    loss_pct = (yield_gap_t / (pot_val + 1e-6)) * 100
                    
                    potential_label = f"{pot_val:.2f} t/ha"
                    forecast_label = f"{final_y_mean:.2f} +/- {final_y_ci:.2f} t/ha"

                # Stress Frequency
                hist_single = res_single['history']
                df_hist = pd.DataFrame(hist_single)
                peak_stress_w = df_hist['Avg_Stress'].max()
                peak_stress_n = df_hist['Avg_N_Stress'].max()
                
                drought_days = (df_hist['Avg_Stress'] > 0.6).sum()
                drought_events = drought_days // 7 

                # --- CHAPTER 0: EXECUTIVE SUMMARY ---
                decision_cards = build_decision_snapshot(hist_single, config, crop_p, uncertainty_profile)
                diagnostic_quality = build_diagnostic_quality(config, res_single)
                disease_evidence = build_disease_evidence(config, _report_disease_name())
                exec_lines = [tr('This first page is an operational summary; detailed model traces follow in later sections.')]
                exec_lines.append(f"{tr('Diagnostic quality score')}: {diagnostic_quality['overall_score']:.1f}% - {tr(diagnostic_quality['label'])}")
                exec_lines.append(f"{tr('Next best measurement')}: {tr(diagnostic_quality['next_best_measurement'])}")
                exec_lines.append(f"{tr('Disease evidence status')}: {tr(disease_evidence['interpretation'])}")
                exec_lines.extend(_economic_summary_lines(economic_plan))
                for card in decision_cards[:4]:
                    exec_lines.append(f"- {tr(card['title'])}: {tr(card['message'])} {tr('Next step:')} {tr(card['recommended_next_step'])} {tr('Confidence:')} {tr(card['confidence'])}")
                for card in model_validity_impact_cards(res_single.get('growth_model'), res_single.get('disease_model'), bool(st.session_state.get('satellite_anomaly_date'))):
                    exec_lines.append(f"- {tr(card['area'])} - {tr(card['level'])}: {tr(card['decision_impact'])}")
                pdf.chapter_title("0. " + tr("Executive decision summary"))
                pdf.chapter_body("\n".join(exec_lines))

                # --- CHAPTER 1: CONFIG ---
                pdf.chapter_title("1. " + tr("Field Configuration"))
                crop_horizon = tr("Perennial - 20 Year Horizon") if is_perennial else tr("Annual - {n} days", n=crop_p['Cycle_Days'])
                disease_label = dis_info['Disease_Name'] if dis_info is not None else tr("None")
                conf_txt = (
                    f"{tr('Location')}: {st.session_state['center_lat']:.4f}, {st.session_state['center_lon']:.4f}\n"
                    f"{tr('Crop')}: {crop_p['Crop_Name']} - {crop_p['Variety']} ({crop_horizon})\n"
                    f"{tr('Soil Type')}: {tr(st.session_state['soil_type'].title())}\n"
                    f"{tr('Initial Nutrients (mg/kg)')}: N={st.session_state['initial_nitrogen']}, P={st.session_state.get('initial_phosphorus',20)}, K={st.session_state.get('initial_potassium',100)}\n"
                    f"{tr('Disease Target')}: {disease_label}"
                )
                pdf.chapter_body(conf_txt)
                
                # --- CHAPTER 2: DIAGNOSTICS ---
                pdf.chapter_title("2. " + tr("Agronomic Diagnostics"))
                
                diag_txt = (
                    f"{tr('Bio-Physical Potential (Optimal Mgmt):')} **{potential_label}**\n"
                    f"{tr('Forecast Yield (Current Scenario):')} **{forecast_label}**\n"
                    f"{tr('Yield Gap:')} **{loss_pct:.1f}%** {tr('loss attributed to current management and disease pressure.')}\n"
                    f"{tr('Est. Total Production')}: {total_production_mean:.1f} +/- {total_prod_ci:.1f} tonnes\n"
                    f"{tr('Current Water Stress Peak')}: {peak_stress_w*100:.1f}% {tr('severity')}.\n"
                    f"{tr('Current Nitrogen Stress Peak')}: {peak_stress_n*100:.1f}% {tr('severity')}."
                )
                
                if is_perennial:
                    diag_txt += f"\n**{tr('Long-Term Risk')}:** {drought_events} {tr('severe drought weeks projected over the next 20 years.')}"
                
                pdf.chapter_body(diag_txt)
                final_inf_margin = 0.0
                if 'Incidence_Std' in stats and len(stats['Incidence_Std']):
                    final_inf_margin = float(1.96 * stats['Incidence_Std'][-1] * 100)
                uncertainty_txt = (
                    f"**{tr('Uncertainty and margins of error')}**\n"
                    f"{tr('The yield and disease margins below are 95% ensemble intervals, not guarantees. They express model uncertainty from stochastic disease spread and weather-driven stress interactions.')}\n"
                    f"{tr('The margins combine stochastic ensemble variability with a conservative operational uncertainty floor based on soil data quality, crop horizon, disease uncertainty and adaptive calibration status.')}\n"
                    f"{tr('They are intentionally cautious and should shrink only after field observations are added through adaptive surveillance.')}\n"
                    f"{tr('Operational uncertainty floor')}: {yield_ci_fraction_95*100:.0f}% {tr('yield')}; {incidence_abs_ci95*100:.0f}% {tr('incidence')}.\n"
                    f"{tr('Forecast yield margin')}: +/- {final_y_ci:.2f} t/ha\n"
                    f"{tr('Total production margin')}: +/- {total_prod_ci:.1f} tonnes\n"
                    f"{tr('Final disease incidence margin')}: +/- {final_inf_margin:.1f}%"
                )
                pdf.chapter_body(uncertainty_txt)
                
                # --- PLOT 1: TRAJECTORY ---
                fig1, ax1 = plt.subplots(figsize=(10, 5))
                dates = pd.to_datetime(stats['Date'])
                
                if is_perennial:
                    ax1.plot(dates, stats['Yield_Mean'], 'g-', linewidth=2, label=tr('Forecast (Standing Fruit)'))
                    lower = stats['Yield_Mean'] - (1.96 * stats['Yield_Std'])
                    upper = stats['Yield_Mean'] + (1.96 * stats['Yield_Std'])
                    lower = np.maximum(lower, 0)
                    ax1.fill_between(dates, lower, upper, color='green', alpha=0.2, label=tr('95% Uncertainty'))
                    
                    ax1.set_ylabel(tr('Standing Fruit (t/ha)'), color='g')
                    ax1.set_title(tr('Simulation Trajectory (20 Year Horizon)'))
                    ax1.xaxis.set_major_locator(mdates.YearLocator(2)) 
                    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
                else:
                    if pot_yield_curve:
                        ax1.plot(pot_yield_dates, pot_yield_curve, 'k--', alpha=0.6, linewidth=1.5, label=tr('Potential'))
                    
                    ax1.plot(dates, stats['Yield_Mean'], 'g-', linewidth=2, label=tr('Forecast'))
                    lower = stats['Yield_Mean'] - (1.96 * stats['Yield_Std'])
                    upper = stats['Yield_Mean'] + (1.96 * stats['Yield_Std'])
                    ax1.fill_between(dates, lower, upper, color='green', alpha=0.2, label='95% Uncertainty')
                    ax1.set_ylabel(tr('Yield (t/ha)'), color='g')
                    ax1.set_title(tr('Yield Accumulation Forecast'))

                ax1.legend(loc='upper left', fontsize='small')
                ax1.grid(True, alpha=0.3)
                pdf.add_plot_to_pdf(fig1)
                plt.close(fig1)
                
                # --- CHAPTER 3: WATER ---
                pdf.chapter_title("3. " + tr("Smart Water Management"))
                
                if peak_stress_w > 0.5: status = "CRITICAL"
                elif peak_stress_w > 0.2: status = "MODERATE"
                else: status = "OPTIMAL"
                
                water_intro = f"{tr('Current Status')}: **{tr(status)}** ({tr('Peak Stress Index')}: {peak_stress_w:.2f})\n"
                if season_advice:
                    season_text = _translate_report_generated_text(season_advice.get('advice', tr('No data')))
                    water_intro += f"**{tr('Seasonality Insight')}:** {season_text}\n"
                pdf.chapter_body(water_intro)
                
                if opt_irr_schedule:
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 8, tr("Recommended Supplemental Irrigation Calendar:"), 0, 1)
                    pdf.set_font('Arial', '', 9)
                    
                    pdf.set_fill_color(240, 240, 240)
                    pdf.cell(40, 7, tr("Date"), 1, 0, 'C', 1)
                    pdf.cell(40, 7, tr("Amount (L/ha)"), 1, 0, 'C', 1)
                    pdf.cell(90, 7, tr("Rationale"), 1, 1, 'L', 1)
                    
                    display_limit = 15
                    for i, event in enumerate(opt_irr_schedule):
                        if i >= display_limit:
                            pdf.cell(40, 7, "...", 1, 0, 'C')
                            pdf.cell(40, 7, "...", 1, 0, 'C')
                            pdf.cell(90, 7, tr("and {n} more events.", n=len(opt_irr_schedule)-display_limit), 1, 1, 'L')
                            break
                        
                        amount_mm = event['amount']
                        amount_l_ha = amount_mm * 10000.0
                        
                        pdf.cell(40, 7, str(event['date']), 1, 0, 'C')
                        pdf.cell(40, 7, f"{amount_l_ha:,.0f} L/ha", 1, 0, 'C') 
                        pdf.cell(90, 7, tr("Refill Soil Moisture to 90% FC"), 1, 1, 'L')
                    
                    pdf.ln(5)
                    
                    if irrigation_feasibility_warnings:
                        pdf.chapter_body(tr('Operational feasibility warnings:') + '\n' + '\n'.join(irrigation_feasibility_warnings[:8]))
                    else:
                        pdf.chapter_body(tr('No irrigation capacity violation was detected from the supplied water constraint.'))
                    pdf.chapter_body(f"**{tr('Projected Impact:')}** {tr('Implementing this schedule contributes to reaching the potential yield.')}")
                else:
                    pdf.chapter_body(tr("No additional irrigation is required."))

                # --- CHAPTER 4: NUTRITION ---
                pdf.chapter_title("4. " + tr("Precision Nutrition Strategy"))
                
                if not opt_fert_schedule:
                    pdf.chapter_body("[OK] " + tr("Soil nutrient stocks are sufficient."))
                else:
                    pdf.chapter_body(tr("Objective: Maintain N-P-K levels above critical thresholds during active growth."))
                    
                    pdf.set_font('Arial', 'B', 10)
                    pdf.cell(0, 8, tr("Recommended Product Application Schedule:"), 0, 1)
                    pdf.set_font('Arial', '', 9)
                    
                    pdf.set_fill_color(230, 240, 255)
                    pdf.cell(30, 7, tr("Date"), 1, 0, 'C', 1)
                    pdf.cell(50, 7, tr("Product"), 1, 0, 'L', 1)
                    pdf.cell(30, 7, tr("Rate (kg/ha)"), 1, 0, 'C', 1)
                    pdf.cell(80, 7, tr("Rationale"), 1, 1, 'L', 1)
                    pdf.set_font('Arial', '', 9)
                    
                    display_limit = 15
                    for i, event in enumerate(opt_fert_schedule):
                        if i >= display_limit:
                            pdf.cell(30, 7, "...", 1, 0, 'C')
                            pdf.cell(160, 7, tr("and {n} more events.", n=len(opt_fert_schedule)-display_limit), 1, 1, 'L')
                            break

                        date_str = str(event['date'])
                        prod_str = _translate_product_name(event['product'])
                        rate_str = f"{event['amount']} kg"
                        rat_str = _translate_report_generated_text(event['rationale'])
                        
                        num_lines = max(1, len(rat_str) // 45 + 1)
                        row_height = 6 * num_lines
                        
                        if pdf.get_y() + row_height > 270:
                            pdf.add_page()
                            pdf.set_font('Arial', 'B', 9)
                            pdf.cell(30, 7, tr("Date"), 1, 0, 'C', 1)
                            pdf.cell(50, 7, tr("Product"), 1, 0, 'L', 1)
                            pdf.cell(30, 7, tr("Rate (kg/ha)"), 1, 0, 'C', 1)
                            pdf.cell(80, 7, tr("Rationale"), 1, 1, 'L', 1)
                            pdf.set_font('Arial', '', 9)

                        x_start = pdf.get_x()
                        y_start = pdf.get_y()
                        
                        pdf.cell(30, row_height, date_str, 1, 0, 'C')
                        pdf.cell(50, row_height, prod_str, 1, 0, 'L')
                        pdf.cell(30, row_height, rate_str, 1, 0, 'C')
                        pdf.set_xy(x_start + 110, y_start) 
                        pdf.multi_cell(80, 6, rat_str, 1, 'L')
                        pdf.set_xy(x_start, y_start + row_height)

                    pdf.ln(5)
                    if fertilizer_product_totals:
                        total_lines = [f"{_translate_product_name(prod)}: {qty:.1f} kg {tr('total product for configured area')}" for prod, qty in fertilizer_product_totals.items()]
                        pdf.chapter_body(tr('Total fertilizer quantities to source locally:') + '\n' + '\n'.join(total_lines[:10]))

                # --- CHAPTER 5: SATELLITE ---
                pdf.chapter_title("5. " + tr("Satellite Reality Check"))
                pdf.chapter_body(tr("Comparison of modeled LAI with observed Sentinel-2 NDVI on real cloud-free dates only. Agreement is supporting evidence, not proof of calibration."))

                sim_start = pd.to_datetime(stats['Date'][0]).date()
                sim_end = pd.to_datetime(stats['Date'][-1]).date()
                today = date.today()
                fetch_end = min(sim_end, today)

                if 'ndvi_data' not in st.session_state:
                    if sim_start <= today:
                        coords = st.session_state['field_coords']
                        st.session_state['ndvi_data'] = fetch_sentinel_ndvi(coords, sim_start, fetch_end)
                    else:
                        st.session_state['ndvi_data'] = None

                df_ndvi = st.session_state.get('ndvi_data')

                if df_ndvi is not None and not df_ndvi.empty:
                    fig_sat, ax1 = plt.subplots(figsize=(8, 4))
                    
                    # UPDATED PLOT: Uses df_hist['LAI'] (green dashed) + NDVI (blue dots) matching Dashboard
                    l1, = ax1.plot(dates, df_hist['LAI'], 'g--', linewidth=1.5, label=tr('Model LAI'))
                    ax1.set_ylabel(tr('Leaf Area Index'), color='g')
                    ax1.tick_params(axis='y', labelcolor='g')
                    
                    ax2 = ax1.twinx()
                    l2, = ax2.plot(df_ndvi['Date'], df_ndvi['NDVI'], 'bo', markersize=4, label=tr('Satellite NDVI'))
                    ax2.set_ylabel('NDVI', color='b')
                    ax2.tick_params(axis='y', labelcolor='b')
                    
                    ax1.legend([l1, l2], [tr('Model LAI'), tr('Satellite NDVI')], loc='upper left')
                    ax1.set_title(tr("Digital Twin vs. Satellite Observations"))
                    ax1.grid(True, linestyle=':', alpha=0.6)
                    pdf.add_plot_to_pdf(fig_sat)
                    plt.close(fig_sat)
                    pdf.chapter_body(tr("Interpretation: agreement between LAI and NDVI supports the simulation trend, but field measurements are still required for calibration."))
                else:
                    pdf.chapter_body(tr("No satellite imagery available (Future dates or Cloud cover)."))

                # --- CHAPTER 6: EPIDEMIOLOGY ---
                if dis_info is not None:
                    pdf.chapter_title("6. " + tr("Epidemiological Risk"))
                    final_inf_mean = stats['Incidence_Mean'][-1]
                    final_inf_std = stats['Incidence_Std'][-1]
                    final_inf_ci = 1.96 * final_inf_std
                    
                    epi_txt = (
                        f"{tr('Pathogen')}: **{dis_info['Disease_Name']}**\n"
                        f"{tr('Final Infection Severity')}: {final_inf_mean*100:.1f}% +/- {final_inf_ci*100:.1f}%."
                    )
                    pdf.chapter_body(epi_txt)
                    
                    fig2, ax = plt.subplots(figsize=(8, 4))
                    ax.plot(dates, stats['Incidence_Mean']*100, 'r-', linewidth=2, label=tr('Infection %'))
                    lower_i = np.clip(stats['Incidence_Mean'] - (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    upper_i = np.clip(stats['Incidence_Mean'] + (1.96 * stats['Incidence_Std']), 0, 1) * 100
                    ax.fill_between(dates, lower_i, upper_i, color='red', alpha=0.2)
                    ax.set_ylabel(tr('Field Infection %'))
                    ax.set_title(tr("Disease Progression"))
                    ax.grid(True, alpha=0.3)
                    pdf.add_plot_to_pdf(fig2)
                    plt.close(fig2)
                    
                    # Map
                    try:
                        fig3, ax3 = plt.subplots(figsize=(8, 6))
                        triang_source = ens_res['triangulation']
                        vals = stats['Final_Grid_Mean']
                        x_plot = triang_source.y 
                        y_plot = triang_source.x 
                        
                        triang_plot = mtri.Triangulation(x_plot, y_plot, triang_source.triangles)
                        if triang_source.mask is not None:
                            triang_plot.set_mask(triang_source.mask)
                        
                        tpc = ax3.tripcolor(triang_plot, vals, cmap='Reds', shading='gouraud', vmin=0, vmax=1)
                        
                        poly = ens_res['field_poly'] 
                        poly_plot = np.vstack([poly, poly[0]])
                        ax3.plot(poly_plot[:, 1], poly_plot[:, 0], 'k-', linewidth=1.5)
                        
                        ax3.set_aspect('equal')
                        ax3.set_title(tr("Final Disease Severity Map"))
                        fig3.colorbar(tpc, ax=ax3, label=tr("Severity (0-1)"))
                        pdf.add_plot_to_pdf(fig3)
                        plt.close(fig3)
                    except Exception:
                        pass

                # --- CHAPTER 7: COUNTERFACTUAL SCENARIOS ---
                pdf.chapter_title("7. " + tr("Scenario Comparison"))
                if scenario_summary:
                    pdf.set_font('Arial', 'B', 9)
                    pdf.cell(55, 7, tr("Scenario"), 1, 0, 'L', 1)
                    pdf.cell(45, 7, tr("Forecast yield"), 1, 0, 'C', 1)
                    pdf.cell(45, 7, tr("Disease incidence"), 1, 0, 'C', 1)
                    pdf.cell(35, 7, tr("Uncertainty"), 1, 1, 'C', 1)
                    pdf.set_font('Arial', '', 9)
                    for scenario_key in ['none', 'optimized']:
                        s = scenario_summary.get(scenario_key, {})
                        if not s.get('available'):
                            continue
                        pdf.cell(55, 7, tr(s.get('label', scenario_key)), 1, 0, 'L')
                        pdf.cell(45, 7, f"{s.get('final_yield', 0):.2f} t/ha", 1, 0, 'C')
                        pdf.cell(45, 7, f"{s.get('final_incidence', 0)*100:.1f}%", 1, 0, 'C')
                        pdf.cell(35, 7, f"+/- {1.96*s.get('yield_std', 0):.2f}", 1, 1, 'C')
                    pdf.ln(4)
                    pdf.chapter_body(tr("The dossier compares two paths: no action and optimized management. This keeps the decision dossier faster while preserving the core baseline-versus-improved-management comparison."))
                    pdf.chapter_body(chr(10).join(_economic_summary_lines(economic_plan)))
                    _add_economic_summary_table(pdf, economic_plan)
                    _add_economic_action_table(pdf, economic_plan)
                    roguing_lines = []
                    for scenario_key in ['optimized']:
                        s = scenario_summary.get(scenario_key, {})
                        if not s.get('available'):
                            continue
                        roguing_lines.append(
                            f"- {tr(s.get('label', scenario_key))}: {tr('roguing/pruning applied in')} {s.get('roguing_applied_probability', 0)*100:.0f}% {tr('of ensemble runs')}; {tr('yield penalty')} {s.get('roguing_yield_penalty', 0)*100:.1f}%; {tr('inoculum benefit score')} {s.get('roguing_inoculum_benefit', 0):.3f}; {tr('yield cost score')} {s.get('roguing_yield_cost', 0):.3f}."
                        )
                    if roguing_lines:
                        pdf.chapter_body(tr("Roguing balance checked by scenario:") + "\n" + "\n".join(roguing_lines))
                else:
                    pdf.chapter_body(tr("Scenario comparison was unavailable for this configuration."))

                # --- CHAPTER 8: RECS ---
                pdf.chapter_title("8. " + tr("Management Recommendations"))
                recs = []
                
                if dis_info is not None:
                    recs.append(f"**{tr('Specific Protocols for {disease}:', disease=dis_info['Disease_Name'])}**")
                    raw_methods = dis_info['Control_Methods'].replace('\\n', '\n')
                    for m in raw_methods.split('\n'):
                        if m.strip(): recs.append(f"- {_translate_report_generated_text(m.strip())}")
                    recs.append(_translate_report_generated_text("**Roguing / pruning decision rule:** removal is never automatic. The scenario engine compares the expected gain from lower inoculum with the yield loss caused by removing productive plants or canopy. For annual crops, removal is considered only when the focus is localized and the epidemiological gain exceeds stand loss. For perennial crops, tree removal or severe pruning carries a durable yield cost and is recommended only with a stricter benefit margin and field confirmation."))
                
                if peak_stress_w > 0.6: recs.append(f"**!! {tr('CRITICAL WATER STRESS.')}**")
                if peak_stress_n > 0.5: recs.append(f"**! {tr('Nitrogen Deficiency.')}**")
                
                if not recs: recs.append("[OK] " + tr("Crop status is healthy."))
                
                pdf.chapter_body("\n".join(recs))
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.download_button(
                    "⬇️ " + tr("Download PDF"), 
                    data=pdf_bytes, 
                    file_name=f"AEF_Report_{date.today()}.pdf", 
                    mime="application/pdf"
                )
                st.success(tr("Report generated successfully."))