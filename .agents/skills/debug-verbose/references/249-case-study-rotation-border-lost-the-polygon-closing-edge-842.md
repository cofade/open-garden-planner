## Case study: rotation border lost the polygon closing edge (#842, fixed 2026-11-14)

**Symptom**: the shared crop-rotation painter coloured three polygon edges but
left the last-to-first edge without a diagnostic border.

**Wrong theory**: a positive changed-pixel count proved the whole outline was drawn.

**Evidence**: the strengthened real-render regression sampled the midpoint of all
four edges and failed at scene point `(100, 175)`, the closing side. The other
three sides changed colour. The independent review's Qt probe confirmed that
`QPainterPath.addPolygon()` left an open subpath; explicitly closing it restored
the missing edge.

**Root cause**: replacing `drawPolygon()` with a no-brush `drawPath()` lost the
implicit polygon closure. Aggregate pixel differences did not detect that loss.

**Fix**: call `closeSubpath()` after `addPolygon()` in `PolygonItem.paint` and
assert diagnostic ink on every side through the real scene renderer.

**Lesson**: when extracting a shared painter, preserve the source primitive's
closure and join semantics. Test the full boundary, not just the existence of ink.
Pin: `tests/integration/test_crop_rotation_border_shapes.py::test_every_bed_shape_paints_the_rotation_status_border`.
