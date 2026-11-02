// The garden's life (Phase 17 L5.2, L5.4): unlit. Leaves and butterflies are lit by
// uLight (the key light and the sky's, linear); fireflies and the bulbs of the garden
// lights GLOW - their colour is light of their own, bright enough for the bloom.
VARYING vec4 vColor;
VARYING vec2 vUV;
VARYING float vKind;
VARYING float vGlow;

void MAIN()
{
    int kind = int(vKind + 0.5);
    vec2 p = vUV - vec2(0.5);
    if (kind == 0) {          // a leaf: an ellipse with a midrib
        if (p.x * p.x / 0.25 + p.y * p.y / 0.11 > 1.0)
            discard;
        float rib = 1.0 - 0.25 * (1.0 - smoothstep(0.0, 0.05, abs(p.y)));
        FRAGCOLOR = vec4(vColor.rgb * uLight * rib, vColor.a);
    } else if (kind == 1) {   // a wing: rounded, darker at its root
        vec2 w = vec2(p.x * 1.6, vUV.y - 0.45);
        if (dot(w, w) > 0.36)
            discard;
        float root = mix(0.55, 1.0, smoothstep(0.0, 0.5, vUV.y));
        FRAGCOLOR = vec4(vColor.rgb * uLight * root, vColor.a);
    } else {                  // a firefly or a bulb: a soft glow
        float r = length(p) * 2.0;
        float core = smoothstep(1.0, 0.0, r);
        vec3 light = kind == 2 ? vec3(1.3, 1.9, 0.35) * 2.2 : vec3(2.6, 1.7, 0.75) * 1.6;
        float alpha = core * core * vGlow;
        if (alpha <= 0.002)
            discard;
        FRAGCOLOR = vec4(light, alpha);
    }
}
