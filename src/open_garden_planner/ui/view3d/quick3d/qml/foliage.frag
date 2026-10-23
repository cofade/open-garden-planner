// Leaves and blades (ported from the L0 spike; shared by foliage.vert and
// grass.vert). albedo = vertex colour x the part's tint, both linear. The alpha is
// uOpacity: 1, unless the part fades as an occluder of the selection (L2.4, X-ray) -
// and only then does the material blend (Garden.qml), so 1 is opaque either way.
VARYING vec4 vColor;
void MAIN()
{
    BASE_COLOR = vec4(vColor.rgb * uTint, uOpacity);
    ROUGHNESS = 0.82;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = 0.25;
}

// Thin leaves and blades: light from BEHIND shines through (wrap + translucency).
// Front: Lambert. Back: 35 % of the light reaching the other face, still gated by
// the shadow map, so only leaves the sun actually reaches can glow.
void DIRECTIONAL_LIGHT()
{
    DIFFUSE += BASE_COLOR.rgb * LIGHT_COLOR * SHADOW_CONTRIB
             * (max(dot(NORMAL, TO_LIGHT_DIR), 0.0) + 0.35 * max(dot(-NORMAL, TO_LIGHT_DIR), 0.0));
}
