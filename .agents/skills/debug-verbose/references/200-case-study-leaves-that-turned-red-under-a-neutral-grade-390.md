# Case study: leaves that turned red under a neutral colour grade (#390)

**Symptom.** A colour grade through Qt's LUT looked right in a contact sheet. An identity table, which
must change nothing, read mean 0.07 and p99 0 against the view, and a maximum of 103.

**Wrong theories.** (1) Rounding through a 16-level table: rounding is at most a few levels. (2) The
table's rows are upside down: that had been the previous bug, and it had made the WHOLE picture
wrong. (3) `flipV` on the Texture: it changed not one pixel, because an effect samples the table raw.

**Key evidence.** Printing the outlying pixels instead of a statistic. All 4181 had R = 0 in the view:
`[0, 19, 11] → [57, 16, 7]`. Not random pixels, the darkest saturated leaves, and only their red.

**Root cause.** Read from Qt's own resources (`:/qtquick3d_helpers/shaders/tonemapper.frag`):
saturation and contrast run unclamped right before the table, and the table is a `texelFetch` at
`int(lutSize*b + r)`. Saturation 1.06 takes a dark green's red below 0, and the column falls into the
previous slice, whose last column is full red.

**Lesson.** Mean and p99 hid the bug; the maximum found it. When a control that should do nothing does
something, list what it did to which pixels before theorising. And when an engine's behaviour is the
question, its shader is one `QFile` away. The fix makes the input of the table 0..1 by construction:
under a grade those two adjustments are 1 in the environment and live in the table.
