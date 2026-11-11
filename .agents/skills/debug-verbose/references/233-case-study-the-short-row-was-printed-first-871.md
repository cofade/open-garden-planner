## Case study: the short row was printed first — the page loop started at the plan's top, and the top held the remainder (#871, fixed 2026-11-11)

**Symptom**: a 1:50 print of the family garden put the short tile row on sheets 1
and 2; both sheets were blank below their strip of plan. The page count and the
legend were right, and every tile contained the plan it covered, so nothing looked
"empty" in a unit test that only checked ink inside a tile.

**Wrong theories**:
- *"`tile_grid` counts the rows wrong."* It only returns counts
  (`ceil(canvas_h / tile_h)`), and the count matched the printed pages.
- *"The printer's margin eats the remainder."* The margin and fitted scale were
  already pinned by #836; the blank area was inside the content frame.
- *"The tile is centred and the blank belongs above and below."* The target rect is
  top-aligned; the blank was below.

**Key evidence**: `_render_scaled` mapped page row 0 to `scene_row = rows - 1 - row`
— the plan's topmost row. When `canvas_h` is not a whole number of tiles, that row
is the SHORT one (`min(tile_h, canvas_h - (rows-1)*tile_h)`). Pages were ordered
top-to-bottom, but the geometry anchored the remainder at the top. The existing test
computed the expected tile height with the same `rows - 1 - row` formula, so it
encoded the defect instead of catching it.

**Root cause**: page order and scene-row order were derived by two different
mental models (reading order vs. Y-up remainder). Neither was wrong alone; together
they put the remainder where the reader starts.

**Fix**: rows are anchored at the TOP of the plan. Page row `r` takes
`top = max(0, canvas_h - r*tile_h)` and `bottom = max(0, canvas_h - (r+1)*tile_h)`,
so page 1 is a full row and the last page carries the remainder at its bottom. The
test now asserts the last painted row of page 1 is lower on the sheet than page 2's,
i.e. the short sheet is last.

**Lesson**: a test that recomputes the implementation's formula cannot catch a
wrong formula; assert the user-visible relation (first page is full, last is short)
instead. And a multi-page print has two orders — reading order and scene Y — that
must be written down separately.
