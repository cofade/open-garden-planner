---
title: "Built world in 3D"
prefixes: ["FR-3D-BUILT"]
---

# Built world in 3D

Furniture, structures, buildings and surfaces in 3D (#388, ADR-065).

- **FR-3D-BUILT-01** (L4.4): Every furniture, play, utility and structure object
  (24 kinds: rectangular and round table, picnic table, chair, bench, lounger,
  parasol, barbecue grill, fire pit, planter pot, sandbox, trampoline, hot tub,
  swing, hammock, compost bin, cold frame, rain barrel, water tap, wheelbarrow,
  bird bath, pergola, trellis, greenhouse) is shown in 3D as a model of the thing,
  in the colours of its
  2D sprite and turned as its sprite is, no longer as a picture on the ground. Its
  top is its height on the plan; nothing of it reaches more than 10 cm past its
  footprint. Every object has a default height, shown and editable in its
  **Object height** field, and casts its shadow in 2D and 3D: also the parasol
  (250 cm), fire pit (30), planter pot (50), cold frame (45), rain barrel (100),
  water tap (80), swing (220), hammock (110) and pergola (250), which had none
  before L4's owner passes. In 2D an open frame (pergola, trellis, swing, hammock,
  garden light) shades its footprint prism in part: it is weighted by its transmittance
  since #698 (FR-SUN-13), as a picket, metal or chain-link fence is since #440; a parasol
  shades a raised canopy slab at its own height and a greenhouse its frame alone
  (#830, FR-SUN-16); a string of lights casts none, FR-3D-LIVE-08). A house is drawn in 2D in the terracotta of its 3D roof
  tiles; its 3D walls are sandstone, whatever the house's 2D colour (a house
  recoloured in 2D before L4 no longer shows that colour on its walls).
- **FR-3D-BUILT-01a** (#769, parametric pergola): A **Pergola** is drawn as a
  scalable rectangle and painted and built from ONE layout
  (`core/pergola.py`): four posts carrying a perimeter of four beams, nine
  rafters across the depth and five purlins on top. The purlins' top is the
  item's height; every member's size is bounded (posts ≤ 14 cm, beams ≤ 18 cm
  deep, rafters ≤ 8 cm wide), so a 12 m pergola is still timber, not a block.
  The canvas picture, the gallery thumbnail and the 3D frame read the same
  layout, so the 2D posts/rafters and the 3D ones cannot drift. No pergola
  sprite ships (the former fixed `pergola.svg` is retired).
- **FR-3D-BUILT-01b** (#768, parametric glasshouse): A **Greenhouse** is a
  first-class ridge-bearing building: drawing a polygon or converting a shape
  creates the same linked `ROOF_RIDGE` a house gets (`core.roof_ridge`), and the
  ridge is anodised aluminium (`#B0B5B9` / `#9EA3A8`) rather than the house's
  brown. The canvas paints the glass fill plus aluminium glazing bars at the
  same ~60 cm bays the 3D frame uses (`core/greenhouse.py`); the 3D builder keeps
  the framed glasshouse when the live ridge is the footprint's natural long
  axis, and otherwise builds the plan's own ridge as a glass gable roof. The
  former fixed `greenhouse_gabled` smart symbol is not needed.
- **FR-3D-BUILT-01c** (#776, sprite orientation): An illustrated object's
  picture TURNS with its footprint instead of being squashed. When the sprite's
  natural aspect and the item's rectangle are opposite (a portrait wheelbarrow
  on a wide rectangle, a landscape bench on a tall one), the 2D renderer draws
  it at the swapped size and rotates it a quarter clockwise, and the 3D builder
  builds the same turned model (`core/sprite_orientation.py` is the one rule).
  Near-square art or near-square targets never turn; a polygon whose local
  bounding box has the opposite aspect turns too.
- **FR-3D-BUILT-02** (L4.1): A house, garage or tool shed has **Roof style**
  (Automatic, Gable, Hip, Single slope, Flat), **Roof pitch** (Auto, 5–60°) and
  **Roof overhang** (Auto, 0–150 cm) in the Properties panel. Each change is one
  undo step and is saved with the plan; Automatic / Auto removes the value. The
  roof's highest point stays the building's height, so a steeper pitch lowers the
  eaves. Automatic is a gable along the house's ridge line, or a flat roof on a
  house without one. A hip on an outline that is not convex is built as a gable.
  An overhang never takes a roof edge lower than half the lowest eave the walls
  may have (2.2 m, or three quarters of a lower building's height under its roof
  slab) above the ground: at a steep pitch on a small building the overhang is
  shortened, and the chosen style and pitch are kept. A building too low even for
  that (a gabled house 18–22 cm tall) keeps its roof without an overhang.
  The plan draws the chosen roof within the building outline. Gables use two
  mirrored tile planes, hips show their eave-to-ridge seams, single slopes
  fall from the high eave, and flat roofs show one surface. Automatic
  garage/shed roofs use the long axis of the footprint. New garage/shed
  objects default to gray roof tiles. Saved fill choices also apply to the
  roof on the plan. In 3D an explicitly selected Flat roof uses the item's
  fill on its top face and keeps the slab finish on its edges and underside.
  An automatic flat house roof keeps the concrete slab finish. The roof-aware
  sun study uses the 3D roof geometry including pitch and overhang (FR-SUN-03).
- **FR-3D-BUILT-03** (L4.1, #965): A building has windows on its walls and a door on the
  wall that faces the nearest path (a garage: the nearest driveway, then path).
  On the door's wall the windows are spaced on each side of the door, so a long
  wall with its door in the middle has a window either side, and an upper row runs
  over them and over the door. Moving the building along its path does not move its
  door to another wall. A building too low for a door has no door or window. A
  flat-roofed house uses contemporary wide, tall, single-pane dark-framed windows
  and a modern door rather than cottage crossbars (#965).
- **FR-3D-BUILT-04** (L4.2, #961): A path shows its style on the 3D ground: stepping
  stones where the plan draws them, boardwalk planks, paving kerbs, a gravel path's
  edging. A gravel path is the gravel texture and a dirt path the soil texture, in
  the path's colour and opaque, in 2D and on the 3D ground alike (owner, L4 manual
  pass: they were translucent strokes the lawn showed through); a new dirt path
  starts in the 2D sprites' light soil colour. A terrace or driveway shows kerbs, or deck boards for a wood pattern;
  a formal pool (rectangular, circular or raised) shows water inside a stone coping,
  while an organic multi-vertex ground pond (5+ vertices per ring) shows a smoothed
  flush low earth shore (strictly below deck height) and darker natural water (#961). All of this lies on the plan's painted
  ground, casts no shadow and cannot be clicked: a click on it is a click on the
  ground, as on the flat surface before L4. A surface given a height is a raised solid with that top.
- **FR-3D-BUILT-05** (L4.2): A path's width is its width on the ground in cm. New
  paths start 70–100 cm wide by style (80 cm without one), and the Properties panel
  sets a path's width up to 500 cm, a fence's or wall's up to 100 cm. Saved plans
  keep their widths.
- **FR-3D-BUILT-06** (L4.5): At the High and Ultra presets, a lawn grows grass
  blades that sway with the wind. No blades grow under a path, terrace or bed drawn
  on the lawn, under a pond's coping, past a gravel or dirt path's round ends, or
  inside a house, shed, garage or greenhouse standing on it; they do grow under a
  pergola, parasol, swing or hammock, and inside a loop of path. A plan grows at
  most 60,000 blades in all; a large lawn is sparser rather than slower. While an
  item is dragged over a lawn, its blades are cut anew at most every 0.4 s. Low and
  Medium do not synthesize or upload blade geometry; changing quality updates that
  admission through the scene diff (#607).
- **FR-3D-BUILT-07** (L4.5): From the Medium preset up, the 3D ground is shaded by
  the relief of its own textures (paving joints, gravel, bark), with no new picture
  of the ground and nothing mirrored.
- **FR-3D-BUILT-08** (L4, owner manual pass): The haze over the 3D view begins
  beyond the plan the camera frames: it starts at 1.5 times the camera's distance
  to the point it looks at and is full at 6 times it, never nearer than 26 m and
  160 m, and full by 760 m, before the view's far limit, so the meadow's end never
  shows against the sky. That holds up to 380 m from the point looked at; farther
  out (the camera reaches 600 m) the haze begins at 570 m, so a camera pulled out
  to its limit sees the plan through thin haze.
- **FR-3D-BUILT-09** (#628 follow-up, owner manual passes of #627): An item that has a
  height is a solid, and the solid shows the item's own **fill** on its TOP: its
  fill pattern tinted with its fill colour, or that colour alone for a SOLID fill -
  exactly the picture the ground bake painted while the item lay flat. Its SIDES
  are the item's colour, not the picture (the canvas paints no texture down an edge;
  one fill-textured prism smeared a lawn's grass and a bed's soil down the walls).
  The item keeps its RELIEF as well: a raised lawn still grows its sward, on the new
  top (the height gates measure the solid, not the blades). This covers the kinds a
  height was newly reachable for (a lawn, path, terrace, driveway, generic shape, and
  a garden bed whose soil cap is its "Boden-Substrat", not a builder's palette soil
  colour); a raised DECK keeps its boards instead, and a raised pond its water — the
  plan's water picture, sampled by the water shader, lit and reflecting as water.
  The picture is cached per (pattern, colour) and shared, so a recolour is a material
  update and a removed object leaves no picture behind. Not shown while X-ray fades
  an object: a faded solid is a screen door of its colour.
- **FR-3D-BUILT-10** (#955): A **GENERIC_POLYGON with the STONE fill and a height** is a
  **rock**: a low upright base (15 % of its height), then a domed, faceted top carrying
  the canvas's stone picture (three rings at 0, 42 and 78 % of the height, the widest at
  the ground, narrowing to one exact peak with a smooth normal per vertex). A per-record
  ring-scale jitter of 0.92–1.0 keeps the rocks from being clones while every ring stays
  inside the convex footprint. Its top is still the plan's height and it stays on its
  footprint. A convex outline of at most 512 vertices is a rock; a concave or hostile
  one keeps its honest prism; every other fill is the plain prism. In 2D the plan keeps
  its stone picture. Pinned by `tests/unit/test_scene3d_rock.py`,
  `tests/integration/test_example_plans.py::test_the_japanese_garden_builds_its_rocks_moss_and_raked_sand`,
  and the rock in `tests/fixtures/plans/bench_built.ogp`.
- **FR-3D-BUILT-11** (#960): **Board Fence** is a fence style of its own (`PathFenceStyle.BOARD_FENCE`,
  category fence). In 3D it is a closed timber screen: vertical boards pitched 14.6 cm with
  a 0.25 cm weather gap, from the ground to just under the post tops, stout posts and one
  rail behind the boards. In 2D it is the drawn panel with vertical seams and stouter posts.
  A file that names the style opens in an older release as its default fence; the style is
  additive and no `FILE_VERSION` changes. Pinned by
  `tests/unit/test_scene3d_builders.py::TestPolylinesAreBuiltFromTheCentreLine::test_a_board_fence_is_a_closed_timber_screen`,
  `tests/integration/test_path_style_export.py`, and the Japanese garden example.
- **FR-3D-BUILT-12** (#960): A **lawn whose fill is MOSS** is an evergreen moss cushion: its blades are
  2.2 cm tall at 1,800 a square metre (`MOSS_BLADES_PER_M2`, wired through `context._blade_shares`),
  dense and low, instead of the lawn's grass; its 2D fill is the hedge texture in the plan's own
  moss colour. Every **terrace, path or other ground surface whose fill is SAND** (including
  existing plans that use `FillPattern.SAND`) is raked in 3D: parallel 13 cm ridges 2.4 cm wide and
  1.5 cm high with alternating 1.0/0.78 shade bands. They follow the court's own outline; a flat
  item painted above the court (a moss island, a path, a bed) stops them, so a tan ridge never
  crosses a green cushion. A stepping-stone path is not a continuous surface: each painted stone
  is its own cut-out, so the rake runs between the stones and stops at their edges. They lie on
  the ground (no shadow, not clickable) and are bounded per
  surface by both rows (`MAX_RAKED_ROWS = 1,000`) and total ridges
  (`MAX_RAKED_RIDGES = 2,000`). Both are additive reads of the fill pattern (no `FILE_VERSION`
  change); plans without `MOSS` or `SAND` fills are unchanged. Pinned by
  `tests/unit/test_scene3d_l4_surfaces.py::test_moss_is_a_low_dense_cushion_and_sand_is_raked`,
  `tests/integration/test_board_fence_and_moss_properties.py`, and the Japanese garden example.
- **FR-3D-BUILT-13** (#956): A **climber trained to a pergola** climbs to the pergola's rafter deck
  and spreads overhead along and inward across the pergola's own rafters, not round the rectangle's
  edge: `plant_forge/climbers.py` asks `core/pergola.py`'s layout for the nine rafters centred on
  the footprint bounding box (`layout(...).rafters`), records the pergola centre in the plant's
  frame, and trains overhead vines along the nearest rafter and laterally across neighbouring
  rafters within the canopy radius, capping mature climbers taller than the pergola at the
  support's top (the rafter deck's height) so vines never hover above the rafters. A young vine
  below deck height stays vertical along
  the post; a pergola too small for the layout keeps its outline, and a trellis/path support is
  unchanged. Pinned by
  `tests/unit/test_plant_forge_l34.py::TestL34ClimberSupportResolution::test_a_climber_on_a_pergola_is_trained_along_a_rafter`.

Acceptance: `tests/integration/test_l4_built_world.py` (§8.10 — the roof
rows through the real panel, undo and a save/load; the door against the path and
a move as a transform; the lawn's cut-outs under a terrace and a greenhouse; a
path's width in cm and its stones; an object without a height), the unit suites
`tests/unit/test_scene3d_l4_objects.py`, `test_scene3d_l4_buildings.py` and
`test_scene3d_l4_surfaces.py` (every builder through `verify_builder` on hostile
input), `tests/integration/test_bench_plans.py` (`bench_built.ogp`), the render
tier `tests/integration/test_scene3d_ground_render.py` and the frozen
`--selftest` (`ground.frag` compiled from the bundle).
