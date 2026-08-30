---
name: debug-verbose
description: Evidence-based debugging via targeted verbose instrumentation. Apply at the first sign of any non-obvious bug — before theorising. Grows with each bug fixed in this project.
user_invocable: true
argument: "Optional: short description of the bug or area to instrument"
---

# Verbose Debug Instrumentation

**Core principle**: stop theorising, start observing. The first step for any non-trivial bug is to instrument the code so the actual runtime sequence is printed to stdout, then reproduce with manual testing and read what happened. Fix from evidence, not assumptions.

---

## When to apply (proactively, without being asked)

- Behaviour differs from what the code appears to do
- Event-driven / asynchronous code (timers, signals, focus events, callbacks)
- Something is called unexpectedly, or not called at all
- A guard/condition seems correct but isn't firing
- Third-party framework (Qt, etc.) is involved and may have side effects

---

## How to instrument

### 1. Identify the execution spine

Map the path from trigger to outcome. For every node on that path add a `print`:

```
trigger → A() → B() → [condition] → C()  ← expected
                               ↘ D()      ← what actually happens?
```

### 2. What to print at each node

| Node type | Print |
|-----------|-------|
| Entry to function | function name + key arguments + `type(self).__name__` |
| State that the condition reads | the exact values used in the `if` |
| Timestamps for time-based guards | `time.monotonic()` before AND inside the guard |
| Focus / visibility / flag checks | `hasFocus()`, `isVisible()`, `flags()` |
| Async callbacks (timers, slots) | "fired" + whether preconditions hold |
| Exit paths | which branch was taken, what was returned |
| Unexpected call sites | `traceback.format_stack()[:-1]` — always include this for "who called me?" questions |

### 3. Use `print`, not `logging`

`logging` requires configuration. `print` goes to stdout unconditionally — exactly what you need when the app is run from a terminal.

### 4. Prefix every line

Use a consistent tag like `[MODULE]` so output is grep-able and doesn't get lost in Qt warnings:

```python
print(f"[LABEL] focusOutEvent: elapsed={elapsed:.4f}s  isVisible={self.isVisible()}")
```

### 5. Include call stacks at "unexpected" sites

Any function that should only be called from specific places should print its caller when debugging:

```python
import traceback
for line in traceback.format_stack()[:-1]:
    print(f"[TAG]   {line.strip()}")
```

This is what revealed the minimap as the culprit below.

---

## Template — event-driven method instrumentation

```python
def some_event_handler(self, event):
    import time, traceback
    t = time.monotonic()
    start = getattr(self, '_start_time', 0)
    print(f"\n[TAG] some_event_handler:")
    print(f"[TAG]   key_state  = {self.some_state}")
    print(f"[TAG]   elapsed    = {t - start:.4f}s")
    print(f"[TAG]   condition  = {self.isVisible() and (t - start) < 0.2}")
    print("[TAG]   caller stack:")
    for line in traceback.format_stack()[:-1]:
        print(f"[TAG]     {line.strip()}")
    # ... rest of method
```

---

## Template — async/deferred callback

```python
def _deferred_action():
    import time
    print(f"[TAG] _deferred_action fired — isVisible={item.isVisible()}  hasFocus={item.hasFocus()}")
    if not item.isVisible():
        print("[TAG] ABORT — item hidden before callback ran")
        return
    item.do_thing()
    print(f"[TAG] after do_thing — hasFocus={item.hasFocus()}")

QTimer.singleShot(0, _deferred_action)
```

---

## Case study: label editor auto-closing (fixed 2026-04-22)

**Symptom**: double-clicking any garden item opened the inline label editor for ~110 ms then it closed by itself.

**Theories entertained (wrong)**:
- Qt's double-click Release-2 event steals focus
- `_label_edit_start_time` set after `setFocus()` so guard evaluated stale `0.0`
- `super().focusOutEvent()` clears text cursor

**What instrumentation revealed** (one double-click, reading stdout):

```
[LABEL] _give_focus() — after setFocus: hasFocus=True  isVisible=True

[LABEL] focusOutEvent:
[LABEL]   elapsed        = 0.109000s
[LABEL]   isVisible()    = False          ← ALREADY HIDDEN before focusOut fired
[LABEL]   guard (<0.2s)  = False          ← guard missed because isVisible is False
[LABEL]   caller stack:
[LABEL]     minimap_widget.py:205 — item.setVisible(False)   ← THE CULPRIT
```

**Root cause**: `MinimapWidget._hide_overlay_items()` iterates all scene items with `ItemIgnoresTransformations` and calls `setVisible(False)` on them — including the `EditableLabel` — before rendering the minimap thumbnail (~110 ms after focus was given). Hiding the item fired `focusOutEvent` with `isVisible() = False`, so the time-based guard (which checks `isVisible()`) never activated.

**Fix** (one line in `minimap_widget.py`): skip the scene's current focus item in `_hide_overlay_items()`.

**Lesson**: the call stack in `focusOutEvent` pointed directly to the file and line number of the external caller. Without it, debugging would have required days of guessing.

---

## Case study: CalloutItem re-editing immediately commits (fixed 2026-04-29)

**Symptom**: right-clicking an empty `CalloutItem` and choosing "Edit Text" did nothing — the item appeared to enter editing and immediately exit it. Items with non-empty content also failed via the context menu.

**Theories entertained (wrong)**:
- Context menu stealing keyboard focus from the view (real, but not the root cause)
- `QGraphicsTextItem.setFocus()` silently failing for zero-width bounding rects
- `_text_child.clearFocus()` in `_commit_edit` breaking subsequent `setFocus` calls

**What instrumentation revealed** (right-click → "Edit Text" on empty callout):

```
[CALLOUT] start_editing: _editing=False  content=''
[CALLOUT]   scene focus before: CalloutItem          ← parent already has scene focus
[CALLOUT]   scene focus after view.setFocus(): CalloutItem  ← still has it after widget focus restore
[CALLOUT] focusOutEvent on CalloutItem: _editing=True       ← fires DURING _text_child.setFocus()
[CALLOUT]   caller: callout_item.py:234 self._text_child.setFocus(...)
[CALLOUT] _commit_edit: _editing=True  content=''           ← immediately committed
[CALLOUT]   _editing after setFocus: False                  ← editing already dead
```

The sequence was: context menu open → `_text_child` loses focus → Qt gives scene focus to the
parent `CalloutItem` (because `ItemIsFocusable` was set) → `_commit_edit` runs (correct at
this point). Then "Edit Text" → `start_editing()` → `view.setFocus()` restores `CalloutItem`
as scene focus → `_text_child.setFocus()` steals it → `CalloutItem.focusOutEvent` fires with
`_editing=True` → `_commit_edit()` immediately exits editing.

**Root cause**: `CalloutItem` had `ItemIsFocusable` set and a `focusOutEvent` that committed
the edit. Whenever `_text_child.setFocus()` transferred scene focus away from the parent,
`focusOutEvent` fired on the parent and exited editing mode synchronously — before the user
could type anything.

**Fix**: removed `ItemIsFocusable` from `CalloutItem` entirely. Created `_CalloutTextChild`
(`QGraphicsTextItem` subclass) that routes its own `focusOutEvent` → parent's
`_on_text_focus_out()` → `_commit_edit()`, and handles Escape via `clearFocus()`. The parent
now never holds scene focus, so `focusOutEvent` on the parent is never triggered during
`start_editing()`.

**Lesson**: when a `QGraphicsItem` parent holds `ItemIsFocusable` AND has a child
`QGraphicsTextItem`, setting focus on the child fires `focusOutEvent` on the parent
synchronously inside `setFocus()`. This is the correct place to commit on "lost focus", but
it fires at the wrong time when you are *entering* editing. The fix is to never let the parent
hold scene focus — put all focus logic in the child subclass.

---

## After fixing: clean up

Remove all `print` instrumentation before committing. The fix lives in the production code; the diagnosis lives in this skill.

---

## How this skill grows

After every non-trivial bug fixed in this project, add a new **Case study** entry above with:
- Symptom (one line)
- Wrong theories (to avoid repeating them)
- The key log line(s) that revealed the truth
- Root cause (one sentence)
- Lesson learned

Over time this becomes a project-specific debugging playbook.

---

## Case study: PNG/SVG export empty after Y-flip fix (fixed 2026-05-01)

**Symptom**: PNG export produced a correctly-sized image filled only with the canvas background color (#f5f5dc). No shapes visible. SVG had file content but rendered empty in browser.

**Theories entertained (wrong)**:
- Scene items not in canvas_rect bounds
- Wrong source rect passed to scene.render()
- DPI calculation error

**What instrumentation revealed**: Added `print(f"[EXPORT] target_rect={target_rect}  isEmpty={target_rect.isEmpty()}")` before `scene.render()`. Output: `isEmpty=True`.

**Root cause**: Previous Y-flip fix used `QRectF(0, H, W, -H)` as the target rect. In PyQt6, `QRectF` with negative height is considered empty — `isEmpty()` returns `True`. Qt's `scene.render()` clips to the target rect, so an empty rect = zero pixels painted.

**Fix**: Replace negative-height rect with painter pre-flip: `painter.translate(0, H_px); painter.scale(1.0, -1.0)` then call `scene.render()` with a normal positive rect. H_px must be the **image height in pixels**.

**Lesson**: Always test `isEmpty()` on any QRectF used as a render target. Negative-dimension rects are valid geometry in some contexts but empty in Qt's rendering pipeline.

---

## Case study: PDF overview rendered as narrow left-edge strip (fixed 2026-05-01)

**Symptom**: PDF export page 2 showed the scene image as a thin strip at the left edge, not filling the content area. Despite correct code for the painter pre-flip, position was wrong.

**Theories entertained (wrong)**:
- Wrong content_rect coordinates
- Painter viewport not matching page layout
- scale() applied before translate()

**What instrumentation revealed**: Added `print(f"[PDF] initial painter.transform(): {p.worldTransform()}")` before the pre-flip. Output showed a non-identity initial transform (QPdfWriter applies margin offsets before the painter is returned). The formula `translate(0, cr.top + cr.bottom)` assumed an identity baseline — invalid for QPdfWriter.

**Root cause**: QPdfWriter's painter has a non-identity initial transform from margin handling. The pre-flip baseline is shifted, so `translate(0, top+bottom)` overshoots.

**Fix**: Switch to "render scene to temp QImage (which has reliable identity transform), then embed with `painter.drawImage(content_rect, img)`". Immune to QPdfWriter's initial transform. See `_scene_to_image()` in `pdf_report_service.py`.

**Lesson**: Never assume QPainter starts at identity when targeting non-QImage devices (PDF, printer, SVG). Always read `painter.worldTransform()` first.

---

## Case study: SVG texture fills inverted/brownish under Y-flip (fixed 2026-05-02)

**Symptom**: SVG export showed correct shapes and satellite image but a brownish overlay covering the scene. Texture-filled polygons (roof tiles, gravel) appeared wrong. PNG export was correct.

**Theories entertained (wrong)**:
- Satellite image color space issue
- Some polygon covering full canvas with wrong fill
- Pattern tiling origin offset

**What instrumentation revealed**: Extracted pattern tiles from the SVG with a Python script (`scripts/validate_exports.py` + base64 decode). Tile images themselves were correct (e.g. grass texture shows green). Inspected SVG transforms: main group had `matrix(0.213774, 0, 0, -0.213774, 0, 877)` (scale + Y-flip). Pattern elements had no `patternTransform`. Rendered SVG to PNG via `QSvgRenderer` — confirmed brownish overlay visible.

**Root cause**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. The pattern tile images are stored in their natural (non-flipped) orientation. When the scene Y-flip transform is active, each tile renders upside-down within the Y-flipped coordinate space — a texture tile that looks like roof tiles right-side-up looks like abstract brown when flipped.

**Fix**: Post-process the SVG after `painter.end()`: read the file, find all `<pattern>` elements, add `patternTransform="matrix(1,0,0,-1,0,{height})"` to flip the tile back. See `ExportService._fix_svg_pattern_yflip()`.

**Lesson**: Qt's SVG generator does NOT propagate painter transforms into pattern tile images. Any painter-level Y-flip requires explicit `patternTransform` compensation as a post-processing step.

---

## Case study: SVG brownish overlay across satellite background (fixed 2026-05-02)

**Symptom**: After the patternTransform Y-flip fix, SVG export still showed a brownish-orange wash across most of the canvas, hiding the satellite background. PNG export was correct. A "transparent test" (forcing every `opacity="0.x"` to 0) made the satellite reappear — proving garden items were the culprit, not the satellite layer or canvas color.

**Theories entertained (wrong)**:
- Satellite Z-order wrong (it isn't — `BackgroundImageItem.setZValue(-1000)`)
- Canvas background color leaking through (`#f5f5dc` beige is fully opaque, never the brownish observed)
- Pattern tile origin offset
- Opacity stacking on transparent group hierarchy

**What instrumentation revealed**: A small Python script decoded every base64 pattern tile and inspected each `<rect>` in the SVG. Output:

```
<rect x="1035.83" y="393.78" width="4382.73" height="4382.73"/>   ← roof tile
<rect x="3366.42" y="2800.94" width="1408.86" height="1408.86"/>  ← roof tile
clipPath elements: 0     ← Qt did NOT serialize the painter clip region
clip-path attributes: 0
```

The texture rects were the **painter's clip bounding rect**, not the polygon shape. The actual polygon was serialized in the *preceding* "shadow" group: `<g fill="#000000" transform="..."><path d="M2729...Z"/></g>` followed immediately by `<g fill="url(#texpattern_X)" transform="..."><rect x="..." y="..." .../></g>`. Qt clips the rect against the painter clip region during native rendering, but the SVG contains no `<clipPath>` for the viewer to honor. So the rect bleeds across the entire canvas.

**Root cause**: `QSvgGenerator` does not emit `<clipPath>` elements for `QPainter::setClipRegion`/`setClipPath` calls. Texture-filled `QGraphicsItem`s end up as a giant unconstrained rect in the SVG.

**Fix**: Post-process the SVG (`ExportService._fix_svg_qt_texture_clipping`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's path (preserving its transform), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 in document order with a `used_textures` set; a naive "scan 4000 chars ahead" matched the same texture from multiple shadows and produced overlapping replacements that corrupted the XML tree (mismatched `</g>` tags). Visual validation: render SVG via Edge headless (`scripts/svg_preview.py`) — Qt's QSvgRenderer is too forgiving and hides this class of bug.

**Lesson**: Qt's `QSvgGenerator` is *not* a faithful serializer of painter state. Anything beyond shape + fill + stroke (clip regions, composition modes, painter transforms applied to brush textures) must be recovered in post-processing. When pairing emitted constructs (shadow ↔ texture), walk both lists in lockstep with a `used` set — never use a forward window scan, because Qt emits empty bookkeeping groups that throw off positional heuristics. Always validate SVG output in a real browser, not just QSvgRenderer.

---

## Case study: US-12.10d plant-soil mismatch border never appears (fixed 2026-05-03)

**Symptom**: Tomato in a bed with mismatched soil pH/N/P/K never triggered the amber/red bed border. `SoilService.get_mismatched_plants()` had a perfect implementation and 14 passing integration tests, yet the live app behaviour was silently broken. Manual hover tooltip showed *one* warning ("heavy N feeder") that never changed regardless of which soil parameters the user altered.

**Theories entertained (wrong)**:
- The 500 ms debounce timer wasn't firing — but the same timer correctly drove the rotation handle hide/show and badge updates.
- The `_child_item_ids` link from bed to plant was missing — verified, it was set correctly.
- `is_bed_type` rejecting the rectangle — false, the bed had `ObjectType.GARDEN_BED`.
- The pH rule had a bug in its boundary comparison — re-read it five times, the logic was right.
- The plant-data file (`planting_calendar.json`) lacked `n_demand` — true but not load-bearing; the legacy `nutrient_demand="heavy"` mapping covers it via `_effective_demand()`.

**What instrumentation revealed**: A diff between `PlantSpeciesData` dataclass field list and the keys returned by `to_dict()`:

```
fields:    ..., nutrient_demand, n_demand, p_demand, k_demand, raw_data
to_dict:   ..., nutrient_demand,                                raw_data    ← three missing
from_dict: ..., nutrient_demand=...,                            raw_data=...
```

Three brand-new fields were declared on the dataclass (US-12.10d) but never added to either serialization site. So the live data flow `library → plant_database_panel.set_plant_data() → metadata["plant_species"] = data.to_dict() → ... → PlantSpeciesData.from_dict(metadata["plant_species"])` silently dropped every per-nutrient demand value, leaving `n_demand=p_demand=k_demand=None` on the reconstructed spec. The N rule still fired via the `nutrient_demand="heavy"` legacy fallback in `_effective_demand`, but it now used the *fallback* mapping, not the direct field — and any test that set the direct fields would silently no-op.

**Root cause**: [src/open_garden_planner/models/plant_data.py:165–221](src/open_garden_planner/models/plant_data.py#L165) and [src/open_garden_planner/models/plant_data.py:223–291](src/open_garden_planner/models/plant_data.py#L223) — `to_dict()` and `from_dict()` were not updated when `n_demand`/`p_demand`/`k_demand` were added to the dataclass.

**Fix**: Add the three keys to both serialization sites. Add a regression test [tests/unit/test_plant_data_serialization.py](tests/unit/test_plant_data_serialization.py) that iterates over every `dataclasses.fields(PlantSpeciesData)` and asserts presence in `to_dict()` output, plus a full equality round-trip.

**Lesson**: When adding a field to a dataclass that already has `to_dict`/`from_dict` methods, **immediately grep for the dataclass name in the same file and update both serialization sites** — and write a `dataclasses.fields()`-driven round-trip test. The integration tests passed because they constructed `PlantSpeciesData` instances directly and never round-tripped through dict; the bug only surfaced on the canvas → metadata → canvas data path. **Construct-and-test is not the same as serialize-and-test.** Whenever a dataclass has both code paths, both must be exercised.

---

## Case study: data fields exist on the model but no UI to set them (US-12.10d, fixed 2026-05-03)

**Symptom**: Even after F1 fixed the silent serialization gap (case study above), tomato beds still didn't show pH-mismatch warnings in real use. Manual REPL round-trip of `PlantSpeciesData(n_demand="high", ph_min=5.8)` worked perfectly — the data plumbing was correct. But in the running app, every plant the user dropped had `ph_min=ph_max=n_demand=p_demand=k_demand=None`.

**Theories entertained (wrong)**:
- The fix didn't actually deploy (it had — `git show df9871e:plant_data.py` confirmed).
- `merge_calendar_data()` was overwriting the new fields (it wasn't — it only merges calendar fields).
- The library lookup was returning a stale cached `PlantSpeciesData` (no cache layer exists).

**Key signal from the user**: a screenshot of the plant details panel showing **no row** for pH or NPK demand. The fields existed on the dataclass and round-tripped through dict, but **the UI never showed them**. So the user had no way to set them — every plant arrived with `None` because the bundled data files (\`planting_calendar.json\`) only carry \`nutrient_demand: "heavy"\` and the API doesn't return pH ranges, leaving the new fields permanently empty.

**Root cause**: [src/open_garden_planner/ui/panels/plant_database_panel.py](src/open_garden_planner/ui/panels/plant_database_panel.py) — `_create_editable_fields()` had no rows for `ph_min`, `ph_max`, `n_demand`, `p_demand`, `k_demand`, or `nutrient_demand`. The model exposed the fields; the panel didn't.

**Fix**: Added 5 new form rows (pH range Min/Max, N/P/K demand combos, overall demand combo) between Hardiness and Planted, with read-back in `_on_field_changed` and population in `_show_plant_data`. After any field change the panel calls `view.refresh_soil_mismatches()` so the bed border updates live.

**Lesson**: A serialization round-trip test proves *data flows*, not *user intent flows*. When you add a field to a model, also audit the panel/dialog/forms that read & write that model — a "ghost field" with no UI is worse than no field at all because it gives the appearance of completeness in the data layer while silently making the feature unusable. Concretely: when adding a field to `PlantSpeciesData`, also grep `plant_database_panel.py` for any nearby field of the same model (e.g. `hardiness_zone_min`) — that's the natural place to add the matching UI row.

**Sister issues raised** (deferred to follow-up work, but caught during this debug session):
- #170 — autoloading from a shipped local species DB on canvas drop (so the new fields actually have values).
- #171 — past records in the History tab need edit/delete affordances; a typo currently requires deleting the whole bed.

---

## Case study: QGraphicsPolygonItem.shape() is the stroke envelope, not the outline (US-12.10/F2.6a, fixed 2026-05-03)

**Symptom**: After fixing the soil-mismatch border to call `closeSubpath()` on `self.shape()`, all polygon edges were finally painted — but the closing edge was visibly *thinner* than the others.

**Wrong theories**:
- Anti-aliasing artifact at the closing vertex (no — clearly a different stroke width).
- `closeSubpath()` not being applied (verified it ran).
- Pen join style needed `MiterJoin` (didn't fix it).

**Key signal**: visually, the closing segment looked like a *single hairline*, while the other edges were a clean 4 px stroke. That's the signature of stroking a thin-band shape: the outline gets a 4 px stroke but the band itself is < 4 px wide.

**Root cause**: [Qt's `QGraphicsPolygonItem.shape()`](src/open_garden_planner/ui/canvas/items/garden_item.py#L589) does **not** return the polygon's outline. It returns the *stroke envelope* — a closed band path that's the polygon outline expanded by the pen width, intended for hit-testing (so clicking near the edge counts as a hit). Stroking that band's outline produces the observed double-line effect, with the addPolygon-induced open seam reduced to a thin closing line.

**Fix**: When the item has a `polygon()` method (i.e. it *is* a `QGraphicsPolygonItem`), bypass `shape()` entirely and use `painter.drawPolygon(self.polygon())`. That uses the raw vertex list and produces a uniform stroke on every edge with proper miter joins. Rect / circle / ellipse keep the `drawPath(self.shape())` fallback because their `shape()` *does* return a closed outline.

**Lesson**: `QGraphicsItem.shape()` is hit-testing geometry, not drawing geometry. When you need to outline an item, use the item's *primitive* (polygon, rect, ellipse) not its shape. Reach for `painter.drawPolygon`/`drawRect`/`drawEllipse` over `drawPath(self.shape())` whenever you can.

---

## Case study: early `return` inside a paint() branch silently bypasses later draws (US-12.10/F2.6b, fixed 2026-05-03)

**Symptom**: GARDEN_BED rectangles correctly showed soil-mismatch borders. RAISED_BED rectangles never did. Both pass `is_bed_type()`, both have a `_soil_mismatch_level`, both call the same paint hook.

**Wrong theories**:
- `is_bed_type(RAISED_BED)` returning False (verified true).
- Pixmap rendering covering the border (no — pen has alpha 220).
- Selection-handle code stealing focus (irrelevant to paint).

**Key signal**: instrumenting paint() showed the border code at line 317 *never ran* for raised beds. That code is unconditional within `is_bed_type` — so something earlier was returning.

**Root cause**: [rectangle_item.py:290](src/open_garden_planner/ui/canvas/items/rectangle_item.py#L290) — RAISED_BED is rendered as a *furniture pixmap* (the wooden-frame look), and that branch had an early `return` (line 290) at the end of the pixmap block. Every line below that — grid overlay, rotation indicator, *and the soil mismatch border* — was bypassed for raised beds. The original code reviewer of US-12.10d wired the border at line 317 thinking it was reachable for all bed types.

**Fix**: Add a second `_draw_soil_mismatch_border` call *inside* the early-return branch, just before the `return`. Both the pixmap path and the standard path now paint the border.

**Lesson**: When wiring a new draw call into an existing `paint()` method, search the method for *every* `return` statement and confirm each control-flow path reaches your new code. Better: factor reusable post-paint hooks into a method called at every exit point. An early-return inside an `if` block is a classic stale-call site for new features added later.

---

## Case study: outer dialog OK appends a duplicate after sub-dialog edit (US-12.10/F2.6c, fixed 2026-05-03)

**Symptom**: Editing a past soil-test record via the History tab → sub-dialog accepted, history list updated. But after closing and reopening the bed's soil dialog, there were now *two* records: the edited original and a duplicate of the pre-edit values.

**Wrong theories**:
- `EditSoilTestCommand` was appending instead of replacing (verified by direct unit test — it correctly mutated by id).
- Race condition in the canvas refresh callback (no — the duplicate was on disk).
- The user pressed OK on the sub-dialog twice (single press confirmed).

**Key signal**: the *outer* dialog's status bar showed "Soil test recorded" after the user closed the dialog with OK. They thought OK = "save my changes", but the outer dialog's `result_record()` had already been built from the entry tab, which was populated at construction time with the *pre-edit* `existing_latest`. So `AddSoilTestCommand` appended a stale copy.

**Root cause**: [application.py:_open_soil_test_dialog](src/open_garden_planner/app/application.py) unconditionally fired `AddSoilTestCommand` on every accepted dialog, regardless of whether the entry tab actually changed.

**Fix**: Compare `result_record()` to the original `existing` field-by-field (ignoring `id` and `date`); if equal, status-bar "No changes" and skip the command. The user's OK becomes a no-op when they only used History-tab affordances.

**Lesson**: Modal dialogs that mix "view past data + edit current data" hide a state-capture trap: any sub-dialog that mutates the underlying state leaves the outer dialog showing stale form values. Either keep state-mutating actions out of the outer dialog (separate browser/editor flows) or *always* compare-before-commit on accept. Don't trust the user's OK to mean "I want to save the entry tab" if the entry tab was never touched.

---

## Case study: same-zValue items reverse stacking after .ogp save/load (US-12.10/F2.7, fixed 2026-05-03)

**Symptom**: A tomato dropped on a polygon bed rendered correctly during the live session. After saving the project and reopening it, the bed was on top — the tomato was gone (actually still in the scene, just hidden behind the bed).

**Wrong theories**:
- The plant wasn't being saved (`scene.items()` after load showed it present).
- The plant's transform was wrong (correct — the dot was just hidden).
- A z-value field wasn't being persisted in `.ogp` (it isn't, but that's a symptom not the cause).

**Key signal**: in the live session, both bed and plant had `zValue() == 0`. The plant was on top. After load, both still had `zValue() == 0` — but the bed was on top. So the *tie-break* between same-z items had flipped between sessions.

**Root cause**: [canvas_scene.py:_update_items_z_order](src/open_garden_planner/ui/canvas/canvas_scene.py#L649) sets every item's z to `layer.z_order * 100`. Items in the same layer get *the same z*. Qt's `QGraphicsScene` then tie-breaks by item insertion order. The live session inserts bed first, then plant — plant on top. The post-load reconstruction inserts items in scene-traversal order from the saved JSON, which is reversed by serialization, putting the plant first and the bed on top.

**Fix**: Add a third pass in `_update_items_z_order` (mirroring the existing ROOF_RIDGE special case at line 658) that walks every item with `_parent_bed_id` set and bumps its z to `parent.zValue() + 1`. Now plants always have a strictly higher z than their bed, regardless of insertion order.

**Lesson**: Identical zValues are a footgun across save/load boundaries because `QGraphicsScene` tie-breaks by *insertion order*, which is **not stable** between live mutation order and JSON-load order. Whenever a parent-child draw relationship matters, encode it explicitly via `parent.zValue() + 1` — never rely on "I inserted them in the right order, it'll just work". Pattern: anywhere `_update_items_z_order` touches multiple item categories, add an explicit ordering pass per parent-child relationship.

---

## Case study: model has display_name(lang) but call sites use .name (US-12.10/F4, fixed 2026-05-03)

**Symptom**: With German locale active, the soil-test dialog's amendments list and the Amendment Plan table both showed substance names in English ("Dolomite lime", "Blood meal") despite the bundled `amendments.json` carrying perfect German `name_de` translations and the `Amendment` dataclass having a `display_name(lang)` helper.

**Root cause**: [`format_amendment_line`](src/open_garden_planner/ui/dialogs/soil_test_dialog.py) and [`AmendmentPlanDialog._populate_table`](src/open_garden_planner/ui/dialogs/amendment_plan_dialog.py) both read `rec.amendment.name` directly — bypassing the localisation helper.

**Lesson**: When you add a localisation helper to a model (`display_name(lang)`), grep every read of the underlying field (`.name`) in the same package and switch them over. A helper added without consumers is dead code that gives a false impression of i18n coverage. Same family of bug as F2 ("ghost field") but at the *call site* instead of the UI layer.

---

## Case study: clipboard format that LOOKS right but fails on paste (US-12.10/F10, fixed 2026-05-03)

**Symptom**: AmendmentPlanDialog → "Copy to clipboard" → paste into LibreOffice / Excel → everything dumped into a single column.

**Root cause**: `_build_clipboard_text` produced human-readable bullet lines (`- Dolomite lime: 10.4 kg (Bed A, Bed B)`). Visually fine on a notepad, but the spreadsheet has no separator to split on.

**Lesson**: "Copy to clipboard" buttons targeting *spreadsheets* must produce **tab-separated** rows with a header row. Always test the receiving application, not just the rendered string. Add a regression test that asserts exact column count via `line.count("\t") == n`.

---

## Case study: max() ties hide newer records of the same date (US-12.10/F2.10a, fixed 2026-05-04)

**Symptom**: User saves a Lab-mode soil test on a bed that already has a Kit-mode record dated the same day. Reopens the dialog → defaults to Kit. The History tab seems to show only one record. The .ogp file does contain a record with `mode: "lab"`, but the dialog can't see it.

**Wrong theories**:
- `AddSoilTestCommand` silently dropped the record (verified — it appended).
- `to_dict` wasn't emitting the `mode` field (verified — it did when != "kit").
- `_records_equivalent` dedup'd it out (mode differs → guard passed).
- Q-signal ordering issue inside the dialog rebuild after save.

**Key signal**: side-by-side comparison of the .ogp file (which had the lab record) and the dialog state on reopen (`existing_latest.mode == "kit"`). The lab record was on disk but `latest` returned the kit record.

**Root cause**: [models/soil_test.py:113](src/open_garden_planner/models/soil_test.py#L113) — `SoilTestHistory.latest` was implemented as `max(self.records, key=lambda r: r.date)`. Python's `max()` returns the **first** maximal element when keys tie ("If multiple items are maximal, the function returns the first one encountered"). The Kit record was appended first, so it won every same-day tie. Compounded by `_format_history_row` showing only categorical fields — the user couldn't tell two records existed for that date.

**Fix**: Walk `reversed(self.records)` and return the first match for the max date. Plus add a ` [Lab]` / ` [Labor]` suffix to History-tab rows whose `mode == "lab"` so they're visually distinguishable from Kit rows on the same date.

**Lesson**: `max(iterable, key=...)` is **left-biased** on ties. For a "most recently saved record" that uses date as the key, the *first* save with the max date wins — not the last. Whenever the semantic is "newest among items with equal sort keys", either (a) walk the iterable backwards, (b) use a tuple key including a stable secondary sort (insertion index, uuid, monotonic counter), or (c) use `sorted(...)[-1]`. Bonus heuristic: if a sort/aggregation key has limited resolution (a date, not a datetime), assume ties are common and design the tie-break explicitly.

---

## Notes from the same sweep (no separate case study warranted)

- **F2.10b — bed history merge with global default**: a UX-semantics fix. The default test should be the bed's *fallback*, not a permanent overlay. Once a bed is tested, the default vanishes from its history; delete the last bed record and the default reappears. Lesson worth remembering: when implementing a "fallback" relationship, the UI should show the fallback *only when actually applied* — having it always visible obscures whether the bed has its own data.

- **F2.10c — RAISED_BED on circles/ellipses**: pixmap-based rendering doesn't clip to the underlying shape. A round bed with `RAISED_BED` rendered as a square wooden frame. Lesson: when a type carries a fixed-aspect-ratio raster asset (the wooden-frame pixmap), the "valid shapes" list for that type must match the asset's aspect — otherwise the result is incoherent. Drop the option from incompatible shape lists rather than trying to clip the pixmap (which would distort it).

---

## Case study: soil-mismatch warning goes stale on plant move/reparent (issue #173, fixed 2026-05-07)

**Symptom**: User drops a tomato (auto-populated with `ph_min=6.0` after #170) into a bed with `pH=4.0`. Bed edges turn red ✓. Drags the tomato outside → edges *stay* red. Bumps bed pH 4.0 → 4.1 → edges flip green. Drags the tomato *back into* the bed → edges *stay* green. Bumps pH 4.1 → 4.2 → red again. The recompute logic is correct; what's broken is the *trigger*.

**Wrong theories**:
- `_update_soil_mismatches` had a bug (verified — synchronous calls from soil-test save worked perfectly).
- `_child_item_ids` wasn't being updated by `SetParentBedCommand` (verified — it was, immediately).
- The 500 ms debounce timer wasn't firing (the most plausible-sounding theory, and partly true — see root cause).

**Key signal**: tracing `_update_soil_mismatches` showed it ran on every soil-test save and every position change *during* the drag, but never *after* the parent-link mutation that completes the drop. Cross-referenced with Qt docs: `QGraphicsScene.changed` is described as "emitted when the scene changes", which everyone reads as "any state change". It is not — it's "any *visual* change". Python attribute writes don't trigger it.

**Root cause**: [src/open_garden_planner/ui/canvas/canvas_view.py:651-654](src/open_garden_planner/ui/canvas/canvas_view.py#L651-L654) — the debounce that drives soil-mismatch refresh is wired exclusively to `scene.changed`. After a drag, `_update_plant_bed_relationships` calls `SetParentBedCommand` which mutates `parent_bed_id` and `_child_item_ids` — plain attribute writes that emit no Qt signal and trigger no scene-rect invalidation. The 500 ms timer never restarts for the parent-link change. The next genuine scene change (e.g. the user editing pH) is what finally refreshes — explaining why steps 4 and 6 of the repro work and steps 3 and 5 don't.

**Fix**: Add `trigger_soil_mismatch_refresh(scene)` (commands.py) that walks `scene.views()` and calls `refresh_soil_mismatches()` on the canvas. Call it from `SetParentBedCommand.execute/undo` so every attach/detach call site (drag, properties-panel "Unlink", future) stays in sync. Bonus catch in the same fix: `SetParentBedCommand` also wasn't elevating the plant's z above the bed's, so a plant drawn before its bed rendered behind it after attach — same class of bug (mutation without re-establishing the invariants the rest of the canvas assumes). Both invariants — z elevation and soil-mismatch refresh — now run inside the command, with the elevation rolled back symmetrically on undo via a `_pre_execute_z` snapshot.

**Lesson**: When a debounced/event-driven refresh handler exists, it imposes an *implicit contract* on every callsite: "if you change state I depend on, you must also produce the event I'm listening to." Python attribute writes never satisfy that contract. Two durable mitigations: (a) funnel state changes through Commands and put the refresh trigger inside the Command rather than at every caller; (b) when adding a new debounced handler, write down the contract in the docstring so the next person extending the code paths knows it exists. Bonus rule: any time you find a fix that's "do X also at site Y", grep for *every* callsite of the same operation — there are almost always 3-5 more.

---

## Case study: tangent constraint flips to the opposite side of the circle on drag (PR "make snap-constraints real", fixed 2026-06-07)

**Symptom**: Draw a line tangent-snapped to a circle, then drag the circle. v1: the line stalls into a *radial* line through the centre ("stable but wrong"). After fix-1 (signed residual) v2: holds for small drags but a large drag *flips the contact to the opposite side*. After fix-2 (continuity warm-start) v3: connectivity holds but *tangency drifts off* (line slides to radial, constraint red). After fix-3 (drop POINT_ON_CIRCLE, pure tangent) v4: tangent holds but *the contact is no longer welded to the rim* (it slides along the line) — the user needs both.

**Wrong theories**:
- *Sign of the emitted signed-radius is inverted* (most plausible). Disproved by the user's own `[TANGENT] emit` log: `sign=+1`, contact on side R, `signed_dist=+320=target` at creation — sign was correct.
- *The creation-time `apply_constraint_solver()` (both items free) flips it*. Disproved — headless creation solve is a no-op (residuals 0 at the snapped point).
- *Coordinate-space mismatch between `snap.point`/`mapToScene` and the solver's `get_anchor_points`*. Disproved — both are scene coords via the same `mapToScene`.

**Key signal**: instrument both the emit (one-shot) and `_propagate_constraints_during_drag` (per-frame) with `[TANGENT]` prints, then have the user run from a terminal (the full GardenPlannerApp hangs in the agent sandbox but runs fine for the user). The per-frame log showed `signed_dist` sliding `+320 → 0 → −320` and settling at `−target` with `side` flipping `R→L` — a clean trajectory through the centre, not a one-shot sign error. Reproduced headless ONLY after matching the user's drag *magnitude and direction* (earlier small/wrong-direction repros passed). The decisive repro drove `_propagate_constraints_during_drag` frame-by-frame with the user's exact geometry from the log.

**Root cause**: the welded-tangent the user wants is `POINT_ON_CIRCLE` (contact on rim) + tangency. The trap was *how* tangency was expressed. Expressed as **"signed perpendicular distance centre→line = ±radius"**, its gradient is the *line-normal*, which at a tangent config is **parallel** to `POINT_ON_CIRCLE`'s *radial* gradient → rank-deficient Jacobian → the pair is degenerate and the solver drifts/stalls/flips (v1–v3 were all faces of this one ill-conditioning, compounded by an unsigned-`|cross|` kink and a stale from-original warm-start). Dropping POINT_ON_CIRCLE (v4) removed the degeneracy but lost the weld. The fix is to express tangency by a residual whose gradient is *orthogonal* to the radial one.

**Fix**: redefine `ConstraintType.TANGENT` as **"the edge is perpendicular to the radius at the contact"** — residual `(C−v1)·(v0−v1)/|edge|` (radius projected onto the edge → 0), gradient *along the edge*. Emit it **with** `POINT_ON_CIRCLE`: the radial gradient (POINT_ON_CIRCLE) and the edge-aligned gradient (TANGENT) are **orthogonal** → full-rank, non-degenerate. The contact is welded to the rim AND stays tangent, and co-moves with the circle. Enforce both passes (Gauss-Seidel translates along the edge by the residual — closed-form; Newton residual as backup) and keep the continuity warm-start (the contact-on-rim still has 2 antipodal solutions; continuity picks the near one). Files: [core/auto_constraint.py](src/open_garden_planner/core/auto_constraint.py), [core/constraints.py](src/open_garden_planner/core/constraints.py), [core/constraint_solver_newton.py](src/open_garden_planner/core/constraint_solver_newton.py), [ui/canvas/canvas_view.py](src/open_garden_planner/ui/canvas/canvas_view.py). See ADR-024.

**Lesson**: (a) When pairing constraints, **the residual *formulation* decides conditioning, not just the geometry you mean**. "Tangent" can be written as "distance-to-line = r" (gradient ∥ radial → degenerate with POINT_ON_CIRCLE) or as "edge ⟂ radius" (gradient ⟂ radial → well-conditioned). Same geometry, opposite numerical behaviour. Before concluding "this pair is impossible," try re-expressing one residual so its gradient is orthogonal to the other's at the solution. (b) Two constraints whose gradients are *parallel at the solution* are rank-deficient — the solver drifts no matter how good the warm-start. (c) A constraint with multiple solutions (contact-on-rim = 2 antipodes) needs *continuous* warm-starting; any driver that re-solves "from scratch" each frame breaks it while single-solution constraints keep working, hiding the bug until you add a multi-solution one. (d) When a GUI bug won't reproduce headless, get the *exact* user coordinates from instrumentation and drive the *exact* event path (live `_propagate_constraints_during_drag`, not `_compute_constraint_propagation`) — the `[TANGENT]` log pinned magnitude + direction and turned a non-reproducing test red.

## Case study: new curve edit-handles appear but are completely inert / can't drag (issue #193, fixed 2026-06-08)

**Symptom**: New `CurveControlHandle` widgets render on a selected Bezier/Arc (blue/green squares show), but no handle — and seemingly nothing — can be dragged; the curve feels "stuck in place." All the unit/integration tests that called the item hooks (`_move_control` etc.) directly were green, so the geometry/undo logic was provably fine.

**Wrong theories**:
- *The reshape math or undo snapshot is wrong*. Disproved — the model hooks pass every direct test; the geometry mutates correctly when `_move_control` is invoked.
- *The handle's own `mousePressEvent`/`grabMouse` is broken*. Disproved — the handle mirrors `VertexHandle` exactly (same `grabMouse()` + `ItemIgnoresTransformations` + zValue).
- *The draw tool is still active and eats the clicks*. Disproved — `add_item`/`bezier_tool` don't auto-select, so handles only appear once the user has selected with the SELECT tool, which lets item clicks through (`select_tool.mouse_press` returns `False`).

**Key signal**: tried to write a view-level reproduction. A hand-built `QMouseEvent` passed to `view.mousePressEvent` did **not** deliver to the handle (`scene.mouseGrabberItem()` stayed `None`, event unaccepted) **even though `itemAt` found it** — because Qt won't hit-test/deliver a synthetic press to an `ItemIgnoresTransformations` child (this is *also* why the polyline tests never drive view-level events). Switching to `QTest.mousePress` on `view.viewport()` (real event dispatch) finally grabbed the handle — and exposed that `view._active_drag_handle` was `None` after the press.

**Root cause**: `CanvasView` works around a PyQt6 bug where Qt **silently drops the mouse grab on `ItemIgnoresTransformations` child items between events** by tracking `self._active_drag_handle` on press and re-establishing the grab in `mouseMoveEvent`/`mouseReleaseEvent`. That tracking only fires for an allow-list of handle types (`isinstance(grabber, (ResizeHandle, RotationHandle, VertexHandle, RectCornerHandle, MidpointHandle))`). The new `CurveControlHandle` wasn't in the tuple, so the press grabbed but the grab was dropped before the first move and never re-established → the handle got the press and *no moves* → inert.

**Fix**: add `CurveControlHandle` to the allow-list tuple (and its import) in [ui/canvas/canvas_view.py](src/open_garden_planner/ui/canvas/canvas_view.py). One-line behavioural change. Regression test `TestHandleDragViaView` drives the real path with `QTest` and asserts `view._active_drag_handle is handle` after the press (fails without the fix, passes with it).

**Lesson**: (a) **Any new in-scene handle that uses `ItemIgnoresTransformations` must be registered in `CanvasView`'s `_active_drag_handle` allow-list** — the dropped-grab workaround is opt-in by type, so a faithful copy of `VertexHandle` is still dead until the view knows about it. Grep `_active_drag_handle` when adding a handle class. (b) Tests that call item hooks directly can't see a view-routing bug; the riskiest layer (press→grab→move delivery) needs a **real** event-path test. (c) `QGraphicsView` does **not** deliver a hand-constructed `QMouseEvent` to `ItemIgnoresTransformations` children — use `QTest.mousePress/Move/Release` on `view.viewport()` (and `centerOn` the target first so it's inside the viewport) for faithful handle-drag tests.

---

## Case study: rotated circle drag-resize collapses / drifts / ghosts (issue #218 follow-up, fixed 2026-06-17)

**Symptom** (PR #221 manual test, screenshots): drag-resizing a 45°-rotated plant was incoherent — a diagonal corner drag barely changed the diameter or collapsed it to ~minimum, the centre drifted across the canvas, the dragged handle did not follow the cursor, and a translucent "ghost" disc lingered where the spacing ring had been.

**Wrong theories**:
- *The #218 `_reanchor_after_rotated_resize` re-pin is wrong*. Partly — but the band-aid was correct for what it did (it held the serialization invariant; the headless trace showed `serialized == visualCenter` throughout). The rot was *underneath* it.
- *The spacing ring should scale with the footprint*. No — that decoupling is the intended #218 model (confirmed with the user); not the bug.
- *Missing `prepareGeometryChange` is the whole bug*. No — that only explained the ghost disc, not the collapse/drift.

**Key signal**: a scripted headless reproduction (place plant → `_apply_rotation(45)` → feed a cumulative-delta drag through the real `ResizeHandle._apply_resize`, printing `rect/radius/pos/origin/visualCenter` each step) showed a `BOTTOM_RIGHT` drag of `(80,80)` leaving **radius stuck at 50.00** — zero growth — and a `TOP_LEFT` outward drag *shrinking* the circle while the supposedly-fixed corner moved **45 cm**. At exactly 45° a screen-diagonal drag projects entirely onto one local axis (`local_dy ≈ 0`), so `min(width, height)` picked the *unchanged* axis.

**Root cause**: three compounding faults in the interactive resize of a rotated circle. (1) `CircleItem._apply_resize` squared via `min(width, height)` — incoherent once `width ≠ height` under rotation (and it capped MIDDLE-handle growth entirely, since `new_height == init_height`). (2) Two *disagreeing* notions of "what stays fixed": `CircleItem` inferred the fixed edge from **scene-space** `abs(pos_x − init_pos.x()) < 0.01`, while the re-anchor inferred it from the **rotated local** `pos_dx == 0` — under rotation they disagree, so the re-anchor pinned the wrong corner → drift. (3) Neither the per-item resize nor the shared helper called `prepareGeometryChange()`, so the shrinking `boundingRect()` (which includes the spacing-ring expansion) left stale pixels → ghost.

**Fix**: stop post-correcting an incoherent step — replace it. The interactive `ResizeHandle._apply_resize` now takes the fixed corner/edge **authoritatively from `self._position`**, lets the item normalise the rect (`CircleItem._constrain_resize_size` squares it so the dragged handle *tracks the cursor* — corner → `max(w,h)`, edge → that axis, so a side handle can now grow a circle), applies it through `resize_rect_item_keeping_anchor` (now `prepareGeometryChange()` + origin re-pin), and refreshes via `_after_resize_geometry()`. The rotation-gated `_reanchor` and the `min(w,h)` + scene-space guess are deleted. Pinned by `tests/integration/test_rotation_aware_resize.py` ({Circle,Rect,Ellipse}×{0,45,215°}×{corner,edge}). See ADR-028 + §11.4.

**Lesson**: (a) **Don't post-correct an incoherent geometry step — fix the step.** A re-anchor layered over `min(w,h)` + a dual fixed-corner inference can never be right because the layer beneath produces nonsense; the senior review flagged this exact fragility before it shipped. (b) When a gesture has a "fixed reference", derive it from the **one authoritative source** (the handle position), never re-infer it in two places in two coordinate frames — they *will* disagree under rotation. (c) A scripted headless drive of the real event-handler (`ResizeHandle._apply_resize` with cumulative deltas) printing geometry each step nails magnitude+direction bugs that a GUI can only show vaguely — and at exactly 45° watch for axis-projection degeneracies (`local_dy ≈ 0`) that `min()`/`max()` turn pathological. (d) Any shrink of a custom `boundingRect()` needs `prepareGeometryChange()` or Qt leaves a ghost.

---

## Case study: export_dxf works in dev venv but errors "No module named 'unittest'" only in the frozen exe (US-D1.4, fixed 2026-07-04)

**Symptom**: the new Agent API `export_dxf` MCP tool worked perfectly under `pytest` and a plain venv script, but calling it against the packaged `.exe` returned an MCP tool error: `"Error executing tool export_dxf: No module named 'unittest'"`. The other three new D1.4 tools (`save_plan`, `export_pdf`, `export_csv`) and the pre-existing `render_canvas_image` all succeeded against the same running frozen exe — only the DXF path failed.

**Wrong theories**:
- *Something about running inside `anyio.to_thread.run_sync` + `MainThreadBridge.run_on_main`'s worker thread breaks frozen imports*. Disproved — `render_canvas_image` goes through the exact same async/thread-hop machinery and worked fine.
- *A `sys.meta_path` shim in a plain venv script simulating PyInstaller's `excludes=["unittest"]`* seemed like a reasonable stand-in for reproducing the frozen behaviour without a full rebuild — it wasn't: blocking `unittest` via `sys.meta_path` in a normal interpreter and calling `ezdxf.new()`/`doc.saveas()` succeeded even with the block in place, which incorrectly suggested `ezdxf` itself doesn't need `unittest` at runtime at all. A pure-Python import-blocking trick does not faithfully reproduce a PyInstaller `excludes` list — the real bundle simply has no `unittest` bytecode anywhere, which is a stronger condition than "the next `import unittest` raises."
- *It must be a bug specific to my new `agent_api/exports.py` module* — disproved once the traceback showed the failure was three frames *inside ezdxf's own import graph*, nothing to do with `exports.py` at all.

**Key signal**: the app is built windowed (`console=False` in `installer/ogp.spec`), so an exception caught by FastMCP's tool-error handling never surfaces a traceback anywhere visible — MCP just returns the stringified exception. Wrapping the one call site (`DxfExportService.export(...)` inside `export_dxf_file`) in a `try/except` that wrote `traceback.format_exc()` to a file, rebuilding, and re-triggering the call from a real MCP client produced the real chain:
```
export_dxf_file → dxf_service.py:100 (import ezdxf)
  → ezdxf/__init__.py → ezdxf/filemanagement.py → ezdxf/tools/standards.py
  → ezdxf/render/__init__.py → ezdxf/render/mleader.py → ezdxf/entities/__init__.py
  → ezdxf/entities/acad_proxy_entity.py → ezdxf/query.py → ezdxf/queryparser.py
  → pyparsing/__init__.py → pyparsing/testing.py
ModuleNotFoundError: No module named 'unittest'
```
Every one of those is a plain, **unconditional** module-level `import` — so this chain fires on the *first-ever* `import ezdxf` anywhere in the frozen process's lifetime, regardless of whether it's triggered by DXF export, DXF import, or the new agent tool.

**Root cause**: `installer/ogp.spec`'s `excludes` list had `"unittest"` (presumably added purely to trim bundle size, with no comment explaining why). `ezdxf`'s DXF-entity-query support (`ezdxf.query`, unconditionally imported by `ezdxf.entities.acad_proxy_entity`, unconditionally imported by `ezdxf.entities`, unconditionally imported by `ezdxf.render`, unconditionally imported by `ezdxf.tools.standards`, unconditionally imported by `ezdxf.filemanagement`, unconditionally imported by `ezdxf/__init__.py` — i.e. reachable from *any* `import ezdxf`) depends on `pyparsing` for its query-string grammar. `pyparsing/__init__.py` unconditionally imports its own `pyparsing.testing` submodule, which subclasses `unittest.TestCase` for a test-assertion mixin — a genuine (if surprising) *runtime* dependency on `unittest`, not merely a test-time one. This is a **pre-existing latent packaging bug** predating this PR — it would have broken the already-shipped GUI "Export as DXF"/"Import DXF" (US-12.3/12.4) too, the first time either was exercised in a freshly-built frozen exe. It simply hadn't been caught because manual DXF testing is normally done against the dev venv, and this PR's exe-verification step was the first thing in a while to exercise a DXF codepath in an actually-frozen build.

**Fix**: remove `"unittest"` from `installer/ogp.spec`'s `excludes` list, with a comment explaining the `pyparsing.testing` chain (mirroring the existing `# NOTE: do NOT exclude "multiprocessing"` comment already in that list for an analogous uvicorn reason). Verified end-to-end: rebuilt the exe, called `export_dxf` via a real MCP client against the running frozen server — file now written successfully (`FILE_EXISTS=True`, valid DXF content) — and re-ran the full `pytest`/`ruff`/`bandit` gates to confirm the un-exclude introduced no regressions.

**Lesson**: (a) A packaged app's `excludes` list is a claim about the *entire* transitive dependency graph never needing a module at runtime — a claim that can be silently falsified by a *sub-sub-dependency* nobody audited (here, `pyparsing`, pulled in only because `ezdxf` happens to support DXF entity queries). Before excluding a stdlib module to save space, grep the actual dependency tree for it, or accept that the first *unexercised* codepath through a frozen build might discover the gap. (b) When a `console=False` (windowed) frozen app hides a real traceback behind a caught-exception error string, temporarily wrap the *one* suspect call in a `try/except` that writes `traceback.format_exc()` to a file, rebuild, reproduce, read the file, then remove the instrumentation — don't try to simulate "missing from a frozen bundle" with a `sys.meta_path` import-blocking trick in a normal interpreter; that only proves the module isn't *cached*, not that it's genuinely absent, and can produce a false negative that sends you down the wrong path. (c) When a new feature is the first to exercise a codepath (DXF, in this case) in a freshly rebuilt exe, a failure there may not be "new" at all — check whether *any* existing, already-shipped feature shares the same first-import trigger before assuming the bug is scoped to your change.

## Case study: a new regression test failed *with* the fix applied — the harness was the variable (#283, fixed 2026-07-27)

**Symptom**: while fixing #283 (three `QToolBar`s missing an `objectName`), a new integration test asserting that a hidden toolbar's state survives a `saveState()`/`restoreState()` round trip failed **with the fix applied**, at `assert category.isHidden()`. The identical sequence, run as a standalone script, passed. The test also failed when run alone, so it was not test-order interference between the file's own tests.

**Wrong theories**:
- "`restoreState()` applies visibility lazily; the script's `processEvents()` is doing the work." Refuted by instrumenting both paths: visibility was applied immediately, before any event processing, in both.
- "The fix doesn't actually work in this scenario." Refuted by the same probe reporting the correct toolbar hidden.

**Key signal**: the standalone script and the pytest run differed in exactly one input nobody had listed as an input — the *contents of the QSettings store at construction time*. `GardenPlannerApp.__init__` calls `_restore_ui_state()`, which restores a previously saved window state and thus a previously saved toolbar layout.

**Root cause**: `app/ui_state.py`'s `UiStateStore` constructs `QSettings("cofade", "Open Garden Planner")` **directly** instead of going through `app/settings.py`, so `tests/conftest.py::isolate_qsettings` — which works by replacing `AppSettings.__init__` — never covered it. Every full-app test was silently reading the developer's *real* saved window state (and rewriting it at teardown, because pytest-qt closes registered widgets and `closeEvent` persists UI state — measured at 120 real-store writes from a single test file). Earlier throwaway probes in the same session had left a layout with `CategoryToolbar` hidden in that real store, so the test's precondition was already violated before its first line ran.

**Fix**: first an autouse `_isolate_ui_state` fixture pointing `ui_state.QSettings` at the test key (local runs then also matched CI, where the store is always pristine). **#285 / ADR-041 then did the real repair and deleted that fixture**: `app/settings.create_qsettings()` is now the only place that constructs or even names a settings store, and `tests/conftest.py` rebinds `settings.ORGANIZATION_NAME` / `APPLICATION_NAME` — which the factory re-reads on every call — **at its own import time, at module scope, not in a fixture**. pytest imports the root conftest before any test module, so every store the app builds, including one built while a module is being imported, lands in the test key. A fixture could not do this: it runs after collection, and a `QSettings` binds its organization/application at construction. Enforced by `tests/unit/test_settings_chokepoint.py` (an AST walk over `src/` *and* `tests/`: nobody else may name `QSettings`, and nobody should build a store at import time — such a store can be redirected by nothing afterwards; belt-and-braces behind the conftest redirection, not the guarantee itself) + `tests/integration/test_settings_isolation.py` (spies `QSettings.value`/`setValue` during a full app boot).

**Lesson**: when a test fails *with* a fix that a direct probe says works, suspect the harness before the fix — and enumerate the hidden inputs. Persistent state (QSettings, registry, `<app-data>` files) is an input to every test that constructs a window, whether or not the test mentions it. Corollary: an isolation fixture only covers the construction path it patches; a second store that hand-rolls its own `QSettings` gets a free pass and nobody notices until its state changes under a test. Also worth knowing before you try to "just look at the console": on Windows, Qt's default message handler writes to `OutputDebugString` rather than `stderr` when `stderr` is not a console, so piping the app's output through `grep` prints **nothing** whether or not the warning fires — `qInstallMessageHandler` is the only reliable programmatic instrument.

**Corollary — the same trap bites the probe, and it bites the developer's real config** (found in manual testing of the very same PR): a throwaway script that constructs `GardenPlannerApp` runs **outside** pytest, so `tests/conftest.py` isolates nothing. `AppSettings` and `UiStateStore` both resolve to the real `QSettings("cofade", "Open Garden Planner")`. The probes for #283 each opened with the line the test fixtures legitimately use — `get_settings().show_welcome_on_startup = False` (to keep the modal Welcome dialog from blocking) — and thereby **persisted it into the user's own configuration**. Symptom reported after the branch was pushed: "the window to pick and load old projects is missing, you land straight on an empty canvas." Nothing in the diff caused it; the debugging did. Any probe script that constructs the real app must redirect the store first — or never write a setting at all. Since #285 that is **one** line, not two: `open_garden_planner.app.settings.ORGANIZATION_NAME = "cofade_probe"` (plus `APPLICATION_NAME`) before building the window, or patch `settings.create_qsettings` to a temp INI as `tests/unit/test_ui_state.py` does. `AppSettings` and `UiStateStore` both take their backend from that factory, so there is no second store left to forget. Also: if the app writes state at teardown, do not call `win.close()` in a probe; just let the process exit. And when a probe is done, diff the real store (`QSettings(...).allKeys()`) against what you expected to touch, rather than assuming the script was read-only.

## Case study: editing "Current Spread" shrinks the shadow but not the plant icon (issue #299, fixed 2026-08-08)

**Symptom**: a user assigned a Trefle-sourced Apple tree (max spread 590 cm) to a plant, which correctly resized the drawn footprint. They then set "Aktuelle Breite" (`current_spread_cm`) to 200 cm, since the tree was young. The sun/shade shadow visibly thinned to a 200 cm-wide shadow — but the SVG tree icon on the canvas stayed at 590 cm, unchanged.

**Investigation, not a wrong-theory chase this time**: reading the code (not instrumenting) settled it in three steps, because the answer was already written down. (1) `plant_database_panel._on_current_spread_changed` → `_update_instance_metadata` writes `metadata["plant_instance"]["current_spread_cm"]` and calls `self._current_plant_item.update()` (a repaint request) — it never touches `self.radius`/`rect()`. (2) `CircleItem.paint()`'s plant branch computed `diameter = rect.width()` directly — a fixed value set once by `set_radius_centered()` at species-assignment time — with no read of `current_spread_cm` or the growth model at all. (3) `core/plant_sizing.py`'s own module docstring explicitly documents this as **intentional**: "a fourth size input this module deliberately does NOT own... it does not affect the spacing ring or the spacing-overlap diagnostic, which stay on the MATURE `max_spread_cm`... One plant can therefore legitimately show three different sizes at once: the drawn circle (selection/snapping), a mature spacing ring, and a smaller measured shadow canopy."

**Root cause**: not a bug at the time — a deliberate, and more thoroughly documented than first found, design decision. The module docstring said "deliberately does NOT own this"; a deeper check found ADR-037's growth addendum states it as an accepted decision with an explicit **rejected alternative**: "the 2D canvas keeps drawing the stored (mature) footprint... not by rescaling canvas circles (rejected: a display-scale on live items perturbs selection/snap/`mapToScene`, exactly the #218/#219 territory)."

**First resolution attempt — confirmed with the user via `AskUserQuestion`, then found broken by senior review before merge.** The user chose to decouple the icon's visual size from the spacing footprint (`CircleItem._visual_plant_diameter_cm()`, growth-model-driven, falling back to the footprint diameter when no growth data exists; `boundingRect()`'s overflow clamped so a shrunk icon never advertises less than the footprint, but still grows for an over-measured plant). Every test passed. A senior-review pass then rendered it and found the decorative drop-shadow — a cosmetic depth effect drawn from `self.rect()`, unrelated to sun/shade — was left at the full mature footprint size while the icon shrank: **a young plant rendered as a large grey disc with a tiny sprite inside it**, measured at 57.6% grey coverage of the frame versus 1.5% before the icon changed size. Reverting the one changed line in `paint()` left all 21 tests green — not one test painted anything.

**Second pass, informed by the review**: told the user plainly that this contradicted an accepted ADR and had a real rendering regression, and asked how to proceed rather than silently patching around either problem. The user's call: they didn't want the ADR's conclusion kept ("I don't care for this previous ADR, we can change it" — a full-size icon casting a visibly smaller shadow read as a bug to them, not a feature), so the ADR was amended in place rather than silently contradicted. The fix computes the diameter **once** at the top of `paint()` and reuses it for both the drop-shadow and the icon (the two can no longer disagree), `plant_database_panel._update_instance_metadata()` now calls `prepareGeometryChange()` unconditionally rather than only for `current_spread_cm` (review found `current_height_cm` and `planting_date` equally change the growth-derived diameter), and `core/plant_renderer.render_plant_pixmap()` now caps its `QImage` allocation at the actual allocation site (`current_spread_cm`'s spin box had no bound and reaches the exact `int(diameter)`-square allocator issue #291/D2.1 already had to cap for a different caller).

**Lesson**: (1) before instrumenting a "why doesn't X update" bug, check whether the gap is *documented* — but check the ADRs, not just the nearest docstring; a module comment can undersell how deliberately something was decided. (2) When a user's mental model conflicts with a documented decision, that's a product conversation before it's a code change — confirming a UX preference does NOT excuse skipping the review a reversed architectural decision deserves. (3) **A green test suite that only asserts against private helpers proves nothing about what a user actually sees** — this fix's real deliverable was a rendered frame, and nothing painted one until a reviewer did. Any change to `paint()` needs at least one test that renders to a `QImage` and measures something about the actual pixels, not just the values fed into it. (4) Reversing an ADR is legitimate with the right authority, but it's still a reversal — amend the ADR in the same change, don't leave it contradicting the code.

---

## Case study: Trefle search results never carried sun/water/pH/foliage data -- dead code, a wrong theory refuted live, and three more bugs found only by trying to break the fix (issue #297, fixed 2026-08-10)

**Symptom**: every plant found via the online species search and assigned from Trefle showed Sun/Water/pH/Foliage as "Unknown"/empty in the Plant Details panel, no matter how the #296 field-mapping fix improved `TrefleClient._parse_species()`.

**Investigation, not a wrong-theory chase this time -- one live call settled it in thirty seconds**: rather than guess, a throwaway probe script (`.env`'s real `TREFLE_API_TOKEN`, never printed) hit the actual API: `GET /plants/search?q=carrot` returned only `['author', 'common_name', 'family', 'genus', 'id', 'image_url', ..., 'scientific_name', 'slug', ...]` -- no `growth`, `specifications`, `foliage` at all. `GET /plants/171170` (the search result's own id) returned all three, nested under `data.main_species`. `PlantAPIManager.get_by_id()` already existed, fully implemented per provider -- but grepping the UI found it was never called from the search-selection flow. `PlantSearchDialog` assigned the raw sparse `search()` result straight through. **Root cause: dead code**, not a parsing bug.

**Fix, and four more rounds of senior review, each catching a real bug in the previous round's own fix -- every claim settled with either a live API call or a positive control (temporarily revert, confirm the pinning test fails with the expected error, restore), never by argument alone:**

1. Wire `PlantAPIManager.get_by_id()` into `PlantSearchDialog._enrich_selected_plant()`, called on confirm (OK/double-click) -- once, not per browsed row, to bound the extra request cost against rate-limited free tiers.
2. **Round 1 reviewer claimed** `get_by_id()` reads the wrong nested id and silently mutates `source_id`/`species_key` -- with plausible-looking but fabricated numbers (that reviewer had no `.env` access in its isolated worktree). **Refuted with a live call**: requesting `/plants/171170` for 4 species (carrot/tomato/apple/basil) showed the top-level `data.id` genuinely differs from the request (live: 171241 vs 171170) -- but `main_species.id` reliably equals it every time. The claim was wrong on the mechanism but right that the code deserved a guard; added one anyway (`detail.source_id == plant.source_id`), which turned out load-bearing for round 3.
3. **Round 2 reviewer caught**: the guard added in round 1 also rejected `common_name in ("", "Unknown")`, reasoning an empty name meant a bad response -- but Trefle genuinely omits `common_name` for real, scientific-name-only species, so the guard discarded fully-populated, correctly-identified records for exactly the plants this fix existed to help. Fixed by validating `source_id` alone.
4. **Round 3 reviewer caught two bugs in round 2's own fix, reproduced with an actual positive control each time**: (a) with only the `source_id` check left, the code did `self._selected_plant = detail` -- a wholesale swap that silently blanked `common_name`/`family`/`genus`/`image_url` whenever the detail response validly omitted them (a null-`common_name` test fixture proved it: `common_name` came back `"Unknown"`, not `"Carrot"`). Fixed with an explicit merge preserving six "identity" fields from the search result. (b) The `QMessageBox.warning()` added in round 1 opens a nested Qt event loop; the dialog's 500ms search-debounce timer could still be armed when it fired, and the nested loop let the timer deliver mid-commit -- `_perform_search()` ran, nulled `_selected_plant`, and `accept()` then closed the dialog with nothing selected. Same failure class as the #210 debounce/flush incident elsewhere in this project. Fixed with `self._search_timer.stop()` as the literal first statement of `_on_accept()`.
5. **Round 4 reviewer, this time WITH live credentials, caught two more**: (a) the six-field identity allowlist from round 3 just relocated the same data-loss bug to the other ~40 fields -- generalized to a loop over every dataclass field, preferring `detail`'s value unless it's at the field's own default (`MISSING`/`default_factory`-aware) and the search result's isn't. (b) Live-probing Perenual (not just Trefle) found its free tier returns **HTTP 429 with a healthy rate-limit budget remaining** for any species detail beyond a low id threshold -- a paywall gate, not rate limiting (body: "Please Upgrade Plan"). Undetected in rounds 1-3 because nobody had tried a live call against a *second* provider. Left as `except Exception` this would nag the user with a scary modal on every single confirm for an entirely ordinary, expected free-tier limitation -- a new `PlantDetailUnavailableError` distinguishes "no richer data exists" from a genuine failure so it can be handled quietly.
6. **Round 5 reviewer, with live credentials again, found the round-4 generalization had a gap and -- worse -- a live-reproducible crash in code four rounds of review had already touched**: (a) the generic merge's `detail_value == f.default` check is not `None`-safe (`None == ""` is `False`), so a client emitting a present-but-null value for a `str` field defeated it entirely; fixed with a blanket `detail_value is None` check first. (b) Trefle's `get_by_id()` had `main_species = plant_data.get("main_species", plant_data)` -- the exact present-but-null `dict.get(key, default)` trap #296 already fixed twice elsewhere in the SAME file -- and round 3's own comment on that exact line asserted, wrongly and without checking, that this was "a shape never observed live." Live-reproduced on real ids 443432/453675/439035 (all scientific-name-only species, ~4% of a 72-id sample): `main_species` genuinely is `null`, `_parse_species(None)` threw a bare `AttributeError`, uncaught by the method's own `except requests.RequestException` -- only the dialog's round-3 `except Exception` stood between this and a hard crash. Fixed identically to the Perenual case (`PlantDetailUnavailableError`, quiet fallback), and swept the four sibling `.get(key, default)` call sites in the same method to the None-safe `.get(key) or default` idiom while there.
7. **Manual testing (not a review round) caught a defect one layer above the fix, after all seven rounds shipped**: the user reported "Tomato" showing Full Shade/Low water/no pH in the Plant Details panel after search+confirm -- looking exactly like the fix had failed. Live-probing `TrefleClient` and the merge logic directly (bypassing the dialog) proved the enrichment pipeline itself was correct: `Full Sun`/`Medium`/`pH 7.0-7.5`, matching Trefle's real API data. The actual cause was pre-existing and one layer up: `PlantAPIManager.search()` always searches the user's local custom-plant library FIRST, concatenated ahead of any API result with no deduplication -- and the real, unstubbed `%APPDATA%\OpenGardenPlanner\custom_plants.json` on the test machine had accumulated 197 entries (180 of them duplicate "Walnut" test debris), including a stale custom "Tomato" record with wrong sun/water values whose `source_id` happened to collide with Trefle's own numeric id. That record was returned first, displayed with text identical to the real Trefle result (`Tomato (Solanum lycopersicum)`), and -- correctly, by design -- skipped enrichment entirely because `data_source == "custom"`. Fixed by labelling every search-result row with its data source, so a stale custom entry can never again be visually indistinguishable from a live one.

**Lesson**: (1) a client's own tests passing with `search()` and `get_by_id()` fixtured *independently* proves nothing about whether the *caller* reaches for the richer one when it should -- the bug was a wiring gap invisible to unit tests of either method alone. (2) When a reviewer makes a specific, checkable factual claim ("the API returns X"), check it against the API, not against the reviewer's confidence -- a wrong claim can still point at a real gap (round 1) as easily as it can be flatly refuted by one real request (round 4's Perenual finding proved the opposite of round 1's Trefle guess: a mismatched id *is* real, just for a different reason). (3) **A validation guard is itself untested code until something specifically tries to make it wrongly reject a *good* input, not just correctly reject a bad one** -- four rounds of tests proved the guard caught bad responses; nobody proved it let a valid-but-unusual one through until round 2 went looking. (4) A fix that reasons carefully about a bug class and hand-lists six fields it applies to is a promise about the other forty fields nobody checked -- prefer a loop over the type's own fields to a hand-maintained list, when the type is stable and the check is generic. (5) **A confidently-worded comment asserting a fact about live behavior ("never observed live") is worse than no comment if it's wrong** -- round 3 wrote it, round 5 disproved it with the same three-line probe script that should have been run before the comment was written. (6) **The whole five-round saga started because nobody had made one real API call before writing the fix, and the worst of the fix's own bugs -- a live crash in the primary provider -- was caught only on the fifth pass, once someone finally probed the specific shape a confident comment had dismissed** -- this project's `.env` has working credentials for all three plant-API providers; use them before theorizing about response shapes, and don't trust a comment's claim about live behavior any more than a reviewer's. (7) **Six rounds of review, run against isolated worktrees and mocked HTTP, structurally cannot catch a bug that only exists in real, unstubbed machine state** -- the custom-plant-library file is real disk state on the developer's own machine, outside git, outside any test fixture, and outside every reviewer's clean worktree. Manual testing against the actually-running app, with actual accumulated state, is the only phase in this project's workflow that can see it -- exactly why CLAUDE.md makes it the final, sovereign gate rather than a formality after review passes.


## Case study: "probable memory leak" after an hour idle — two `scene.changed` feedback loops nobody could see (issue #305, fixed 2026-08-17)

**Symptom**: a macOS user worked in OGP for 15–20 min, left it in the background for ~1 h, and the whole system froze; the Force Quit dialog showed **Open Garden Planner at 134.01 GB** (Chrome, for scale: 7 GB). No logs — the OS restarted itself.

**Wrong theories** (all discarded by measurement): a per-tick allocation in the autosave timer (it early-returns when not dirty); the sun-shadow debounce (disabled by default); and — the one that survived into the first fix and was caught only in senior review — "the companion/spacing handlers are fine because their setters have an early-return guard", *measured with a `GENERIC_RECTANGLE` on the plan*, which those handlers skip entirely. Re-measured with one gallery-dropped plant carrying database spacing: 19 `changed` + 20 renders per 3 s, forever. A measurement that does not exercise the code path proves nothing about it.

**Instrumentation that found it** — counting, not printing state: (1) monkey-patch `MinimapWidget._do_update` with a counter and pump the event loop for a fixed window: `1 render / 1.5 s` with no overlay item, `13–14 renders / 1.5 s` with one *transformable* `zValue >= _OVERLAY_Z_MIN` item — a self-sustaining ~9 Hz loop. (Senior review later measured that `ItemIgnoresTransformations` items — every real handle/label/badge — emit no `changed` on `setVisible()` at all, so in production this loop is reachable only through the curve-edit connector lines; the reporter's churn came from the other three loops.) (2) Inside the real `GardenPlannerApp`, connect a counter to `scene.changed` and add one item at a time: `GARDEN_BED` never selected → `16 scene.changed + 8 minimap renders per 4 s`, forever; `GENERIC_RECTANGLE` → 0. (3) Wrap `item.update()` on that bed with `traceback.format_stack()` (the rule this skill exists for): every call came from `canvas_view.py:_on_soil_debounce_tick → _update_soil_mismatches` — the 500 ms soil debounce was calling `setToolTip()` + `update()` unconditionally, which re-emitted `changed`, which restarted the very timer that called it. Key measured Qt fact along the way: `setVisible()`/`update()` emit `changed` **asynchronously** — the hide's emission (with the rects) and the restore's (`[]`) arrive on two *separate* event-loop turns after the calling method returned — printing rects from a `changed` slot made that visible and killed the first fix idea (an in-call re-entrancy flag) and then the second (a single `singleShot(0)`, which cleared the flag between the two emissions; the implementer measured the loop surviving it).

**Root cause**: four independent `scene.changed` → timer → mutate-scene → `scene.changed` cycles — the minimap's hide/restore of overlay items around its render, the soil-mismatch refresh's unconditional `update()`, and the spacing and companion refreshers' "clear everything, then set" passes (which push every plant's value through `None` each tick, defeating the setters' guards) — each of which also fired every other `changed` subscriber (full-scene render into fresh pixmaps + O(n²) scans) ~10×/s while idle.

**Fix**: the minimap's `changed` slot is content-based — it remembers the scene rects of the overlay items it just toggled and ignores an emission iff every rect lies inside one of them (a first cut used a two-turn `singleShot(0)` timing window instead; senior review pointed out it silently dropped genuine changes sharing the turn and bet on Qt's emission count — replaced); a toggled-off minimap no longer renders; soil handlers made idempotent (write only on real change); spacing/companion compute the final state per plant and call each setter once, no clear pass. Pinned by `tests/integration/test_idle_scene_quiescence.py`: bed, DB-spacing plant, antagonist pair, selected plant with beneficial neighbour — settle 1.5 s, then 0 emissions and 0 renders over 2 s in the real app, plus a positive control.

**Lesson**: (1) for "leak while idle" reports, **count events per fixed time window** first — a loop shows up as a non-zero rate on a supposedly quiescent app long before any RSS graph moves (Windows RSS was flat at 59 MB while the loop spun; the platform that accumulated was the reporter's, not the dev box). (2) `scene.changed` gives you rects, not culprits — the only way to name the emitter is a stack trace at the mutation site (`item.update`, `setVisible`, `setPos`). (3) Every `scene.changed`-driven slot must be idempotent — *compute the final state, then apply once*; an early-return guard in the setter is necessary but not sufficient, because a handler that clears-then-sets defeats it every tick (`_update_container_capacity()` is the model; spacing/companion were not). (4) When a review says your measurement did not exercise the path, re-measure before arguing — the reviewer's plant-on-the-plan probe was right and the rectangle probe was worthless. (5) Report the hypothesis boundary honestly: the loop is proven and platform-independent; the 134 GB accumulation path on macOS is not — say so in the issue and ask for the measurement that would close it.


## Case study: full test battery stalls silently / settings reads return their defaults right after a write — a *second pytest process* was clearing the shared registry key (Package 3a #308, fixed 2026-08-17)

**Symptom**: `pytest tests/` (5 100 tests) stopped producing output for 18 minutes at `tests/integration/test_trellis.py`; the file passes alone in 6 s. Later runs: a `pytest-timeout` dump ending in `application.py … dialog.exec()` (the modal Welcome dialog) inside `test_idle_scene_quiescence.py`, although two fixtures had written `show_welcome_on_startup=False` before the app was built; and `test_nearest_snap_workflow.py::test_action_persists_setting` asserting `get_settings().nearest_snap_enabled is True` immediately after setting it — `False`. Different test every run; each passes alone.

**Wrong theories** (in order, all written down before being killed): (1) "a leaked slot/thread from an earlier full-app test, playbook rows 14–16" → written into §11.4 as an unsolved incident, refuted by the senior reviewer's stack dump naming the Welcome dialog (a §11.4 entry from #279 already described it — nobody had grepped §11.4 for "Welcome"). (2) "the settings-based Welcome guard loses a race with the 500 ms startup timer" → a class-level method patch made the dialog impossible, but the *default reads* kept happening (`nearest_snap`), so the guard was treating a symptom. (3) "`_reset_app_settings`'s `clear()` temporary is destroyed late and kills the singleton" → the mechanism half was real (see the probe below) but the trigger half was not: `weakref` showed the temporary dies at once, and per-key removal instead of `clear()` did *not* stop the failures.

**Instrumentation that found it** — three probes of ≤ 15 lines each, run with the venv's own PyQt6, no theory accepted without one: (a) `q1 = QSettings(k); q1.setValue("a", 1); t = QSettings(k); t.clear(); del t; q1.value("a") → DEFAULT` and further `q1` writes vanish — a `clear()`ed instance deletes the registry key **when destroyed**, turning every store built in between into a *black hole*; (b) the same with `t` kept alive across `s`'s construction: `s` reads fine until `del t`, then dies — destruction timing is the killer; (c) a **tripwire** in `_reset_app_settings` teardown that writes+reads a probe key on the live singleton and `pytest.fail("settings singleton is a BLACK HOLE …")` — it fired at the teardown of the *first* test of a three-file run, non-deterministically, and never with the same file set twice. That non-determinism plus "no in-process caller of `clear()` outside conftest" pointed *outside the process*: `Get-CimInstance Win32_Process | ? CommandLine -match pytest` — the senior-reviewer agent was running the same suite in its worktree, on the same fixed registry key `HKCU\Software\cofade_test\Open Garden Planner Test`. Decisive experiment: three files, 3 runs alone → clean; 3 runs with a deliberately concurrent pytest process → black holes every run; after the fix, 3/3 clean under the same concurrency.

**Root cause**: the test key was a fixed name shared by every pytest process on the machine; another process's per-test `create_qsettings().clear()` deleted it under this process's live `AppSettings` singleton, whose writes then vanished and whose reads returned class defaults — `show_welcome_on_startup` → `True` → modal `exec()` → hang; `nearest_snap_enabled` → `False`. The reviewer worktree running the suite *while the main battery runs* is the project's normal workflow, so the interference was systematic, and the "passes alone" signal was worthless because "alone" was never alone.

**Fix**: `TEST_APPLICATION = f"Open Garden Planner Test {os.getpid()}"` (per-process key; the session-end `clear()` removes it); `_reset_app_settings` wipes per key (`remove()` — immediate, key survives) instead of `clear()`, as in-process defence in depth; the tripwire stays; `_silence_welcome_dialog` (session-scoped class-level no-op) guards the dialog regardless of what any store says. `pytest-timeout` (180 s/test) stays as the detector that turned an 18-minute silence into a stack dump. Everything is in `tests/conftest.py`; §11.4 "silence the startup Welcome dialog" addendum + debugging-playbook row 35 record it.

**Lesson**: (1) **grep §11.4 for the symptom's nouns before writing a new §11.4 entry** — the first write-up misfiled a documented pitfall as unsolved, inside a documentation commit. (2) When a symptom is "reads return the default", ask *which store* the read hit and *who else can touch it* — including other processes: `QSettings` on Windows is a shared registry key, not a private object. (3) A probe that reproduces the *mechanism* is not a proof of the *trigger* — theory (3) had the right mechanism and the wrong caller; the fix for the wrong caller was applied and the failure survived it, which is what finally forced the "who else is running?" question. (4) "Passes alone, fails together" needs the qualifier *alone in the process, or alone on the machine?* — list the machine's pytest processes before trusting either result. (5) A detector (`pytest-timeout`, the tripwire) is worth shipping only next to the defusal — but once shipped it is what makes the next occurrence a diagnosis: the tripwire named the black hole on its first firing.

## Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories were wrong, one primitive default was the bug (Package 3b #309, fixed 2026-08-18)

**Symptom.** `check_texture_tileability.py` reported `wood.png x=0.65 y=1.85 SEAM` right after the new numpy torus painter produced it; the planks run vertically, every grain line is a `sin(2πk·y/256)` (periodic by construction), knots are windowed modulo the tile — nothing in the layout should have a y-seam.

**Wrong theories (each plausible, each 10 minutes).** (1) The full-height plank `rect`s were painted with `h = SIZE + 4`, so their bevelled top/bottom edges wrap into a dark horizontal band at y = 0/256 → added an infinite-height mode (`h=None`) → *still 1.88*. (2) The wrap blur → ruled out by reading `wrap_blur` (it is `np.roll`-based).

**Key evidence.** Measured instead of theorised: per-column `|row0 − row255|` on the PNG → the top offenders were columns 16, 48, 80, … 240 (step ≈ 27) — exactly the plank-*joint* columns. Then painted the joint primitive alone on a fresh `Tile((178,138,88))` and printed the canvas at rows 0–2 vs 509–511:

```
row 0    [178. 118.2 110.  118.2 178.]
row 511  [178. 178.  142.4 178.  178.]
```

Coverage of a supposedly constant-width line fell from full (110) at the top to a third (142) at the bottom.

**Root cause.** `Tile.capsule(..., taper: float = 0.0)`: the parameter means "width fraction remaining at the far end", so the default made every capsule a pointed blade. Only `grass_blades` passed `taper` explicitly (0.05, intended); the wood joints, mulch splinters, compost straw, slate cleft streaks and bark cracks were all silently tapered — the wood joint's taper crossed the wrap and became the seam.

**Fix.** Default `taper = 1.0` (constant width); docstring states the semantics. All 24 textures re-rendered; max seam ratio 1.43 (0.95 — pebbles, x — after the senior review's second finding — integer sampling put a half-pixel bias into wrap-centred joints — was fixed by sampling at pixel centres).

**Lesson.** The seam metric already knows *where* the seam is — ask it (per-column diff) before forming a layout theory. Then isolate the suspect primitive on a blank canvas and print numbers at the two rows that must agree; a two-line probe beats two plausible refactors. Recorded as debugging-playbook row 36 and §11.4.

## Case study: the full battery aborts with heap corruption in a plant-SPRITE test — an unparented debounce timer from a plant-SEARCH dialog fired 500 ms after its dialog died (Package 3c #310, fixed 2026-08-18)

**Symptom.** `pytest tests/` (5,400 tests) died at 13 %: `tests/integration/test_plant_sprite_rendering.py ...........Windows fatal exception: code 0xc0000374` — no assertion, no traceback beyond the faulthandler dump. The same battery had passed twice that day on the sibling branch.

**Wrong theory (2 minutes, discarded on evidence).** "My icon changes to `PlantSearchPanel` broke something in the plant search dialog." The panel and the dialog are different classes; the crashing frame was `plant_search_dialog.py:234 _perform_search` — the `QMessageBox.warning(self, …)` in the *except* branch — reached from `pytestqt/plugin.py:220 _process_events` inside `pytest_runtest_setup` of the sprite test.

**Key evidence.** The stack itself: a dialog slot running during the SETUP of an unrelated test means nobody in that test called it — an event did. `grep -n "QTimer()" src/…/plant_search_dialog.py` → `self._search_timer = QTimer()` — no parent. `grep search_input.setText tests/` → six tests type into the box (arming the 500 ms debounce), call `_perform_search()` synchronously themselves and finish in milliseconds. So: dialog closed and deleted by qtbot, Python-owned timer alive, fires 500 ms later into whichever test is then processing events; the real `requests.Session.get` (monkeypatch already undone) raises `PlantAPIError`, and a modal box is opened with a deleted parent → heap corruption. Two new test files (`test_iconography_3c.py`, `test_icon_names_referenced_in_src.py`) had shifted the schedule so the fire landed on a setup `processEvents` instead of a harmless gap.

**Root cause.** A debounce timer left ARMED by every test that typed and then searched synchronously, plus a timer slot that can open a modal `QMessageBox(self)`. Two mechanisms fit the evidence and the crashing run predates the probe, so which one fired is not known: (a) unparented timer outliving a collected dialog (fires into a dead widget), or (b) a still-alive dialog (kept by its own `timeout → bound method` reference cycle) opening a modal mid-`processEvents`, whose nested loop then processes the deferred deletion of that dialog. Latent since the dialog was written; timing-flaky by nature.

**Fix — and the second abort that taught the third leg.** `QTimer(self)` + `done()` stopping it was applied first; the battery aborted again at the same frame. Because pytest capture dies with the process, the next probe logged every `_perform_search` call to a FILE with `PYTEST_CURRENT_TEST`, `sip.isdeleted(self)` and `timer.isActive()`: 17 calls, all synchronous test calls, all leaving the timer ARMED — the dialog's own signal cycle keeps the Python object (and its now-parented timer) alive until a later GC, so parenting alone cannot prevent a late fire. Third leg: `_perform_search()` stops the timer at entry (a search that runs settles the debounce). Regression pins in `tests/unit/test_plant_search_dialog_timer.py` (arm → `done(0)` → `qtbot.wait(700)` → slot not called; arm → direct `_perform_search()` → timer inactive). §11.4 entry; playbook row 37.

**Lesson.** When a battery crash lands in a test that cannot possibly own the crashing code, read the crashing frame, not the test name — the culprit is an earlier test that left a timer/thread alive. Log timing-flaky probes to a file, not stdout. Every `QTimer` created inside a widget takes that widget as parent, a slot that can open a modal is stopped in `done()`, and a debounced action that runs settles its own timer.

## Case study: a real Preferences-to-picker integration test appeared to hang after the first successful workflow (Issue #342, fixed 2026-08-30)

**Symptom.** The new satellite workflow test printed `imported key='preference-key'`, then reported `FAILED` at the second Preferences save and stopped producing pytest output while Qt teardown was pending.

**Wrong theories.** The first suspects were a leaked WebEngine thread, the existing Agent API server, and the known modal-dialog teardown hazard. None explained why the failure occurred exactly after the import path had completed.

**Key evidence.** Flushed milestone prints narrowed the boundary to `[SAT-DBG] clearing Preferences`; a traceback wrapper then showed `AttributeError: '_PasswordLineEdit' object has no attribute 'clear'` at the test's `self._google_maps_key.clear()` call.

**Root cause.** The test treated the application's password-field wrapper as if it were the wrapped `QLineEdit`; the assertion failure happened before the test could print its post-save state, making the surrounding Qt teardown look like the cause.

**Fix.** Replace the wrapper call with its supported `setText("")` API, remove all temporary instrumentation, and keep the real Preferences dialog in the integration path while stubbing only the network-bound picker boundary.

**Lesson.** In a Qt integration test, print flushed milestones around each boundary before theorising about teardown; when a custom widget wrapper is involved, inspect its public API instead of assuming it forwards the underlying control's methods. A test that reaches the real UI save path is only useful if its own harness failure is distinguishable from application lifecycle noise.

## Case study: the corrected satellite import integration test passed but never completed teardown (Issue #342, fixed 2026-08-30)

**Symptom.** After the wrapper API failure was fixed, the test printed `PASSED` but pytest produced no summary and remained alive until interrupted.

**Wrong theories.** A leaking WebEngine object, an unjoined map worker, and the Agent API timer were all plausible because the test exercised the real main window.

**Key evidence.** The import handler at `GardenPlannerApp._on_load_satellite_background()` marks the project dirty; `GardenPlannerApp.closeEvent()` then calls `_confirm_discard_changes()`, whose modal save prompt cannot be answered in the offscreen pytest-qt teardown.

**Root cause.** The test intentionally exercised a mutating import workflow but left the window dirty, so the normal close path opened a headless modal dialog after the test body had already passed.

**Fix.** Call `win._project_manager.mark_clean()` immediately after asserting the import path has completed, before pytest-qt closes the window; this preserves the production workflow while making teardown deterministic.

**Lesson.** For headless Qt integration tests that mutate a document, inspect the production close path and neutralize its expected user prompt in test cleanup. A passing test body is not a passing test process when teardown can enter a modal loop.

## Case study: retrying a failed satellite fetch could call a deleted QThread wrapper (Issue #342, fixed 2026-08-30)

**Symptom.** After a satellite fetch failed or was cancelled, a later Cancel click could raise `RuntimeError: wrapped C/C++ object of type _FetchWorker has been deleted`.

**Wrong theories.** The HTTP worker was suspected of still running, and the dialog's `closeEvent()` detachment looked like the likely source of the stale reference.

**Key evidence.** `_on_accept()` connected `finished → worker.deleteLater()` but never cleared `self._worker`; `_on_cancel()` then called `self._worker.isRunning()` after Qt had destroyed the C++ object.

**Root cause.** Python retained a wrapper whose underlying QThread had already been deleted, so the next lifecycle action dereferenced invalid Qt state.

**Fix.** Connect each worker's terminal signal to an identity-checked cleanup slot that clears `_worker`, guard stale wrappers in Cancel/close, and add a real-thread regression test that waits for failure before issuing a second Cancel.

**Lesson.** In Qt worker code, `deleteLater()` is not reference cleanup. Track terminal ownership explicitly, test the action that follows completion, and use the worker identity so a late signal from an older request cannot clear a replacement.
