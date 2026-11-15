"""Fixed-timestep accumulator.

Why: if physics runs once per rendered frame with a variable ``dt``, the result
depends on the machine's frame rate (jump height changes, objects tunnel through
walls on a lag spike). Instead the engine renders as fast as it likes but advances
the simulation in constant slices, so gameplay is deterministic.

This is the "Fix Your Timestep!" pattern (Glenn Fiedler).
"""

from __future__ import annotations


class FixedTimestep:
    def __init__(self, step: float = 1 / 60, max_frame_time: float = 0.25):
        if step <= 0:
            raise ValueError("step must be positive")
        self.step = step
        # If the game stalls (window dragged, debugger paused) we don't try to
        # "catch up" with hundreds of updates - that causes the spiral of death.
        self.max_frame_time = max_frame_time
        self._accumulator = 0.0

    def advance(self, frame_time: float) -> int:
        """Feed in the real elapsed time; returns how many fixed updates to run."""
        self._accumulator += min(max(frame_time, 0.0), self.max_frame_time)
        steps = 0
        # The tiny epsilon stops float error (60 * 1/60 != 1.0) from losing a step.
        while self._accumulator >= self.step - 1e-9:
            self._accumulator -= self.step
            steps += 1
        self._accumulator = max(self._accumulator, 0.0)
        return steps

    @property
    def alpha(self) -> float:
        """How far (0..1) we are between the last update and the next one.

        Renderers can use this to interpolate positions for smoother visuals.
        """
        return self._accumulator / self.step

    def reset(self) -> None:
        self._accumulator = 0.0
