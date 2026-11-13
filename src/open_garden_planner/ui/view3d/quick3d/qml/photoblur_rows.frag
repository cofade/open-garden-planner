// Photo blur, passes 2, 4, 6 and 8 (PhotoBlur.qml): a premultiplied layer blurred along the
// rows, at the full sigma or a third of it (sigmaScale).

// ---- shared with photoblur_compose.frag (tests/unit/test_quick3d_qml.py keeps them equal) ----
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

void MAIN()
{
    float sigma = blurShare * sigmaScale * OUTPUT_SIZE.y;
    FRAGCOLOR = gaussianAlong(INPUT, INPUT_UV, vec2(1.0 / INPUT_SIZE.x, 0.0), sigma);
}
