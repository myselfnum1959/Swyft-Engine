"""Action-based input.

Game code asks "is *jump* pressed?" rather than "is the Space key down?". That
makes rebinding keys trivial and lets one action map to keyboard *and* mouse.

Keys are plain lowercase strings as produced by ``pygame.key.name`` ("space",
"left ctrl", "a", ...). Mouse buttons are the pseudo-keys "mouse1", "mouse2", ...
Because the manager never touches pygame itself, it is fully unit-testable.

Edge detection (pressed / released) is evaluated once per *fixed update tick*
via :meth:`tick`, and raw key events are buffered between ticks, so a quick tap
that begins and ends between two ticks is still seen as a press.
"""

from __future__ import annotations

from typing import Iterable


class InputManager:
    def __init__(self) -> None:
        self._bindings: dict[str, set[str]] = {}
        self._down: set[str] = set()
        self._pressed_buffer: set[str] = set()
        self._released_buffer: set[str] = set()
        self._pressed: set[str] = set()
        self._released: set[str] = set()
        self.mouse_pos: tuple[int, int] = (0, 0)

    # ---- bindings ---------------------------------------------------------
    def bind(self, action: str, *keys: str) -> None:
        """Add keys to an action (existing keys are kept)."""
        self._bindings.setdefault(action, set()).update(k.lower() for k in keys)

    def rebind(self, action: str, *keys: str) -> None:
        """Replace all keys of an action."""
        self._bindings[action] = {k.lower() for k in keys}

    def unbind(self, action: str) -> None:
        self._bindings.pop(action, None)

    def bindings(self) -> dict[str, list[str]]:
        """Copy of the current bindings (handy for saving a controls menu)."""
        return {a: sorted(keys) for a, keys in self._bindings.items()}

    def _keys_for(self, action: str) -> set[str]:
        return self._bindings.get(action, set())

    # ---- raw events (called by the engine) --------------------------------
    def key_down(self, key: str) -> None:
        key = key.lower()
        if key not in self._down:
            self._down.add(key)
            self._pressed_buffer.add(key)

    def key_up(self, key: str) -> None:
        key = key.lower()
        if key in self._down:
            self._down.discard(key)
            self._released_buffer.add(key)

    def set_mouse_pos(self, pos: tuple[int, int]) -> None:
        self.mouse_pos = pos

    def release_all(self) -> None:
        """Forget held keys (e.g. when the window loses focus)."""
        for key in list(self._down):
            self.key_up(key)

    def tick(self) -> None:
        """Latch buffered edges. Call once at the start of every fixed update."""
        self._pressed = self._pressed_buffer
        self._released = self._released_buffer
        self._pressed_buffer = set()
        self._released_buffer = set()

    # ---- queries (called by game code) ------------------------------------
    def down(self, action: str) -> bool:
        """True while any key of the action is held."""
        return not self._keys_for(action).isdisjoint(self._down)

    def pressed(self, action: str) -> bool:
        """True only on the tick the action went from up to down."""
        return not self._keys_for(action).isdisjoint(self._pressed)

    def released(self, action: str) -> bool:
        return not self._keys_for(action).isdisjoint(self._released)

    def axis(self, negative: str, positive: str) -> int:
        """-1, 0 or +1 from two actions, e.g. ``axis("left", "right")``."""
        return int(self.down(positive)) - int(self.down(negative))

    def raw_down(self, key: str) -> bool:
        return key.lower() in self._down

    def raw_pressed(self, key: str) -> bool:
        return key.lower() in self._pressed

    def set_defaults(self, mapping: dict[str, Iterable[str]]) -> None:
        for action, keys in mapping.items():
            self.bind(action, *keys)


DEFAULT_BINDINGS: dict[str, tuple[str, ...]] = {
    "confirm": ("return", "space", "mouse1", "z"),
    "cancel": ("escape", "x"),
    "up": ("up", "w"),
    "down": ("down", "s"),
    "left": ("left", "a"),
    "right": ("right", "d"),
    "jump": ("space", "up", "w"),
    "skip": ("left ctrl", "right ctrl"),
    "quicksave": ("f5",),
    "quickload": ("f9",),
    "toggle_debug": ("f3",),
    "toggle_fullscreen": ("f11",),
}
