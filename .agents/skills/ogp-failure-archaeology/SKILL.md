---
name: ogp-failure-archaeology
description: >
  The chronicle of every major OGP investigation, dead end, rejected fix, and revert — so
  nobody re-fights a settled battle. Load this skill when: (1) you are about to change a
  subsystem that has history (rotation/resize, properties panel, undo stack, task status,
  sidebar lists, exception handling at file-load, release workflow, installer, i18n,
  Agent API render); (2) a bug you're chasing resembles something described here; (3) you
  are tempted to "fix" code that looks wrong (a broad `except Exception`, a debounce plus
  a flush queue, a `rect().center()` pivot, a write-only `task_completions` mirror — it
  may be the scar of a fixed bug); or (4) you're investigating WHY code is written in a
  strange way. Fast triage for a live bug = ogp-debugging-playbook; the invariants as
  forward-looking contracts = ogp-architecture-contract. This skill records how those
  invariants were learned, the hard way.
---

# ogp-failure-archaeology reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| OGP Failure Archaeology | [Read](references/000-ogp-failure-archaeology.md) |
| Index — scan this first | [Read](references/001-index-scan-this-first.md) |
| 1. The rotated-geometry saga (#213 → #219 → #218/#221) | [Read](references/002-1-the-rotated-geometry-saga-213-219-218-221.md) |
| 2. The panel-rebuild saga (#200 → #206/#222 → #223 → #225) | [Read](references/003-2-the-panel-rebuild-saga-200-206-222-223-225.md) |
| 3. Undo/redo data loss — the two-chokepoint invariant (#209/#211) | [Read](references/004-3-undo-redo-data-loss-the-two-chokepoint-invariant-209-211.md) |
| 4. Free-text commit granularity — debounce plus flush (#210/#214) | [Read](references/005-4-free-text-commit-granularity-debounce-plus-flush-210-214.md) |
| 5. Task dual-store convergence (#227 → #228) | [Read](references/006-5-task-dual-store-convergence-227-228.md) |
| 6. Find Plants selection flakiness — two rounds (#212/#215) | [Read](references/007-6-find-plants-selection-flakiness-two-rounds-212-215.md) |
| 7. Smart-symbol exception-family enumeration — the losing game (PR #236) | [Read](references/008-7-smart-symbol-exception-family-enumeration-the-losing-game-pr-236.md) |
| 8. Release-workflow races (chore race; #229 date matching) | [Read](references/009-8-release-workflow-races-chore-race-229-date-matching.md) |
| 9. Data loss on update — the installer wiped user plans (#199/#204, ADR-027) | [Read](references/010-9-data-loss-on-update-the-installer-wiped-user-plans-199-204-adr-027.md) |
| 10. i18n incidents — hardcoded strings and mojibake | [Read](references/011-10-i18n-incidents-hardcoded-strings-and-mojibake.md) |
| 11. CI-only teardown crashes (#230, PR #235) | [Read](references/012-11-ci-only-teardown-crashes-230-pr-235.md) |
| 12. Agent API render tool (D1.3, PR #242) — layers fix + two empirical mcp facts | [Read](references/013-12-agent-api-render-tool-d1-3-pr-242-layers-fix-two-empirical-mcp-facts.md) |
| 13. Retired feature: US-B7 Paper Space (dropped in PR #191 review) | [Read](references/014-13-retired-feature-us-b7-paper-space-dropped-in-pr-191-review.md) |
| 14. The export Y-flip saga (PNG/PDF/SVG, 2026-05) | [Read](references/015-14-the-export-y-flip-saga-png-pdf-svg-2026-05.md) |
| 15. Tangent-constraint degeneracy (PR #198, ADR-024, fixed 2026-06-07) | [Read](references/016-15-tangent-constraint-degeneracy-pr-198-adr-024-fixed-2026-06-07.md) |
| 16. Inert curve handles — the `ItemIgnoresTransformations` grab drop (#193) | [Read](references/017-16-inert-curve-handles-the-itemignorestransformations-grab-drop-193.md) |
| 17. Label editor auto-closing — the minimap culprit (fixed 2026-04-22) | [Read](references/018-17-label-editor-auto-closing-the-minimap-culprit-fixed-2026-04-22.md) |
| 18. QSettings global-static poison — "passes alone, fails together, CI green" | [Read](references/019-18-qsettings-global-static-poison-passes-alone-fails-together-ci-green.md) |
| 19. The stale-trigger family (#173/#175) | [Read](references/020-19-the-stale-trigger-family-173-175.md) |
| 20. The ghost-field family (US-12.10d, fixed 2026-05-03) | [Read](references/021-20-the-ghost-field-family-us-12-10d-fixed-2026-05-03.md) |
| 21. UNKNOWN-enum display corruption (#231/#232) | [Read](references/022-21-unknown-enum-display-corruption-231-232.md) |
| 22–25. Short entries | [Read](references/023-22-25-short-entries.md) |
| Still open / unsettled (as of 2026-07-03) | [Read](references/024-still-open-unsettled-as-of-2026-07-03.md) |
| When NOT to use this skill | [Read](references/025-when-not-to-use-this-skill.md) |
| Provenance and maintenance | [Read](references/026-provenance-and-maintenance.md) |
