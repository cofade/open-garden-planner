// Foliage wind: sway grows with the leaf's height in the crown (uv.x) and
// shifts phase per leaf (uv.y) and across the garden (world position).
VARYING vec4 vColor;
void MAIN()
{
    float w = UV0.x * UV0.x;
    float ph = UV0.y * 6.28318;
    vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    float gust = 0.6 + 0.4 * sin(uTime * 0.35 + wp.x * 0.002);
    VERTEX.x += sin(uTime * 1.9 + ph + wp.x * 0.011) * uWind * w * gust;
    VERTEX.z += cos(uTime * 1.4 + ph + wp.z * 0.009) * uWind * 0.6 * w * gust;
    vColor = COLOR;
    POSITION = MODELVIEWPROJECTION_MATRIX * vec4(VERTEX, 1.0);
}
