import json

import pytest

from swyft.story import (
    Choice,
    Command,
    End,
    Expression,
    ExpressionError,
    SaveIncompatibleError,
    Say,
    ScriptError,
    StoryRunner,
    StoryRuntimeError,
    parse_story,
)
from swyft.story.errors import ExpressionEvalError
from swyft.story.expr import interpolate

HEADER = 'character mira "Mira" color "#7fd1ff"\ncharacter bob "Bob"\n'


def run_all(source, choices=(), label="start"):
    """Drive a story to the end; returns every step. ``choices`` are picked in order."""
    story = parse_story(source)
    runner = StoryRunner(story)
    runner.start(label)
    picks = iter(choices)
    steps = []
    for _ in range(500):
        step = runner.next()
        steps.append(step)
        if isinstance(step, Choice):
            runner.choose(next(picks))
        if isinstance(step, End):
            return steps, runner
    raise AssertionError("story did not end")


def texts(steps):
    return [s.text for s in steps if isinstance(s, Say)]


# ============================================================================
# Expressions
# ============================================================================
def test_expression_arithmetic_comparison_logic():
    env = {"a": 3, "b": 4, "name": "Zed"}
    assert Expression("a + b * 2").evaluate(env) == 11
    assert Expression("a < b < 10").evaluate(env) is True  # chained comparison
    assert Expression("a > b or name == 'Zed'").evaluate(env) is True
    assert Expression("not (a == 3)").evaluate(env) is False
    assert Expression("-a").evaluate(env) == -3
    assert Expression("'e' in name or name in ['Zed', 'Amy']").evaluate(env) is True
    assert Expression("true and not false").evaluate({}) is True
    assert Expression("7 // 2").evaluate({}) == 3
    assert Expression("7 % 4").evaluate({}) == 3


def test_expression_short_circuits():
    # 'boom' is undefined: evaluating it would raise, so short-circuit must skip it.
    assert Expression("false and boom").evaluate({}) is False
    assert Expression("true or boom").evaluate({}) is True


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('echo pwned')",  # call
        "().__class__.__bases__",  # attribute access
        "open('/etc/passwd')",  # call
        "[x for x in range(9)]",  # comprehension
        "lambda: 1",  # lambda
        "a ** 99999999",  # power is deliberately not allowed
        "a[0]",  # subscript
        "a if b else c",  # ternary
        "x := 5",  # walrus
        "f'{a}'",  # f-string
        "a is b",  # identity comparison
    ],
)
def test_expression_rejects_anything_unsafe(source):
    with pytest.raises(ExpressionError):
        Expression(source)


def test_expression_syntax_error_and_runtime_errors():
    with pytest.raises(ExpressionError):
        Expression("1 +")
    with pytest.raises(ExpressionEvalError, match="unknown variable"):
        Expression("ghost + 1").evaluate({})
    with pytest.raises(ExpressionEvalError, match="division by zero"):
        Expression("1 / zero").evaluate({"zero": 0})
    with pytest.raises(ExpressionEvalError, match="type error"):
        Expression("'a' + 1").evaluate({})


def test_expression_collects_names():
    assert Expression("a + b > c and true").names == {"a", "b", "c"}


def test_interpolation_and_brace_escapes():
    assert interpolate("Hi {name}, {{literal}}", {"name": "Zed"}) == "Hi Zed, {literal}"
    assert interpolate("score: {n}", {"n": 3}) == "score: 3"
    with pytest.raises(ExpressionEvalError):
        interpolate("{nope}", {})


# ============================================================================
# Parser: valid programs
# ============================================================================
def test_say_narration_and_comments():
    steps, _ = run_all(HEADER + """
label start:
    # a comment line
    "Narration."          # trailing comment
    mira "Hello # not a comment"
""")
    assert steps[0] == Say(None, "Narration.")
    assert steps[1] == Say("mira", "Hello # not a comment")
    assert isinstance(steps[-1], End)


def test_string_escapes():
    steps, _ = run_all('label start:\n    "She said \\"hi\\"\\nthen left."\n')
    assert steps[0].text == 'She said "hi"\nthen left.'


def test_commands_pass_through_with_typed_args():
    steps, _ = run_all(HEADER + """
label start:
    scene harbor
    show mira calm at left
    shake 12 0.5
    music "theme song.ogg"
""")
    cmds = [s for s in steps if isinstance(s, Command)]
    assert cmds[0] == Command("scene", ("harbor",))
    assert cmds[1] == Command("show", ("mira", "calm", "at", "left"))
    assert cmds[2] == Command("shake", (12, 0.5))  # numbers are converted
    assert cmds[3] == Command("music", ("theme song.ogg",))  # quoted strings keep spaces


def test_custom_commands_can_be_registered():
    story = parse_story('label start:\n    flash "red"\n', extra_commands=["flash"])
    runner = StoryRunner(story)
    runner.start()
    assert runner.next() == Command("flash", ("red",))


def test_variables_set_and_interpolation():
    steps, runner = run_all(HEADER + """
default hp = 10
default hero = "Ana"
label start:
    set hp -= 3
    set hp *= 2
    set hero = hero + "!"
    mira "{hero} has {hp} hp. {{braces}}"
""")
    assert texts(steps) == ["Ana! has 14 hp. {braces}"]
    assert runner.variables == {"hp": 14, "hero": "Ana!"}


def test_if_elif_else_chain():
    source = HEADER + """
default n = {n}
label start:
    if n < 0:
        "negative"
    elif n == 0:
        "zero"
    elif n < 10:
        "small"
    else:
        "big"
    "after"
"""
    for n, expected in [(-5, "negative"), (0, "zero"), (7, "small"), (99, "big")]:
        steps, _ = run_all(source.replace("{n}", str(n)))
        assert texts(steps) == [expected, "after"], n


def test_if_without_else_and_nesting():
    steps, _ = run_all("""
default a = 1
default b = 0
label start:
    if a == 1:
        if b == 1:
            "both"
        else:
            "only a"
    "done"
""")
    assert texts(steps) == ["only a", "done"]


def test_jump_and_fall_through_between_labels():
    steps, _ = run_all("""
label start:
    "one"
    jump third
label second:
    "never shown"
label third:
    "three"
""")
    assert texts(steps) == ["one", "three"]


def test_end_statement_stops_early():
    steps, _ = run_all('label start:\n    "a"\n    end\n    "b"\n')
    assert texts(steps) == ["a"]


def test_menu_choice_branches_and_rejoins():
    source = HEADER + """
default trust = 0
label start:
    menu:
        "Be kind":
            set trust += 1
            mira "Thanks."
        "Be rude":
            set trust -= 1
            mira "Hmph."
    "Back together."
"""
    steps, runner = run_all(source, choices=[0])
    assert texts(steps) == ["Thanks.", "Back together."]
    assert runner.variables["trust"] == 1
    steps, runner = run_all(source, choices=[1])
    assert texts(steps) == ["Hmph.", "Back together."]
    assert runner.variables["trust"] == -1


def test_menu_option_conditions_hide_options():
    source = """
default brave = {brave}
label start:
    menu:
        "Fight" if brave:
            "You fight."
        "Run":
            "You run."
"""
    story = parse_story(source.replace("{brave}", "false"))
    runner = StoryRunner(story)
    runner.start()
    choice = runner.next()
    assert [o.text for o in choice.options] == ["Run"]
    story = parse_story(source.replace("{brave}", "true"))
    runner = StoryRunner(story)
    runner.start()
    assert [o.text for o in runner.next().options] == ["Fight", "Run"]


def test_menu_option_text_interpolates():
    story = parse_story('default who = "Bob"\nlabel start:\n    menu:\n        "Ask {who}":\n            "ok"\n')
    runner = StoryRunner(story)
    runner.start()
    assert runner.next().options[0].text == "Ask Bob"


def test_visited_tracks_labels_for_conditions():
    steps, _ = run_all("""
label start:
    jump cave
label cave:
    "In the cave."
    jump check
label check:
    if "cave" in visited:
        "You remember the cave."
    if "forest" in visited:
        "forest?!"
""")
    assert texts(steps) == ["In the cave.", "You remember the cave."]


def test_loops_are_possible_with_visible_progress():
    steps, runner = run_all("""
default i = 0
label start:
    jump loop
label loop:
    set i += 1
    "tick {i}"
    if i < 3:
        jump loop
""")
    assert texts(steps) == ["tick 1", "tick 2", "tick 3"]


def test_character_display_names():
    story = parse_story(HEADER + 'label start:\n    mira "x"\n')
    assert story.display_name("mira") == "Mira"
    assert story.characters["mira"].color == "#7fd1ff"
    assert story.display_name(None) is None


# ============================================================================
# Parser: errors carry line numbers and helpful hints
# ============================================================================
def err(source, **kw):
    with pytest.raises(ScriptError) as info:
        parse_story(source, name="t.swy", **kw)
    return info.value


def test_error_unknown_label_with_suggestion_and_line():
    e = err("label start:\n    jump finalee\nlabel finale:\n    end\n")
    assert e.line == 2
    assert "finale" in str(e) and "t.swy:2" in str(e)


def test_error_duplicate_label():
    assert err("label a:\n    end\nlabel a:\n    end\n").line == 3


def test_error_undefined_variable_with_hint():
    e = err("default courage = 0\nlabel start:\n    if couragee > 1:\n        end\n")
    assert e.line == 3 and "courage" in str(e)


def test_error_undefined_variable_in_text():
    assert err('label start:\n    "hp: {hp}"\n').line == 2


def test_error_undeclared_speaker():
    e = err('label start:\n    zed "hi"\n')
    assert "not declared" in str(e) and e.line == 2


def test_error_unknown_command_suggests_closest():
    e = err("label start:\n    sene harbor\n")
    assert "scene" in str(e)


def test_error_statement_outside_label():
    assert err('"orphan line"\n').line == 1


def test_error_missing_indented_block():
    assert err("label start:\n").line == 1
    assert err('label start:\n    if true:\n    "x"\n').line == 2


def test_error_bad_indentation_and_tabs():
    assert err('label start:\n    "a"\n      "b"\n').line == 3
    assert err('label start:\n\t"a"\n').line == 2


def test_error_else_without_if_and_unterminated_string():
    assert "without a matching" in str(err('label start:\n    else:\n        "x"\n'))
    assert "unterminated" in str(err('label start:\n    "never closed\n'))


def test_error_menu_problems():
    e = err("label start:\n    menu:\n")  # a menu with no options at all
    assert e.line == 2 and "indented block" in str(e)
    assert "must end with ':'" in str(err('label start:\n    menu:\n        "A"\n            "x"\n'))
    assert err('label start:\n    menu:\n        oops:\n            "x"\n').line == 3


def test_error_unsafe_expression_reported_with_line():
    e = err("default a = 1\nlabel start:\n    if a.real:\n        end\n")
    assert e.line == 3


def test_error_reserved_names():
    assert "reserved" in str(err("default set = 1\nlabel start:\n    end\n"))
    assert "reserved" in str(err("default visited = 1\nlabel start:\n    end\n"))
    assert err('character label "x"\nlabel start:\n    end\n').line == 1


def test_default_cannot_reference_variables():
    assert err("default a = 1\ndefault b = a + 1\nlabel start:\n    end\n").line == 2


# ============================================================================
# Runner behaviour
# ============================================================================
def test_runner_requires_start_and_known_label():
    runner = StoryRunner(parse_story('label start:\n    "x"\n'))
    with pytest.raises(StoryRuntimeError):
        runner.next()
    with pytest.raises(StoryRuntimeError):
        runner.start("nope")


def test_runner_blocks_next_while_choice_pending():
    story = parse_story('label start:\n    menu:\n        "A":\n            "a"\n')
    runner = StoryRunner(story)
    runner.start()
    assert isinstance(runner.next(), Choice)
    assert runner.waiting_for_choice
    with pytest.raises(StoryRuntimeError):
        runner.next()
    with pytest.raises(StoryRuntimeError):
        runner.choose(5)
    runner.choose(0)
    assert runner.next() == Say(None, "a")
    with pytest.raises(StoryRuntimeError):
        runner.choose(0)  # nothing pending any more


def test_runner_all_options_hidden_is_a_clear_error():
    story = parse_story('default x = 0\nlabel start:\n    menu:\n        "A" if x > 0:\n            "a"\n')
    runner = StoryRunner(story)
    runner.start()
    with pytest.raises(StoryRuntimeError, match="hidden"):
        runner.next()


def test_infinite_silent_loop_is_detected():
    story = parse_story("label start:\n    jump start\n")
    runner = StoryRunner(story)
    runner.start()
    with pytest.raises(StoryRuntimeError, match="infinite loop"):
        runner.next()


def test_runtime_expression_errors_include_script_line():
    story = parse_story("default z = 0\nlabel start:\n    set z = 1 / z\n", )
    runner = StoryRunner(story)
    runner.start()
    with pytest.raises(StoryRuntimeError, match=":3:"):
        runner.next()


def test_finished_runner_keeps_returning_end():
    runner = StoryRunner(parse_story('label start:\n    end\n'))
    runner.start()
    assert runner.next() == End()
    assert runner.next() == End()


def test_history_backlog_is_recorded_and_capped():
    story = parse_story('label start:\n    "a"\n    "b"\n    "c"\n')
    runner = StoryRunner(story, history_limit=2)
    runner.start()
    while not isinstance(runner.next(), End):
        pass
    assert runner.history == [(None, "b"), (None, "c")]


def test_start_resets_state():
    story = parse_story('default n = 0\nlabel start:\n    set n += 1\n    "x"\n')
    runner = StoryRunner(story)
    runner.start()
    runner.next()
    runner.start()
    assert runner.variables == {"n": 0} and runner.visited == set()


# ============================================================================
# Save / load
# ============================================================================
SAVE_SCRIPT = HEADER + """
default gold = 5
label start:
    mira "First line."
    set gold += 10
    mira "Gold: {gold}"
    menu:
        "Left":
            "went left"
        "Right":
            "went right"
    "The end."
"""


def advance_to(runner, predicate):
    for _ in range(50):
        step = runner.next()
        if predicate(step):
            return step
    raise AssertionError("never reached")


def test_save_and_resume_mid_dialogue_is_exact():
    story = parse_story(SAVE_SCRIPT)
    runner = StoryRunner(story)
    runner.start()
    advance_to(runner, lambda s: isinstance(s, Say) and s.text.startswith("Gold"))
    blob = json.loads(json.dumps(runner.save_state()))  # must survive real JSON

    restored = StoryRunner(story)
    restored.load_state(blob)
    assert restored.current == Say("mira", "Gold: 15")  # UI can re-show the line
    assert restored.variables["gold"] == 15
    choice = restored.next()
    assert [o.text for o in choice.options] == ["Left", "Right"]


def test_save_and_resume_while_choice_is_pending():
    story = parse_story(SAVE_SCRIPT)
    runner = StoryRunner(story)
    runner.start()
    advance_to(runner, lambda s: isinstance(s, Choice))
    blob = json.loads(json.dumps(runner.save_state()))

    restored = StoryRunner(story)
    restored.load_state(blob)
    assert restored.waiting_for_choice
    restored.choose(1)
    assert restored.next() == Say(None, "went right")
    assert restored.next() == Say(None, "The end.")


def test_original_and_restored_runs_continue_identically():
    story = parse_story(SAVE_SCRIPT)
    a = StoryRunner(story)
    a.start()
    advance_to(a, lambda s: isinstance(s, Say) and s.text.startswith("Gold"))
    b = StoryRunner(story)
    b.load_state(json.loads(json.dumps(a.save_state())))
    for runner in (a, b):
        runner.next()  # the choice
        runner.choose(0)
    assert [a.next(), a.next()] == [b.next(), b.next()]


def test_load_rejects_saves_from_a_different_script():
    runner = StoryRunner(parse_story(SAVE_SCRIPT))
    runner.start()
    runner.next()
    blob = runner.save_state()

    edited = StoryRunner(parse_story(SAVE_SCRIPT.replace("First line.", "First line!!")))
    with pytest.raises(SaveIncompatibleError):
        edited.load_state(blob)
    edited.load_state(blob, force=True)  # explicit override is allowed


def test_editing_comments_does_not_invalidate_saves():
    a = parse_story(SAVE_SCRIPT)
    b = parse_story("# a brand new comment\n\n" + SAVE_SCRIPT.replace("label start:", "label start:   # hi"))
    assert a.fingerprint == b.fingerprint


def test_load_rejects_garbage_state():
    runner = StoryRunner(parse_story(SAVE_SCRIPT))
    with pytest.raises(SaveIncompatibleError):
        runner.load_state({"version": 99})
    runner.start()
    blob = runner.save_state()
    blob["pc"] = 10_000
    with pytest.raises(SaveIncompatibleError):
        runner.load_state(blob)
