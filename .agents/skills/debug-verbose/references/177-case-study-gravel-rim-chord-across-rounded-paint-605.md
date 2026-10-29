## Case study: a gravel rail cut across its rounded painted corner (#605, PR #645 owner pass)

**Symptom.** In Split mode, the 2D gravel corner was round while its raised
3D edging crossed the textured outer bend as a straight chord. Rounded end
caps likewise extended beyond two square-ended rails.

**Wrong theories.** The earlier review treated gravel like the paved path's
`_offset_path` borders, and tested its relief against the nominal caster
footprint. The gravel painter already used `_paint_rim` with round caps and
joins; improving `_offset_line` could never make its chord fit that rim.

**Key evidence.** Tagged `_rails`/`_offset_line` probes printed the outer
90-degree joint as `(0,-48.75)` to `(48.75,0)`: its chord midpoint radius was
34.47146 cm while the painted rim centre was at 48.75 cm (100 cm path).
All twelve independent Qt-stroke cases failed before the fix, for outer arc
coverage, cap coverage or triangles occupying the texture interior.

**Root cause.** 3D gravel reused a two-rail, chord-joined construction. Its
truth gate also compared round painted ground with a square/butt analytical
shadow footprint, so it rewarded the wrong outline.

**Fix.** Reuse `polyline_round_outline` (already the round path lawn cut-out
source), with 0.01 cm arc tolerance for visible edging; sweep the existing
bevelled section inward around every boundary ring, including caps and holes.
The nominal caster stays unchanged. Bound arc work before allocation and
output by 4096 outline vertices; complex paths keep their painted ground.
The painted-outline reach bound is now 0.05 cm, supported by an independent
Qt oracle which also rejects geometry over the inner texture and outside lawn.

**Pinned by.** `tests/integration/test_gravel_rim_relief.py` and
`tests/unit/test_scene3d_l4_surfaces.py`.

**Lesson.** Test decorative relief against the picture it decorates. A caster
footprint is an analytical model, not necessarily the rounded painted outline.
Include both coverage and exclusion: an edging with no protruding vertex can
still cut a chord through the wrong material.
