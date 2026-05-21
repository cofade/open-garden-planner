"""Bounded-depth quadtree for accelerated snap candidate lookup.

The implementation is intentionally small: the snap engine only needs a
"find items whose bounding rect intersects this query rect" primitive.
A quadtree fits well because scene items tend to be spatially
clustered and the depth bound keeps the worst case tame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QRectF
from PyQt6.QtWidgets import QGraphicsItem

MAX_DEPTH = 6
NODE_CAPACITY = 8


@dataclass
class _Node:
    bounds: QRectF
    depth: int
    items: list[tuple[QRectF, QGraphicsItem]] = field(default_factory=list)
    children: list[_Node] | None = None

    def is_leaf(self) -> bool:
        return self.children is None

    def subdivide(self) -> None:
        x = self.bounds.x()
        y = self.bounds.y()
        w = self.bounds.width() / 2
        h = self.bounds.height() / 2
        d = self.depth + 1
        self.children = [
            _Node(QRectF(x, y, w, h), d),
            _Node(QRectF(x + w, y, w, h), d),
            _Node(QRectF(x, y + h, w, h), d),
            _Node(QRectF(x + w, y + h, w, h), d),
        ]


class QuadTree:
    """Spatial index over scene-coordinate bounding rectangles."""

    def __init__(self, bounds: QRectF) -> None:
        self._root = _Node(bounds=QRectF(bounds), depth=0)

    @property
    def bounds(self) -> QRectF:
        return QRectF(self._root.bounds)

    def insert(self, rect: QRectF, item: QGraphicsItem) -> None:
        """Insert an item indexed by its scene bounding rect."""
        self._insert(self._root, rect, item)

    def query(self, region: QRectF) -> list[QGraphicsItem]:
        """Return items whose bounding rect intersects ``region``."""
        out: list[QGraphicsItem] = []
        seen: set[int] = set()
        self._query(self._root, region, out, seen)
        return out

    @staticmethod
    def _intersects(a: QRectF, b: QRectF) -> bool:
        return not (
            a.right() < b.left()
            or a.left() > b.right()
            or a.bottom() < b.top()
            or a.top() > b.bottom()
        )

    def _insert(self, node: _Node, rect: QRectF, item: QGraphicsItem) -> None:
        if not self._intersects(node.bounds, rect):
            # Item lies entirely outside the tree's bounds; still store it
            # at the root so queries can find it (the bounds were just a
            # hint, not an exclusion).
            if node is self._root:
                node.items.append((QRectF(rect), item))
            return

        if node.is_leaf():
            node.items.append((QRectF(rect), item))
            if len(node.items) > NODE_CAPACITY and node.depth < MAX_DEPTH:
                node.subdivide()
                existing = node.items
                node.items = []
                for r, it in existing:
                    self._insert_into_children(node, r, it)
            return

        self._insert_into_children(node, rect, item)

    def _insert_into_children(
        self, node: _Node, rect: QRectF, item: QGraphicsItem
    ) -> None:
        assert node.children is not None
        placed = False
        for child in node.children:
            if self._intersects(child.bounds, rect):
                self._insert(child, rect, item)
                placed = True
        if not placed:
            # Item straddles or lies outside all children -- keep at this node.
            node.items.append((QRectF(rect), item))

    def _query(
        self,
        node: _Node,
        region: QRectF,
        out: list[QGraphicsItem],
        seen: set[int],
    ) -> None:
        if not self._intersects(node.bounds, region) and node is not self._root:
            return
        for rect, item in node.items:
            if self._intersects(rect, region):
                key = id(item)
                if key not in seen:
                    seen.add(key)
                    out.append(item)
        if node.children is not None:
            for child in node.children:
                self._query(child, region, out, seen)


def build_from_items(
    items: list[QGraphicsItem],
    scene_bounds: QRectF | None = None,
) -> QuadTree:
    """Convenience: build a quadtree from a flat item list."""
    if scene_bounds is None:
        if not items:
            return QuadTree(QRectF(0, 0, 1, 1))
        union = items[0].sceneBoundingRect()
        for item in items[1:]:
            union = union.united(item.sceneBoundingRect())
        scene_bounds = union
    tree = QuadTree(scene_bounds)
    for item in items:
        tree.insert(item.sceneBoundingRect(), item)
    return tree
