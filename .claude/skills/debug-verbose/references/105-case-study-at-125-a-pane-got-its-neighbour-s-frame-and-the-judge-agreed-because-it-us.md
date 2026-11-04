## Case study: at 125 % a pane got its neighbour's frame — and the judge agreed, because it used the suspect's own rule (Phase 17 L1.2, fixed 2026-10-12)

**Symptom**: none. Every tier green on three platforms and on CI. A reviewer set
`QT_SCALE_FACTOR=1.25`, made the 3D pane ONE logical pixel wider while nothing drew the view,
and asked the host for a frame: it got the frame of the pane as it had been — and a pick
against the old viewport — from a host whose contract begins "`grab()` returns the scene at the
window's current size, or it raises".

**Wrong theories**:

1. *"The size check is exact to the device pixel"* — the round before had written that, after
   replacing a tolerance of two pixels. The code said `abs(frame - logical * ratio) < 1.0`.
   That IS exact at a ratio of 1, 1.5 and 2: the three ratios in the tests.
2. *"The matrix would have seen a wrong frame: its judge compares every frame with the size Qt
   gives for the window."* The judge's comparison was `abs(...) >= 1` — the same inequality,
   written a second time. Round 1's judge had asked the suspect for its state; this one had
   copied the suspect's rule. Blind in the same place, for the same reason.

**Key evidence**: the reviewer's probe, before and after —

```
pane 442 -> 443 px: grab() HANDED OUT a 553 px frame (the frame of the 442 px pane was 553 px; a 443 px pane's is 554 px); state=live; pick -> {'hit': 'w', 'point': [-0.2, -0.0, 20.0]}
RESULT dpr=1.25: of 12 one-pixel changes with the render target behind, grab() handed out the OLD frame 0 times and refused 12 times (skipped 12)
```

and the arithmetic that says how often: of 11,993 neighbour frames (a window one or two logical
pixels beside the one asked for) 750 passed at 1.25, some at every ratio strictly between 1 and
1.5, none at 1.0, 1.5 or above.

**Root cause**: Qt sizes a render target as `QSize(logical) * ratio` — `qRound` per side. The
right frame is therefore at most HALF a device pixel off `logical × ratio`; "less than one"
leaves room for a neighbour wherever the product ends in .5 (442 × 1.25 = 552.5 → 553, and
553 is 0.75 off 553.75). Nobody had written down what "exact" was exact against.

**Fix**: the host: at most half a device pixel off. The judge: its own `qt_round`, and equality
with it — not the host's predicate. The arithmetic for every width from 2 to 3000 at twelve
ratios against `QSize * ratio` asked of Qt itself, in the default tier; one real-window row at
125 %, which first asserts with a RAW grab that the render target is behind (a row that cannot
fail proves nothing).

**Lesson**: **an oracle must come from somewhere else than the thing it judges** — from the
platform's definition, never from the implementation's tolerance. If the test and the code
share a formula, the test checks typing. And **test where rounding bites**: between the round
ratios, at the widths whose product ends in .5 — not at 100 %, 150 % and 200 %, where any
tolerance below one pixel is exact.

