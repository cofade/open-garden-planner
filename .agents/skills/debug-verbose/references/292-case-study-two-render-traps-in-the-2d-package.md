## Case study: two render traps in the 2D package (PR pending, 2026-11-25)

Symptom: a repaint-count gate failed during a rectangle-tool hover with 237
`CircleItem.boundingRect` calls per move (limit 40, baseline ~76). The obvious
suspects — the new group rotation handle, the sprite cache key change, a
BSP regression — were all wrong: disabling only `_schedule_sprite_prefetch()`
made the test pass in 1.4 s.

Key evidence: the gate counts calls across a hover, so the number came from
extra full paints, not from the tool. `_drain_sprite_prefetch` had called
`viewport.update()` after every batch. The paint then queued the next zoom
level again — including entries already cached — so the timer repainted
forever. A second, older trap in the same package: a deduped SVG `<use>` with
absolute x/y moved the balcony's sprites, which only the PNG-vs-SVG fidelity
test saw (mean difference 6.29, limit 5.0).

Root cause: "the next level" was queued unconditionally, and `<use>` was
written as if it placed a picture at the origin. Cachedness and the referenced
element's own x/y were not part of either model.

Lesson: a background prefetch is a state machine with two obligations — queue
only uncached work, and never make its own consumer repaint. And a file
transform that "looks equal" must be rasterised: a payload-count assertion
passes on a misplaced `<use>`. Pinned by
`tests/integration/test_canvas_repaint_package.py::test_rectangle_tool_hover_and_drag_do_not_walk_whole_plan`,
`tests/unit/test_sprite_raster.py::TestNextLevelPrefetch` and
`tests/integration/test_svg_export_fidelity.py`.
