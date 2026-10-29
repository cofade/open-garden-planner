## 17. The built world complete on the engine (L4)

Concept: docs §8.29.12; decisions: ADR-065; lessons: PF-L3D-11, PF-L3D-12. Measured on the
RTX 4070 (Direct3D 11), 2026-10-26:

- **Relief on the painted ground is a `ground_detail` part** (`MeshPart.ground_detail`): a
  Model with `groundDetail: true`, never pickable, no shadow, and the item stays painted by the
  bake. The "ground alone" gates take it off (`ground_bake_render_driver._without_relief`):
  they judge the tiles, and stones, water and blades stand on them.
- **Lawn blades are one Model per lawn**, admitted only for High/Ultra (#607).
  `LookController.preset_changed` updates the controller's admission flag; the existing
  scene diff adds/removes the blade geometry on a quality change. Offscreen admission
  uses the same `without_lawn_blades` rule. Lawn blades use `lawn.frag`, whose normal
  faces upward (#604); plant grass retains its original material. Wind still sways both.
- **Detail normals are a material switch, not a texture:** `materials: root.detailNormals > 0.0
  ? [tileDetail] : [tileFlat]` on the ground tile; `tileDetail` is `ground.frag` with the tile's
  own `Texture` as a `TextureInput` (one Texture per tile for life, PF-L3D-04, unchanged).
- **The scene file's look defaults ARE `NEUTRAL_DAY`** (High): `lawnBlades: true`,
  `detailNormals: 3.0`, inside the look block (`test_quick3d_qml.py` holds them to the mapping).

**Not measured (L4):** the blades' fill-rate cost at Ultra on a weak GPU (they are bounded at
60,000 per plan, 180,000 triangles); the detail normals at grazing angles under the looks'
post effects.


### Qt 6.11 selection witness (#600)

The engine picker accepts only front-facing triangles even for a NoCulling
foliage material. At one birch ray the two mesh hits had determinants -903.39
and -923.48; Qt selected nothing. The tagged
[v6.11.0 triangleIntersect source](https://raw.githubusercontent.com/qt/qtquick3d/v6.11.0/src/runtimerender/qssgrenderray.cpp)
accepts positive determinants and comments out the back-face branch. Test-only
`workspace_render_state.front_facing_oracle` filters camera-facing triangles
from the admitted mesh. General collision/analysis rays remain two-sided. An
explicit Qt 6.11 guard requires recharacterization on upgrade; Qt 6.12 changes
the material/picking contract. Eighty seeded clicks retain the minimum 45
robust comparisons. Restore minimized test windows before entering 3D: the
product correctly pauses both records and forge work while minimized.
