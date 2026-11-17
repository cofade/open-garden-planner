## Case study: lighter hairline along sun-shadow outlines from DestinationOut + SourceOver (#854) (2026-11-17)

**Symptom:** A faint lighter 1-px hairline ran along every non-pixel-aligned sun-shadow outline (diagonal edges, round canopy discs, subpixel-shifted edges, and any shape at non-integer zoom such as 56 % fit).

**Theories entertained (wrong):**
- Blaming the coarse `falloff_pictures` lattice resolution or bilinear upsampling under-shooting `1.0` at edges. (Measuring `alpha_f` inside `layer` before step 4 showed `alpha_f = 110`, full shade alpha, along straight diagonal edges!)
- Assuming `DestinationOut` and `SourceOver` of complementary coverages $1 - c$ and $c$ sum cleanly to $\alpha$.

**Key evidence:** Measuring rendered darkness across the boundary (`_SHADOW_COLOR` $\alpha = 110/255$, full interior darkness `97`):
- 45° diagonal at `scale=4.0` before fix: `[..., 97, 97, 97, 86, 94, 92, 89, ...]` (`11`-level dip right at the boundary pixel where $c \approx 0.5$!).
- Disc at `scale=4.0`: `[..., 97, 97, 86, 92, 89, ...]`.
- L-corner, sunlit hole, and 4 cm slot at `0.56` fit zoom: `9–10`-level outline dip.

**Root cause:** `paint_feather` (`shadow_feather.py`) cut `shade` out of the offscreen feather `QImage` with `Antialiasing` + `CompositionMode_DestinationOut`, leaving $(1 - c)\alpha_f$ on boundary pixels with fractional inside coverage $c \in (0, 1)$. `SunShadowOverlayItem._rasterise` then filled `shade` ($c\alpha_s$) on top with `CompositionMode_SourceOver`. Porter-Duff `SourceOver` treats the two passes as uncorrelated rather than disjoint geometric partitions:
$$c\alpha_s + (1 - c\alpha_s)(1 - c)\alpha_f = \alpha - c(1 - c)\alpha^2 < \alpha$$
At $c = 0.5$ and $\alpha = 110/255$, $\alpha_{\text{out}} = 0.892\,\alpha \implies 86.5$ instead of `97`.

**Fix (`src/open_garden_planner/ui/canvas/shadow_feather.py`, `_cut_out_shade`):** Rasterise exact `shade` coverage `c` (and `tones` coverage `c * alpha_s` when weighted) over `shown`, zero `c == 255`, and scale fractional boundary pixels (`0 < c < 255`) by `(1 - c) / (1 - c * alpha_s)` so the subsequent `SourceOver` fill matches the exact geometric mix `c * alpha_s + (1 - c) * alpha_f` (falling back to `DestinationOut` only if allocation fails).

**Lesson:** Cutting an antialiased mask out of one `SourceOver` layer with `DestinationOut` and painting the complementary shape with `SourceOver` always leaves a $c(1-c)\alpha^2$ seam at $\alpha < 1$. Compensate the underlayer alpha by $(1 - c) / (1 - c\alpha_s)$ (or composite disjoint partitions in one layer) and pin across diagonal, circular, concave, subpixel, and weighted shapes (`tests/integration/test_shadow_feather_concave.py::test_no_lighter_hairline_along_any_outline`, `test_diagonal_and_curved_edge_transition_monotonically`).
