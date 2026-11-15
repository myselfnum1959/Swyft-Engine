"""Exceptions raised by the story system."""

from __future__ import annotations


class StoryError(Exception):
    """Base class for everything the story package raises."""


class ScriptError(StoryError):
    """A mistake in a script, reported with file and line number."""

    def __init__(self, message: str, line: int | None = None, source: str = "<script>"):
        self.message = message
        self.line = line
        self.source = source
        where = f"{source}:{line}" if line is not None else source
        super().__init__(f"{where}: {message}")


class ExpressionError(StoryError, ValueError):
    """An expression that is invalid or uses something not allowed (compile time)."""


class StoryRuntimeError(StoryError):
    """Something went wrong while a story was running."""


class ExpressionEvalError(StoryRuntimeError):
    """An expression failed while evaluating (unknown variable, divide by zero...)."""


class SaveIncompatibleError(StoryError):
    """A save was made with a different version of the script."""
