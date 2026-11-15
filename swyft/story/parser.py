"""Compile Swyft story scripts (``.swy``) into a :class:`~swyft.story.model.Story`.

The language is line-oriented and indentation-based::

    character mira "Mira" color "#7fd1ff"
    default courage = 0

    label start:
        scene harbor
        show mira calm at left
        mira "You're late."
        menu:
            "Apologise":
                set courage += 1
            "Shrug" if courage > 2:
                jump rude_end
        if courage >= 1:
            mira "Fine. Hop on."
        else:
            "She doesn't answer."

See docs/SCRIPT_REFERENCE.md for the full reference.

Implementation: a single-pass recursive-descent parser that emits instructions
directly, back-patching jump targets (``if``/``menu`` need to jump forward to code
that hasn't been emitted yet). Labels are resolved in a final fix-up pass, and a
validation pass then reports typos (unknown labels, variables or speakers) with
line numbers - so authors find mistakes when loading, not mid-playthrough.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import ExpressionError, ScriptError
from .expr import Expression, interpolation_names
from .model import (
    Character,
    ICommand,
    IEnd,
    IJump,
    IJumpIfFalse,
    IMenu,
    IMenuOption,
    ISay,
    ISet,
    Story,
)

#: Presentation commands every script may use. The game decides what they do.
BUILTIN_COMMANDS = frozenset({"scene", "show", "hide", "music", "sound", "wait", "shake"})
_STRUCTURAL = frozenset({"label", "default", "character", "set", "jump", "end", "menu", "if", "elif", "else"})
_RESERVED_NAMES = _STRUCTURAL | {"visited"}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SET = re.compile(r"set\s+([A-Za-z_][A-Za-z0-9_]*)\s*(\+=|-=|\*=|/=|=)(?!=)\s*(.+)")
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


@dataclass
class _Line:
    no: int
    indent: int
    text: str


# =============================================================================
# Lexical helpers
# =============================================================================


def _strip_comment(text: str) -> str:
    """Remove a trailing ``# comment`` while respecting ``#`` inside quotes."""
    out: list[str] = []
    in_string = escaped = False
    for ch in text:
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == "#":
                break
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _read_string(text: str, pos: int) -> tuple[str, int]:
    """Read a double-quoted string starting at ``text[pos]``; returns (value, next_pos)."""
    i = pos + 1
    buf: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 1
            if i >= len(text):
                break
            buf.append(_ESCAPES.get(text[i], "\\" + text[i]))
        elif ch == '"':
            return "".join(buf), i + 1
        else:
            buf.append(ch)
        i += 1
    raise ValueError("unterminated string (missing closing quote)")


def _coerce(word: str) -> Any:
    for cast in (int, float):
        try:
            return cast(word)
        except ValueError:
            pass
    return word


def _tokenize(text: str) -> list[Any]:
    """Split command arguments: quoted strings stay strings, bare numbers become numbers."""
    tokens: list[Any] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
        elif ch == '"':
            value, i = _read_string(text, i)
            tokens.append(value)
        else:
            j = i
            while j < len(text) and not text[j].isspace() and text[j] != '"':
                j += 1
            tokens.append(_coerce(text[i:j]))
            i = j
    return tokens


def _preprocess(source: str, name: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ScriptError("tabs are not allowed for indentation; use spaces", number, name)
        text = _strip_comment(raw).rstrip()
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip(" "))
        lines.append(_Line(number, indent, text.strip()))
    return lines


# =============================================================================
# Parser
# =============================================================================


class _Parser:
    def __init__(self, lines: list[_Line], name: str, commands: frozenset[str]):
        self.lines = lines
        self.name = name
        self.commands = commands
        self.pos = 0
        self.code: list[Any] = []
        self.labels: dict[str, int] = {}
        self.defaults: dict[str, Any] = {}
        self.characters: dict[str, Character] = {}
        self._jumps: list[IJump] = []
        self._speakers: list[tuple[str, int]] = []
        self._assigned: set[str] = set()
        self._uses: list[tuple[str, int]] = []

    # ---- error helper ------------------------------------------------------
    def fail(self, message: str, line: int | None = None) -> ScriptError:
        return ScriptError(message, line, self.name)

    def _expr(self, source: str, line: int) -> Expression:
        try:
            expression = Expression(source)
        except ExpressionError as exc:
            raise self.fail(str(exc), line) from exc
        for name in expression.names:
            self._uses.append((name, line))
        return expression

    def _here(self) -> int:
        return len(self.code)

    def _emit(self, instruction: Any) -> Any:
        self.code.append(instruction)
        return instruction

    # ---- top level ---------------------------------------------------------
    def parse(self) -> Story:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if line.indent != 0:
                raise self.fail("unexpected indentation", line.no)
            keyword = self._keyword(line.text)
            if keyword == "label":
                self._label(line)
            elif keyword == "default":
                self._default(line)
            elif keyword == "character":
                self._character(line)
            else:
                raise self.fail(
                    "only 'label', 'default' and 'character' may appear at the top level "
                    "(did you forget to put this inside a label?)",
                    line.no,
                )
        self._emit(IEnd())  # running off the end of the script ends the story
        self._resolve_jumps()
        self._validate()
        return Story(self.code, self.labels, self.defaults, self.characters, name=self.name)

    @staticmethod
    def _keyword(text: str) -> str | None:
        match = _IDENT.match(text)
        return match.group(0) if match else None

    def _child_indent(self, parent: _Line, what: str) -> int:
        if self.pos >= len(self.lines) or self.lines[self.pos].indent <= parent.indent:
            raise self.fail(f"expected an indented block after {what}", parent.no)
        return self.lines[self.pos].indent

    def _block(self, indent: int) -> None:
        while self.pos < len(self.lines):
            line = self.lines[self.pos]
            if line.indent < indent:
                return
            if line.indent > indent:
                raise self.fail("unexpected indentation", line.no)
            self._statement()

    # ---- top-level statements ---------------------------------------------
    def _label(self, line: _Line) -> None:
        match = re.fullmatch(r"label\s+([A-Za-z_][A-Za-z0-9_]*)\s*:", line.text)
        if not match:
            raise self.fail("expected: label name:", line.no)
        name = match.group(1)
        if name in self.labels:
            raise self.fail(f"label {name!r} is defined twice", line.no)
        self.labels[name] = self._here()
        self.pos += 1
        self._block(self._child_indent(line, f"label {name!r}"))

    def _default(self, line: _Line) -> None:
        match = re.fullmatch(r"default\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)", line.text)
        if not match:
            raise self.fail("expected: default name = value", line.no)
        name, source = match.groups()
        if name in _RESERVED_NAMES:
            raise self.fail(f"{name!r} is a reserved word and can't be a variable", line.no)
        expression = self._expr(source, line.no)
        if expression.names:
            raise self.fail("a default value can't refer to other variables", line.no)
        self.defaults[name] = expression.evaluate({})
        self._assigned.add(name)
        self.pos += 1

    def _character(self, line: _Line) -> None:
        try:
            tokens = _tokenize(line.text[len("character"):])
        except ValueError as exc:
            raise self.fail(str(exc), line.no) from exc
        # Expected: <id> "<Display name>" [color "#rrggbb"]
        if len(tokens) not in (2, 4) or (len(tokens) == 4 and tokens[2] != "color"):
            raise self.fail('expected: character id "Display Name" [color "#rrggbb"]', line.no)
        ident, display = str(tokens[0]), tokens[1]
        color = tokens[3] if len(tokens) == 4 else None
        if not _IDENT.fullmatch(ident) or ident in _RESERVED_NAMES or ident in self.commands:
            raise self.fail(f"{ident!r} is not a valid character id (reserved word or bad name)", line.no)
        if color is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)):
            raise self.fail('colour must look like "#rrggbb"', line.no)
        self.characters[ident] = Character(ident, str(display), None if color is None else str(color))
        self.pos += 1

    # ---- statements inside labels -----------------------------------------
    def _statement(self) -> None:
        line = self.lines[self.pos]
        text = line.text
        try:
            self._dispatch(line, text)
        except ValueError as exc:  # raised by _read_string / _tokenize
            raise self.fail(str(exc), line.no) from exc

    def _dispatch(self, line: _Line, text: str) -> None:
        if text.startswith('"'):
            self._say(line, None, text)
            return
        keyword = self._keyword(text)
        if keyword == "set":
            self._set(line)
        elif keyword == "jump":
            self._jump(line)
        elif keyword == "end":
            if text != "end":
                raise self.fail("'end' takes no arguments", line.no)
            self._emit(IEnd(line=line.no))
            self.pos += 1
        elif keyword == "menu":
            self._menu(line)
        elif keyword == "if":
            self._if(line)
        elif keyword in ("elif", "else"):
            raise self.fail(f"'{keyword}' without a matching 'if'", line.no)
        elif keyword in ("label", "default", "character"):
            raise self.fail(f"'{keyword}' is only allowed at the top level, not inside a block", line.no)
        elif keyword in self.commands:
            assert keyword is not None
            args = _tokenize(text[len(keyword):])
            self._emit(ICommand(keyword, tuple(args), line=line.no))
            self.pos += 1
        elif keyword is not None and text[len(keyword):].lstrip().startswith('"'):
            self._say(line, keyword, text[len(keyword):].lstrip())
        else:
            known = sorted(self.commands | _STRUCTURAL)
            hint = difflib.get_close_matches(keyword or "", known, n=1)
            suffix = f" - did you mean '{hint[0]}'?" if hint else ""
            raise self.fail(f"don't understand {text!r}{suffix}", line.no)

    def _say(self, line: _Line, speaker: str | None, quoted: str) -> None:
        value, end = _read_string(quoted, 0)
        if quoted[end:].strip():
            raise self.fail("unexpected text after the closing quote", line.no)
        for name in interpolation_names(value):
            self._uses.append((name, line.no))
        if speaker is not None:
            self._speakers.append((speaker, line.no))
        self._emit(ISay(speaker, value, line=line.no))
        self.pos += 1

    def _set(self, line: _Line) -> None:
        match = _SET.fullmatch(line.text)
        if not match:
            raise self.fail("expected: set name = value   (or +=, -=, *=, /=)", line.no)
        name, op, source = match.groups()
        if name in _RESERVED_NAMES:
            raise self.fail(f"{name!r} is a reserved word and can't be assigned", line.no)
        self._assigned.add(name)
        if op != "=":
            self._uses.append((name, line.no))
        self._emit(ISet(name, op, self._expr(source, line.no), line=line.no))
        self.pos += 1

    def _jump(self, line: _Line) -> None:
        match = re.fullmatch(r"jump\s+([A-Za-z_][A-Za-z0-9_]*)", line.text)
        if not match:
            raise self.fail("expected: jump label_name", line.no)
        jump = self._emit(IJump(label=match.group(1), line=line.no))
        self._jumps.append(jump)
        self.pos += 1

    def _if(self, line: _Line) -> None:
        indent = line.indent
        end_jumps: list[IJump] = []
        current = line
        keyword = "if"
        while True:
            if not current.text.endswith(":"):
                raise self.fail(f"'{keyword}' line must end with ':'", current.no)
            condition = current.text[len(keyword):-1].strip()
            if not condition:
                raise self.fail(f"'{keyword}' needs a condition", current.no)
            jump_if_false = self._emit(IJumpIfFalse(self._expr(condition, current.no), line=current.no))
            self.pos += 1
            self._block(self._child_indent(current, f"'{keyword}'"))

            nxt = self.lines[self.pos] if self.pos < len(self.lines) else None
            same_level = nxt is not None and nxt.indent == indent
            if same_level and self._keyword(nxt.text) == "elif":
                end_jumps.append(self._emit(IJump(line=current.no)))
                jump_if_false.target = self._here()
                current, keyword = nxt, "elif"
                continue
            if same_level and nxt.text == "else:":
                end_jumps.append(self._emit(IJump(line=current.no)))
                jump_if_false.target = self._here()
                self.pos += 1
                self._block(self._child_indent(nxt, "'else'"))
            else:
                jump_if_false.target = self._here()
            break
        for jump in end_jumps:
            jump.target = self._here()

    def _menu(self, line: _Line) -> None:
        if line.text != "menu:":
            raise self.fail("expected: menu:", line.no)
        self.pos += 1
        option_indent = self._child_indent(line, "'menu:'")
        menu = self._emit(IMenu([], line=line.no))
        end_jumps: list[IJump] = []
        while self.pos < len(self.lines) and self.lines[self.pos].indent == option_indent:
            option_line = self.lines[self.pos]
            if not option_line.text.startswith('"'):
                raise self.fail('menu options look like:  "Text":   or   "Text" if condition:', option_line.no)
            text, end = _read_string(option_line.text, 0)
            rest = option_line.text[end:].strip()
            if not rest.endswith(":"):
                raise self.fail("a menu option must end with ':'", option_line.no)
            rest = rest[:-1].strip()
            condition = None
            if rest.startswith("if ") or rest == "if":
                condition = self._expr(rest[2:].strip(), option_line.no)
            elif rest:
                raise self.fail("expected ':' or 'if <condition>:' after the option text", option_line.no)
            for name in interpolation_names(text):
                self._uses.append((name, option_line.no))
            option = IMenuOption(text, condition, target=self._here())
            menu.options.append(option)
            self.pos += 1
            self._block(self._child_indent(option_line, "a menu option"))
            end_jumps.append(self._emit(IJump(line=option_line.no)))
        if not menu.options:
            raise self.fail("a menu needs at least one option", line.no)
        for jump in end_jumps:
            jump.target = self._here()

    # ---- post-processing ---------------------------------------------------
    def _resolve_jumps(self) -> None:
        for jump in self._jumps:
            assert jump.label is not None
            if jump.label not in self.labels:
                hint = difflib.get_close_matches(jump.label, list(self.labels), n=1)
                suffix = f" - did you mean {hint[0]!r}?" if hint else ""
                raise self.fail(f"jump to unknown label {jump.label!r}{suffix}", jump.line)
            jump.target = self.labels[jump.label]

    def _validate(self) -> None:
        for name, line in self._uses:
            if name not in self._assigned and name != "visited":
                hint = difflib.get_close_matches(name, sorted(self._assigned), n=1)
                suffix = f" - did you mean {hint[0]!r}?" if hint else ""
                raise self.fail(
                    f"variable {name!r} is never defined (add 'default {name} = ...'){suffix}", line
                )
        for speaker, line in self._speakers:
            if speaker not in self.characters:
                raise self.fail(
                    f"speaker {speaker!r} is not declared (add: character {speaker} \"Name\")", line
                )


# =============================================================================
# Public API
# =============================================================================


def parse_story(source: str, name: str = "<script>", extra_commands: Iterable[str] = ()) -> Story:
    """Compile script text. Raises :class:`ScriptError` (with line number) on mistakes."""
    commands = BUILTIN_COMMANDS | frozenset(extra_commands)
    return _Parser(_preprocess(source, name), name, commands).parse()


def load_story(path: str | Path, extra_commands: Iterable[str] = ()) -> Story:
    path = Path(path)
    return parse_story(path.read_text(encoding="utf-8"), name=path.name, extra_commands=extra_commands)
