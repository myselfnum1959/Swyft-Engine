"""Executes a compiled :class:`~swyft.story.model.Story`.

The runner knows nothing about graphics. The game repeatedly calls :meth:`next`
and gets back a *step* to present:

* ``Say``      - show a line of dialogue (wait for the player)
* ``Choice``   - show options, then call :meth:`choose` with the picked index
* ``Command``  - a presentation instruction (``scene``, ``show``, ...) to apply
* ``End``      - the story is over

Silent instructions (``set``, ``jump``, ``if``) are executed internally.
"""

from __future__ import annotations

from typing import Any

from .errors import ExpressionEvalError, SaveIncompatibleError, StoryRuntimeError
from .expr import interpolate
from .model import (
    Choice,
    ChoiceOption,
    Command,
    End,
    ICommand,
    IEnd,
    IJump,
    IJumpIfFalse,
    IMenu,
    ISay,
    ISet,
    Say,
    Step,
    Story,
    step_from_dict,
    step_to_dict,
)

SAVE_VERSION = 1
_ARITHMETIC = {
    "+=": lambda a, b: a + b,
    "-=": lambda a, b: a - b,
    "*=": lambda a, b: a * b,
    "/=": lambda a, b: a / b,
}


class StoryRunner:
    #: Safety net: this many instructions in a row without showing anything
    #: almost certainly means a script loop like ``label a: jump a``.
    MAX_SILENT_INSTRUCTIONS = 10_000

    def __init__(self, story: Story, *, history_limit: int = 200):
        self.story = story
        self.history_limit = history_limit
        self.variables: dict[str, Any] = {}
        self.visited: set[str] = set()
        self.history: list[tuple[str | None, str]] = []  # backlog of (speaker, text)
        self.current: Step | None = None  # the last blocking step shown
        self.finished = False
        self.pc: int | None = None
        self._pending: Choice | None = None

    # ---- lifecycle ---------------------------------------------------------
    def start(self, label: str = "start") -> None:
        if label not in self.story.labels:
            raise StoryRuntimeError(f"story {self.story.name!r} has no label {label!r}")
        self.variables = dict(self.story.defaults)
        self.visited = set()
        self.history = []
        self.current = None
        self.finished = False
        self._pending = None
        self.pc = self.story.labels[label]

    @property
    def waiting_for_choice(self) -> bool:
        return self._pending is not None

    # ---- running -----------------------------------------------------------
    def next(self) -> Step:
        """Run until something needs presenting and return it."""
        if self.pc is None:
            raise StoryRuntimeError("call start() before next()")
        if self._pending is not None:
            raise StoryRuntimeError("a choice is waiting; call choose() before next()")
        if self.finished:
            return self._emit(End())

        code = self.story.code
        for _ in range(self.MAX_SILENT_INSTRUCTIONS):
            if self.pc >= len(code):
                self.finished = True
                return self._emit(End())
            for label in self.story.labels_at(self.pc):
                self.visited.add(label)
            instruction = code[self.pc]
            self.pc += 1
            try:
                step = self._execute(instruction)
            except ExpressionEvalError as exc:
                raise StoryRuntimeError(f"{self.story.name}:{instruction.line}: {exc}") from exc
            if step is not None:
                return self._emit(step)
        raise StoryRuntimeError(
            f"{self.story.name}: ran {self.MAX_SILENT_INSTRUCTIONS} instructions without showing "
            "anything - is there an infinite loop in the script?"
        )

    def _env(self) -> dict[str, Any]:
        return {**self.variables, "visited": self.visited}

    def _execute(self, ins: Any) -> Step | None:
        """Run one instruction; returns a step if the game has something to show."""
        if isinstance(ins, ISay):
            text = interpolate(ins.text, self.variables)
            self.history.append((ins.speaker, text))
            del self.history[: -self.history_limit]
            return Say(ins.speaker, text)
        if isinstance(ins, ICommand):
            return Command(ins.name, ins.args)
        if isinstance(ins, ISet):
            value = ins.value.evaluate(self._env())
            if ins.op == "=":
                self.variables[ins.name] = value
            else:
                if ins.name not in self.variables:
                    raise ExpressionEvalError(f"unknown variable {ins.name!r}")
                try:
                    self.variables[ins.name] = _ARITHMETIC[ins.op](self.variables[ins.name], value)
                except ZeroDivisionError as exc:
                    raise ExpressionEvalError("division by zero") from exc
                except TypeError as exc:
                    raise ExpressionEvalError(f"type error in 'set {ins.name} {ins.op} ...': {exc}") from exc
            return None
        if isinstance(ins, IJump):
            self.pc = ins.target
            return None
        if isinstance(ins, IJumpIfFalse):
            if not ins.cond.evaluate(self._env()):
                self.pc = ins.target
            return None
        if isinstance(ins, IMenu):
            env = self._env()
            options = tuple(
                ChoiceOption(interpolate(o.text, self.variables), o.target)
                for o in ins.options
                if o.cond is None or o.cond.evaluate(env)
            )
            if not options:
                raise StoryRuntimeError(
                    f"{self.story.name}:{ins.line}: every option of this menu is hidden by its condition"
                )
            self._pending = Choice(options)
            return self._pending
        if isinstance(ins, IEnd):
            self.finished = True
            return End()
        raise StoryRuntimeError(f"unknown instruction {ins!r}")  # pragma: no cover

    def _emit(self, step: Step) -> Step:
        if isinstance(step, (Say, Choice)):
            self.current = step
        return step

    def choose(self, index: int) -> None:
        """Pick option ``index`` of the pending choice."""
        if self._pending is None:
            raise StoryRuntimeError("there is no choice to make")
        if not 0 <= index < len(self._pending.options):
            raise StoryRuntimeError(f"choice index {index} out of range")
        option = self._pending.options[index]
        self.history.append((None, f"> {option.text}"))
        del self.history[: -self.history_limit]
        self.pc = option.target
        self._pending = None
        self.current = None

    # ---- saving ------------------------------------------------------------
    def save_state(self) -> dict[str, Any]:
        """JSON-serialisable snapshot. Only makes sense at a blocking step (Say/Choice)."""
        return {
            "version": SAVE_VERSION,
            "fingerprint": self.story.fingerprint,
            "pc": self.pc,
            "variables": self.variables,
            "visited": sorted(self.visited),
            "history": [[s, t] for s, t in self.history],
            "finished": self.finished,
            "current": step_to_dict(self.current) if self.current is not None else None,
        }

    def load_state(self, data: dict[str, Any], *, force: bool = False) -> None:
        if data.get("version") != SAVE_VERSION:
            raise SaveIncompatibleError(f"unsupported story save version {data.get('version')!r}")
        if data.get("fingerprint") != self.story.fingerprint and not force:
            raise SaveIncompatibleError(
                "this save was made with a different version of the story script; "
                "loading it could jump to the wrong place"
            )
        pc = data["pc"]
        if not isinstance(pc, int) or not 0 <= pc <= len(self.story.code):
            raise SaveIncompatibleError("save refers to a position outside the script")
        self.pc = pc
        self.variables = dict(data["variables"])
        self.visited = set(data["visited"])
        self.history = [(s, t) for s, t in data["history"]]
        self.finished = bool(data["finished"])
        current = data.get("current")
        self.current = step_from_dict(current) if current else None
        self._pending = self.current if isinstance(self.current, Choice) else None
