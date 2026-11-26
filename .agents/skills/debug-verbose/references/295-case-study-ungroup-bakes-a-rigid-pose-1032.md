## Case study: the member pose after Ungroup (#1032, 2026-11-26)

Ungroup required rotating a group back to zero because a visually correct
Qt detachment left the group turn in the child's base matrix. The standalone
shape serializers write their own angles, translation or control points.

A Qt probe applied a 32-degree group turn to members with a 23-degree local
angle. The detached ordinary member's world basis read 55 degrees while its
Qt rotation property still read 23. The detached reflected text's world basis
read 9 degrees, which needs a stored local angle of minus 9 degrees.

Capture the scene transform before detaching. Re-express it in canonical
member geometry. Apply the original local pose after reparenting for Undo.
The round-trip test in `tests/integration/test_group_rotation.py` covers text
with zero net angle, arcs, Beziers, nested groups, and the ordinary shapes.
