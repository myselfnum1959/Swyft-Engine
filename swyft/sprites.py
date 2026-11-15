"""Sprite sheet slicing."""

from __future__ import annotations

import pygame


class SpriteSheet:
    """Cuts a grid image into equally sized frames (row by row, left to right).

    Pair it with :class:`swyft.animation.Animator`: the animator yields a frame
    *index*, ``sheet[index]`` gives the surface to draw.
    """

    def __init__(self, image: pygame.Surface, frame_width: int, frame_height: int, *, margin: int = 0, spacing: int = 0):
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame size must be positive")
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frames: list[pygame.Surface] = []
        width, height = image.get_size()
        y = margin
        while y + frame_height <= height - margin:
            x = margin
            while x + frame_width <= width - margin:
                self.frames.append(image.subsurface((x, y, frame_width, frame_height)))
                x += frame_width + spacing
            y += frame_height + spacing

    def __len__(self) -> int:
        return len(self.frames)

    def __getitem__(self, index: int) -> pygame.Surface:
        return self.frames[index]

    def flipped(self, horizontal: bool = True, vertical: bool = False) -> list[pygame.Surface]:
        """Mirrored copies of every frame (e.g. for a character facing left)."""
        return [pygame.transform.flip(f, horizontal, vertical) for f in self.frames]
