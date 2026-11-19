# Explicit flat roofs lost their fill in 3D (PR #978)

- **Symptom** — The family garden shed and house showed gray roof tiles in the 2D plan and a plain light slab in 3D after selecting Flat.
- **Initially plausible** — Bright lighting or a texture lost in the bundle washed out the tiles.
- **Evidence** — The 3D part probe reported `fill_texture=False` and zero UVs on the slab. In the noon frames, standard deviation of roof-centre luminance was below 0.6 on both buildings. With the fill on the cap it reached 16.2 on the house and 21.4 on the shed. Both kept their height, extent and 12 roof triangles.
- **Cause and fix** — The Flat branch used the automatic concrete slab material. Give an explicit Flat roof a separate top part with plan UVs and pass the item's fill through the existing material pipeline. Keep the automatic slab finish for houses with no ridge.
- **Pinned by** — `tests/integration/test_scene3d_built_world.py` exercises the Properties and undo workflow. `tests/integration/test_quick3d_render.py` checks the tiled cap against a solid cap on the real renderer. Removing the QML roof texture binding makes that test fail.
