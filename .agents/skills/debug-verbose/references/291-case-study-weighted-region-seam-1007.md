# Case study: one sample of sun vanished at a weighted-region seam (#1007)

**Symptom.** On the hours-of-sun map, one or two cells per plan-day read one
15-minute sample darker than their neighbours, always in the narrow band at the
edge of a porous object. The solid map of the same plan did not show it. The
report came from a survey of the bundled examples and named the seam between
the weighted raster's regions.

**Wrong theories (all disproved).**

1. *A half-open edge rule in the reference rasterizer.* The reference's
   point-in-polygon rule and QPainter could disagree on a cell centre exactly on
   an edge — plausible, and the issue suggested it. It explained some cells, but
   not the ones the map darkened: those were inside a region by both rules.
2. *The union polygon is missing a bite.* Checked by rasterizing the union and
   comparing it with the OR of the region masks. In the family garden two cells
   at one sample disagreed only in the **owner** raster (not the union), so the
   union was not the missing piece.
3. *A sample-centre offset in the QImage rasterizer.* `painter.scale(1/cell)` +
   `translate(-x0)`, then a pixel centre at `(c+0.5, r+0.5)` is exactly the grid
   convention. A 1/64-px painter offset reduced the ambiguity but did not
   remove it, and it changed boundary cells globally. Rejected.

**Key evidence.** For one sample of the family garden, rasterizing each
`WeightedShadowRegion` separately and summing the booleans produced
`cover_count > 1` at some cells: region 0 (`t=0`) and region 4 (`t=0.567`) both
painted one cell whose centre the point-in-polygon rule placed in region 0. At
other samples `cover_count` was 0 while the union painted the cell. The pattern
was always a cell centre exactly on a region boundary: QPainter classifies a
pixel by the **path** that painted it, so two disjoint polygons sharing an edge
can both claim that pixel — or neither can. `min()` over the regions then made
the cell once darker than the darker neighbour; a miss made it once lighter.

**Root cause.** The weighted path paints every transmittance region on its own
(one path over all of them would let odd-even filling cancel where regions
meet). At a seam, the presence of a cell was decided by the painter's edge
tie-break, not by geometry. The solid path never had the problem: it paints one
union, one path.

**Fix.** `_weighted_sun_factor` takes **presence from the union** — the one path
the solid sweep has always painted — and settles a seam cell by the even-odd
point-in-polygon rule at its centre (darkest region that contains it). The seam
cells are found from the region-id map (a cell whose id differs from any
neighbour's), so only a handful of cells per sample get the geometric pass.
A single-region map skips both the union paint and the seam pass.

**Lesson.** When two implementations rasterize the same geometry in different
groupings, the raster is not a pure function of the geometry: an edge exactly
through a pixel centre is decided by the path. Pin the *one* grouping that has
the authoritative answer (the union), and resolve only the cells where the
groupings disagree. Do not tune the sample offset: it hides the seam by moving
every boundary cell.

**Pinned by.** `tests/unit/test_weighted_seam.py` (a fake painter that
double-paints one seam column and misses two, held to geometry and union
presence) and
`tests/integration/test_open_frame_shade.py::test_every_sample_of_a_two_region_plan_keeps_the_unions_presence`
(two touching frames, every sample of a day).
