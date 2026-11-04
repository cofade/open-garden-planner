## Case study: 34.6 MB per reload, and nothing was leaking in Python or in VRAM — two retentions inside Qt, and a soak that could not present a frame (Phase 17 L1.3, fixed 2026-10-12)

**Symptom**: the memory soak of the 3D workspace in the real app (20 reloads of `bench_small`,
every reload rebuilding the engine scene; private bytes; Theil–Sen over reloads 11–20) read
**34.6 MB per reload** against a bound of 10. Reloads that rebuilt nothing read 0.2. The
positive control (25 MB kept per reload) read 58.8, so the instrument worked.

**Wrong theories**:

1. *"Something of ours keeps the old scene — the controller's records, the plant shape cache,
   the sink's books."* `tracemalloc` between reloads 5 and 15 of the same soak: 0.045 MB per
   reload. A weak set of every geometry wrapper ever made: 0 alive.
2. *"Then it is a D3D resource, in VRAM."* DXGI's figure for this process
   (`IDXGIAdapter3::QueryVideoMemoryInfo`): 298.1 MB before, 305.6 after the first reload, 305.6
   after the twentieth.
3. *"It is the mesh buffers — 1.5 times their size per round — and they are freed at the end of
   a presented frame, which a readback is not."* TRUE, measured in a bare host (22 MB per round
   by readback, 6.5 with presented frames) — and in the production host presenting frames
   changed nothing: 27.9 and 38.5. A cause that explains the probe and not the product is half
   a cause.
4. *"The remainder is the QML engine's garbage, it will be collected."*
   `QQmlEngine.collectGarbage()` per round: 6.1 instead of 6.3 to 7.7.

**Key evidence**: a bare `Quick3DHost`, 100 Models of 3,000 vertices (14.9 MB of buffers)
created, drawn and destroyed per round — and ONE thing changed per run:

```
VARIANT buffers        SLOPE second half -0.13 MB/round          (no Qt object)
VARIANT geometry       SLOPE second half 0.00 MB/round           (no Model)
VARIANT models_hidden  SLOPE second half 0.78 MB/round           (never drawn)
VARIANT models         SLOPE second half 22.00 MB/round (x1.48)  afterFrameEnd 0  grabs 40
VARIANT models_update  SLOPE second half 6.77 MB/round (x0.46)   afterFrameEnd 40 grabs 0   [QT_D3D_NO_VBLANK_THREAD=1]
   + embedded 6.43 · foliage material 6.60 · host.clear() 6.13 · extra frames 6.33
   + PROBE_SUN=1            18.06 MB/round          <- the production difference
   + sun, verts=300         18.19   (x12.22 of the buffers)   <- not the mesh
   + sun, verts=12000       24.59   (x0.41 of the buffers)
   + sun, no shadow casting  6.17
   + sun, releaseResources() per round   3.90 (20 rounds) · 0.85 (60 rounds)
```

**Root cause**: two things inside Qt Quick 3D, and one about the instrument. (1) Qt keeps
cached per-draw-call state for every Model it ever drew, after the Model is destroyed — about
three times as much for a Model that also casts into the sun's shadow cascades — until
`QQuickWindow.releaseResources()`. (2) A destroyed Model's mesh buffers are freed at the end of a
PRESENTED frame; `grabWindow()` never ends a frame that way. (3) The display was asleep: Windows
presented no frame at all, so every frame of every soak on this machine that night was a
readback.

**Fix**: `Quick3DHost.release_cached_resources()`; the pipeline's passes count the items whose
Models they destroyed, and the workspace releases when 64 piled up and the pipeline is quiet,
or at once at 512. The soak's child runs with `QT_D3D_NO_VBLANK_THREAD=1` and asserts that
frames were presented. After: 3.9 and 4.9 MB per reload (the large plan 5.1, WARP 7.4; 1.8
over reloads 31–60 of a 60-reload run), the control 28, the same soak with the release out of
reach 29. What is left — about 20 kB per destroyed Model — has a floor in bare Qt: 3.4 kB per
`Model` with a material created and destroyed without ever being drawn.

**Postscript — the instrument was still in the picture.** Every number of that "After" came
from a soak that READ BACK once or twice per reload, and so did the next finding built on it
("a view that presents nothing keeps every byte uploaded to it", and a rule that paced the
pipeline by presented frames). A reviewer of another story took the readback out of the loop:
flat. Here, the same twenty rebuilds without a readback in the loop: 2.0 MB per rebuild
presenting and 1.5 with the view's frames withheld (19 and 1.5 without the release); with one
readback per rebuild and frames withheld 8.5 (26 without the release). The cached state per
drawn Model was real — the bare-host rows took no readback — but the dark-view growth was
the readback's own frame, never presented and so never given back. The pacing was removed;
the rule that stayed is "nothing takes a frame from the live view, and a soak takes none
inside its loop".

**Lesson**: **shrink it until one run takes seconds, then change one thing per run** — the
whole table above cost less than the first three theories. **Scale the suspect**: three vertex
counts said "not the mesh" in thirty seconds. **A cause must explain the product, not only the
probe**: theory 3 was real and was not it. **Know what your instrument does to the thing it
measures** — a readback is not a frame the way the product makes frames; list every frame the
measuring loop itself renders and run the loop once without them BEFORE a rule is built on
the curve. And when a fix lands,
keep three numbers from one instrument: with it, without it, and a control that must fail.

