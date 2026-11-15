"""Math, timing, events, input, camera, animation, text, saves."""

import json
import math

import pytest

from swyft import AABB, Animation, Animator, Camera2D, EventBus, FixedTimestep, InputManager, SaveManager, Typewriter, Vec2, wrap_text
from swyft.save import CorruptSave, SaveError, SaveNotFound
from swyft.text import reveal_lines


# ---- math -------------------------------------------------------------------
def test_vec2_arithmetic_and_immutability():
    a, b = Vec2(1, 2), Vec2(3, 4)
    assert a + b == Vec2(4, 6)
    assert b - a == Vec2(2, 2)
    assert a * 3 == Vec2(3, 6) and 3 * a == Vec2(3, 6)
    assert b.length() == 5
    assert Vec2(0, 0).normalized() == Vec2(0, 0)
    assert a.lerp(b, 0.5) == Vec2(2, 3)
    with pytest.raises(Exception):
        a.x = 9  # frozen


def test_aabb_touching_is_not_intersecting():
    a = AABB(0, 0, 10, 10)
    assert a.intersects(AABB(5, 5, 10, 10))
    assert not a.intersects(AABB(10, 0, 10, 10))  # shares an edge only
    a.bottom = 50
    assert a.y == 40  # setters move, never resize
    assert a.h == 10


# ---- fixed timestep ---------------------------------------------------------
def test_fixed_timestep_counts_whole_steps():
    ts = FixedTimestep(step=1 / 60)
    total = sum(ts.advance(1 / 60) for _ in range(60))
    assert total == 60  # float error must not lose a step


def test_fixed_timestep_clamps_long_stalls():
    ts = FixedTimestep(step=0.01, max_frame_time=0.1)
    assert ts.advance(5.0) == 10  # not 500


def test_fixed_timestep_accumulates_fractions():
    ts = FixedTimestep(step=0.1)
    assert ts.advance(0.06) == 0
    assert ts.advance(0.06) == 1
    assert 0 <= ts.alpha < 1


# ---- events -----------------------------------------------------------------
def test_event_bus_subscribe_once_unsubscribe():
    bus, seen = EventBus(), []
    unsub = bus.subscribe("hit", lambda n: seen.append(n))
    bus.once("hit", lambda n: seen.append(f"once{n}"))
    assert bus.emit("hit", 1) == 2
    assert bus.emit("hit", 2) == 1
    unsub()
    assert bus.emit("hit", 3) == 0
    assert seen == [1, "once1", 2]


def test_event_bus_handler_can_unsubscribe_during_emit():
    bus, calls = EventBus(), []

    def handler():
        calls.append(1)
        unsub()

    unsub = bus.subscribe("e", handler)
    bus.emit("e")
    bus.emit("e")
    assert calls == [1]


# ---- input ------------------------------------------------------------------
def test_input_edges_are_per_tick():
    inp = InputManager()
    inp.bind("jump", "space")
    inp.key_down("space")
    assert inp.down("jump") and not inp.pressed("jump")  # edge not latched yet
    inp.tick()
    assert inp.pressed("jump")
    inp.tick()
    assert inp.down("jump") and not inp.pressed("jump")  # held, no new edge
    inp.key_up("space")
    inp.tick()
    assert inp.released("jump") and not inp.down("jump")


def test_input_quick_tap_between_ticks_is_not_lost():
    inp = InputManager()
    inp.bind("confirm", "return")
    inp.key_down("return")
    inp.key_up("return")  # pressed and released before the next tick
    inp.tick()
    assert inp.pressed("confirm") and inp.released("confirm")
    assert not inp.down("confirm")


def test_input_axis_and_rebind():
    inp = InputManager()
    inp.bind("left", "a")
    inp.bind("right", "d")
    inp.key_down("d")
    assert inp.axis("left", "right") == 1
    inp.key_down("a")
    assert inp.axis("left", "right") == 0
    inp.rebind("right", "l")
    assert inp.axis("left", "right") == -1  # 'd' no longer counts


# ---- camera -----------------------------------------------------------------
def test_camera_follow_snap_and_bounds():
    cam = Camera2D(800, 600)
    cam.bounds = AABB(0, 0, 1600, 600)
    cam.follow(Vec2(100, 300))
    cam.snap_to_target()
    assert cam.position == Vec2(0, 0)  # clamped at left edge
    cam.follow(Vec2(1500, 300))
    cam.snap_to_target()
    assert cam.position.x == 800  # clamped at right edge


def test_camera_smoothing_is_frame_rate_independent():
    def settle(dt, seconds=0.5):
        cam = Camera2D(100, 100)
        cam.smoothing = 8
        cam.follow(Vec2(1050, 50))  # desired x = 1000
        for _ in range(round(seconds / dt)):
            cam.update(dt)
        return cam.position.x

    assert settle(1 / 30) == pytest.approx(settle(1 / 240), rel=1e-6)


def test_camera_world_screen_roundtrip_and_shake_decay():
    cam = Camera2D(800, 600, seed=1)
    cam.position = Vec2(100, 50)
    p = Vec2(130, 90)
    assert cam.screen_to_world(cam.world_to_screen(p)) == p
    cam.shake(0.2, 10)
    cam.update(0.1)
    assert cam.offset != Vec2(0, 0)
    cam.update(0.2)
    assert cam.offset == Vec2(0, 0)


# ---- animation --------------------------------------------------------------
def test_animation_loops_and_oneshot_finishes_once():
    anim = Animator()
    anim.add(Animation("walk", (0, 1, 2), fps=10))
    anim.add(Animation("hit", (5, 6), fps=10, loop=False))
    anim.play("walk")
    anim.update(0.25)
    assert anim.frame == 2
    anim.update(0.1)
    assert anim.frame == 0  # looped

    finished = []
    anim.on_finish = finished.append
    anim.play("hit")
    anim.update(0.05)
    assert anim.frame == 5 and not anim.finished
    anim.update(0.5)
    anim.update(0.5)
    assert anim.finished and anim.frame == 6
    assert finished == ["hit"]  # callback fired exactly once


def test_animator_play_same_clip_does_not_restart():
    anim = Animator()
    anim.add(Animation("walk", (0, 1, 2), fps=10))
    anim.play("walk")
    anim.update(0.15)
    anim.play("walk")  # called every frame by game code
    assert anim.frame == 1
    with pytest.raises(KeyError):
        anim.play("nope")


# ---- text -------------------------------------------------------------------
def measure(s):
    return len(s)  # 1 unit per character


def test_wrap_text_basic_and_newlines():
    assert wrap_text("the quick brown fox", measure, 10) == ["the quick", "brown fox"]
    assert wrap_text("a\nb", measure, 10) == ["a", "b"]
    assert wrap_text("", measure, 10) == [""]


def test_wrap_text_splits_overlong_words():
    lines = wrap_text("abcdefghij", measure, 4)
    assert lines == ["abcd", "efgh", "ij"]
    assert all(len(line) <= 4 for line in lines)


def test_reveal_lines():
    lines = ["hello", "world"]
    assert reveal_lines(lines, 3) == ["hel"]
    assert reveal_lines(lines, 8) == ["hello", "wo"]  # 1 char reserved for the removed space
    assert reveal_lines(lines, 99) == lines


def test_typewriter_reveals_pauses_and_skips():
    tw = Typewriter("Hi. Yo", chars_per_second=10)
    assert tw.visible == "" or tw.visible == "H"
    tw.update(0.15)
    assert tw.visible.startswith("Hi")
    # The full stop ends a word, so there is a pause before " Yo".
    tw.update(0.1)
    assert not tw.done
    tw.skip()
    assert tw.done and tw.visible == "Hi. Yo"


def test_typewriter_no_pause_inside_numbers_and_instant_mode():
    slow = Typewriter("3.14", chars_per_second=10)
    slow.update(0.35)
    assert slow.visible == "3.14"  # no pause after the '.'
    instant = Typewriter("abc", chars_per_second=0)
    assert instant.done


# ---- saves ------------------------------------------------------------------
def test_save_roundtrip_list_delete(tmp_path):
    saves = SaveManager(tmp_path / "saves")
    saves.save("slot1", {"hp": 3, "name": "Zoë"}, label="Chapter 1")
    assert saves.exists("slot1")
    assert saves.load("slot1") == {"hp": 3, "name": "Zoë"}
    assert saves.list_slots()[0]["label"] == "Chapter 1"
    saves.delete("slot1")
    with pytest.raises(SaveNotFound):
        saves.load("slot1")


def test_save_rejects_path_traversal_and_corruption(tmp_path):
    saves = SaveManager(tmp_path)
    with pytest.raises(SaveError):
        saves.save("../evil", {})
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(CorruptSave):
        saves.load("bad")
    (tmp_path / "future.json").write_text(json.dumps({"format": 999, "data": {}}))
    with pytest.raises(CorruptSave):
        saves.load("future")


def test_save_is_atomic_leaves_no_temp_files(tmp_path):
    saves = SaveManager(tmp_path)
    saves.save(1, {"a": 1})
    saves.save(1, {"a": 2})
    assert saves.load(1) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["1.json"]
