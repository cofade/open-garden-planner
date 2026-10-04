VARYING vec4 vColor;
void MAIN()
{
    BASE_COLOR = vec4(vColor.rgb, 1.0);
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
