"""End-to-end smoke tests: real Engine + StoryScene running headless.

Skipped automatically when pygame isn't installed. Pure-logic tests live in the
other test files and never need pygame.
"""

import pytest

pytest.importorskip("pygame")

from swyft import Engine, PhysicsEntity, Scene, StaticEntity  # noqa: E402
from swyft.story import StoryScene, parse_story  # noqa: E402

SCRIPT = """
character a "Alice" color "#ff8800"
default n = 0
label start:
    scene park
    show a happy at left
    a "Hello."
    menu:
        "Yes":
            set n += 1
        "No":
            set n -= 1
    a "Number: {n}"
"""


def make_engine(tmp_path):
    return Engine("Smoke Test", 320, 240, headless=True, fps_cap=0, asset_path=tmp_path / "assets", save_dir=tmp_path / "saves")


def frame(engine, *keys):
    """One tick + render with the given keys tapped."""
    for k in keys:
        engine.input.key_down(k)
    engine._tick(engine.config.fixed_dt)
    for k in keys:
        engine.input.key_up(k)
    engine._render()


def test_story_scene_plays_choice_and_ends(tmp_path):
    engine = make_engine(tmp_path)
    scene = StoryScene(parse_story(SCRIPT))
    engine.push_scene(scene)
    frame(engine)
    assert scene._say.text == "Hello."
    frame(engine, "return")  # first press completes the typewriter...
    frame(engine, "return")  # ...second advances
    assert scene._choice is not None
    frame(engine)  # a render pass lets the scene compute button rectangles
    frame(engine, "down")
    frame(engine, "return")
    assert scene.runner.variables["n"] == -1
    assert scene._say.text == "Number: -1"
    frame(engine, "return")
    frame(engine, "return")
    assert scene._ended
    engine.shutdown()


def test_quick_save_and_load_restores_state_and_stage(tmp_path):
    engine = make_engine(tmp_path)
    scene = StoryScene(parse_story(SCRIPT))
    engine.push_scene(scene)
    frame(engine)
    frame(engine, "f5")
    assert engine.saves.exists("quick")
    frame(engine, "return")
    frame(engine, "return")
    assert scene._choice is not None  # moved on
    scene.sprites.clear()
    frame(engine, "f9")
    assert scene._say.text == "Hello."
    assert "a" in scene.sprites and scene.background == "park"
    engine.shutdown()


def test_scene_stack_push_pop_and_run_exits_when_empty(tmp_path):
    engine = make_engine(tmp_path)
    log = []

    class Probe(Scene):
        def on_enter(self): log.append(f"enter {self.name}")
        def on_exit(self): log.append(f"exit {self.name}")
        def on_pause(self): log.append(f"pause {self.name}")
        def on_resume(self): log.append(f"resume {self.name}")

    engine.push_scene(Probe("base"))
    engine.push_scene(Probe("overlay"))
    engine.pop_scene()
    engine.pop_scene()
    assert log == ["enter base", "pause base", "enter overlay", "exit overlay", "resume base", "exit base"]
    with pytest.raises(RuntimeError):
        engine.run()  # nothing to run
    engine.shutdown()


def test_run_loop_steps_physics_and_returns_normally(tmp_path):
    engine = make_engine(tmp_path)
    scene = engine.scene  # v0.1-style: creates a default scene
    scene.add_entity(StaticEntity(0, 200, 320, 40))
    box = scene.add_entity(PhysicsEntity(50, 0, 20, 20))
    engine.run(max_frames=5)  # must not call sys.exit
    assert box.position.y > 0
