"""Command-line tools:  python -m swyft check path/to/story.swy

``check`` compiles a script and reports errors with line numbers - no window, no
pygame needed - so it works in CI or as an editor save-hook.
"""

from __future__ import annotations

import sys

from .story import ScriptError, load_story


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "check":
        print("usage: python -m swyft check <script.swy> [more scripts...]")
        return 2
    status = 0
    for path in argv[1:]:
        try:
            story = load_story(path)
        except ScriptError as exc:
            print(f"error: {exc}")
            status = 1
        except OSError as exc:
            print(f"error: {exc}")
            status = 1
        else:
            print(f"{path}: OK ({len(story.labels)} labels, {len(story.code)} instructions, "
                  f"{len(story.defaults)} variables, {len(story.characters)} characters)")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
