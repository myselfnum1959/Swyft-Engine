"""Entities: the objects that live inside a Scene.

Rendering helpers import pygame lazily (inside ``render``) so this module - and
therefore scene/physics logic - can be imported and tested without pygame.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .animation import Animator
from .math2d import Vec2
from .physics import Body

if TYPE_CHECKING:  # pragma: no cover
    from .camera import Camera2D
    from .engine import Engine
    from .scene import Scene


class Entity:
    """Base class for everything in a scene. Override the hooks you need."""

    def __init__(
        self,
        name: str = "Entity",
        x: float = 0.0,
        y: float = 0.0,
        *,
        z_index: int = 0,
        tags: tuple[str, ...] = (),
    ):
        self.name = name
        self.position = Vec2(x, y)
        self.active = True  # inactive entities are neither updated nor rendered
        self.visible = True
        self.z_index = z_index  # higher draws on top
        self.tags: set[str] = set(tags)
        self.scene: Scene | None = None

    @property
    def engine(self) -> Engine:
        if self.scene is None or self.scene.engine is None:
            raise RuntimeError(f"{self.name} is not attached to a running engine")
        return self.scene.engine

    # ---- lifecycle hooks ---------------------------------------------------
    def on_added(self) -> None:
        """Called when the entity enters a scene."""

    def on_removed(self) -> None:
        """Called when the entity leaves a scene."""

    def update(self, dt: float) -> None:
        """Called every fixed update, before physics."""

    def late_update(self, dt: float) -> None:
        """Called every fixed update, after physics (positions are final here)."""

    def render(self, surface: Any, camera: Camera2D) -> None:
        """Draw the entity. ``camera`` converts world to screen coordinates."""

    def destroy(self) -> None:
        if self.scene is not None:
            self.scene.remove(self)


class PhysicsEntity(Entity):
    """An entity driven by a dynamic :class:`~swyft.physics.Body`.

    The body is the source of truth for position; ``position`` is synced from it
    after every physics step. To teleport, call :meth:`teleport`.
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: int = 40,
        height: int = 40,
        mass: float = 1.0,
        *,
        color: tuple[int, int, int] = (50, 150, 255),
        **body_options: Any,
    ):
        super().__init__("PhysicsEntity", x, y)
        self.body = Body(x, y, width, height, mass=mass, owner=self, **body_options)
        self.color = color

    def on_added(self) -> None:
        assert self.scene is not None
        self.scene.world.add_body(self.body)

    def on_removed(self) -> None:
        if self.scene is not None:
            self.scene.world.remove_body(self.body)

    @property
    def velocity(self) -> Vec2:
        return self.body.velocity

    @velocity.setter
    def velocity(self, value: Vec2) -> None:
        self.body.velocity = value

    @property
    def is_on_ground(self) -> bool:
        return self.body.on_ground

    @property
    def center(self) -> Vec2:
        return self.body.aabb.center

    @property
    def rect(self):  # -> pygame.Rect  (kept for the engine's v0.1 API)
        import pygame

        return pygame.Rect(*(round(v) for v in self.body.aabb.as_tuple()))

    def apply_force(self, force: Vec2) -> None:
        self.body.apply_force(force)

    def teleport(self, x: float, y: float) -> None:
        self.body.set_position(x, y)
        self.position = Vec2(x, y)

    def late_update(self, dt: float) -> None:
        self.position = self.body.position

    def render(self, surface: Any, camera: Camera2D) -> None:
        import pygame

        pygame.draw.rect(surface, self.color, camera.apply_rect(self.body.aabb))


class StaticEntity(Entity):
    """Immovable solid geometry: floors, walls, platforms."""

    def __init__(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
        *,
        color: tuple[int, int, int] = (80, 120, 220),
        **body_options: Any,
    ):
        super().__init__("StaticEntity", x, y)
        self.body = Body(x, y, width, height, static=True, owner=self, **body_options)
        self.color = color

    def on_added(self) -> None:
        assert self.scene is not None
        self.scene.world.add_body(self.body)

    def on_removed(self) -> None:
        if self.scene is not None:
            self.scene.world.remove_body(self.body)

    @property
    def rect(self):
        import pygame

        return pygame.Rect(*(round(v) for v in self.body.aabb.as_tuple()))

    def render(self, surface: Any, camera: Camera2D) -> None:
        import pygame

        pygame.draw.rect(surface, self.color, camera.apply_rect(self.body.aabb))


class Sprite(Entity):
    """Draws an image, or an animated sheet frame, at its position."""

    def __init__(
        self,
        image: Any = None,
        x: float = 0.0,
        y: float = 0.0,
        *,
        frames: list[Any] | None = None,
        animator: Animator | None = None,
        **kwargs: Any,
    ):
        super().__init__("Sprite", x, y, **kwargs)
        self.image = image
        self.frames = frames
        self.animator = animator

    def update(self, dt: float) -> None:
        if self.animator is not None:
            self.animator.update(dt)

    def render(self, surface: Any, camera: Camera2D) -> None:
        image = self.image
        if self.frames is not None and self.animator is not None and self.animator.current:
            image = self.frames[self.animator.frame]
        if image is not None:
            surface.blit(image, camera.world_to_screen_xy(self.position))


# Names from Swyft v0.1, kept so old code keeps importing.
PhysicsBody = PhysicsEntity
StaticBody = StaticEntity
