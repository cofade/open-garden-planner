# Case study: a black mat that read tan, and a gate that could not see it (#801, #803)

## Symptom

The 3D promo survey read the family garden's black trampoline mat (#303336) as tan facing a
golden-hour sun (luma 99, hue 23°) and its blue pad 32° off (#427bc2), and proposed rubber at
roughness 0.95 / specular 0.05. With the surface classes built and rubber at exactly those
numbers, the mat in a probe facing the same sun was still brown: luma 62.8, hue 21°.

## Wrong theories

1. **"Lower specular is a weaker highlight."** The issue's own model. A sweep of the amount at
   roughness 0.95 read 63.5 (0.35), 62.8 (0.05), 62.2 (0.02), 62.8 (0.015) — flat — and then
   25.4 at 0.01, 0.005 and 0.0: not a dial but a switch.
2. **The sky reflection (image light) makes the sheen.** Roughness moved it (73.2 at 0.90, 54.6
   at 1.0), but not the way a blurrier sky would explain a switch.
3. **The render-tier gate proves the fix.** The first class row put the trampoline 9.5 m in
   front of a 4.5 m house along the sun's azimuth: at 15° the house's shadow reaches 16.8 m, the
   mat lay in it, and with the OLD 0.78 / 0.35 everywhere the gate still passed (the mat 1.32x
   its specular-free luma; the tan needs direct sun). The pond gate passed the old, clipping
   glint too.

## Key evidence

```text
rubber 0.95 / 0.015 -> mat luma 62.8      rubber 0.95 / 0.010 -> 25.4
positive control (every surface 0.78 / 0.35), house to the side: mat 4.08x, 128 deg off -> FAIL
pond mask from the white/black water keys: the glint is bright in BOTH -> a hole where it is
```

## Root cause

Qt keys a principled material's specular in only above an amount of 0.01, and its Fresnel
reaches 1 at grazing whatever F0 the amount sets: any "dull" value above the switch is the full
sheen. The gate was blind twice: its scene put the mat in shadow, and its water mask was cut
out exactly where the glint was.

## Fix

Rubber and canvas specular 0 (PF-E3D-32); plastic fully rough (1.0: the pad 8.0° off its blue).
The gate judges each part against its OWN specular-free frame (PF-L3D-34), its class row stands
the house, shed and wall to the sides so their low-sun shadows miss the small things, and the
pond's keyed mask is filled row by row (it is convex). With every surface back at 0.78 / 0.35
and the old water shaders, 8 of its 10 tests fail.

## Lesson

A material "off" may be a threshold, not a zero: sweep across it before trusting a value. And
run every new gate against the defect it pins (a positive control with the OLD code paths) —
two of this gate's tests passed the defect until the control showed it.
