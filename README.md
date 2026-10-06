# Swyft Engine

**Swyft Engine** is a lightweight 2D game engine built from scratch in **Python and Pygame**.

The project is designed to explore how game engines work internally while providing a simple foundation for building 2D games. It currently includes basic entities, physics, collision detection, input handling, scene management, and a game loop.

> **Status:** Early development
> Started in October 6, 2026

---

## Overview

Swyft Engine is being developed as a learning-focused but expandable game engine.

Instead of relying entirely on an existing engine such as Unity or Godot, the project focuses on understanding and implementing the fundamental systems that make a game engine work.

Current systems include:

* Entity system
* 2D physics
* Gravity and forces
* Velocity and acceleration
* Drag
* Collision detection and resolution
* Static bodies
* Keyboard input
* Scene management
* Game loop
* Basic rendering

The architecture is intentionally kept simple so that new systems can be added without making the engine difficult to understand.

---

## Project Structure

```text
Swyft Engine/
│
├── main.py
│
└── swyft/
    ├── __init__.py
    ├── swyft_engine.py
    └── entity.py
```

### `main.py`

The game's entry point.

This is where a game built with Swyft Engine creates the engine, entities, platforms, and other gameplay objects.

Example:

```python
from swyft import SwyftEngine, PhysicsBody, StaticBody
```

---

### `swyft_engine.py`

Contains the core engine systems.

Currently includes:

* `SwyftEngine`
* `PhysicsBody`
* `StaticBody`
* `InputManager`
* `SceneManager`

---

### `entity.py`

Contains the base `Entity` class.

Entities provide a common foundation for objects that can exist inside a scene.

---

### `__init__.py`

Provides a clean public API for the engine.

Instead of importing classes from individual implementation files:

```python
from swyft.swyft_engine import SwyftEngine
```

users can simply write:

```python
from swyft import SwyftEngine
```

---

# Core Architecture

Swyft Engine currently follows a simple hierarchy:

```text
Entity
│
├── PhysicsBody
│
└── StaticBody
```

This allows different types of game objects to share common functionality while having their own behavior.

For example, a player can inherit from `PhysicsBody`:

```python
class Player(PhysicsBody):

    def __init__(self, x, y):
        super().__init__(x, y)

    def update(self, delta_time):
        # Player behavior
        super().update(delta_time)
```

This makes it possible to build specialized game objects without modifying the engine's core classes.

---

# Physics

Swyft Engine uses basic Newtonian-style physics.

A `PhysicsBody` contains:

```text
Position
Velocity
Acceleration
Mass
Gravity
Drag
```

Forces can be applied using:

```python
body.apply_force(force)
```

The basic physics update follows the idea:

```text
Force
  ↓
Acceleration
  ↓
Velocity
  ↓
Position
```

The engine uses delta time so that physics is not directly tied to the number of frames rendered.

---

# Collision System

The engine currently uses `pygame.Rect` for basic axis-aligned collision detection.

Example:

```python
if self.rect.colliderect(other.rect):
    ...
```

When two physics bodies overlap, Swyft Engine calculates the overlap and attempts to resolve the collision by moving the body out of the other object.

Current collision handling supports basic:

* Horizontal collision resolution
* Vertical collision resolution
* Ground detection
* Velocity cancellation

This system is intentionally simple and will likely be replaced or expanded as the engine develops.

---

# Static Bodies

A `StaticBody` represents an object that does not move through physics.

For example:

```python
ground = StaticBody(
    0,
    500,
    800,
    100
)
```

Static bodies can be used for:

* Ground
* Platforms
* Walls
* Obstacles
* Level geometry

---

# Scene Management

The `SceneManager` stores and manages the entities currently active in a scene.

It is responsible for:

```text
Add entities
     ↓
Update entities
     ↓
Check collisions
     ↓
Render entities
```

Entities can be added with:

```python
game.scene.add_entity(player)
```

This keeps the main game code relatively clean while the engine handles the underlying systems.

---

# Input

Swyft Engine currently provides an `InputManager` for keyboard input.

Example:

```python
if game.input.is_key_pressed("SPACE"):
    player.jump()
```

The input system is planned to become more flexible as the engine develops, including support for configurable controls and potentially controller input.

---

# Game Loop

The engine provides the main game loop automatically.

A typical game only needs:

```python
game = SwyftEngine(
    "My Game",
    800,
    600
)

game.run()
```

Internally, the engine repeatedly performs:

```t
```
