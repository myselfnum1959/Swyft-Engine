"""Data types for the story system.

Two layers:

* **Instructions** (``I*``): what the parser compiles a script into - a flat list,
  like tiny bytecode, with explicit jump targets. Flat code makes the runtime
  trivial (a program counter) and makes saving state as simple as storing an int.
* **Steps**: what the runner hands to the game - something to *show* (a line of
  dialogue, a choice, a presentation command) or the end of the story.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .expr import Expression

# =============================================================================
# Instructions (compiled form)
# =============================================================================


@dataclass
class ISay:
    speaker: str | None
    text: str
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class ICommand:
    name: str
    args: tuple[Any, ...]
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class ISet:
    name: str
    op: str  # "=", "+=", "-=", "*=", "/="
    value: Expression
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class IJump:
    target: int = -1
    label: str | None = None  # symbolic name, resolved to ``target`` after parsing
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class IJumpIfFalse:
    cond: Expression
    target: int = -1
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class IMenuOption:
    text: str
    cond: Expression | None
    target: int = -1


@dataclass
class IMenu:
    options: list[IMenuOption]
    line: int = field(default=0, repr=False, compare=False)


@dataclass
class IEnd:
    line: int = field(default=0, repr=False, compare=False)


# =============================================================================
# Steps (runtime output)
# =============================================================================


@dataclass(frozen=True)
class Say:
    speaker: str | None
    text: str


@dataclass(frozen=True)
class ChoiceOption:
    text: str
    target: int  # instruction index to continue from if picked


@dataclass(frozen=True)
class Choice:
    options: tuple[ChoiceOption, ...]


@dataclass(frozen=True)
class Command:
    name: str
    args: tuple[Any, ...]


@dataclass(frozen=True)
class End:
    pass


Step = Say | Choice | Command | End


def step_to_dict(step: Step) -> dict[str, Any]:
    if isinstance(step, Say):
        return {"type": "say", "speaker": step.speaker, "text": step.text}
    if isinstance(step, Choice):
        return {"type": "choice", "options": [{"text": o.text, "target": o.target} for o in step.options]}
    if isinstance(step, Command):
        return {"type": "command", "name": step.name, "args": list(step.args)}
    return {"type": "end"}


def step_from_dict(data: dict[str, Any]) -> Step:
    kind = data.get("type")
    if kind == "say":
        return Say(data.get("speaker"), data["text"])
    if kind == "choice":
        return Choice(tuple(ChoiceOption(o["text"], int(o["target"])) for o in data["options"]))
    if kind == "command":
        return Command(data["name"], tuple(data.get("args", ())))
    if kind == "end":
        return End()
    raise ValueError(f"unknown step type {kind!r}")


# =============================================================================
# Story
# =============================================================================


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    color: str | None = None  # "#rrggbb" used for the name tag


@dataclass
class Story:
    code: list[Any]
    labels: dict[str, int]
    defaults: dict[str, Any]
    characters: dict[str, Character]
    name: str = "<script>"
    fingerprint: str = ""
    _label_at: dict[int, list[str]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for label, address in self.labels.items():
            self._label_at.setdefault(address, []).append(label)
        if not self.fingerprint:
            # Hash of the compiled program (not the raw text) so that editing comments
            # or whitespace doesn't invalidate players' saves.
            digest = hashlib.sha1(repr((self.code, sorted(self.labels.items()))).encode("utf-8"))
            self.fingerprint = digest.hexdigest()[:16]

    def labels_at(self, address: int) -> list[str]:
        return self._label_at.get(address, [])

    def display_name(self, speaker: str | None) -> str | None:
        if speaker is None:
            return None
        character = self.characters.get(speaker)
        return character.name if character else speaker
