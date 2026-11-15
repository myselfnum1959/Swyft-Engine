"""Swyft story system: scripting language, runner and (optionally) a ready-made scene."""

from .errors import (
    ExpressionError,
    SaveIncompatibleError,
    ScriptError,
    StoryError,
    StoryRuntimeError,
)
from .expr import Expression
from .model import Character, Choice, ChoiceOption, Command, End, Say, Story
from .parser import BUILTIN_COMMANDS, load_story, parse_story
from .runner import StoryRunner

__all__ = [
    "BUILTIN_COMMANDS",
    "Character",
    "Choice",
    "ChoiceOption",
    "Command",
    "End",
    "Expression",
    "ExpressionError",
    "SaveIncompatibleError",
    "Say",
    "ScriptError",
    "Story",
    "StoryError",
    "StoryRunner",
    "StoryRuntimeError",
    "load_story",
    "parse_story",
    "StoryScene",
]


def __getattr__(name: str):
    # StoryScene needs pygame; load it only when asked for so the rest of this
    # package (parser, runner) works in headless tools like a script linter.
    if name == "StoryScene":
        from .scene import StoryScene

        return StoryScene
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
