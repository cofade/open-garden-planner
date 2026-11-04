## 15. Selection, picking in perspective, walk mode (L1.8)

Concept: docs §8.29.8; decisions and every number: ADR-060 addendum "selection, info card and
walk (L1.8)"; test patterns: docs §8.10.12; traps: PF-E3D-08. What the ENGINE taught:

- **`View3D.pick()` agrees with a ray caster of our own in the perspective view too.** 400
  seeded view positions per plan, from the orbit camera's own framing, against
  `src/open_garden_planner/core/scene3d/pick_oracle.py` (Möller–Trumbore over the records' posed
  meshes; a camera model of ours — eye, target, vertical field of view, no roll):
  `bench_small` 360 of 360 and `scene3d_edge_cases` 362 of 362 positions OFF the silhouette
  edges agree, the same numbers on the RTX 4070 and on WARP; ON an edge (the oracle's answer
  changes within 1.5 px) 36 of 40 and 38 of 38 — either answer is right there. 0.03 to 0.11 ms
  a pick with 98 Models. Judge picks off the edges only, and say how many were on one.
- **`View3D.pickAll()` is the whole chain, nearest first, one entry per MODEL.** An item of
  several parts is in it several times: keep first appearances per item id. Against the
  oracle's `cast_all`: 349 of 349 and 362 of 362 whole chains equal (34 of them two or more
  items deep, the longest four). `host.pick()` returns the first hit with the rest in
  `PickHit.behind` — ONE call and one probe frame for "the click falls through a locked item".
- **The ground and the sky are not pickable: nothing is `None`.** A click on the lawn clears
  the selection; a flat item (a lawn, a path — no height, no solid) cannot be selected from 3D.
- **A `QQuick3DGeometry` can be re-loaded in place while its Model lives.**
  `setVertexData` / `setIndexData` / `setBounds` / `update()` on the same object: 120
  selection changes in the real workspace re-loaded the ring 120 times into ONE geometry —
  no Model created, `BufferGeometry.uploads` unmoved (`quick3d/geometry.py`,
  `ReloadableGeometry`). §2's
  "one geometry per Model lifetime" is about a geometry that OUTLIVES its Model — the opposite
  case. Give it generous bounds: a vertex shader that moves vertices is culled by the bounds
  of the mesh it was handed.
- **A band of constant width on screen is a vertex shader, not a mesh.** `ring.vert`: every
  outline point three times at ONE position; `UV0.x` = band widths outward along the stored
  mitre normal, `UV0.y` = band widths up; one band width is `uFlat` cm in the orthographic view
  and `depth × uPerDepth` cm in perspective (`2·tan(fov/2) / view height × pixels`). Top-down
  every ring pixel lies within 3.82 px of OUR projection of the outline (bound 3·√2 + 1 =
  5.24) and the outline is covered 100 %.
- **"In front of everything" without a second pass: pull clip z towards the near plane —
  and ask the backend where that is.** `POSITION.z = mix(NEAR_CLIP_VALUE * POSITION.w,
  POSITION.z, 0.01)`. The first version scaled z (`POSITION.z *= 0.01`): right on Direct3D
  (clip z 0..1), and on OpenGL (−1..1) it moves the fragment to the MIDDLE of the depth range
  — behind the ground of the orthographic view: **0 ring pixels in every top-down frame**,
  1,548 with the fix (the perspective frame hid the bug: 587 px either way, because nearly
  all of a perspective scene lies in the far half of the range). Run anything that touches
  clip space with `QSG_RHI_BACKEND=opengl` once — it works on the Windows dev box too. Why in
  front at all: a WALL is built 30 cm thick on a 5 cm stroke; the depth-tested ring of its
  footprint, seen from above, shows 3.6 % of the outline (48 px of 1,548). Cost: the ring
  writes a near depth — a depth-reading post effect will see it.
- **An `Unshaded` custom material still goes through exposure and the tone curve** in the
  perspective view: the canvas blue (0, 120, 215), handed over in linear light, arrives as
  rgb(0, 142, 226) — hue 202.3° against 206.5°. A look that changes the exposure changes the
  ring's brightness.
- **A shader is compiled when something first uses it.** The ring's two shaders compile with
  the first selection — so the frozen `--selftest` selects one swatch (`selftest.SELECTED`)
  and its judge looks for the band; without that a broken `ring.vert` ships and the first
  user to click finds it.
- **Whatever resizes the native view between two clicks takes the second click's aim.** An
  info card that appeared below the view with the selection took 152 px from it; the vertical
  field of view is fixed, so the picture was re-scaled, and a Ctrl+click on the neighbour of
  the item just selected met the lawn and CLEARED the selection. A resize is also a new
  swapchain, and a host between two sizes answers `HostStateError`. Reserve the room
  (`View3DCardSlot`: one height, card or no card; `QSizePolicy.setRetainSizeWhenHidden` for a
  control that comes and goes) and pin the engine widget's geometry in a test. What found
  it: `QTest`'s own warning "Mouse event at … occurs outside target window" in the judge's
  message list.
- **Real input in a test.** `QTest.mouseClick(host._view, button, modifiers, QPoint)` and
  `QTest.keyPress` / `keyRelease(host._view, key)` reach the event filters as a user's do; a
  drag needs its buttons said — `QCoreApplication.sendEvent(view, QMouseEvent(...))`.
- **A key in the embedded view meets the MAIN window's shortcuts first** (fix round 1,
  measured on Windows with the real main window). The `QQuickView` sits in a window
  container, so the main window stays the active window and its window shortcuts are live.
  Qt sends `ShortcutOverride` to the view's window (and then to its active focus item, if it
  has one) BEFORE it tries a shortcut: an event filter on the view that accepts it
  (`event.accept()`, return True) owns the key — the `KeyPress` follows. A filter that takes
  only `KeyPress` lost S to Snap to Grid. To give the view the keyboard,
  `QQuickView.requestActivate()` (or the container's `setFocus()`): afterwards
  `QGuiApplication.focusWindow()` is the view and the container is the focus widget; the
  previous widget's `activateWindow()` + `setFocus()` gives it back. Under the offscreen
  platform the focus window changes at once but its focus events come later — let the loop
  run before the first key.
- **Near plane 5 cm, walk field of view 60°.** The farthest corner of the near rectangle is
  6.94 cm from the eye at 4:3 (`walk.near_plane_reach_cm`; below the walker's 22.5 cm up to
  an aspect of 7:1). Pressed against a 180 cm wall and into an inside corner of two, all
  round in 15° steps, level and ±35°, at 165 and 110 cm: 288 frames, 0 pixels of the marker
  behind the wall. Control: an eye 2 cm in front of the masonry sees 114,560 — back faces
  are culled, so from inside a wall the camera looks out.
- **Walk collision is with what is DRAWN.** The builders make a wall 30 cm thick with a 38 cm
  coping whatever stroke the plan drew; the walker's world is the footprints PLUS the
  plan-view edges of the built meshes between step height (25 cm) and headroom (200 cm).

Running the story's tiers:

```bash
# default tier (no GPU)
venv/Scripts/python.exe -m pytest tests/unit/test_scene3d_walk.py tests/unit/test_scene3d_selection.py \
    tests/unit/test_scene3d_pick_oracle.py tests/integration/test_view3d_selection_workspace.py \
    tests/integration/test_view3d_selection_walk.py tests/integration/test_view3d_walk_bench.py
# render tier, on the GPU and on WARP (about two minutes each)
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_selection_render.py -s
OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest \
    tests/integration/test_view3d_selection_render.py -s
```

**Not measured (L1.8):** a device pixel ratio other than 1 through the real window (the click
is handed over in logical pixels; pinned on the stand-in host only); the ring under L1.4's
looks and post effects; the pick's cost on the large bench plan; walk mode in a frozen exe;
the whole render file on OpenGL (one row runs there: the ring's depth); pointer capture.

