// Grass wind: blade tips (uv.x = 1) bend most, bases stay put.
VARYING vec4 vColor;
void MAIN()
{
    float w = UV0.x * UV0.x;
    float ph = UV0.y * 6.28318;
    vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
    float gust = 0.55 + 0.45 * sin(uTime * 0.5 + wp.x * 0.003 + wp.z * 0.002);
    VERTEX.x += sin(uTime * 2.3 + ph + wp.x * 0.02) * uWind * w * gust;
    VERTEX.z += cos(uTime * 1.7 + ph + wp.z * 0.02) * uWind * 0.5 * w * gust;
    vColor = COLOR;
    POSITION = MODELVIEWPROJECTION_MATRIX * vec4(VERTEX, 1.0);
}
