---
name: ogp-proof-and-analysis-toolkit
description: >
  First-principles proof methods for Open Garden Planner — how this project verifies
  claims instead of assuming them. Load when: you are about to assert something about a
  third-party library's behavior (mcp/FastMCP, PyQt6, Qt geometry, numpy); you are about
  to write or trust geometry/transform code (rotation, resize, coordinate frames,
  serialization invariants); you are choosing a tolerance, threshold, or epsilon; two
  coordinate frames (scene vs pixel, local vs scene) might disagree; a reviewer or doc
  claims something about the code and you're deciding whether to act on it; you're
  designing tests for a class of inputs (shapes × angles × handles) or hardening a
  trust boundary against hostile files; or any claim needs proof before it goes into a
  PR, ADR, or doc. Theme: "prove it, don't just install it."
---

# OGP Proof & Analysis Toolkit

Nine proof methods this project actually uses, each as a recipe with a worked example
mined from the repo's real history (docs §11.4, §8.9/§8.12/§8.19, ADRs, CLAUDE.md
progress rows, and the pinned tests). The unifying rule: **a claim earns its way into
code, review responses, or docs by a reproducible experiment or a primary-source read —
never by memory, plausibility, or authority.**

All doc references: `docs/08-crosscutting-concepts/README.md` (§8.x),
`docs/09-architecture-decisions/README.md` (ADR-xxx),
`docs/11-risks-and-technical-debt/README.md` (§11.4). Version facts date-stamped
2026-07-05 (repo at v1.23.0; mcp library facts pinned against **mcp 1.28.1**).

**Jargon (defined once):**
- **Pin / pinned test** — a test whose only job is to make an empirically-discovered
  fact permanent, so a refactor that silently breaks it fails CI.
- **Probe** — a minimal throwaway script/REPL run against the *real* library or object
  to observe one behavior; not a test, not committed.
- **Trust boundary** — a seam where data arrives from outside your control (user-dropped
  JSON, network responses, other apps' files).
- **Scene frame (nominal Qt labeling)** — the coordinates items live in: cm,
  nominally "origin top-left, +y down." Operationally the data path consumes raw
  scene y as CAD **Y-up** (the view's `scale(zoom, −zoom)` makes larger scene-y
  render higher; there is no `scene_to_canvas` conversion in production). See
  `ogp-qt-cad-reference` §1 — the single owner of the Y-axis reconciliation.
- **Serializer invariant** — a rect-bearing item saves `pos + rect.center()` with
  rotation as a separate angle; this only round-trips if
  `transformOriginPoint() == rect().center()` at all times (§8.9.8).

## When NOT to use this skill

- You need the *process* rules (branch/PR/gates) → `ogp-change-control`.
- You have a live bug and need symptom→cause triage → `ogp-debugging-playbook` and the
  `debug-verbose` skill (instrumentation mechanics live there, not here).
- You want the evidence *policy* (what must be proven before merge) →
  `ogp-validation-and-qa`. This skill is the *how*; that one is the *what/when*.
- You want the tool inventory (runners, scripts, flags) → `ogp-diagnostics-and-tooling`.
- The claim is trivially checked by running the existing test suite — just run it.
- Post-mortem catalogue of past failures → `ogp-failure-archaeology`.

---

## Method 1 — Empirical verification of third-party behavior

**When to use:** before asserting anything about a library's edge behavior — decorator
constraints, serialization of exotic types, annotation resolution, return-value
coercion. Library docs and your memory of them are hypotheses, not facts; minor-version
behavior differences are common.

**Recipe:**
1. State the exact claim ("FastMCP can return `list[Image | RenderMeta]`").
2. Write a minimal probe against the *installed* version — smallest script that
   exercises exactly that path (build the server, call the tool, inspect output).
3. Record the library version with the result. The fact is only pinned to that version.
4. If the probe refutes the claim, probe the *fix* too before trusting it.
5. Land the fact as (a) a pinned test where feasible, and (b) a dated note in the ADR/§
   with the words "empirically verified" — so the next person knows it wasn't guessed.

**Worked example (US-D1.3, mcp 1.28.1 — §8.19 + ADR-034 addendum, CLAUDE.md D1.3 row):**
Two facts were established by experiment, not assumption:
- `Image` (from `mcp.server.fastmcp.utilities.types`) is not pydantic-representable, so
  the natural `-> list[Image | RenderMeta]` annotation **crashes `build_server()` at
  decoration time**; `@mcp.tool(structured_output=False)` is the verified fix (cost:
  no `structuredContent` for that one tool).
- With `from __future__ import annotations`, `Image` must be a genuine **module-level
  import in `server.py`** — a function-local import raises `NameError` at server-build
  time, because FastMCP resolves stringified annotations via
  `inspect.signature(func, eval_str=True)`, which uses the function's own
  `__globals__`, not the enclosing call's locals.

Same method, US-D1.2 (§8.19): the **dict-first union return**
`list[dict] | list[ObjectRef]` was chosen because a probe showed model-first ordering
coerces raw dicts back into the model and **drops unknown keys**; dict-first keeps a
clean `anyOf` schema *and* preserves `raw` keys — "verified mcp 1.28.1".

**What "proven" looks like:** a runnable probe result + library version recorded, the
behavior pinned in a test or a dated ADR/doc note. "The docs say so" is not proven.

---

## Method 2 — Coordinate-frame proof by pixel scan

**When to use:** whenever two coordinate frames could disagree — scene vs rendered
pixels, model vs view, export vs canvas. Frame mismatches are invisible in code review
(both frames are "just numbers") and only falsifiable by observing real output.

**Recipe:**
1. Place a marker item at a *known, asymmetric* position (near one edge, not center —
   center is invariant under flips and proves nothing).
2. Render through the *production* pipeline (no shortcuts).
3. Scan actual pixels for the marker (`QImage.pixelColor` vs background).
4. Compare found position against both candidate frames; write down the winning
   correction formula.
5. Pin it: one test for the inversion, one for the exact formula, and one control
   render with the transform disabled to isolate it as the sole cause.

**Worked example (US-D1.3 — `tests/unit/test_agent_api_render_coordinate_frame.py`,
verified to exist and read):** `render_scene_region`'s `y_flip=True` means a small
scene-y lands near the **bottom** of the rendered image, inverted relative to the D1.2
scene frame agents use for queries. The test renders a circle at scene y=50 cm, scans
pixel columns for non-background rows, and pins three things:
`test_small_scene_y_lands_near_image_bottom` (the inversion exists),
`test_correction_formula_holds`
(`px_y = image_height_px − (y_cm − region_y_cm) * px_per_cm` — the exact formula
documented on `RenderMeta.px_per_cm`), and
`test_unflipped_render_aligns_directly_with_scene_frame` (control: with `y_flip=False`
the direct mapping holds, isolating `y_flip` as the sole cause).

**What "proven" looks like:** pixels scanned, correction formula written down and
pinned by a test *plus a control*, formula published where the consumer reads it
(here: the `RenderMeta` field docstring).

---

## Method 3 — Geometry invariant derivation

**When to use:** before writing any transform-touching code (resize, rotate, reparent,
serialize). Derive the algebra on paper from the platform's own definition first; code
that "looks right on screen" for unrotated items is the classic false positive.

**Recipe:**
1. Write down the platform's ground-truth mapping. For Qt:
   `mapToScene(p) = pos + O + R(θ)·(p − O)` where `O = transformOriginPoint`.
2. State the invariant that must survive the operation (OGP: the serializer invariant,
   `transformOriginPoint() == rect().center()` — §8.9.8).
3. Solve for the unknown symbolically *before* coding. Every term you can't justify in
   the derivation is a bug you're about to write.
4. Implement the formula in **one** shared primitive; make every path (interactive
   drag, programmatic, undo closure) route through it.
5. Pin with rotated-item tests — an unrotated test cannot falsify frame errors
   (R(0) = identity makes every wrong formula collapse to the right one).

**Worked example (#218 — ADR-028, §8.9.8, §11.4 "Closed (#218)"):**
`resize_handle.resize_rect_item_keeping_anchor(item, new_rect, scene_anchor,
local_anchor)` (in `src/open_garden_planner/ui/canvas/items/resize_handle.py`) applies

```
pos = scene_anchor − O − R(θ)·(local_anchor − O)
```

derived directly from Qt's `mapToScene`. The derivation *explains why the naive fix
failed*: the first cut kept a rotation-gated post-correction
(`_reanchor_after_rotated_resize`) over an incoherent step — `min(w,h)` squaring picked
the axis a 45° diagonal drag never changed, and the fixed edge was inferred two
disagreeing ways (scene-space `abs(pos_x − init_pos.x()) < 0.01` vs rotated-local
`pos_dx == 0`). No post-correction can reconcile two inconsistent frames; ADR-028's
recorded lesson: **"do not post-correct an incoherent geometry step — fix the step."**
The same derivation exposed #219: pivoting on `boundingRect().center()` breaks the
invariant when a runtime-only badge expands the box asymmetrically — pivot on the
geometric `rect().center()`, never the decoration-expanded bounding rect.

**What "proven" looks like:** formula derived from the platform definition, one
primitive owning it, rotated-configuration tests
(`tests/integration/test_rotation_aware_resize.py`) pinning position *and* pivot *and*
serialized-centre invariants across undo.

---

## Method 4 — Headless numeric trace to refute a theory

**When to use:** when you hold a theory about numeric/geometric behavior ("it just
needs a post-correction") and can't tell from reading whether it's true. Drive the
scene programmatically — no UI, no human timing — and print per-step numbers.

**Recipe:**
1. Write the theory as a falsifiable numeric prediction ("after an (80,80) drag the
   radius grows").
2. Script the gesture headlessly (create scene + item, rotate, call the same
   `_apply_resize` path the handle calls) and print each intermediate quantity per
   step: inputs, local deltas, resulting rect, pos, center.
3. Read the numbers against the prediction. The first value that contradicts the
   theory is your real lead; follow *it*, not the theory.
4. Convert the decisive trace into either a fix + pinned test, or a documented
   refutation.

**Worked example (#218 — §11.4 "Closed (#218)" entry, CLAUDE.md #218 row):** the
theory was "the rotated resize needs a re-anchor post-correction." A headless trace
showed the **radius stuck at 50 through an (80,80) drag** — at 45° the diagonal drag
projects onto one local axis (`local_dy ≈ 0`), so `min(width, height)` selected the
*unchanged* axis and the circle mathematically could not grow. The trace also
quantified the centre drift (45–135 cm) from the two disagreeing fixed-edge
inferences. That refuted "needs post-correction" and proved the resize step itself was
incoherent — leading to the ADR-028 redesign (Method 3), not a patch.

**What "proven" looks like:** a numbered trace where a specific printed value
contradicts the theory; the refutation is written down (§11.4) so the dead theory
isn't re-tried. Cross-ref: `debug-verbose` for print-instrumentation mechanics.

---

## Method 5 — Adversarial input probing at trust boundaries

**When to use:** any code that ingests data you don't control (user-dropped files,
downloaded content, other apps' exports). Enumerate hostile inputs by **CLASS**, not by
instance — one example per failure *family*, then ask which families you haven't tried.

**Recipe:**
1. Identify the boundary and the contract (OGP smart symbols: "a bad user file must
   never crash the app").
2. Enumerate hostile classes: **structural** (wrong types/shapes — a list where a dict
   belongs), **arithmetic** (overflow, divide-by-zero, domain errors),
   **resource-exhaustion** (recursion depth, node count, size/repeat budgets). Probe at
   least one input per class through the *real* ingestion path.
3. Note *which phase* each failure escapes from (parse vs structural validation vs
   dry-run evaluation) — narrow catches placed at one phase miss the others.
4. Conclusion pattern: one **broad `except Exception` at the ingestion seam** for
   untrusted input (log-and-skip); keep narrow typed catches only for trusted
   first-party input so your own bugs stay loud. `BaseException` still propagates.
5. Pin every probe class as a test; add hard resource caps as defense in depth.

**Worked example (US-C4 smart symbols, PR #236 — §11.4 trust-boundary entry, verified
verbatim):** the first catch was `(OSError, JSONDecodeError, ValueError)`. It broke
**three review rounds in a row**, each a different family escaping:
(1) `9**9**9` overflow and `round(x, float)` raised `ArithmeticError`/`TypeError` in
the dry-run `generate()` — neither subclasses `ValueError`;
(2) `"+".join(["1"]*5000)` raised `RecursionError` **during `ast.parse`**, before any
evaluator whitelist ran;
(3) a non-dict `parameters` entry (`[42]`) raised `AttributeError` in the *structural*
phase, which runs before the dry-run and bypassed its wrapper entirely.
Each "fix" added the family that bit it and re-declared victory — the losing game. Real
fix: the user-file load loop catches `Exception` (`smart_symbol_library.py`); the
bundled-file loop stays narrow so packaging bugs crash loud; `parametric_eval` caps AST
size (`_MAX_NODES = 250`, verified in `core/parametric_eval.py`). Pinned by
`tests/unit/test_smart_symbol_library.py` and `tests/unit/test_parametric_eval.py`
(both verified to exist).

**What "proven" looks like:** at least one probe per hostile *class* passing through
the real seam, the catch strategy justified in an ADR/§11.4 entry, resource caps in
place, and the "malformed *bundled* file still crashes loud" counter-test present.

---

## Method 6 — Tolerance / threshold derivation

**When to use:** any time you're about to type an epsilon, tolerance, snap distance, or
residual threshold. Never pick by feel — derive from the physical scale of what the
number gates and who observes the error.

**Recipe:**
1. Identify what the tolerance *gates* (an early return? a conflict flag? a Jacobian
   step?) and in what units (OGP scene units are **cm**).
2. Identify the observer: a user watching pixels needs sub-render-precision; a
   diagnostic warning can tolerate ~1 cm; a numeric derivative needs a step small
   against the quantity but large against float noise.
3. Derive the bound from the observer, write the derivation in a comment/doc, and check
   different call sites may legitimately need *different* tolerances — don't unify by
   reflex.
4. Prove the failure mode of the wrong scale (a trace or test showing the slack band
   being exploited).

**Worked example (PR #169 follow-up — §11.4 "Live-drag projection tolerance must be
sub-pixel", verified verbatim):** `ConstraintGraph.project_to_feasible()` starts each
frame with the moving vertex *at the cursor* and early-returns if
`max_err <= tol`. At cm-scale `tol` (0.5 cm), a near-stationary drag keeps the cursor
inside the slack band **every frame**, so projection returns the cursor unchanged and
the vertex slips — on a fully edge-length-constrained chain the whole polyline appears
to rigidly translate. Derivation: the user perceives sub-pixel motion, so the gate must
be **below render precision** → default `tolerance=1e-4`. Crucially, `solve_anchored`
and other full-graph callers *keep* their cm-scale tolerances — the derivation is
per-observer, not global. Same discipline across §8.12 (verified): Newton central
differences use `h = 1e-3` cm (step scale), and conflict detection flags constraints
whose post-solve residual exceeds **1.0 cm** (user-meaningful geometric error) —
three different numbers, each derived from what it gates.

**What "proven" looks like:** the number has a written derivation tied to units and
observer; a test or trace demonstrates the failure at the wrong scale; differing
tolerances at different call sites are each justified.

---

## Method 7 — Signal/timing analysis for event-driven bugs

**When to use:** something happens "by itself" — a widget closes, focus jumps, state
flips — with no visible cause. In Qt, the cause is almost always another component
reacting to a signal/timer you didn't know about. Time and attribution are the
evidence.

**Recipe (mechanics live in the `debug-verbose` skill — this is the proof pattern):**
1. Instrument the *effect site* (the setter/close/hide that fires) with a `[TAG]`
   print including a monotonic timestamp **and `traceback.format_stack()`** — the
   stack is what names the external caller; a timestamp alone only tells you *when*.
2. Reproduce once; read the log. The stack frame you didn't expect *is* the finding.
3. Fix at the caller or add a principled guard; remove instrumentation; add a Case
   study entry to `.claude/skills/debug-verbose/skill.md`.

**Worked example (label editor auto-closing — debug-verbose skill, "Case study: label
editor auto-closing (fixed 2026-04-22)", verified):** double-clicking any item opened
the inline label editor for **~110 ms**, then it closed itself. The stack print at the
`setVisible(False)` site revealed
`minimap_widget.py:205 — item.setVisible(False) ← THE CULPRIT`:
`MinimapWidget._hide_overlay_items()` hides all `ItemIgnoresTransformations` items
before rendering its thumbnail — including the freshly-focused `EditableLabel`. Hiding
fired `focusOutEvent` with `isVisible() == False`, so the time-based guard (which
checked `isVisible()`) never engaged. One-line fix: skip the scene's current focus item.
No amount of reading the label-editor code could find this — the culprit was in a file
nobody suspected, and only the stack trace named it.

**What "proven" looks like:** a log line whose stack names the unexpected caller, a fix
at that caller, and a Case study written so the pattern is searchable next time.

---

## Method 8 — Refutation by primary source

**When to use:** a reviewer, doc, comment, or your own memory claims X about the code
and you're about to act on it (rewire signals, "fix" behavior, accept a P1). Read the
actual source *first* — authority and confidence are not evidence, and acting on a
false claim creates real churn.

**Recipe:**
1. Reduce the claim to a checkable statement about specific code ("`can_undo_changed`
   fires only when the boolean flips, not on every undo").
2. Read the defining code path end-to-end (the emit sites, not the connect sites).
3. If refuted: respond with file+line evidence, don't change the code, and record the
   refutation where the next person will look (CLAUDE.md row / PR thread).
4. If confirmed: proceed — and thank the reviewer with the same evidence.
5. Symmetry check: apply this to *your own* recalled claims too, before writing them
   into docs.

**Worked example (#223 — CLAUDE.md #223 row, verified):** a senior-review P1 claimed
the constraints/properties-panel rewiring changed behavior because
`can_undo/redo_changed` doesn't fire unconditionally on undo/redo. Reading
`core/commands.py` showed the signals **already fired unconditionally on every
undo/redo** — the rewiring to `stack_changed` was behavior-preserving for those panels.
The P1 was refuted with the source read and recorded in the row ("a senior-review P1
claimed otherwise — refuted by reading commands.py"); the *real* fix in that PR was
elsewhere (the plant-database panel had never been wired to any command signal at all).
Counter-example in the same codebase showing the method cuts both ways: §11.4's older
"Dimension line updates after undo/redo" entry proves `command_executed` genuinely
does NOT fire on undo/redo — the two signals differ, and only reading the emit sites
tells you which claim is true for which signal.

**What "proven" looks like:** file+line citations for the emit/definition sites; the
verdict recorded next to the claim; no code changed on the strength of an unverified
assertion.

---

## Method 9 — Counting / exhaustiveness proofs

**When to use:** the claim is universal — "every bed shape has the menu", "resize is
correct for all shapes and rotations". Sampling one instance proves nothing about the
class; parametrise over the *whole* enumerable class, and add a structural guard so the
class can't silently grow past the test.

**Recipe:**
1. Enumerate the class explicitly (the four bed-capable shapes; the shape × angle ×
   handle grid). If the class is a cross-product, test the product, and include at
   least one "ugly" element per axis (215°, not just 0/45; edge handles, not just
   corners).
2. `@pytest.mark.parametrize` over the enumeration — one assertion body, N cases.
3. Add a **structural** companion test that catches new members bypassing the shared
   mechanism (source-level check that each class routes through the shared builder).
4. State the boundary honestly: the proof covers the enumerated class, nothing more.

**Worked examples (both files verified to exist and read):**
- `tests/integration/test_bed_context_menu.py` — parametrises `BED_SHAPES`
  (factory, supports_grid, supports_soil) so every bed-capable shape is asserted to
  expose every bed action with correct capability gating, plus a second parametrised
  pass for translated menu text, **plus** the structural test
  `test_context_menu_uses_shared_builder` over
  `[RectangleItem, PolygonItem, EllipseItem, CircleItem]` that inspects each
  `contextMenuEvent` source for the shared builder + dispatcher — catching a future
  shape that regresses to a hand-rolled menu (the original bug class: features
  forgotten on one shape because each rolled its own menu).
- `tests/integration/test_rotation_aware_resize.py` — the #218 matrix
  **{Circle, Rect, Ellipse} × {0°, 45°, 215°} × {corner, edge}** (ADR-028): fixed side
  stays put across a multi-step drag, dragged handle tracks the cursor, circle stays
  circular, no small-drag collapse, pivot + serialized-centre invariants, undo restores
  geometry+pivot. 45° alone would have missed sign errors that 215° (odd quadrant,
  both trig signs flipped) exposes.

**What "proven" looks like:** the whole enumerated class under one parametrised test,
ugly-element coverage on each axis, and a structural guard against silent class growth.

---

## Decision table: kind of claim → minimum proof method

| Kind of claim | Minimum proof | Method |
|---|---|---|
| "Library X supports / requires / returns Y" | Probe against installed version; record version; pin | 1 |
| "These two coordinate frames agree / differ by T" | Render known-position marker, pixel scan + control render, pin formula | 2 |
| "This transform keeps point/invariant P fixed" | Derive from platform algebra first; rotated-config tests | 3 |
| "This numeric behavior just needs a small correction" | Headless per-step trace; find the value that contradicts the theory | 4 |
| "Bad input can't crash this ingestion path" | One probe per hostile class (structural/arithmetic/resource) through the real seam | 5 |
| "Tolerance/epsilon/threshold = N is right" | Written derivation from units + observer; failure demo at wrong scale | 6 |
| "Something closes/fires/changes by itself" | Timestamp + `traceback.format_stack()` at the effect site | 7 |
| "Reviewer/doc says the code does X" | Read the defining code path; cite file+line; record verdict | 8 |
| "This holds for EVERY member of class C" | Parametrise over all of C + structural anti-bypass guard | 9 |
| "It works" (feature-level) | Not this skill — see `ogp-validation-and-qa` (evidence policy) and the `verify` skill | — |

Combinations are normal: #218 used 4 (refute) → 3 (derive) → 9 (pin the matrix).
D1.3 used 1 (library probes) → 2 (pixel scan).

## Cross-references

`ogp-debugging-playbook` (symptom triage), `debug-verbose` (instrumentation mechanics +
case-study archive), `ogp-failure-archaeology` (the incidents behind these methods),
`ogp-validation-and-qa` (which proofs are mandatory before merge),
`ogp-diagnostics-and-tooling` (runners/scripts), `ogp-qt-cad-reference` (the Qt geometry
model these derivations rest on), `ogp-architecture-contract` (invariants worth
proving), `ogp-change-control` (where proof artifacts land in the workflow),
`ogp-3d-sunshade-campaign` (applies these methods to Phase 14),
`ogp-research-methodology` (proof standards for research claims).

## Provenance and maintenance

Every worked example above was verified against the repo on 2026-07-05 (v1.23.0).
Re-verify with:

- Method 1: `grep -n "structured_output=False\|__globals__\|dict-first" docs/08-crosscutting-concepts/README.md docs/09-architecture-decisions/README.md`
- Method 2: `ls tests/unit/test_agent_api_render_coordinate_frame.py && grep -n "px_per_cm" tests/unit/test_agent_api_render_coordinate_frame.py`
- Method 3: `grep -n "scene_anchor − O − R" docs/09-architecture-decisions/README.md docs/08-crosscutting-concepts/README.md` and `grep -n "def resize_rect_item_keeping_anchor" src/open_garden_planner/ui/canvas/items/resize_handle.py`
- Method 4: `grep -n "radius stuck at 50" docs/11-risks-and-technical-debt/README.md`
- Method 5: `grep -n "9\*\*9\*\*9\|RecursionError" docs/11-risks-and-technical-debt/README.md` and `grep -n "_MAX_NODES" src/open_garden_planner/core/parametric_eval.py`
- Method 6: `grep -n "sub-pixel\|1e-4" docs/11-risks-and-technical-debt/README.md` and `grep -n "1e-3\|1.0 cm" docs/08-crosscutting-concepts/README.md`
- Method 7: `grep -n "110 ms\|THE CULPRIT" .claude/skills/debug-verbose/skill.md`
- Method 8: `grep -n "refuted by reading" CLAUDE.md`
- Method 9: `grep -n "parametrize" tests/integration/test_bed_context_menu.py tests/integration/test_rotation_aware_resize.py`

If any command comes back empty, the underlying fact moved or changed — re-verify the
worked example before trusting it, and update this file.
