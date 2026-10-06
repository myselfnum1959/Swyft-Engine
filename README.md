# Swyft

**Swyft** is a lightweight 2D game engine built with **Python and Pygame**.

The project started on **October 6, 2026**, with the goal of learning how game engines work by building one from the ground up.

## Features

* 2D physics
* Gravity and forces
* Velocity and acceleration
* Drag
* Basic collision detection
* Static bodies
* Entity system
* Scene management
* Keyboard input
* Delta-time game loop
* Basic rendering

## Built With

* Python
* Pygame

## Current Structure

```text
Swyft/
├── main.py
└── swyft/
    ├── __init__.py
    ├── swyft_engine.py
    └── entity.py
```

## Example

```python
from swyft import SwyftEngine

game = SwyftEngine("My Game", 800, 600)

game.run()
```

## What's Next

Swyft is still in its early stages. Future development will focus on things like:

* Sprite rendering
* Animation
* Camera system
* Better physics
* Audio
* Scene tools
* Editor
* Asset management
* More flexible input
* Custom scripting

The engine will grow as I learn more about game development and engine architecture.

---

**Started:** October 6, 2026
**Language:** Python
**Framework:** Pygame
**Status:** In Development
