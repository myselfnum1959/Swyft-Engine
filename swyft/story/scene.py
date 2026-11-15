"""A ready-made scene that plays a story script: visual-novel style presentation.

It owns *presentation* (what is on screen); the :class:`StoryRunner` owns *flow*
(what happens next). They only communicate through steps, so you could replace
this class with your own renderer and keep the same scripts.

Asset conventions (all relative to the engine's asset folder; all optional -
placeholders are drawn if a file is missing so you can write the story first):

    backgrounds/<name>.png            used by   scene <name>
    characters/<name>_<expr>.png      used by   show <name> <expr>
    characters/<name>.png             fallback when there is no expression image
    music/<file>   sounds/<file>      used by   music "<file>" / sound "<file>"
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

import pygame

from ..save import SaveError
from ..scene import Scene
from ..text import Typewriter, reveal_lines, wrap_text
from .errors import StoryError
from .model import Choice, Command, End, Say, Story
from .runner import StoryRunner

log = logging.getLogger("swyft.story")

FADE_SECONDS = 0.5
SKIP_INTERVAL = 0.06
SLOTS = {"left": 0.2, "center": 0.5, "right": 0.8, "farleft": 0.08, "farright": 0.92}

CommandHandler = Callable[[tuple[Any, ...]], None]


@dataclass
class StoryTheme:
    text_color: tuple[int, int, int] = (240, 240, 245)
    box_color: tuple[int, int, int, int] = (12, 14, 28, 215)
    border_color: tuple[int, int, int] = (150, 160, 200)
    choice_color: tuple[int, int, int] = (28, 32, 60)
    choice_selected_color: tuple[int, int, int] = (70, 90, 170)
    text_size: int = 30
    name_size: int = 30
    box_height_ratio: float = 0.28
    margin: int = 24
    padding: int = 20
    font: str | None = None  # a font file inside the asset folder, or None for pygame's default


def _stable_color(text: str, low: int = 50, high: int = 150) -> tuple[int, int, int]:
    """A colour derived from text, identical on every run (unlike Python's hash())."""
    digest = hashlib.md5(text.encode("utf-8")).digest()
    span = high - low
    return tuple(low + digest[i] * span // 255 for i in range(3))  # type: ignore[return-value]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16))


class StoryScene(Scene):
    def __init__(
        self,
        story: Story,
        *,
        start: str = "start",
        on_end: Callable[[StoryScene], None] | None = None,
        text_speed: float = 45.0,
        theme: StoryTheme | None = None,
    ):
        super().__init__("StoryScene")
        self.story = story
        self.runner = StoryRunner(story)
        self.start_label = start
        self.on_end = on_end
        self.theme = theme or StoryTheme()
        self.typewriter = Typewriter(chars_per_second=text_speed)

        # What is currently on screen (saved/restored together with the runner).
        self.background: str | None = None
        self.sprites: dict[str, dict[str, Any]] = {}
        self.music: str | None = None

        self._say: Say | None = None
        self._choice: Choice | None = None
        self._selected = 0
        self._choice_rects: list[pygame.Rect] = []
        self._last_mouse: tuple[int, int] | None = None
        self._wait = 0.0
        self._ended = False
        self._fade = 0.0
        self._time = 0.0
        self._skip_timer = 0.0
        self._toast = ""
        self._toast_time = 0.0
        self._wrap_cache: tuple[str, int, list[str]] | None = None
        self._bg_cache: dict[tuple[str, int, int], pygame.Surface] = {}

        self._handlers: dict[str, CommandHandler] = {
            "scene": self._cmd_scene,
            "show": self._cmd_show,
            "hide": self._cmd_hide,
            "music": self._cmd_music,
            "sound": self._cmd_sound,
            "wait": self._cmd_wait,
            "shake": self._cmd_shake,
        }

    # ---- extension point -------------------------------------------------------
    def register_command(self, name: str, handler: CommandHandler) -> None:
        """Handle a custom script command (also pass it to ``parse_story(extra_commands=...)``)."""
        self._handlers[name] = handler

    # ---- lifecycle ---------------------------------------------------------------
    def on_enter(self) -> None:
        self.runner.start(self.start_label)
        self._advance()

    def on_exit(self) -> None:
        self.engine.audio.stop_music(fade_ms=300)  # type: ignore[union-attr]

    # ---- driving the story ---------------------------------------------------------
    def _advance(self) -> None:
        """Pull steps from the runner until one needs the player's attention."""
        self._say = None
        self._choice = None
        for _ in range(1000):
            step = self.runner.next()
            if isinstance(step, Command):
                self._apply_command(step)
                if self._wait > 0:
                    return
            elif isinstance(step, Say):
                self._say = step
                self.typewriter.set_text(step.text)
                self.engine.events.emit("story.say", speaker=step.speaker, text=step.text)  # type: ignore[union-attr]
                return
            elif isinstance(step, Choice):
                self._choice = step
                self._selected = 0
                return
            elif isinstance(step, End):
                self._finish()
                return
        log.error("a script ran 1000 presentation commands in a row without a line of dialogue")
        self._finish()

    def _finish(self) -> None:
        self._ended = True
        self.engine.events.emit("story.end")  # type: ignore[union-attr]
        if self.on_end is not None:
            self.on_end(self)

    def _leave(self) -> None:
        self.engine.pop_scene()  # type: ignore[union-attr]

    # ---- commands ---------------------------------------------------------------------
    def _apply_command(self, step: Command) -> None:
        handler = self._handlers.get(step.name)
        try:
            if handler is not None:
                handler(step.args)
            else:
                self.engine.events.emit("story.command", name=step.name, args=step.args)  # type: ignore[union-attr]
        except (ValueError, IndexError, TypeError) as exc:
            log.warning("bad arguments for command %s%r: %s", step.name, step.args, exc)

    def _cmd_scene(self, args: tuple[Any, ...]) -> None:
        self.background = str(args[0])
        self.sprites.clear()  # a new scene starts with an empty stage
        if "instant" not in args[1:]:
            self._fade = 1.0

    def _cmd_show(self, args: tuple[Any, ...]) -> None:
        name = str(args[0])
        rest = list(args[1:])
        position: Any = "center"
        if "at" in rest:
            i = rest.index("at")
            position = rest[i + 1] if i + 1 < len(rest) else "center"
            rest = rest[:i]
        expression = str(rest[0]) if rest else None
        self.sprites[name] = {"expr": expression, "pos": position}

    def _cmd_hide(self, args: tuple[Any, ...]) -> None:
        self.sprites.pop(str(args[0]), None)

    def _cmd_music(self, args: tuple[Any, ...]) -> None:
        if str(args[0]) == "stop":
            self.music = None
            self.engine.audio.stop_music()  # type: ignore[union-attr]
        else:
            self.music = str(args[0])
            self.engine.audio.play_music(f"music/{self.music}")  # type: ignore[union-attr]

    def _cmd_sound(self, args: tuple[Any, ...]) -> None:
        self.engine.audio.play_sound(f"sounds/{args[0]}")  # type: ignore[union-attr]

    def _cmd_wait(self, args: tuple[Any, ...]) -> None:
        self._wait = float(args[0]) if args else 1.0

    def _cmd_shake(self, args: tuple[Any, ...]) -> None:
        intensity = float(args[0]) if args else 8.0
        duration = float(args[1]) if len(args) > 1 else 0.4
        self.camera.shake(duration, intensity)

    # ---- saving ---------------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "story": self.runner.save_state(),
            "presentation": {
                "background": self.background,
                "sprites": {k: dict(v) for k, v in self.sprites.items()},
                "music": self.music,
            },
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.runner.load_state(data["story"])
        pres = data["presentation"]
        self.background = pres["background"]
        self.sprites = {k: dict(v) for k, v in pres["sprites"].items()}
        self.music = pres["music"]
        if self.music:
            self.engine.audio.play_music(f"music/{self.music}")  # type: ignore[union-attr]
        else:
            self.engine.audio.stop_music()  # type: ignore[union-attr]
        self._ended = False
        self._wait = 0.0
        self._say = self._choice = None
        current = self.runner.current
        if isinstance(current, Say):
            self._say = current
            self.typewriter.set_text(current.text)
            self.typewriter.skip()
        elif isinstance(current, Choice):
            self._choice = current
            self._selected = 0
        else:
            self._advance()

    def quick_save(self) -> None:
        if self._ended or (self._say is None and self._choice is None):
            self._show_toast("Can't save right now")
            return
        self.engine.saves.save("quick", self.snapshot(), label="Quick save")  # type: ignore[union-attr]
        self._show_toast("Quick saved")

    def quick_load(self) -> None:
        try:
            self.restore(self.engine.saves.load("quick"))  # type: ignore[union-attr]
            self._show_toast("Quick loaded")
        except (SaveError, StoryError, KeyError) as exc:
            log.warning("quick load failed: %s", exc)
            self._show_toast("No usable quick save")

    def _show_toast(self, text: str) -> None:
        self._toast, self._toast_time = text, 1.8

    # ---- per-tick update ----------------------------------------------------------------------
    def update(self, dt: float) -> None:
        super().update(dt)
        assert self.engine is not None
        inp = self.engine.input
        self._time += dt
        self.typewriter.update(dt)
        self._fade = max(0.0, self._fade - dt / FADE_SECONDS)
        self._toast_time = max(0.0, self._toast_time - dt)

        if inp.pressed("quicksave"):
            self.quick_save()
        if inp.pressed("quickload"):
            self.quick_load()

        if self._ended:
            if self.on_end is None and inp.pressed("confirm"):
                self._leave()
            return
        if self._wait > 0:
            self._wait -= dt
            if self._wait <= 0:
                self._advance()
            return
        if self._choice is not None:
            self._update_choice()
            return
        if self._say is not None:
            if inp.pressed("confirm"):
                if self.typewriter.done:
                    self._advance()
                else:
                    self.typewriter.skip()
            elif inp.down("skip"):  # hold Ctrl to fast-forward
                self.typewriter.skip()
                self._skip_timer -= dt
                if self._skip_timer <= 0:
                    self._skip_timer = SKIP_INTERVAL
                    self._advance()

    def _update_choice(self) -> None:
        assert self._choice is not None and self.engine is not None
        inp = self.engine.input
        count = len(self._choice.options)
        if inp.pressed("up"):
            self._selected = (self._selected - 1) % count
        if inp.pressed("down"):
            self._selected = (self._selected + 1) % count

        # Hovering only changes the selection when the mouse actually moves, so a
        # parked mouse cursor doesn't fight with keyboard navigation.
        if inp.mouse_pos != self._last_mouse:
            self._last_mouse = inp.mouse_pos
            for i, rect in enumerate(self._choice_rects):
                if rect.collidepoint(inp.mouse_pos):
                    self._selected = i

        picked: int | None = None
        if inp.raw_pressed("mouse1"):
            for i, rect in enumerate(self._choice_rects):
                if rect.collidepoint(inp.mouse_pos):
                    picked = i
        elif inp.pressed("confirm"):
            picked = self._selected

        if picked is not None and picked < count:
            option = self._choice.options[picked]
            self.engine.events.emit("story.choice", index=picked, text=option.text)
            self.runner.choose(picked)
            self._advance()

    # ---- rendering ------------------------------------------------------------------------------
    def render(self, surface: pygame.Surface) -> None:
        assert self.engine is not None
        width, height = surface.get_size()
        shake_x, shake_y = round(self.camera.offset.x), round(self.camera.offset.y)  # shakes the stage, not the UI

        self._draw_background(surface, width, height, shake_x, shake_y)
        self._draw_sprites(surface, width, height, shake_x, shake_y)
        super().render(surface)
        self._draw_dialogue(surface, width, height)
        if self._choice is not None:
            self._draw_choices(surface, width, height)
        if self._fade > 0:
            veil = pygame.Surface((width, height))
            veil.set_alpha(round(255 * self._fade))
            surface.blit(veil, (0, 0))
        if self._ended and self.on_end is None:
            self._draw_centered(surface, "The End", width, height, size=64)
        if self._toast_time > 0:
            font = self.engine.assets.font(self.theme.font, 24)
            surface.blit(font.render(self._toast, True, (255, 230, 140)), (16, 14))

    def _box_rect(self, width: int, height: int) -> pygame.Rect:
        t = self.theme
        box_h = int(height * t.box_height_ratio)
        return pygame.Rect(t.margin, height - box_h - t.margin, width - 2 * t.margin, box_h)

    def _draw_background(self, surface: pygame.Surface, width: int, height: int, ox: int, oy: int) -> None:
        if self.background is None:
            return
        image = self._background_image(self.background, width, height)
        if image is not None:
            surface.blit(image, (ox, oy))
            return
        pygame.draw.rect(surface, _stable_color(self.background, 25, 90), (ox, oy, width, height))
        font = self.engine.assets.font(self.theme.font, 22)  # type: ignore[union-attr]
        label = font.render(f"[background: {self.background}]", True, (170, 170, 190))
        surface.blit(label, (16 + ox, height - 24 + oy - self._box_rect(width, height).height - 60))

    def _background_image(self, name: str, width: int, height: int) -> pygame.Surface | None:
        key = (name, width, height)
        if key not in self._bg_cache:
            assets = self.engine.assets  # type: ignore[union-attr]
            raw = assets.try_image(f"backgrounds/{name}.png") or assets.try_image(f"backgrounds/{name}.jpg")
            if raw is None:
                return None
            self._bg_cache[key] = pygame.transform.smoothscale(raw, (width, height))
        return self._bg_cache[key]

    def _draw_sprites(self, surface: pygame.Surface, width: int, height: int, ox: int, oy: int) -> None:
        assets = self.engine.assets  # type: ignore[union-attr]
        feet_y = self._box_rect(width, height).top + 60
        for name, info in self.sprites.items():
            slot = info["pos"]
            fraction = SLOTS.get(str(slot)) if not isinstance(slot, (int, float)) else float(slot)
            x = round(width * (fraction if fraction is not None else 0.5)) + ox
            expression = info["expr"]
            image = None
            if expression:
                image = assets.try_image(f"characters/{name}_{expression}.png")
            image = image or assets.try_image(f"characters/{name}.png")
            if image is not None:
                surface.blit(image, image.get_rect(midbottom=(x, feet_y + oy)))
                continue
            # No art yet: draw a labelled stand-in so the scene is still readable.
            character = self.story.characters.get(name)
            color = _hex_to_rgb(character.color) if character and character.color else _stable_color(name)
            body = pygame.Rect(0, 0, round(width * 0.17), round(height * 0.52))
            body.midbottom = (x, feet_y + oy)
            pygame.draw.rect(surface, color, body, border_radius=18)
            pygame.draw.rect(surface, (255, 255, 255), body, 2, border_radius=18)
            font = assets.font(self.theme.font, 26)
            label = font.render(self.story.display_name(name) or name, True, (255, 255, 255))
            surface.blit(label, label.get_rect(center=(body.centerx, body.top + 28)))
            if expression:
                small = assets.font(self.theme.font, 22).render(f"({expression})", True, (235, 235, 245))
                surface.blit(small, small.get_rect(center=(body.centerx, body.top + 56)))

    def _draw_dialogue(self, surface: pygame.Surface, width: int, height: int) -> None:
        if self._say is None:
            return
        t = self.theme
        assets = self.engine.assets  # type: ignore[union-attr]
        box = self._box_rect(width, height)
        panel = pygame.Surface(box.size, pygame.SRCALPHA)
        panel.fill(t.box_color)
        surface.blit(panel, box.topleft)
        pygame.draw.rect(surface, t.border_color, box, 2, border_radius=8)

        name = self.story.display_name(self._say.speaker)
        if name:
            name_font = assets.font(t.font, t.name_size)
            character = self.story.characters.get(self._say.speaker or "")
            color = _hex_to_rgb(character.color) if character and character.color else (255, 225, 140)
            label = name_font.render(name, True, color)
            tag = pygame.Rect(box.x + 16, box.y - label.get_height() - 8, label.get_width() + 24, label.get_height() + 10)
            pygame.draw.rect(surface, (12, 14, 28), tag, border_radius=6)
            pygame.draw.rect(surface, t.border_color, tag, 2, border_radius=6)
            surface.blit(label, (tag.x + 12, tag.y + 5))

        font = assets.font(t.font, t.text_size)
        max_width = box.width - 2 * t.padding
        text = self._say.text
        if self._wrap_cache is None or self._wrap_cache[0] != text or self._wrap_cache[1] != max_width:
            # Wrap the *full* text up front so words don't jump lines while typing.
            self._wrap_cache = (text, max_width, wrap_text(text, lambda s: font.size(s)[0], max_width))
        lines = reveal_lines(self._wrap_cache[2], self.typewriter.visible_count)
        y = box.y + t.padding
        for line in lines:
            surface.blit(font.render(line, True, t.text_color), (box.x + t.padding, y))
            y += font.get_linesize()

        if self.typewriter.done and int(self._time * 2) % 2 == 0:  # blinking "continue" arrow
            x, by = box.right - 34, box.bottom - 30
            pygame.draw.polygon(surface, t.text_color, [(x, by), (x + 18, by), (x + 9, by + 12)])

    def _draw_choices(self, surface: pygame.Surface, width: int, height: int) -> None:
        assert self._choice is not None
        t = self.theme
        font = self.engine.assets.font(t.font, t.text_size)  # type: ignore[union-attr]
        options = self._choice.options
        button_h, gap = 46, 14
        widest = max(font.size(o.text)[0] for o in options) + 56
        button_w = min(max(widest, 300), width - 2 * t.margin)
        area_h = height - self._box_rect(width, height).height - 2 * t.margin
        top = max(t.margin, (area_h - (len(options) * button_h + (len(options) - 1) * gap)) // 2)
        self._choice_rects = []
        for i, option in enumerate(options):
            rect = pygame.Rect((width - button_w) // 2, top + i * (button_h + gap), button_w, button_h)
            self._choice_rects.append(rect)
            selected = i == self._selected
            pygame.draw.rect(surface, t.choice_selected_color if selected else t.choice_color, rect, border_radius=10)
            pygame.draw.rect(surface, (255, 255, 255) if selected else t.border_color, rect, 2, border_radius=10)
            label = font.render(option.text, True, t.text_color)
            surface.blit(label, label.get_rect(center=rect.center))

    def _draw_centered(self, surface: pygame.Surface, text: str, width: int, height: int, *, size: int) -> None:
        font = self.engine.assets.font(self.theme.font, size)  # type: ignore[union-attr]
        label = font.render(text, True, (255, 255, 255))
        shade = pygame.Surface((width, height), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 150))
        surface.blit(shade, (0, 0))
        surface.blit(label, label.get_rect(center=(width // 2, height // 2)))
