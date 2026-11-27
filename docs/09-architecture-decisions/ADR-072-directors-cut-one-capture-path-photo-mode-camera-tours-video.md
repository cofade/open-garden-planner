---
id: ADR-072
title: "Director's cut — one capture path, photo mode, camera tours, video and `render_3d_view`"
status: "Accepted; shipped in v1.37.0 (PR #729) after the owner's manual acceptance on 4 November 2026 (two rounds: the blur band, and the Ultra crash with the blur that needed a focus point)."
refs: ["Phase 17 L6", "#390"]
legacy_anchor: adr-072-directors-cut--one-capture-path-photo-mode-camera-tours-video-and-render_3d_view-phase-17-l6-390
---

# ADR-072: Director's cut — one capture path, photo mode, camera tours, video and `render_3d_view`

**Status:** Accepted; shipped in v1.37.0 (PR #729) after the owner's manual acceptance on 4 November 2026 (two rounds: the blur band, and the Ultra crash with the blur that needed a focus point).

## Context

L6 asks for three things that all need a picture of the garden that is not the view on screen:
a photo up to 4K, the frames of a camera tour, and a picture for an agent — the last
"through a second View3D of the same scene so the owner's camera and date never jump". The
issue names "the offscreen path" for the photo, and its owner's comment makes video part of
the issue ("Photo and video capture need to be implemented both in this issue"), where the
body had made it conditional on verifying a Qt Multimedia path.

`offscreen.render_records` cannot serve any of them while the view is open: it refuses beside a
shown Qt Quick window (its message recorder deadlocks with a render thread), builds every Model
again, and creates a graphics device per call. ADR-060 decision 17 forbids a frame from the live
view on any steady path.

## Decision

1. **One capture path: a second `View3D` of the same scene, for all three.**
   `Quick3DHost.capture(size, shot, wind_time_s=, photo=)` renders through `captureView` in
   `Garden.qml`: `importScene: view.scene`, the same camera, the same environment object. Nothing
   exists twice, so a photo, a video frame and an agent's picture cannot disagree. This replaces
   the issue's "offscreen path" for the photo: measured, it is identical to the view, needs no
   second device and is a hundred times cheaper than a rebuilt scene.

2. **Nothing moves on screen, by construction.** A capture is one synchronous call on the GUI
   thread. It moves the camera (when a shot is given), renders one frame that is never
   presented, and puts the camera back before the event loop runs. The view read back afterwards
   differs in no pixel; a capture from a camera equals the view moved to that camera, pixel for
   pixel, on Direct3D 11, GPU and WARP.

3. **`grabWindow` drives `grabToImage`.** An item's grab is taken in the window's next frame, and
   on Windows that frame is paced by a thread that waits for the display: with the display
   asleep it never comes (`ogp-3d-renderer` §6). `grabWindow` renders on the spot and emits the two
   signals the item's grab hangs on; the completion event is then delivered to that one object
   with `sendPostedEvents(result, 0)`. No nested event loop, so no user input during a capture.

4. **The capture view is never destroyed, and rests small.** Making and destroying a `View3D`
   per picture left about 20 MB behind each time at 4K, linearly (WARP, 60 pictures); on the GPU
   the driver's pools hid it behind a plateau. A hidden `View3D` keeps its render targets (500 MB
   after a 4K picture), so before it hides, the host renders it once at `MIN_CAPTURE_SIDE`, which
   makes Qt replace them. A tour holds the large targets for its frames (`begin_captures`).
   Measured: 60 single 4K pictures stay flat on the GPU and on WARP.

5. **Photo mode develops a picture and changes nothing in the garden.** Exposure in stops,
   depth of field on a focused POINT (a tour keeps it on the plant; Qt compares depths, so the
   point becomes a depth along the view's axis), a vignette towards black and a colour grade, all `ExtendedSceneEnvironment` features on the one environment, so the view previews
   what is saved. All off is the view, pixel for pixel. A click sets the focus while photo mode
   is on: selection has its 2D side. No setting is saved in the plan.
   *(#734: a saved photo, an agent's picture and a held camera's frames fit the shadow map to
   the casters; all off, such a picture differs from the view along shadow edges only, and a
   low sun's long shadows are sharper in it than in the preview — ADR-059 addendum "low-sun
   shadows". A capture that does not ask for it is still the view, pixel for pixel.)*

6. **A grade is a procedural table, and it carries the look's saturation and contrast.** Qt
   applies them unclamped right before its table lookup, and that lookup is a `texelFetch` whose
   column a colour below 0 pushes into the neighbouring slice: the darkest leaves came out red
   (R 0 became 57, 4181 pixels of a 720p frame). Under a grade the environment's two adjustments
   are 1 and the table applies them, clamped, with Qt's own formula. Identity table against the
   view: mean 0.13 levels, p99 1, at most 5.

7. **A tour is a list of frames computed from their index, never timed.** `core/camera_path.py`,
   Qt-free: a centripetal Catmull-Rom spline at constant speed (`CameraPath`), a `DroneOrbit` from
   the view's own pose, a `HeldCamera`; a day or a stretch of the year on the sim clock. A slow
   machine takes longer and writes the same video. `TourRecorder` renders one frame per pass of
   the event loop, waits for the pipeline to settle after each clock step, and pauses when the
   view gives no frame. Wind is the frame's own time. A year's date moves at most 8 times per
   second of video: each new date regrows every dated plant (about a second and 2 MB, #531).
   While it records, each plant keeps the finest detail any point of the flight asks for
   (`ForgeWorker.fly_path`), and the first frame waits for that: the view's camera used to decide,
   and on a close camera a frame lay 17 levels (mean) from the same frame with the flight's detail;
   now it lies 0 from the view moved there. A plant keeping one detail for the flight also does not
   change its leaves in mid-video.

8. **Video through Qt Multimedia, verified for size and licence as the issue asked.**
   `QVideoFrameInput` → `QMediaCaptureSession` → `QMediaRecorder`, all inside the pinned
   `PyQt6-Qt6` wheel (LGPL v3). Its FFmpeg 9.0.1 reports `LGPL version 2.1 or later` at run time
   and its configure line has no `--enable-gpl`. Size: the bundle grows by about 20 MB. H.264
   comes from the operating system's encoder (`h264_mf`, Windows Media Foundation), so the app
   ships no H.264 encoder; where there is none, FFmpeg's own MPEG-4 Part 2 encoder writes the file
   (both tested). The app is GPLv3 and links the wheel dynamically; no new dependency, no new
   licence category. `video_writer.py` is the only importer, and it imports on first use.

9. **The frames are BT.709 YUV computed by the app, never RGB.** Handed RGB, the recorder converts
   with swscale's default matrix (BT.601) and writes no colour tag, and every player reads an
   untagged HD stream as BT.709: (200, 60, 30) came back as (212, 73, 27). `core/video_yuv.py`
   computes limited-range BT.709 4:2:0 in fixed point: within 2 levels. All tour sizes are HD,
   because below HD players assume BT.601.

10. **`render_3d_view` is a read-only tool that refuses instead of waiting.** No token (ADR-034):
    it changes nothing. It calls the one capture path with the owner's camera or one of its own,
    undeveloped (`NO_PHOTO`), and returns a PNG and what it shows, plan date and sun included.
    `capture_blocker()` answers at once: `not_open`, `warming_up` (first frame, pipeline, forge),
    `recording`, `unavailable`. A clean sentence in under a millisecond, where a plain wait would be
    a 5 s timeout. `run_on_main(timeout=30)`: a 2048 px PNG on a software adapter takes about a
    second. It has no date argument: the date is the owner's, and a second date needs a second
    scene.

## Alternatives rejected

- **`render_records` in the running app** (the issue's words): refuses beside a shown window, one
  device per call, every Model again. Kept for what it is for: tools, tests, the self-test.
- **A child process per photo or per video**: isolates a crash, but needs the whole look, weather,
  analysis and date serialized, a second path to the same picture, and a second copy of the plan
  in memory.
- **`QQuickRenderControl`**: renders off-window at any size, but PyQt6 cannot hand it a native
  texture on Direct3D 11.
- **Creating the capture view per picture** (`Loader`): built, measured, withdrawn (decision 4).
- **A vignette through `vignetteStrength`**: a lower strength darkens the middle of the picture
  too (mean luma 99 → 47 at 2.4). The exponent reaches only into the corners.
- **PNG sequence only, video later** (the issue's fallback): the owner's comment asks for both.
- **`imageio-ffmpeg` or a bundled `ffmpeg.exe`**: a new dependency of about 30 MB, for what the
  pinned wheel already holds. GPL builds of it would change the distribution's obligations.

## Consequences

- `render_3d_view` needs the 3D view open: an agent is told so in a sentence (follow-up: a picture
  while the plan is shown, through the offscreen path, which is allowed then).
- An agent's picture from another camera has the plant detail of the view's camera: it is one
  synchronous call and cannot wait for the forge. The tool's description says so (follow-up: ask
  the forge for that camera's detail, and let the next call find it ready).
- Keys of a tour live in the session: closing the app loses them, and the plan stays free of 3D
  data (follow-up: keep tours in the file as additive metadata).
- A year's time-lapse spent #531's 2 MB per regrowth; a 12 s video about 200 MB. *(Since the
  ADR-069 addendum of 2026-11-24 a regrowth reloads its Models in place: date playback measured
  about 13 kB of committed memory per regrown tree, #1013. A tour is not re-measured.)*
- An MP4 carries no colour tag: the writer relies on the HD convention (decision 9), which the
  owner's manual test confirms in real players. Qt offers no way to set the tag. *(Superseded by
  the addendum "review-grade video" (#807): the app writes the tags into the finished file.)*
- **The blur is only roughly the same in the pane and in a saved photo.** Qt blurs a half-resolution copy
  with three taps, so the blur is about 2 px at any picture size: a 4K photo looks sharper than its
  preview (gradient ratio in the middle of the garden at blur 0.8: 0.66 in the pane, 0.91 in a 4K save
  seen at the same size), and Qt's amount is capped at its 1080p value because more only shows the taps
  as copies. The slider moves the width of the sharp band, not the amount (owner's manual test: with a
  band of 40 % a high and a low blur gave one picture). A picture-relative blur needs a custom depth
  of field `Effect` (follow-up). Done by the addendum "photo mode's own depth of field" (#743).
- **Screen-space reflections stand down while the blur is drawn.** On Ultra, reflections + depth of
  field + glow in one effect chain took Qt's render thread down in `d3d11.dll` at the owner's first
  focus click (two crashes, one address; PF-E3D-21), and it showed on the owner's `quality = ultra`
  only. Ultra's photos have no reflections; Low to High never had any. Finding the Qt-side cause, to
  give them back, is #744 (generalised and reproduced without project code in the addendum "photo
  mode's own depth of field"; the workaround stays).
- **The blur needs a focused point, so the first blur sets one.** The slider used to do nothing before
  the first click on the view (owner's manual test: "no difference between a high and a low blur").
  Three edges of that first focus (another plan, walk mode, one invariant) are #745.
- No `FILE_VERSION` change; nothing new in the `.ogp`.

## Addendum: capture-session integrity (#730, #731, #732, #745)

Delivered in **v1.37.2** (PR #750) after the owner's manual acceptance on 5 November 2026.

Four follow-ups from the reviews of this PR share one rule: a capture session must not change
anything the owner did not ask it to change - not the clock, not a kept file, not the focus.

1. **One clock hold, taken only by a tour that moves the clock.** `start_tour` stores the owner's
   `clock.wall` only when `date_range` or `time_range` is set (`WorkspaceCaptureCoordinator._clock_hold`);
   a flight preview stores nothing and restores nothing, so a date the user sets while a preview
   runs survives it (#730). The held moment is what `owner_plan_date()` reports while the
   tour runs; the normal clock write path is unchanged.
2. **Agent reads and writes use the owner's held date.** `AgentHost._agent_plan_date()` resolves
   `WorkspaceCaptureCoordinator.owner_plan_date()` first and the sim clock second;
   `ProjectManager.snapshot_dict(scene, as_of_date=...)` derives `as_of_date` and every object's
   `present` from that one date. A plant an agent creates during a time-lapse is stamped with the
   owner's planting date, not the frame being rendered. A document change still ends a tour (the
   scene it was rendering is gone); the dialog's status says "Cancelled." Diagnostics and the 2D
   render describe
   the frame the tour is currently showing; they are not date claims.
3. **A year's tour holds UTC, not the wall time.** The sun is `SimClock.utc`'s function; a wall
   time held across a DST change moved the sun by an hour (measured: an 18.07-level step between
   neighbouring frames of a two-week clock-change tour; the owner read 24 in the year video,
   #732). The first frame records its UTC time-of-day and every later frame asks
   `SimClock.set_utc_time_on(day, held)` for the instant whose local date is the frame's and
   whose UTC time-of-day matches: the wall reading is derived through the zone, so the repeated
   autumn hour gets the occurrence whose instant matches (`fold` included) and the spring gap
   gets the real local hour. A local date with no instant at the held UTC time (a 23-hour spring
   day) gets the nearest reading on that date, within the missing hour. The dates the dialog
   promised hold. See ADR-053's addendum for the clock-side statement.
4. **A finished render is never deleted without the user's word.** `Mp4Writer` takes the first
   free `<stem>.part[<n>].mp4`, so a render kept because its target was held open by a player is
   never removed by the next recording of the same name (#731). Esc or X on a recording that has
   run for `ASK_DISCARD_AFTER_S` (10 s) asks first; Cancel keeps it running; a programmatic
   engine teardown does not ask. `Workspace.shutdown` calls
   `WorkspaceCaptureCoordinator.shutdown`, which aborts the recorder and waits (bounded,
   2.5 s) for its file to close; if the encoder is still closing then, it names the unfinished
   output in a warning, so the user can find it instead of the part disappearing unreported.
   Numbered parts are kept: a kept render is never deleted by a later run, and the user can
   remove one. (A successful save to the target does replace that target, as any save does.)
5. **The focus invariant lives in one place.** `set_settings` enforces "blur above 0 in photo mode
   implies a focused point": with no clicked point it focuses the camera target, or, while
   walking, the ground point under the view's centre (the 100 cm mid-air target is behind the
   walker after a few steps). `document_changed` clears the old point and records that the new
   plan's framing is pending; a setting changed meanwhile is stored and applied then, never
   focused on the plan that is going away; `document_shown` re-establishes the point once the
   camera is framed (#745).

**Alternatives considered**: refusing agent writes during any recording (rejected: a read is
harmless and a write can use the owner's date, which is what the user expects); holding the wall
time and compensating the sun only (rejected: two sources of truth); deleting a stale `.part.mp4`
at startup (rejected: it may be the only copy of a long render); clearing the blur when a plan
opens (rejected: the owner asked for the same blur with a new point, and the label now says the
focus is moving until it has one).

**Consequences**: no `.ogp` change and no `FILE_VERSION` bump; two new UI strings in every
registered locale. Pinned by `tests/integration/test_directors_cut.py` (the invariant, the walk
fallback, a second plan, the flight preview, the owner's date, the UTC hold, the discard question,
the app-close file) and `tests/integration/test_video_writer.py` (a kept render); the render tier's
`timelapse` scenario carries the two-week clock-change luma gate. Measured after the fix: largest
neighbouring-frame step 1.53 levels, against 18.07 before it.

## ADR-072 addendum: what a saved picture is made of (#733, #735, #738)

Delivered in **v1.37.6** (PR #759) after the owner's manual acceptance on 6 November 2026.

Two decisions #729 left open, and the measured cause of a look that differed by size.

1. **A picture uses the view's quality preset.** A photo or a video frame is the second
   `View3D` of the same scene (decision 1), so it is made at whatever preset the view runs.
   Raising it for the capture's own frames was rejected: the pane would preview one look and
   the file would hold another (the parity decision 5 rests on), every raised frame rebuilds
   the render targets and the preset's geometry, and the machine that dropped to Low is the
   one that cannot afford the raise. The quality setting is the user's lever; `AutoPreset`
   already treats a capture's stall as no data rather than a slow machine. Pinned by
   `test_a_picture_is_taken_at_the_views_preset_and_never_changes_it`.
2. **The MP4 keeps relying on the HD convention, and its frames state BT.709.** Qt's
   recorder writes no colour tag in the container, and it offers no API to add one.
   `Mp4Writer` computes limited-range BT.709 YUV itself and tags the `QVideoFrameFormat`
   with that space, range and transfer; every offered tour size is HD, and a player that
   reads an untagged HD stream as BT.709 reads what the frames are (decision 9). The
   assumption is now pinned: `test_the_stream_is_tagged_bt709_and_every_offered_size_is_hd`.
   A player that gets it wrong is a bug report with a named player, not a reason to invent
   a second colour path. *(#807: the frames are unchanged, and the finished file now states
   them in its `colr` box and every SPS - addendum "review-grade video".)*
3. **A bigger picture keeps 1080p's look by scaling the occlusion, not the glow.** #733
   read a 4K picture's horizon band as about 9 levels darker than 1080p and suspected Qt's
   pixel-sized glow. Measured on the family garden at the sunset anchor, the glow is not the
   cause: with glow off the band still differs by the same amount, and with ambient
   occlusion off it differs by 0.0. Qt samples SSAO's scene-unit radius on a PIXEL grid, so
   the same radius covers twice the pixels at twice the height and darkens the far meadow
   more. `Quick3DHost.capture` therefore sets `captureAoDistanceScale =
   look.ao_distance_scale(height)` (1080p and smaller: 1.0; 2x the height: 0.5; floored at
   0.25) for the captured frame and restores 1.0 after it. Measured on that shot: the band
   (36-44 % of the picture's height) read -1.75 luma mean / -2.82 worst bucket before and
   -0.41 / -0.53 after; the sky is the control and moves by 0.03. The render tier pins it
   (`test_a_4k_picture_keeps_the_low_suns_horizon_band_within_1080ps_look`, band <= 1.0,
   bucket <= 1.6, sky <= 0.5). The garden *below* the horizon still differs by up to ~3
   levels at 4K: that is texture minification resolving more detail, not the reported band,
   and it is left alone rather than tuned away with a second fudge factor.
4. **A capture that raises nothing leaves nothing behind** (#738): a capture from another
   camera refuses when the host has no camera to put back, rather than leave the view on the
   shot; the capture's `finally` restores the photo, selection, wind and AO scale even when
   the resting frame raises; a video frame the queue refused is offered again from the same
   `QVideoFrame` instead of converting its YUV planes twice; and a tour's clock hold is
   released in a `finally`, so a raising clock listener cannot leave automatic quality
   paused. The tour recorder keeps its hidden-view guard: a hidden pane's controller stays
   paused and dirty, so `settled()` never becomes true and without the guard the first
   "Waiting" sentence arrived only after the 180 s first-frame limit (measured by the gate
   review; the issue's suggestion to drop it was wrong).

**Consequences**: no `.ogp` change and no `FILE_VERSION` bump. The capture AO scale is a
render-only input (the view's own 1.0 is untouched). Pinned by the tests named above, the unit
row for `look.ao_distance_scale`, `tests/ui/test_quick3d_host.py`'s no-camera and
raising-resting-frame rows, and the tour-hygiene tests of #738 (including the workspace-level
hidden-view guard and the closing-dialog twin).

## ADR-072 addendum: camera tours kept in the plan (#737)

**Status:** shipped in v1.39.0 (PR #882) for issue #737.
It replaces the consequence above that "keys of a tour live in the session".

A tour's keyframes and settings lived only as long as the dialog, so a user could not come back
next week, after changing the garden, and render the same flight again.

1. **The plan owns its tours.** `ProjectManager.camera_tours` is a tuple of immutable
   `SavedTour` objects (`core/camera_tours.py`, Qt-free). The dialog's controls are a draft:
   "Save Tour" / "Save Tour As" keep the draft in the plan under a name, choosing a saved
   tour puts it back into the controls. Names are unique whatever their case, one clean line
   of at most 60 characters. A new, opened or recovered plan replaces the list and clears the
   draft (its keyframes were points of the old plan); Save As, a template (`camera_tours` is
   a kept field of ADR-066: a path through kept geometry, no site data) and a new season keep
   the tours.
2. **A saved tour holds a camera and a clock, and nothing of the garden.** What is written is
   what the dialog needs to make the same video: the motion, its keyframes (kept whatever the
   motion is: they are the user's work), the loop flag, the frame's duration, rate and size,
   and a day's or a year's range. Rendering it later renders the garden as it is then. Not
   written: the output path, the wind (reduced motion is the machine's setting), and the
   look: photo mode's development, the weather and the quality preset stay the view's at the
   time of the render, as for every picture (addendum above, decision 1).
3. **A saved orbit or held view carries the view it started from.** The dialog's orbit "starts
   where the view is now"; saved like that it would be another video on every render. The
   orbit's pose (target, distance, yaw, pitch, field of view, turns, direction) and the held
   camera are saved, the dialog says that the tour starts at its saved view, and "Use Current
   View" lets it go.
4. **The format is one additive top-level key, and `FILE_VERSION` stays `"1.4"`.**

   ```json
   "camera_tours": [
     {
       "name": "Promo Flight",
       "motion": "path",
       "keys": [
         {"eye": [6370.2, -2718.9, 3521.4], "target": [1200.0, 800.0, 0.0], "fov_deg": 40.0},
         {"eye": [3208.7, -3921.0, 3912.3], "target": [1200.0, 800.0, 0.0], "fov_deg": 40.0}
       ],
       "closed": true,
       "date_range": ["2027-03-01", "2027-10-31"],
       "duration_s": 12.0,
       "fps": 30,
       "size": [1920, 1080]
     },
     {
       "name": "Drone",
       "motion": "orbit",
       "orbit": {"target": [1200.0, 800.0], "distance_cm": 2150.75, "yaw_deg": 33.5,
                 "pitch_deg": 28.25, "fov_deg": 40.0, "turns": 2, "clockwise": false},
       "duration_s": 12.0,
       "fps": 30,
       "size": [1920, 1080]
     }
   ]
   ```

   `motion` is `orbit`, `path` or `hold` (`held`: one key); `time_range` is `["06:00", "21:00"]`;
   points are scene centimetres (east, north, up). The key is absent when the plan has no tour.
   No bump, because an older build can ignore it safely (architecture contract, row 9): its
   loader reads the keys it knows, the plan validator checks numbers only, and the version
   guard refuses only a file newer than its own. Proven on the real thing: release v1.37.9's
   own code loads a plan written with tours and loses nothing but the tours
   (`test_a_file_with_tours_opens_in_the_last_release_that_did_not_know_them`). The degrade is
   the one of every additive key: an older build that saves the plan writes it back without
   the tours. The same holds one level down: a field of a tour this build does not know is
   left out when the tour is saved again.
5. **Every edit is one undo step through one writer.** `SaveCameraTourCommand` (a new name is
   added at the end, a known name replaces that tour in place), `RenameCameraTourCommand` and
   `DeleteCameraTourCommand` go through `CommandManager.execute`; each keeps the whole list
   before and after, so undo and redo restore exactly what was there, in its order.
   `ProjectManager.set_camera_tours` is the only writer besides load and new, and marks the
   plan dirty. Changing the draft, choosing a tour and a cancelled name dialog are no step. A
   command that cannot be built (unknown name, name taken, more than 50 tours) raises before
   anything reaches the stack. The commands say they change neither the ground band nor
   containment, so the canvas skips both restack scans.
6. **The reader is a trust boundary.** `load_tours` is the one reader. One broad `except` per
   entry (architecture contract, row 14): what is not a tour this build can render is skipped,
   logged and counted, and the load of the plan goes on. Geometry is never repaired (a path
   with one key changed is another video): a wrong type, a number that is no camera (not
   finite, beyond 10 km, a field of view outside 0 to 180, an eye on its target), fewer than
   two different keys, a range that runs backwards and both ranges at once skip the tour.
   Settings are put back into their range: duration 1 to 600 s (default 12), a frame rate
   and a size the dialog offers (defaults otherwise), whole turns 1 to 4. Caps: 50 tours per
   plan, 100 keyframes per tour; a second tour of a name is skipped. The status bar says how
   many tours could not be read, since they are gone with the next save. The document's
   numeric boundary is unchanged: a NaN or an infinity anywhere in the file, a tour included,
   refuses the whole document before any tour is read (`plan_io`, AUD-041). A tour's name is
   shown as plain text wherever it appears.
7. **The agent surface is unchanged.** `snapshot_dict` is the plan as the file holds it, so the
   tours are in it; the curated agent schema names none of them, and no tool was added.

**Alternatives rejected:** an id per tour with per-tour restore methods (the journal-note
pattern): the name is the identity the user sees, and a whole-list snapshot is exact and
small; the tours in `QSettings` (they would stay on one machine and not travel with the
plan); nesting them under the file's `metadata` (a template drops it, and every other
plan-scoped store is top-level); saving an orbit as "from wherever the view is" (not the same
video twice); clamping a hostile coordinate into range; keeping unread entries and writing
them back verbatim (unvalidated data would pass the boundary on every save); a `FILE_VERSION`
bump (it locks every older install out of data it can ignore).

**Consequences:** 23 new UI strings in every registered locale. A year's range is absolute
dates, so a tour carried into a new season still names last year's dates until the user
changes them. The autosave file holds the scene only, so a plan recovered after a crash has
no tours, like the rest of the plan's metadata (location, soil tests, tasks, and the
plan's north orientation since #663); that is older
than tours and is not changed here. Pinned by `tests/unit/test_camera_tours.py` (the model,
one probe per class of hostile entry, the three commands' step counts) and
`tests/integration/test_tour_persistence.py` (the dialog's own controls, save and reopen, the
same frames, the changed garden along the saved path, another plan, the previous release,
the real window).

## ADR-072 addendum: photo mode's own depth of field (#743, #744)

**Status**: Accepted; shipped in v1.39.0 (PR #882, visual-polish package; owner's manual test 2026-11-10).

**Context**: decision 5 promises that the view previews what is saved, and the consequences above
record where it failed. Qt's `depthOfField*` blurs a half-resolution copy with three taps
`0.53 x amount` px apart, about 2 px at any picture size. Measured on bench_small's hero camera at
blur 0.8 (60 px tiles, gradient kept against the sharp picture): the 640 x 360 preview kept 0.53 of
its detail, a 4K save shrunk to the same size 0.92. On a bench with known answers
(`tests/integration/photoblur_bench.qml`) Qt's blur put a 7 to 8 level fringe of an in-focus bar on
the blurred wall beside it at 4K, drew a thin far line 3.6 times wider (as a share of the picture)
at 360 px than at 4K, and left a blurred near bar's edge 1 px wide at 4K.

**Decision**:

1. **The app blurs, not Qt.** `qml/PhotoBlur.qml` is an `Effect` in the environment's `effects`,
   only while the blur is drawn (`depthOfFieldActive`), so blur 0 is the view to the level. A user
   effect runs on the scene's linear colour, before exposure, tone mapping, glow, the grade and the
   vignette (measured: a constant 0.25 written there came out tone-mapped), so a blurred highlight
   still glows.
2. **The blur is a share of the picture's height.** The Gaussian's sigma is `blur x
   BLUR_SIGMA_SHARE (0.006) x height`: 6.5 px at 1080p at the slider's end, 13 px at 4K, 2 px in a
   328 px pane. Nothing in `photo_properties` depends on a picture's size any more; `blur_amount`,
   `BLUR_MAX` and the 1080p cap are gone.
3. **Two layers, premultiplied, at two sizes.** Out of focus is 0 inside the band and grows to 1
   one band beyond its edge. What lies behind the band and what lies in front of it are separate
   layers; each is premultiplied by its weight and blurred at sigma and at a third of it, rows then
   columns, each tap a bilinear pair of texels (exact for premultiplied data, no texel skipped: no
   copies). A far pixel takes the average of its own layer only (no fringe); the near layer covers
   its own pixels and spreads past its edge (soft against a sharp background). Up to a third out of
   focus the small blur takes over from the sharp pixel, beyond that the full blur from the small one:
   lerping a sharp pixel with the full blur drew sharp leaves inside a haze. A layer's silhouette
   pixel counts for a fifth (PF-E3D-27): its colour is multisampled, its depth one sample.
4. **The sharp band keeps a whole plant and loses the scale model** (decided in this package; the
   owner may veto either constant): `FOCUS_RANGE_MIN_CM` stays the owner's 60 cm (the band is now
   sharp to its edge, half in front of the point and half behind), and the band is never thinner
   than `FOCUS_RANGE_FLOOR_SHARE` (8 %) of the depth at `FOCUS_RANGE_FLOOR_AT_CM` (25 m), growing
   with the square of the depth as a lens's depth of field does: 2 m (8 %) at 25 m, 4.6 m (12 %)
   at 38 m, 5.7 m (13.5 %) at the family garden's 42 m camera, where the strongest blur left about a metre (3D
   review of #729). Below about 9 m the floor is under the strong share and changes nothing. The
   slider moves the band and the blur together.
5. **Ultra's reflections still stand down under the blur** (#744). With the app's blur in Qt's
   place the crash stayed: reflections kept under the blur on Ultra died at the first blurred frame,
   3 of 3; with the workaround 10 of 10 rounds drew. With glow on, any two effects ahead of Qt's
   own scene effect break its chain (PF-E3D-21): reflections with Qt's depth of field, reflections
   with one user effect, two pass-through user effects (a wrong picture, or a crash). One effect
   ahead of it, with any number of passes and buffers, is fine. A reproducer without project code is
   in `adr-048-evidence/qt-effect-chain-glow/`, filed upstream as
   [QTBUG-152289](https://qt-project.atlassian.net/browse/QTBUG-152289) (2026-11-14). Re-test on every
   Qt bump and on every change of that ticket; when it is fixed, drop the `depthOfFieldActive` term
   from `ssrEnabled` and invert the `ultra_blur` gate.

**Measured** (dev box, RTX 4070, Direct3D 11, medium preset unless named; GPU shared with other
work, so costs are ranges of A/B rounds interleaved):

| | Qt's blur (base `53b48405`) | PhotoBlur |
|---|---|---|
| preview 640 x 360 against a 4K save at blur 0.8, mean gradient ratio of 41 tiles | 0.528 / 0.919 (0.391 apart) | 0.428 / 0.435 (0.033 apart) |
| the same, middle third | 0.539 / 0.944 | 0.426 / 0.462 |
| slider 0.05 against 1.0: share of 60 px tiles below 0.8, focus tile kept | 0.137 / 0.657; 1.20 / 0.93 | 0.000 / 0.652; 1.00 / 0.97 |
| bench: fringe of an in-focus bar on the blurred wall, 4K | 7 to 8 levels | 0.0 |
| bench: a 2 cm far line's width, share of the height, 360 px / 4K | 0.0083 / 0.0023 | 0.0139 / 0.0153 (one hump) |
| bench: a near bar's 10-90 % edge, share of the height, 360 px / 4K | 0.0056 / 0.0005 | 0.0083 / 0.0069 |
| frame at 1280 x 720, blur off / on, median of 60 grabs | | low 8.0 / 10.2 ms, medium 9.4 / 11.0, high 8.9 / 7.3, Ultra 3.1-4.2 / 3.5-5.7 |
| a 4K capture, blur off / on, median of 8 | | medium 781 / 1245 ms (one run), Ultra 1691 / 1692 ms |

Blur 0 with a focus set: 0 levels from the view. The memory loop of 30 1080p captures: +73 MB
before, -88 MB after (noise). The five buffers are RGBA16F at the picture's size, about 330 MB
during a 4K capture; the capture view rests small afterwards and gives them back (decision 4).

**Alternatives rejected**: the issue's single pass weighted by each tap's own circle of confusion
(no near spread: a blurred picket keeps its hard edge); scatter-as-gather with a per-tap sigma (not
separable, and its approximations draw their own halos); a half-resolution layer for the full blur
(a 2 px sigma in the pane would be 1 px, and the preview would part from the save again); lerping
the sharp pixel with one full blur (sharp leaves inside a haze, round 1 of the look-dev); turning
glow off on Ultra under the blur instead of reflections (glow changes the whole picture's
brightness, reflections only water and glass).

**Not fixed here, measured** (#743's "separate" bullet): with photo mode off, the 360 px pane reads
+4.75 luma (mean) and up to +12.3 in a 40-row band brighter than 1080p and a 4K capture of the same
camera (family garden, medium). It is ambient occlusion, not glow: with AO off the gap is 0.25 mean
and 1.0 worst band; glow on or off moves it by 0.15. Scaling AO's distance by 1080/height below
1080p, the #733 lever, does not help (+4.86). `aoSoftness` is the pixel-sized term: at 360 px a
softness of 25 instead of 45 zeroes the mean (+0.5) but a 40-row band stays 8.9 brighter, so no
single knob gives the pane a 4K save's occlusion. Proposed: while photo mode is on, render the pane
at a 1080p-equivalent internal height and show it scaled (the preview then is a save), or retune
SSAO per height (softness and distance together) with the owner's eye on the everyday view. Both
change the pane's look or its cost and are left to a follow-up.

**Consequences**: no `.ogp` change, no `FILE_VERSION` bump, no new dependency, no user-visible
string. The 3D view's look with photo mode off is untouched. Pinned by
`tests/integration/test_directors_cut_render.py` (`test_a_saved_photo_has_the_blur_its_preview_shows`
failed on Qt's blur at 0.394 apart; the slider; blur 0; the bench; `ultra_blur` now asserts that
reflections stand down under the blur and come back without it), `tests/unit/test_scene3d_photo.py`
(the sigma share and the band floors), and `tests/unit/test_quick3d_qml.py` (the effect's wiring,
the shared shader code, the silhouette weight, the shader paths).

## ADR-072 addendum: review-grade video, and an orbit's ease and tilt (#807)

**Status**: Accepted; shipped in v1.39.0 (PR #882, visual-polish package; owner's manual test 2026-11-10).
Decisions 5, 6 and 7 were the owner's to confirm (each is one constant) and stand as built.

**Context**: the 3D promo survey found the MP4 review-grade only: H.264 Constrained Baseline at
0.2 bit/px (12 Mbit/s at 1080p30), no colour tags, and an orbit that starts and stops at full
speed, tilted 31.6 degrees, one degree a frame. The owner will record a promo video with the
Camera Tour, so the file must be good enough to publish as it is. Measured on 1080p30 PNG
frames rendered on Ultra (RTX 4070, 2026-11-10): a foliage-heavy held shot (food forest, wind,
180 frames) and a slow orbit (family garden, 0.5 degrees a frame, 180 frames), each encoded
through the app's own writer and read back through Qt's decoder against the very YUV the writer
fed the encoder. Detail is the mean gradient decoded/source over 32 px tiles whose source
gradient is 8 levels or more (leaves, mulch, pickets); colour is the 32 px tile means through the
BT.709 oracle (the 4:2:0 round trip alone reads 0.70-0.73 at worst) and the frame mean.

| | before (0.2 bit/px) | 0.35 bit/px (the issue) | Standard | Best |
|---|---|---|---|---|
| orbit: Mbit/s (MB per minute) | 12.0 (90) | 19.4 (146) | 26.5 (199) | 35.7 (268) |
| orbit: Y-PSNR mean / worst frame | 42.6 / 41.8 dB | 45.3 / 42.0 | 47.5 / 47.1 | 49.5 / 49.2 |
| orbit: detail kept, mean / worst frame | 0.966 / 0.941 | 0.978 / 0.941 | 0.983 / 0.969 | 0.986 / 0.978 |
| orbit: colour, frame mean / worst tile | 0.59 / 3.35 levels | | 0.35 / 1.80 | 0.63 / 2.06 |
| foliage: Mbit/s (MB per minute) | 10.0 (75) | 10.6 (79) | 7.9 (59) | 11.4 (86) |
| foliage: Y-PSNR mean / worst frame | 46.7 / 40.4 dB | 47.2 / 40.4 | 46.0 / 45.8 | 48.2 / 48.1 |
| foliage: detail kept, mean / worst frame | 0.988 / 0.957 | 0.989 / 0.957 | 0.986 / 0.977 | 0.992 / 0.985 |
| foliage: colour, frame mean / worst tile | 0.27 / 2.57 levels | | 0.06 / 1.51 | 0.27 / 1.71 |
| profile / level | Constrained Baseline 4.0 | 4.0 | 4.0 (4.1 when it needs it) | 4.1 |
| colour tags, as Qt reads them | none (`ColorSpace_Undefined`) | none | BT.709, limited | BT.709, limited |
| timing | 180 of 180 frames at 33.333 ms everywhere | | | |

The new default orbit (decisions 5 to 7) recorded end to end at 1080p30, Best: 30 s, 900 of 900
frames at 33.333 ms, 24.8 Mbit/s (186 MB per minute), 50.5 / 49.9 dB, detail 0.986 / 0.972,
colour 0.51 frame mean, level 4.1, BT.709 limited.

**4K, once, end to end** (the slow orbit at 3840 x 2160, Ultra, one run writing the MP4 at Best
and a PNG of every frame, nothing else of the slice running): 180 of 180 frames in 61.9 s, every
one 33.333 ms; the process's peak working set 3.3 GB and peak commit 7.1 GB (the PNG writers'
queue included), the GPU from 0.76 to 3.65 GB; no out-of-memory error (#809 records one on a
machine short of commit). The same frames, before / Standard / Best: 44.6 / 76.7 / 109.9 Mbit/s
(335 / 575 / 824 MB per minute), 45.1 / 43.0, 48.1 / 47.7 and 50.0 / 49.7 dB (mean / worst frame),
detail 0.973 / 0.938, 0.984 / 0.967 and 0.987 / 0.978, colour 0.59, 0.34 and 0.66 levels (frame
mean); level 5.1, BT.709 limited.

**Decision**:

1. **Constant quality, not a bit rate.** Qt's `AverageBitRateEncoding` reaches Windows' encoder
   (`h264_mf`) as CBR (the average and the CBR modes wrote byte-identical files): the first 18
   frames of every video read 40.4 to 42.0 dB at any rate from 0.2 to 1.0 bit/px, and above 0.7
   bit/px it spent no more (31.0, then 32.1 Mbit/s). `Mp4Writer` asks for
   `ConstantQualityEncoding`; the dialog's **Video quality** offers **Standard** (Qt's
   `HighQuality`, Media Foundation's quality 90) and **Best, for Publishing** (`VeryHighQuality`,
   100). A choice beats one fixed setting here: Best costs 1.35 to 1.45 times the size for about
   2 dB. Standard is the default. The quality is not part of a saved tour: like the look, it is the
   render's (addendum #737, decision 2), and it lives as long as the dialog. `BITS_PER_PIXEL` is gone.
2. **The profile is what Windows writes: Constrained Baseline.** `QMediaRecorder` has no profile
   setting, Qt 6.12 hands `h264_mf` only `rate_control` and `quality` (the strings in
   `ffmpegmediaplugin.dll`), and FFmpeg's Media Foundation encoder takes an unset profile as
   Baseline. High (CABAC, 8x8 transforms, B-frames) would need a Qt change, FFmpeg called around Qt,
   or an encoder of our own: a new dependency, which #807 rules out. The constant quality pays for
   the profile in bits. The writer logs the profile and level every file got.
3. **The file states its colour.** Qt's recorder writes no colour description, and Qt's own
   decoder read the file as `ColorSpace_Undefined`. `core/mp4_stream.py` (Qt-free) rewrites the
   finished part once, on a worker thread, before it gets the user's name: a `colr` box (`nclx`
   1/1/1, `full_range_flag` 0) in the sample entry, and the same values as `video_signal_type` in
   every SPS (Media Foundation repeats the SPS at each IDR frame, once a second; a tag in `avcC`
   alone would be overruled in the stream). Every other bit stays. The range is limited because the
   frames are (decision 9). Checked without new tools: Qt's player prints FFmpeg's stream line,
   `yuv420p(progressive)` before and `yuv420p(tv, bt709, progressive)` after; its frames report
   BT.709 / BT.709 / video range; the decoded planes were identical, 180 of 180. A file the module
   cannot rewrite (an MP4 layout other than FFmpeg's, a full disk) is saved untagged and the log
   says so: the tags are a statement about a render, never a reason to lose it.
4. **The file states the level its frames need.** Asked for constant quality, Media Foundation is
   given no bit rate and labels a 1080p30 stream level 4.0 at any rate (36 Mbit/s as 4.0, whose
   Baseline limit is 24). The same rewrite raises the level, never lowers it, to the lowest one
   whose frame size, macroblock rate and coded picture buffer the samples fit (H.264 Table A-1,
   the buffer as Annex C's leaky bucket, full at the start): Best's orbit says 4.1.
5. **A new orbit eases in and out; a looping one does not** (owner's to confirm). `DroneOrbit.ease`
   follows a raised cosine over the first and last `ORBIT_EASE_SHARE` (0.15) of the time, the share
   a keyframe path eases over: the speed rises from 0 with no kick and joins the cruise with no kick,
   and the cruise is 1.18 times the even speed. An eased orbit is not a loop: it ends at rest on its
   first view. The dialog's **Start and stop smoothly** is on for a new orbit and off for a loop.
   It is a stored, additive, defaulted field of a saved orbit (`"ease": true`, written only when
   set): an orbit saved before it has no field, loads as the even loop, flies the frames it flew
   (pinned frame by frame on the pre-#807 entry), and is written back unchanged. A keyframe path
   keeps its linear ramp: changing it would move every saved path's frames.
6. **The orbit has a tilt control, 18 degrees for a new orbit** (owner's to confirm). The view's
   31.6 degrees shows no sky at all (the survey's 0.7-2.8 % were blue pixels below the horizon:
   the pond, the trampoline, the haze); at 18 degrees the sky is 5.4 % of the picture (measured 5.37,
   analytic 5.36 at 40 degrees' field of view), the horizon sits in the top fifth and every bed
   still shows at every turn of the family garden; at 12 degrees the house hides the garden from
   behind. The range is the view's own, 5 to 89 degrees, and never so low that the eye comes closer
   than `MIN_EYE_CM` (20 cm) to the ground (`orbit_pitch_range`: at a 1 m orbit the floor is 11.5
   degrees). The tilt is one value: the control shows it, a saved tour brings its own exactly (not
   the control's rounding), and **Use Current View**, now always on the orbit page, puts the view's
   own tilt into it so the first frame is the view. The orbit's place and distance still come from
   the view (or the saved tour).
7. **A new orbit takes 30 s a turn** (owner's to confirm). At 12 s a turn the horizon a lower tilt
   brings into view moves 26 px a frame across a 1080p picture; at 30 s 10 px (12 px at the eased
   cruise). The duration follows the camera until the user sets one: 30 s a turn for an orbit that
   leaves the clock alone, 12 s for everything else, because a year's regrowths cost a second and
   2 MB each, eight per second of video (#531). A file that names no duration still gets 12 s.
8. **A moving camera keeps the view's locked shadow map** (decision 5 of this ADR, #734). An eased
   orbit's slow ends crawl less, not more: the board's `--stairs` orbit, locked, High, 1080p, the
   shadow's edge 0-10 / 10-20 m out: 0.079 / 0.094 px a frame at 0.5 degrees a frame (the reference),
   0.071 / 0.064 at 0.05, 0.043 / 0.036 at 0.01.

The second proposal of the issue, a PNG sequence for an external master-quality encode, has been
there since L6.2: **Save PNG Sequence...** writes every frame losslessly (`frame_000001.png`, ...).

**Alternatives rejected**: a higher bit rate in the average mode (the first second stays starved,
and the encoder stops spending near 32 Mbit/s); one fixed quality (Best everywhere costs 1.4 times
Standard's size for files that are not published); High profile through `ctypes` into the wheel's
`avcodec` (version-specific structure layouts, a second encoder path to keep in step with Qt's);
an `ffmpeg.exe` or `imageio-ffmpeg` (rejected again, ADR-072); tagging only the `colr` box (a decoder
that reads only the bit stream would still guess); tagging only `avcC` (the in-band SPS at every IDR
frame overrules it); easing every orbit (a looped video would stop at its seam); easing paths with
the new curve (saved paths would fly other frames); a tilt saved apart from the orbit's pose (two
truths for one number); a 30 s default for every tour (a year's time-lapse would cost 2.5 times the
regrowths and #531's memory).

**Consequences**: no `FILE_VERSION` change: one additive field inside a saved orbit, which an
older build ignores (and drops when it saves the tour again, like any field it does not know).
A finished video costs one extra copy of the file on disk while it is tagged (about 1 GB a minute
at 4K Best, see below), and the delivery waits for it. 12 new UI strings. The consequences above
that say "an MP4 carries no colour tag" (this ADR) and "the MP4 keeps relying on the HD
convention" (addendum #733, decision 2) are superseded: the frames are still HD and BT.709, and the
file now says so. Pinned by `tests/unit/test_mp4_stream.py` (every SPS variant, the box rewrite,
the level, the refusals), `tests/unit/test_camera_path.py` (the even orbit's old frames, the eased
one's rest and smoothness, the tilt range), `tests/unit/test_camera_tours.py` (the pre-#807 orbit,
the new field, the default duration), `tests/integration/test_video_writer.py` (constant quality, the
tags read back by Qt, the untagged fallback, the kept render), `tests/integration/test_directors_cut.py`
(the dialog's defaults, the tilt clamp, Use Current View, Save Video end to end) and
`tests/integration/test_tour_persistence.py` (the older orbit through the dialog, an eased tilted
orbit kept and flown again); the render tier's tour scenario probes its MP4.

## ADR-072 addendum: tour and video reliability (#889, #890, #891, #896)

**Status:** Shipped in v1.40.2; owner manual testing accepted on 2026-11-14.

**Decision:** Refine #807 decision 3's fallback: a structural `Mp4Error` is a failed
delivery, not permission to overwrite a good destination with an unreadable part.
Keep that part and name it in the translated failure message. Validate the encoder's
table counts, chunk runs, sample bounds and durations before attempting colour tagging.
Only a structurally intact part may be delivered untagged when optional tagging fails
with an unexpected `Exception` (including allocation errors) or an I/O error. Log the
exception and final path; do not expose a bare exception as the entire user message.
Temporary-copy cleanup must not hide the delivery outcome or its primary exception.
Before untagged fallback, read and validate the samples too: an early copy failure can
otherwise bypass the tagger's later malformed-NAL detection. This extra full scan is
needed only on fallback, not on every successful recording.

A delivery worker already owns a closed recording. Window close waits for it within
the existing limit, then names its destination and its retained-part path on failure;
it must not describe that recording as an unfinished file left at the part path. The
non-daemon worker finishes independently of the window.

A `SavedTour` validates an orbit by sampling its first camera key, using the same FOV
and camera rules as playback. A hostile plan produces at most five per-entry warnings
and one aggregate skipped count; later valid entries are still read. Valid saved
motions, serialized data and the file version stay unchanged.

**Locale scope:** #896's date/time adapters landed in #838 and its coordinate formatting
landed in #908. Keep those shared helpers. Explicit integration coverage now exercises
German/English on opposite system locales, pasted decimal marks, metric/imperial
coordinate rows and save/reopen without changing stored numeric values.

**Rejected:** unconditional untagged promotion after a layout error (destroys a good
video); a second MP4 repair or encoder path (cannot prove the missing bytes); an
unbounded GUI-thread join on a gigabyte copy (freezes close).

**Pinned by:** `tests/unit/test_mp4_stream.py`, `tests/unit/test_camera_tours.py`,
`tests/integration/test_tour_video_reliability.py`, and the real encoder/decoder workflows
in `tests/integration/test_video_writer.py`.

## ADR-072 addendum: a drone orbit's part turn (#966)

**Status**: Shipped in [v1.41.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.41.3) after owner acceptance (2026-11-23; [PR #998](https://github.com/cofade/open-garden-planner/pull/998)).

**Context**: `DroneOrbit(turns=0.5)` already existed in `core/camera_path.py`, but the
tour dialog offered a `QSpinBox` of whole turns (1–4) and `SavedTour` refused any
non-integer. A garden with a house on one side could only fly a full turn, so three
bundled examples showed the back of the house for half the video.

**Decision**:
1. **Turns are a part or a whole turn.** `ORBIT_TURNS = (0.25, 4.0)`; the dialog's
   **Turns** is a `QDoubleSpinBox` with two decimals and a 0.25 step (the tooltip
   explains the garden-side use). `default_duration_s` multiplies
   `ORBIT_SECONDS_PER_TURN` by the fractional turns, so a half turn lasts 15 s.
2. **The file carries the fraction.** `_orbit_dict` writes an integer when the value is
   whole and a float otherwise; `_orbit_from` clamps any written value to the dialog's
   range and rounds to two decimals. `SavedTour` validates the range, not integrality.
3. **The bundled examples use it.** Terraced-house, Mediterranean and modern gardens
   store a counter-clockwise (`ORBIT_CLOCKWISE = False`) half-turn orbit sweeping across
   the south/garden side opposite the house; their first frame is still the stored view.

**Alternatives rejected**: a separate "half turn" checkbox (two truths for one number);
only whole turns in the file (a plan could not say what the dialog offers); a fixed
half-turn preset (a quarter turn is useful on a small courtyard).

**Consequences**: no `FILE_VERSION` change; `turns` stays the same additive orbit
field with a wider value range. An older app rounds a fractional value to a whole turn
(a stored 0.5 becomes 1) and flies a full turn; it does not fail to open the plan. No new
UI string except the tooltip, translated in all five locales. Pinned by
`tests/unit/test_camera_tours.py` (round trip, clamp, default duration),
`tests/integration/test_directors_cut.py::test_a_part_turn_starts_the_orbit_at_the_view_and_stops_half_way_round`,
and `tests/unit/test_example_specs.py` (the three stored half turns).
