# What-if economic reoptimization log

Date: 2026-06-21

Target copy: `C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822`

Backup created before edits: `C:\Users\tankamch\AppData\Local\Temp\aef_corrected_1781125311822\backups\pre_what_if_economic_consistency_2026-06-21T16-54-33-684Z`

## Diagnosis

The supplied screenshot showed three scenario rows only: `No action`, `Optimized management` and `Edited what-if scenario`. The edited what-if scenario had a higher net return than `Optimized management`, which is inconsistent if that row is presented as an economic optimum.

The root cause was twofold:

- The recommendation/economic engine used a narrow candidate set: baseline, full agronomic management and a crude profitable-action subset. It could not choose partial irrigation or fertilization intensities, so the economic optimum was often identical to the agronomic optimum.
- The What-if page compared the edited user scenario against the previously generated optimized plan, but did not insert a recalculated economic optimum row that included the edited scenario as a candidate.

The supplied JSONs confirm the case is a small cocoa field (`3.69 ha`, crop id `C_COC_01`) with an editable XAF economic profile. The issue is therefore algorithmic/comparative, not only a bad cost default.

## Corrections

### Economic engine

File: `src/models/economic_engine.py`

- Added a lightweight deterministic candidate grid for economic optimization.
- Water and fertilization actions can now be evaluated at 0%, 25%, 50%, 75% and 100% intensity.
- Disease control remains binary in the generic engine because partial disease control is pathogen-specific and should not be inferred blindly.
- Added a normalized saturating response curve so costs scale near-linearly while benefits follow diminishing marginal returns.
- Kept the full agronomic plan in the candidate set, so the economic optimum cannot be worse than the agronomic optimum under the same expected-value assumptions.
- Selected economic actions now carry an `economic_scale` and selected action rows are cost/benefit scaled consistently with the summary.

### What-if page

File: `pages/main/what_if.py`

- Replaced the three-row comparison with four coherent rows:
  - `No action`
  - `Agronomic optimum`
  - `Economic optimum`
  - `What-if scenario`
- The edited what-if scenario is included as a candidate when recalculating the economic optimum.
- If the user-edited scenario is the best economic candidate, the `Economic optimum` row is promoted to the same result. The what-if row can therefore equal, but not exceed, the economic optimum.
- Added `Net difference vs economic optimum` to the page and PDF report.
- Updated JSON/PDF exports to include the economic source used for the optimum row.

### Recommendations page

File: `pages/main/recommendations.py`

- Added an `Economic scale` column so users can see whether the economic optimum keeps an action fully or partially.
- Updated explanatory text from the old profitable-action subset to the new partial cost-scaled intervention mixes.

### Internationalization

File: `src/utils/i18n.py`

- Added French translations for the new rows, captions, PDF explanation and economic-scale labels.

### User guide

Files:

- `support/User guide.md`
- `support/User guide.docx`
- `support/User guide.pdf`

The guide was rewritten as an operator guide in French. It now covers single-field mode, cooperative mode, economics, recommendations, what-if scenarios, report generation, adaptive surveillance, result interpretation and troubleshooting. The PDF parses successfully with `pdfjs-dist` and the DOCX has a valid Word archive structure. LibreOffice visual rendering could not be run because process execution is blocked in this environment.

## Validation

Test report: `support/test_results/aef_what_if_economic_reoptimization_100_checks.json`

- 100 checks executed.
- 100 passed.
- 0 failed.

Important validation note: Python/Streamlit execution is blocked here (child process spawn returns `EPERM`), so these are static and invariant checks rather than full app simulations. The checks include code-structure validation, translation coverage, guide-file validation, PDF parsing, and explicit economic invariants using the screenshot values.

## No requirements update

No new runtime dependency was added to the application. The app changes use Python standard-library modules only (`math`, `itertools`). The DOCX/PDF guide was generated as a support artifact outside the app runtime.
