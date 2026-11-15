"""The Engine: window, main loop, and the shared services every scene uses.

Frame structure::

    pump OS events -> feed InputManager
    run N fixed-size update ticks (N depends on how much real time passed)
    render once
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pygame

from .assets import AssetManager
from .audio import AudioManager
from .events import EventBus
from .input import DEFAULT_BINDINGS, InputManager
from .save import SaveManager
from .scene import Scene, SceneStack
from .timing import FixedTimestep

log = logging.getLogger("swyft.engine")


@dataclass
class EngineConfig:
    title: str = "Swyft Game"
    width: int = 800
    height: int = 600
    fps_cap: int = 60  # 0 = uncapped
    fixed_dt: float = 1 / 60  # simulation step in seconds
    resizable: bool = True
    headless: bool = False  # no window/audio: for tests and CI
    asset_path: str | Path = "assets"
    save_dir: str | Path | None = None  # default: ~/.swyft/<title>/saves
    clear_color: tuple[int, int, int] = (30, 30, 35)
    debug: bool = False


class Engine:
    """Create one per game::

        engine = Engine("My Game", 960, 540)
        engine.push_scene(MyScene())
        engine.run()
    """

    def __init__(self, title: str = "Swyft Game", width: int = 800, height: int = 600, *, config: EngineConfig | None = None, **options):
        self.config = config or EngineConfig(title=title, width=width, height=height, **options)
        cfg = self.config

        if cfg.headless:
            # Must be set before pygame creates a display / audio device.
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        pygame.init()
        flags = 0 if cfg.headless else (pygame.SCALED | (pygame.RESIZABLE if cfg.resizable else 0))
        self.screen = pygame.display.set_mode((cfg.width, cfg.height), flags)
        pygame.display.set_caption(cfg.title)
        self.clock = pygame.time.Clock()

        # Services shared by every scene.
        self.events = EventBus()
        self.input = InputManager()
        self.input.set_defaults(DEFAULT_BINDINGS)
        self.assets = AssetManager(cfg.asset_path)
        self.audio = AudioManager(self.assets)
        self.saves = SaveManager(cfg.save_dir or self._default_save_dir(cfg.title))
        self.scenes = SceneStack(self)

        self.debug = cfg.debug
        self.running = False
        self._timestep = FixedTimestep(cfg.fixed_dt)
        self._debug_font: pygame.font.Font | None = None

    @staticmethod
    def _default_save_dir(title: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "game"
        return Path.home() / ".swyft" / slug / "saves"

    @property
    def width(self) -> int:
        return self.config.width

    @property
    def height(self) -> int:
        return self.config.height

    # ---- scene shortcuts -----------------------------------------------------
    def push_scene(self, scene: Scene) -> None:
        self.scenes.push(scene)

    def pop_scene(self) -> None:
        self.scenes.pop()

    def replace_scene(self, scene: Scene) -> None:
        self.scenes.replace(scene)

    @property
    def scene(self) -> Scene:
        """The active scene. (v0.1 compatibility: creates an empty one if none exists.)"""
        if self.scenes.top is None:
            self.scenes.push(Scene("Main"))
        top = self.scenes.top
        assert top is not None
        return top

    def stop(self) -> None:
        self.running = False

    # ---- main loop -------------------------------------------------------------
    def run(self, max_frames: int | None = None) -> None:
        """Run until the window closes, ``stop()`` is called, or no scenes remain.

        ``max_frames`` is for tests/benchmarks. Unlike v0.1 this returns normally
        instead of calling ``sys.exit()`` - a library shouldn't kill your program.
        """
        if self.scenes.top is None:
            raise RuntimeError("nothing to run: call engine.push_scene(...) first")
        self.running = True
        frames = 0
        try:
            while self.running and self.scenes.top is not None:
                frame_time = self.clock.tick(self.config.fps_cap) / 1000.0
                self._pump_events()
                for _ in range(self._timestep.advance(frame_time)):
                    self._tick(self.config.fixed_dt)
                    if not self.running or self.scenes.top is None:
                        break
                self._render()
                frames += 1
                if max_frames is not None and frames >= max_frames:
                    break
        finally:
            self.running = False
            self.shutdown()

    def shutdown(self) -> None:
        if pygame.get_init():
            pygame.quit()

    def _pump_events(self) -> None:
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop()
            elif event.type == pygame.KEYDOWN:
                self.input.key_down(pygame.key.name(event.key))
            elif event.type == pygame.KEYUP:
                self.input.key_up(pygame.key.name(event.key))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.input.key_down(f"mouse{event.button}")
            elif event.type == pygame.MOUSEBUTTONUP:
                self.input.key_up(f"mouse{event.button}")
            elif focus_lost is not None and event.type == focus_lost:
                self.input.release_all()  # avoid "stuck" keys after alt-tab
        self.input.set_mouse_pos(pygame.mouse.get_pos())

    def _tick(self, dt: float) -> None:
        self.input.tick()
        if self.input.pressed("toggle_debug"):
            self.debug = not self.debug
        if self.input.pressed("toggle_fullscreen"):
            try:
                pygame.display.toggle_fullscreen()
            except pygame.error as exc:
                log.warning("fullscreen not available: %s", exc)
        scene = self.scenes.top
        if scene is None:
            return
        # Scene changes requested during update take effect after it finishes.
        self.scenes.locked = True
        try:
            scene.update(dt)
        finally:
            self.scenes.locked = False
        self.scenes.flush()

    def _render(self) -> None:
        self.screen.fill(self.config.clear_color)
        self.scenes.render(self.screen)
        if self.debug:
            self._draw_debug_overlay()
        pygame.display.flip()

    def _draw_debug_overlay(self) -> None:
        if self._debug_font is None:
            self._debug_font = pygame.font.Font(None, 20)
        top = self.scenes.top
        lines = [
            f"{self.clock.get_fps():.0f} FPS",
            "scenes: " + " > ".join(s.name for s in self.scenes.scenes),
        ]
        if top is not None:
            lines.append(f"entities: {len(top.entities)}  bodies: {len(top.world.bodies)}")
        for i, line in enumerate(lines):
            shadow = self._debug_font.render(line, True, (0, 0, 0))
            text = self._debug_font.render(line, True, (255, 255, 255))
            self.screen.blit(shadow, (9, 9 + i * 18))
            self.screen.blit(text, (8, 8 + i * 18))


# v0.1 name
SwyftEngine = Engine
