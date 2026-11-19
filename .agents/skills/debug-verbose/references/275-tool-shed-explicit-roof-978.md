# Explicit roofs could lose the tool shed's 2D drawing (PR #978)

- **Symptom** — Flat, hip and gable roofs disappeared when selected on a tool shed. A single slope retained its shading gradient.
- **Initially plausible** — The shape failed triangulation or a stale repaint replaced the sprite.
- **Evidence** — The isolated 2D raster probe counted 29,562 nonwhite pixels in Automatic and zero in Flat, Hip and Gable. The four property-edit cases also failed to match the roof fill after saving and reopening the plan.
- **Cause and fix** — The sprite-backed rectangle installed an empty brush and pen. An explicit roof uses the same stored styles as other buildings. Refresh the styles as part of the roof-style command so undo can restore the sprite.
- **Pinned by** — `tests/integration/test_house_roof_ridge.py` selects each explicit style in the Properties panel, compares the rendered fill, and checks undo, redo and reload.
