## Case study: Linux raster controls confused noise and paint order (#897) (2026-11-16)

**Symptom:** A translucent succession badge and an excluded sun-map label failed Linux pixel assertions.

**Theories checked:** Different fits were suspected, but both badge captures had the same scale, translation, viewport and tag bounds. The label was also absent from the chosen foreground labels.

**Evidence:**

```text
[BADGE897] scale=1.0888888888888888 dy=748 both; [LEGEND897] repeat=11 max_delta=4 sum_delta=48
```

**Root cause:** A transparent tag over white has a different threshold-green area; identical Qt raster draws can differ by sub-ink rounding.

**Fix:** Use the same view and full-coverage green interiors overlapped by the white pot. The sun-key test keeps a small channel bound below its visible-ink positive control. Remove blanket platform xfails.

**Lesson:** A pixel oracle must isolate the user-visible mechanism and demonstrate that its positive control still fails.

### Takeover: the remaining Linux font oracles (2026-11-16)

The first PR CI run still failed the area-label and SVG-note checks. Ubuntu 24.04,
locked Python 3.11.9 and Qt 6.12 reproduced ten cases. A misplaced region was not
the remaining label cause: instrumentation found the visible label inside the
measured region, but the 8 pt italic Liberation Sans glyphs had four solid-ink
pixels instead of the test's arbitrary minimum of twelve. Sample nonempty ink;
controls with absent text or absent halo must still fail.

```text
[LABEL897] region=(417,302,50,20) changed_bounds=[419,306,465,317] ink_count=4
[SVG897-FAMILY] actual=Liberation Sans canvas=239.25 QtSvg_list=275.5 primary_only=239.0
[SVG897-BROWSER] original_CSS_font_list width_cm=240.5
```

QtSvg on Linux treats the CSS family list as one family and substitutes another
font. Chromium renders the unchanged export at the canvas size. The test reader
uses the primary font-family token alone; production SVG, point-size assertions
and the 8% raster bound are unchanged. Do not change a correct export to match an
incomplete test renderer.

The map/time-of-day comparison passed twenty isolated repetitions, then failed
in a replay of the full Ubuntu coverage partition. Saved pictures isolated all
229 changed pixels to the key's text at x=22..384, y=411..439: maximum six levels
per channel, summed sixteen. Every map pixel outside the key was identical.
Keep exact equality outside the key's device rectangle; allow the existing
sub-ink key bound inside it. A mutation restoring the time-of-day shadow fails
the comparison on both Windows and Ubuntu. Sampling only the standalone test
would have missed the cause.
