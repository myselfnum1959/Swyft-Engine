"""Swyft: a small 2D engine for story-driven games, built on pygame.

Everything that does not need a window (math, physics, camera, input mapping,
scenes, the story parser/runner, saves) imports without pygame. The pieces that
do (Engine, AssetManager, AudioManager, StoryScene...) load lazily on first use.
"""

from importlib import import_module

from .animation import Animation, Animator
from .camera import Camera2D
from .entities import Entity, PhysicsBody, PhysicsEntity, Sprite, StaticBody, StaticEntity
from .events import EventBus
from .input import InputManager
from .math2d import AABB, Vec2
from .physics import Body, PhysicsWorld, Trigger
from .save import SaveManager
from .scene import Scene, SceneStack
from .text import Typewriter, wrap_text
from .timing import FixedTimestep

__version__ = "0.2.0"

# name -> (module, attribute). Resolved on first access (PEP 562).
_LAZY = {
    "Engine": (".engine", "Engine"),
    "EngineConfig": (".engine", "EngineConfig"),
    "SwyftEngine": (".engine", "Engine"),  # v0.1 name
    "AssetManager": (".assets", "AssetManager"),
    "AudioManager": (".audio", "AudioManager"),
    "SpriteSheet": (".sprites", "SpriteSheet"),
    "StoryScene": (".story.scene", "StoryScene"),
}

__all__ = [
    "AABB",
    "Animation",
    "Animator",
    "Body",
    "Camera2D",
    "Entity",
    "EventBus",
    "FixedTimestep",
    "InputManager",
    "PhysicsBody",
    "PhysicsEntity",
    "PhysicsWorld",
    "SaveManager",
    "Scene",
    "SceneStack",
    "Sprite",
    "StaticBody",
    "StaticEntity",
    "Trigger",
    "Typewriter",
    "Vec2",
    "wrap_text",
    *_LAZY,
]


def __getattr__(name: str):
    if name in _LAZY:
        module_name, attribute = _LAZY[name]
        value = getattr(import_module(module_name, __name__), attribute)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
