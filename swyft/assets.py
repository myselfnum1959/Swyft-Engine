"""Asset loading with caching.

Loading an image from disk every time a sprite is drawn would be very slow, so
every asset is loaded once and reused. Missing files never crash the game by
default: ``try_image`` returns ``None`` and ``image`` returns a visible
magenta/black placeholder (the classic "missing texture"), with a single warning
in the log. Pass ``strict=True`` to turn missing files into errors instead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pygame

log = logging.getLogger("swyft.assets")


class AssetError(Exception):
    pass


class AssetManager:
    def __init__(self, base_path: str | Path = "assets", *, strict: bool = False):
        self.base_path = Path(base_path)
        self.strict = strict
        self._images: dict[str, pygame.Surface | None] = {}
        self._fonts: dict[tuple[str | None, int], pygame.font.Font] = {}
        self._sounds: dict[str, Any] = {}
        self._warned: set[str] = set()

    def path(self, name: str) -> Path:
        return self.base_path / name

    def has(self, name: str) -> bool:
        return self.path(name).is_file()

    def _missing(self, name: str, kind: str) -> None:
        if self.strict:
            raise AssetError(f"missing {kind}: {self.path(name)}")
        if name not in self._warned:
            self._warned.add(name)
            log.warning("missing %s %r (looked in %s)", kind, name, self.base_path)

    # ---- images ----------------------------------------------------------
    def try_image(self, name: str, *, warn: bool = False) -> pygame.Surface | None:
        """The image, or ``None`` if the file doesn't exist (misses are cached too)."""
        if name in self._images:
            return self._images[name]
        image: pygame.Surface | None = None
        path = self.path(name)
        if path.is_file():
            try:
                image = pygame.image.load(str(path))
                try:
                    image = image.convert_alpha()  # faster blits; needs a display
                except pygame.error:
                    pass
            except pygame.error as exc:
                raise AssetError(f"could not load image {path}: {exc}") from exc
        elif warn:
            self._missing(name, "image")
        self._images[name] = image
        return image

    def image(self, name: str) -> pygame.Surface:
        """The image, or a magenta placeholder if it is missing."""
        found = self.try_image(name, warn=True)
        return found if found is not None else self._placeholder()

    @staticmethod
    def _placeholder(size: int = 64) -> pygame.Surface:
        surface = pygame.Surface((size, size))
        surface.fill((255, 0, 255))
        half = size // 2
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, half, half))
        pygame.draw.rect(surface, (0, 0, 0), (half, half, half, half))
        return surface

    # ---- fonts -------------------------------------------------------------
    def font(self, name: str | None = None, size: int = 28) -> pygame.font.Font:
        """A font file from the assets folder, or pygame's built-in font if ``name`` is None."""
        key = (name, size)
        if key not in self._fonts:
            if name is None:
                self._fonts[key] = pygame.font.Font(None, size)
            else:
                path = self.path(name)
                if not path.is_file():
                    self._missing(name, "font")
                    self._fonts[key] = pygame.font.Font(None, size)
                else:
                    self._fonts[key] = pygame.font.Font(str(path), size)
        return self._fonts[key]

    # ---- sounds ------------------------------------------------------------
    def sound(self, name: str) -> Any | None:
        if name in self._sounds:
            return self._sounds[name]
        sound = None
        if not pygame.mixer.get_init():
            pass  # no audio device (e.g. headless CI)
        elif self.has(name):
            try:
                sound = pygame.mixer.Sound(str(self.path(name)))
            except pygame.error as exc:
                log.warning("could not load sound %r: %s", name, exc)
        else:
            self._missing(name, "sound")
        self._sounds[name] = sound
        return sound

    def clear(self) -> None:
        """Drop every cached asset (e.g. when switching to a new chapter)."""
        self._images.clear()
        self._fonts.clear()
        self._sounds.clear()
