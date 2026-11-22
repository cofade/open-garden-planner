// A window pane (#992). The pane's sky reflection (IBL) already needs the measured
// 0.70 roughness floor against Ultra SSR flicker (#883); the SCREEN-SPACE reflection
// reads ROUGHNESS, so it takes the lower 0.38 from the QML material while the view
// actually draws SSR. With SSR off (the default and the photo blur's chain), both are
// the same 0.70 and the pane is the reviewed #883 look exactly.
VARYING vec4 vColor;

void MAIN()
{
    BASE_COLOR = vec4(vColor.rgb * uTint * uAlbedo, 1.0);
    ROUGHNESS = uSsrRough;
    METALNESS = 0.0;
    SPECULAR_AMOUNT = uSpecular;
}
