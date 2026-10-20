# Archive 10: Phase 17 L1.8 selection, info card and walk

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

### 11.4.19 What selection, the info card and walk mode taught (Phase 17 L1.8, #385)

Symptom → root cause → fix, for the things that cost time (ADR-060 addendum, §8.29.8). The
engine's own facts are in the `ogp-3d-renderer` skill, §15.

1. **Selecting an item made the next Ctrl+click clear the selection.** *Symptom* (the render
   tier's first run on the real engine; the default tier was green): plain click on A → {A};
   Ctrl+click on B → {} ; Ctrl+click on B again → {B}. And two `QTest` warnings, "Mouse event at
   … occurs outside target window". *Root cause:* the info card appeared below the view with
   the selection and took 152 px from it. The view's vertical field of view is fixed, so the
   picture was re-scaled; B was no longer under the pointer, the click met the lawn, and a click
   on nothing clears. *Fix:* the card has a place of one height (`View3DCardSlot`), and the
   eye-height box kept its room while hidden (the strip grew 4 px in walk mode; since fix round 1
   the eye height is a menu on the Walk button — a box beside it made the strip's row wider than
   a 455 px pane, and the workspace's notices were cut). *Lesson:* in a
   pane that holds a native 3D view, anything that comes and goes is a resize of the view —
   reserve its room, and pin the view's rectangle in a test. A stand-in host has no picture and
   cannot see this; only a real click on a real frame can.
2. **The ring was invisible from above on OpenGL.** *Symptom:* none on the dev box (Direct3D) —
   found by running the ring scenario once with `QSG_RHI_BACKEND=opengl`: 0 ring pixels in every
   top-down frame, 587 in the perspective frame. *Root cause:* "in front" was written as
   `POSITION.z *= 0.01`. Where clip z runs 0..1 that pulls a fragment to the near plane; where
   it runs −1..1 it pulls it to the MIDDLE of the range — and in an orthographic view from
   4,000 cm the ground lies in the near half. In a perspective view nearly everything lies in
   the far half, which hid it. *Fix:* `mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, 0.01)`.
   *Lesson:* a shader that touches clip space is run on both depth conventions; the Windows dev
   box can do that.
3. **A depth-tested ring of a wall is inside the wall.** A WALL is built 30 cm thick on whatever
   stroke the plan drew; the footprint's outline is 12.5 cm inside the masonry on both sides.
   Measured from above: 3.6 % of the outline visible. The same fact stops a walker that
   collides with footprints 12.5 cm inside the wall. *Lesson:* the footprint is the plan's
   truth, not the picture's; whatever must agree with what the user SEES asks the builder.
4. **Every selection change costs a whole-plan snapshot.** The canvas repaints a selected item,
   the scene emits `changed`, and the pipeline's controller cannot tell a repaint from an edit:
   120 of 120 selection changes rode a pass that took a snapshot (3.6 ms on the small bench
   plan, 14 on the large). The ring itself needs none. Not fixed here — it is the pipeline's
   rule ("every `changed` marks the plan dirty"; the workspace story's plan revision is the
   fix) — and reported. A strict-`xfail` test asserted zero snapshots; it XPASSED when the plan
   revision landed (re-measured 2026-10-19: 6 snapshots for 4 selection changes before, 0 after)
   and its mark is gone.
5. **The canvas does not treat Shift the same everywhere.** A Shift+click on an item toggles it.
   A Shift+click THROUGH a locked item acts as a plain click: the select tool's Shift branch
   looks at the top item only, finds it locked, and falls into the plain path, which replaces
   the selection. 3D toggles in both cases. Reported as a defect of the canvas.
6. **A test of the workspace raced its first pass.** `open3d()` waited 80 ms and then cleared the
   sink's call log; on a busy machine the first pass came later and its calls were counted as
   the selection's. *Fix:* wait on the condition — `controller.apply_count >= 1 and not
   controller.dirty` — never on a duration.
7. **A hidden pane is not a clean controller.** "Select while 3D is hidden, show it, expect ONE
   ring call" failed: the canvas repaint had marked the plan dirty too, so the catch-up was a
   full pass (correct), and the "Building the 3D view…" notice showed for it. Assert what is
   sent, not that nothing else is owed.
8. **`print` with an arrow failed under `-s`.** A measured line containing "→" raised
   `UnicodeEncodeError` on the Windows console's cp1252. Measured lines are ASCII.
9. **A brute-force judge can be the slowest thing in the suite.** Checking 20,000 walker
   positions against 32,548 segments one by one took about 100 s per plan. In runs of 256
   positions against the segments within reach of the run's bounding box — still no grid, still
   every candidate segment — it takes 3 s.
10. **A guessed bound is not a measured one.** Three first-draft assertions were wrong about the
    code they tested: "more than a kilometre walked" (841 m), "no step longer than v·dt" (a push
    out of a corner adds 0.03 %), "more than 120 triangles hit" (112). Each was replaced by the
    measured number with its margin, and the measured number stands in the test.
11. **A selection change did not reach the engine, once.** WARP, the first run of the render
    tier's timing loop: 119 of 120 arrived within two seconds, and the ring was loaded 121
    times instead of 120. Not seen again in 3,240 changes on WARP and 480 on the GPU, with and
    without load on the machine. The cause is not known. The driver now records every pass of a
    change that misses (what was selected on the canvas, what the sync wished and sent, the
    ring loads), so the next occurrence explains itself. Stated as an open doubt, not as fixed.
12. **"The document was replaced" comes BEFORE the old document goes** (found when master's
    #428 mechanism, `CanvasScene.document_replaced`, replaced the main window's hand-called
    hook). The workspace's slot used to read the canvas selection "for the new document" —
    and at that moment the old items are still in the scene and still selected. It did no
    harm only because Qt's `clear()` / `removeItem` then emit `selectionChanged` for every
    removed selected item (measured: a mutant that keeps the read passes the same test). *Fix:*
    the slot reads nothing of the scene and empties the ring's wish. *Lesson:* a slot of a
    "replaced" signal must not read the thing being replaced; a test that passes on both
    versions is a pin of the outcome, not of the fix — say so.
13. **Five lists, five ways to select an object by its id.** The Diagnostics, Canopy and Guilds
    panels walked `parentItem()` to a group, the plant search took the item as found, the 3D
    list used the canvas's click rules — each with its own resolver. They agreed only because
    every group in the app is a `QGraphicsItemGroup` (whose `setSelected` hands the selection
    to the group) and a locked item's `setSelected(True)` does nothing. *Fix:* ONE path,
    `ui/canvas/select_by_id.py`. *Lesson:* a behavioural test cannot tell two copies that
    happen to agree from one path; pin the structure as well (§8.10.12).
14. **Every mutant read BROKEN after the suite went parallel.** The three L1 mutation scripts
    (`scripts/mutation_check_scene3d.py`, `…_built_world.py`, `…_plant_art.py`) run
    `pytest <tests> -q -x`; with master's `-n auto` in `addopts` (ADR-058) a failing test under
    `-x` ends the run as "interrupted" — exit code 2, not 1 — and the scripts count only exit 1
    as KILLED. Measured: a mutant whose tests failed 5 times read "BROKEN … 0/1 mutants
    killed". *Fix:* each script passes `-n 0` (a later `-n` wins). Found while two of the
    scene3d mutants had gone STALE: L1.8's selection lines sat inside their patterns, which
    the default run reports (`test_every_mutant_still_matches_its_file_exactly_once`); both
    re-anchored, and the new lines got mutants of their own. *Lesson:* a tool that reads an
    exit code must be re-checked when the runner's defaults change — run one mutant whose kill
    is certain.
15. **In walk mode S toggled Snap to Grid and never moved the walker** (review 1, P0). *Root
    cause:* Qt sends `ShortcutOverride` to the view's window before it looks for a shortcut;
    the walker took only `KeyPress`, and the 3D view is embedded, so the main window stayed the
    active window and its `S` shortcut fired. W A D and the arrows worked only because no
    shortcut sat on them. Every test passed: they called `eventFilter` by hand, which has no
    shortcut map. *Fix:* claim `WALKER_KEYS` at `ShortcutOverride`; deliver test input through
    Qt (§8.10.12). *Lesson:* a key filter in an embedded window owns a key only if it owns
    its `ShortcutOverride`.
16. **"Walk" left the keyboard on the plan** (review 1, P1-2): W then picked the Wall tool and
    Escape went to the canvas. *Fix:* `Quick3DHost.focus` (`requestActivate`), measured on the
    real window; the focus goes back on leaving while the view still has it.
17. **Ctrl+click on a locked item with nothing behind it cleared in 3D; the canvas keeps the
    selection** (review 1, P1-1). The bridge was told only "toggle"; Qt's own rule is that a
    Ctrl click on an unselectable item changes nothing, while Shift (the select tool's)
    and a plain click clear. Measured rows pin both now.
18. **A look in walk mode could select** (review 1, P2-4): walk mode kept every move to itself,
    so the orbit filter never saw a flick of up to 4 px within 0.4 s and picked on the
    release. Now a left drag turns only past the click's slop, and a drag that turned cancels
    the click.
