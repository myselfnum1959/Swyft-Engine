"""Text helpers for dialogue boxes: word wrapping and a typewriter reveal.

Both are pure functions/classes (no fonts or surfaces) so they can be tested.
Wrapping takes a ``measure`` callback, e.g. ``lambda s: font.size(s)[0]``.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Callable

# Extra pause (seconds) after punctuation that ends a clause/sentence.
PUNCTUATION_PAUSE = {".": 0.28, "!": 0.28, "?": 0.28, ",": 0.12, ";": 0.12, ":": 0.12, "…": 0.28}


def wrap_text(text: str, measure: Callable[[str], float], max_width: float) -> list[str]:
    """Greedy word wrap. Honours explicit newlines and splits over-long words."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        started = False
        for word in paragraph.split(" "):
            candidate = word if not started else f"{current} {word}"
            if measure(candidate) <= max_width or not started and not word:
                current, started = candidate, True
                continue
            if started:
                lines.append(current)
            # Start a new line with this word; hard-split it only if it is too long.
            current, started = "", True
            if measure(word) <= max_width:
                current = word
                continue
            for ch in word:
                if current and measure(current + ch) > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current += ch
        lines.append(current)
    return lines


def reveal_lines(lines: list[str], count: int) -> list[str]:
    """Show only the first ``count`` characters across wrapped ``lines``.

    One character is reserved between lines for the space/newline that wrapping
    removed, so the reveal speed matches the typewriter's character count
    (approximately, for hard-split words).
    """
    shown: list[str] = []
    remaining = count
    for line in lines:
        if remaining <= 0:
            break
        shown.append(line[:remaining])
        remaining -= len(line) + 1
    return shown


class Typewriter:
    """Reveals text over time, pausing briefly after sentence punctuation."""

    def __init__(self, text: str = "", chars_per_second: float = 45.0):
        self.chars_per_second = chars_per_second
        self._text = ""
        self._times: list[float] = []
        self._elapsed = 0.0
        self.set_text(text)

    def set_text(self, text: str) -> None:
        self._text = text
        self._elapsed = 0.0
        self._times = self._reveal_times(text)

    def _reveal_times(self, text: str) -> list[float]:
        """Time at which each character becomes visible."""
        if self.chars_per_second <= 0:
            return [0.0] * len(text)
        per_char = 1.0 / self.chars_per_second
        times: list[float] = []
        t = 0.0
        for i, ch in enumerate(text):
            times.append(t)
            t += per_char
            # Only pause when the punctuation ends a word ("Hi." yes, "3.14" no).
            ends_word = i + 1 == len(text) or text[i + 1].isspace()
            if ends_word and ch in PUNCTUATION_PAUSE:
                t += PUNCTUATION_PAUSE[ch]
        return times

    def update(self, dt: float) -> None:
        self._elapsed += dt

    def skip(self) -> None:
        """Reveal everything immediately."""
        self._elapsed = float("inf")

    @property
    def text(self) -> str:
        return self._text

    @property
    def visible_count(self) -> int:
        return bisect_right(self._times, self._elapsed)

    @property
    def visible(self) -> str:
        return self._text[: self.visible_count]

    @property
    def done(self) -> bool:
        return self.visible_count >= len(self._text)
