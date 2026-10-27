# 3D hardening after L4 — 27 October 2026

Scope: #611, #607, #604, #617, #624, #618, #609, #600, #603,
#626 and #536, delivered together. This report records the measurements; ADR-065
and the pitfall entries hold the contracts. Owner executable acceptance confirmed on 27 October 2026; shipped in v1.34.1 via PR #630.

## Path alpha (#617)

The fail-first interior probe measured a maximum channel change of 26 for gravel
and 8 for dirt at 50% painter opacity. The rim was under the texture. An odd-even
pair of stroke outlines failed again at a bend and a crossing; Qt's stroke uses
winding overlaps. Exact vector subtraction passed the pictures but took 582 ms
for 1,024 vertices and 6,628 ms for 4,096 vertices on this machine.

The chosen mask paints the outer stroke and erases the complete inner stroke
with DestinationOut in device tiles no larger than 512 × 512 pixels. Each tile
is then composited once at the item opacity. The texture remains a pattern fill
for SVG/PDF. Opaque items keep the existing fast stroke because their texture
covers its underpaint. The clipped 340 × 140 probe took 3.8 / 14.9 / 60.7 ms at
1,024 / 4,096 / 16,384 vertices; work follows the input cap and visible output,
with no intersection search or whole-path-sized image allocation.

`test_translucent_path_rims.py` covers straight lines, bends and crossings;
layer opacity, colour alpha and their combination; rotated/Y-flipped painting;
the actual CanvasScene layer; and bounded allocation with vector subtraction
disabled. Existing SVG, PNG and PDF tests remain part of validation.

## Render measurements (#600, #603, #609, #536)

The selection oracle now exports the workspace sink's admitted mesh triangles,
including its forged LODs. CPU projection and ray intersection remain independent
of engine picks. A still-picture oracle requires a zero wind clock, not a clock
paused at a nonzero phase. Workspace waits include ground, camera motion, pending
forge jobs, in-flight admissions and the forge timer.

A document reload deliberately invalidates the forge's applied-state book.
Therefore a full rebuild uploads v0 parts plus their forged replacements; a
reload with retained SceneSync records re-admits the forged parts. The soak
counts both stages explicitly and separately asserts zero uploads for an
unchanged pass within the same document. It takes one readback before the loop
and one after; frames inside the memory loop are presented, never grabbed.

The fractional-pixel lifecycle child fixes both the screen factor (1) and the
application factor (1.25). Qt multiplies them. The full-window selection scenario
uses the desktop work area via maximization, rather than requesting 1500 × 900
logical pixels on a smaller scaled display. Startup drivers retry a STARTING
host's short idle refusal within one total 10 s deadline. The product host's
0.5 s idle policy is unchanged.


The final selection run exposed one more contract difference: both CPU leaf
hits at a remaining mismatch were back faces (determinants -903.39 and -923.48).
Qt 6.11.0's [triangleIntersect implementation](https://raw.githubusercontent.com/qt/qtquick3d/v6.11.0/src/runtimerender/qssgrenderray.cpp)
accepts only positive determinants and comments out its back-face branch. A
NoCulling material does not change that picker contract until Qt 6.12. The
workspace selection witness therefore filters front-facing triangles from the
raw admitted mesh using the fixed camera eye; the general two-sided collision
and analysis oracle remains unchanged. Front/back winding regressions and an
explicit Qt 6.11 guard require recharacterization on upgrade. Seeded clicks
increase from 60 to 80 while retaining the minimum 45 robust comparisons.

## Ground memory (#626)

The failed master run 40505527450's downloaded Windows artifact contains this
default-adapter curve (MB):

```text
658.05 674.31 690.45 685.15 661.14 693.24 661.20 693.30 661.27 661.11
693.23 693.25 661.12 691.22 693.25 661.13 691.23 693.32 661.21 691.36
```

Its median last-ten step was 2.06 MB/cycle, while readings alternated between
in-flight generations roughly 32 MB apart. The separate WARP soak in the same
artifact was flat. A fixed 20 ms event pump was not a release boundary.

After waiting for two presented frames per cycle, the local hardware curve reads
0.000 MB/cycle and WARP 0.030; the deliberately retained-texture controls read
32.190 and 32.195. Grabbing twins read 0.000 and 0.005. Every cycle presented at
least two frames. The 2.0 MB/cycle upper bound, 8.0 control floor, median statistic
and 20-cycle sample count are unchanged. A display that presents nothing has a
bounded wait and reports that limitation instead of treating a readback as a
presentation.

## Lawn and far views (#604, #618, #624)

The original High walk ROI (867 sunlit lawn pixels) read mean 169.41 luma with
10.96% below 150. The lawn-only normal fold reads 175.236 and 4.268%. With blades
removed but the same High lighting, AO and shadow filter, the same ROI reads
175.387 and 3.576%: the blades add only 0.692 percentage points of dark pixels
and reduce mean luma by 0.151. This removes approximately 91% of the blade-induced
dark share. Low reads 188.50; its 13.11-luma difference from blade-free High is
a preset comparison, not evidence of back-lit blades. Changing roughness,
specular or forcing a vertical normal did not establish the issue's proposed
High/Low equality, and those trials are not shipped. Plant grass retains its
original shader.

Fresh distant horizon frames cover both presets at 67/202/403/600 m and default
and 15 degree pitch, with no Qt warning/error. Each outer 18% band is measured
separately. The final 600 m / 15 degree High frame reads 1.803 luma for adjacent
rows (3.543 over two rows, separately reported). Two image-border rows are
excluded explicitly: an SSAO sampling border at rows 538/539 of a 540-row frame
is outside the complete image neighborhood and is unrelated to the distant
meadow. Independent review judges this measurement boundary.

The far-plan probe at 4? framing (268.91 m) finds 3,323 shadowed samples out of
4,438 ground samples, with maximum shadow-on/off difference 81.517 luma and
outer-row step 1.045. The 2?/4? frames retain long shadows and show no 101 m AO
line. Every L4 object kind is included in the 43-row shadow agreement table.

## Delivery evidence

The full correctness/performance batteries, production render probes, independent
visual and senior reviews, frozen executable checks and hosted CI results are
recorded in the pull request after execution. No release or wiki publication is
All hosted CI checks, local frozen executable checks, and owner manual testing passed; shipped in v1.34.1 via PR #630.
