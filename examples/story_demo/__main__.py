"""Run with:  python -m examples.story_demo   (from the repository root)

Controls: Enter / Space / click = continue, Up/Down + Enter or mouse = choose,
Hold Ctrl = fast-forward, F5 / F9 = quick save / load, F3 = debug overlay.
"""

import logging
from pathlib import Path

from swyft import Engine
from swyft.story import StoryScene, load_story

HERE = Path(__file__).parent


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    engine = Engine("The Last Ferry", 960, 540, asset_path=HERE / "assets")
    engine.push_scene(StoryScene(load_story(HERE / "story.swy")))
    engine.run()


if __name__ == "__main__":
    main()
