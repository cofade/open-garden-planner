## 5. Phase 3 — 2D shadow projection MVP — TO BUILD

The high-value cheap slice. **Definition:** for each item with effective
height `h` and sun at (α, Az) with α > 0:

- **Shadow length** `L = h / tan α` (cm, on flat ground — elevation_m of the
  *site* shifts nothing on-site; slopes are out of scope v2.0, state that in
  the FR).
- **Shadow direction** (unit vector, **canvas frame**, +x=E, +y=N):
  `d_canvas = (−sin Az, −cos Az)` — the shadow extends *opposite* the sun's
  compass bearing `(sin Az, cos Az)`.
- **Shadow polygon** = footprint swept along `D = L·d_canvas` = Minkowski sum
  of the footprint with segment [(0,0) → D]. For convex footprints this is
  `convex_hull(P ∪ (P+D))`; for arbitrary polygons use
  `pyclipper.MinkowskiSum(pattern, path, True)` (available in pyclipper ≥1.3 —
  **REQUIRES VERIFICATION at implementation**: probe
  `venv/Scripts/python.exe -c "import pyclipper; print(pyclipper.MinkowskiSum([[0,0],[100,50]], [[0,0],[400,0],[400,300],[0,300]], True))"` — expect a list of
  integer polygons; if absent/odd, fall back to union of the footprint
  translated in N=8 steps along D, which is visually identical at garden
  scale). Then union all per-item shadows via `pyclipper.Pyclipper` CT_UNION.
  Use the integer scale-factor discipline from `core/tools/offset_tool.py`
  (line 22) — pyclipper is integer-only.

### Y-axis discipline (THE trap — fence it with a test)

**Owner of the Y-axis convention: `ogp-qt-cad-reference` §1** — read it once and
defer to it. Its operative rule: scene coordinates ARE the CAD coordinates the
user sees; scene +y is already North/up in the data path; there is **no
`scene_to_canvas` conversion** in production (that helper computes `H − y` but
has zero production callers). So there is **no extra flip** between "canvas
frame" and "Qt scene frame" for shadow math — do the math once, in scene cm.

**Derivation (one line).** Az is a compass bearing clockwise from North, so in
the CAD Y-up frame (East=+x, North=+y) the sun's horizontal direction is
`(sin Az, cos Az)`; the shadow points *opposite* the sun →
`d = (−sin Az, −cos Az)`. Because scene +y is already North (no conversion
layer), the scene-space shadow vector is the **same**:
`d_scene = d_canvas = (−sin Az, −cos Az)`. (This matches the sign convention the
existing linear/grid-array code already uses in scene cm — §11.4 "Canvas
Y-axis flip".) Do **not** re-flip the y-component at an "item-construction
boundary"; that double-flip is exactly the mirrored-shadow bug.

**Worked example** (numbers from the shipped oracle, Appendix): Berlin,
2026-06-21 12:00 UTC → Az = 203.74°, α = 59.29°.
`sin Az = −0.4025`, `cos Az = −0.9154`.
- Shadow direction (scene = canvas): `(−sin Az, −cos Az) = (+0.4025, +0.9154)`
  — mostly **+y = NORTH**, slightly east. Correct: early-afternoon sun is just
  west of south, so the shadow falls north-northeast. 100 cm object → L = 59.4 cm,
  so `tip_scene = base_scene + 59.4·(0.4025, 0.9154)`.
- Rendered pixels (`y_flip=True`, §8.19):
  `px_y = image_height_px − (y_cm − region_y_cm)·px_per_cm` with `y_cm` the
  **raw scene y**. The shadow tip has the *larger* scene-y (it went North) →
  the *smaller* px_y → nearer the image **top**. That is exactly where North
  renders. No paradox: the arithmetic is settled — larger scene-y renders
  higher, in agreement with the live view.

**The binding test** (the regression pin, not the tiebreaker): place a 100 cm-tall
40×40 item at a known scene position, set sim time to Berlin 2026-06-21 12:00 UTC,
render via `render_canvas_image` (or `render_scene_region` directly in the
test), compute the expected shadow-tip pixel with the RenderMeta formula from
the raw scene coordinates `tip_scene = base_scene + 59.4·(0.4025, 0.9154)` (no
`canvas_to_scene` step — scene IS the CAD frame), and assert the shadow color
at that pixel ± 2 px. If it passes, your frames are consistent; if the shadow
appears mirrored, you re-flipped y where you shouldn't have — remove the flip,
keep the math in scene cm.

### Rendering rules (existing-pattern compliance)

- **Overlay item(s)** on a dedicated, non-serialized layer (or scene-level
  overlay item like the existing warning badges): one `QGraphicsPathItem`-ish
  item holding the unioned shadow path, z-order above background image, below
  garden items. Runtime-only — **never serialized** (the #219 lesson: runtime
  visuals must not perturb save-time geometry; also don't let the overlay
  affect any item's `boundingRect`).
- **Precompute, never in `paint()`**: recompute the union when (a) an item
  with height moves/resizes/rotates/changes height, (b) sim date/time changes,
  (c) location changes (`ProjectManager.location_changed` — already a signal,
  `application.py` line 158). Debounce with the established
  `QTimer`+`contextlib.suppress(RuntimeError)` pattern (#230 teardown pitfall).
- **Time control UI**: a small toolbar/dock with date + time-of-day slider and
  an animate button (the roadmap's "time-of-day animation" = just advancing
  the slider on a QTimer; each tick only re-runs the precompute + one
  `update()`). *As shipped:* the sim time is NOT persisted at all (FR-SUN-04),
  and since Phase 17 L1.0 it lives in the one `core/sim_clock.SimClock`
  (ADR-053) — the toolbar is a view of it and hands it naive wall
  readings. Read ADR-053 before touching sun or growth time.
- **Empty states**: no `project.location` → overlay disabled + one-line hint
  ("Set garden location first: File → Set Garden Location"), i18n'd. Sun below
  horizon → no shadows + "night" hint.
- **Historical naming collision (superseded by ADR-062)**: Phase 14 distinguished
  solar simulation from the cosmetic shadow toggle. Both now run automatically;
  neither toggle nor the Sun & 3D submenu remains. Ignore the old saved preference.

### Gate P3

| Command | Expected | If not → |
|---|---|---|
| `python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py \| grep "shadow"` | `Berlin Jun 21 12:00Z: … shadow 59.4 cm, canvas dir (dx=+0.403, dy=+0.915)`; `Berlin Dec 21 12:00Z: … shadow 430.4 cm, canvas dir (dx=+0.226, dy=+0.974)` | Oracle drift — re-run full script; if self-checks fail, stop. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_shadow_geometry.py -v` | Qt-free geometry tests: 100 cm object, α=59.29° → L=59.4±0.1 cm; α=13.08° → 430.4±1 cm; direction vectors ±0.01 | tan/atan mixup or degrees passed raw into `math.tan` — the L formula takes RADIANS internally. |
| `venv/Scripts/python.exe -m pytest tests/integration/test_shadow_overlay.py -v` | The pixel assertion described above passes; shadow recompute count ≤1 per change event (assert with a counter, the #206 discipline) | Mirrored → Y-boundary flip misplaced. Recompute storm → you wired recompute to `scene.changed` raw instead of debounced. |
| Profile: `venv/Scripts/python.exe -m pytest tests/integration/test_shadow_overlay.py -k perf -v` (write one: 200 items with heights, one recompute) | < 50 ms per recompute on dev hardware (pyclipper is C++; 200 Minkowski+union at garden vertex counts is small) | >50 ms: check you're not converting through QPainterPath per item (stay in raw coordinate lists until the final path build); check integer scale factor isn't absurd (1000 is plenty). |

---

