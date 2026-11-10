## 24. Qt's ambient occlusion on flat ground, its bias and the picture size; height fog; a custom material's vertex colour (#687)

Concept: docs §8.29.13; decisions and numbers: ADR-070 addendum (#687); lessons PF-L3D-26,
PF-L3D-27, PF-E3D-28. Measured on the dev box (RTX 4070, Direct3D 11, PyQt6-Qt6 6.12.0,
2026-11-10), the family garden through the board (`render_beauty_board.py --living`, its
`living_occlusion` phase) and through `Quick3DHost.capture` (#831's setup). Source reading
(qtquick3d 6.10 `ssao.frag`, `fog.glsllib`) only where it says so; every behaviour below was
measured on 6.12.

- **Flat ground occludes ITSELF.** Read in the source: the pass derives its normal from depth
  derivatives normalised over the camera's whole range (`clipFar` 1.6e6 cm), so it is
  effectively camera-facing; measured: open ground seen at a slant darkens wherever no nearer
  object stands in its samples. At the spike's 55 / 14 / 0 (strength, distance, bias), High,
  1280 x 720: the meadow far from objects 12-13 levels darker than without AO, the snowy lawn
  25 (17 under the Low preset, which has no AO), the overcast lawn 15.6 — and the meadow
  straight above a silhouette 9.5-10 levels LIGHTER than far away (the samples that land on the
  nearer object do not count): the light rim the 3D survey saw round the beds.
- **`aoBias` ends it, and with it most contact.** The bias moves the samples towards the camera
  (cm). Against the reach D (`aoDistance`), at strength 99: bias 0.16 D left a 6-8 level rim,
  0.25 D 3.1 on snow, 0.3 D 1.2-2.1 (far self-occlusion 1.9-2.8); 0.5 D did nothing at all — a
  box caster's lit-side foot 0.004 against 0.022 for the clear look. Strength and reach without
  a bias (99 / 35 / 0) greyed open snow by 49. The contact a box's foot shows under a
  sky-lit day by its geometry is 0.10-0.17 in display luma (sky view factor of the ring 2-14 cm
  against 60-120 cm out: 0.58 / 0.87); Qt's pass with a rim-free bias gives 0.040.
- **The capture's AO scale must take the bias too.** `captureAoDistanceScale` shrinks the reach
  above 1080p (#733); with the bias left as it was, a 4K overcast picture read +4.51 levels over
  1080p (mean, shrunk to 360 rows), scaled +1.25.
- **What the bias leaves is a ring that moves with the picture.** On #831's far camera
  (medium, sun 38°/250°) the open meadow at 1080p is darkened 0.1 / 7.4 / 18.7 / 16.1 / 7.2 /
  3.5 levels in 40-row bands from the horizon down at bias 0.3 D, and the peak moves nearer at
  720p and 360 px (the sample radius is a world radius on a pixel grid). Pane against 1080p:
  overcast mean +4.14 → +0.73 at 360 px, but bands +13.4 / -11.7 (today +10.5 / 0); 720p +5.1
  / -7.5 (+3.9 / 0); 4K +11.1 / -7.9 (+2.1 / -4.0). A bias scaled by 1080/height below 1080p
  over-corrected (720p bands up to +8.7). On the board's closer cameras the ring is not seen.
- **Qt 6.12's height fog is a slab.** `Fog { heightEnabled: true; mostIntenseY: 0;
  leastIntenseY: 120 }` on the morning-dew shot: the ground nearest the camera +121.6 levels
  (fully fogged), the middle rows +29.7, the far rows under the horizon +0.8; density 1 and 0.3,
  `heightCurve` 1 and 4 drew the SAME frame (read in the source: the curve's place holds the
  enabled flag, and density does not scale the height term). A ground mist cannot be made with
  it.
- **`VAR_COLOR` in a CustomMaterial without its own vertex stage is not the colour a
  PrincipledMaterial reads.** The same roof vertices: principled (vertex colours on, white
  tint) 187 / 99 / 71; a shaded custom material reading `VAR_COLOR.rgb` 136 / 46 / 39 (darker,
  more saturated); the same material with a vertex stage that hands `COLOR` on through its own
  varying 187 / 99 / 71, to the level — as `foliage.vert` does. `screen.frag` and
  `water.frag` read `VAR_COLOR`.
- **The world normal in a shaded custom fragment is `NORMAL`** (as `foliage.frag` reads it for
  its snow): a snow mix driven by `normalize(VAR_WORLD_NORMAL).y` barely showed (a roof pixel
  165 / 80 / 58 against 223 / 205 / 198 with `NORMAL.y`).
- **A negative horizon row.** `Pinhole.horizon_row()` is negative for a camera looking down
  enough that the horizon lies above the frame (-131 on the board's overcast and snow cameras);
  a probe that slices `[:row]` with it takes every row but the last ones (PF-L3D-27).
