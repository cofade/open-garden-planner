---
name: debug-verbose
description: Evidence-based debugging via targeted verbose instrumentation. Apply at the first sign of any non-obvious bug — before theorising. Grows with each bug fixed in this project.
user_invocable: true
argument: "Optional: short description of the bug or area to instrument"
---

# Verbose Debug Instrumentation

## Case study: compiled catalogs passed while current UI keys were missing (#496)

**Symptom.** A newly registered Russian locale passed existing tests while current UI
labels remained English. The contributor guide incorrectly said all locales were checked.

**Wrong theories.** A successful compile and the absence of unfinished German entries
were not evidence of source coverage. No alternative runtime theory was adopted before
the extraction/compilation probes.

**Evidence.** Fresh standard extraction found 36 keys absent from German; tagged
`[496-INVENTORY] 2631` output included audited helper/table and bundled species sources.
Six regressions failed first: blank/whitespace targets, nonempty unfinished targets,
missing placeholders, vanished output and the third-language German reason fallback.

**Root cause.** Required keys came from stale catalogs rather than independent source.
The compiler synthesized source fallbacks and did not enforce translation state. The
companion service used a binary English/else-German language choice.

**Fix.** Derive source keys, bind finite dynamic sources to their production tables,
validate every registered locale and compiled lookup, and reject unresolved sources.
Compile only completed active records. Select German reasons only for de. Temporary
tagged probes were kept outside production; no debug prints remain in committed code.

**Lesson.** Test both additions to the source axis and additions to the locale axis.
An equal count or a fixture generated from an incomplete catalog cannot prove coverage.
Pinned by the translation gate unit/integration tests and the required Test check.

## Case study: QThread destroyed while still running on window close (issues #480, #483, 2026-10-15)

**Symptom.** Closing the application window while a network worker (such as the update checker or weather forecast worker) is in-flight crashes or aborts with code `0xC0000409` and Qt fatal error `QThread: Destroyed while thread is still running`.

**Wrong theories.** Blaming Python garbage collection order or relying solely on daemon threads. Python daemon threads do not prevent Qt's C++ object tree destructor `~QThread()` from terminating the process when a parent `QObject` is deleted while its child `QThread` is active.

**Evidence.** Triggering an update check or weather fetch and immediately closing the main window resulted in an abnormal exit (`0xC0000409`). Inspecting `GardenPlannerApp.closeEvent` showed `UpdateChecker(self)` had the application window as parent and lacked a cancellation/shutdown handshake.

**Root cause.** When `GardenPlannerApp` closes and is destroyed, its C++ child `QObject`s (including `UpdateChecker` and weather fetch workers) are destroyed. Because network operations block synchronously in `run()`, the thread was still running when Qt's C++ `~QThread()` ran, triggering `qFatal`. Furthermore, signals emitted by in-flight threads could invoke slots on destroyed receivers. If unparented, Python GC could delete the wrapper object while running, triggering the same C++ destructor abort.

**Fix.** Provide an explicit `cancel()` flag and `shutdown()` handshake on background workers (`UpdateChecker`, `_WeatherFetchWorker`). In `shutdown()`, mark cancelled, suppress disconnect errors to detach all signal listeners, clear the QObject parent via `setParent(None)` so window destruction does not destroy the active thread, issue a short `wait()`, and retain in `core.worker_lifecycle._RETIRING_WORKERS` until the `finished` signal fires. Call `shutdown()` in `closeEvent` for update check and weather services alongside the sun heatmap worker. Pin with lifecycle integration and cancellation unit tests. Remove temporary prints before committing.

**Lesson.** Every background `QThread` attached to a parent `QObject` must have a deterministic cancellation and shutdown protocol before parent destruction. Never let `~QThread()` run while `isRunning()` is true.


## Case study: a fast worker fails a GUI heartbeat count (PR #490, 2026-10-14)

**Symptom.** One CI Test job failed `test_explicit_worker_keeps_gui_responsive`
with two timer ticks instead of three. The same head passed the other full Test
job, both Coverage jobs and the Windows full suite.

**Wrong theories.** No product-threading theory was adopted before tracing. A
fixed tick count over an uncontrolled computation duration was not a responsiveness
contract, and ticks delivered after completion could inflate the count.

**Evidence.** Tagged worker/timer instrumentation recorded `[490-RESP] worker-start`
on thread 12492 at 0.003 s, worker-end at 0.057 s, and GUI ticks on thread 5184
continuing from 0.119 s through 0.181 s. The failed CI assertion recorded `[1, 1]`.

**Root cause.** The test counted timer ticks during however long a small real
computation and its queued result delivery happened to take. Faster completion
could legitimately produce fewer ticks; later ticks did not prove an in-flight worker.

**Fix.** Hold the real computation at a thread Event, require three GUI heartbeat
ticks while the worker is still running/pending, assert a different thread identity,
release it and verify the real result. Always release on failure. Preserve the
existing timer interval and result timeout. All 18 sun-mismatch workflows pass;
a synchronous-worker negative control fails the thread-identity assertion.
Remove all temporary probe prints before committing.

**Lesson.** Control the in-flight interval when proving responsiveness. Do not
infer it from the incidental duration of a small fixture or loosen the tick count.

## Case study: frozen code absent from a passing SBOM (#454, 2026-10-14)

**Symptom.** The inventory check passed for 47 components, but an independent review
of the newly built executable found frozen setuptools/packaging, development dependencies
and setuptools-vendored copies absent from both the SBOM and notices.

**Wrong theories.** No alternate runtime theory was adopted. The earlier special case
for vendored importlib-metadata described one observed hook; it was not an inventory.

**Evidence.** Reading the actual executable PYZ and physical collected source paths gave
`[490-OWNERS] packaging 26.3; setuptools._vendor.packaging 26.0; zipp 3.23.0`.
The independent artifact regression failed with `frozen setuptools has no inventory component`.

**Root cause.** The metadata collector and synthetic tests both used the same declared
Requires-Dist closure. PyInstaller's actual code collection independently included hook
and vendored files, so a check of the declared set could not detect those omissions.

**Fix.** Attribute actual Analysis pure/binary/data/runtime-script paths through wheel
RECORD ownership, with nested vendored precedence. Bundle those owners' exact metadata
and declared license texts. Record module/file ownership and verify the manifest against
the actual executable PYZ; tie vendored versions to their locked containing wheel rather
than a name-based exemption. Preserve distinct installed/vendored versions. Temporary
probe output stays out of committed code.

**Lesson.** A fixture generated from the expected inventory cannot prove actual shipped
composition. Inspect the executable and physical source ownership independently.


## Case study: the same metadata query returned 5 distributions under pytest and 48 in the shell (#454, 2026-10-13)

**Symptom.** The runtime-closure resolver behind the release's third-party notices and SBOM
returned five names (the project, `Pillow`, and the three `PyQt6*` wheels) when a unit test
called it, but 48 names when the identical module was executed directly with the same
interpreter. No product code ran at all.

**Wrong theories.** First theory: `importlib.metadata` caching inside pytest. It has no such
cache. Second: the frozen bundle's `.dist-info` set differing from the environment's. The
bundle was not involved in the failing call. Third: a marker evaluation difference between
`evaluate()` calls. The same wrong answer repeated verbatim, which is the tell for "a
different object, not a different judgement".

**Evidence.** The decisive line was printing the resolved distribution's own location:

```python
print(metadata.distribution("open-garden-planner")._path)
# C:\...\open-garden-planner\src\open_garden_planner.egg-info
```

and then listing every distribution whose name contains "garden":

```python
[x._path for x in metadata.distributions() if "garden" in x.metadata["Name"].lower()]
# [ ...\src\open_garden_planner.egg-info,
#   ...\venv\Lib\site-packages\open_garden_planner-1.30.2.dist-info,
#   ...\src\open_garden_planner.egg-info ]
```

Two records for one name; the stale one (version `0.1.0`, two dependencies, written years
earlier by a legacy editable install) won under pytest because the editable install's `.pth`
puts `src/` on `sys.path` ahead of site-packages.

**Root cause.** `importlib.metadata.distribution(name)` returns the **first** matching
distribution on `sys.path`, not the newest — and `sys.path` order differs between a plain
`python -c` run and pytest (which inserts test paths). The resolver trusted "the project's own
installed metadata" while an unowned artefact of the project's history shadowed it.

**Fix.** The resolver now anchors on `pyproject.toml`'s `[project].dependencies` and walks
only *third parties* through installed metadata (`installer/runtime_closure.py`); the stale
`*.egg-info` was removed from the dev checkout as well, and a test pins the manifest anchor
with an injected manifest. Same build task, second discovery: PyInstaller's
`hook-importlib_metadata` bundles setuptools' **vendored** `importlib_metadata` (Apache-2.0)
although nothing declares it, so the initial fix added an explicit hook exception. PR #490 superseded that exception
with physical RECORD attribution of actual collected owners (see the preceding case study).

**Lesson.** When a metadata lookup disagrees with a file a human can read, print the
distribution's `_path` before theorising — the answer is usually "you resolved a different
distribution than you meant". And an input that must describe what ships has no business
depending on the environment's copy of yourself: read the manifest.

## Case study: sun-cache test fails only late at night (#457 gate run, 2026-10-13)

**Symptom.** Full validation and an isolated sun-mismatch workflow failed with
exposure_reason `absent` instead of `ready` after adding one hour.
**Wrong theories.** No localization or timing theory was adopted before tracing.
**Evidence.** `[A5-SUN-CLOCK] before= 2026-06-21 23:49:00 after=
2026-06-22 00:49:00 reason= ready`; caller stack identified the test's datetime write.
**Root cause.** The fixture set only the date, retaining the host time. After 23:00,
its alleged within-day edit changed the plan date and correctly invalidated the
heatmap (ADR-053). The test's expectation, not the cache, was wrong.
**Fix.** Set the fixture's time of day explicitly to noon. Retain real worker,
geometry, cache and invalidation assertions and all timeouts. Remove diagnostics.
**Lesson.** A test claiming a within-day edit must fix both date and time; a
set_date call does not fix the wall clock's hour.


## Case study: English unnamed objects in German constraint rows (#457, 2026-10-13)

**Symptom.** Owner screenshot showed `Polygon – Rectangle Deckungsgleich`, while
Properties correctly showed `Rechteck`. Other unnamed types shared the path.
**Wrong theory.** A missing Rectangle translation was ruled out by the compiled
translator. No theory was adopted before tracing the label builder.
**Evidence.** `[A5-LABEL] GENERIC_RECTANGLE row= Rectangle canonical= Rechteck`;
`traceback.format_stack()` traced command-history refresh into `_build_item_labels`.
An exhaustive catalog test additionally found missing Hedge/Roof Ridge entries.
**Root cause.** Enum title-casing bypassed the canonical translated object names.
Direct descriptor tests supplied `A`/`B`, so they never exercised this boundary.
**Fix.** Reuse `get_translated_display_name` for unnamed constraint endpoints and
compare-overlay plants; register Hecke/Dachfirst. Preserve explicit names and data.
Four failing-first regressions cover all 52 object types, duplicate numbering,
explicit names, real German row/tooltip wiring and all three overlay plant types.
Remove temporary prints before commit.
**Lesson.** Verify translated templates with real upstream object labels, and
check catalog coverage against the full enum rather than only registered messages.


## Case study: metre formatting changes after descriptor extraction (#457, 2026-10-13)

**Symptom.** Review found 17.5 cm displaying 0.18 m after extraction, previously
0.17 m. Six formatting-boundary regressions failed before correction.
**Wrong theory.** Algebraically equivalent multiply/divide operations need not
produce identical binary floats. Translation and numeric precision were unchanged.
**Evidence.** `[A5-ROUND] 17.5 division 0.17 multiplication 0.18`;
`[A5-ROUND] 20.5 division 0.20 multiplication 0.21`.
**Root cause.** Target multiplication by 0.01 replaced the existing division by
100.0, changing the last binary bit at display rounding ties.
**Fix.** The descriptor stores a divisor (100.0 for metres, 1.0 for degrees) and
preserves division. Pinned by `test_constraint_descriptors.py` distance/edge/tangent
boundary tests; all temporary diagnostics removed.
**Lesson.** Presentation equivalence includes the arithmetic operation at rounding
boundaries, not only the number of formatted decimal places.

## Case study: all-pinned constraints reported solved (#457, 2026-10-13)

**Symptom.** Two pinned anchors 100 cm apart with a 200 cm target returned
converged=True and max_error=0.0. Direct Newton and graph regressions failed first.
**Wrong theories.** No theory adopted before tracing; pin mutation was ruled out
by unchanged positions/deltas. The historical mutation score did not prove this bug.
**Evidence.** `[A5-NEWTON] no free slots ... positions ...[0,0]...[100,0]...
constraints [('DISTANCE', 200)]`; `traceback.format_stack()` showed the call from
ConstraintGraph.solve_anchored into Newton's no-variable early return.
**Root cause.** Newton returned success before evaluating residuals. The graph
replaced its real warm-start error with the minimum of that error and zero.
**Fix.** Evaluate residuals before the no-variable return. Preserve pinned geometry
and report actual feasibility/error. No damping, tolerance or iteration changes.
Pinned by `tests/unit/test_constraint_solver_invariants.py` and
`tests/integration/test_constraint_presentation_workflow.py`. Remove trace prints.
**Lesson.** An empty set of movable variables establishes immobility, not feasibility;
assert independently measured residuals and pinned state, not just convergence flags.

## Case study: a rectangle edge-length graph row without a resize (#406, 2026-10-12)

**Symptom.** A real single-click Edge Length gesture on a 200 cm rectangle accepted 250 cm and added an undoable graph row, while the edge remained 200 cm.
**Wrong theories.** No runtime theory adopted before tracing. An earlier rotation-fixture failure was separate: Qt setRotation alone does not populate the item's rotation_angle; fixtures must use the product's _apply_rotation path.
**Evidence.** `[406-EDGE] nonvertex fallback RectangleItem target 250.0 ... rect ...200.0...`; `[406-EDGE] computed moves ([], [])`. The printed caller stack traced EdgeLengthConstraintTool.mouse_press -> CanvasView._execute_constraint_with_solve -> _compute_edge_length_constraint_moves. The real gesture/geometry assertion failed before the fix.
**Root cause.** The tool offers rectangle edges, but direct endpoint movement only handles polygon/polyline vertices. Its fallback translation solve treats rectangles as rigid, and both anchors name the same pinned item.
**Fix.** Reuse the existing rectangle size applier from EQUAL, which delegates to canonical geometry_apply, and bundle it on AddConstraintCommand. No second geometry closure or second undo step. Tests cover all four rectangle edges at 0, 45 and 215 degrees, center/origin, graph identity and exact undo/redo. Independent review exposed two mixed-graph gaps: `[406-MIXED] before ... types [HORIZONTAL]` was refused before probing the resize; `[406-MIXED] after ... (475,500) fixed [(500,500)]` violated a pin. Probe canonical proposed geometry before feasibility; restore its exact snapshot on refusal/error, and refuse a resize that moves FIXED item.pos. Compatible center alignment, incompatible edge lengths, fixed pins and probe-error restoration are pinned at all three rotations. Further review reproduced `[406-PROPOSAL] QRectF(...250...,160...) QPointF(475,500) [EQUAL,EQUAL]` with caller stacks: the solver skips EQUAL, a nested refusal modal let a timer serialize proposed geometry, and Override removed old rows outside undo. Fifteen rotated regressions failed before correction. Keep the proposal synchronous, restore before every modal, refuse changed EQUAL dimensions and probe conflicts without Override; carry successful size changes through the existing command/solve path. Equal chains, unrelated equal-height preservation, timer-driven ProjectManager serialization, and conflicting replacement history are pinned. Remove probe prints.
**Lesson.** Constraint type/IDs and an undoable row are insufficient evidence. Assert the resulting scene geometry satisfies the requested relation, as well as restoring the pre-gesture state.

## Case study: guild names and gallery-click layer assignment (PR #433, 2026-10-11)

**Symptom.** A German guild picker showed Apple Tree/Runner Bean/Borage/Strawberry. With auto-assignment enabled, a gallery-selected blueberry drawn on the canvas still used the active layer.
**Wrong theories.** No theory adopted before tracing; a failed checkbox or missing shrub trait was ruled out by the runtime values.
**Evidence.** `[F1] auto=True species=shrub chosen=<active-id> active=<active-id>`; `traceback.format_stack()` identified `CircleTool._finalize_circle -> CanvasView.add_item -> CreateItemCommand.execute`. `[F2] centre=Apple Tree members=['Runner Bean', 'Borage', 'Strawberry']` reproduced the German widget contents.
**Root cause.** The existing drop test bypassed gallery-click circle creation, which constructed its own plant with the active layer. Guild controls directly displayed catalog common_name values without translation.
**Fix.** Reuse `build_plant` for circle-based plant placement; translate guild catalog labels at display time in the existing GalleryData context and register all missing bundled common names. Preserve explicit user names and canonical saved species identity. Remove all probe prints before committing.
**Lesson.** Test each actual creation surface, and assert displayed translated data as well as static labels. A green drop workflow and a complete translation table cannot establish click-placement or data-label behavior.

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

## Case study: same-scene reload duplicates and false-success deletes (fixed 2026-09-24)

**Symptom**: after a project was loaded into the same `CanvasScene`, `list_layers.object_count` exceeded the top-level `list_objects` roster; a call to `delete_object` could report success while a same-ID callout remained visible.

**Theories entertained (wrong)**:
- Concurrent MCP requests were bypassing the Qt main-thread queue and needed a second global lock.
- `CommandManager.execute()` could acknowledge a command before `DeleteItemsCommand` removed the item.
- The layer-count mapper was deliberately counting child/overlay items.

**What instrumentation and probes revealed**: `MainThreadBridge` already serialized the provider bodies on the main thread. The decisive probe was a same-scene save/load followed by a type/UUID census: old `CalloutItem`, `ArcItem`, and `BezierItem` instances remained because `_deserialize_to_scene()` removed only an older explicit class tuple. `find_item_by_id()` then returned the first duplicate, so deleting it left the other alive.

**Root cause**: the load cleanup roster had drifted from the serializer's actual document-item roster.

**Fix**: centralize a serialized-document-item predicate in `ProjectManager`, preserve compare/dimension overlay owners, refuse duplicate live UUIDs before agent deletion, and verify all requested targets are detached before returning success. The real-MCP integration test now exercises the round trip and concurrent delete contract.

**Lesson**: UUID identity is a scene invariant, not merely a lookup hint; a successful command receipt is not proof that the addressed object is gone.

---

## Case study: non-finite MCP numbers become valid callout defaults (fixed 2026-09-24)

**Symptom**: `1e308` callout offsets were rejected, but `Infinity`/`NaN` sent through the real MCP client unexpectedly created ordinary callouts instead of failing.

**Theories entertained (wrong)**:
- `require_finite()` was not being called for callout offsets.
- Qt accepted the values and the problem was only a rendering issue.
- The client would preserve non-finite JSON values all the way to the Python provider.

**What instrumentation revealed**: the hostile-call test showed the first two calls failed in `require_bounded_signed_offset`, while the Infinity/NaN calls returned ordinary create results. The transport had normalized those JSON values to `null`; `float | None = None` made the provider interpret them as omitted and apply default offsets.

**Root cause**: validation happened after the transport had erased the distinction between an omitted optional argument and a hostile null/non-finite value.

**Fix**: validate signed, canvas-relative offsets before the loader, use an omission sentinel in the MCP handler, and reject explicit null before dispatch. Refusals now occur before `_deserialize_item_core` and `CreateItemCommand`.

**Lesson**: adversarial-input coverage must cross the real transport; a direct pure-function test cannot see JSON/Pydantic normalization.

---

## Case study: one noisy CI benchmark hides the real distribution (fixed 2026-09-24)

**Symptom**: one Python 3.11/Linux run measured 284.1 ms for the 1000-item spatial-index rebuild against a 250 ms limit, while a parallel run and the full local suite passed; the implementation was unchanged by the branch.

**Theories entertained (wrong)**:
- The quadtree had a deterministic performance regression.
- Raising the hard ceiling again would be a sufficient fix.
- The fast local run represented the runner distribution.

**What instrumentation revealed**: repeated local samples were tightly clustered around 15 ms, while the historical CI value was an isolated scheduler outlier. A single wall-clock sample had no way to express that distinction.

**Root cause**: the gate encoded a noisy point measurement as a universal contract.

**Fix**: warm the path, collect five rebuild and five query samples, report the samples on failure, and gate medians at 200 ms / 1 ms. This preserves a sustained-regression failure while tolerating one shared-runner spike.

**Lesson**: performance gates should protect a distribution, not assume a noisy runner is quiet; record the platform and evidence alongside the threshold.

---


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

**Root cause**: `models/plant_data.py:210` `to_dict` and `models/plant_data.py:275` `from_dict` — neither was updated when `n_demand`/`p_demand`/`k_demand` were added to the dataclass.

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

**Root cause**: Qt's `QGraphicsPolygonItem.shape()` (bypassed at `ui/canvas/items/garden_item.py:1155` `drawPolygon`) does **not** return the polygon's outline. It returns the *stroke envelope* — a closed band path that's the polygon outline expanded by the pen width, intended for hit-testing (so clicking near the edge counts as a hit). Stroking that band's outline produces the observed double-line effect, with the addPolygon-induced open seam reduced to a thin closing line.

**Fix**: When the item has a `polygon()` method (i.e. it *is* a `QGraphicsPolygonItem`), bypass `shape()` entirely and use `painter.drawPolygon(self.polygon())`. That uses the raw vertex list and produces a uniform stroke on every edge with proper miter joins. Rect / circle / ellipse keep the `drawPath(self.shape())` fallback because their `shape()` *does* return a closed outline.

**Lesson**: `QGraphicsItem.shape()` is hit-testing geometry, not drawing geometry. When you need to outline an item, use the item's *primitive* (polygon, rect, ellipse) not its shape. Reach for `painter.drawPolygon`/`drawRect`/`drawEllipse` over `drawPath(self.shape())` whenever you can.

---

## Case study: early `return` inside a paint() branch silently bypasses later draws (US-12.10/F2.6b, fixed 2026-05-03)

**Symptom**: GARDEN_BED rectangles correctly showed soil-mismatch borders. RAISED_BED rectangles never did. Both pass `is_bed_type()`, both have a `_soil_mismatch_level`, both call the same paint hook.

**Wrong theories**:
- `is_bed_type(RAISED_BED)` returning False (verified true).
- Pixmap rendering covering the border (no — pen has alpha 220).
- Selection-handle code stealing focus (irrelevant to paint).

**Key signal**: instrumenting paint() showed the `ui/canvas/items/rectangle_item.py:349` `_draw_soil_mismatch_border` call *never ran* for raised beds. That code is unconditional within `is_bed_type` — so something earlier was returning.

**Root cause**: an early `return` at the end of the RAISED_BED furniture-pixmap block bypassed it — RAISED_BED is rendered as a *furniture pixmap* (the wooden-frame look), and that branch returned before reaching the border. Every line below that — grid overlay, rotation indicator, *and the soil mismatch border* — was bypassed for raised beds. The original code reviewer of US-12.10d wired the border thinking it was reachable for all bed types.

**Fix**: Add a second `_draw_soil_mismatch_border` call *inside* the early-return branch, just before the `return` — now `ui/canvas/items/rectangle_item.py:320` `_draw_soil_mismatch_border`. Both the pixmap path and the standard path now paint the border.

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

**Root cause**: `ui/canvas/canvas_scene.py:355` `_refresh_layer_z` set every item's z to `layer.z_order * 100` (since revised by #338/ADR-043 into a per-item ranked z within that band — §8.25). Items in the same layer get *the same z*. Qt's `QGraphicsScene` then tie-breaks by item insertion order. The live session inserts bed first, then plant — plant on top. The post-load reconstruction inserts items in scene-traversal order from the saved JSON, which is reversed by serialization, putting the plant first and the bed on top.

**Fix**: Add a third pass in `_update_items_z_order` (mirroring the existing ROOF_RIDGE special case, now `ui/canvas/canvas_scene.py:925` `ROOF_RIDGE` inside `_stack_entries` since #338/ADR-043's rewrite — §8.25) that walks every item with `_parent_bed_id` set and bumps its z to `parent.zValue() + 1`. Now plants always have a strictly higher z than their bed, regardless of insertion order.

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

**Root cause**: `models/soil_test.py:116` `latest` — `SoilTestHistory.latest` was implemented as `max(self.records, key=lambda r: r.date)`. Python's `max()` returns the **first** maximal element when keys tie ("If multiple items are maximal, the function returns the first one encountered"). The Kit record was appended first, so it won every same-day tie. Compounded by `_format_history_row` showing only categorical fields — the user couldn't tell two records existed for that date.

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

**Root cause**: `ui/canvas/canvas_view.py:901` `_on_scene_changed_for_soil` — the debounce that drives soil-mismatch refresh is wired exclusively to `scene.changed`. After a drag, `_update_plant_bed_relationships` calls `SetParentBedCommand` which mutates `parent_bed_id` and `_child_item_ids` — plain attribute writes that emit no Qt signal and trigger no scene-rect invalidation. The 500 ms timer never restarts for the parent-link change. The next genuine scene change (e.g. the user editing pH) is what finally refreshes — explaining why steps 4 and 6 of the repro work and steps 3 and 5 don't.

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

**Wrong theory (2 minutes, discarded on evidence).** "My icon changes to `PlantSearchPanel` broke something in the plant search dialog." The panel and the dialog are different classes; the crashing frame was inside `plant_search_dialog.py` (historical line 246) `QMessageBox.warning(self, …)` — the *except* branch of `_perform_search` — reached from `pytestqt/plugin.py:220` `_process_events` inside `pytest_runtest_setup` of the sprite test.

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

## Case study: closing the satellite picker froze the GUI (Issue #342 / PR #344, fixed 2026-08-31)

**Symptom**: Closing the satellite picker during a slow Static Maps request could freeze the whole application until the HTTP timeout elapsed.

**Theories entertained (wrong)**:
- The worker's interruption request would make the network call stop immediately.
- A finite HTTP timeout made a synchronous join safe enough for dialog teardown.

**What targeted lifecycle review revealed** (the regression test holds the worker inside a simulated in-flight request): `MapPickerDialog.closeEvent()` called `requestInterruption()` and then `worker.wait()` on the GUI thread, but `google_maps_service._fetch_tile()` cannot observe cancellation while `requests.get(timeout=10)` is active.

**Root cause**: cooperative cancellation was paired with a blocking GUI-thread join, so the dialog's close path inherited the network timeout.

**Fix** (the dialog lifecycle): `closeEvent()` now ignores the close request, asks the worker to stop, and rejects asynchronously after the worker's terminal signals clear ownership and in-flight state. Unexpected failures log a traceback only after `_scrub_key()` redaction.

**Lesson**: a cancellation request is not a completion guarantee; Qt dialogs must own network workers asynchronously and must never wait on them from the GUI thread.

## Case study: zero-delay deferred-close polling busy-spun the GUI (Issue #342 / PR #344, fixed 2026-08-31)

**Symptom**: After the GUI close request returned, a blocked satellite request kept the event loop busy while the deferred-close timer repeatedly re-fired.

**Wrong theories**: A zero-delay timer was treated as harmless because each callback was short, and worker interruption was assumed to complete before the next callback.

**Key evidence**: Review of the lifecycle state showed `_complete_deferred_close()` scheduling another zero-delay callback while `_fetch_in_progress` remained true. The request could remain blocked until its network timeout, so the GUI loop had no quiet interval.

**Root cause**: Deferred polling on the GUI thread was being used to wait for a worker whose cancellation was cooperative and asynchronous.

**Fix**: Close only from the identity-checked `QThread.finished` path; route `reject()` and `closeEvent()` through the same cancellation state machine, and have the application track an active modal picker during application shutdown. Escape and parent-window close now have regression coverage.

**Lesson**: A zero-delay retry loop is still a busy loop when the condition depends on I/O. Use the worker's terminal signal as the completion event, and guard every dialog rejection path—not just the window-manager close event.

## Case study: retrying a failed satellite fetch could call a deleted QThread wrapper (Issue #342, fixed 2026-08-30)

**Symptom.** After a satellite fetch failed or was cancelled, a later Cancel click could raise `RuntimeError: wrapped C/C++ object of type _FetchWorker has been deleted`.

**Wrong theories.** The HTTP worker was suspected of still running, and the dialog's `closeEvent()` detachment looked like the likely source of the stale reference.

**Key evidence.** `_on_accept()` connected `finished → worker.deleteLater()` but never cleared `self._worker`; `_on_cancel()` then called `self._worker.isRunning()` after Qt had destroyed the C++ object.

**Root cause.** Python retained a wrapper whose underlying QThread had already been deleted, so the next lifecycle action dereferenced invalid Qt state.

**Fix.** Connect each worker's terminal signal to an identity-checked cleanup slot that clears `_worker`, guard stale wrappers in Cancel/close, and add a real-thread regression test that waits for failure before issuing a second Cancel.

**Lesson.** In Qt worker code, `deleteLater()` is not reference cleanup. Track terminal ownership explicitly, test the action that follows completion, and use the worker identity so a late signal from an older request cannot clear a replacement.

## Case study: live capture harness saw "capture did not complete" while the feature worked (Issue #346, fixed 2026-09-01)

**Symptom.** The end-to-end live verification of the JS view capture printed nothing after "starting capture" and the process exited with code 0 — the harness reported the dialog had not accepted.

**Wrong theories.** The capture pipeline was suspected: JS `beginCapture` failing silently, the `tilesloaded`+`idle` readiness gate never firing, the widget grab returning a blank.

**Key evidence.** Wrapping the dialog's methods with print traces showed the full chain working — `beginCapture → 'ok'`, `captureReady`, grab → crop → `accept()` — followed instantly by process exit.

**Root cause.** Two stacked harness/pitfall findings: (1) `QDialog.accept()` hides the window, so with `quitOnLastWindowClosed` the event loop ended before the harness's 500 ms poll could read `fetch_result`; (2) the earlier "map never ready" polls were blind — the page declares `let map` / `let bridge` (top-level `let` never attaches to `window`), so `runJavaScript("window.map")` returns undefined while the real map sits healthy on screen.

**Fix.** Poll page-scope expressions (`typeof map !== 'undefined' && map && map.getZoom`) and hook the accept itself instead of racing a timer against window-closed quiescence.

**Lesson.** A verification harness that polls an event-driven Qt flow needs to instrument the *end state transition* (the accept), not poll the result — and any JS probe of a page written with `let` must scope to the page, not `window`. Both red herrings wasted a debugging round on a pipeline that had already succeeded; the process had exited because success itself hides the dialog.

## Case study: spike page rendered beige with `tilesloaded=true` and no tiles (Issue #346, fixed 2026-09-01)

**Symptom.** The first map spike inside QtWebEngine painted the Google beige background (`#e8eaed`) everywhere, `tilesloaded` fired, yet the DOM held one `<img>` and `map.getCenter()` returned undefined.

**Wrong theories.** WebGL context failure (proved alive), CSP blocking the tile domain, missing `LocalContentCanAccessRemoteUrls`, an EEA-side tile ban on this project, and a QtWebEngine 6.10.2 rendering bug were each plausible — the last two would have killed the whole feature design.

**Key evidence.** After fixing a self-inflicted nested-`<script>` splice (the first "fix" broke the page worse), the map rendered normally: 58 `<img>`s, 20 tile images, `fetchStatus 200`, WebGL fine, maps `3.65.12f`. The beige run had been a genuinely broken page state, not an engine restriction.

**Root cause.** Harness page bugs (broken script structure) — compounded by an earlier probe that printed tile URLs with the API key embedded (the key lives in every `/maps/vt` URL's query string), which then demanded sanitization discipline across the spike.

**Lesson.** When a WebEngine map shows Google's beige with `tilesloaded`, suspect the page's own script/CSP state before suspecting the engine — and never print or log DOM-derived URLs from a Google page: they carry the credential. The clean probe also became the §11.4 rule: pixels leave the map only via the widget grab; metadata only via the bridge.

## Case study: linux-offscreen suite segfaults in an unrelated minimap test — CI-bisect pinned a 10 ms watchdog timer racing pytest-qt's wait loop (Issue #346 finalization, fixed 2026-09-01)

**Symptom.** CI (`Test` job, linux offscreen) aborted with `Fatal Python error: Segmentation fault` — always in `test_minimap_widget.py::TestMinimapIdleQuiescence`, a different member test each run, always at ~66% of the suite. Local Windows green, every time.

**Wrong theories.** (1) A runner flake / pre-existing master instability. (2) Collection-time import of `map_picker_dialog` (QtWebEngine) from the new test module shifting the corruption schedule. (3) The QPixmap/QPainter grab stand-in churning offscreen memory.

**Key evidence.** CI-bisect as the instrument, seven pushes: a throwaway probe branch at `origin/master` HEAD ran green → the branch introduces it; disabling both new test files → green; unit file only → green; `pytestmark = skip` (collect everything, run nothing) → green (collection imports innocent); skipping the second half of classes → red; only the lifecycle class → green; only the success class → green; the cancel class without its three watchdog tests → green. The three watchdog tests — each of which did `_capture_watchdog.setInterval(10); _capture_watchdog.start(10)` inside a `qtbot.waitUntil(lambda: dialog._capture_in_progress is False)` — were the only red constellation.

**Root cause.** A real 10 ms single-shot QTimer racing pytest-qt's process-events wait loop in the offscreen platform destabilised Qt's native timer/event machinery; the corruption surfaced later, in the quiescence-counting minimap tests (exactly row 37's "the test *after* the guilty one errors" shape, but a segfault instead of an abort).

**Fix.** The tests now drive the handler deterministically by emitting the signal (`dialog._capture_watchdog.timeout.emit()` — same slot, synchronously, no real timer); the real 20 s watchdog timing remains covered by the live E2E harness. Pinned §11.4 ("short-interval QTimer racing pytest-qt's waitUntil").

**Lesson.** When CI is red on linux offscreen and green locally, treat CI itself as the instrument: master-probe first (one push), then bisect by *skipping*, not by editing logic. And never race a widget timer against `waitUntil` in a Qt test — emit the signal if the goal is handler coverage.

## Case study: JS-side number-vs-string token guard silently ate every capture report — "capture times out" with all tests green (Issue #347, fixed 2026-09-02)

**Symptom**: First manual test of the shipped pan-grid view capture: Capture view → after ~20 s a box appeared: "The capture timed out. Check your network or the API key, then try again." — while the map was plainly healthy. All 109 automated tests were green, including the bridge-contract drift guard.

**Wrong theories**:
- Stale QtWebEngine cache serving the old single-frame HTML (new page functions `beginCaptureChrome` etc. undefined → silent `runJavaScript` → watchdog). Disproved: a live API probe printed `{"chrome":"function","frames":"function","map":"object","zoom":18}` — the new page was live.
- Tiles never finishing / `tilesloaded` never firing (the settle would then force-report via its grace timer — and no report arrived at all).
- A JS runtime error in the report path (would have returned `'error: …'` through the `runJavaScript` callback — Python logged `result='ok'`).

**Key log lines** (live harness driving the real dialog + real key + real page, timestamps elided):
```
[CAPTURE] js_result result='ok' gen=1        <- beginCaptureChrome RAN and returned ok
[CAPTURE] failure msg='The capture timed out...'   <- 20 s later, watchdog; NO 'ready' ever arrived
```
So the page accepted the call but its readiness report never crossed the bridge — a guard between the two ate it.

**Root cause**: `map_picker.html` stored the capture generation token as received and later compared it with a stringified echo: `captureState = { token: token, ... }` then `if (!captureState || captureState.token !== String(token)) return;`. Python drives the page with hand-built JS literals — `window.beginCaptureChrome(1)` — so `captureState.token` was the **number** `1`, `String(token)` the **string** `'1'`, and `1 !== '1'` is **always true**. Every capture report (profile frame -1, per-frame ready) died inside that guard; the dialog's 20 s watchdog produced the timeout box. The same bug lay latent in `beginCaptureFrames`' entry guard. Automated tests can't see it: they drive the QtWebEngine-free bridge in-process and never execute the page's JavaScript; the contract drift guard only greps the HTML text, never executes the page's JS.

**Fix**: stringify at storage — `captureState = { token: String(token), ... }` — making the echo comparison string-vs-string (and the same shape in `beginCaptureFrames`). The `TestBridgeContract` drift guard now additionally pins `token: String(token)` in the HTML so the coercion contract can't regress silently. Verified by the live harness: profile -> 3x1 frame settles -> stitch completes (`tile_grid=(1, 3)`). The harness now lives in the repo as `scripts/live_capture_harness.py`.

**Lesson**: (a) Any page-side guard comparing a value echoed from Python must stringify BOTH operands (or store it stringified) — Python hand-builds JS literals, and `1 !== '1'` is a silent always-false guard. This is the second #346/#347 case where **only a live run exercises the page's JavaScript**; pytest-bridge tests and name-grep drift guards are necessary but not sufficient — keep a real-key live harness in the repo and run it before shipping any page choreography change. (b) When "silence" is the symptom (OK returned, nothing after), look for a guard between the OK and the report, and probe the page state directly (`typeof window.fn`, `typeof map`) instead of trusting the cached bundle.

## Case study: frozen self-test kept the pre-layer provider contract (D2.4/D2.5, fixed 2026-09-06)

**Symptom**: The full test suite had one failure in `test_main_hardening.py`: the Qt3D checks passed, but the embedded Agent API self-test returned 1 with `AgentProviders.__init__()` missing the six layer providers.

**Wrong theories**: The failure initially looked like an Agent API server or PyInstaller regression because it occurred in the self-test that protects the frozen executable.

**Key evidence**: The captured self-test output named the exact constructor error before the server could start; the application startup path already supplied all six new layer callables by keyword.

**Root cause**: D2.4 added required layer providers to the shared `AgentProviders` dataclass, but the independent `_run_selftest()` probe in `main.py` still instantiated the old contract.

**Fix**: Update the self-test probe with no-op callables for every provider, preserving its rule that no provider may be invoked. The existing self-test then covers constructor completeness and server startup together.

**Lesson**: When extending an injected provider contract, search for every constructor—not only production wiring and tests. Keep the frozen self-test's no-op provider fixture aligned so it remains a whole-contract smoke test.

## Case study: layer deletion redo bypassed a lock added after undo (D2.4, fixed 2026-09-07)

**Symptom**: Senior review found that deleting a layer, undoing it, locking the replacement layer, and redoing could still delete the source layer and move its items onto the now-locked replacement.

**Wrong theories**: The GUI preflight and `CanvasScene.remove_layer()` guard appeared to cover the transition, and the initial command constructor check made direct execution tests pass. The missed path was command-manager redo, which re-executes an already-constructed command.

**Key evidence**: `CommandManager.redo()` popped the command before calling `execute()`, while `DeleteLayerCommand` checked `replacement.locked` only in `__init__`. The redo path therefore had neither a current precondition check nor a recoverable redo-stack entry.

**Root cause**: A mutable layer lock was treated as a construction-time invariant instead of a mutation-time precondition; redo is a second mutation entry point.

**Fix**: Revalidate the replacement lock at the start of `DeleteLayerCommand.execute()`, restore a command to the redo stack when redo execution raises, and add an undo → lock → redo regression test.

**Lesson**: Every undoable command must enforce mutable preconditions immediately before mutation, including redo. Test the state-changing interleavings explicitly, not only initial command construction.

## Case study: canonical delete-vertex builder read the post-deletion index (US-D2.6, fixed 2026-09-25)

**Symptom**: The interactive polyline "delete last vertex" gesture built an undo command whose stored position was read after the vertex had already been removed. Undo either restored the wrong point or, for the final index, tripped the builder's index guard.

**Wrong theories**: The initial shared builder looked correct because the Agent API path computes the position before executing the command. The assumption "the vertex still exists when the builder runs" was true for one caller and false for the other.

**Key evidence**: `PolylineVertexEditMixin._delete_vertex` removes the point and then calls `_on_vertex_delete(index, deleted_pos)`; the builder ignored `deleted_pos` and re-read the live index. The new regression test deleting index 4 of a 5-point fence failed at the builder's `0..3` guard, naming the off-by-state exactly.

**Root cause**: A shared command builder replaced two call-site orderings with one ordering. The interactive path is post-mutation; the agent path is pre-mutation. Reading shared state at build time made the seam order-dependent.

**Fix**: `build_delete_vertex_command` takes an optional already-captured local position. The interactive path passes its `deleted_pos` and permits the undo insertion index to equal the current count; the Agent API omits it and the builder reads the still-present vertex. Pinned by `tests/integration/test_polyline_vertex_edit.py::TestVertexAddDeleteShiftsConstraintIndices::test_delete_last_vertex_undo_restores_its_exact_position`.

**Lesson**: When consolidating two call paths into one helper, enumerate each path's mutation order relative to the helper call. "One canonical path" must preserve caller-supplied state where the caller has already mutated the thing the helper is tempted to re-read.

---

## Case study: the roof-ridge sync was a membrane, not a recompute (issue #364, fixed 2026-09-29)

**Symptom**: A HOUSE's linked roof ridge drifted off its polygon on vertex edits and never recovered. `add_vertex` moved the ridge's second endpoint onto a newly introduced slanted edge; undo restored the house to its exact original 4 vertices but left the ridge 36 cm out, and repeated edit/undo cycles accumulated the drift. The house itself looked perfect, so the only symptom was a ridge line that was very slightly wrong - and a roof texture that was very slightly tilted with it.

**Wrong theories**: Three, all pointing at the newest code. (1) The D2.6 vertex commands were corrupting the ridge - refuted by `git log -S "_update_ridge_on_boundary"`, which put the sync in `818e3fb` (#114); D2.6 only added a *call site*, `_after_vertex_topology_change`. (2) The constraint solver was moving the ridge as a side effect. (3) The bug needed a constrained or multi-item house to appear - it reproduces on a fresh, unconstrained, 300x200 rectangle drawn seconds earlier. Theory (1) is the instructive one: a bug reported against a recent PR reads like a recent regression, and measuring *when the code was written* rather than *when it was reported* is what redirected the whole investigation.

**Key evidence**: `polygon_item.py:308 _update_ridge_on_boundary()` never called the canonical `compute_roof_ridge_endpoints`. It looped over `ridge.points` and re-projected each onto the boundary with `_project_to_polygon_boundary`, then wrote `ridge._points` directly - outside the command system. The clincher came from widening the experiment: running the *same* code against a house rotated 30 and 90 degrees showed the ridge staying at 0 degrees, 75 cm and 180 cm off. A re-projection cannot rotate anything, because it only ever snaps an existing point to the nearest edge. A second measurement killed the issue's own proposed fix: `compute_roof_ridge_endpoints(polygon, item.pos())` returns `(1000, 2075)-(1200, 2075)` at **0 degrees** for a house rotated 30 degrees, because that formula adds `pos` to local points and ignores the item transform entirely. It is correct only for an unrotated item. Following the issue's fix option (a) verbatim would have made the filed test pass and left rotation broken.

**Root cause**: The ridge is *derived* geometry, but the sync treated it as *independent* state to be nudged into place. Re-projection is a membrane: it is idempotent only if the point is already canonical, and it has no notion of what the answer *should* be, so a once-perturbed endpoint can never return. And because the write bypassed the command system, no undo step covered it - restoring the polygon and restoring the ridge were two unrelated events.

**Fix**: Recompute through the one canonical `compute_roof_ridge_endpoints`, called in the polygon's **local** frame (`QPointF(0, 0)`) and mapped through the item's full transform (`mapToScene` -> `mapFromScene`). See ADR-046.

**The fix was incomplete, and the review round is the interesting part.** The first version passed 6509 tests and was still wrong: `_update_ridge_on_boundary` is called from four places, but a HOUSE's polygon is written by a **fifth** - the apply closure `ResizeItemCommand` replays for execute/undo/redo, built inside `_on_resize_end`. That closure restored the polygon and left the ridge sized for the *resized* house: **300 cm** of drift on a 300->600 cm resize, written into the `.ogp` because the ridge is itself a serialized item. No test anywhere in the suite resized a HOUSE, so nothing noticed. The closure is now module-level (`polygon_resize_apply`) specifically so the test can drive the production function instead of re-implementing it - my first attempt at that test copied the apply logic, which would have passed while the real closure stayed broken. It also failed on `command.redo()`, which does not exist; redo replays `execute()`.

**A later round found a sixth writer**, the constraint solver's `finally` block, which restored a polygon with a bare `setPolygon` while its polyline sibling restored through `_move_vertex_to` — asymmetric in the same file, 150 lines from the one already fixed. Found by review, not by a test. ADR-046 now enumerates all six and tells the next person to re-derive the list with grep rather than trust it.

**Lesson**: Three. (1) When B is derived from A, the sync must *recompute* B from A, never *adjust* B from B's own current position - an adjustment creates a second source of truth that no undo can own, and the drift is invisible until something measures it. (2) Before reusing a geometry helper, check what it is invariant to. `compute_roof_ridge_endpoints(polygon, pos)` looks like the canonical ridge function and is correct for every unrotated object, so it passes every test written against a default; it is simply wrong under rotation. "Works at the default value" is a symptom, not a guarantee - parametrise over the parameter the defect scales with, and if the unfixed code passes some of your cases, that is information about the defect, not about the test. (3) **Enumerate every writer of the owner's state, not every caller of the sync you can see.** A green suite is evidence about the paths it exercises; the resize-undo hole survived 6509 passing tests because no test had ever resized a HOUSE, and "grep for the function I edited" would not have found it either. When a test needs to pin a private apply path, make the path reachable from the test (module-level) rather than copying it - and check the assertion fails without the fix, which is what caught both this and the `redo` mistake.

---

## Case study: the roof tiles lapped uphill because "left" does not mean "downhill" (issue #372, fixed 2026-09-30)

**Symptom**: A HOUSE's roof tile texture lapped back *up toward the ridge* on **both** halves of the roof - they read the same outward sequence, being mirror images of each other, so the inversion could not appear on one side alone. The owner reported it from the #364 manual test as: "rest of the roof manipulations work well now - but the roof tile direction doesn't check out, it is inverted", then, on being shown a render: "regardless of whether I paint a vertical or horizontal house, it is always the wrong direction", and gave the physics - the tiles nearer the ridge must overlap the outer ones, or water runs back inside.

**That last clause was the diagnosis.** "Always wrong, in both orientations" rules out a rotation bug immediately, because a rotation bug would be correct at whichever angle the code was written for. I had been treating this as a question about *which* orientation the user wanted; the user had already told me the invariant (down-slope points away from the ridge) and that both orientations violated it. Asking "which do you prefer" when the answer is "water must not run uphill" wasted a round-trip and framed a physical bug as a preference.

**Wrong theories**: (1) The brush rotation was broken. Refuted by rendering the transform in isolation: `rotate(90)` does turn the courses. (2) The inverse brush mapping introduced a 180-degree flip. Refuted: `T = translate . rotate(a)` has determinant +1, so `T^-1` is a pure rotation -- there is no reflection in the sampling frame to explain a reversal. A four-quadrant probe texture also showed the pattern is symmetric under the rotation. (3) The mirror axis was wrong. Refuted by measuring: the mirror does track the ridge correctly.

**Key evidence**: The roof-tile texture's direction, read off the texture itself rather than assumed - a dark lapse line near `y=10` with the light rounded free edge beneath, so `+Y` is down-slope. Then rasterizing the two clip regions returned by `_split_path_by_line` and asking which side of the ridge each one actually covered: for a +X ridge, `left_path` is the LOWER half; for a +Y ridge, it is the LEFT half. The halves were named by the left-perpendicular, which follows ridge *direction* and says nothing about which side is downhill - so the half needing the true down-slope was the one being mirrored. Finally the identity that made the fix exact: `normal_tx` is `translate . rotate(angle)`, a `QBrush` samples the texture at `T^-1.p`, so texture `+Y` lands at `R(angle).(0,1) = (-sin a, cos a)`, which is precisely the `n` that `left_path` is offset along. `left_path` is therefore the down-slope half and must take the normal brush - a swap, not a probe.

**The measurement nearly cost the fix, and the user called it.** I had shown the two builds differ, then built a harness to demonstrate it and got *byte-identical* images at every angle - so I concluded the fix was a no-op and put a revert proposal to the user, who replied with a screenshot: "I don't know why you think your result is a no-op. you fixed it, the roof now looks correctly." The user was right. The harness was the bug: to stop the ridge's stroke covering its sample points it called `scene.removeItem(ridge)`, which makes `_find_ridge()` return `None`, which means `_paint_with_ridge` is never called. Every render measured `super().paint()` - the fallback both builds share. The senior reviewer's P1 ("your test does not call the production code") was this same defect pointing at me, and the correct response to it was to re-measure the *fix* with a corrected instrument, not to conclude from the broken one. With the ridge hidden by `setVisible(False)` the difference is unambiguous: fixed `RBBRBB`, pre-fix `BRRBRR`, on both halves, at every ridge angle.

**The same class of bug bit twice more in the same file, and each produced a plausible-sounding false conclusion.** (a) The second attempt hid the ridge with `ridge.setPen(QPen(NoPen))` and its docstring claimed that stopped the stroke - it does not, because `_paint_roof_ridge` strokes three *hardcoded* pens and never reads `self.pen()`; the docstring asserted a suppression that never happened. The working call is `setVisible(False)`, which `_find_ridge` does not filter on and `scene.render` does skip. (b) `_ridge_axis` ran the ridge points through `house.mapToScene` although they are already scene space (since #364), so the harness sampled 30 degrees off the real ridge normal at 30 degrees of rotation - and that produced a phantom "degenerate band" at 90 and 270 degrees which I then wrote into the ADR as a fact about the roof. (c) The test swept the house's *rotation* over nine angles and I called that angle coverage, but the angle `_paint_with_ridge` feeds to `normal_tx.rotate()` is the ridge direction in the polygon's **local** frame, which `compute_roof_ridge_endpoints` pins to the longest bounding-box axis: 0 for a landscape house at *every* rotation, 90 for a portrait one at every rotation (measured by spying on the value). `rotate(-a)` and `rotate(+a)` are the same transform when `a` is 0, so a rotation-only sweep is structurally **blind** to a negated sign - the very term the swap argument rests on. Adding a portrait house caught it at once: negated, the landscape cases still read `RBBRBB` and all four portrait cases read `BRRBRR`. A fourth item was simply wrong: I wrote that reversing the ridge's point order "re-breaks both halves". It does not. Reversal flips the texture coordinate `u` and leaves `v` alone, so it mirrors the pattern *along* the ridge - measured 0.00% pixel difference with a probe symmetric in `x`, 44-93% with one asymmetric in `x`. The lap direction is untouched. With it fixed, a sweep of every 15 degrees from 0 to 345 reads `RBBRBB` at all of them, on both landscape and portrait houses: the result is orientation-independent, which is what one should expect when the defect tracked *which half got the mirror*. **A sweep that looks thorough can still pin nothing** - see (c) below, where nine rotation angles all left the quantity the code consumes pinned at 0.

**Root cause**: A geometric naming convention standing in for a physical one. The code branched on `left_path`/`right_path` as though those names meant "downhill"/"uphill", and they encode ridge direction instead.

**The measurement almost hid it.** Correlating the real 256px tile texture against the render - the obvious approach - produced peak correlations of ~0.03 *either way*, and at the diagonal a 0.020-vs-0.019 coin flip. A few hundred sampled pixels span barely one texture period, so the metric had no power to separate right from wrong, and the first version of the test would have passed broken code. The fix came from throwing away the real texture and substituting a **two-colour probe**: red on the top half, blue on the bottom, so blue *is* the down-slope, and reading a six-pixel sequence outward from the ridge answers the question. A single pixel cannot: the probe tiles, so its value depends on where the sample happens to land. A separate dead end: pytest reported a *hang* rather than a failure, because a `NameError` in a function annotation surfaces as a timeout under the thread method - and the actual cause was that `create_pattern_brush` builds a `QPixmap`, which needs a live `QApplication`, so the test had to take `qtbot`.

**Fix**: Give the normal brush to `left_path` and the mirrored one to `right_path`, with the arithmetic recorded at the call site. The two-sided `setClipPath` + oversized `drawRect` shape is deliberately untouched: Qt does not serialize the painter clip into SVG and `ExportService._fix_svg_qt_texture_clipping` pairs shadow and texture groups 1:1. Pinned by `tests/unit/test_roof_tile_orientation.py` with the two-colour probe, parametrised over eight house/rotation cases spanning landscape, portrait and square. The defect is wrong at *every* orientation including the axis-aligned ones - an earlier claim that the old naming coincidentally lined up there was falsified by `ridge0` failing against the pre-fix code - so those angles are ordinary rotation coverage, not a search for whichever ones happen to fail. See the ADR-046 addendum.

**Lesson**: (1) A geometric name is not a physical one - when you branch on `left`/`right`, `near`/`far` or `first`/`second`, verify the name survives rotation before trusting it. (2) A user who says "this is always wrong" has usually already localised the bug to an invariant, and the useful response is to extract that invariant, not to ask which behaviour they prefer. (3) If a rendering assertion cannot separate the two cases, change *what it measures* - a two-colour probe, an asymmetric marker - instead of loosening the threshold; and sanity-check that the new metric actually fails on the old code before trusting it to pass on the new. (4) A green 6515-test suite contained zero assertions about a rendered roof pixel, which is why a bug visible at a glance survived for two years.

## Case study: nine tests, one wrong assumption - `species_key` is a function, not a field (issue #331, fixed 2026-10-01)

**Symptom**: Adding `suggest_succession` to the Agent API (US-D3.2). Nine unit tests in
`tests/unit/test_agent_succession_domain.py` failed, and they failed *identically* - several
returning an empty list where a ranked candidate list was expected, others raising `KeyError` on a
species key that had been returned by the function under test a moment earlier.

**Wrong theories, in order**. (1) That the family-exclusion filter was too aggressive and was
discarding everything - plausible, because three of the failures were exactly "expected 3 species,
got 0", and `within_plan_families` was the newest input. (2) That the window-fit arithmetic was
wrong (`fits_window` was `False` in two cases). (3) That `PlantSpeciesData` simply had no
`family` populated, since `_species()` built the records by hand and `family` came back empty.
Each of these would have justified a "fix" that changed the filter, the date maths, or the test
fixture. All three were wrong, and theories (1) and (3) were actively misleading: the filter was
never reached, because the candidate loop skipped every record before reaching it.

**Key evidence**: two `KeyError`s that were decisive. A test asserted `by_key["beans"]` after
`by_key` had been built from the function's own output - so the key `beans` had to be in the input
somewhere. It was not. Following it into `_species()` showed the fixture setting
`scientific_name`/`common_name` but never a `species_key` field, and
`suggest_succession_for_agent` deriving its key with `getattr(record, "species_key", "")`. That
attribute does not exist: `species_key(species_dict)` is a **module-level function** in
`models/plant_data.py` (ADR-016). `getattr` returned `""` for all 118 bundled species, the
`if not key: continue` guard skipped every one, and the function returned `[]`. Nine symptoms, one
assumption.

**Two further facts surfaced only after that was fixed**, and both would have broken the story in
production rather than in tests. (a) ADR-016's priority is `source_id -> scientific_name ->
common_name`, so a bundled plant's canonical key is its **scientific** name: `"phaseolus
vulgaris"`, never `"beans"`. The first integration run failed with
`Unknown species_key 'beans'`, having already passed every unit test. (b) `WriteResult` has no
`message`/`undo_step` fields - it has `action: Literal[...]` and `undo_description: str` - so the
write tool's return value failed pydantic validation with `2 validation errors`. Both were caught
only because the integration test wired a **real** command instead of a stub.

**Root cause**: a `getattr` with a default, used to read a field that had been imagined. The
default made the bug silent - no `AttributeError`, just an empty result that reads as a legitimate
answer ("this bed has no suitable crops") rather than a crash.

**Fix**: Derive the key with `species_key(record)` inside the domain function, and change the
contract from "species objects" to "raw species dicts" so the canonical derivation is the only
path. Also switched the schema's `species_key` derivation and the test fixtures to real scientific
names, and corrected the `WriteResult` construction in both `application.py` and the test.

**Lesson**: (1) When many tests fail the *same* way, hunt the shared assumption before fixing any
of them - three theories in this case each pointed at a different function, and none was the cause.
(2) `getattr(obj, "field", default)` converts a missing-attribute bug into a silent empty result;
prefer an explicit lookup so a renamed or non-existent field fails loudly. (3) Verify the
*constructor* of any shared result schema before building on it - `WriteResult` had accumulated
required fields, and a unit test with a stub could never have noticed. (4) An integration test
built from stubs proves the transport and nothing else; the three defects above were all invisible
to unit tests and all visible the moment a real `CommandManager` and real schema were used.


## Case study: a drag preview that drew behind the bed (issue #377, fixed 2026-10-02)

**Symptom**: While drawing a plant into a raised bed, the dashed preview circle was
invisible for the whole drag - it showed only where it poked outside the bed silhouette - and
the plant "popped" into the front on release. With a plant much smaller than the bed the
entire preview was hidden and placement was blind, guided only by the `Dist / Winkel` HUD.
Reproduced with raised and polygon beds alike.

**Wrong theories**. (1) A paint-order regression from the per-object stacking work (#338) -
plausible, because stacking order was the most recent change to z-values. (2) The preview
item being inserted into the wrong parent. (3) The bed's own paint() drawing over everything.
All wrong. `git log -S "setZValue" -- core/tools/circle_tool.py` returned nothing: the
preview had *never* had a z-value, so it predated #338 entirely.

**Key evidence**: two measurements that made the bug a two-line fact.

```
bed z            = 50.0
preview circle z = 0.0        <- QGraphicsEllipseItem, not a CircleItem
bed beats preview = True
final plant z    = 66.67       <- after release, via the derived-z refresh
plant beats bed  = True
```

`0.0 < 50.0` during the drag, `66.67 > 50.0` after it. Real items get a derived z strictly
inside `(0, 100)` from `CanvasScene._refresh_layer_z`; a bare `QGraphics*Item` keeps Qt's
default `z = 0`, so it loses to everything.

**Root cause**: the preview primitives were never assigned a z-value, and the derived-z
system silently outranked them. A class defect, not one tool: **11** modules built previews
with no z-value.

**A wrong census nearly cost the fix**: the issue's own list of affected modules named 13,
omitting `construction_tool.py` (which does build previews) and including `text_tool`,
`fillet_tool`, `chamfer_tool` (which build no preview item at all - zero grep matches). The
fix therefore re-derived the set from source, and the drift-guard test does the same rather
than trusting a hand-written list.

**Fix**: `core/tools/preview_z.py` defines the reserved band (`999` fill, `1000` line,
`1001` label, `1002` handle), deliberately below `minimap_widget._OVERLAY_Z_MIN` (`10_000`)
so a preview stays visible in the minimap thumbnail. Every preview construction site calls
`setZValue`.

**Lesson**: (1) **No test had ever drawn a preview over an existing item** - every tool test
drew on an empty canvas, where `z = 0` is enough. A green suite is evidence only about the
paths it exercises. (2) When a bug report hands you a list of affected sites, treat it as a
symptom description, not a census - re-derive the set from the source. (3) Measured z-values
turned a "painting problem" into a two-line inequality; instrumenting the numbers beat
reading the paint code.


## Case study: 10-second shutdown that only happened with a client attached (issue #373, fixed 2026-10-02)

**Symptom**: closing the app took about 10 seconds, with two log lines: a WARNING that the
Agent API thread "did not stop within 5.0s", then an ERROR that it was "STILL RUNNING after
5.0s + 5.0s". Intermittent - it did not happen every time the app closed.

**Wrong theories**. (1) The app wiring missing `MainThreadBridge.abort_pending()` before
`stop()` - that is exactly what the `server.py:248` `_STOP_TIMEOUT_S` comment says callers must do. Falsified
by reading the code: `application._stop_agent_api` already calls `abort_pending()` first.
(2) uvicorn's `force_exit` needing to be set - plausible from uvicorn's docs, and the obvious
first fix. **Measured and falsified**: `force_exit = True` alone left the shutdown at 10.01 s.
That is the single most useful result in this case, because it is the fix everyone reaches for.

**Key evidence**: a watchdog thread that dumped every thread stack and every live asyncio task
6 seconds into the join.

```
--- thread 43964 ---
  _run
    loop.run_until_complete(server.serve())
      ...
        self._selector.select(timeout)      <- the loop is IDLE
--- WATCHDOG: 12 live asyncio task(s) ---
  task: Task-1 ... Server.serve            state=PENDING
  task: sse_starlette.sse.EventSourceResponse.__call__.<locals>.cancel_on_finish
  task: mcp.server.session.ServerSession._receive_loop
  task: Task-7 ... _shutdown_watcher
  task: mcp.server.streamable_http_manager.StreamableHTTPSessionManager._handle_stateless_request
```

The stack showed `serve()` suspended in the event-loop selector - **not** in a Python frame
inside the shutdown path - and the task dump named the blockers: the MCP `ServerSession`
receive loop and sse-starlette's stream. Reproduction confirmed the trigger: **0.19 s with no
client, 10.03 s with a client holding the SSE stream open**.

**Root cause**: uvicorn's graceful shutdown waits for open connections to finish. An MCP
client holding the SSE stream open never closes it, so `serve()` never returned and both
5-second joins expired. `force_exit` skips uvicorn's connection drain but the MCP session/SSE
tasks keep the loop alive past it, which is why it did not help on its own.

**Fix**: `stop()` stores the loop on the server and, via `call_soon_threadsafe`, cancels the
loop's tasks and calls `loop.stop()`. `run_until_complete` then raises
`RuntimeError("Event loop stopped")`, which `_run` recognises as the deliberate path and does
**not** log as a crash. Measured after: 0.58 s with a streaming client, 0.00 s without.

**Lesson**: (1) **A lifecycle defect whose reproduction needs a concurrent peer will not be
found by a single-threaded test of the happy path** - no test held a client across a stop, so
the fast default path stayed green. (2) The obvious library-supplied fix (`force_exit`) can be
wrong; only measuring it proved it. (3) A stack dump that shows a loop **idle in its selector**
says "nothing is running and something is still awaited" - pair it with an asyncio task dump,
which names the waiters the stack cannot.


## Case study: six defects where a plausible value was not the value the engine means (issues #332/#333, fixed 2026-10-03)

**Symptom**: No symptom, in the usual sense - this is the case for writing tests
that compare against the ENGINE rather than against an expected literal. While
building US-D3.3 (task tools) and US-D3.4 (soil tools) six defects surfaced, five
of them in code I had just written, and not one of them announced itself as a
crash. Each produced a value that looked entirely reasonable.

**Wrong theories, in order.** (1) That the soil health ratings were a mapping bug -
`health_level(record, "ca")` returned `"poor"` for a healthy bed and I assumed the
secondary scale was being read wrongly. (2) That `get_effective_record` was
returning the wrong record. (3) That the Rapitest validation was too strict, since
`n_level=5` was refused. Theories (1) and (2) each would have justified editing
working code.

**Key evidence.** (a) `SoilService.health_level` has no `else` and no error for an
unknown parameter: `if parameter == PARAM_PH ... if PARAM_K ... # OVERALL`. A
sixth call **falls off the end and returns the overall rating**. So `ca`'s
"health level" was the whole bed's health - a real number, wrong subject. (b)
`grep 'source="' services/task_generator.py` returned eight hits with the values
`calendar, propagation, succession, succession, soil, soil, frost, manual` - **six**
distinct, while my `TASK_SOURCES` tuple had seven, because I had copied
`soil_amendment` / `soil_mismatch` out of the issue text. Both soil generators
emit `source="soil"`; `task_type` is what tells them apart. (c) `grep -rn "_ppm"
src/` showed hits only in `models/soil_test.py`, `soil_test_dialog.py` and one
comparison helper - **nothing in `services/` reads the ppm fields at all**.

**Two guards were themselves the bug.** The `TASK_SOURCES` drift guard asserted
`emitted <= TASK_SOURCES`, a **subset** check, which passes on extra entries - so
it green-lit two values no generator can emit. The field failure would have been
`source="soil"` refused as unknown while `source="soil_mismatch"` silently returned
nothing. Separately, the first version of that guard was fixture-driven, and four
of seven generators need live inputs a bare `PlanState` cannot supply, so it
would have under-reported and passed vacuously. It is now AST-based and asserts it
saw at least seven `Task(...)` constructions.

**Root cause**: every one of these is a **fall-through or a copied name**. A
default branch that answers a question nobody asked; an identifier taken from prose
instead of from code; a hierarchy applied inside a function so the caller cannot
see which branch ran; and a range that looks uniform and is three different ranges.
Nothing raises, and nothing looks wrong.

**Fix**: (a) route only `RATED_PARAMETERS` through `health_level` and make
`SoilReading.health_level` optional, where `None` means "no rating exists" -
distinct from `'unknown'`, which means "not tested"; (b) read the source values
from the module by AST and assert **equality both ways**; (c) refuse ppm by name
and take kit-only parameters whose names state the scale, with per-nutrient
ranges (`k_level` is `1-4`, the kit has no K0); (d) report `record_source`
alongside the reading, since `get_effective_record` applies its hierarchy
invisibly; (e) accept `credits` as the `(kind, current, target)` triple it is -
caught on the first call by the field-for-field equality test, which is exactly
what that test is for.

**Lesson**: (1) **Write the assertion against the engine, not against a literal
from the issue** - a test written from prose inherits prose's errors, and five of
these six would have shipped green under one. (2) A fall-through default is a
silent wrong answer; make the field that cannot be computed **nullable** rather
than letting a default fill it. (3) A drift guard must assert **equality in both
directions** and must assert that it observed something - a guard that can pass
vacuously reports success forever, which is worse than no guard because it is
trusted. (4) When a model carries two representations of one value (`*_level` and
`*_ppm`), check **which one the engine actually reads** before designing input for
it; the one that is stored but unread looks like a feature and behaves like a
trap.


## Case study: D3 provider tests passed while public soil tools failed (2026-10-04)

**Symptom.** A handover reported 6951 passing tests. A real MCP client against the
frozen executable returned errors from both soil reads and the soil-planning
prompt. Annual task calendars also returned empty, fully-covered years.

**Rejected explanations.** A frozen-only hidden import problem and a broken
main-thread bridge were plausible before the probe. Neither explained successful
manual-task writes, undo and amendment recommendations in that same client.

**Key evidence.** The scratch client printed the actual results:

```
[D3-LIVE] get_soil_status ERROR: 6 validation errors for SoilStatus
[D3-LIVE] get_soil_mismatches ERROR: total Field required
[D3-LIVE] plan-soil-amendments ERROR: 6 validation errors for SoilStatus
[D3-CALENDAR] requested=2027 reference=2026-10-03 months=[]
```

Status providers returned `beds` lists; the server constructed a single-bed
model. Mismatch providers returned per-bed mappings; their server model required
an unrelated top-level `total`. The integration suite never made those public
calls. Separate failing probes found that an old global soil reading checked an
empty bed history, German names remained English, and MCP validation coerced
booleans/strings into numeric readings before the domain guard could refuse them.
Propagation generated nothing because the provider supplied no plans.

**Root cause.** The tests stopped before the boundary their prose claimed to
exercise. Calendar generation also discarded inactive tasks before the requested
period filter, and the requested year reached only bucketing, not generation.

**Fix.** Typed soil envelopes, explicit per-bed extraction in the prompt, and
real HTTP integration workflows using the production provider graph. The shared
engine now separates year from reference date and has an explicit actionable-only
option; cross-year intervals are clipped. Propagation uses the extracted GUI
calculator. The soil service resolves record/source/history together; names use
its existing bilingual display method; MCP soil numbers use strict annotations.
Every defect has a regression observed failing first. Instrumentation stayed in
the scratch probe and temporary test prints were removed before commit.

**Lesson.** A green provider test cannot validate server schema construction.
Drive the public call with the production graph. Generate a period before
classifying urgency, preserve the chosen record's provenance through derived
checks, and test refusal before and after framework argument coercion.


### Case study: D3 frost anchors and unassessed lab readings (2026-10-04)

**Symptom.** Extending a task window into the next year changed its earlier-year
results; an unknown lab-only soil record was described as near target.

**Wrong theory.** Matching the requested calendar years was sufficient after
year bucketing was fixed; an empty engine result implied healthy measured soil.

**Key evidence.** Temporary regression prints showed [D3-ANCHOR] lacked
llium sativum:direct_sow:2027 in the 2026-only result even though its dates
were 2026-10-15 through 2026-10-29. [D3-LAB] showed unknown health and an empty
plan beside the near-target prompt claim. Three regressions failed first.

**Root cause.** Negative and multi-year frost offsets cross anchor-year
boundaries; existing GUI lab ppm records are not converted to kit levels.

**Fix.** Derive anchor years from the actual calendar/propagation offsets, then
filter date overlaps through the same path for both annual and window reads.
Keep empty-result prose neutral and explicitly mention unassessed lab readings.
Temporary prints were removed.

**Lesson.** Generate from dates, not matching year labels. An empty result
establishes only what the engine assessed, not what the caller hopes it means.

## Case study: three i18n leaks the zero-unfinished gate cannot see (issues #393, #408, #410, fixed 2026-10-04)

**Symptom.** With German UI, generated soil-amendment task titles stayed English
(`Compost`, `Elemental sulfur`) while the same bed's amendment recommendations were
German; the agent `suggest_companions` tool returned English plant names while the
Companion panel was German; and the opt-in "Garden journal notes" PDF page printed five
strings in English. `test_german_ts_has_no_unfinished` was green throughout.

**Wrong theories.** "The `.ts` file is missing translations" (it was not — the strings
were either data-selected or never registered). "The agent layer must translate" (it
must not — localisation is upstream, and a second path is the failure the D3 convention
exists to prevent). "Make `display_name()` default to the active language" (that would
have changed the persisted task id and orphaned saved done/snooze state).

**Key evidence.** `ruff check scripts --select F601` reported five repeated
`TRANSLATIONS` keys; an `ast` diff showed 62 strings shadowed, 5 absent from `de.ts`.
`grep` found the only no-language call sites: `task_generator.py::_bed_amendment_recs`
and `companion_sets.py::suggest_companions`. `tests/unit/test_task_generator.py` pinned
the task id as `soil_amendment:bed-1:Garden lime`, proving the id was the English name.

**Root cause.** All three are display strings produced by shared, Qt-free services that
never resolved the active UI language (a `lang="en"` default), or were dropped by a
duplicated dict key before they could be registered. The gate only inspects strings
already in the table.

**Fix.** One shared `app/settings.py::active_language()`; `BedInput.amendment_recs`
carries `(stable_name, display_name, rationale)` so the id stays English and only the
title localises; `suggest_companions` takes a `language` argument; the five shadowed
`PdfReportService` strings were merged into their surviving block; and CI now runs
`ruff check src/ tests/ scripts/` with an `ast` uniqueness test.

**Lesson.** "All strings translated" is three separate claims: the string reaches
`tr()`, its literal matches the registered key, and the registry actually emits it. A
data-selected display name and a duplicated registry key each pass the gate while
failing the user.


### Case study: repeated absolute propagation overrides (2026-10-04)

**Symptom.** An annual task read counted one overridden propagation step three
times; a three-year read counted it five times.

**Wrong theory.** Deduplicating by canonical task ID handled absolute dates.

**Key evidence.** Temporary [D3-OVERRIDE] output showed five prick-out tasks
on 2026-03-10 with IDs ending in 2024 through 2028. The integration regression
failed before the fix.

**Root cause.** The expanded anchor loop reapplied the same override, but the
shared propagation generator assigned a different anchor-year ID to each copy.

**Fix.** Assign overridden steps to their start-date year in the shared generator;
relative steps retain anchor-year IDs. The regression checks one task, its ID,
GUI convergence and annual month counts. Temporary instrumentation was removed.

**Lesson.** Preserve the distinction between absolute and relative time through
identity, not just range calculation. Deduplication cannot repair wrong identity.

## Case study: models blank and unpickable after a probe swapped them out and back (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the Windows evidence run picked **0/20** where the container picked 20/20 with
the same code. A board render after the same flags looked normal up to the probes and was
not looked at afterwards.

**Wrong theories**. (1) A Direct3D 11 vs OpenGL picking difference — plausible, because the
container renders OpenGL and the runner D3D11 on WARP. (2) Display scaling on the runner.
Both died on one reproduction: the Windows command ran `--iou --orient` *before* `--pick`;
the container run had not. Running `--orient --pick` locally gave 0/20 on OpenGL too.

**Key evidence**: an A/B over the swap itself, picks and a pixel diff against the first frame:

```
1 initial                         hits=20/20
2 same objects re-attached        hits=0/20     frame == empty scene (diff 66.34 vs 66.34)
3 fresh SpikeModel+NumpyGeometry  hits=20/20    frame == initial (diff 0.00)
B re-attached + update():         hits=0
C re-attached after set_mesh():   hits=20
5 partial removal then restore    hits=19/20   <- after the first fix
```

**Root cause**: once the Model using a `QQuick3DGeometry` is destroyed, the same geometry
handed to a new Model renders and picks nothing (the C++ object is alive — `sip.isdeleted`
is False — but its data is gone); `update()` does not restore it, a full re-upload does. The
probes restored the scene with the same model objects, so everything measured after them —
picks, the soak, its re-entry times — ran against an empty garden. The first fix
re-uploaded only models that had been removed and measured **19/20**: a `Repeater3D` over a
JS array destroys and recreates **every** delegate on any change, so the one model that never
left came back blank too.

**Fix**: `SpikeRenderer.set_models` re-uploads every previously shown geometry; the pick probe
re-checks after a detach/re-attach cycle and the render tier runs it after `--iou`.

**Lesson**: (1) **A probe that mutates shared state must restore it through the same path the
product uses** — and every measurement after it inherits its mistakes silently. (2) When a
fix scores 19/20, the miss is the hypothesis test: here it was the model that had never been
removed, which disproved "only removed models break". (3) Compare the *same flag order* on
both machines before blaming the platform.

## Case study: the 56-minute "hang" that was a stopwatch problem (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the temporary Windows workflow built the frozen exe, passed `--selftest`, then ran
the spike for 56 minutes until the job limit killed it — no output, no metrics, 7 PNGs in the
uploaded artifact (which could not be downloaded from the analysis container anyway).

**Wrong theories**. (1) A deadlock in the threaded render loop. (2) The window never exposed on
a headless runner, so no frame ever arrived. Neither could be tested: there was no evidence at
all, because a GUI-subsystem exe has no stdout (`print` is a no-op — the #291 precedent) and
`Start-Process -Wait` has no timeout.

**Key evidence**: after the spike learned to write a flushed, timestamped `spike.log`, rewrite
`metrics.json` after every phase and arm `faulthandler.dump_traceback_later` (verified first by
forcing a 12 s watchdog, which named the exact `wait_frames` call), the next run said:

```
 12.61s [wait] label=first_frame want=2 got=3 ms=6247.4 timeout=False exposed=True
 26.39s [wait] label=golden_hour_low want=6 got=6 ms=6344.1 timeout=False exposed=True
 97.03s [grab] label=golden_hour_low ms=69156.5 px=960x540
```

Frames arrived about once a second; one `grabWindow()` of the sky-lit scene took ~69–100 s.
Later grabs of the same sky took 20–500 ms; every *new* sky light probe cost 40–85 s again.

**Root cause**: not a hang — software rendering (WARP) of a freshly prefiltered sky light probe,
paid in the first frames or grab after each sun change, times the many shots of run v1.

**Fix**: headless evidence tooling writes its own log, per-phase metrics and a watchdog; the CI
driver bounds the run with a hard timeout and prints the evidence into the job log; every grab
is timed on its own.

**Lesson**: **without timestamps, "slow" and "hung" are indistinguishable** — instrument
before theorising, and give any process that must run headless its own evidence channel.

## Case study: ~30 MB per project reload, and it was our keep-alive list (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the first soak with real project reloads (`--soak 50`: 50 hide/show cycles, every
fifth one reads the plan from disk into a new scene, re-bakes the ground and builds every model
and geometry new) exited 0 — no crash on the QML-vs-Python lifetime path — but RSS went
700 → 1015 MB.

**Wrong theories**. (1) The engine keeps the GPU buffers of destroyed `QQuick3DGeometry`
objects. (2) RSS growth is just the allocator not returning memory to the OS. Both were
plausible; the total-growth number could not tell them apart.

**Key evidence**: one A/B with a temporary toggle, RSS recorded after every refill (with
`gc.collect()` first, so cyclic garbage does not count):

```
keep every ground texture : 771 822 844 910 939 969 969 998 1005 1035   (+30 MB per reload, linear)
hold only the shown one   : 771 805 799 864 864 889 889 887  887  882   (settles)
```

The per-reload step matched one baked ground: 2400×1600 RGBA = 15.4 MB in the texture data
plus its GPU copy (system RAM on a software rasteriser).

**Root cause**: `SpikeRenderer.set_ground()` appended every `ImageTexture` to an append-only
`_keep` list (Python owns the texture, so *something* must hold it while QML shows it). Engine
and geometries released their memory; our keep-alive did not. Releasing the replaced texture
*after* the scene shows the new one ran 10 reloads clean (llvmpipe).

**Fix**: hold exactly the texture the scene shows; `preserved_state()` re-pins the texture it
restores. The soak now reports the RSS curve and its least-squares slope over the second half
(`rss_tail_slope_mb_per_reload`); the render tier and the CI driver require < 10 MB/reload.

**Lesson**: **judge a leak by its slope, not by total growth.** Both variants grew ~70 MB on
the first reload (a second model set, allocator arenas); only the trend separates a leak from
an allocator settling. And a keep-alive list is a leak with a good excuse: hold the one
object that is in use, not every object that ever was.

## Case study: a second window that "differed" by 9.8 luma: the comparison was right, the first diagnosis was not (ADR-048 spike, fixed 2026-10-04)

**Symptom**: `--second-window` reported `frame_diff_vs_first` 9.8 mean luma on llvmpipe and
9.75 on D3D11 (Windows v9), so the second window seemed not to render the first window's view.

**Wrong theories**. (1) Temporal anti-aliasing not yet converged in the young window, but
the low preset has no AA at all. (2) `copy_view_from` missing a property, but the state keys
come from the QML meta-object, so nothing was left out by hand. (3) **A stale reference
frame**, grabbed right after the previous probe restored its state, before a redraw. This
one shipped as a fix (a three-frame settle before the reference grab), validated by a run
that **left out `--iou`**, the probe that triggers the defect. Without the trigger the
difference is 0.0 with or without the settle, so that run proved nothing, and the commit's
"17 passed" came from a tree that never held both the assertion and the settle. Senior
review ran the full flag set and read 9.83 again.

**Key evidence** (senior review, pass 4): the first window grabbed before and after
`shadow_iou_probe` alone differed by **13.1** mean luma, 0.0 in the top half and 26.2 in the
bottom half: the plan ground (lawn, paths, pond) was white. No root state key had changed.

```
ground.update() alone                          diff 13.1   (no effect)
ground.setTextureData(textureData()) + update  diff 0.0
a fresh ImageTexture                           diff 0.0
```

**Root cause**: the texture twin of the geometry rule in the case study above. The IoU and
orientation probes set `groundTexture` to null, which detaches the `QQuick3DTextureData` from
its QML `Texture`; `preserved_state()` set the *same* object back, and Qt Quick 3D draws a
re-attached texture data object untextured (white) until its data is uploaded again. The
first window kept a white ground until the soak's next reload; the second window, with its
own texture, drew the right one. `preserved_state`'s identity guard passed throughout: it
checked Python's bookkeeping (the shown texture is the one held), not the engine's pixels.

**Fix**: `preserved_state()` re-uploads the ground whenever it was detached; the settle wait
is gone. Test-first: the runner grabs the first window before the probes and after them
(`probe_restore_frame_diff`), the render tier asserts it below 1.0 (9.83 before the fix, 0.0
after, with `--iou --orient --pick --update-bench --second-window`), and the CI driver checks
it and `frame_diff_vs_first`.

**Lesson**: **a validation run that omits the trigger proves nothing.** Before accepting a
root cause, reproduce the failure with the exact flags that produced it, then show that same
run passing with the fix; a fix validated where the bug cannot occur is a guess with a green
tick. And a guard on bookkeeping (the right object is held) is not a check of the outcome
(the right pixels are drawn): test a contract in the currency it promises.

### Case: the Tasks tab said "you're all caught up" while a harvest was open

**Symptom**: a southern plan (20 September last spring frost) put a tomato harvest at
29 Nov 2026 – 7 Feb 2027. On 1 January 2027 the Tasks tab and the planting-calendar
dashboard listed nothing; a tomato-only plan rendered *"No tasks — you're all caught up."*
The agent's `get_tasks`, over the same plan and the same date, listed it. A garlic plan
(9 April frost) had an autumn sowing on 9-23 Oct 2026 that reached no GUI surface at all.

**Wrong theories, in order**:
1. *The dashboard and the Tasks tab filter differently.* They do not — both called
   `generate_all(build_plan_state(...))` and shared the urgency rule. Reading the two
   call sites "fixed" nothing, because they agreed.
2. *The offset maths is wrong.* It is not. `generate_calendar_tasks` computes
   `last_frost + timedelta(weeks=offset)` and the numbers were right for the year it
   anchored on.
3. *The agent is being generous and showing speculative windows.* No: the agent's
   `generate_for_date_window` derives the set of anchor years from the offsets
   (asparagus harvests 104 weeks after its frost; garlic is sown 26 weeks *before* it),
   and the GUI had exactly one anchor year.

**Key evidence**: `[TASK-MULTI-ANCHOR]` — a sweep applying the GUI's own listing rule
(`classify_urgency(...) is not None`) to **both** sides, over 64 bundled species x 6 frost
dates x every 10th day of 2026 (222 cases):

```
(todo, frost date, day) cases: 222
missed by the GUI on master : 1849
missed by the GUI after fix: 0
tasks the GUI now lists that the 90-day agent window did not: 0
```

Harness: `scripts/measure_task_window_sweep.py` (committed with this case). It
prints the same three figures under its own labels — `cases swept`,
`missed by the GUI now`, `listed now but not by the agent` — not the labels
used above, which were written for readability. The first number to print was **0 surplus**, not 0 missed. Without it you cannot tell a
correct fix from one that simply lists everything — and this bug's fix passes straight
through the exact place that mistake is made: the shared date-window path runs with
`actionable_only=False`, so a wrapper that forgets to re-apply its own filter turns the
Tasks tab into the next decade. That mistake actually happened during the work (an empty
task list and a blank Gantt) and was caught only because the surplus count was asserted.

**Root cause**: three surfaces each built their own list. The Tasks tab and the dashboard
passed the snapshot to `generate_all`, which anchors on `state.year` alone; the Gantt went
further and re-derived every bar from `self._last_frost` plus the raw species offsets — a
*second* implementation of "offset to date" — the agent's `generate_for_date_window` and the dashboard's `generate_all` both *call* `generate_calendar_tasks` rather than reimplementing it, so the generator itself is the first implementation and the Gantt's re-derivation the second; the old count included the callers. `generate_for_date_window` (the engine
behind the agent's task tools) was already correct.

**Fix**: one shared entry point, `task_generator.generate_actionable_for_surface`, which
*wraps* `generate_for_date_window` (does not reimplement it) and re-applies the GUI's
urgency filter at the edge. The Gantt consumes the generated windows instead of
recomputing them. ADR-029 addendum.

**Lesson**: **two surfaces calling the same generator can still disagree about the inputs
they hand it.** The functions were shared; the arguments were not. Find that class of bug
by comparing the two outputs under one rule applied to both, and always print what the fix
*added* as well as what it removed — for a "we were hiding too much" bug the added count is
the one that catches the over-correction.

---

### Case: a date field that reformatted for display corrupted saved plans

**Symptom**: the planting calendar's propagation editor moved each displayed step date into
the current year, start and end independently ("for readability"). A step crossing New Year
was persisted into the `.ogp` as `start 2026-12-24 / end 2026-01-22` — an inverted step —
and `compute_propagation_plan` applied stored overrides verbatim, so the corruption was
permanent for any plan already saved. 1,036 (species, frost-date) pairs in 2026 had at least
one such step.

**Wrong theories**:
1. *The defect is in the writer, so fixing the editor repairs existing files.* No — the
   reader applies the stored pair without validation, so a file written by the buggy build
   stays wrong forever. The two halves have to be fixed separately, and only the writer fix
   is invisible in a fresh plan.
2. *The helpful repair is to swap the pair on load.* That silently rewrites what the user
   typed; if they meant an overnight or wrap-around step, we have corrupted their intent.
3. *It is only a display issue because the stored value is what the user sees.* The stored
   value is what every other surface reads (the Gantt's propagation sub-row, the dashboard,
   `get_tasks`).

**Key evidence**: `[TASK-PROP-EDITOR-YEARS]` — the repro is the *stored dict*, not the
screen. Leek with a 1 April last frost and no override has an indoor sowing of
24 Dec 2025 - 21 Jan 2026; the editor showed "24 Dec - 21 Jan" and moving the end by one day
stored `{'start': '2026-12-24', 'end': '2026-01-22'}`. The 29-February corners were the
tell that the year rewrite was conditional: `except ValueError: display = s` kept the REAL
year for the 29-Feb date while the other date moved into the current one, so the step
stretched or inverted *depending on leap-ness* — a shape no single "wrong year" theory
predicts.

**Root cause**: the populate method rebuilt the displayed date from month/day rather than
using the step's date. Two further defects sat in the same 40-line function and were
covered by the same tests: the editor wrote an override on every `dateChanged` and ran the
calendar's full `refresh()` each time — one gesture, one write and one refresh per keystroke, and the refresh re-fetches the weather. It now commits **once per gesture**. (Not an *undo* step: a propagation override never reaches the `CommandManager`, so it is not undoable at all — a pre-existing gap this change does not close.),
and the species detail line was five hardcoded English f-strings the i18n gate is
structurally blind to.

**Fix**: the editor shows each step's real dates; an override whose end precedes its start
is **ignored on read and refused on write**, leaving the stored value in the file untouched.
The commit is now once per gesture (600 ms debounce plus immediate on focus-out, mirroring
`properties_panel._TEXT_COMMIT_DEBOUNCE_MS`).

**Lesson**: **a date field that reformats what it holds for display is a data-corruption
site.** Before choosing a repair for a persisted bad value, find out who reads it back: the
writer's bug and the reader's missing validation are two defects, and fixing only the writer
leaves every existing file broken. When the value is untrustworthy, *ignoring* it (keeping the
file intact) beats *repairing* it (rewriting the user's intent).

### Case: the wrapper broke the tabs it was written to fix

**Symptom**: two regressions in the *same eight lines* of the new
`generate_actionable_for_surface`, both invisible to the suite that shipped the
multi-anchor fix. (1) Opening either task tab on a plan with an **undated** manual
task raised `TypeError: '<=' not supported between instances of 'NoneType' and
'datetime.date'` — a state the agent's own `add_manual_task` produces on purpose
("omit `date` for an undated task"), so an agent-written plan bricked both tabs
on next open. (2) A manual task due in **December** disappeared from the Tasks tab
when read in **June**.

**Wrong theories**:
1. *The multi-anchor change broke the urgency filter.* No — the filter was correct;
   it was being applied to tasks it was never written for.
2. *`classify_urgency` should tolerate `None`.* Possible, but it papers over the
   real mistake: manual tasks should never reach an urgency test at all.
3. *The date-window span is too narrow.* This was the actual second cause, and it
   only appeared *after* fixing the first: narrowing the span from ±10 years to the
   urgency window (a ~50x speedup) silently dropped absolute-date manual tasks
   before the exemption could apply. A fix for one P0 caused a second P0.

**Key evidence**: `[TASK-MANUAL-REGRESSION]` — the same plan, the same date, the
two code paths:

```
master  (generate_all): ['far', 'longpast', 'undated']
branch  (surface fn)  : ['undated']          # then TypeError once more cases run
```

and the crash, from the real widget, not a unit test:

```
TasksView.__init__ -> refresh() -> generate_actionable_for_surface
  -> task_generator.py:757 -> task_generator.py:151
TypeError: '<=' not supported between instances of 'NoneType' and 'datetime.date'
```

The lesson about *where* to look: the reviewer's reproducer was "add one undated
manual task". My own tests for the multi-anchor change had all used **frost-derived**
tasks, because that was the thing under change. The bug lived in the population I
never varied.

**Root cause**: the wrapper assumed every generator below it behaves alike. Two
deliberately do not — `generate_manual_tasks` documents "a manual task is never
filtered out by urgency", and `TasksView._bucket` re-derives a bucket for exactly
those cases including a `no_date` bucket that exists only for undated tasks. The
wrapper imposed a fourth rule without reconciling the three below it.

**Fix**: undated tasks pass through unclassified; manual tasks are merged in from
their own generator (they carry absolute dates, so the date span drops them) and
are never urgency-filtered. Three regression tests, run against the **real
`TasksView`**, not the helper.

**Lesson**: **a shared generator's flags and its filters are inherited by every
caller.** When you wrap one, enumerate what sits below it before applying a uniform
rule — and when a bug appears only in a population you did not vary, widen the
fixture before you widen the theory. A speed fix that narrows an input span is a
behaviour change and must be swept like one.

### Case study: a dead status route hid two untranslated strings until it was fixed

**Symptom.** #415 made the propagation-date refusal "refuse visibly". It delivered
nothing: the field snapped back and no message appeared anywhere.

**Wrong theories, in order.** (1) The panel was not emitting the rejection. (2) The
slot was not connected. (3) The signal had no receiver. All three were verified
correct — the emit fired, the slot ran, and the message was constructed.

**The key log line.** `[STATUS] set_status_message -> parent=QSplitter has_statusBar=False`,
which is what made it obvious the route terminated at a widget that cannot display
anything. Twenty-four other callers shared that route.

**Root cause.** `set_status_message` did a parent lookup instead of a signal. The
canvas's parent is the splitter, so the `hasattr` guard made the miss silent.

**Lesson, and the part worth keeping.** The interesting half is not the bug — it is
that the bug was a *hiding place*. A dead code path looks harmless, and fixing it
does not reveal what it was hiding; it publishes it, to every user, at once. Two of
the twenty-four suppressed strings were not translatable, and a German user saw
`Calibration complete` in English. Before repairing a silent no-op, enumerate what
it was suppressing. The guard that followed walks every `set_status_message` call
site by AST — because a bare literal is invisible to any scan for translations, and
that is how this survived one round of scanning.

Related: §11.4.6, `tests/unit/test_status_literals_are_translated.py`.


## Case study: source version changes stale a locked release environment (#404/#399)

**Symptom:** a mechanical version-only source edit failed the proposed lock-freshness gate.
**Initial assumption tested:** version sync could continue to change only the two source
version declarations. **Key evidence:** the temporary-copy probe returned a stale-lock error
from `uv lock --check --offline`; `uv lock --offline` changed the editable project's version
while preserving third-party selections. **Root cause:** the project version is lock metadata.
**Fix:** prepare_version_sync stages source, native lock and export together, compares complete
third-party package records, and writes only with --apply. **Lesson:** prove metadata-only
changes against the actual install path. The subprocess regression covers dry-run nonmutation,
apply, export agreement and idempotent reruns; no remote production merge is part of this test.


## Case study: clean checkout and malformed-report checks expose false confidence (#404/#402)

**Symptom:** the initial local lock check passed, but the reviewer's fresh Windows checkout
failed it. **Assumption refuted:** a byte comparison passing in the developer working copy
proves portability. **Key measured evidence:** `[LOCK] checkout CRLF: 1857 export CRLF: 0
normalized equal: True`. Git autocrlf transformed a generated artifact. **Fix:** LF attributes
for uv.lock and pylock.toml; rerun the real CLI in a fresh checkout.

The same review's malformed coverage probe declared two statements with one covered, but
repeated a covered line eight times: the old aggregation reported 8/9 and passed an 80% floor.
**Root cause:** counting XML elements without checking file/line identities or supplied totals.
**Fix:** refuse duplicate files/lines and contradictory totals before aggregation, with an
actual subprocess refusal test. A successful write test also does not prove rollback: an
injected failure on the second version-sync file now verifies the first file was changed and
all four inputs were restored. **Lesson:** measure fresh checkout behavior and adversarial
report shape as well as ordinary tool output; keep temporary diagnostics out of commits.


## Case study: offline version sync needs no universal-resolution cache (#399/#404)

**Symptom:** Windows sync tests passed, while the first locked Linux suite failed its sync
subprocess. **Assumption refuted:** installing the lock necessarily primes all metadata that
an offline re-resolve needs. **Key measured evidence:** `[OFFLINE-COLD] 1` reported PyQt6 not
found in the cache for a Windows/Python >=3.15 resolution split; `[CHECK-COLD] 0` followed by
`[OFFLINE-AFTER-CHECK] 1` proved a freshness check alone did not prime that metadata.
**Root cause:** changing the editable project version invalidated the lock and triggered a
universal re-resolve; current-platform installation does not cache every other platform.
**Fix:** stage only the editable project's lock version alongside both source declarations,
then run native uv lock validation offline and regenerate the export. Compare full third-party
records before applying. **Lesson:** test cache independence explicitly. The real subprocess
sync test uses an empty UV_CACHE_DIR and passes on both Windows and Linux; underlying uv
stderr is now reported on failure. Supported-Python metadata and dependency selections stay
unchanged. No temporary instrumentation remains in production scripts.


## Case study: hosted dependency updater lags the pinned tool (2026-10-09)

**Symptom:** project CI and release succeeded, but Dependabot could not prepare the newly
reported setuptools security update. **Assumption refuted:** hosted update tooling can run
the same uv version as the project runners. **Key log:** `tool_version_not_supported`
reported detected uv `==0.12.23` and supported uv `0.12.18` in
[run 37951191628](https://github.com/cofade/open-garden-planner/actions/runs/37951191628).
**Root cause:** the hosted updater's supported tool version lagged the approved exact pin.
**Disposition:** retain reproducible installation and keep the moderate setuptools advisory
open for a separately reviewed manual setuptools/lock update; no remediation is claimed.
**Lesson:** check updater compatibility when introducing a lock/tool pin. A green project
workflow does not prove automatic security updates work. See risks sections 11.2 and 11.4.


## Case study: Unicode wiki diffs fail in a Windows pipe (fixed 2026-10-09, issue #417)

**Symptom**: the real comparison CLI returned the expected drift exit code, but its UTF-8 subprocess reader failed to decode stdout. A longer diff also failed while printing a check mark.

**Theories entertained (wrong)**: none. The captured traceback and stream instrumentation identified the encoding directly.

**What instrumentation revealed** (real CLI against the existing wiki):

```text
[WIKI] stdout_encoding=cp1252 utf8_mode=0
[WIKI] non_utf8_byte_0x96=True
```

The next print failed because the code page could not encode a check mark.

**Root cause**: redirected Python stdout used the Windows system code page, while the parent correctly expected UTF-8. UTF-8 file I/O alone did not set console encoding.

**Fix**: `scripts/sync_wiki.py` configures its CLI stdout and stderr as UTF-8 before printing. Temporary diagnostic prints were removed.

**Lesson**: specify both file and CLI stream encoding for Unicode tooling. Pinned by `tests/integration/test_wiki_publication.py`, whose real subprocess comparisons exercise Unicode diffs without a UTF-8 environment override.


## Case study: a plant's shadow that flipped with a warning badge (Phase 17 L1.6, fixed 2026-10-11)

**Symptom**: a plant linked to a raised bed, its centre 1 cm inside the bed's east edge, stood on the bed's soil (base 38 cm in the 3D record and in the 2D shadow caster). When the companion check put the red antagonist badge on it, both read 0 — the plant dropped to the ground and its shadow lost 38 cm of base. Badge off: 38 again. No test failed.

**Theories entertained (wrong)**:
1. *"Every membership decision must ask the same point, then they cannot disagree."* That was the previous fix, and it was the cause: the lift had been given the link decisions' point.
2. *"The centre of `boundingRect()` is the geometric centre plus symmetric decorations."* True for the shadow margin, the companion highlight and the spacing ring. Not for the badge.

**What the instrumentation revealed** (a ten-line probe printing the point and both bases, run on the tree with the previous fix):

```text
[BASE] badge off: link point (699.0, 400.0)  3D base 38  2D caster base 38
[BASE] badge on : link point (700.8, 401.8)  3D base 0  2D caster base 0
[BASE] badge off: link point (699.0, 400.0)  3D base 38  2D caster base 38
```

The point moved by 1.8 cm in x AND y. Nothing about the plant's geometry had changed.

**Root cause**: `CircleItem.boundingRect()` grows towards +x / +y only while the badge shows (`base.adjusted(0, 0, overflow, overflow)`, `overflow = 0.3 * min(0.45 * radius, 12)`), so its centre moves by half of that. `footprints.bed_membership_point` is `mapToScene(boundingRect().center())` — fine for the shipped link decisions, which have always used it, and wrong as the answer to "where does this plant stand".

**Fix**: the lift asks `footprints.standing_point` — the item's stable geometric centre, the anchor of its outline and the origin of its 3D record. The link decisions keep their point; one predicate (`shape_contains`) serves both. `tests/integration/test_scene3d_base_stacking.py::TestWhereAPlantStandsDoesNotDependOnABadge` toggles the badge and compares the record, the caster and the real overlay's path; `::TestWhichPointEachDecisionAsks` pins the point of each decision on a probe where the two points differ.

**Lesson**: a bounding rect is a PAINT rect. Before using one as geometry, list everything that changes it — here a badge, a highlight, a margin, a ring — and ask whether each is symmetric. And when a refactor claims "identical behaviour" for a value that two candidates could supply, build one probe where the candidates differ: swapping them had passed all 114 related tests.


## Case study: a negative control that only CI could fail — the overlay's own echo (Phase 17 L1.6, fixed 2026-10-11)

**Symptom**: `assert controller.recompute_count == count + 4` failed with `assert 6 == (1 + 4)` in the CI Test job. The Coverage job passed on the same commit; twenty local runs passed.

**Theories entertained (wrong)**:
1. *"CI is slow; the wait of two debounce intervals was too short."* The control waits for NOTHING to happen; a longer wait can only make it fail more often.
2. *"The helper waits on a count, not on a duration, so it cannot race."* It waited for the count and then for the debounce timer to be idle — and the timer IS idle straight after a recompute.

**What the instrumentation revealed** (a probe that runs the recompute synchronously and counts event-loop rounds):

```text
[ECHO] height 75: recompute_count 1 -> 2; debounce active False
[ECHO]   rounds of processEvents until scene.changed: 1; debounce active True
[ECHO] race: recompute_count 5, debounce active False, undo done
[ECHO]   after the echo and its debounce: recompute_count 6 (the control expected 5)
```

**Root cause**: a recompute sets the shadow overlay's path. The scene emits `changed` one event-loop round later, and `changed` is wired to `SunShadowController.schedule_recompute`. That echo's recompute is a no-op while nothing changed (the key holds) — but the test's negative control makes an edit nothing announces, and an echo delivered after it carries the edit into the overlay. Locally the echo always arrived inside the helper's first 10 ms poll; in one CI job it did not.

**Fix**: the helper (`OverlayWatch.settled`) waits for the recompute count, THEN for a `scene.changed` delivered since that recompute, then for the debounce the echo starts. `tests/integration/test_scene3d_base_stacking.py::TestTheOverlaysOwnEcho` holds both halves of the race still by calling `recompute_now()` directly — the echo is then certainly undelivered — once without waiting for it (exactly one extra recompute) and once through the helper (none). With the old helper the second test fails three times out of three.

**Lesson**: "the timer is idle" is not "nothing is pending". When a system answers its own action with a signal, wait for that signal. And a race is turned into a regression by taking the event loop out of the step that hides it: run that step synchronously, and the bad interleaving is the only one there is.

## Case study: grouped guild navigation test picked a child instead of the group (F1/F2)

**Symptom.** A grouped-centre diagnostic assertion passed alone and failed in a combined run.
**Wrong theory.** The coordinator had failed to remap the centre to its enclosing group.
**Evidence.** `[GUILD-GROUP] selected` printed a `GroupItem` plus selected `CircleItem` child wrappers; their order varied. `centre.parentItem()` and the diagnostic agreed.
**Fix.** Address the group through the centre's actual parent, never `scene.selectedItems()[0]`. A second idempotence assertion printed `[GUILD-REFRESH] changed keys ['metadata']`: serialization stamps `modified` on every call. Compare content after removing only that volatile timestamp.
**Lesson.** Inspect framework state before changing correct production logic. Keep selection/serialization tests independent of unspecified ordering and wall-clock stamps. All temporary prints were removed.

## Case study: guild previews and deferred navigation outlive a document (F1/F2, 2026-10-11)

**Symptom.** Independent review reproduced a deleted-wrapper exception when a plan was cleared while its guild preview was open. A pending sidebar click selected an object in a newly loaded copy of the plan.
**Wrong theories.** None adopted; the old branch was exercised directly before changing the lifecycle contract.
**Evidence.** A temporary probe against the second review snapshot printed `[GUILD-LIFECYCLE] markers_after_clear 4`, followed by `RuntimeError: wrapped C/C++ object of type QGraphicsEllipseItem has been deleted` in `clear_preview()`. The same probe printed `[GUILD-NAVIGATION] selected_after_load 1` when the replacement document reused the original UUIDs. The final regression passes after the fix; all probe prints and files were removed.
**Root cause.** A UUID guards object identity within a document, not across document replacement. Preview wrappers also outlived the C++ objects owned by the scene.
**Fix.** Close the picker on `document_replaced` before scene teardown, invalidate its document generation, and tolerate already-destroyed preview wrappers during idempotent cleanup. Stop pending sidebar navigation and discard queued IDs at replacement.
**Lesson.** Every deferred GUI operation needs both object identity and a document-lifetime boundary. A teardown test must cover a replacement that retains the same object UUIDs, not just an empty scene.

## Case study: the guild coordinator assumed every plant was a circle (F1/F2, 2026-10-11)

**Symptom.** The complete suite reported Qt event-loop errors in existing agent task/soil workflows even though the guild-specific tests passed.
**Wrong theories.** None adopted; the captured exception identified the accessed property before any lifecycle theory was pursued.
**Evidence.** The traceback ended at `GuildCoordinator.refresh`, reading `item.radius`: `AttributeError: 'RectangleItem' object has no attribute 'radius'`. A focused regression printed `[GUILD-GEOMETRY] plant RectangleItem has_radius False` and failed both directly and at Qt teardown before the fix.
**Root cause.** The plant ObjectType predicate is semantic; saved/imported or directly constructed plant records need not use CircleItem. Badge-signature calculation unnecessarily inspected geometry even for unassigned plants.
**Fix.** Skip badge geometry for plants with neither a missing-role status nor an existing badge. For a badge that needs updating, use the item's rectangle or bounding rectangle, retaining the circle radius where provided. The regression also pins a rectangular centre's badge and unchanged serialized geometry.
**Lesson.** A semantic type predicate does not prove a concrete graphics-item class. Run the complete suite to exercise representations absent from the new subsystem fixtures. The temporary print was removed.

**Follow-up: imported polygon centres.** Review then exercised the real save/load/picker path, not only badge refresh. A temporary regression printed `[GUILD-CENTRE] loaded_type PolygonItem eligible_index 1`; Insert refused with `PolygonItem object has no attribute rect`. An initial probe omitted a layer and correctly found no eligible centre; the decisive probe persisted a valid visible/unlocked layer. `guild_plant_bounds()` now supplies base-shape bounds to existing-centre placement, whole-layout preflight, preview and badges. Polygon/path bounds exclude painted shadows and cosmetic children. Round-trip insertion and exact undo restoration are pinned at 0?, 45? and 215?, including the centre-relative mature-spacing layout. All probe prints were removed.

## Case study: sun self-shadow and old-document heatmaps (#314/#428, 2026-10-12)

**Symptom.** Both reference tomatoes read zero hours, and a heatmap worker finishing after New/Open/recovery repainted the replacement plan.
**Wrong theories.** The centre-lookup acceptance assumption was rejected by the measured self-shadow probe. No alternative solar formula, date owner or per-caller reset was adopted. Date-only clearing and `is_running` checks do not establish document ownership.
**Key evidence.** The planning probe recorded `north=0 h south=0 h` with all casters and `north=0 h south=16.5 h` excluding each receiver only. Six deterministic controlled-worker regressions failed on `assert not heatmap.heatmap_visible()` with actual True before the reset fix; malformed-load preservation already passed. Queued timing waits for run() to return without delivering success to the GUI, proving thread completion is not queued-signal completion.
**Root cause.** A solid plant shadows its own ground centre. The old controller lacked the canonical document-reset subscription and result-generation/signature ownership checks.
**Fix/lesson.** Retain the displayed grid policy; accumulate sparse owner-aware receiver sun in the same explicit worker. Reset on `CanvasScene.document_replaced` before teardown, reject stale result ownership and retain the worker until finished. Test missing/stale values as unavailable, not zero/pass; compare against the independent point reference and measured constants. General Diagnostics needs one publisher for all cached producers. No debug instrumentation remains in committed application code.


## Case study: sun badge footprint, malformed species and collected observers (F3, 2026-10-12)

**Symptom.** Review found an L-shaped imported plant's badge outside its footprint and a selected legacy tree raising in the refresh timer. The complete suite also caught an exception during delayed QObject destruction.
**Wrong theories.** None adopted before reproducing the exact shape, accepted metadata, and captured teardown traceback.
**Evidence.** The imported/grouped regression failed `path.contains(QRectF(1189, 1319, 22, 22))`; accepted string/list species metadata failed at `species.get` with AttributeError. The suite traceback identified `disconnect -> Channel.disconnect: ValueError("listener is not connected")`. All regressions pass after correction.
**Root cause.** Bounding rectangles contain empty space in concave footprints. Evaluation and canopy paths normalized species differently. A weak observer can be pruned during cyclic collection before Qt emits destroyed.
**Fix.** Fit the complete badge rectangle inside the undecorated QPainterPath, normalize species once for both consumers, and make destruction cleanup idempotent for an already-removed subscription. Preserve navigation and item geometry across grouped save/load.
**Lesson.** Test actual containment rather than rectangle placement, exercise accepted legacy metadata, and allow both Python collection and Qt destruction to own cleanup without raising.

## Case study: every plant in a raised bed had "too little sun" — the sample point was inside the bed (US-F3 x base stacking, found 2026-10-12 while merging v1.30.1 into Phase 17 L1)

**Symptom**: none reported — the feature had shipped the same day with its reference plan
green (a tree and two tomatoes: 0 h north, 16.5 h south). The merge brought it together with
the rule "a plant in a raised bed stands on the bed's soil", and the coordinator asked one
question before any code was touched: does a raised bed shade the tomato standing on it?

**Wrong theories**: none were needed; one was avoided. "The base rule will fix it" — lifting
the plant's own solid by 38 cm changes nothing for the plant: its own solid is left out of its
estimate anyway.

**Key evidence** (a probe test on an export of `origin/master`, the real window, the real
worker, Berlin, 21 June 2026, nothing else on the plan):

```
PROBE | open ground                  | hours=16.5 | record=None                    | badge=False
PROBE | on the 40 cm bed             | hours=0.0  | record=sun_mismatch:too_little | badge=True
PROBE | on the 5 cm bed              | hours=0.0  | record=sun_mismatch:too_little | badge=True
PROBE | in a bed, not linked         | hours=0.0  | record=sun_mismatch:too_little | badge=True
```

**Root cause**: the estimate samples the GROUND cell under the plant's centre and leaves out
the plant's own solid. A raised bed is a solid too, its footprint contains that cell, and a
solid's shadow polygon includes its footprint — the point is "shaded" in every sample of the
day. The reference plan has no bed on it.

**Fix**: the receiver names the soil parent whose solid it stands in
(`SunReceiver.stands_on` ← `ui/canvas/footprints.standing_parent`: linked, visible, a
soil-capable solid, the centre inside — the membership half of the base rule the casters and
the 3D records already used), and that caster is spared for this receiver like its own.
After: 16.5 h on the bed; 10.5 h for a plant on the ground 10 cm north of the bed (the bed
still shades what is beside it); a 3 m wall south of the bed takes exactly the hours it takes
from the same plant with the bed removed. The first cut asked "is the plant LIFTED?" (base >
0) and would have left a plant in a 2 cm edging at 0 hours: a solid can cover the point
without lifting anything — the question is "is the plant in the parent's solid?".

**Lesson**: **when a sample point is "under" an object, list everything else that is under
the object.** And **try a feature first on the plan it is for** — a sun-requirement warning
is for vegetable gardens, and a vegetable garden is raised beds; the reference plan was a
tree. A merge is a second chance to ask the question the feature's own tests did not.

## Case study: a broken shader failed the render, and the run's own summary counted 0 Qt errors (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: the positive control "a broken shader fails the render" did what it should: the
render raised `RenderError` and the driver exited with its error code. The same run's summary
(`result.json`, `qt_messages.counts.error`) said 0. The frame's own report listed the shader
errors; the run's report had never heard of them.

**Theories entertained**: none worth the name, and no instrumentation was added — say so
rather than dress it up. The cause was found by reading the two places that install a Qt
message handler. The entry is here because the SYMPTOM is the kind this skill exists for (a
count that contradicts an exception raised a line earlier), and because the tempting first
theory — "the summary is written before the error arrives" — would have sent the search into
the order of events, where nothing was wrong.

**Key evidence**: the two recorders themselves. `render_records` creates a `QtMessages`
recorder for ONE frame and installs it with `qInstallMessageHandler`; the render driver had
installed one for the WHOLE run with the same call. The inner one held the errors, the outer
one held none.

**Root cause**: `qInstallMessageHandler` keeps a single handler per process. Installing the
inner recorder REPLACED the outer one for the duration of the frame — and a shader's compile
messages arrive during exactly that frame.

**Fix**: `qt_messages.install()` forwards every message to the handler it replaced and returns
it; `uninstall(previous)` puts that one back. Recorders nest. Inside the running app the same
chaining keeps the app's own handler hearing everything during an offscreen render. Pinned by
`tests/unit/test_quick3d_pure.py::test_nested_recorders_both_hear_an_error` and
`::test_a_recorder_listens_in_and_then_steps_aside`.

**Lesson**: **a "one per process" API turns a second listener into a replacement** — when a
count is 0 where an error was just raised, compare the listeners before suspecting the order of
events. The same shape came back twice in the same story: `faulthandler` has ONE
`dump_traceback_later` timer (a watchdog inside a watchdog cancels the outer one), and
`QLoggingCategory.setFilterRules` holds ONE rule set (a nested block must not switch the outer
block's rule off).

## Case study: a grab that returned a perfect image, and a process that was dead a moment later (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: found by an independent reviewer, not by the suite (the render tier was green):
`host.show(); host.grab()` returned a correct frame, and the process ended a moment later with
exit code 3, `0xC0000005` or `0xC0000374` — in whatever ran next. 5 of 5. No Python exception
anywhere, so no `pytest.raises` could ever have seen it.

**Wrong theories** — all mine, and three of them were written into the code or the docs:

1. *"Visible" is the condition for a frame.* `grab()` guarded on `isVisible()`. Between
   `show()` and the first expose a window is visible and has no scene graph.
2. *A never-shown host that took its one frame can be shown afterwards.* The error message for
   the second hidden grab recommended exactly that. It is the second killing order.
3. *The L0 run's "access violation in `grab()`" belongs to the sleeping-display family.*
   Stated in the risk log without evidence.
4. *(While building the positive control)* "the two orders no longer kill" — the control
   survived 6 of 6.

**Key evidence**: Qt's own predicates, printed after every step, ONE CALL ORDER PER CHILD
PROCESS (a death is then an exit code instead of the end of the test run):

```
                         visible exposed scene-graph
new                         F       F       F
show()                      T       F       F      <- grab here: good image, dead process
one processEvents()         T       T       T
hide()                      F       T       T      <- still "exposed" until the loop ran
hide() + events             F       F       T
minimised                   T       F       T
```

For theory 4: the control returned from its function, its host went out of scope, and Python
destroyed the `QQuickView` BEFORE the event loop ran again. With the host kept alive across the
next second of event loop, the same script died 3 of 3 on the GPU and 3 of 3 on WARP.

**Root cause**: `grabWindow()` on a window that has no scene graph renders one throwaway frame
and tears the scene graph down again. For a window that is never shown, that is the one
offscreen frame it has. For a window that is shown — or is shown afterwards — the window's own
first expose then meets what the grab tore down. The condition is
`isSceneGraphInitialized()`; `isVisible()` is neither necessary nor sufficient.

**Fix**: `Quick3DHost` is a state machine over Qt's predicates (new / starting / live / hidden
/ spent / closed); every call answers for the state or raises `HostStateError`; `wait_ready()`
pumps to the first expose and reports. The tests run one call order per child process and take
"the last line is `END`" as survival; two controls do the forbidden thing on the raw view and
must die (`tests/integration/test_quick3d_lifecycle.py`). *This fix was itself incomplete —
three predicates were too few, and the tests judged the host by its own word: the case study
"a state machine that was right on Windows" below.*

**Lesson**: **when the failure is a dead process, the evidence channel must be another
process** — and a control must keep alive the thing whose death it demonstrates. And print the
engine's own predicates before choosing one by its name.

## Case study: a `hide()` that never returned — a Python Qt message handler, Qt's render thread and the GIL (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: found by the second independent review, not by the suite. The engine host had a
"watch" for a shown view's errors: a recorder installed with `qInstallMessageHandler` for the
host's lifetime. With it, `host.hide()` — and so `close()` — sometimes never came back; with a
debug category switched on, 5 of 5. And the self-test's watchdog, armed for exactly this kind
of hang, wrote its stack dump and **the process stayed alive**.

**Wrong theories** — the first is in the round-1 code and docs, in my words:

1. *"The recorder takes a lock and never raises, so it is safe to call from Qt's render
   thread."* Thread-safe is not the question. The question is which lock the CALLER holds.
2. *"`faulthandler.dump_traceback_later(exit=True)` needs no GIL, so the exit is certain."* The
   dump needs no GIL. The exit is `_exit`, which on Windows is `ExitProcess`.
3. *(while fixing)* "Then end the process from a native timer thread." `ExitProcess` from
   there hangs the same way; `TerminateProcess` on itself works, with an exit code that is
   not ours.
4. *(in my own fix)* "A supervising process that waits on the process and on a release
   event." It would have killed a process that had FINISHED its block (below).

**Key evidence**: the watchdog's own dump of the control that reproduces it — two threads,
and the one that is NOT in Python is the telling one:

```
Timeout (0:00:04)!
Thread 0x00001dd0 (most recent call first):
  <no Python frame>                         <- Qt's render thread: about to call the Python
                                               handler, waiting for the GIL — no frame yet
Thread 0x0000c45c (most recent call first):
  File "…/ui/view3d/quick3d/host.py", line 550 in hide     <- the GUI thread: inside
  File "…/quick3d_lifecycle_child.py", line 771 in deadlock   QWindow.hide(), holding the GIL,
  …                                                           waiting for the render thread
```

and one line of Qt's own log, read from stderr (`QT_FORCE_STDERR_LOGGING=1`,
`QT_LOGGING_RULES=qt.scenegraph.general.debug=true`): `threaded render loop` — on Direct3D 11
(GPU and WARP) and on xcb + OpenGL. For theory 2: the process list, a minute after the dump.
For theory 4: a child whose block is `pass`, sleeping six seconds after it — exit code 1.

**Root cause**: Qt Quick renders a shown window on its own thread. Qt's message handler is
process-wide; PyQt calls a Python handler under the GIL on whichever thread emits. The GUI
thread holds the GIL while it is inside a Python-called Qt function; `hide()` waits there for
the render thread; the render thread emits a message and waits for the GIL. Then: `_exit` =
`ExitProcess` runs DLL detach code that waits for those threads. And the supervisor: a block
that ends before the supervising process has started signals and DESTROYS the release event;
the late supervisor found no event, waited on the process alone, and terminated it at the
deadline.

**Fix**: no message handler beside a shown window, ever — the watch is gone; a shown host
reports what Qt delivers on the GUI thread (`Quick3DHost.health()`: the QML engine's
`warnings`, the window's `sceneGraphError`, a frame count, the latter two connected queued).
A recorder only around rendering on the calling thread, and it counts messages that arrive
elsewhere. The watchdog got a second line of defence — another process that calls
`TerminateProcess(handle, 1)` — for which a missing release event means "released", and which
identifies its process by pid and creation time. Pinned by controls that must fail the old
way: `test_a_python_message_handler_beside_a_shown_window_deadlocks`,
`test_the_supervised_watchdog_ends_the_deadlock`,
`test_the_supervisor_leaves_a_process_alone_whose_block_finished_first`.

**Lesson**: **the GIL is a lock, and a callback from a foreign thread acquires it** — before
handing Python to another thread's callback, ask what the thread that holds the GIL may be
waiting for. And a watchdog is only as good as its exit: test it against the hang it is for,
not against `time.sleep`. And every "wait for A or B" needs an answer for "B is already
gone".

## Case study: a state machine that was right on Windows, and a judge that asked the suspect (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: two findings of the same review. (1) The Linux CI job was red: a call order the
lifecycle matrix PINNED AS SAFE — `show(); hide(); grab()` — segfaulted one event-loop pass
after a correct grab. (2) In a splitter pane dragged shut the host said "live" and handed out
a blank frame, a bogus pick and a projection of (0, 0) — and the matrix was green.

**Wrong theories**:

1. *"No scene graph and not visible means never shown."* Measured on Direct3D 11, where that
   order survives. On xcb the window has a platform window by then, and that is what counts.
2. *"Scene graph, visible and exposed means a frame can be had."* A collapsed pane is all
   three and 0 px wide.
3. *"The matrix checks every answer."* It checked every answer against the state THE HOST
   reported. A host that reports the wrong state passes.

**Key evidence**: Qt's facts printed per step — this time with the geometry, and with the
platform-window event:

```
                              surface visible exposed scene-graph  window   root item
show(); hide() (no event)        1       F       F       F        320x240   320x240   <- "new"? xcb says no
pane collapsed                   1       T       T       T          0x500   447x500   <- visible AND exposed
pane reopened (no event)         1       T       T       T        447x500     0x500   <- the scene lags one pass
1 px wide                        1       T       T       T          1x500     1x500   <- draws no 3D at all
```

and the same matrix run in a container with the CI job's stack: the four killing orders die 5
of 5 on xcb.

**Root cause**: three predicates named after what they sound like, chosen on one platform; and
a test that derived its expectation from the output of the code under test.

**Fix**: the state is a pure function of nine facts (ten since the case study after next;
`quick3d/lifecycle.py`): "new" = Qt never
created a platform window (the `PlatformSurface` event; PyQt6 does not bind
`QWindow.handle()`); "live" also needs an area of 2 × 2 px and a root item that has the
window's size. The judge has a table of what a TRUTHFUL host must answer per step and checks
the pixels; a control hands it the raw view's blank frames and requires it to reject them.

**Lesson**: **a measurement belongs to the platform it was made on** — "harmless, also
measured" needs the platform's name next to it, and the other platform's control. And **an
oracle must not be computed from the answer it judges**: if the expected value comes out of
the code under test, the test can only fail when the code disagrees with itself.

## Case study: "ready" — and the next grab was an image of the old size: a resize that arrives inside the call (Phase 17 L1.2, fixed 2026-10-11)

**Symptom**: after `showFullScreen()` — of a standalone view, or of the main window that embeds
it — `host.wait_ready()` returned True and the very next `host.grab()` raised `EngineError: …
Qt rendered a 320 x 240 px image for a 5120 x 1440 window`. 20 of 20 in the review, on the GPU
and on WARP. The suite was green on three platforms; the lifecycle matrix had no full-screen
row, and `application.py` calls `showFullScreen()` on the window the 3D workspace is embedded in.

**Wrong theories**:

1. *"After every resize the QML root item lags the window by one event-loop pass — so a root
   item of the window's size means the host has caught up."* The rule of the fix before, by then
   written into nine documents. True for a splitter move; false here.
2. *"Then wait for `frameSwapped` after the resize."* That signal is queued from the render
   thread: one emitted BEFORE the resize can arrive after it. (And with the display asleep a
   window presents one frame and then none.)
3. *"`wait_ready()` taking a second after a resize is my wait loop."* It was ONE
   `processEvents()` pass, inside Qt's own expose handling.

**Key evidence**: an event filter on the view. Per call: what Qt delivered INSIDE the call,
then what each later pass delivered — with the size of a raw `grabWindow()` beside it. (The
`state=` column is the fixed host's; before the fix the first line read `live`.)

```
showFullScreen: sync events [Resize(5120x1440) Move State] window 5120x1440 root 5120x1440 state=starting raw grab 320x240
     pass 1: [Expose(exposed)] window 5120x1440 root 5120x1440 state=live raw grab 5120x1440
showNormal: sync events [Resize(320x240) Move Expose(exposed)] window 320x240 root 320x240 state=live raw grab 320x240
showMaximized: sync events [-] window 5120x1369 root 320x240 state=starting raw grab 320x240
     pass 1: [Resize(5120x1369) Move State Expose(exposed)] window 5120x1369 root 5120x1369 state=live raw grab 5120x1369
window.showMaximized: sync events [-] window 447x500 root 447x500 state=live raw grab 447x500
     pass 1: [Resize(2557x1369) Move Expose(exposed)] window 2557x1369 root 2557x1369 state=live raw grab 2557x1369
```

(The last pair is the embedded view while its main window is maximised: until the layout ran
NOTHING has changed for it, and it is — truthfully — live at its old size.)

**Root cause**: `showFullScreen()` delivers its resize synchronously — window and root item
agree before the call returns — while `grabWindow()` on a shown window renders into the swap
chain as it is, and Qt resizes the swap chain only when it handles the NEXT expose. The state
machine had no fact for "the render target has the window's size", so the host read "live" in
between. In every line above the grab is wrong exactly between a `Resize` event and the next
`Expose` event of the exposed window.

**Fix**: that fact, latched from the window's own events by the filter that already latched "a
platform window was created": `Resize` clears it, the next `Expose` of the exposed window sets
it, and "live" needs it. `wait_ready()` delivers what is pending once for ANY visible host
before it answers. A grab whose image has another size after all raises `HostStateError` — a
state, like every other "not now" — instead of `EngineError`. And the contract moved into ONE
docstring (`quick3d/lifecycle.py`); the nine copies had drifted apart. *(Review round 4: the
latch was the next defect — "a host that waited for a message that never came", below. The
size check stayed; the fact went.)*

**Lesson**: **"one event-loop pass" is not a unit.** Before writing a rule about "after a
resize", print what each CALL delivers before it returns — per call, per platform. And when a
hand-written matrix of orders has missed the failing order twice, **add an order nobody wrote**:
a seeded random walk whose judge knows only what Qt said about the window (it found nothing
more on the dev box — and on a 1024 px CI runner it found the defect of this very fix).

## Case study: a healthy block was terminated four seconds in — and another block's log said why (Phase 17 L1.2, fixed 2026-10-11)

**Symptom** (the review's measurement, never seen in a test): two supervised watchdog blocks in
one process. Block A, 1 s budget, an empty body. Then block B, 60 s budget, healthy. The process
was terminated 4.1 s into B — and the line that said why, "block A was still alive …", stood in
A's log.

**Wrong theory**: *"A missing release event means the block is over — so a supervisor that
comes up late can never act."* That was the fix for the trap before (a block that finishes
before its supervisor is up). True, and not enough: A's supervisor did not find a MISSING
event. It found B's.

**Key evidence**: the sequence against the previous head — the process ends with exit code 1
after 4.7 s, and this is block A's log:

```
    0.005s [watchdog] armed=True seconds=1.0 what=block A supervisor=process 78652, ends this one 4 s from now …
          [supervisor] fired=True what=block A reason=block A was still alive 4 s after its watchdog was armed — … terminated from outside, exit code 1
```

and after the fix — two supervising processes, each released by its own block, both gone with
exit code 0:

```
    0.009s [watchdog] armed=True seconds=1.0 what=block A supervisor=process 66160, ends this one 4 s from now …
    0.159s [watchdog] released=True what=block A supervisor_exit=0
    0.169s [watchdog] armed=True seconds=60.0 what=block B supervisor=process 80200, ends this one 63 s from now …
   20.189s [watchdog] released=True what=block B supervisor_exit=0
```

and the pin for it failing (the process ends with exit code 1 instead of 0) as soon as the
nonce is taken out of the event's name again.

**Root cause**: the event was named after the PROCESS — pid and creation time — which the next
block of the same process has too. "An event that exists is mine" was never true.

**Fix**: a random nonce per block in the event's name, handed to the supervising process on its
command line; one armed watchdog per process at a time (a second raises); and a supervisor that
checks whom it works for before it opens anything — validated arguments, its target must be its
own parent process, in the frozen build running the same image. And the gate's own blind spot:
a supervisor that could not be started used to be logged as `supervisor=none` while the
self-test passed; on Windows the self-test now FAILS without one.

**Lesson**: **something that may kill names its target by what nobody else can have** — a random
name it was handed — never by what the next user will have too. And **a safety net is a
subsystem**: if nothing checks that it started, the day it cannot start looks like every other
day until it is needed.

## Case study: a host that waited for a message that never came — red on the CI runner's small screen, green on the dev box (Phase 17 L1.2, fixed 2026-10-12)

**Symptom**: `Render 3D (windows-latest)` red, one test: the story's own seeded walk, 7 problems
in 252 looks. Three looks where Qt showed the pane and the host never came up, and
`wait_ready()` taking its whole 5 s three times in a row on a 2 × 60 px pane. The same commit:
green on the RTX 4070, green on WARP, green on xcb in a container, 99 of 100 each.

**Wrong theories**:

1. *"A grab has the wrong size exactly between a `Resize` event and the next `Expose` — so
   'live' waits for that expose."* The fix of the round before (the case study above the last
   one), measured in every order anyone had written. It made an OS paint message a condition
   of a state.
2. *"Then name the place: a state for 'no part of the view is on a screen'."* The review
   offered it. Measured before building it: beyond the SAME edge of the SAME screen the pane
   kept its old render target while the display slept and got the new one while it was awake
   — both ways on one day, and on WARP the new one either way. Geometry does not say whether
   Qt draws.
3. *"The local tiers pass, so it is the runner."* They passed because every window of the
   matrix fits on a 5120 px screen. The walk asked for 1203 and 1500 px wide windows on
   whatever screen it found.

**Key evidence**: the runner's own line — every fact Qt reports is in place, and the one the
host had invented is not:

```
[59] setSizes(.., 49) / pump window=[56, 701] state=starting: STUCK — Qt shows the window and the host does not come up:
     WindowFacts(surface_created=True, visible=True, minimised=False, width=56, height=701, scene_graph=True, exposed=True, root_width=56.0, root_height=701.0, target_synced=False)
```

and the events the view gets when the pane grows beyond the screen's right edge (an event
filter on the view, the raw `grabWindow()` beside it, then the FIXED host) — the same probe,
the same day, the display awake and, 25 idle minutes later, asleep:

```
grown to 137  : window 137x500 events ['Resize', 'Move', 'UpdateRequest'] exposed=True raw grab 137x500 ok; host: state=live wait_ready(5)=True
grown to 137  : window 137x500 events ['Resize', 'Move'] exposed=True raw grab 49x500 STALE; host: state=live wait_ready(5)=False
```

**Root cause**: the host had made a MESSAGE its evidence for something it can look at. Windows
sends no expose to a pane that grows where no screen is; a state that waits for one waits for
ever. And the test that should have caught it let the window system decide where its windows
were.

**Fix**: the frame is the witness. `grab()`, `pick()`, `project()` and `wait_ready()` take a
frame and compare its size with the window's, to the device pixel ("less than one pixel off"
— which round 5 found is not exact at 125 %: the next case study); another size is a refusal
and nothing is remembered. `wait_ready()` starts no delivery of events once its timeout is up
(a zero timeout runs none; it had taken 1.0 to 1.4 s), defaults to 1 s instead of 10,
and answers False 0.5 s after the last sign of progress — for every cause at once. In the
tests: every window is placed on the screen on purpose; the walk runs a second time where a
1024 × 768 screen leaves the window; and the condition is MADE, not hoped for — an event filter
that eats the view's `Expose` / `UpdateRequest` / `Paint`:

```
linux: grown live/refused; shrunk live/refused; wait_ready(5) after grown: False in 0.502 s, wait_ready(60) after long: False in 0.503 s, wait_ready(0) after zero: False in 0.002 s; frames refused for their size 20
```

**Lesson**: **do not infer what you can observe** — three rounds had each added a fact to the
state (three, nine, ten), and each new fact was a new way to be wrong about the one question
that matters: is the frame right? Ask the frame. **A test must not depend on where the window
system puts a window, or on how large the screen is**: place it, and run once as on the
smallest screen you ship to. And **a condition that differs between two days on one machine
cannot be a pin**: reproduce it on purpose (here: withhold the paint events), pin THAT, and
assert only what holds on every machine for the real thing.

## Case study: at 125 % a pane got its neighbour's frame — and the judge agreed, because it used the suspect's own rule (Phase 17 L1.2, fixed 2026-10-12)

**Symptom**: none. Every tier green on three platforms and on CI. A reviewer set
`QT_SCALE_FACTOR=1.25`, made the 3D pane ONE logical pixel wider while nothing drew the view,
and asked the host for a frame: it got the frame of the pane as it had been — and a pick
against the old viewport — from a host whose contract begins "`grab()` returns the scene at the
window's current size, or it raises".

**Wrong theories**:

1. *"The size check is exact to the device pixel"* — the round before had written that, after
   replacing a tolerance of two pixels. The code said `abs(frame - logical * ratio) < 1.0`.
   That IS exact at a ratio of 1, 1.5 and 2: the three ratios in the tests.
2. *"The matrix would have seen a wrong frame: its judge compares every frame with the size Qt
   gives for the window."* The judge's comparison was `abs(...) >= 1` — the same inequality,
   written a second time. Round 1's judge had asked the suspect for its state; this one had
   copied the suspect's rule. Blind in the same place, for the same reason.

**Key evidence**: the reviewer's probe, before and after —

```
pane 442 -> 443 px: grab() HANDED OUT a 553 px frame (the frame of the 442 px pane was 553 px; a 443 px pane's is 554 px); state=live; pick -> {'hit': 'w', 'point': [-0.2, -0.0, 20.0]}
RESULT dpr=1.25: of 12 one-pixel changes with the render target behind, grab() handed out the OLD frame 0 times and refused 12 times (skipped 12)
```

and the arithmetic that says how often: of 11,993 neighbour frames (a window one or two logical
pixels beside the one asked for) 750 passed at 1.25, some at every ratio strictly between 1 and
1.5, none at 1.0, 1.5 or above.

**Root cause**: Qt sizes a render target as `QSize(logical) * ratio` — `qRound` per side. The
right frame is therefore at most HALF a device pixel off `logical × ratio`; "less than one"
leaves room for a neighbour wherever the product ends in .5 (442 × 1.25 = 552.5 → 553, and
553 is 0.75 off 553.75). Nobody had written down what "exact" was exact against.

**Fix**: the host: at most half a device pixel off. The judge: its own `qt_round`, and equality
with it — not the host's predicate. The arithmetic for every width from 2 to 3000 at twelve
ratios against `QSize * ratio` asked of Qt itself, in the default tier; one real-window row at
125 %, which first asserts with a RAW grab that the render target is behind (a row that cannot
fail proves nothing).

**Lesson**: **an oracle must come from somewhere else than the thing it judges** — from the
platform's definition, never from the implementation's tolerance. If the test and the code
share a formula, the test checks typing. And **test where rounding bites**: between the round
ratios, at the widths whose product ends in .5 — not at 100 %, 150 % and 200 %, where any
tolerance below one pixel is exact.

## Case study: 34.6 MB per reload, and nothing was leaking in Python or in VRAM — two retentions inside Qt, and a soak that could not present a frame (Phase 17 L1.3, fixed 2026-10-12)

**Symptom**: the memory soak of the 3D workspace in the real app (20 reloads of `bench_small`,
every reload rebuilding the engine scene; private bytes; Theil–Sen over reloads 11–20) read
**34.6 MB per reload** against a bound of 10. Reloads that rebuilt nothing read 0.2. The
positive control (25 MB kept per reload) read 58.8, so the instrument worked.

**Wrong theories**:

1. *"Something of ours keeps the old scene — the controller's records, the plant shape cache,
   the sink's books."* `tracemalloc` between reloads 5 and 15 of the same soak: 0.045 MB per
   reload. A weak set of every geometry wrapper ever made: 0 alive.
2. *"Then it is a D3D resource, in VRAM."* DXGI's figure for this process
   (`IDXGIAdapter3::QueryVideoMemoryInfo`): 298.1 MB before, 305.6 after the first reload, 305.6
   after the twentieth.
3. *"It is the mesh buffers — 1.5 times their size per round — and they are freed at the end of
   a presented frame, which a readback is not."* TRUE, measured in a bare host (22 MB per round
   by readback, 6.5 with presented frames) — and in the production host presenting frames
   changed nothing: 27.9 and 38.5. A cause that explains the probe and not the product is half
   a cause.
4. *"The remainder is the QML engine's garbage, it will be collected."*
   `QQmlEngine.collectGarbage()` per round: 6.1 instead of 6.3 to 7.7.

**Key evidence**: a bare `Quick3DHost`, 100 Models of 3,000 vertices (14.9 MB of buffers)
created, drawn and destroyed per round — and ONE thing changed per run:

```
VARIANT buffers        SLOPE second half -0.13 MB/round          (no Qt object)
VARIANT geometry       SLOPE second half 0.00 MB/round           (no Model)
VARIANT models_hidden  SLOPE second half 0.78 MB/round           (never drawn)
VARIANT models         SLOPE second half 22.00 MB/round (x1.48)  afterFrameEnd 0  grabs 40
VARIANT models_update  SLOPE second half 6.77 MB/round (x0.46)   afterFrameEnd 40 grabs 0   [QT_D3D_NO_VBLANK_THREAD=1]
   + embedded 6.43 · foliage material 6.60 · host.clear() 6.13 · extra frames 6.33
   + PROBE_SUN=1            18.06 MB/round          <- the production difference
   + sun, verts=300         18.19   (x12.22 of the buffers)   <- not the mesh
   + sun, verts=12000       24.59   (x0.41 of the buffers)
   + sun, no shadow casting  6.17
   + sun, releaseResources() per round   3.90 (20 rounds) · 0.85 (60 rounds)
```

**Root cause**: two things inside Qt Quick 3D, and one about the instrument. (1) Qt keeps
cached per-draw-call state for every Model it ever drew, after the Model is destroyed — about
three times as much for a Model that also casts into the sun's shadow cascades — until
`QQuickWindow.releaseResources()`. (2) A destroyed Model's mesh buffers are freed at the end of a
PRESENTED frame; `grabWindow()` never ends a frame that way. (3) The display was asleep: Windows
presented no frame at all, so every frame of every soak on this machine that night was a
readback.

**Fix**: `Quick3DHost.release_cached_resources()`; the pipeline's passes count the items whose
Models they destroyed, and the workspace releases when 64 piled up and the pipeline is quiet,
or at once at 512. The soak's child runs with `QT_D3D_NO_VBLANK_THREAD=1` and asserts that
frames were presented. After: 3.9 and 4.9 MB per reload (the large plan 5.1, WARP 7.4; 1.8
over reloads 31–60 of a 60-reload run), the control 28, the same soak with the release out of
reach 29. What is left — about 20 kB per destroyed Model — has a floor in bare Qt: 3.4 kB per
`Model` with a material created and destroyed without ever being drawn.

**Postscript — the instrument was still in the picture.** Every number of that "After" came
from a soak that READ BACK once or twice per reload, and so did the next finding built on it
("a view that presents nothing keeps every byte uploaded to it", and a rule that paced the
pipeline by presented frames). A reviewer of another story took the readback out of the loop:
flat. Here, the same twenty rebuilds without a readback in the loop: 2.0 MB per rebuild
presenting and 1.5 with the view's frames withheld (19 and 1.5 without the release); with one
readback per rebuild and frames withheld 8.5 (26 without the release). The cached state per
drawn Model was real — the bare-host rows took no readback — but the dark-view growth was
the readback's own frame, never presented and so never given back. The pacing was removed;
the rule that stayed is "nothing takes a frame from the live view, and a soak takes none
inside its loop".

**Lesson**: **shrink it until one run takes seconds, then change one thing per run** — the
whole table above cost less than the first three theories. **Scale the suspect**: three vertex
counts said "not the mesh" in thirty seconds. **A cause must explain the product, not only the
probe**: theory 3 was real and was not it. **Know what your instrument does to the thing it
measures** — a readback is not a frame the way the product makes frames; list every frame the
measuring loop itself renders and run the loop once without them BEFORE a rule is built on
the curve. And when a fix lands,
keep three numbers from one instrument: with it, without it, and a control that must fail.

## Case study: an access violation in a test that had nothing to do with the change — a Python callable on `destroyed`, and the garbage collector (Phase 17 L1.3, fixed 2026-10-12)

**Symptom**: after `connect_qobject` — "take a clock subscriber off its channel when Qt destroys
it" — was built on `receiver.destroyed.connect(<closure>)`, the suite died with
`Windows fatal exception: access violation` in
`tests/integration/test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`, a test that was
not changed.

**Wrong theory**: *"a slot was called after its receiver died"* — the very thing the helper
exists to prevent, so the helper was the last place looked at. The receiver was alive; what was
called dead was the helper's own closure.

**Key evidence**: bare PyQt 6.11, no product code, four ways to let an object with a closure on
its own `destroyed` signal go:

```
toplevel_plain   (refcount frees the wrapper)                       survived; hook ran 1 time(s)
toplevel_cycle   (wrapper in a cycle; gc.collect())                 collected 6;  hook ran 0 time(s)   <- silently never called
child_cycle      (a child of that wrapper)                          collected 7;  hook ran 1 time(s)
deferred_cycle   (Qt owns it, deleteLater() pending; gc.collect();  collected 11; Windows fatal exception: access violation
                  then the deferred delete runs)                                  File "...", line ??? in hook
```

**Root cause**: a Python callable connected to `destroyed` lives and dies with Python's idea of
the wrapper, not with the C++ object. When the wrapper is garbage in a reference cycle while Qt
still owns the object — a `deleteLater()` is pending, a parent holds it — the cyclic collector
clears the callable, and the connection stays behind in C++. Then either the signal is never
delivered (the second line), or Qt delivers it into what is left (the fourth). It surfaced in
an unrelated test because that is where the collector happened to run.

**Fix**: nothing hangs on `destroyed`. The clock's channel calls a guard that asks
`sip.isdeleted(receiver)` at every delivery and takes itself off
(`src/open_garden_planner/ui/sim_clock_subscription.py`); a test pins that the module never
names the signal.

**Lesson**: **a crash in a test you did not touch is a lifetime bug in what you did touch** —
suspect the garbage collector, and reproduce with an explicit `gc.collect()` in bare PyQt before
reading product code. **Do not hang clean-up on a QObject's `destroyed` signal from Python**:
the callable can be collected before the signal fires. Ask at the moment of use
(`sip.isdeleted`) instead of waiting to be told.

## Case study: A1 trust boundaries (#453, 2026-10-13)

**Symptoms.** Non-finite JSON reached scene preparation and could overwrite a good
plan; an image/png header allowed HTML into the cache; duplicate installer assets
selected the first entry; native Linux Qt 6.11 settings were mode 0644 under umask 022.
**Wrong theories.** No runtime hypothesis adopted before baseline reproduction.
The Windows registry sandbox failure was isolated by running the same failing-first
tests outside the sandbox; it was not treated as product behavior.
**Evidence.** The failing regression emitted `[A1-NUMERIC] invalid data reached scene
preparation`, with the load -> _prepare_scene_data stack. The save test reported
`DID NOT RAISE ValueError`; the image test returned a cached path for HTML; the
duplicate test returned a download URL. A disposable Linux Qt probe printed
`{'qt': '6.11.0', 'umask': '022', 'mode': '0o644'}`.
**Root cause.** Permissive JSON at several independent file paths, content-type-only
cache validation, unbound updater metadata/download/launch, and reliance on Qt's
default creation permissions. Conditional angle serialization could also omit NaN.
**Fix.** Shared strict/atomic plan I/O; detached journal reconciliation; a release-bound
verified installer result and pre-launch recheck; bounded image streaming plus full
decode and atomic PNG caches; Linux descriptor protection in the existing settings
factory and explicit startup refusal. Keep Windows/native stores and existing keys.
**Lesson.** Pin every bypass, not only the main caller. Finite operands can overflow;
headers are not data validation; a downloaded path is not a verification result; a
mocked Windows chmod does not establish Linux permissions. Probe logs are task
artifacts only. Pins live in the A1 unit/integration safety tests and settings isolation.

## Case study: host ICU DLL contaminates frozen WebEngine (#453, 2026-10-13)

**Symptom.** Source self-test passed, but the frozen self-test opened a missing-
procedure error while importing QtWebEngineWidgets.
**Wrong theories.** Qt micro-version mismatch remained unproven; source/frozen Qt
DLL hashes matched. A PE probe initially reported many missing Qt symbols because
pefile stopped after 8,192 exports; raising its export limit removed those false hits.
**Evidence.** Analysis-00.toc collected icuuc.dll from the host Poppler runtime.
The frozen ICU was 78.3 with suffixed exports; source Qt loaded Windows ICU 72.1.
Only the Qt6Core -> bundled ICU missing imports remained after correcting the probe.
**Root cause.** The build inherited an unrelated tool runtime on PATH, which made
PyInstaller bundle an incompatible ICU DLL ahead of the native Windows library.
**Fix.** Clean rebuild with a controlled PATH. Detached self-test exited 0 and the
eight-second smoke exited 124. No dependency pins or packaging spec were changed.
**Lesson.** Read actual loader paths and collection provenance before upgrading Qt.
A diagnostic tool's truncation limit can masquerade as a dependency defect.

## Case study: finite operands overflow after Qt geometry composition (#453)

**Symptom.** Independent review loaded finite rectangles/groups and an embedded
image whose computed scene bounds contained infinity. Opaque metadata value="NaN"
also failed even though it was ordinary text.
**Wrong theories.** Raw finite values and individually finite extents were not
sufficient evidence of finite transformed/grouped geometry.
**Evidence.** Five regressions failed first: translated group bounds, aggregate
group bounds, a 45-degree rectangle, a decoded 4x4 image scaled by 1e308, and opaque
metadata. The four real application tests failed DID NOT RAISE ValueError while
the metadata test raised PlanValidationError on text.
**Root cause.** Raw validation omitted derived Qt geometry and propagated numeric-
string semantics into arbitrary nested metadata.
**Fix.** Validate Qt-computed local/mapped bounds and transform coefficients across
the detached graph before active-scene mutation and across live items before saves.
Check decoded image dimensions before calibration; propagate PlanValidationError
instead of skipping an item or replacing it with a placeholder. Scope numeric-
string checks to geometry containers while rejecting actual non-finite numbers
everywhere. The focused preservation/image/atomicity run passed 63 tests.
**Lesson.** Finite operands need a checked composition boundary. Let Qt compute
its own transforms, then validate the detached result before publishing it.

## Case study: an empty Qt bounding rectangle hides an infinite line span (#453)

**Symptom.** A construction line with x1=-1e308 and x2=1e308 passed finite-input
validation. Qt returned an empty bounding rectangle despite infinite dx and length.
**Wrong theories.** A finite or empty bounding rectangle does not prove that the
underlying primitive has finite intermediate geometry.
**Evidence.** Independent review measured infinite QLineF dx/length. The real
load-preservation regression failed DID NOT RAISE ValueError before the fix.
**Root cause.** The raw preflight omitted endpoint spans, and Qt's empty rectangle
concealed the overflow from the detached bounds check.
**Fix.** Check both endpoint differences and hypot length before construction,
including point/anchor/control segments and polygon closing edges. Check arc
endpoint/midpoint angle sums at the raw boundary; do not construct enormous sweeps
to test arithmetic. Polyline, polygon and arc regressions also failed first.
Pure huge-finite Qt path rendering limits preserve the serialized model and stay
outside A1; no coordinate cap or zero-length rejection was introduced.
**Lesson.** Validate primitive arithmetic when invalid geometry can collapse to an
empty bounding rectangle. Keep the detached Qt composition gate as well.


## Case study: a complete catalog can hide the wrong source inventory (#496 review)

**Symptom.** The new gate passed, yet helper keyword calls and unmarked table members
were absent; offset-tool status text still appeared in English with German installed.
**Wrong theory.** Marker presence and an enclosing class identify every runtime key.
**Evidence.** Four independent mutation tests failed first. A real CanvasView/OffsetTool
regression returned `Select a shape to offset` instead of the German status message.
**Root cause.** Helper keyword arguments were skipped; marker scans omitted plain table
values; dynamic disambiguation was discarded; `.tr()` inherited the caller's context
instead of its receiver's context.
**Fix.** Bind supported helper arguments, enumerate complete display fields/values,
preserve dynamic comments, require explicit external receiver contexts, and translate
offset status through CanvasView explicitly. Reject escaping/imported helper aliases.
**Lesson.** Validate extraction with mutations at real production source shapes and
runtime lookups, not only against catalogs generated from that same extractor.

## Case study: a fill that costs minutes, and the frame it froze (#472, 2026-10-16)

**Symptom.** A crafted plan froze the 2D canvas for minutes, with no crash and no log line.
**Wrong theories.** The cost was in item lookup/snapping; the loader was the bottleneck; a plant or tree sprite was the expensive item; my own first fix ("bound the vertex count, draw the outline instead of the fill") bounded it.
**Evidence.** Painting the issue's comb into an offscreen 512x512 `QImage` and timing `PolygonItem.paint` **with the item's own pen**, not a default painter pen. Full-detail fill: 38 ms at 256 vertices, 322 ms at 1024, 1449 ms at 4096, 5580 ms at 16384. The same shape stroked as "the outline": **35 / 319 / 640 / 2547 ms** - barely cheaper, because Qt strokes a *wide solid* pen by building a fill. The same outline with a **cosmetic** 1-px pen: 2 / 4 / 20 / 69 ms. A convex 4096-vertex polygon fills in a few milliseconds - the cost is reflex geometry, not size.
**Root cause.** `PolygonItem.paint` called `painter.drawPolygon` on whatever vertex count the file held; nothing bounded it at load and nothing degraded the paint. Qt's rasteriser is quadratic on a reflex-heavy fill, and the first draft's bound sat at the very count the report called pathological (1024) while its "outline" reuse of the item's pen stayed quadratic.
**Fix.** Bound full detail at 256 vertices; degrade an interactive, unselected over-budget paint to the exact outline with a **cosmetic** pen and no fill (exports and selected items keep the exact fill); refuse a polygon above 16384 at the load seam. ADR-057, section 8.28.
**Lesson.** A degraded path must be measured with the same inputs as the slow one - the pen the item actually uses, not a convenient default - or you have bounded the shape, not the paint. And a bound set at the count the bug report quotes as pathological does not fix the report.

## Case study: a copy that looked right until the next save (#470, 2026-10-16)

**Symptom.** The offset tool's copy of a rectangle, circle or ellipse came back in its object type's default fill, pattern and stroke, while a polygon or line copy "kept all of it".
**Wrong theories.** The offset geometry was wrong; the style dialog never applied the look; the serializer dropped the colour.
**Evidence.** After the offset the copy's `fill_pattern`/`stroke_style` read as the type default and the save -> reload pen reverted, although the in-session pen/brush on the polygon path looked correct. One row of a save/reload round-trip test separated the two representations.
**Root cause.** An item carries its look twice - live (`QPen`/`QBrush`) and serialized (`fill_pattern`/`fill_color`/`stroke_color`/`stroke_width`/`stroke_style`). The rectangle/circle/ellipse path copied neither; the polygon/line path copied only the live pair, so it looked right until the next save. Two failures, one defect.
**Fix.** One seam, `core/item_look.py::copy_visual_style`, copies both; the offset tool and `mirror_geometry` share it.
**Lesson.** A copy that writes only one of an item's two appearance representations is a round-trip bug a rendering test cannot see - assert through the save/reload boundary.

## Case study: a bound that was never reached, and a test value that could not fail (#472/#502 review, 2026-10-17)

**Symptom.** Nothing. The polygon paint bound shipped green, the tests passed, and the owner's plan painted correctly. Independent review found the degrade never executed in the product, and a sibling test asserted a value that could not fail.
**Wrong theories.** That the degrade threshold was too high (it was 256, already measured); that Qt's `widget` argument was being passed where the guard expected it; that the failing perf budget was a regression from the fix.
**Evidence.** A spy on `PolygonItem.paint` through a real `CanvasScene` + `CanvasView`: an unselected item is `DeviceCoordinateCache`, and the paints that actually run (cache regeneration, forced by `view.resetCachedContent()`) arrive with `widget = None`; `widget` is present only when the item is `NoCache`. The old guard was `... and widget is not None`. Separately, deleting only the `fill_color` restore from `restore_stored_look` left `test_the_look_survives_a_second_save` **passing**, because its fill colour was the owner's green `#ff90ee90` - which is `GENERIC_RECTANGLE`'s default `fill_color`. Re-pointing the test at a colour that collides with none of the 52 `OBJECT_STYLES` entries made the same mutation fail.
**Root cause.** Two flavours of the same error - an idempotent condition in the guard or in the assertion. `widget is not None` looked like "is this an interactive paint" because that is what the LOD flat fill's own comment claims, but Qt passes `widget = 0` for every *cached* paint and unselected canvas items are cached, so the condition was never true on the canvas that matters; the render paths that must keep full detail are exactly the ones that disable caches first. And `after.fill_color == item.fill_color` holds identically when the loader writes nothing back and the constructor default happens to be the user's colour.
**Fix.** The #472 degrade now keys on the item's **cache mode** (`widget is not None or self.cacheMode() != NoCache`), and `tests/integration/test_polygon_paint_bound.py` drives a real `CanvasView` plus the real `ExportService._disable_item_caches` convention - it fails on the old guard (3 of 12 cases). The round-trip tests use a non-default `USER_FILL`, guarded by a test that walks every object type; the owner's literal green stays as its own case, labelled as a tint regression rather than restore evidence. The same `widget` idiom in `should_use_lod_flat_fill` is filed as **#503**, out of scope here.
**Lesson.** A guard borrowed from a neighbouring file is a hypothesis, not a fact - check that its condition is ever true on the path you are protecting, because caching can make it permanently false. And a regression test proves nothing when its chosen value equals the value the defect leaves behind; if the value must be realistic, prove the non-default separately. Verify both by mutation in the same sitting as the fix: a test that passes on the broken code is exactly the failure a test cannot report about itself.

## Case study: a dormant optimisation, the measurement that killed it, and a fix that was the wrong fix twice (#503, 2026-10-17)

**Symptom.** Nothing. The LOD flat fill's comment and tests say it fires below 0.4 zoom during
interactive painting; the product never showed it. The issue was measured by review, not by a
failure.

**Wrong theories.** That the threshold was the problem; that the polygon-bound fix had already
covered "the same trap" because its issue said so; and - the one that cost the most - that
"the cheap correct fix is one discriminator", so deleting the branch was dismissed as losing
#409's design intent rather than repairing it. That reasoning was reasonable, unmeasured, and
wrong: the branch was carried to production on the strength of an argument about a guard rather
than a number about the workload.

**Evidence, in two rounds.** Round 1 - reachability. A real `CanvasScene` + `CanvasView`, one
textured `GARDEN_BED` rectangle: `should_use_lod_flat_fill` is called once per paint with **no**
widget at `fit_in_view` and after four `zoom_out()`s, and returns `False` every time; a
`NoCache` control item - a state no unselected canvas item is ever in - sees a widget and
returns `True`. Keying the guard on the cache mode made it fire: a rendered-pixel measure
(fill-intensity spread of a deep-blue tint over the roof-tile texture) went **13.61 -> 0.00** at
0.25 zoom, with textured controls at 20.1.

Round 2 - the question reachability cannot answer. Measured on the reference plan the branch was
written for (990 scene items, 1600x1000 view, seven rounds of fifteen repaints), both scenarios
below the 0.4 threshold: `fit_in_view` at zoom 0.316 read **10.61 and 11.50 ms median with the
flat fill disabled, 10.87 ms with it live** - the arms' ranges overlap entirely; `zoom_step` at
0.348 read **7.97 / 7.98 ms disabled, 8.20 ms live**. All six `tests/perf/test_nfr_budgets.py`
cases pass with the branch stubbed to `return False`, worst reading 12.21 ms against the 16.70 ms
budget. The reason is structural and was visible in the code all along: `DeviceCoordinateCache`
rasterises a textured item **once** and every later frame is a cheap blit, so the expensive
textured `paint()` the LOD existed to avoid was already amortised by the sibling fix from the
same PR. The branch could only pay per *cache regeneration*; the acceptance metric is
steady-state repaint.

What the measurement establishes is that the effect sits **below this harness's noise**:
within-arm variation is 8 % against a 0.26 ms between-arm difference, and no reversed-order run
was taken, so no claim about which arm is faster survives. An earlier single-pair reading
(10.58/10.64, 8.21/7.40) is **superseded** - it put the `zoom_step` sign the other way round, and
a draft of this very case study asserted the ordering it implied and was wrong on its own
numbers. *A conclusion drawn from one ordering of a noisy measurement is the same class of
mistake as a guard whose condition was never true: both are confident and both are unfounded.*

**Root cause, twice over.** The `widget is not None` idiom, for the third recorded time (#472's
first draft, then the LOD guard, then #472's suite) - Qt passes `widget = 0` for every
*cached* paint and every unselected canvas item is `DeviceCoordinateCache`, while the tests
called the helper directly with a fabricated widget. And beneath that, a second defect no guard
could fix: the branch's *premise* was never tested. It assumed the textured paint was a
per-frame cost, and the cache that shipped beside it had already made that false.

**Fix.** Deleted: `should_use_lod_flat_fill`, `get_lod_fill_color`, `LOD_FLAT_FILL_THRESHOLD` and
seven call sites across the rectangle, circle, ellipse and polygon items. Kept:
`is_interactive_paint`, which the #472 paint bound needs for real (a cached 1,024-vertex comb is
44.7 ms at full detail, 589 ms at 16,384); its docstring now says it classifies paints and does
not decide detail. `tests/integration/test_canvas_item_cache.py` (renamed) renders a textured,
tinted `RectangleItem` through a real `CanvasView` at five zoom levels plus the export path and
asserts the texture's luminance spread survives - **lower bound only**, so a future change may
soften a texture but cannot delete it. Re-introducing a `< 0.4` flat fill fails the 0.1, 0.25 and
export cases.

**The sibling suite's part, in both directions.** With the branch live,
`tests/integration/test_polygon_paint_bound.py` failed 3 of 12: its below-budget polygons carry
`LAWN`'s pre-seeded `GRASS` pattern and a *test-only* magenta brush, so at the harness's
fit-in-view zoom (0.35 < 0.4) the canvas now *correctly* painted the designed flat fill and the
magenta count went to zero. The harness was moved to 100 % zoom and a low-zoom seam pair was
added. When the branch was then deleted, **all of that work was reverted** - the suite is back to
its pre-#507 state in full. A seam test for a deleted feature encodes the deletion as a contract.

**The pin took two rounds and was vacuous for most of it.** The replacement is
`tests/integration/test_canvas_item_cache.py`, parametrised over rectangle, circle, ellipse and
polygon, each rendered through a real `CanvasView` at five zoom levels plus the export path, with
the interior sampled from the item's own `QGraphicsItem.shape()` rather than its bounding box: the
box's corners are page background for three of the four shapes, so a *solid* circle measured as
high-contrast and the pin passed while the branch was firing. Then two further holes. The seven
deleted call sites were not seven instances of one thing - two sat behind `if is_plant` and two
behind `if is_furniture_type`, which a `GENERIC_*` fixture never enters, so four shapes watched
four of seven and the three unwatched were exactly the sprite paths; a flat fill in a plant branch
took a `TREE` circle from interior std 43.09 to 0.00 while 212 tests in the repo stayed green.
And the export mask applied the render scale but forgot the `-source.topLeft()` translation
`QGraphicsScene.render` composes in, so the circle's export case passed at spread 45.97 with a
flat fill live and read 1.67 once aligned. All seven sites are caught now, mutation-verified per
site, and `TestTheMaskIsTheItem` asserts the invariant every other test silently depends on: the
masked interior must be measurably darker than the page behind it. The calibration tells the same
story from the other side - the four textured shapes' export column *converges* on 15.47-16.02
once aligned, where the displaced mask gave 15.83 / 37.27 / 49.85 / 16.37.

**CI's part, and the lesson it bought.** The first pixel regression found its sample region by
matching blue-ish pixels image-wide, and the Linux/offscreen CI failed it at spread 62.59 (Windows
measured 0.00) because the scene's faint background passed the filter. One red CI job taught the
rule that then had to be re-taught twice more: *a sampler that reads background does not fail - it
reports the contrast between background and fill, which is precisely what the statistic was built
to see.* Sampling must be computed from geometry and checked, never discovered from the pixels.
cannot fail for being small rather than wrong. One red CI job bought that lesson.

**Lesson.** Reachability is necessary, not sufficient - before promoting a dormant path, ask
whether it earns the degradation it costs, on the workload it was written for, and treat a
number you have not taken as an argument you have not had. "The cheap fix is one shared
predicate" was true *as a repair of the guard* and wrong *as a decision about the feature*:
fixing the guard is what made the feature's cost visible, and the cost is information. Deleting
a feature leaves no test that fails when it returns, so replace its tests with a negative pin
rather than dropping them. And when a fix makes a dead branch live, run the sibling suites - then
be willing to revert the collateral if the branch does not survive.

## Case study: six wrong theories, five of them instruments that did not reach the code (#509, 2026-10-18)

**Symptom.** The test suite took 912.6 s serially and gated every iteration between a change
and the owner's hands-on pass. Issue #509 proposed `pytest-xdist`, and the diagnosis was
supposed to be straightforward: measure where the time goes, then parallelise.

**Wrong theories, and each one cost real time.**

1. *"`apply_theme()` costs 2-3 s per call and the icon cache clear dominates."* Refuted by
   ablation: removing the `clear_cache` listener changed nothing, 1.0x. The benchmark had
   built synthetic `QLabel`/`QWidget` trees, which request no icons at all - the cache was
   `svg=0 icon=0 pixmap=0`. **The instrument never reached the mechanism it was testing.**
2. *"`gc.collect()` will reclaim the leaked widgets."* It freed 8 337 objects and moved the
   widget count only 38 271 -> 37 638, so they are not reachable as collectable cycles
   and the plausible one-liner would have been useless. **What holds them is NOT
   identified** - the referrer probe walked into PyQt6/sip bookkeeping and stopped - so
   "strong references" is the reading consistent with the `gc` measurement, not a proven
   mechanism. The chokepoint does not need it to be true, and claiming it would repeat
   this file's own first case study: an instrument that asserts a mechanism it never saw.
3. *"The chokepoint cannot reclaim them either."* `sendPostedEvents(None, 0)` - the shape
   that looks right - flushes nothing; `DeferredDelete` must be named explicitly. **A
   measurement that mis-invokes its instrument refutes the call, not the idea**, and I was
   one step from discarding a correct fix on that basis.
4. *"`-n 8 --dist worksteal` now takes 740 s, so parallelising made it worse."* 740 s is
   suspiciously close to the 673 s **serial** figure. `$args` is a PowerShell *automatic*
   variable, so `function Time-Run($label, $args)` + `@args` splatting meant the flags never
   reached pytest: three serial runs were reported as parallel, and the two runs disagreed on
   failure count for no scheduler-related reason.
5. *"'CI no longer pays for the suite twice, so that is 31 minutes of wall clock."* The `test`
   and `coverage` jobs have no `needs:` between them and run concurrently. What doubles is
   runner-minutes, not the wait.
6. *"`--cov` and the perf tests are mutually exclusive, so the `Coverage` job has been
   measuring something it cannot gate."* The repaint budget fails locally under tracing -
   20.29 ms against a 16.70 ms budget - and that is true. But
   `tests/perf/test_nfr_budgets.py:56-57` reads `_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"` and
   `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`, so **on CI the budget is 50 ms**. The
   20.29 ms was measured against the LOCAL budget and then generalised to a configuration
   nobody ran; `gh run view 39076508170` records master's `Coverage` job **succeeded**.
   One variable, both ways: `CI=true` -> 6 passed, unset -> 1 failed. **An instrument
   pointed at the right code can still answer a different question than the one you carry
   to the next file.** The corollary cost a fifth review round, and the same claim had
   already been corrected in four documents by the time it was found a fifth time in
   11.4 - so the real instrument here is `git grep`, not the measurement.

**Key evidence.** The one measurement that mattered was the cheapest: re-run the slow file
**on its own**. `test_iconography_3c.py` takes 2.14 s alone and 96.7 s in the suite; the same
file right after `test_main_window.py` takes 447 s with individual theme tests at 60-66 s.
That contradiction sends you straight to the cause, and probing `QApplication` closed it: a
clean process holds **0** widgets and one `apply_theme()` round-trip costs **1.3 ms**; after
`test_main_window.py` it holds **38 271** widgets and **1 580** top-level widgets, **0 % of
them visible**, and the round-trip costs **22 478 ms**. `qtbot.addWidget` closes a widget and
closing is not deleting, so 30 apps leaked their C++ widget graphs into the process and every
later theme switch paid for all of them.

**Lesson.** *A per-test duration table says which tests are slow, not which files are.* The
expensive tests here were the **victims** - they were the only ones calling the one global,
cache-destroying, widget-count-proportional operation in a loop. And a second lesson, from
reading the scheduler results wrong: **total call time is summed per test and inflates under
parallel execution.** The same suite read 620.6 s of call time serially and 1 700 s under
`-n auto` while its wall clock *fell* from 673.6 s to 182 s - a 2.7x "regression" that was
actually a 3.7x speed-up. Compare wall clock and ratios; the per-test table is useful for its
shape, not its sum. Finally: this box drifts. Two files that were never touched moved 37-63 %
across the session, so a single run's absolute seconds are evidence about the machine as much
as about the suite.

**Two hazards found only because parallel execution made them visible, both pre-existing.**
A test staged a canary file in the **real git working tree** and scanned it, while another
globbed that tree and read what it found - two moments, so a parallel run could read a file
that no longer existed. And two autouse fixtures, one merely *depending* on the other, left an
instant in which the settings key did not exist at all, so a read returned the production
default (`True`) and the port read 8765, and a deferred `_maybe_start_agent_api` timer landing
there started a **real** server. Neither was created by parallel execution; serial runs made
both windows too narrow to hit. `@pytest.mark.xdist_group` would have scheduled around the
first one and left it exactly as dangerous for the two-concurrent-pytest-process case that
`conftest.py` already documents for QSettings. Fix the shared state, not the schedule.

## Case study: green on every dev run, red on the Linux runner — a fixed wait for a pass the product holds (Phase 17 L1.3, fixed 2026-10-19)

**Symptom**: `tests/integration/test_view3d_workspace.py::test_a_plan_with_a_refused_item_shows_the_indicator_and_fixing_it_clears_it`
read `workspace.problems_text() == ''` 120 ms after the switch to Split — on CI only; green in
every local run.

**Wrong theory**: *"the indicator is filled late — a race in the product"*. It was not tested,
it was measured.

**Key evidence**: the CI log had the refused item's snapshot line in the test's **teardown**
(the pass ran after the assertion). A probe that recorded `problems_text()` inside a slot on
the controller's `applied` signal: set in the same call, 10 of 10. Time from the switch to the
pass: 53–62 ms when the "Building the 3D view…" label paints, 295–307 ms when its paint is
withheld (the pass is held for the paint, or 250 ms, then 25 ms). A scratch pytest plugin that
withholds the label's paint from the workspace's filter made the slow path deterministic: the
old test failed with CI's exact message — and so did **21 widget tests and the §8.10 workflow**,
because the shared helpers (`Bench.settle()`, `_calls()`) waited a fixed 80 ms.

**Root cause**: test helpers guessed how fast a deliberately HELD pass would run.

**Fix**: one condition (`pipeline_settled`: no first pass held, none posted, none timed), waited
for; the indicator asserted at the signal that sets it.

**Lesson**: **force the slow path to prove a timing test** — a plugin that withholds one event
turned a once-a-week CI failure into 23 deterministic ones. A fixed wait in a test is a guess
about the slowest machine it will ever run on.

## Case study: a surviving mutant that was the product's behaviour — Qt's empty `changed([])` (Phase 17 L1.3, fixed 2026-10-19)

**Symptom**: the hand mutant "an explained repaint arms the quiet timer too" survived every test
of the 3D sync controller. The test written to kill it failed on the UNMUTATED product: a write
that nudged the plan revision and then repainted was in 3D at once — and 400 ms later a second
whole-plan snapshot ran and found nothing.

**Wrong theory**: *"the 2D side's debounced work repaints later"* — plausible (the matrix test
had seen late repaints) and wrong.

**Key evidence**: a probe that logged every `scene.changed` with its rectangles and every pass,
for five write patterns:

```
update_only:        changed([(397, 297, 306, 206)]), changed([]), applied(net)
write_nudge_update: applied(announced), changed([(397, 297, 306, 206)]), changed([]), applied(net)
```

**Root cause**: with a listener on `QGraphicsScene.changed`, Qt reports an item's `update()` at
once from `_q_processDirtyItems`; the queued `_q_emitUpdated` the same update asked for arrives
afterwards and emits what is left — an empty list. The controller's "explained" test compared
the plan revision with the one the previous `changed` had recorded; the empty echo came right
after the explained one, saw no move, and armed the net.

**Fix**: an empty `changed` reports no repaint and is ignored
(`ui/view3d/sync_controller.py::Scene3DController._on_scene_changed`).

**Lesson**: **log a signal's ARGUMENTS, not just that it fired** — two emissions per update looked
like "something else repainted" until the second one was seen to carry nothing. And a surviving
mutant is a question about the product as much as about the tests.
