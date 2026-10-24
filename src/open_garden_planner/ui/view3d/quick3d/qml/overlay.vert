// The analysis overlays (Phase 17 L2, #386): the drape of the 2D sun analysis and the
// sun path / compass / probe pin. The mesh is in the scene's own frame and its colour is
// the vertex colour, LINEAR, alpha included (core/scene3d/drape.py, sun_path.py) - this
// passes it on, unchanged; nothing here moves a vertex.
VARYING vec4 vColor;
void MAIN()
{
    vColor = COLOR;
    POSITION = MODELVIEWPROJECTION_MATRIX * vec4(VERTEX, 1.0);
}
