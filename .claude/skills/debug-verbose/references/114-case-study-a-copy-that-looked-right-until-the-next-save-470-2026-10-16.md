## Case study: a copy that looked right until the next save (#470, 2026-10-16)

**Symptom.** The offset tool's copy of a rectangle, circle or ellipse came back in its object type's default fill, pattern and stroke, while a polygon or line copy "kept all of it".
**Wrong theories.** The offset geometry was wrong; the style dialog never applied the look; the serializer dropped the colour.
**Evidence.** After the offset the copy's `fill_pattern`/`stroke_style` read as the type default and the save -> reload pen reverted, although the in-session pen/brush on the polygon path looked correct. One row of a save/reload round-trip test separated the two representations.
**Root cause.** An item carries its look twice - live (`QPen`/`QBrush`) and serialized (`fill_pattern`/`fill_color`/`stroke_color`/`stroke_width`/`stroke_style`). The rectangle/circle/ellipse path copied neither; the polygon/line path copied only the live pair, so it looked right until the next save. Two failures, one defect.
**Fix.** One seam, `core/item_look.py::copy_visual_style`, copies both; the offset tool and `mirror_geometry` share it.
**Lesson.** A copy that writes only one of an item's two appearance representations is a round-trip bug a rendering test cannot see - assert through the save/reload boundary.

