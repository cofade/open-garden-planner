## Case study: the ground drew mirrored north–south under the detail-normal material (#388, L4.5)

**Symptom.** With the ground tiles switched from the flat `PrincipledMaterial` to the new
`CustomMaterial` (`ground.frag`, detail normals from the tile's own luminance), a top-down
frame of the plan showed every painted surface mirrored north–south inside each tile:
paths and beds lay where the bake had them on the opposite side.
**Wrong theories.** None was needed: the change touched only the material, so the control
was the same `Texture` drawn through the flat material, which matched the bake.
**Evidence.** The same tile, the same `Texture` with `flipV: true`, two materials: the
`PrincipledMaterial` frame agreed with the bake; the `CustomMaterial` frame sampling
`texture(uBaseMap, UV0)` agreed with the bake flipped north–south.
**Root cause/fix.** `flipV` is applied by `PrincipledMaterial`'s own texture lookup, not
to a `TextureInput` a custom shader samples. `ground.frag` now samples at
`vec2(UV0.x, 1.0 - UV0.y)`, and its "north" neighbour is `-texel.y`.
**Lesson.** A `Texture`'s properties are instructions to the built-in materials. When a
custom material takes over a textured surface, re-run the orientation gate on the new
material. Here the north-up render gate runs at the High preset, so it judges the custom
material. Pins: `tests/integration/test_scene3d_ground_render.py::test_the_engine_shows_the_bake_north_up`,
`tests/unit/test_quick3d_qml.py::test_the_ground_detail_shader_flips_v_itself`. PF-L3D-11.

