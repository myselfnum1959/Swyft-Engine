"""Exhaustively explores every branch of the bundled demo story."""

from pathlib import Path

from swyft.story import Choice, End, StoryRunner, load_story

STORY = Path(__file__).parent.parent / "examples" / "story_demo" / "story.swy"


def explore(story):
    """Depth-first walk over all choice combinations; returns the set of endings reached."""
    endings = set()
    stack = [[]]  # each item is a list of choice indexes to replay
    seen_paths = 0
    while stack:
        picks = stack.pop()
        runner = StoryRunner(story)
        runner.start()
        replay = iter(picks)
        for _ in range(2000):
            step = runner.next()
            if isinstance(step, End):
                endings.add(tuple(t for _, t in runner.history[-1:]))
                seen_paths += 1
                break
            if isinstance(step, Choice):
                try:
                    runner.choose(next(replay))
                except StopIteration:  # a new decision point: branch into every option
                    for i in range(len(step.options)):
                        stack.append(picks + [i])
                    break
        else:
            raise AssertionError(f"no end reached for picks {picks}: possible infinite loop")
        assert seen_paths < 500, "branching exploded"
    return endings


def test_demo_story_parses_and_every_path_reaches_an_ending():
    endings = explore(load_story(STORY))
    final_lines = {line for (line,) in endings}
    assert any(line.startswith("You made it across") for line in final_lines)  # ferry ending
    assert any("miss the boat" in line for line in final_lines)  # walked-away ending
    assert {line for line in final_lines if line.startswith("You made it across")} == {
        "You made it across. Courage gained: 0.",
        "You made it across. Courage gained: 1.",
    }  # both courage values are reachable
