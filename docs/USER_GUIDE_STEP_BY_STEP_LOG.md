# User guide step-by-step rewrite log

Date: 2026-06-21
Backup: backups/pre_user_guide_step_by_step_2026-06-21T18-26-03-589Z

## Requested change

The quick map was useful, but the user guide needed to become a real step-by-step manual for a user who does not know the application at all. The maintenance-style sentence about the bilingual guide/version was removed. Only Markdown and HTML outputs should remain.

## What changed

- Rewrote support/User guide.md as a long operational guide, from first login to final report.
- Rebuilt support/User guide.html from the same content, with a sticky table of contents, responsive layout, readable tables and Scale AG logo.
- Kept the Quick map at the beginning.
- Added detailed beginner workflows for:
  - access and language selection;
  - single-field mode;
  - cooperative mode;
  - GPS, DMS, place search and manual polygon drawing;
  - plot naming;
  - crop and variety setup;
  - annual versus perennial horizons;
  - disease detection and manual disease entry;
  - roguing and pruning caution;
  - soil configuration;
  - economics configuration;
  - JSON save/reload;
  - dashboard reading;
  - reality check;
  - uncertainty margins;
  - recommendations;
  - irrigation and fertilization calendars;
  - disease control recommendations;
  - readable recommendations PDF;
  - What-if scenarios;
  - final report;
  - adaptive surveillance;
  - troubleshooting and cautious interpretation.
- Removed the sentence: Guide utilisateur bilingue / Bilingual user guide. Version 2026-06-21. Ce guide suit la même codification visuelle que l’application et doit être mis à jour à chaque évolution fonctionnelle.
- Deleted support/User guide.pdf.
- Deleted support/User guide bilingual.docx.
- Deleted the temporary Word lock file support/~$er guide.docx.

## Remaining limitation

support/User guide.docx could not be deleted because Windows still reports it as locked with EBUSY. The file was backed up before the attempt. Once it is closed/unlocked on Windows, it can be removed manually; the maintained guide versions are now support/User guide.md and support/User guide.html.

## Validation

39 guide-specific checks passed:

- Markdown length and HTML length are substantial;
- forbidden sentence is absent;
- version/maintenance wording is absent;
- all major beginner workflows are present;
- HTML includes a table of contents and Scale AG logo;
- PDF and bilingual DOCX generated previously were removed;
- locked legacy DOCX status was recorded.

Test result file: support/test_results/aef_user_guide_step_by_step_tests.json
