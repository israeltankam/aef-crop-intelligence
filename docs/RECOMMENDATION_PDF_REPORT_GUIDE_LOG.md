# Recommendation PDF, final report signature and guide log

Date: 2026-06-21
Backup: `backups/pre_recommendation_pdf_report_guide_2026-06-21T17-57-58-474Z`

## Scope

This change keeps the existing business logic and focuses on the user-facing recommendation/report workflow requested by the product owner:

- annual crops no longer expose a configurable economic horizon on the Recommendations, What-if or final Report pages;
- perennial crops keep the horizon selector because multi-year harvest windows remain relevant;
- recommendations are generated only after the user clicks the run button;
- the farmer-facing Action list now prioritizes a readable PDF export while keeping the JSON export as a technical option;
- What-if reuses the already-computed Recommendations plan only when crop, disease, disease spots, planting date, economics, horizon and cooperative plot count still match;
- final reports append the same detailed recommendation sections used by the Recommendations PDF;
- all reports are signed with `src/images/logo/logo_company/logo_scale.png` where pyfpdf accepts the PNG;
- the user guide was rewritten in French and English with the application emoji codification.

## Files changed

- `app.py`: discreet Scale AG logo display on login and sidebar.
- `pages/main/recommendations.py`: annual horizon handling, manual optimization trigger, readable PDF export, technical JSON export, safer PDF cache signature.
- `pages/main/what_if.py`: safe reuse of cached recommendation calendars before falling back to regeneration.
- `pages/main/report.py`: Scale AG page header/footer and detailed recommendation sections in final PDF reports.
- `src/utils/recommendation_pdf.py`: shared branded PDF builder for recommendation sections.
- `src/utils/i18n.py`: French translations for new labels, alerts, report titles and PDF sections.
- `support/User guide.md`: bilingual guide source.
- `support/User guide.html`: visually structured bilingual guide.
- `support/User guide bilingual.docx`: bilingual DOCX fallback because `support/User guide.docx` was locked by Windows.
- `support/User guide.pdf`: lightweight PDF guide export.
- `support/test_results/aef_recommendation_pdf_report_guide_tests.json`: automated check results.

## Implementation notes

### Annual crop horizon

Annual crops now use the crop-cycle horizon automatically. The UI does not ask for `Economic analysis horizon (years)` unless `crop_params['Type'] == 'Perennial'`. Internally the annual horizon remains stored as one crop cycle for compatibility with existing economic functions, while the user-facing text describes it as planting date to expected harvest.

### Recommendations PDF

The readable PDF includes:

- decision summary comparing baseline, agronomic optimum and economic optimum;
- full action list;
- optimized irrigation calendar;
- optimized fertilization calendar;
- disease-control summary with a roguing/pruning caution;
- operational caution about uncertainty and adaptive surveillance.

The PDF cache signature includes summaries, actions, selected actions, single-field schedules and cooperative plot rows so stale PDFs are not reused after calendar changes.

### What-if reuse

The What-if page does not blindly reuse any old plan. It reuses the Recommendations plan only if the full signature still matches. If not, the existing manual generation button remains the path forward. This protects scientific consistency while reducing duplicated waiting time in the common case.

### Final report integration

The final report now calls the same shared recommendation-section renderer used by the Recommendations PDF. This keeps formatting and content aligned between the standalone recommendation PDF and the complete final dossier.

### Logo signing

Both standalone recommendation PDFs and final reports attempt to render the Scale AG logo on each page. Logo rendering is intentionally non-fatal because classic pyfpdf can reject some PNG variants on some systems; in that case the report still renders with Scale AG text in the header/footer.

### User guide

The guide is bilingual and uses the same emoji map as the application:

- 🔐 access;
- 🌍 field setup;
- 🤝 cooperative mode;
- 🛰️ dashboard;
- 🧭 recommendations;
- 🧪 what-if;
- 🗃️ final report;
- 📄 readable PDFs;
- 💾 technical JSON.

The legacy `support/User guide.docx` file was locked (`EBUSY`) and could not be overwritten in this session. The complete rewritten DOCX is therefore saved as `support/User guide bilingual.docx`; the Markdown and HTML guide files are also complete.

## Validation

142 automated checks passed:

- 100+ static and product-invariant checks for UI behavior, i18n keys, PDF signatures, report inclusion and guide content;
- table-width checks for the generated PDF sections to avoid obvious page overflow;
- structural checks on edited Python files for unmatched brackets, open strings and merge-conflict markers.

Python/Streamlit execution could not be launched in this sandbox because process spawning is blocked with `EPERM`. The test result JSON records this limitation.

## Requirements

No new runtime dependency was added. The implementation uses existing application dependencies, especially `fpdf==1.7.2`.
