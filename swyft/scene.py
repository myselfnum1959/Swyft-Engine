"""Scenes and the scene stack.

A *Scene* is one self-contained screen of the game (title menu, a level, a
dialogue sequence, a pause menu). The engine keeps scenes on a **stack**: pushing
a pause menu on top of a level freezes the level underneath (it still draws if the
top scene is ``transparent``), and popping returns to it exactly as it was.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .camera import Camera2D
from .entities import Entity
from .physics import PhysicsWorld

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Engine


class Scene:
    #: If True, the scene underneath is still drawn (for overlays like pause menus).
    transparent = False

    def __init__(self, name: str | None = None):
        self.name = name or type(self).__name__
        self.engine: Engine | None = None
        self.entities: list[Entity] = []
        self.world = PhysicsWorld()
        self.camera = Camera2D(800, 600)
        self._to_add: list[Entity] = []
        self._to_remove: list[Entity] = []
        self._updating = False

    # ---- engine plumbing ---------------------------------------------------
    def attach(self, engine: Engine) -> None:
        self.engine = engine
        self.camera.view_w, self.camera.view_h = engine.width, engine.height

    # ---- hooks for game code ----------------------------------------------
    def on_enter(self) -> None:
        """The scene became part of the stack."""

    def on_exit(self) -> None:
        """The scene was removed from the stack."""

    def on_pause(self) -> None:
        """Another scene was pushed on top of this one."""

    def on_resume(self) -> None:
        """The scene above was popped; this scene is active again."""

    # ---- entity management ------------------------------------------------
    def add(self, entity: Entity) -> Entity:
        # Adding while we iterate over self.entities would corrupt the loop, so
        # changes made during update() are queued and applied afterwards.
        if self._updating:
            self._to_add.append(entity)
        else:
            self._attach_entity(entity)
        return entity

    def remove(self, entity: Entity) -> None:
        if self._updating:
            self._to_remove.append(entity)
        else:
            self._detach_entity(entity)

    def _attach_entity(self, entity: Entity) -> None:
        if entity in self.entities:
            return
        entity.scene = self
        self.entities.append(entity)
        entity.on_added()

    def _detach_entity(self, entity: Entity) -> None:
        if entity not in self.entities:
            return
        entity.on_removed()
        self.entities.remove(entity)
        entity.scene = None

    def _flush(self) -> None:
        pending_add, self._to_add = self._to_add, []
        pending_remove, self._to_remove = self._to_remove, []
        for entity in pending_add:
            self._attach_entity(entity)
        for entity in pending_remove:
            self._detach_entity(entity)

    def find(self, name: str) -> Entity | None:
        return next((e for e in self.entities if e.name == name), None)

    def find_by_tag(self, tag: str) -> list[Entity]:
        return [e for e in self.entities if tag in e.tags]

    # v0.1 names
    add_entity = add
    remove_entity = remove

    # ---- per-tick work ----------------------------------------------------
    def update(self, dt: float) -> None:
        """Advance one fixed step. Subclasses override and call ``super().update``."""
        self._updating = True
        try:
            for entity in list(self.entities):
                if entity.active:
                    entity.update(dt)
            self.world.step(dt)
            for entity in list(self.entities):
                if entity.active:
                    entity.late_update(dt)
            self.camera.update(dt)
        finally:
            self._updating = False
        self._flush()

    def render(self, surface: Any) -> None:
        for entity in sorted((e for e in self.entities if e.visible and e.active), key=lambda e: e.z_index):
            entity.render(surface, self.camera)
        if self.engine is not None and self.engine.debug:
            self._draw_debug(surface)

    def _draw_debug(self, surface: Any) -> None:
        import pygame

        for body in self.world.bodies:
            color = (90, 255, 120) if not body.static else (255, 200, 60)
            pygame.draw.rect(surface, color, self.camera.apply_rect(body.aabb), 1)
        for trigger in self.world.triggers:
            pygame.draw.rect(surface, (255, 80, 200), self.camera.apply_rect(trigger.aabb), 1)


class SceneStack:
    """Owns the scenes. Changes requested mid-update are applied afterwards."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self._scenes: list[Scene] = []
        self._queue: list[tuple[str, Scene | None]] = []
        self.locked = False  # the engine locks the stack while scenes are updating

    @property
    def top(self) -> Scene | None:
        return self._scenes[-1] if self._scenes else None

    def __len__(self) -> int:
        return len(self._scenes)

    @property
    def scenes(self) -> list[Scene]:
        return list(self._scenes)

    def push(self, scene: Scene) -> None:
        self._request("push", scene)

    def pop(self) -> None:
        self._request("pop", None)

    def replace(self, scene: Scene) -> None:
        self._request("replace", scene)

    def _request(self, op: str, scene: Scene | None) -> None:
        self._queue.append((op, scene))
        if not self.locked:
            self.flush()

    def flush(self) -> None:
        while self._queue:
            op, scene = self._queue.pop(0)
            if op == "push":
                assert scene is not None
                if self._scenes:
                    self._scenes[-1].on_pause()
                self._scenes.append(scene)
                scene.attach(self.engine)
                scene.on_enter()
            elif op == "pop":
                if self._scenes:
                    self._scenes.pop().on_exit()
                    if self._scenes:
                        self._scenes[-1].on_resume()
            elif op == "replace":
                assert scene is not None
                if self._scenes:
                    self._scenes.pop().on_exit()
                self._scenes.append(scene)
                scene.attach(self.engine)
                scene.on_enter()

    def render(self, surface: Any) -> None:
        # Walk down until we reach a scene that fully covers what's below it.
        start = len(self._scenes) - 1
        while start > 0 and self._scenes[start].transparent:
            start -= 1
        for scene in self._scenes[max(start, 0):]:
            scene.render(surface)
