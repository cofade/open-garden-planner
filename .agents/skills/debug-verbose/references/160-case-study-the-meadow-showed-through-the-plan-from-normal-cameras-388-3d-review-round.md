## Case study: the meadow showed through the plan from normal cameras (#388, 3D review rounds 1–2)

**Symptom.** On the baked Beauty Board and in the live view, the pond, the terraces and the
paths vanished from some cameras: the endless meadow's green drew over the plan's ground.
**Wrong theories.** "Depth-buffer resolution": the meadow lay 1 cm under the plan, so it was
lowered to 5 cm. A 36-view orbit gate went to 0, but the next review found 13 of 120 views
of the workspace's own framing, a few wheel notches out, still failing (up to 52 % of the
plan). The 5 cm step also drew a ±14 luma ambient-occlusion line along the plan's edge, and
the fitted edge probe read 0.45: blind to it.
**Evidence.** The reviewer's control: the same −5 cm meadow cut into 100 m cells lost no
view. A 24-bit buffer resolves about 0.3 cm at 50 m, so precision was never the limit; the
one 4 km quad of two triangles was, its depth interpolated across 2 km.
**Root cause/fix.** Nothing lies under the plan any more. The meadow is a frame in the
plan's plane with the plan cut out, in 100 m cells (`core/scene3d/meadow.py`), loaded by the
host into one `ReloadableGeometry`. A QML `ProceduralMesh` was tried first and drew stale
data, then nothing (PF-L3D-14). The gate measures the workspace's own camera on three plans
and asserts that the meadow is drawn at all: one attempt passed by drawing no meadow.
**Lesson.** A gate made of the cameras that showed the bug proves the fix only for those
cameras. Gate the views users actually get (`frame_pose` and wheel notches). And when a
"resolution" fix only moves the failures, look for the geometry that is out of scale.
Pins: `tests/integration/test_scene3d_ground_render.py::test_the_meadow_never_shows_through_the_plan`,
`tests/unit/test_scene3d_meadow.py`, `tests/ui/test_quick3d_meadow_host.py`. PF-L3D-13/14.

