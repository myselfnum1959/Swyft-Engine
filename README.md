# Swyft Engine

A small 2D engine for **story-driven games**, written in Python on top of pygame.
It pairs a conventional engine core (fixed-timestep loop, scene stack, physics,
camera, input mapping, saves) with a **dialogue scripting language** that has
branching, variables, conditions and save/load.

```text
label start:
    scene harbor_dusk
    show mira calm at left
    mira "You're late. The ferry leaves in five minutes."
    menu:
        "Apologise and ask for help":
            set courage += 1
        "Say you don't need her help":
            mira "Suit yourself."
    if courage >= 1:
        mira "At least you're polite."
```

## Quick start

```bash
pip install -e ".[dev]"
python main.py                 # story demo ("The Last Ferry"), placeholder art included
python -m examples.platformer  # physics / camera / trigger demo
pytest                         # run the test suite (no display needed)
python -m swyft check examples/story_demo/story.swy   # lint a script
```

Controls in the story demo: Enter / Space / click to continue, Up/Down + Enter or
mouse to choose, hold Ctrl to fast-forward, F5 / F9 quick save / load, F3 debug overlay.

## A minimal game

```python
from swyft import Engine
from swyft.story import StoryScene, load_story

engine = Engine("My Story", 960, 540, asset_path="assets")
engine.push_scene(StoryScene(load_story("story.swy")))
engine.run()
```

## Features

| Area | What's there |
|---|---|
| **Loop** | Fixed-timestep simulation decoupled from rendering (deterministic physics at any FPS) |
| **Scenes** | Scene stack with enter/exit/pause/resume hooks and transparent overlays; safe add/remove during update |
| **Input** | Action mapping (`pressed("confirm")`), rebinding, per-tick edge detection, keyboard + mouse |
| **Physics** | AABB bodies, axis-separated collision, substepping (no tunnelling), contact flags, layers/masks, trigger zones, area queries |
| **Camera** | Smooth follow (frame-rate independent), world bounds, screen shake |
| **Animation** | Clips + animator, sprite-sheet slicing |
| **Assets / audio** | Cached loading, placeholders for missing files, audio that degrades gracefully without a device |
| **Saves** | Atomic JSON slots, versioned format, slot-name sanitising |
| **Story system** | Script compiler, runner, safe expression language, typewriter dialogue UI, choices, quick save/load, custom commands |
| **Tooling** | `python -m swyft check` script linter, debug overlay (F3), CI workflow |

The pure-logic modules (everything except `Engine`, `AssetManager`, `AudioManager`,
`SpriteSheet`, `StoryScene`) import **without pygame**, which is why they can be
unit-tested headlessly.

## Documentation

- [Architecture and design decisions](docs/ARCHITECTURE.md)
- [Script language reference](docs/SCRIPT_REFERENCE.md)
- [Changelog / migration from v0.1](CHANGELOG.md)

## Known limitations (and roadmap)

- Dynamic bodies don't collide with each other (only with static geometry) and bodies must not spawn inside solids.
- Collision broad-phase is a linear scan; a spatial hash is the next step for large levels.
- No tilemap loader, no rollback ("go back one line"), no read-text tracking for skip mode.
- Rendering code (`StoryScene` drawing, `Engine` window handling) is covered by headless smoke tests but has had less real-world testing than the logic layers.

## Project layout

```text
swyft/            engine package
  story/          script parser, runner, safe expressions, StoryScene
examples/         story demo + platformer demo
tests/            pytest suite
docs/             architecture + script reference
```

## License

MIT
