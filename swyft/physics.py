"""A small 2D AABB physics world.

Design notes (things worth being able to explain in an interview):

* **Gravity is an acceleration**, not a force. Forces are divided by mass
  (F = ma) but gravity affects light and heavy objects equally. The original
  engine applied gravity as a force, which made heavy bodies fall *slower*.
* **Axis-separated collision**: move on X, resolve, then move on Y, resolve.
  Resolving per axis gives exact "landed on top" / "hit a wall" information and
  avoids the corner-snagging that comes from guessing direction by smallest overlap.
* **Substepping** limits how far a body moves per collision check (half its
  smallest dimension) so fast bodies can't tunnel through thin walls.
* **Drag is exponential and per-second** (``v *= exp(-drag * dt)``), so it behaves
  the same at any update rate. A per-frame multiplier like ``v *= 0.98`` doesn't.
* **Triggers** are sensor volumes (no collision response) that report
  enter/exit. For story games these are the "walk up to the NPC / door" hooks.

Only static bodies are solid. Dynamic bodies don't push each other; that keeps
the system small and predictable for the kinds of games Swyft targets.
Broad-phase is a plain loop; a spatial hash is a natural future optimisation.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from .math2d import AABB, Vec2

#: How close (in pixels) counts as "touching" when probing for contacts.
CONTACT_EPS = 1e-3

CollideCallback = Callable[["Body", "Body", Vec2], None]
TriggerCallback = Callable[["Body"], None]


class Body:
    def __init__(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        static: bool = False,
        mass: float = 1.0,
        gravity_scale: float = 1.0,
        drag: float = 0.0,
        solid: bool = True,
        layer: int = 1,
        mask: int = 0xFFFFFFFF,
        terminal_velocity: float | None = 1600.0,
        owner: Any = None,
    ):
        if mass <= 0:
            raise ValueError("mass must be positive")
        self.aabb = AABB(x, y, w, h)
        self.velocity = Vec2()
        self.static = static
        self.mass = mass
        self.gravity_scale = gravity_scale
        self.drag = drag
        self.solid = solid
        self.layer = layer
        self.mask = mask
        self.terminal_velocity = terminal_velocity
        self.owner = owner
        self.enabled = True

        self.on_ground = False
        self.on_ceiling = False
        self.on_wall_left = False
        self.on_wall_right = False

        # Called as on_collide(self, other, normal); normal points from other to self.
        self.on_collide: CollideCallback | None = None
        self._force = Vec2()

    @property
    def position(self) -> Vec2:
        return Vec2(self.aabb.x, self.aabb.y)

    def set_position(self, x: float, y: float) -> None:
        self.aabb.x = float(x)
        self.aabb.y = float(y)

    def apply_force(self, force: Vec2) -> None:
        """Continuous force for the next step only (a = F / m)."""
        self._force = self._force + force

    def apply_impulse(self, impulse: Vec2) -> None:
        """Instant change of momentum (dv = J / m), e.g. a jump or knockback."""
        self.velocity = self.velocity + impulse / self.mass

    def collides_with(self, other: Body) -> bool:
        return bool(self.mask & other.layer) and bool(other.mask & self.layer)


class Trigger:
    """A non-solid area that reports when dynamic bodies enter or leave it."""

    def __init__(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        *,
        tag: str = "",
        on_enter: TriggerCallback | None = None,
        on_exit: TriggerCallback | None = None,
        mask: int = 0xFFFFFFFF,
        owner: Any = None,
    ):
        self.aabb = AABB(x, y, w, h)
        self.tag = tag
        self.on_enter = on_enter
        self.on_exit = on_exit
        self.mask = mask
        self.owner = owner
        self._inside: dict[Body, None] = {}  # dict used as an insertion-ordered set

    @property
    def occupants(self) -> list[Body]:
        return list(self._inside)


class PhysicsWorld:
    def __init__(self, gravity: Vec2 = Vec2(0.0, 1000.0)):
        self.gravity = gravity
        self._bodies: list[Body] = []
        self._triggers: list[Trigger] = []

    # ---- membership -------------------------------------------------------
    def add_body(self, body: Body) -> Body:
        if body not in self._bodies:
            self._bodies.append(body)
        return body

    def remove_body(self, body: Body) -> None:
        if body in self._bodies:
            self._bodies.remove(body)
        for trigger in self._triggers:
            trigger._inside.pop(body, None)

    def add_trigger(self, trigger: Trigger) -> Trigger:
        if trigger not in self._triggers:
            self._triggers.append(trigger)
        return trigger

    def remove_trigger(self, trigger: Trigger) -> None:
        if trigger in self._triggers:
            self._triggers.remove(trigger)

    @property
    def bodies(self) -> list[Body]:
        return list(self._bodies)

    @property
    def triggers(self) -> list[Trigger]:
        return list(self._triggers)

    def query(self, area: AABB, mask: int = 0xFFFFFFFF) -> list[Body]:
        """All enabled bodies overlapping ``area`` (e.g. 'who is in front of me?')."""
        return [b for b in self._bodies if b.enabled and (b.layer & mask) and b.aabb.intersects(area)]

    # ---- simulation -------------------------------------------------------
    def step(self, dt: float) -> None:
        for body in list(self._bodies):
            if body.static or not body.enabled:
                continue
            self._integrate(body, dt)
        self._update_triggers()

    def _integrate(self, body: Body, dt: float) -> None:
        # Semi-implicit Euler: update velocity first, then use the new velocity
        # to move. It is stable for game use and cheap.
        ax = self.gravity.x * body.gravity_scale + body._force.x / body.mass
        ay = self.gravity.y * body.gravity_scale + body._force.y / body.mass
        body._force = Vec2()

        vx = body.velocity.x + ax * dt
        vy = body.velocity.y + ay * dt

        if body.drag > 0:
            damping = math.exp(-body.drag * dt)
            vx *= damping
            vy *= damping
        if body.terminal_velocity is not None:
            vy = min(vy, body.terminal_velocity)

        body.velocity = Vec2(vx, vy)
        solids = self._solids_for(body)
        self._move(body, solids, vx * dt, vy * dt)
        self._probe_contacts(body, solids)

    def _solids_for(self, body: Body) -> list[Body]:
        return [
            s
            for s in self._bodies
            if s.static and s.solid and s.enabled and body.collides_with(s)
        ]

    def _move(self, body: Body, solids: list[Body], dx: float, dy: float) -> None:
        max_step = max(1.0, min(body.aabb.w, body.aabb.h) * 0.5)
        steps = max(1, math.ceil(max(abs(dx), abs(dy)) / max_step))
        sx, sy = dx / steps, dy / steps
        for _ in range(steps):
            if sx and self._move_axis(body, solids, sx, 0.0):
                sx = 0.0
            if sy and self._move_axis(body, solids, 0.0, sy):
                sy = 0.0
            if not sx and not sy:
                break

    def _move_axis(self, body: Body, solids: list[Body], dx: float, dy: float) -> bool:
        """Move along one axis and push out of any solid. Returns True on a hit."""
        box = body.aabb
        box.x += dx
        box.y += dy
        hit = False
        for solid in solids:
            other = solid.aabb
            if not box.intersects(other):
                continue
            hit = True
            if dx > 0:
                box.right = other.left
                body.velocity = Vec2(0.0, body.velocity.y)
                normal = Vec2(-1.0, 0.0)
            elif dx < 0:
                box.left = other.right
                body.velocity = Vec2(0.0, body.velocity.y)
                normal = Vec2(1.0, 0.0)
            elif dy > 0:
                box.bottom = other.top
                body.velocity = Vec2(body.velocity.x, 0.0)
                normal = Vec2(0.0, -1.0)
            else:
                box.top = other.bottom
                body.velocity = Vec2(body.velocity.x, 0.0)
                normal = Vec2(0.0, 1.0)
            if body.on_collide:
                body.on_collide(body, solid, normal)
        return hit

    def _probe_contacts(self, body: Body, solids: list[Body]) -> None:
        """Set on_ground / on_ceiling / on_wall_* by looking for solids touching the body.

        Flags are derived from *contact*, not from "did we just move into it", so a
        body resting against a wall keeps ``on_wall_*`` even though it no longer
        moves. Each probe is nudged by a tiny EPS and shrunk on the perpendicular
        axis, so sliding along a floor seam is never mistaken for a wall hit.
        """
        b = body.aabb
        eps = CONTACT_EPS
        probes = {
            "on_ground": AABB(b.x + eps, b.y + b.h, b.w - 2 * eps, eps * 2),
            "on_ceiling": AABB(b.x + eps, b.y - eps * 2, b.w - 2 * eps, eps * 2),
            "on_wall_left": AABB(b.x - eps * 2, b.y + eps, eps * 2, b.h - 2 * eps),
            "on_wall_right": AABB(b.x + b.w, b.y + eps, eps * 2, b.h - 2 * eps),
        }
        for flag, probe in probes.items():
            setattr(body, flag, any(probe.intersects(s.aabb) for s in solids))

    def _update_triggers(self) -> None:
        for trigger in list(self._triggers):
            now: dict[Body, None] = {}
            for body in self._bodies:
                if (
                    not body.static
                    and body.enabled
                    and (trigger.mask & body.layer)
                    and trigger.aabb.intersects(body.aabb)
                ):
                    now[body] = None
            for body in now:
                if body not in trigger._inside:
                    trigger._inside[body] = None
                    if trigger.on_enter:
                        trigger.on_enter(body)
            for body in list(trigger._inside):
                if body not in now:
                    del trigger._inside[body]
                    if trigger.on_exit:
                        trigger.on_exit(body)
