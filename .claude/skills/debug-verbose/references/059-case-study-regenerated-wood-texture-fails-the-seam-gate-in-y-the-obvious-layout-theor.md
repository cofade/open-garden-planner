## Case study: regenerated wood texture fails the seam gate in y — the "obvious" layout theories were wrong, one primitive default was the bug (Package 3b #309, fixed 2026-08-18)

**Symptom.** `check_texture_tileability.py` reported `wood.png x=0.65 y=1.85 SEAM` right after the new numpy torus painter produced it; the planks run vertically, every grain line is a `sin(2πk·y/256)` (periodic by construction), knots are windowed modulo the tile — nothing in the layout should have a y-seam.

**Wrong theories (each plausible, each 10 minutes).** (1) The full-height plank `rect`s were painted with `h = SIZE + 4`, so their bevelled top/bottom edges wrap into a dark horizontal band at y = 0/256 → added an infinite-height mode (`h=None`) → *still 1.88*. (2) The wrap blur → ruled out by reading `wrap_blur` (it is `np.roll`-based).

**Key evidence.** Measured instead of theorised: per-column `|row0 − row255|` on the PNG → the top offenders were columns 16, 48, 80, … 240 (step ≈ 27) — exactly the plank-*joint* columns. Then painted the joint primitive alone on a fresh `Tile((178,138,88))` and printed the canvas at rows 0–2 vs 509–511:

```
row 0    [178. 118.2 110.  118.2 178.]
row 511  [178. 178.  142.4 178.  178.]
```

Coverage of a supposedly constant-width line fell from full (110) at the top to a third (142) at the bottom.

**Root cause.** `Tile.capsule(..., taper: float = 0.0)`: the parameter means "width fraction remaining at the far end", so the default made every capsule a pointed blade. Only `grass_blades` passed `taper` explicitly (0.05, intended); the wood joints, mulch splinters, compost straw, slate cleft streaks and bark cracks were all silently tapered — the wood joint's taper crossed the wrap and became the seam.

**Fix.** Default `taper = 1.0` (constant width); docstring states the semantics. All 24 textures re-rendered; max seam ratio 1.43 (0.95 — pebbles, x — after the senior review's second finding — integer sampling put a half-pixel bias into wrap-centred joints — was fixed by sampling at pixel centres).

**Lesson.** The seam metric already knows *where* the seam is — ask it (per-column diff) before forming a layout theory. Then isolate the suspect primitive on a blank canvas and print numbers at the two rows that must agree; a two-line probe beats two plausible refactors. Recorded as debugging-playbook row 36 and §11.4.

