## Provenance and maintenance

Written 2026-07-03 against master at v1.23.0. Every row cites its §11.4 chronicle entry, debug-verbose case study, or docs/07–08 section; nothing here is folklore. Re-verify before trusting a row after major refactors:

```bash
# Chronicle keywords (one per table row family) — each must still hit docs/11 §11.4:
G=docs/11-risks-and-technical-debt/README.md
grep -c "transformOriginPoint" $G          # row 1
grep -c "_active_drag_handle" $G           # row 2
grep -c "renders upside-down" $G           # row 3
grep -c "setResolution(72)" $G             # row 11
grep -c "torn down" $G                     # row 14
grep -c "store only the stable" $G         # row 21
grep -c "trigger_soil_mismatch_refresh" $G # row 22
grep -c "setSpecialValueText" $G           # row 29
grep -c "NEVER use PowerShell" $G          # row 27
grep -c "register_applied" $G              # row 20

# Source anchors still exist:
grep -n "_fix_svg_pattern_yflip\|_fix_svg_qt_texture_clipping" src/open_garden_planner/services/export_service.py
grep -n "isinstance(grabber" src/open_garden_planner/ui/canvas/canvas_view.py
grep -n "def trigger_soil_mismatch_refresh\|def _refresh_z_after_relink" src/open_garden_planner/core/commands.py
grep -n "class TestNoHardcodedEnglish" tests/unit/test_i18n.py
grep -n "multiprocessing" docs/07-deployment-view/README.md

# Sibling docs this skill defers to:
ls .agents/skills/debug-verbose/SKILL.md
grep -n "8.9.8\|8.19" docs/08-crosscutting-concepts/README.md | head -4
```

Maintenance duty: when a new §11.4 entry or debug-verbose case study lands, add (or update) the matching triage row here — symptom phrased as a tester would say it, plus the discriminating experiment. Keep this file *triage-only*; full narratives belong to the chronicle and `ogp-failure-archaeology`.
