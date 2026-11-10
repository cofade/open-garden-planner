## 4. Material value ranges (PBR, roughness 0–1)

Since #803 every built surface's numbers live in `core/scene3d/materials.SURFACES` (one per
palette entry or tinted part; reference 19 has the table and why); this table is their range.
Qt switches a principled material's specular OFF at an amount of 0.01 or less and barely scales
a grazing highlight above it (PF-E3D-32): "specular ≈ 0.05" is not a dull surface, 0 is.

| Material | Roughness | Notes |
|---|---|---|
| Lawn blades, leaves | 0.75–0.85 | specular ≈ 0.25; vertex colours from palettes |
| Bark, soil, mulch | 0.85–0.95 | |
| Plaster walls | 0.85–0.95 | warm off-white, never `#ffffff`; a house's walls are `plaster` (0.90 / 0.15) and show the canvas's concrete picture as render (#801) |
| Masonry, stone, concrete | 0.90 | specular 0.15; a garden wall is `masonry`: the canvas's stone courses (#801) |
| Rubber, canvas | 0.95 | specular **0** (off): at any amount above 0.01 a black mat facing a low sun read tan (#803) |
| Plastic | 1.0 | specular 0.20: a blue pad facing a 15° sun 8.0° off its 2D blue (9.3° at 0.95, 31.7° at 0.55) |
| Steel, iron, enamel | 0.45 / 0.60 / 0.60 | specular 0.50 / 0.35 / 0.15 |
| Roof tiles | 0.70–0.85 | terracotta `#b4553d` range (matches the 2D roof texture); their own material (`roofMat`, roughness 0.80, specular 0.15: `gable_house_parts` emits the roof as kind `"roof"`). Specular is NOT what makes a sun-facing roof read coral at noon: PrincipledMaterial scales its image-light diffuse by (1 − `specularAmount`), so 0.35 → 0.15 lifted the sky diffuse 1.31× and cancelled the lost highlight (noon_low roof sRGB (248, 135, 92) → (248, 135, 90)); the coral is the per-channel filmic shoulder (R compressed, G linear: hue 12.1° → 16.7°, inside the 10° line). Since #801 the tile faces carry the 2D brush's uvs and show the canvas's own roof picture (contrast 0.6: at full contrast 15 % of the noon roof clipped red; mean −0.6 % luma, 0.0° hue against the flat roof) |
| Wood (deck, fence, beds) | 0.60–0.80 | `wood` 0.75 / 0.25; a shed's walls `wood_cladding` 0.80 / 0.20 with the canvas's boards (#801) |
| Terracotta pots | 0.80–0.90 | |
| Water | 0.02 | 2D water colour `#4d92c5` (linear); a tight sun glint (0.05 still clipped ~23 % of the visible pond at morning, 0.3 blew it over the whole pond); a small custom shader (`qml/water.frag`) keeps its hue in every mood and adds a Fresnel × 0.15 sky reflection — PrincipledMaterial's grazing sky reflection turned the pond lavender at golden hour and ignores `specularAmount`/`fresnelScale`/`fresnelPower`. Since #803 the glint is `water.frag`'s own GGX, soft-capped at 0.6 / exposure: at the mirror angle of a morning sun 0 % clipped (was 2.7-6.1 %), peak luma 213-237 |
| Glass | 0.02–0.06 | opacity 0.2–0.35, blended, no depth write, casts no shadow (an OPAQUE window pane in a facade is `glass_pane`, 0.40 / 0.40: it mirrors the sky) |
| Aluminium frames | 0.30–0.50 | |

