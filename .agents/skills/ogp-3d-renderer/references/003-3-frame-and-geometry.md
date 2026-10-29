## 3. Frame and geometry

- **Frame mapping, exactly once:** scene (E, N, up) → engine (x = E, y = up, z = −N);
  determinant +1, so triangle winding survives. Done in `quick.py`, never in QML.
  The production mapping is `core/scene3d/frame.py` (`scene_to_engine_points` / `_vectors` and
  their inverses, exact column selection). Meshes there are in the **item-local** frame and a
  record's transform poses them: `engine_pose(transform)` gives the Model position
  `(east_cm, base_cm, −north_cm)` and a turn of `+rotation_deg` about the engine's +Y — proven
  equal to posing in the scene and mapping the result (`tests/unit/test_scene3d_frame.py`), and
  **measured on the engine in L1.2**: `eulerRotation.y = +rotation_deg` is the
  counter-clockwise turn seen from above — a 240 × 60 cm bar matched the CPU prediction with
  mask IoU 0.9994 at 17° and 0.9895 at 213.5°, the opposite sense with 0.288 and 0.157
  (`tests/integration/test_quick3d_render.py`).
- **The byte layout is Qt-free since L1.2:** `core/scene3d/interleave.py::engine_buffers(mesh)`
  builds the vertex and index bytes (and maps the frame, once);
  `ui/view3d/quick3d/geometry.py::BufferGeometry` only hands them to Qt — one upload per
  object, no re-upload method.
- **The top-down view is linear (L1.2).** With `TonemapModeNone` a pixel is linear radiance,
  so it can be computed: a lit horizontal face reads `255 × tint × (brightness × sin(elevation)
  × sun colour + fill)`, all in linear light — predicted 167.2, measured 171.
- **Vertex layout, stride 48 bytes:** position f32×3 @0, normal f32×3 @12, colour f32×4 @24
  (**linear**, not sRGB), uv f32×2 @40 (spike convention: u = wind weight, v = phase), indices
  U32; `setBounds` + `update()`.
- **Update cost** of replacing a 100k-vertex geometry (`NumpyGeometry.set_mesh`: frame mapping +
  interleave + copy): median **10.5 ms** (n = 10, max 25 ms; cloud container CPU,
  `--update-bench`), 14–27 ms on Windows runner instances. GO criterion 6 says ≤ 10 ms —
  borderline; measure on the owner box before optimising, and look at the interleave copy
  first.

