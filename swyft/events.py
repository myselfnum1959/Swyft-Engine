"""A tiny publish/subscribe event bus.

Lets systems talk without importing each other: the story system can emit
``"story.choice"`` and an achievements module can react without either knowing
about the other.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

Handler = Callable[..., None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> Callable[[], None]:
        """Register ``handler``. Returns a function that unsubscribes it."""
        self._handlers[event].append(handler)

        def unsubscribe() -> None:
            handlers = self._handlers.get(event, [])
            if handler in handlers:
                handlers.remove(handler)

        return unsubscribe

    def once(self, event: str, handler: Handler) -> Callable[[], None]:
        """Like subscribe, but the handler fires at most one time."""

        def wrapper(*args: Any, **kwargs: Any) -> None:
            unsubscribe()
            handler(*args, **kwargs)

        unsubscribe = self.subscribe(event, wrapper)
        return unsubscribe

    def emit(self, event: str, *args: Any, **kwargs: Any) -> int:
        """Call every handler for ``event``; returns how many were called.

        Iterates over a copy so handlers may safely (un)subscribe while running.
        Exceptions are not swallowed - a broken handler should be loud.
        """
        handlers = list(self._handlers.get(event, ()))
        for handler in handlers:
            handler(*args, **kwargs)
        return len(handlers)

    def clear(self, event: str | None = None) -> None:
        if event is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event, None)
