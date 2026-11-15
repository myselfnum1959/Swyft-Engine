"""Small 2D math types used across the engine.

These deliberately do *not* depend on pygame. Keeping the engine core free of the
rendering library means the physics, camera and story code can be unit-tested
headlessly (e.g. in CI) and, in principle, ported to another backend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator


def clamp(value: float, low: float, high: float) -> float:
    """Limit ``value`` to the range [low, high]."""
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class Vec2:
    """An immutable 2D vector.

    Immutable on purpose: ``a + b`` always returns a new vector, so you can't
    accidentally mutate a vector that something else is holding on to.
    """

    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: Vec2) -> Vec2:
        if not isinstance(other, Vec2):
            return NotImplemented
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vec2) -> Vec2:
        if not isinstance(other, Vec2):
            return NotImplemented
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vec2:
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Vec2(self.x * scalar, self.y * scalar)

    __rmul__ = __mul__

    def __truediv__(self, scalar: float) -> Vec2:
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Vec2(self.x / scalar, self.y / scalar)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def __iter__(self) -> Iterator[float]:
        yield self.x
        yield self.y

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vec2:
        """Unit-length copy of this vector (the zero vector stays zero)."""
        n = self.length()
        return Vec2(0.0, 0.0) if n == 0 else self / n

    def dot(self, other: Vec2) -> float:
        return self.x * other.x + self.y * other.y

    def lerp(self, other: Vec2, t: float) -> Vec2:
        """Linear interpolation: t=0 gives self, t=1 gives other."""
        return Vec2(self.x + (other.x - self.x) * t, self.y + (other.y - self.y) * t)

    def to_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)


class AABB:
    """Axis-aligned bounding box (x/y is the top-left corner; y grows downward)."""

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float):
        if w < 0 or h < 0:
            raise ValueError("AABB width and height must be non-negative")
        self.x = float(x)
        self.y = float(y)
        self.w = float(w)
        self.h = float(h)

    # Edge accessors. The setters move the box (they never resize it), which makes
    # collision resolution read naturally: ``body.bottom = floor.top``.
    @property
    def left(self) -> float:
        return self.x

    @left.setter
    def left(self, value: float) -> None:
        self.x = value

    @property
    def right(self) -> float:
        return self.x + self.w

    @right.setter
    def right(self, value: float) -> None:
        self.x = value - self.w

    @property
    def top(self) -> float:
        return self.y

    @top.setter
    def top(self, value: float) -> None:
        self.y = value

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @bottom.setter
    def bottom(self, value: float) -> None:
        self.y = value - self.h

    @property
    def center(self) -> Vec2:
        return Vec2(self.x + self.w / 2, self.y + self.h / 2)

    def intersects(self, other: AABB) -> bool:
        """True if the boxes overlap. Boxes that merely touch do NOT intersect."""
        return (
            self.x < other.x + other.w
            and other.x < self.x + self.w
            and self.y < other.y + other.h
            and other.y < self.y + self.h
        )

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def copy(self) -> AABB:
        return AABB(self.x, self.y, self.w, self.h)

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)

    def __repr__(self) -> str:
        return f"AABB(x={self.x}, y={self.y}, w={self.w}, h={self.h})"
