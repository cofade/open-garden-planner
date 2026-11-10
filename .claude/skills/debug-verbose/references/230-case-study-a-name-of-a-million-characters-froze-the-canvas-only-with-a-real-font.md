## Case study: a name of a million characters froze the canvas, and only where a real font was registered — plan text that reaches a painter is the same trust boundary as plan text that reaches a tooltip (review of #793, fixed 2026-11-10)

**Symptom**: the full test battery of the 2D visual-polish branch hung for 45 minutes. A rerun with a per-test timeout named `tests/integration/test_view3d_workspace_widget.py::test_a_huge_hostile_name_costs_a_capped_row_and_a_capped_tooltip`: a raised bed whose name is `"<table><tr><td>" * 100_000 + "\nsecond line"`, 1.5 million characters. The stack at the timeout was not in the 3D pane the test is about but in the 2D canvas beside it: `halo_text._paint_vector` (`painter.strokePath`) under `paint_text`, the scene's label pass and `CanvasView.paintEvent`. Run alone, the test passed in 3 s. On master it passed in the battery too.

**Theories on the table (wrong)**:
- *"Another test leaves object labels switched on, or a persisted setting shows the label."* Labels are on by default, and the label was laid out and painted in the lone run as well: `plan_labels_shown` returned it there too.
- *"The label is only painted when the bed is selected or large enough."* It was painted either way; what differed was what one paint COST.
- *"It hangs."* With a million and a half characters it does not hang: Qt's stroker dies with an access violation. The 45 minutes were the run waiting for a worker that was gone, and a name a third shorter does hang, for 47 s.

**What instrumentation revealed** (a probe: one raised bed, a name of N characters, the first paint timed, with and without `QFontDatabase.addApplicationFont` on the offscreen platform):

```
[HUGE] no font database (box font) 1,500,012 chars: first paint     56 ms   label box 8388621 px wide
[HUGE] real font registered        1,000,012 chars: first paint  46877 ms   label box 6600005 px wide
[HUGE] real font registered        1,500,012 chars: Windows fatal exception: access violation
                                   halo_text.py _paint_vector  <-  _picture  <-  paint_text  <-  the label pass
[HUGE] after the fix, real font    1,500,012 chars: label text 81 chars, first paint 21 ms
```

**Root cause**: two things that were each harmless alone. (1) An object's name went into its label on the plan as the plan file had it: `PlanLabelItem(text, self)` and `setText(text)`. Since #793 a label strokes the outline of every glyph for its halo, so the label's cost is the length of its text, and nothing bounded it. `core/plain_text.py` caps a name for every row, card, tooltip and log line (§8.11); the canvas was not on that list. (2) Windows' `offscreen` platform has no font database: every glyph is a box with no outline, so there is nothing to stroke and the paint is cheap. The suite's session-scoped `ui_font_family` fixture (`tests/conftest.py`) registers a real Windows face for the REST of the worker process. A lone run of the hostile-name test never asks for it; in a full run some earlier test in the same worker does. That is the state the test "inherited", and it is no test state at all: the real application always has real fonts, so a plan file with such a name froze or crashed the app at its first paint.

**Fix** (`ui/canvas/items/halo_text.py`, `ui/canvas/items/garden_item.py`): `label_text` is `core.plain_text.clip_line` (one line, `NAME_MAX_CHARS`, an ellipsis), applied at the two places a `PlanLabelItem` gets a text and where the succession badge gets its crop names. The name itself is untouched. `tests/integration/test_plan_label_text_bound.py` asks for `ui_font_family` on purpose and bounds the label's text and width BEFORE it paints anything, so on unbounded text it fails in a millisecond instead of hanging.

**Lesson**: a string from a plan file that reaches a painter is at the same trust boundary as one that reaches a tooltip: whoever does work for every character needs the cap, and "it is only drawn" is not an exemption. When a test passes alone and hangs in the run with a paint in the stack, ask what process-wide state changes what PAINTING costs before asking what changes whether something is painted; a font database is such a state, and on the offscreen platform a box font hides every cost that depends on glyph outlines (the same blindness as the hinting case, in the other direction). And write the regression test so that it measures a size first: a test that reproduces a hang by hanging takes the run down with it.
