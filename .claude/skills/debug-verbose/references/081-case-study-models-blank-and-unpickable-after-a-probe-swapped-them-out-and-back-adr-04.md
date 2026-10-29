## Case study: models blank and unpickable after a probe swapped them out and back (ADR-048 spike, fixed 2026-10-04)

**Symptom**: the Windows evidence run picked **0/20** where the container picked 20/20 with
the same code. A board render after the same flags looked normal up to the probes and was
not looked at afterwards.

**Wrong theories**. (1) A Direct3D 11 vs OpenGL picking difference — plausible, because the
container renders OpenGL and the runner D3D11 on WARP. (2) Display scaling on the runner.
Both died on one reproduction: the Windows command ran `--iou --orient` *before* `--pick`;
the container run had not. Running `--orient --pick` locally gave 0/20 on OpenGL too.

**Key evidence**: an A/B over the swap itself, picks and a pixel diff against the first frame:

```
1 initial                         hits=20/20
2 same objects re-attached        hits=0/20     frame == empty scene (diff 66.34 vs 66.34)
3 fresh SpikeModel+NumpyGeometry  hits=20/20    frame == initial (diff 0.00)
B re-attached + update():         hits=0
C re-attached after set_mesh():   hits=20
5 partial removal then restore    hits=19/20   <- after the first fix
```

**Root cause**: once the Model using a `QQuick3DGeometry` is destroyed, the same geometry
handed to a new Model renders and picks nothing (the C++ object is alive — `sip.isdeleted`
is False — but its data is gone); `update()` does not restore it, a full re-upload does. The
probes restored the scene with the same model objects, so everything measured after them —
picks, the soak, its re-entry times — ran against an empty garden. The first fix
re-uploaded only models that had been removed and measured **19/20**: a `Repeater3D` over a
JS array destroys and recreates **every** delegate on any change, so the one model that never
left came back blank too.

**Fix**: `SpikeRenderer.set_models` re-uploads every previously shown geometry; the pick probe
re-checks after a detach/re-attach cycle and the render tier runs it after `--iou`.

**Lesson**: (1) **A probe that mutates shared state must restore it through the same path the
product uses** — and every measurement after it inherits its mistakes silently. (2) When a
fix scores 19/20, the miss is the hypothesis test: here it was the model that had never been
removed, which disproved "only removed models break". (3) Compare the *same flag order* on
both machines before blaming the platform.

