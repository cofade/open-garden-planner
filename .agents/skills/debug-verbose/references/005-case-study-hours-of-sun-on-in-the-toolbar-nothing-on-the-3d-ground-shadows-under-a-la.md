## Case study: Hours of Sun on in the toolbar, nothing on the 3D ground; shadows under a lawn (PR #584 manual pass)

**Symptom.** The owner's screenshot: toolbar Hours of Sun on, the canvas showing its
map, the 3D ground showing nothing. Separately, the 2D shadows and the map were hidden
under a lawn ("objects of height = 0 like grass").
**Wrong theories.** None adopted. Candidates measured before any change: the ultra
preset (SSR, 8x MSAA), a 151k-vertex drape on a 50 x 30 m plan, Animate running, the
drape grabbed but never presented, depth fighting with the lawn's ground tile.
**Evidence.** An external probe drove the real `GardenPlannerApp` on the real engine at
the owner's settings, printing `[386-DRAPE]` from monkeypatched controller methods:
`_drape_mesh shown=(2031-03-24, 300, 500) -> (151604, 'verts')`, `root drapeVisible
True`, and a desktop capture of the presented frame equal to `host.grab()`, both
showing the drape, in every order (menu first, 2D Shadows first, toolbar first). The
pipeline was sound, so the screenshot's state had to be "Nothing on the Ground" with
the toolbar on — reachable only from the toolbar side. For 2D: overlays fixed at z -500
/ -450, "below every layer item".
**Root cause.** The 3D drape followed the shared switch going off, never going on. The
2D overlays sat under every layer item, so anything flat drawn over the ground hid them.
**Fix.** The drape follows both edges (off brings back what lay there before), and a
3D view opened with Hours of Sun on lays it (PF-L3D-09). The garden's ground surfaces
(a lawn, path, terrace, driveway, pond, in-ground bed without a height, and groups of
only those) take a z band below the overlays, order kept (PF-CAN-22). Review of the
first version found three more defects. Widening the rule to "everything without a
height" sank a cold frame under its raised bed. Arrange still ranked over the whole
layer, so a step could change nothing visible. Grouped lawns stayed above the
overlays. Arrange now works inside a band, and a group of only surfaces takes the band.
All probe code stayed in the scratchpad.
**Lesson.** When a report contradicts a green suite, reproduce the user's exact state
on the real artifact first. A sound pipeline turns the question into "which state
shows this", and here the answer named the missing edge. When one property gets two
orders (rank and drawing), check every surface that acts on one and shows the other.

