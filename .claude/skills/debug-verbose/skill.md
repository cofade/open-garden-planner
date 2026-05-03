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
