VARYING vec4 vColor;
void MAIN()
{
    BASE_COLOR = vec4(vColor.rgb, 1.0);
    ROUGHNESS = 0.82;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = 0.25;
}
