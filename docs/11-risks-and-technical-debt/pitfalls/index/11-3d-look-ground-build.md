# 3D Look & Ground Pitfalls (PF-L3D)

| ID | Rule | Status | Where | Legacy |
|---|---|---|---|---|
| PF-L3D-01 | A gate that the repair itself makes true proves nothing, so measure before the repair, make the repair report what it changed, and never make a constraint hold by translating the result. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-01) | 11.4.12 |
| PF-L3D-02 | A plant in a raised bed casts from the bed's soil and is lifted only while its link holds and its stable geometric centre, not its `boundingRect()` centre, lies inside the bed's shape. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-02) | 11.4.13 |
| PF-L3D-03 | A bound that keeps the topmost N records drops what everything stands on, so a tile loses its smallest records by how much of the tile their paint covers, not by count. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-03) | 11.4.17 |
| PF-L3D-04 | A `Texture` element holds one texture for life, because destroying any texture it once held nulls its `textureData` and turns the tile white, so a re-baked tile is a new Model with a new texture. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-04) | 11.4.17 |
| PF-L3D-05 | Hand the engine every colour derived in linear light through `engine_srgb`, build each sky as a new `Texture` with its own data, and stop the wind clock whenever the pane is hidden. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-05) | 11.4.18 |
| PF-L3D-06 | A blended custom material must keep the frame's alpha (`sourceAlphaBlend: Zero`, `destinationAlphaBlend: One`): with the colour factors on alpha too, a translucent overlay brightens the view by `a(1 − a)` of the window's white instead of darkening it. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-06) |  |
| PF-L3D-07 | An unlit overlay passes through the mood's exposure, so a 3D shadow drape multiplies the frame and an overlay colour is divided by the exposure. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-07) |  |
| PF-L3D-08 | A hidden or blended Model drops out of the shadow map, so a part that must keep casting while it fades or is cut is an opaque screen door (a fragment discard) that collapses in the AO depth pass. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-08) |  |
| PF-L3D-09 | The 3D drape follows the shared Hours of Sun both ways, also when 3D opens with it on. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-09) |  |
| PF-L3D-10 | Render production plants and verify final seasonal bounds. | standing | [11](../11-3d-look-ground-build.md#pf-l3d-10) |  |
