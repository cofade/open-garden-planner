## Case study: ~30 MB per project reload, and it was our keep-alive list (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the first soak with real project reloads (`--soak 50`: 50 hide/show cycles, every
fifth one reads the plan from disk into a new scene, re-bakes the ground and builds every model
and geometry new) exited 0 — no crash on the QML-vs-Python lifetime path — but RSS went
700 → 1015 MB.

**Wrong theories**. (1) The engine keeps the GPU buffers of destroyed `QQuick3DGeometry`
objects. (2) RSS growth is just the allocator not returning memory to the OS. Both were
plausible; the total-growth number could not tell them apart.

**Key evidence**: one A/B with a temporary toggle, RSS recorded after every refill (with
`gc.collect()` first, so cyclic garbage does not count):

```
keep every ground texture : 771 822 844 910 939 969 969 998 1005 1035   (+30 MB per reload, linear)
hold only the shown one   : 771 805 799 864 864 889 889 887  887  882   (settles)
```

The per-reload step matched one baked ground: 2400×1600 RGBA = 15.4 MB in the texture data
plus its GPU copy (system RAM on a software rasteriser).

**Root cause**: `SpikeRenderer.set_ground()` appended every `ImageTexture` to an append-only
`_keep` list (Python owns the texture, so *something* must hold it while QML shows it). Engine
and geometries released their memory; our keep-alive did not. Releasing the replaced texture
*after* the scene shows the new one ran 10 reloads clean (llvmpipe).

**Fix**: hold exactly the texture the scene shows; `preserved_state()` re-pins the texture it
restores. The soak now reports the RSS curve and its least-squares slope over the second half
(`rss_tail_slope_mb_per_reload`); the render tier and the CI driver require < 10 MB/reload.

**Lesson**: **judge a leak by its slope, not by total growth.** Both variants grew ~70 MB on
the first reload (a second model set, allocator arenas); only the trend separates a leak from
an allocator settling. And a keep-alive list is a leak with a good excuse: hold the one
object that is in use, not every object that ever was.

