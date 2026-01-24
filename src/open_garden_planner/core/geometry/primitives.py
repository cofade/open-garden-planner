"""Geometry primitives for the garden planner.

All coordinates are in centimeters with:
- Origin at bottom-left corner
- X-axis positive to the right (East)
- Y-axis positive upward (North) - CAD convention
- Z-axis positive upward (for future 3D)
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Point:
    """A point in 2D/3D space.

    Coordinates are in centimeters.
    Z is optional and defaults to 0 for 2D operations.
    """

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: Point) -> Point:
        """Add two points (vector addition)."""
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Point) -> Point:
        """Subtract two points (vector subtraction)."""
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Point:
        """Multiply point by scalar."""
        return Point(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Point:
        """Right multiply by scalar."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Point:
        """Divide point by scalar."""
        return Point(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> Point:
        """Negate point."""
        return Point(-self.x, -self.y, -self.z)

    def distance_to(self, other: Point) -> float:
        """Calculate Euclidean distance to another point (2D, ignores Z)."""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx * dx + dy * dy)

    def distance_to_3d(self, other: Point) -> float:
        """Calculate Euclidean distance to another point (3D)."""
        dx = other.x - self.x
        dy = other.y - self.y
        dz = other.z - self.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def midpoint(self, other: Point) -> Point:
        """Calculate midpoint between this point and another."""
        return Point(
            (self.x + other.x) / 2,
            (self.y + other.y) / 2,
            (self.z + other.z) / 2,
        )

    def rotate_around(self, center: Point, angle_degrees: float) -> Point:
        """Rotate this point around a center point by angle (in degrees)."""
        angle_rad = math.radians(angle_degrees)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        # Translate to origin
        dx = self.x - center.x
        dy = self.y - center.y

        # Rotate
        new_x = dx * cos_a - dy * sin_a
        new_y = dx * sin_a + dy * cos_a

        # Translate back
        return Point(new_x + center.x, new_y + center.y, self.z)

    def snap_to_grid(self, grid_size: float) -> Point:
        """Snap point to nearest grid intersection."""
        return Point(
            round(self.x / grid_size) * grid_size,
            round(self.y / grid_size) * grid_size,
            self.z,
        )

    def to_tuple(self) -> tuple[float, float]:
        """Convert to (x, y) tuple for Qt compatibility."""
        return (self.x, self.y)

    def to_tuple_3d(self) -> tuple[float, float, float]:
        """Convert to (x, y, z) tuple."""
        return (self.x, self.y, self.z)

    @classmethod
    def from_tuple(cls, t: tuple[float, float]) -> Point:
        """Create Point from (x, y) tuple."""
        return cls(t[0], t[1])

    @classmethod
    def origin(cls) -> Point:
        """Return the origin point (0, 0, 0)."""
        return cls(0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned bounding box."""

    min_point: Point
    max_point: Point

    @property
    def width(self) -> float:
        """Width of the bounding box (X dimension)."""
        return self.max_point.x - self.min_point.x

    @property
    def height(self) -> float:
        """Height of the bounding box (Y dimension)."""
        return self.max_point.y - self.min_point.y

    @property
    def center(self) -> Point:
        """Center point of the bounding box."""
        return self.min_point.midpoint(self.max_point)

    @property
    def area(self) -> float:
        """Area of the bounding box."""
        return self.width * self.height

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside the bounding box."""
        return (
            self.min_point.x <= point.x <= self.max_point.x
            and self.min_point.y <= point.y <= self.max_point.y
        )

    def intersects(self, other: BoundingBox) -> bool:
        """Check if this bounding box intersects with another."""
        return not (
            self.max_point.x < other.min_point.x
            or self.min_point.x > other.max_point.x
            or self.max_point.y < other.min_point.y
            or self.min_point.y > other.max_point.y
        )

    def contains_box(self, other: BoundingBox) -> bool:
        """Check if this bounding box fully contains another."""
        return (
            self.min_point.x <= other.min_point.x
            and self.max_point.x >= other.max_point.x
            and self.min_point.y <= other.min_point.y
            and self.max_point.y >= other.max_point.y
        )

    def expanded(self, margin: float) -> BoundingBox:
        """Return a new bounding box expanded by margin on all sides."""
        return BoundingBox(
            Point(self.min_point.x - margin, self.min_point.y - margin),
            Point(self.max_point.x + margin, self.max_point.y + margin),
        )

    @classmethod
    def from_points(cls, points: Sequence[Point]) -> BoundingBox:
        """Create bounding box from a sequence of points."""
        if not points:
            return cls(Point.origin(), Point.origin())

        min_x = min(p.x for p in points)
        min_y = min(p.y for p in points)
        max_x = max(p.x for p in points)
        max_y = max(p.y for p in points)

        return cls(Point(min_x, min_y), Point(max_x, max_y))

    @classmethod
    def union(cls, boxes: Sequence[BoundingBox]) -> BoundingBox:
        """Create bounding box that contains all given boxes."""
        if not boxes:
            return cls(Point.origin(), Point.origin())

        min_x = min(b.min_point.x for b in boxes)
        min_y = min(b.min_point.y for b in boxes)
        max_x = max(b.max_point.x for b in boxes)
        max_y = max(b.max_point.y for b in boxes)

        return cls(Point(min_x, min_y), Point(max_x, max_y))


@dataclass(slots=True)
class Polygon:
    """A polygon defined by a sequence of vertices.

    Vertices should be in counter-clockwise order for positive area.
    """

    id: UUID = field(default_factory=uuid4)
    vertices: list[Point] = field(default_factory=list)

    def __len__(self) -> int:
        """Number of vertices."""
        return len(self.vertices)

    def __iter__(self) -> Iterator[Point]:
        """Iterate over vertices."""
        return iter(self.vertices)

    def __getitem__(self, index: int) -> Point:
        """Get vertex by index."""
        return self.vertices[index]

    @property
    def is_closed(self) -> bool:
        """A polygon with 3+ vertices is considered closed."""
        return len(self.vertices) >= 3

    @property
    def bounding_box(self) -> BoundingBox:
        """Get axis-aligned bounding box."""
        return BoundingBox.from_points(self.vertices)

    @property
    def center(self) -> Point:
        """Get centroid of the polygon."""
        if not self.vertices:
            return Point.origin()

        sum_x = sum(p.x for p in self.vertices)
        sum_y = sum(p.y for p in self.vertices)
        n = len(self.vertices)

        return Point(sum_x / n, sum_y / n)

    @property
    def area(self) -> float:
        """Calculate area using the shoelace formula.

        Returns positive area for counter-clockwise vertices,
        negative for clockwise.
        """
        if len(self.vertices) < 3:
            return 0.0

        n = len(self.vertices)
        area = 0.0

        for i in range(n):
            j = (i + 1) % n
            area += self.vertices[i].x * self.vertices[j].y
            area -= self.vertices[j].x * self.vertices[i].y

        return area / 2.0

    @property
    def perimeter(self) -> float:
        """Calculate perimeter (total edge length)."""
        if len(self.vertices) < 2:
            return 0.0

        total = 0.0
        n = len(self.vertices)

        for i in range(n):
            j = (i + 1) % n
            total += self.vertices[i].distance_to(self.vertices[j])

        return total

    def contains_point(self, point: Point) -> bool:
        """Check if point is inside polygon using ray casting."""
        if len(self.vertices) < 3:
            return False

        n = len(self.vertices)
        inside = False

        j = n - 1
        for i in range(n):
            vi = self.vertices[i]
            vj = self.vertices[j]

            if ((vi.y > point.y) != (vj.y > point.y)) and (
                point.x < (vj.x - vi.x) * (point.y - vi.y) / (vj.y - vi.y) + vi.x
            ):
                inside = not inside

            j = i

        return inside

    def translate(self, offset: Point) -> Polygon:
        """Return a new polygon translated by offset."""
        return Polygon(
            id=self.id,
            vertices=[v + offset for v in self.vertices],
        )

    def rotate(self, angle_degrees: float, center: Point | None = None) -> Polygon:
        """Return a new polygon rotated around center (or its own center)."""
        if center is None:
            center = self.center

        return Polygon(
            id=self.id,
            vertices=[v.rotate_around(center, angle_degrees) for v in self.vertices],
        )

    def scale(self, factor: float, center: Point | None = None) -> Polygon:
        """Return a new polygon scaled by factor around center."""
        if center is None:
            center = self.center

        new_vertices = []
        for v in self.vertices:
            # Translate to origin, scale, translate back
            dx = (v.x - center.x) * factor
            dy = (v.y - center.y) * factor
            new_vertices.append(Point(center.x + dx, center.y + dy, v.z))

        return Polygon(id=self.id, vertices=new_vertices)

    @classmethod
    def rectangle(
        cls,
        x: float,
        y: float,
        width: float,
        height: float,
        id: UUID | None = None,
    ) -> Polygon:
        """Create a rectangle polygon.

        Args:
            x: Left edge X coordinate
            y: Bottom edge Y coordinate
            width: Width (X dimension)
            height: Height (Y dimension)
            id: Optional UUID, generated if not provided
        """
        return cls(
            id=id or uuid4(),
            vertices=[
                Point(x, y),
                Point(x + width, y),
                Point(x + width, y + height),
                Point(x, y + height),
            ],
        )


@dataclass(slots=True)
class Polyline:
    """An open path defined by a sequence of points."""

    id: UUID = field(default_factory=uuid4)
    points: list[Point] = field(default_factory=list)

    def __len__(self) -> int:
        """Number of points."""
        return len(self.points)

    def __iter__(self) -> Iterator[Point]:
        """Iterate over points."""
        return iter(self.points)

    @property
    def length(self) -> float:
        """Calculate total length of the polyline."""
        if len(self.points) < 2:
            return 0.0

        total = 0.0
        for i in range(len(self.points) - 1):
            total += self.points[i].distance_to(self.points[i + 1])

        return total

    @property
    def bounding_box(self) -> BoundingBox:
        """Get axis-aligned bounding box."""
        return BoundingBox.from_points(self.points)
