# Architecture

```text
                 +-----------------------------+
                 |           Engine            |
                 |  window, main loop, services|
                 +--+-----+------+------+------+
                    |     |      |      |
              InputManager EventBus AssetManager SaveManager  (AudioManager)
                    |
              SceneStack  ---->  Scene  --- owns --->  entities, PhysicsWorld, Camera2D
                                   |
                              StoryScene  ---- drives ---> StoryRunner <--- Story <--- parser
```

## Frame structure

```text
each rendered frame:
    pump OS events -> InputManager (buffers key edges)
    N = FixedTimestep.advance(real_elapsed)      # 0..15 whole steps
    repeat N times: input.tick(); scene.update(1/60)
    render once
```

**Why fixed timestep?** With a variable `dt`, jump height and collisions depend on the
player's frame rate, and a lag spike can move a body far enough to skip a wall.
A constant step makes the simulation deterministic and testable. The accumulator clamps
stalls to 0.25 s to avoid the "spiral of death".

## Decisions worth knowing

| Decision | Reasoning |
|---|---|
| Own `Vec2`/`AABB` instead of `pygame.Vector2/Rect` | Keeps the core free of the rendering library, so logic is unit-testable in CI and the backend is swappable. |
| Lazy imports for pygame-dependent classes (PEP 562 `__getattr__`) | `import swyft` and the script linter work without pygame installed. |
| Action-based input; edges latched per **tick** | Rebindable controls; a tap that begins and ends between two ticks is still seen (raw events are buffered). |
| Gravity as acceleration, forces divided by mass | Matches physics (F = ma) and fixes v0.1 where heavy bodies fell slower. |
| Axis-separated collision + substeps | Exact "landed / hit wall" info, no corner snagging, no tunnelling through thin walls. |
| Contact flags from **probing**, not from "moved into" | A body resting against a wall keeps `on_wall_*` even though it no longer moves (found via a failing test). |
| Scene changes and entity add/remove are deferred during update | Mutating a list while iterating it is a classic crash; changes apply after the update finishes. |
| Exponential smoothing / drag (`exp(-k*dt)`) | Frame-rate independent, unlike `lerp(a, b, 0.1)` per frame. Covered by tests at 30 vs 240 Hz. |

## Story system

```text
script text --parse--> Story(code[], labels, defaults, characters) --run--> Steps --> game
```

- **Compiler** (`story/parser.py`): recursive descent over indentation, emitting a *flat*
  instruction list with explicit jump targets (`if`/`menu` back-patch forward jumps).
  A validation pass reports unknown labels, undefined variables and undeclared speakers
  with line numbers and "did you mean ...?" hints, so authors find mistakes at load time.
- **Runner** (`story/runner.py`): a program counter over the instruction list. Returns
  `Say` / `Choice` / `Command` / `End` steps; silent instructions run internally.
  A step budget detects scripts that loop forever without showing anything.
- **Save state** is just `{pc, variables, visited, history, current step}`, trivially JSON,
  possible *because* the program is flat. A fingerprint of the compiled program rejects
  saves from an incompatible script (comment edits don't change it).
- **Safe expressions** (`story/expr.py`): Python's `ast` parser plus a node whitelist,
  evaluated by our own walker. There is no `eval`/`exec`, so scripts and saves can't run code.
  Tests assert that calls, attribute access, comprehensions, lambdas, `**` etc. are rejected.
- **Presentation** (`StoryScene`) is separate from **flow** (`StoryRunner`), connected only
  by steps. Custom commands: pass `extra_commands=` to the parser and
  `scene.register_command(name, handler)`, or listen to the `story.command` event.

## Testing strategy

- Pure-logic modules are tested without pygame (math, timing, input, physics, camera,
  animation, text, saves, script language).
- Regression tests encode real bugs found while building (see CHANGELOG).
- An exhaustive walk over every branch of the demo story guards the example script.
- Headless smoke tests run the real `Engine` + `StoryScene` under SDL's dummy driver.
