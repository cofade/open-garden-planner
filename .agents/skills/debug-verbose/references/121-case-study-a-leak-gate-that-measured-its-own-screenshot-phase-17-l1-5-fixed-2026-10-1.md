## Case study: a leak gate that measured its own screenshot (Phase 17 L1.5, fixed 2026-10-12)

**Symptom**: twenty full re-bakes of a 16 MB ground grew the process by 16 MB each on the
hardware adapter — although every replaced texture object was destroyed — and by nothing on WARP.
The gate was reported as an expected failure "in a Direct3D 11 window that presents no frame",
and the next story was told to apply edits no faster than frames are presented.

**Wrong theories**:

1. *"Direct3D keeps every UPLOAD until a frame is presented."* Half right: Direct3D does free
   released resources on Present. But nothing is uploaded for a frame that is never rendered.
2. *"The display is asleep, so the window presents nothing."* An OpenGL window on the same GPU
   presented 45 frames in the same session — in the gate's own table.

**Key evidence** — the reviewer took the `grab()` out of the measured loop:

```
no grab()                +0.000 MB/cycle     (0 frames presented, RTX 4070)
grab() every 5th cycle   +3.2
grab() every cycle       +16.1
all three on WARP        flat
```

**Root cause**: the soak called `host.grab()` after every re-bake "to take a finished frame". A
grabbed frame is rendered — its textures are uploaded for it — and never presented, so what it
uploaded stays committed until a Present. The growth belongs to the instrument.

**Fix**: the soak takes no frame in its loop and is an unconditional gate on the hardware
adapter and on WARP (measured: −0.10 to +0.01 and +0.02 to +0.14 MB a cycle); the grabbing soak
is kept as the control that must show the growth where nothing is presented. The rule for the
product: no repeated `grab()` on a live host that is not presenting — screenshots go through the
offscreen path. *What the re-check added:* that hardware cell presented no frame, so it rendered
nothing and cannot see the graphics side — half a gate. The other half is WARP (it presents)
and a manual check with the display on; a gate's report names the cell it measured.

**Lesson**: **a soak measures everything in its loop — before a growth is blamed on the thing
under test, run the loop without the instrument.** And an expected failure with a plausible
story attached is where a diagnosis goes to stop being checked: the remedy it handed on (pace
the edits) would have been built and would have fixed nothing.

