// Photo blur, passes 1, 3, 5 and 7 (PhotoBlur.qml): one depth layer of the scene's linear
// colour, premultiplied by its weight. layerSign +1: what lies behind the band; -1: what lies
// in front of it. layerStrong 0: weighted by the amount out of focus (the small blur);
// 1: by its strong part, from a third to all of it (the full blur: what lies just outside
// the band takes no part in it).

// ---- shared with photoblur_compose.frag (tests/unit/test_quick3d_qml.py keeps them equal) ----
// The depth along the view's axis, cm: Qt's depth texture holds the GL-style depth mapped to
// 0..1 on every backend (Qt's own depth-of-field shader reads it the same way)
float viewDepth(vec2 uv)
{
    float near = CAMERA_PROPERTIES.x;
    float far = CAMERA_PROPERTIES.y;
    float ndc = 2.0 * texture(DEPTH_TEXTURE, uv).r - 1.0;
    return 2.0 * near * far / (far + near - ndc * (far - near));
}

// Signed: 0 inside the sharp band, growing to 1 one band beyond its edge; negative in front
float outOfFocus(vec2 uv)
{
    float offset = viewDepth(uv) - focusDistance;
    float amount = clamp((abs(offset) - 0.5 * focusRange) / max(focusRange, 1.0), 0.0, 1.0);
    return offset < 0.0 ? -amount : amount;
}
// ---- end of shared ----

float layerAmount(vec2 uv)
{
    return max(outOfFocus(uv) * layerSign, 0.0);
}

// A pixel on the layer's silhouette is multisampled: its colour is partly the thing beside it,
// while the depth pass (one sample) puts all of it in this layer. At full weight a dark blurred
// bar took a light rim from the sharp panel behind it (its edge pixel was 26 times brighter in
// linear light than the bar), and a far roof would take an in-focus leaf's colour. So it counts
// for a fifth: its own colour still leads where nothing else of the layer is near.
const float SILHOUETTE_WEIGHT = 0.2;

void MAIN()
{
    float amount = layerAmount(INPUT_UV);
    float weight = layerStrong > 0.5 ? smoothstep(0.3333333, 1.0, amount) : amount;
    if (weight > 0.0) {
        vec2 pixel = vec2(1.0) / OUTPUT_SIZE;
        float inside = min(min(layerAmount(INPUT_UV + vec2(pixel.x, 0.0)),
                               layerAmount(INPUT_UV - vec2(pixel.x, 0.0))),
                           min(layerAmount(INPUT_UV + vec2(0.0, pixel.y)),
                               layerAmount(INPUT_UV - vec2(0.0, pixel.y))));
        if (inside <= 0.0)
            weight *= SILHOUETTE_WEIGHT;
    }
    vec3 colour = texture(sceneSampler, INPUT_UV).rgb;
    FRAGCOLOR = vec4(colour * weight, weight);
}
