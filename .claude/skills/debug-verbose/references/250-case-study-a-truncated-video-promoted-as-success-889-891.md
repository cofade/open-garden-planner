## Case study: a truncated video promoted as success (#889, #890, #891, fixed 2026-11-14)

**Symptom:** a truncated MP4 replaced an earlier good video and reported success;
unexpected tagging exceptions exposed a raw error instead of identifying the render.
Closing during tagging named the part as unfinished although delivery continued.
An orbit with FOV 0 or 180 was saved but failed when sampled.

**Wrong theories:** optional colour tagging can always fall back to moving the source;
the writer's `finished` status proves its output is usable; a numeric range check
proves a saved camera can be sampled.

**Key trace:** `[MP4-TABLE] stsz count=65536 payload=32 required=262152` preceded a
`struct.error`. `[TOUR-DELIVERY] fallback after Mp4Error: the top-level b'moov' box's
size is wrong` was immediately followed by `promoting ...tour.part.mp4 to ...tour.mp4`.
The source was truncated by 100 bytes, and the earlier good destination disappeared.

**Root cause:** the fallback conflated optional annotation failure with invalid binary
structure. Counts and chunk runs were used before byte bounds were checked. The shutdown
report also conflated encoder closing with delivery; saved-orbit validation stopped
before the `CameraKey` that playback builds.

**Fix:** bound counts and runs by payloads, validate sample spans and timing, refuse
structural errors without replacing the destination, and allow broad optional-tagging
fallback only for an intact source. Bound detailed tour-load warnings and sample the
first orbit key at construction. Name both delivery destinations on a close timeout.

**Lesson:** preserve a render under its part name when its structure cannot be proved;
preserving bytes and reporting success are different claims. Test the encoder, delivery,
and close phases separately. Regression tests failed on unchanged master, including a
worker held by an event while the window closed. Locale coverage passed on master:
the merged date-field and units work already addressed #896.

Pins: `tests/unit/test_mp4_stream.py`, `tests/unit/test_camera_tours.py`, and
`tests/integration/test_tour_video_reliability.py`.
