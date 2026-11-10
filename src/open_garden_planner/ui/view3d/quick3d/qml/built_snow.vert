// The vertex stage of the snow on built tops (#687): it only hands the vertex colour on as
// it is. Read as VAR_COLOR without a vertex stage of its own, a CustomMaterial's colour came
// out darker and more saturated than the PrincipledMaterial's of the same vertices (a roof
// pixel 136, 46, 39 against 187, 99, 71, measured); through COLOR, as the foliage shaders
// read it, the snowless snow look is the principled look to the level.
VARYING vec4 vColor;

void MAIN()
{
    vColor = COLOR;
}
