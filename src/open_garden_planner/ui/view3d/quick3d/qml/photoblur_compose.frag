// Photo blur, pass 9 (PhotoBlur.qml): the four blurred layers' columns, composed over the
// sharp scene. INPUT is the far layer's full blur after its rows; the samplers the others.

// ---- shared with photoblur_layer.frag (tests/unit/test_quick3d_qml.py keeps them equal) ----
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

// ---- shared with photoblur_rows.frag (tests/unit/test_quick3d_qml.py keeps them equal) ----
// A normalised Gaussian of sigma pixels along one axis, truncated at three sigma. One bilinear
// tap reads two neighbouring texels at the point between them that their two weights put it:
// exact for a linear blur, and no texel is skipped, so a thin slat cannot alias into copies.
// The reach is capped (an 8192 px picture at the strongest blur), never the spacing.
vec4 gaussianAlong(sampler2D source, vec2 uv, vec2 texel, float sigma)
{
    vec4 sum = texture(source, uv);
    if (sigma < 0.05)
        return sum;
    int reach = min(int(ceil(3.0 * sigma)), 192);
    float falloff = -0.5 / (sigma * sigma);
    float total = 1.0;
    for (int i = 1; i <= reach; i += 2) {
        float first = exp(falloff * float(i * i));
        float second = i + 1 <= reach ? exp(falloff * float((i + 1) * (i + 1))) : 0.0;
        float pair = first + second;
        vec2 offset = texel * (float(i) + second / pair);
        sum += pair * (texture(source, uv + offset) + texture(source, uv - offset));
        total += 2.0 * pair;
    }
    return sum / total;
}
// ---- end of shared ----

const float SMALL = 0.3333333;      // the small blur's sigma, of the full one
const float EMPTY = 1.0e-4;         // a layer's weight below which it holds no colour here

// A pixel out of focus by amount (0..1): up to a third of the way the small blur takes over
// from the sharp pixel, beyond it the full blur from the small one - a blur that grows with the
// amount, where lerping the sharp pixel with the full blur drew sharp leaves inside a haze
vec3 defocus(vec3 sharp, vec4 small, vec4 full, float amount)
{
    vec3 lesser = small.a > EMPTY ? small.rgb / small.a : sharp;
    if (amount <= SMALL)
        return mix(sharp, lesser, amount / SMALL);
    vec3 greater = full.a > EMPTY ? full.rgb / full.a : lesser;
    return mix(lesser, greater, (amount - SMALL) / (1.0 - SMALL));
}

void MAIN()
{
    float sigma = blurShare * OUTPUT_SIZE.y;
    vec2 texel = vec2(0.0, 1.0 / INPUT_SIZE.y);
    vec4 farFull = gaussianAlong(INPUT, INPUT_UV, texel, sigma);
    vec4 farSmall = gaussianAlong(farSmallSampler, INPUT_UV, texel, sigma * SMALL);
    vec4 nearFull = gaussianAlong(nearFullSampler, INPUT_UV, texel, sigma);
    vec4 nearSmall = gaussianAlong(nearSmallSampler, INPUT_UV, texel, sigma * SMALL);
    vec4 scene = texture(sceneSampler, INPUT_UV);
    float here = outOfFocus(INPUT_UV);
    vec3 colour = scene.rgb;
    if (here < 0.0) {
        colour = defocus(scene.rgb, nearSmall, nearFull, -here);
    } else {
        // behind the band: averages of what lies behind it nearby, never of a sharp or near
        // pixel (Qt averaged an in-focus edge's colour into the blurred wall: a light fringe)
        if (here > 0.0)
            colour = defocus(scene.rgb, farSmall, farFull, here);
        // what lies in front spreads past its own edge over what lies behind it: fully covered
        // at the edge, a third a sigma out (a blurred bar is soft against a sharp panel)
        if (nearSmall.a > EMPTY)
            colour = mix(colour, nearSmall.rgb / nearSmall.a, clamp(2.0 * nearSmall.a, 0.0, 1.0));
    }
    if (nearFull.a > EMPTY)
        colour = mix(colour, nearFull.rgb / nearFull.a, clamp(2.0 * nearFull.a, 0.0, 1.0));
    FRAGCOLOR = vec4(colour, scene.a);
}
