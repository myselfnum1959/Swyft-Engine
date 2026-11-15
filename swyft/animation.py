"""Frame-based animation clips and a small player for them.

Pure logic: it only produces a *frame index*. Turning that index into pixels is
the job of whoever owns the sprite sheet (see ``swyft.sprites.SpriteSheet``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Animation:
    name: str
    frames: tuple[int, ...]
    fps: float = 10.0
    loop: bool = True

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("an animation needs at least one frame")
        if self.fps <= 0:
            raise ValueError("fps must be positive")


class Animator:
    def __init__(self) -> None:
        self._clips: dict[str, Animation] = {}
        self.current: Animation | None = None
        self.speed = 1.0
        self.finished = False
        self.on_finish: Callable[[str], None] | None = None
        self._time = 0.0

    def add(self, animation: Animation) -> None:
        self._clips[animation.name] = animation

    def play(self, name: str, *, restart: bool = False) -> None:
        """Start a clip. Asking for the clip that's already playing is a no-op,
        so it is safe to call every frame from game logic."""
        if name not in self._clips:
            raise KeyError(f"unknown animation {name!r}")
        clip = self._clips[name]
        if self.current is clip and not restart and not self.finished:
            return
        self.current = clip
        self._time = 0.0
        self.finished = False

    def update(self, dt: float) -> None:
        if self.current is None or self.finished:
            return
        self._time += dt * self.speed
        if not self.current.loop and int(self._time * self.current.fps) >= len(self.current.frames):
            self.finished = True
            if self.on_finish:
                self.on_finish(self.current.name)

    @property
    def frame(self) -> int:
        """The sheet frame to draw right now."""
        if self.current is None:
            raise RuntimeError("no animation is playing")
        index = int(self._time * self.current.fps)
        count = len(self.current.frames)
        index = index % count if self.current.loop else min(index, count - 1)
        return self.current.frames[index]
