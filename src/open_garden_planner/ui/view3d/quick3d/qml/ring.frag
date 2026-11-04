// The selection ring (L1.8): one flat colour, unlit - the canvas's selection blue,
// handed over in linear light (uColor).
void MAIN()
{
    FRAGCOLOR = vec4(uColor, 1.0);
}
