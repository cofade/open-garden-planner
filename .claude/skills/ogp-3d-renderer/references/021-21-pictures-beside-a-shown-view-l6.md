## 21. Pictures beside a shown view: the capture view (L6, #390)

Concept: docs §8.29.15; decisions and numbers: ADR-071; tests: §8.10.17; lessons: PF-E3D-18,
PF-E3D-19, PF-E3D-20. Measured on the dev box (RTX 4070, Direct3D 11; WARP on the same machine),
2026-11-03, PyQt6 / PyQt6-Qt6 6.12.0:

- **A second `View3D` with `importScene: view.scene`, `camera: view.camera` and `environment:
  view.environment` renders the same picture.** The environment object can be shared, effects
  included. At the view's size: 0 levels apart on the GPU and on WARP. From another camera: 0 levels
  from the view moved to that camera. Declared after the main view with `z: -1`, under it.
- **`grabToImage` waits for the window's next frame; one `grabWindow` is that frame.** It renders on
  the spot, needs no display, and emits `beforeSynchronizing` and `afterRendering`, which the item's
  grab hangs on. `QCoreApplication.sendPostedEvents(result, 0)` then delivers its completion event,
  and `result.image()` is ready with no event loop at all. Measured `ready` after 0 passes, 30 of 30.
- **Size:** `explicitTextureWidth` / `Height` fix the render target in device pixels; `grabToImage(s)`
  gives `s × ratio` pixels, so pass `size / ratio` (at 125 %, 1280 x 720 came back 1600 x 900).
- **Cost at bench_small:** 720p 25 ms, 1080p 20 to 65 ms, 4K 54 to 140 ms on the GPU; 1080p 420 ms,
  4K 720 to 950 ms on WARP. The first picture after a change of size is the slow one.
- **Memory:** a shown session's 300 pictures at 1080p and 100 at 4K are flat after one step
  (+450 MB at 1080p, +650 MB at 4K). A hidden `View3D` keeps those targets; one frame at the
  smallest size gives them back (back to +130 MB). A `Loader` that makes and destroys the view per
  picture: +20 MB per 4K picture, linear on WARP, and on the GPU a plateau at +1.2 GB that looks
  like nothing is wrong. Keep the view; let it rest small.
- **The chain in `tonemapper.frag`** (read it: `:/qtquick3d_helpers/shaders/tonemapper.frag`, after
  an `ExtendedSceneEnvironment` was created): exposure, dither, tonemap (clamped), glow,
  brightness/contrast/saturation (NOT clamped), LUT, vignette. The LUT is a `texelFetch` at
  `int(lutSize*b + r)`: below 0 it reads the previous slice, above 1 the next. Its `fixY` undoes the
  flip of a LOADED image, so texture data runs its rows the other way, and a `Texture`'s `flipV`
  does not reach an effect's sampler.
- **Vignette:** `mix(vignetteColor, colour, (u(1−u)v(1−v) × strength) ^ radius)`. Its default colour is
  GREY: it brightens whatever is darker (34 % of a night's pixels), so set black. A lower strength
  darkens the middle too; the exponent reaches only into the corners. Strength 15, radius 0.35 is
  Qt's default, and a dark one.
- **Depth of field compares DEPTHS:** `focusDistance` is along the view's axis, and `focusRange` is the
  whole band, half in front and half behind. The straight distance to a point near a corner kept
  0.37 of its sharpness. Blur is three taps, in pixels of the picture: scale it with the height (or
  a 4K photo is sharper than its preview), and above about 5 at 1080p the taps read as ghosts.
- **A capture from another camera has the view camera's plant LOD:** nothing but `_apply_camera` tells
  the forge about a camera, and `capture` must not. A tour gives it the whole flight first
  (`ForgeWorker.fly_path`: 0 levels from the view moved there, 17 on a close camera without it); an agent's single
  picture cannot wait, and its tool description says so.
- **Qt Multimedia in the wheels:** `QVideoFrameInput` is bound and works. `supportedVideoCodecs` for
  MPEG4 on Windows: MPEG1, MPEG2, MPEG4, H264, MotionJPEG (H264 is `h264_mf`, the system's encoder,
  Constrained Baseline). `errorOccurred` cannot be connected from PyQt6: its enum is unknown to the
  signature parser. Use `errorChanged`. `sendVideoFrame` returns False when the queue is full.
- **A probe on the full main window answers its own dialogs:** stub `_show_welcome_dialog` and
  `_confirm_discard_changes` first. A plan loaded `as_template` is dirty, so `window.close()` raises
  a modal "Unsaved Changes" that nobody clicks: the probe waits for ever, with no CPU, in the
  developer's face. `view3d_capture_driver.main_window_on_plan` does both.
- **Not measured:** the capture on xcb and llvmpipe before CI's first run; a display scale other than
  100 % and 125 %; what the frozen exe's encoder does on a Windows N edition.
