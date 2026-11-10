# What built parts are made of — surfaces, roof tiles and wall pictures (#801, #803)

The values #801 and #803 gave the built world (`core/scene3d/materials.SURFACES`,
`builders/roofs.py`, `qml/built_detail.*`, `qml/water.frag`) and the reasons they hold.
Truth first: no geometry moved — stored normals, heights, footprints and every roof's IoU are
the builders' as before (the roof's uvs ride in the slot every vertex already had), and a
surface's picture keeps its mean colour (PF-L3D-35), so the board's colour, shadow and IoU
gates did not move.

| Surface | Roughness / specular | Picture | Why |
|---|---|---|---|
| default | 0.78 / 0.35 | — | the look every built part had before #803: a raised surface's sides, the plain block, a plant's wood |
| rubber, canvas | 0.95 / **0** | — | specular OFF: Qt keys a principled material's specular in only above 0.01 and its grazing Fresnel reaches 1 whatever the amount (PF-E3D-32) — the issue's 0.05 left the mat tan (luma 62.8 against 25.4) |
| plastic | **1.0** / 0.20 | — | the pad facing a 15° sun: 8.0° off its 2D blue at 1.0, 9.3° at 0.95, 11.5° at 0.85, 31.7° at the issue's 0.55 |
| wood | 0.75 / 0.25 | — | §4 wood 0.60-0.80 |
| steel, iron, enamel | 0.45 / 0.50, 0.60 / 0.35, 0.60 / 0.15 | — | §4 aluminium 0.30-0.50; a black grill's enamel at 0.45 / 0.40 read 1.74x its specular-free luma facing the sun, at 0.60 / 0.15 1.40x |
| terracotta, stone, concrete, soil | 0.85 / 0.20, 0.90 / 0.15, 0.90 / 0.15, 0.95 / 0.10 | — | §4 ranges |
| glass pane (an opaque window in a facade) | 0.40 / 0.40 | — | it mirrors the sky: brighter and bluer-grey than before (luma 43 → 85 at golden hour) |
| roof tile | 0.80 / 0.15 | `ROOF_TILES`, the mesh's uvs, 256 cm a picture, normal 1.5, contrast 0.6, fade 40 m | the 2D roof's own tiles, size and phase (below); at full contrast 15 % of the noon roof clipped red |
| shingle | 0.80 / 0.15 | `SLATE`, uvs, 100 cm a picture (rows of 20 cm), normal 1.5 | a shed's roof; the canvas has no shingle picture, its slate is the nearest |
| plaster | 0.90 / 0.15 | `CONCRETE`, the face's plane, 128 cm, normal 1.0, contrast 0.85, fade 20 m | a house's render; §4 plaster 0.85-0.95 |
| masonry | 0.90 / 0.15 | `STONE`, the face's plane, 256 cm (43 × 26 cm blocks), normal 2.0, contrast 0.8 | a garden wall (a WALL line, a stone-wall fence) — the balcony's navy slab |
| wood cladding | 0.80 / 0.20 | `WOOD`, the face's plane, 128 cm (16 cm boards), normal 1.5 | a shed's walls, in the item's colour |

**The tiles' size and direction.** The canvas lays its 256-px roof picture at 256 cm (1 px =
1 cm): its tiles are 16 cm wide and 21.3 cm a course IN PLAN (the issue's "25 cm along the
eave, 18 cm up the slope" was not the picture's scale). A gable's uvs are the 2D brush's frame
— u along the ridge from its middle, v the plan distance from the ridge, the far half mirrored
as the canvas mirrors it — so seen from above the 3D roof IS the plan's picture; on a 38° slope
a course is 27 cm long, as a real tile is longer than its shadow on the plan. A hip's faces and
a shed's plane run along their own eave and down their own slope; the canvas draws no hips, so
there only the size and the lap direction agree.

**Measured** (RTX 4070, high): the noon roof (1280 × 720 close-up) luma std 1.8 → 12.5, its
mean 153.9 → 152.8 (render tier, 640 × 360: −0.6 %, 0.0° hue); at a 15° sun std 2.5 → 7.7,
mean 34.3 → 36.1 — a grazing sun lights the tiles' edges by their detail normals, so a low-sun
roof reads 1-2 luma lighter than the flat one. The walls on their shaded side at golden hour
(render tier, the box all wall): masonry std 1.2 → 7.0, plaster 0.8 → 2.1, cladding 1.2 → 7.3;
the balcony's wall (1280 × 720) 2.8 → 7.5.

**Judge a material against its own specular-free frame (PF-L3D-34).** Facing a 15° sun, the
light alone moves a part's hue off its 2D colour: a plaster wall 27.6°, a red canvas 12.8°, the
mat's near-grey has none to keep. What a material must not do is repaint or wash out the part:
every chromatic surface within 4.2° of its specular-free look, every matte one at most 1.43x
its luma (the render tier's class row). With every surface back at 0.78 / 0.35 the mat read
4.08x and 128° off — the tan of the survey — and the pad 1.52x and 13.8°.

**Weather.** A part with a picture takes the ground's rain darkening (`groundTint`) and the
rain's roughness / specular shift from the dry ground's (`wetRoughShift`, `wetSpecularShift`:
−0.2 / +0.1 under rain), and the living garden's snow on what faces up (`builtSnow`, the rule of
`built_snow.frag`: smoothstep(0.35, 0.75, NORMAL.y), the relief filled under it). Bound to the
ground's own cover (0.75) a terracotta roof read pink.

**The pond's glint** is GGX soft-capped at 0.6 / exposure (`water.frag`): a believable bright
glint (peak luma 213-237 at the mirror angle of a 10-30° sun), no clipped blob.

Taste calls left to the owner (none of these was said by the owner): the plaster's speckle (the
canvas's concrete picture) against a smoother render; the masonry's dark joints in shade; a
grey "concrete"-filled garage shed boarded like a tool shed (a shed's walls are always
cladding); plastic fully rough; windows that mirror the sky; a low-sun roof 1-2 luma lighter
from its tiles' lit edges.
