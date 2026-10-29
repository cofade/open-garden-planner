## 8. Owner taste log (append-only, newest last)

- **2026-10-03** — chose Lush Cinematic, experience + analyze, 100 % procedural; asked for
  both a creator and an independent reviewer agent; wants "really usable, beautiful, modern".
- **2026-10-05** — signed off the L0 Beauty Board on his dedicated GPU ("images look good, day and
  night"). No open taste points: his fifteen open questions (winter leaves, moon shadows,
  path/wall widths, partial-shade truth, grade, unplanned ground, pond hue, unmodelled heights,
  golden-hour ramp, roof hue, fruit without data, small-leaved crowns, sunset framing, crispness)
  are all answered *keep as-is*. Gave **GO** on ADR-048 (Qt Quick 3D replaces Qt 3D; `QQuickView`
  host; the D3D11 leak accepted open, closing in L1.3). Owner-GPU numbers in ADR-048 entry 19.
- **2026-10-19** — accepted L1 (PR #484, v1.30.14) after the 36-step manual checklist, with no
  problems found, and kept every look decision put to them as built: the twilight fade through
  civil twilight into a moonlit night (not a hard switch at sunset), the noon horizon's lime band
  (not a haze), 4× MSAA at Low, and the flat sky and even fill light in compatibility mode;
  accepted the new view's cost over the old window (no lighter default preset); and shipped the
  default with #532 open (ADR-060 addendum D5).
- **2026-10-27** — L4 manual pass (PR #613): "all the rest works perfectly", but soil did not
  look like soil and gravel not at all like gravel (translucent strokes, dots, pebble "tents"):
  both are now their textures, opaque. Objects without a height must cast in 3D ("in 3D they are
  also displayed with some height"). The 2D house should be terracotta like its 3D roof (walls
  stay a separate sandstone). Windows either side of a centred door: yes. The fog was too
  aggressive ("I usually only ever see fog, until I zoom in"): it now follows the camera.
  Porosity of tables and frames: fine. The silent overhang clamp and the "mushroom" shed: keep.
  The detail-normal strength is still open: they asked to be shown, with walk-height views.
- **2026-10-27** — L4 second manual pass (PR #613): paths, house colours, camera and fog fine.
  Detail-normal strength 3.0 (from 1.0), chosen from walk-height views of gravel, earth and
  paving side by side. Every standing object gets a real height ("doesn't make sense that a
  parasol doesn't have a height, while a trampoline has it"): the open frames' solid 2D
  shadow is accepted.
- **2026-10-27** — L4 third manual pass (PR #613, shipped v1.34.0): "all perfect" — every
  decision above confirmed as built, with no further change requested. Detail strength 3.0's
  sky-blue gravel highlights under a low sun (#619) remain an **open** taste question, not
  settled by this pass.
- **2026-10-27** — rejected sparse, isolated example layouts: crops must fit inside
  actual soil; food-forest companions need realistic groups and cultivated beds;
  mature perennials need credible planting history. Balcony examples need planted
  troughs and believable furniture/enclosure. All examples need localized tutorial
  annotations, a northern location for solar study and useful soil demonstrations.
  These are content requirements, independent of L4's built-world mesh work.
### L4 hardening follow-up (#604, #618, #624)

Judge lawn blades against a blade-free frame of the **same High look** before
comparing presets: Low/High also differ in AO, lighting and shadow filtering.
The lawn-only upward normal fold leaves plant grass unchanged. Measured sunlit
walk ROI: mean175.236 with blades /175.387 without, added dark share0.692
percentage points (original blades added about7.38). Do not compensate for a
preset's own lighting difference by brightening lawn albedo.

The meadow spans20km in100m cells with a16km far plane; perspective shadows
follow reach to allfour plan corners plus10m, capped by fog reach with a90m
floor. The board's distant horizon rows span67/202/403/600m at default/15degree
pitch; outer18% bands are separate, adjacent-rowstep<=3luma, two-row/full/border
steps retained as diagnostics. The two viewport-border rows lack the full
postprocessing neighborhood and are excluded explicitly from the valid-row gate.
Use `--far-plan` for bench_large shadow-on/off pairs at2x/4x framing.

- **2026-10-27** - #627 manual pass of the #628 height field: "it works, but all the objects
  loose their texture when giving them height" - a lawn raised to 40 cm drew as a flat green
  slab, a soil bed as plain brown, while both are textured on the ground. A solid now carries
  the item's own canvas fill on its faces (`MeshPart.fill_texture` -> `vcPart.baseColorMap`;
  measured top-down luma std 26.0 with GRASS against 0.0 with SOLID). The look is the 2D
  picture extruded, not a new material; the frame of a raised bed and a container's soil keep
  the builders' own look, and an X-ray ghost of a raised surface is its flat colour.
