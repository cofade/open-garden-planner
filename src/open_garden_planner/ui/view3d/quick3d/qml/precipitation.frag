// Rain and snow (Phase 17 L5.2): unlit, in the light the look gives an unlit particle
// (uLight - the key light and the sky's, linear: rain is dark at night). An Unshaded
// material still goes through the view's exposure and tone curve, as every surface does.
VARYING vec4 vColor;
VARYING vec2 vUV;
VARYING float vFade;

void MAIN()
{
    float alpha;
    vec3 albedo;
    if (uKind > 1.5) {   // a soft round flake
        float r = length(vUV - vec2(0.5)) * 2.0;
        alpha = smoothstep(1.0, 0.3, r) * 0.9;
        albedo = vec3(0.92, 0.94, 0.97);
    } else {             // a thin streak, faint at both ends
        float across = 1.0 - abs(vUV.x - 0.5) * 2.0;
        alpha = across * sin(vUV.y * 3.14159) * 0.27;   // as bright as 0.38 at 0.9 px
        albedo = vec3(0.62, 0.68, 0.76);
    }
    FRAGCOLOR = vec4(albedo * vColor.rgb * uLight, alpha * vFade);
}
