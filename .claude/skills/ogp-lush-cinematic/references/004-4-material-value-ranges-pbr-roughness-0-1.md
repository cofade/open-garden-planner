## 4. Material value ranges (PBR, roughness 0–1)

| Material | Roughness | Notes |
|---|---|---|
| Lawn blades, leaves | 0.75–0.85 | specular ≈ 0.25; vertex colours from palettes |
| Bark, soil, mulch | 0.85–0.95 | |
| Plaster walls | 0.85–0.95 | warm off-white, never `#ffffff` |
| Roof tiles | 0.70–0.85 | terracotta `#b4553d` range (matches the 2D roof texture); their own material (`roofMat`, roughness 0.80, specular 0.15: `gable_house_parts` emits the roof as kind `"roof"`). Specular is NOT what makes a sun-facing roof read coral at noon: PrincipledMaterial scales its image-light diffuse by (1 − `specularAmount`), so 0.35 → 0.15 lifted the sky diffuse 1.31× and cancelled the lost highlight (noon_low roof sRGB (248, 135, 92) → (248, 135, 90)); the coral is the per-channel filmic shoulder (R compressed, G linear: hue 12.1° → 16.7°, inside the 10° line) |
| Wood (deck, fence, beds) | 0.60–0.80 | |
| Terracotta pots | 0.80–0.90 | |
| Water | 0.02 | 2D water colour `#4d92c5` (linear); a tight sun glint (0.05 still clipped ~23 % of the visible pond at morning, 0.3 blew it over the whole pond); a small custom shader (`qml/water.frag`) keeps its hue in every mood and adds a Fresnel × 0.15 sky reflection — PrincipledMaterial's grazing sky reflection turned the pond lavender at golden hour and ignores `specularAmount`/`fresnelScale`/`fresnelPower` |
| Glass | 0.02–0.06 | opacity 0.2–0.35, blended, no depth write, casts no shadow |
| Aluminium frames | 0.30–0.50 | |

