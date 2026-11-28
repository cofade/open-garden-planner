---
title: "Camera tours"
prefixes: ["FR-3D-TOUR"]
---

# Camera tours

- **FR-3D-TOUR-01** (L6.2): **Camera Tour** moves the camera as a **drone orbit** from where the
  view is, along **keyframes** (each the current view, on a smooth path at constant speed), or not
  at all; and the clock not at all, through **a day**, or **through the year**. Duration 1 to 600 s, 24
  to 60 frames per second, 720p to 4K. A **year** tour holds the UTC time, not the wall time: the sun
  moves evenly through both daylight-saving changes, the local clock shifts by the offset, and the
  dates the dialog names are the dates of the first and last frame. *(#807)* The orbit has a
  **Camera tilt** (5 to 89 degrees; the eye never closer than 20 cm to the ground) and **Start and
  stop smoothly**: an orbit that eases starts and ends at rest on its first view; one that does not
  turns at one speed and loops without a jump. A new orbit tilts 18 degrees (the horizon and a band
  of sky in view), eases, and takes 30 s a turn until the user sets a duration (a time-lapse keeps
  12 s). **Use Current View** starts the orbit exactly at the view, its tilt included.
- **FR-3D-TOUR-02** (L6.2): A tour is saved as an **MP4 video** (H.264 where the system has an encoder,
  else MPEG-4) or a **PNG sequence**. It is rendered frame by frame, so a slower computer takes
  longer and writes the same video. A progress bar shows each frame, Cancel stops it, and a cancelled
  video leaves nothing behind and never replaces an earlier file. A structurally invalid finished
  video is kept under its part name, reports failure with that path, and never replaces the
  destination (#889, #890). An intact video whose optional tagging fails unexpectedly can be
  delivered untagged, with the reason and destination in the log. When an earlier file is
  held open (a player has it), the finished video stays beside it and the message says where; a later
  recording of the same name takes a free part name and never deletes that kept render. **Esc or the
  window's X asks before throwing away a recording that has already run for 10 s**; Cancel keeps it
  running. Closing the app ends a running recording and waits (bounded) for its file to close; if
  the encoder cannot close in time, it names the unfinished output so the user can find it.
  A closed recording still being delivered names its eventual destination and the retained
  part on failure; delivery continues after the window closes. If
  the 3D view stops being visible, the recording waits and goes on. Frames are limited-range
  BT.709 YUV computed by the app, and every offered size is HD. *(#807)* A video is encoded at
  constant quality, **Standard** or **Best, for Publishing** (the dialog's **Video quality**, not
  kept in a saved tour), so its first second is as good as the rest; the finished file states
  BT.709 limited range in its container and in its stream, and the H.264 level its frames need
  (ADR-072 addendum "review-grade video"). The H.264 profile is Constrained Baseline, the one
  Windows' encoder writes through Qt. A PNG sequence keeps every frame losslessly, for an external
  master-quality encode.
- **FR-3D-TOUR-03** (L6.2): **Preview** plays the tour small and in real time inside the dialog and
  saves nothing. After a tour the plan's date, time and the view's camera are as they were; a
  time-lapse changes no plan data and leaves nothing to undo. Only a tour that actually moves the
  clock holds and restores it: a date the user sets during a **flight preview** survives its end.
- **FR-3D-TOUR-04** *(issue #737)*: A tour can be **kept in the plan under a name** and rendered
  again later. The dialog's first group lists the plan's tours: **Save Tour As** keeps the
  controls as a new tour (a name the plan already has is asked about before it is replaced),
  **Save Tour** writes changed controls back to the tour they came from, **Rename** and
  **Delete** do what they say, and choosing a tour puts its camera, time range, duration, frame
  rate and size back into the controls. Saving, changing, renaming and deleting a tour are
  **one undo step each** and mark the plan as changed; setting up a tour without saving it, and
  choosing one, change nothing. A saved tour holds a camera and a clock and nothing of the
  garden, so rendering it after the garden changed shows the changed garden along the saved
  path. A saved drone orbit or held view starts from the view it was saved with, and the dialog
  says so; **Use Current View** starts it from the view again. A saved orbit keeps its tilt and
  whether it eases; an orbit saved before #807 loads as the even loop it was and flies the same
  frames. Choosing another tour asks
  before it discards unsaved keyframes or unsaved changes. The tours are saved with the plan
  file and belong to it: a new or opened plan shows its own tours and none of the last plan's;
  Save As, a template and a new season keep them. A plan keeps up to 50 tours of up to 100
  keyframes each. The file's format version does not change: a release from before this
  feature opens a plan with tours and ignores them (and writes the plan back without them if it
  saves). A tour in a file that cannot be read is skipped, the rest of the plan loads, and the
  status bar says how many were skipped. An orbit with FOV 0 or 180 is rejected before playback;
  rejected entries produce at most five detailed warnings plus the aggregate count (#891).
  Tour number, date and time controls follow FR-I18N-10/11/12 (#896).
  The look of the picture (photo mode, weather, quality)
  is not part of a tour: it is the view's when the tour is rendered, and the weather is the
  plan's own (FR-3D-LIVE-10). Not included: a tour is not
  kept in the crash-recovery file (which holds the drawing only).
- **FR-3D-TOUR-05** (#966): A drone orbit's **Turns** may be a **part turn or a whole turn**,
  from 0.25 to 4, in steps of 0.25 (a two-decimal field). A garden with a house on one side
  can store a half turn on its garden side; the first frame is the view it was set from
  (Use Current View) and an eased half turn stops exactly opposite its start. A tour with a
  part turn takes 30 s a turn until the user sets a duration (a half turn: 15 s), and the
  value is written as a fractional `turns` and read back unchanged. A file that asks for less
  than 0.25 or more than 4 is clamped to the dialog's range; one that is not a finite number
  is refused as before. Pinned by `tests/unit/test_camera_tours.py`,
  `tests/integration/test_directors_cut.py::test_a_part_turn_starts_the_orbit_at_the_view_and_stops_half_way_round`,
  and the three bundled half-turn orbits in `tests/unit/test_example_specs.py`.

Acceptance: `tests/integration/test_directors_cut.py` (§8.10 — photo mode, the click, Save Photo,
the dialog, a recording end to end, every refusal, the blur/point invariant, the owner's date during
a tour, the clock-change hold), `test_agent_api_render_3d.py` (the real MCP transport),
`test_video_writer.py` (a real encode, read back; a kept render survives the next recording), the
unit suites `test_camera_path.py`, `test_video_yuv.py` and `test_scene3d_photo.py`, the render tier
`test_directors_cut_render.py` (including the two-week clock-change luma gate, and since #743 the
preview-against-4K blur parity and the slider's blur 0.05 against 1.0), and `--selftest`, which
captures and encodes from the bundle.
