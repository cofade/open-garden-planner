## Provenance and maintenance

Primary sources, in order of density: the pitfall entries in
`docs/11-risks-and-technical-debt/pitfalls/` (the index is §11.4 of the chapter README; the
narratives are in `archive/`), `.claude/skills/debug-verbose/SKILL.md` case
studies, `CLAUDE.md` progress tables, `docs/roadmap.md` (US-B7 note ~line 2277),
`docs/09-architecture-decisions/README.md`, `git log --oneline`.

Re-verification one-liners (run from repo root):

```bash
# Pinning tests still exist / still pin what this skill claims:
grep -rln "test_apply_keeps_rotated_plant_centered\|test_rotation_pivots_about_rect_center_with_badge" tests/
ls tests/integration/test_rotation_aware_resize.py tests/integration/test_undo_redo_dirty.py \
   tests/integration/test_properties_panel_incremental.py tests/integration/test_properties_text_edit_undo.py \
   tests/integration/test_panel_refresh_wiring.py tests/integration/test_calendar_task_convergence.py \
   tests/integration/test_find_plants_selection.py tests/unit/test_smart_symbol_library.py \
   tests/integration/test_save_location.py tests/unit/test_paths.py tests/integration/test_bed_context_menu.py
grep -rn "TestCrossSurfaceSync\|TestOverdueReminderBar\|TestHandleDragViaView\|TestFrostDashboardNavigation" tests/ -l

# Pitfall keyword sweep (new entries land in `pitfalls/` first — re-mine after every merged fix):
grep -rn "Closed (#\|Lesson\|pinned\|Pinned\|Regression test" docs/11-risks-and-technical-debt/pitfalls docs/11-risks-and-technical-debt/archive

# New sagas since this skill was written:
git log --oneline -30
grep -n "Case study" .claude/skills/debug-verbose/SKILL.md

# US-B7 retirement + paper_layouts ignore still documented:
grep -n "paper_layouts" docs/roadmap.md CLAUDE.md

# Release-race procedure unchanged:
grep -n "tag transition\|before_tag\|date matching" .claude/skills/finalize-us/SKILL.md
```

Maintenance rule (mirrors CLAUDE.md's continuous-documentation policy): after any fix
that survived a wrong theory, a rejected design, a multi-round review, or a manual-test
failure, add an entry here in the standard format AND a case study to `debug-verbose`
if instrumentation cracked it. Date-stamp anything volatile (versions, library
behaviour, "still open" claims).
