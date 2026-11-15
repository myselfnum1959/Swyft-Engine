# Changelog

## 0.2.0

### Fixed (bugs in 0.1)
- Demo player used `drag = 1000` against a per-frame multiplier, launching it off-screen on frame 1.
- Gravity was applied as a force, so heavier bodies fell slower. It is now an acceleration.
- Drag was a per-frame multiplier (frame-rate dependent). It is now exponential per second.
- Collision resolution used smallest-overlap guessing (corner snagging, tunnelling). Replaced by axis-separated, substepped resolution.
- `run()` called `sys.exit()`; it now returns normally.
- Committed `__pycache__` removed; `.gitignore` added.

### Added
- Fixed timestep, scene stack, event bus, action-based input, camera, animation, asset/audio/save managers.
- Trigger zones, collision layers, contact flags, area queries.
- Story system: scripting language, safe evaluator, runner with save/load, `StoryScene`.
- Tests, CI, `python -m swyft check`.

### Migrating from 0.1
- `SwyftEngine` is now an alias of `Engine`; `PhysicsBody`/`StaticBody` alias `PhysicsEntity`/`StaticEntity`.
- `engine.scene.add_entity(x)` still works. Prefer subclassing `Scene` and `engine.push_scene(...)`.
- `entity.rect` still returns a `pygame.Rect`; physics state lives in `entity.body`.
- Read input with actions: `self.engine.input.down("left")` instead of `pygame.key.get_pressed()`.
