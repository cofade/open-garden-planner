// The analysis overlays (Phase 17 L2, #386): unlit - the vertex colour as it is,
// alpha included (the drape blends; the lines are opaque). An Unshaded material still
// goes through the view's exposure and tone curve (ogp-3d-renderer 15).
VARYING vec4 vColor;
void MAIN()
{
    FRAGCOLOR = vColor;
}
