---
title: "Photo mode"
prefixes: ["FR-3D-PHOTO"]
---

# Photo mode

- **FR-3D-PHOTO-01** (L6.1): The 3D strip's **Capture** menu (and View → Workspace) offers **Photo
  Mode**: a line of controls for exposure, vignette, blur and a colour grade (Golden Hour, Crisp Day,
  Cool Morning, Soft Film, Black and White). The view previews them at once. They change how the
  picture looks, never what stands in the garden, and with photo mode off the view is the view
  again, pixel for pixel. The blur is a share of the picture's height, so a saved photo of any size
  shows the blur the view previewed (#743: seen at the preview's size, within 0.06 of the detail a
  60 px tile keeps).
- **FR-3D-PHOTO-02** (L6.1): In photo mode a **click sets the focus** on what is under it (or on the
  ground) instead of selecting, and the line says how far away it is. The focus is a point: it stays
  on the plant when the camera moves. **Blur above 0 always has a point**: setting the blur without a
  click focuses what the camera looks at (while walking, the ground under the view's centre, not the
  mid-air point 100 cm ahead), so the slider always does something and the line never says "Click"
  beside a blur. Opening another plan keeps the blur and gives it the new plan's point once that
  plan's camera is framed; until then the line says the focus is moving.
- **FR-3D-PHOTO-03** (L6.1): **Save Photo** writes a PNG or JPEG at the view's size, Full HD, QHD or
  4K, whatever the window's size, without moving the view. No selection highlight is in the picture.
  The file says what date it shows. The picture uses the view's **quality preset** (`AutoPreset`'s
  current level, or the user's fixed choice) and keeps 1080p's look at 1080p and larger (a smaller picture is left as it was): the
  ambient occlusion's radius follows the picture's height, so a 4K picture's horizon band lies
  within 1 luma of 1080p's (ADR-072 addendum; the render tier's `picture` gate).

Acceptance: `tests/integration/test_directors_cut.py` (§8.10 — photo mode, the click, Save Photo,
the dialog, a recording end to end, every refusal, the blur/point invariant, the owner's date during
a tour, the clock-change hold), `test_agent_api_render_3d.py` (the real MCP transport),
`test_video_writer.py` (a real encode, read back; a kept render survives the next recording), the
unit suites `test_camera_path.py`, `test_video_yuv.py` and `test_scene3d_photo.py`, the render tier
`test_directors_cut_render.py` (including the two-week clock-change luma gate, and since #743 the
preview-against-4K blur parity and the slider's blur 0.05 against 1.0), and `--selftest`, which
captures and encodes from the bundle.
