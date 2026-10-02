"""Reserved z-values for in-progress tool previews (docs §8.25.6).

A preview primitive is a bare ``QGraphics*Item`` created during a gesture. Qt
gives it the default ``z = 0``, while every real document item gets a *derived*
z strictly inside ``(0, 100)`` from ``CanvasScene._refresh_layer_z``. So an
ungoverned preview always loses to a bed or shape it overlaps and is invisible
for the whole drag (issue #377).

Assign one of these values to every preview item at creation:

* ``PREVIEW_Z_FILL`` — translucent fill body (circle/rect/ellipse/polygon).
* ``PREVIEW_Z_LINE`` — rubber-band line or path outline.
* ``PREVIEW_Z_LABEL`` — text readout item.
* ``PREVIEW_Z_HANDLE`` — vertex markers / bezier control handles.

Keep relative order fill < line < label < handle so a multi-part preview stays
readable. The whole band MUST stay below ``minimap_widget._OVERLAY_Z_MIN``
(10_000): the minimap hides any item at or above that value, so a higher preview
z would pop in and out of the thumbnail during a drag (§8.9.5 / §8.25.6).
"""

PREVIEW_Z_FILL = 999
PREVIEW_Z_LINE = 1000
PREVIEW_Z_LABEL = 1001
PREVIEW_Z_HANDLE = 1002

#: The upper bound of the preview band. Must stay below the minimap cutoff.
MAX_PREVIEW_Z = 9999
