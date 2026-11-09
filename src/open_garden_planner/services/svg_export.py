"""Vector SVG export through a recorded display list (#787).

``QSvgGenerator`` is not a faithful serializer of painter state. Measured on
Qt 6.12:

* a brush's own transform (a roof's mirrored tiles, a per-object pattern angle
  or scale) is dropped — the pattern is written without ``patternTransform``;
* a pixmap's source rectangle is ignored;
* painter clips are dropped in the default SVG Tiny 1.2 mode; in SVG 1.1 mode a
  clip that is the intersection of two clips is written as a one-unit staircase
  (``QPainter.clipPath()`` falls back to an integer region), and
  ``QSvgRenderer`` ignores ``clip-path`` altogether.

So the scene is not painted into the generator directly. It is painted into a
recording paint engine, which keeps every draw call with the painter state it
was made under — including the exact clip as a path. The recording is then
replayed into the generator with the three things it cannot express rewritten
as things it can:

* a clipped fill is written as the fill's outline intersected with the clip —
  plain geometry, no clip needed;
* a clipped stroke is written as the stroke's outline intersected with the clip;
* a brush transform is moved into the world transform, which the generator
  does write.

Only a clipped picture or a clipped piece of text keeps a real ``<clipPath>``
(written exactly, in SVG 1.1 mode). Every painter is covered because the
recorder sits below ``QPainter``: nothing in an item's ``paint`` has to know it
is being exported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QPaintDevice,
    QPaintEngine,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
    QTransform,
)
from PyQt6.QtSvg import QSvgGenerator

#: User units per inch of an exported SVG. A drawing is written at print
#: resolution, so a picture rasterised for the painter's scale (a plant sprite,
#: a texture tile) is as sharp in the SVG as in a 300-dpi PNG, and a
#: constant-pixel-size label or hairline is the size it has there.
SVG_UNITS_PER_INCH = 300

_FALLBACK_LOGICAL_DPI = 96.0
_EPSILON = 1e-6

#: Font families that are serif; every other proportional family falls back to
#: ``sans-serif`` and every fixed-pitch one to ``monospace``.
_SERIF_FAMILIES = frozenset({
    "times new roman", "times", "georgia", "cambria", "garamond", "palatino",
    "palatino linotype", "book antiqua", "constantia", "dejavu serif",
    "liberation serif", "noto serif", "baskerville", "didot",
})
#: A family is fixed-pitch when the font database says so, or — where the
#: family is not installed — when its name does.
_MONOSPACE_WORDS = ("mono", "courier", "consolas", "typewriter")


def logical_dpi() -> float:
    """The resolution Qt lays text out at when no paint device is given."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return _FALLBACK_LOGICAL_DPI
    dpi = float(screen.logicalDotsPerInchY())
    return dpi if dpi > 0 else _FALLBACK_LOGICAL_DPI


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Clip:
    """A clip in device coordinates; ``rect`` is set when it is a plain rectangle."""

    path: QPainterPath
    rect: QRectF | None

    def contains(self, bounds: QRectF) -> bool:
        if self.rect is not None:
            grown = self.rect.adjusted(-_EPSILON, -_EPSILON, _EPSILON, _EPSILON)
            return grown.contains(bounds)
        return bool(self.path.contains(bounds))


@dataclass(frozen=True)
class _State:
    transform: QTransform
    pen: QPen
    brush: QBrush
    brush_origin: QPointF
    opacity: float
    clip: _Clip | None


@dataclass(frozen=True)
class _ShapeOp:
    state: _State
    path: QPainterPath
    fillable: bool


@dataclass(frozen=True)
class _PixmapOp:
    state: _State
    target: QRectF
    pixmap: QPixmap


@dataclass(frozen=True)
class _TextOp:
    state: _State
    position: QPointF
    text: str
    font: QFont
    bounds: QRectF


def _rect_of(path: QPainterPath) -> QRectF | None:
    """*path* as a rectangle, or None when it is any other shape."""
    count = path.elementCount()
    if count not in (4, 5):
        return None
    points = [path.elementAt(index) for index in range(count)]
    if any(point.isCurveTo() for point in points):
        return None
    if count == 5 and (abs(points[0].x - points[4].x) > _EPSILON
                       or abs(points[0].y - points[4].y) > _EPSILON):
        return None
    corners = points[:4]
    for first, second in zip(corners, corners[1:] + corners[:1], strict=True):
        if abs(first.x - second.x) > _EPSILON and abs(first.y - second.y) > _EPSILON:
            return None
    bounds = path.boundingRect()
    return bounds if bounds.width() > 0 and bounds.height() > 0 else None


def _intersect(first: _Clip | None, second: _Clip) -> _Clip:
    """The intersection of two clips, exact whenever one is a rectangle around the other."""
    if first is None:
        return second
    if first.rect is not None and second.rect is not None:
        both = first.rect.intersected(second.rect)
        path = QPainterPath()
        path.addRect(both)
        return _Clip(path, both)
    if first.contains(second.path.boundingRect()):
        return second
    if second.contains(first.path.boundingRect()):
        return first
    return _Clip(first.path.intersected(second.path), None)


class _RecordingEngine(QPaintEngine):
    """Keeps every draw call together with the painter state it was made under."""

    # What ``QSvgGenerator``'s own engine declares: QPainter then prepares the
    # same calls for the recorder as it would for the generator.
    _FEATURES = (
        QPaintEngine.PaintEngineFeature.AllFeatures
        & ~QPaintEngine.PaintEngineFeature.PerspectiveTransform
        & ~QPaintEngine.PaintEngineFeature.ConicalGradientFill
        & ~QPaintEngine.PaintEngineFeature.PorterDuff
    )

    def __init__(self) -> None:
        super().__init__(self._FEATURES)
        self.ops: list[_ShapeOp | _PixmapOp | _TextOp] = []
        self._reset()

    def _reset(self) -> None:
        self._transform = QTransform()
        self._pen = QPen(Qt.PenStyle.NoPen)
        self._brush = QBrush(Qt.BrushStyle.NoBrush)
        self._brush_origin = QPointF()
        self._opacity = 1.0
        self._clips: list[_Clip] = []
        self._clip_enabled = False
        self._snapshot: _State | None = None

    # -- QPaintEngine ------------------------------------------------------

    def begin(self, _device: QPaintDevice | None) -> bool:
        self.ops = []
        self._reset()
        return True

    def end(self) -> bool:
        return True

    def type(self) -> QPaintEngine.Type:
        return QPaintEngine.Type.User

    def updateState(self, state: Any) -> None:
        dirty = QPaintEngine.DirtyFlag
        flags = state.state()
        self._snapshot = None
        if flags & dirty.DirtyTransform:
            self._transform = QTransform(state.transform())
        if flags & dirty.DirtyPen:
            self._pen = QPen(state.pen())
        if flags & dirty.DirtyBrush:
            self._brush = QBrush(state.brush())
        if flags & dirty.DirtyBrushOrigin:
            self._brush_origin = QPointF(state.brushOrigin())
        if flags & dirty.DirtyOpacity:
            self._opacity = float(state.opacity())
        if flags & (dirty.DirtyClipPath | dirty.DirtyClipRegion):
            self._update_clip(state, bool(flags & dirty.DirtyClipPath))
        if flags & dirty.DirtyClipEnabled:
            self._clip_enabled = bool(state.isClipEnabled())

    def _update_clip(self, state: Any, is_path: bool) -> None:
        operation = state.clipOperation()
        if operation == Qt.ClipOperation.NoClip:
            self._clips = []
            self._clip_enabled = False
            return
        if is_path:
            local = QPainterPath(state.clipPath())
        else:
            local = QPainterPath()
            local.addRegion(state.clipRegion())
        # The transform that came with THIS clip: on QPainter.restore() the
        # saved clips are replayed, each with the matrix it was set under.
        matrix = QTransform(state.transform())
        path = matrix.map(local)
        rect = _rect_of(path) if matrix.type().value <= QTransform.TransformationType.TxScale.value else None
        clip = _Clip(path, rect)
        if operation == Qt.ClipOperation.ReplaceClip:
            self._clips = [clip]
        else:
            self._clips.append(clip)
        self._clip_enabled = True

    def drawPath(self, path: QPainterPath) -> None:
        self.ops.append(_ShapeOp(self._state(), QPainterPath(path), True))

    def drawPolygon(self, points: Any, mode: QPaintEngine.PolygonDrawMode) -> None:
        polygon = QPolygonF([QPointF(point) for point in points])
        if polygon.isEmpty():
            return
        path = QPainterPath()
        path.addPolygon(polygon)
        if mode == QPaintEngine.PolygonDrawMode.PolylineMode:
            self.ops.append(_ShapeOp(self._state(), path, False))
            return
        path.closeSubpath()
        if mode == QPaintEngine.PolygonDrawMode.WindingMode:
            path.setFillRule(Qt.FillRule.WindingFill)
        self.ops.append(_ShapeOp(self._state(), path, True))

    def drawPixmap(self, target: QRectF, pixmap: QPixmap, source: QRectF) -> None:
        whole = QRectF(0, 0, pixmap.width(), pixmap.height())
        # QSvgGenerator ignores a source rectangle: hand it the cut-out itself.
        picture = QPixmap(pixmap) if source == whole else pixmap.copy(source.toAlignedRect())
        self.ops.append(_PixmapOp(self._state(), QRectF(target), picture))

    def drawImage(self, target: QRectF, image: QImage, source: QRectF, _flags: Any = None) -> None:
        self.drawPixmap(target, QPixmap.fromImage(image), source)

    def drawTextItem(self, position: QPointF, item: Any) -> None:
        text = item.text()
        if not text:
            return
        bounds = QRectF(position.x(), position.y() - item.ascent(),
                        item.width(), item.ascent() + item.descent())
        self.ops.append(_TextOp(self._state(), QPointF(position), text, QFont(item.font()), bounds))

    # -- state -------------------------------------------------------------

    def _state(self) -> _State:
        if self._snapshot is None:
            clip: _Clip | None = None
            if self._clip_enabled:
                for one in self._clips:
                    clip = _intersect(clip, one)
            self._snapshot = _State(
                QTransform(self._transform), QPen(self._pen), QBrush(self._brush),
                QPointF(self._brush_origin), self._opacity, clip,
            )
        return self._snapshot


class _RecordingDevice(QPaintDevice):
    """A paint device of *width* x *height* units that records what is painted on it."""

    def __init__(self, width: float, height: float, units_per_inch: float) -> None:
        super().__init__()
        self._width = width
        self._height = height
        self._units_per_inch = units_per_inch
        self._dpi = round(logical_dpi())
        self.engine = _RecordingEngine()

    def paintEngine(self) -> QPaintEngine:
        return self.engine

    def metric(self, metric: QPaintDevice.PaintDeviceMetric) -> int:
        kind = QPaintDevice.PaintDeviceMetric
        if metric == kind.PdmWidth:
            return max(1, round(self._width))
        if metric == kind.PdmHeight:
            return max(1, round(self._height))
        if metric == kind.PdmWidthMM:
            return max(1, round(self._width / self._units_per_inch * 25.4))
        if metric == kind.PdmHeightMM:
            return max(1, round(self._height / self._units_per_inch * 25.4))
        # Logical resolution as a QImage has it: text is laid out for it.
        if metric in (kind.PdmDpiX, kind.PdmDpiY, kind.PdmPhysicalDpiX, kind.PdmPhysicalDpiY):
            return self._dpi
        if metric == kind.PdmDepth:
            return 32
        if metric == kind.PdmNumColors:
            return 2**24
        if metric == kind.PdmDevicePixelRatio:
            return 1
        if metric == kind.PdmDevicePixelRatioScaled:
            return int(QPaintDevice.devicePixelRatioFScale())
        return super().metric(metric)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def _has_own_frame(brush: QBrush, origin: QPointF) -> bool:
    """True when *brush* paints in a frame of its own that the generator drops."""
    if brush.style() in (Qt.BrushStyle.NoBrush, Qt.BrushStyle.SolidPattern):
        return False
    return not brush.transform().isIdentity() or not origin.isNull()


def _replay_fill(painter: QPainter, state: _State, path: QPainterPath) -> None:
    brush, clip = state.brush, state.clip
    clipped = clip is not None and not clip.contains(state.transform.mapRect(path.boundingRect()))
    world = state.transform
    if _has_own_frame(brush, state.brush_origin):
        world = brush.transform() * QTransform.fromTranslate(
            state.brush_origin.x(), state.brush_origin.y()) * state.transform
        brush = QBrush(brush)
        brush.setTransform(QTransform())
    elif not clipped:
        painter.setWorldTransform(world)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(brush)
        painter.drawPath(path)
        return
    outline = state.transform.map(path)
    if clipped and clip is not None:
        outline = outline.intersected(clip.path)
    if outline.isEmpty():
        return
    inverse, invertible = world.inverted()
    if not invertible:
        return
    painter.setWorldTransform(world)
    painter.setBrushOrigin(QPointF())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(brush)
    painter.drawPath(inverse.map(outline))


def _replay_stroke(painter: QPainter, state: _State, path: QPainterPath) -> None:
    pen, clip = state.pen, state.clip
    centre_line = state.transform.mapRect(path.controlPointRect())
    if clip is None or clip.contains(centre_line):
        painter.setWorldTransform(state.transform)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        return
    # A clipped stroke: its outline, cut to the clip, as a fill.
    if pen.isCosmetic():
        device_pen = QPen(pen)
        device_pen.setCosmetic(False)
        device_pen.setWidthF(max(1.0, pen.widthF()))
        outline = QPainterPathStroker(device_pen).createStroke(state.transform.map(path))
    else:
        outline = state.transform.map(QPainterPathStroker(pen).createStroke(path))
    outline.setFillRule(Qt.FillRule.WindingFill)
    outline = outline.intersected(clip.path)
    if outline.isEmpty():
        return
    painter.setWorldTransform(QTransform())
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(pen.brush())
    painter.drawPath(outline)


def _explicit_font(font: QFont) -> QFont:
    """*font* with every property that an SVG states set by hand.

    A font handed out by a text layout (a ``QGraphicsTextItem``'s) can carry no
    record of which of its properties were set. ``QPainter.setFont`` resolves
    such a font against the device's default font and every property is lost:
    measured, a 28 pt Arial note was written as the 9 pt application font.
    Underline and strike-out are left off: they arrive as shapes of their own.
    """
    explicit = QFont()
    explicit.setFamilies(font.families())
    if font.pixelSize() > 0:
        explicit.setPixelSize(font.pixelSize())
    elif font.pointSizeF() > 0:
        explicit.setPointSizeF(font.pointSizeF())
    explicit.setWeight(font.weight())
    explicit.setStyle(font.style())
    if font.letterSpacing() != 0:
        explicit.setLetterSpacing(font.letterSpacingType(), font.letterSpacing())
    return explicit


def _with_clip(painter: QPainter, state: _State, bounds: QRectF) -> bool:
    """Set a real clip for something that cannot be cut to shape; True when one was set."""
    clip = state.clip
    if clip is None or clip.contains(state.transform.mapRect(bounds)):
        return False
    painter.setWorldTransform(QTransform())
    painter.setClipPath(clip.path)
    return True


def _replay(ops: list[_ShapeOp | _PixmapOp | _TextOp], painter: QPainter) -> None:
    for op in ops:
        state = op.state
        painter.setOpacity(state.opacity)
        if isinstance(op, _ShapeOp):
            fills = op.fillable and state.brush.style() != Qt.BrushStyle.NoBrush
            strokes = state.pen.style() != Qt.PenStyle.NoPen
            plain = (
                not _has_own_frame(state.brush, state.brush_origin)
                and (state.clip is None
                     or state.clip.contains(state.transform.mapRect(op.path.boundingRect())))
            )
            if plain and op.fillable:
                # Nothing the generator cannot express: one draw, as painted.
                painter.setWorldTransform(state.transform)
                painter.setPen(state.pen)
                painter.setBrush(state.brush)
                painter.drawPath(op.path)
                continue
            if fills:
                _replay_fill(painter, state, op.path)
            if strokes:
                _replay_stroke(painter, state, op.path)
        elif isinstance(op, _PixmapOp):
            clipped = _with_clip(painter, state, op.target)
            painter.setWorldTransform(state.transform)
            painter.drawPixmap(op.target, op.pixmap,
                               QRectF(0, 0, op.pixmap.width(), op.pixmap.height()))
            if clipped:
                painter.setClipping(False)
        else:
            clipped = _with_clip(painter, state, op.bounds)
            painter.setWorldTransform(state.transform)
            painter.setPen(state.pen)
            painter.setFont(_explicit_font(op.font))
            painter.drawText(op.position, op.text)
            if clipped:
                painter.setClipping(False)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------

def _generic_family(family: str) -> str:
    name = family.lower()
    if name in _SERIF_FAMILIES or ("serif" in name and "sans" not in name):
        return "serif"
    if any(word in name for word in _MONOSPACE_WORDS) or QFontDatabase.isFixedPitch(family):
        return "monospace"
    return "sans-serif"


def _finish_svg(file_path: Path, width_mm: float, height_mm: float) -> None:
    """State the physical size exactly and give every font a generic fallback."""
    text = file_path.read_text(encoding="utf-8")

    def size(match: re.Match[str]) -> str:
        tag = match.group(0)
        tag = re.sub(r'\bwidth="[^"]*"', f'width="{width_mm:.4g}mm"', tag, count=1)
        return re.sub(r'\bheight="[^"]*"', f'height="{height_mm:.4g}mm"', tag, count=1)

    text = re.sub(r"<svg\b[^>]*>", size, text, count=1)

    fallbacks: dict[str, str] = {}

    def family(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in fallbacks:
            fallbacks[name] = _generic_family(name)
        return f"font-family=\"'{name}', {fallbacks[name]}\""

    text = re.sub(r'font-family="([^",\']+)"', family, text)
    file_path.write_text(text, encoding="utf-8")


def record_scene(
    scene: Any,
    source_rect: QRectF,
    width: float,
    height: float,
    units_per_inch: float = SVG_UNITS_PER_INCH,
) -> list[_ShapeOp | _PixmapOp | _TextOp]:
    """Paint *source_rect* of *scene*, Y-up, onto a recorder of *width* x *height* units."""
    device = _RecordingDevice(width, height, units_per_inch)
    painter = QPainter()
    if not painter.begin(device):
        raise ValueError("Failed to start the SVG recording painter")
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(0, height)
        painter.scale(1.0, -1.0)
        scene.render(painter, QRectF(0, 0, width, height), source_rect)
    finally:
        painter.end()
    return device.engine.ops


def write_svg(
    ops: list[_ShapeOp | _PixmapOp | _TextOp],
    file_path: Path,
    width: float,
    height: float,
    *,
    units_per_inch: float = SVG_UNITS_PER_INCH,
    title: str = "",
    description: str = "",
) -> None:
    """Replay a recording into an SVG 1.1 file of *width* x *height* user units."""
    generator = QSvgGenerator(QSvgGenerator.SvgVersion.Svg11)
    generator.setFileName(str(file_path))
    # The resolution text is laid out at, so a font's size in user units is the
    # size its item measured itself with. The physical size is stated below.
    generator.setResolution(round(logical_dpi()))
    generator.setSize(QSize(max(1, round(width)), max(1, round(height))))
    generator.setViewBox(QRectF(0, 0, width, height))
    generator.setTitle(title)
    generator.setDescription(description)

    painter = QPainter()
    if not painter.begin(generator):
        raise ValueError(f"Failed to write SVG to {file_path}")
    try:
        _replay(ops, painter)
    finally:
        painter.end()
    _finish_svg(file_path, width / units_per_inch * 25.4, height / units_per_inch * 25.4)
