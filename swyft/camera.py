"""2D camera: follow target, world bounds, screen shake, coordinate conversion."""

from __future__ import annotations

import math
import random

from .math2d import AABB, Vec2


class Camera2D:
    def __init__(self, view_w: int, view_h: int, *, seed: int | None = None):
        self.view_w = view_w
        self.view_h = view_h
        self.position = Vec2(0.0, 0.0)  # world coords of the view's top-left corner
        self.smoothing = 8.0  # higher = snappier; 0 = lock on instantly
        self.bounds: AABB | None = None  # keep the view inside this world rectangle
        self.offset = Vec2(0.0, 0.0)  # current shake offset (screen pixels)
        self._target: Vec2 | None = None
        self._shake_time = 0.0
        self._shake_total = 0.0
        self._shake_magnitude = 0.0
        self._rng = random.Random(seed)

    def follow(self, target: Vec2 | None) -> None:
        """Set the world point to keep centred (``None`` stops following)."""
        self._target = target

    def snap_to_target(self) -> None:
        """Jump straight to the target (use after teleporting / loading a level)."""
        if self._target is not None:
            self.position = self._clamped(self._desired())

    def shake(self, duration: float, magnitude: float) -> None:
        self._shake_time = self._shake_total = duration
        self._shake_magnitude = magnitude

    def _desired(self) -> Vec2:
        assert self._target is not None
        return Vec2(self._target.x - self.view_w / 2, self._target.y - self.view_h / 2)

    def _clamped(self, pos: Vec2) -> Vec2:
        if self.bounds is None:
            return pos
        b = self.bounds
        # If the world is smaller than the view on an axis, centre it on that axis.
        x = b.x + (b.w - self.view_w) / 2 if b.w <= self.view_w else max(b.left, min(pos.x, b.right - self.view_w))
        y = b.y + (b.h - self.view_h) / 2 if b.h <= self.view_h else max(b.top, min(pos.y, b.bottom - self.view_h))
        return Vec2(x, y)

    def update(self, dt: float) -> None:
        if self._target is not None:
            desired = self._desired()
            if self.smoothing <= 0:
                new_pos = desired
            else:
                # Frame-rate independent exponential smoothing.
                t = 1.0 - math.exp(-self.smoothing * dt)
                new_pos = self.position.lerp(desired, t)
            self.position = self._clamped(new_pos)
        elif self.bounds is not None:
            self.position = self._clamped(self.position)

        if self._shake_time > 0:
            self._shake_time = max(0.0, self._shake_time - dt)
            falloff = self._shake_time / self._shake_total if self._shake_total else 0.0
            m = self._shake_magnitude * falloff
            self.offset = Vec2(self._rng.uniform(-m, m), self._rng.uniform(-m, m))
        else:
            self.offset = Vec2(0.0, 0.0)

    # ---- conversion -------------------------------------------------------
    def world_to_screen(self, point: Vec2) -> Vec2:
        return Vec2(point.x - self.position.x + self.offset.x, point.y - self.position.y + self.offset.y)

    def screen_to_world(self, point: Vec2) -> Vec2:
        return Vec2(point.x + self.position.x - self.offset.x, point.y + self.position.y - self.offset.y)

    def world_to_screen_xy(self, point: Vec2) -> tuple[int, int]:
        """Pixel-snapped screen position (rounding avoids sub-pixel shimmer)."""
        s = self.world_to_screen(point)
        return (round(s.x), round(s.y))

    def apply_rect(self, box: AABB) -> tuple[int, int, int, int]:
        x, y = self.world_to_screen_xy(Vec2(box.x, box.y))
        return (x, y, round(box.w), round(box.h))
