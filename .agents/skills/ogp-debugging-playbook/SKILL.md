---
name: ogp-debugging-playbook
description: >
  Fast symptom→cause→experiment triage for Open Garden Planner's recurring failure modes.
  Load this when: a bug is reported (by a user, manual tester, or reviewer); a test fails
  unexpectedly; CI is red while local is green (or vice versa); a test passes alone but fails
  in the full run; behaviour differs from what the code appears to do; a visual glitch appears
  on the canvas (mirrored text, ghost shapes, items drifting/jumping, handles that won't drag);
  an export (PNG/SVG/PDF/DXF) looks wrong or empty; the German UI shows English or mojibake;
  panels go stale or steal focus; the packaged exe crashes or a bundled service silently fails.
  This skill classifies the symptom against the project's hard-won pitfall chronicle so you
  fix from precedent instead of re-fighting a solved bug.
---

# ogp-debugging-playbook reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| OGP Debugging Playbook | [Read](references/000-ogp-debugging-playbook.md) |
| When NOT to use this skill | [Read](references/001-when-not-to-use-this-skill.md) |
| Triage protocol | [Read](references/002-triage-protocol.md) |
| Triage table A — canvas geometry & interaction | [Read](references/003-triage-table-a-canvas-geometry-interaction.md) |
| Triage table B — export (PNG / SVG / PDF) | [Read](references/004-triage-table-b-export-png-svg-pdf.md) |
| Triage table C — tests, CI, teardown | [Read](references/005-triage-table-c-tests-ci-teardown.md) |
| Triage table D — panels, signals, staleness | [Read](references/006-triage-table-d-panels-signals-staleness.md) |
| Triage table E — i18n, encoding, data display | [Read](references/007-triage-table-e-i18n-encoding-data-display.md) |
| Triage table F — packaging / frozen exe | [Read](references/008-triage-table-f-packaging-frozen-exe.md) |
| Qt debugging facts you probably don't know | [Read](references/009-qt-debugging-facts-you-probably-don-t-know.md) |
| Provenance and maintenance | [Read](references/010-provenance-and-maintenance.md) |
