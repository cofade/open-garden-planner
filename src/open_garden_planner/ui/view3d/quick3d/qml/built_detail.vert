// A built part's detail picture (#801): where on the picture each vertex lies, in
// pictures (1.0 = one 256-px picture, uDetailTile cm wide).
//
// uDetailMode 1 (a roof's tiles): the mesh's own uvs, in cm (builders/roofs.py: u along
// the ridge from its middle, v away from the ridge - the 2D brush's frame, so a roof seen
// from above is the canvas's picture).
// uDetailMode 2 (a wall): the face's own plane in the item's frame (MODEL space, so the
// picture stays on the item when it moves or turns): a face that stands (|normal.y| <
// 0.7) runs u along it, to the right seen from outside, and v DOWN from the ground's
// level, so a wall's courses stay level round its corners; a face that lies takes the
// plan's x and z (north up, as the canvas lays a picture).
//
// The vertex colour goes on through COLOR: read as VAR_COLOR without a vertex stage of
// its own a custom material's colour comes out darker and more saturated than the
// principled material's (#687, built_snow.vert). VERTEX is not touched: the depth and
// shadow passes see the part as it is.
VARYING vec4 vColor;
VARYING vec2 vDetailUV;

void MAIN()
{
    vColor = COLOR;
    vec2 cm;
    if (uDetailMode < 1.5) {
        cm = UV0;
    } else if (abs(NORMAL.y) < 0.7) {
        vec2 along = normalize(vec2(NORMAL.z, -NORMAL.x));
        cm = vec2(dot(VERTEX.xz, along), -VERTEX.y);
    } else {
        cm = VERTEX.xz;
    }
    vDetailUV = cm / uDetailTile;
}
