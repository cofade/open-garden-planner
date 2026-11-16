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
