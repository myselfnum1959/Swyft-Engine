"""Music and sound effects, degrading gracefully when there is no audio device."""

from __future__ import annotations

import logging

import pygame

from .assets import AssetManager
from .math2d import clamp

log = logging.getLogger("swyft.audio")


class AudioManager:
    def __init__(self, assets: AssetManager):
        self.assets = assets
        self.enabled = bool(pygame.mixer.get_init())
        self._music_volume = 0.7
        self._sfx_volume = 1.0
        self.current_music: str | None = None
        if not self.enabled:
            log.info("audio mixer unavailable; sound is disabled")

    @property
    def music_volume(self) -> float:
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value: float) -> None:
        self._music_volume = clamp(value, 0.0, 1.0)
        if self.enabled:
            pygame.mixer.music.set_volume(self._music_volume)

    @property
    def sfx_volume(self) -> float:
        return self._sfx_volume

    @sfx_volume.setter
    def sfx_volume(self, value: float) -> None:
        self._sfx_volume = clamp(value, 0.0, 1.0)

    def play_music(self, name: str, *, loop: bool = True, fade_ms: int = 600) -> None:
        if name == self.current_music:
            return  # already playing; don't restart the track
        self.current_music = name
        if not self.enabled:
            return
        if not self.assets.has(name):
            log.warning("missing music %r", name)
            return
        try:
            pygame.mixer.music.load(str(self.assets.path(name)))
            pygame.mixer.music.set_volume(self._music_volume)
            pygame.mixer.music.play(-1 if loop else 0, fade_ms=fade_ms)
        except pygame.error as exc:
            log.warning("could not play music %r: %s", name, exc)

    def stop_music(self, *, fade_ms: int = 600) -> None:
        self.current_music = None
        if self.enabled:
            pygame.mixer.music.fadeout(fade_ms)

    def play_sound(self, name: str) -> None:
        sound = self.assets.sound(name)
        if sound is not None:
            sound.set_volume(self._sfx_volume)
            sound.play()
