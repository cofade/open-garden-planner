// The analysis overlays (Phase 17 L2, #386): unlit vertex colour. An Unshaded
// material still goes through the view's exposure and tone curve (ogp-3d-renderer
// 16), so the colour is divided by the exposure here: the arcs and the hours-of-sun
// ramp keep their colour from noon to night (3D review of #386: at night's exposure
// 2.4 they washed out to near white). uExposure is 1 for the shade layer, whose
// colour is a MULTIPLIER of what lies under it (Garden.qml), not a light.
VARYING vec4 vColor;
void MAIN()
{
    FRAGCOLOR = vec4(vColor.rgb / uExposure, vColor.a);
}
