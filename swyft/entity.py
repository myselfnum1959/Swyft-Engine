import pygame


class Entity:
    """
    Base class for objects in Swyft Engine.
    """

    def __init__(self, name: str = "Entity"):
        self.name = name

        # Position
        self.position = pygame.Vector2(0, 0)

        # Movement
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)

        # Whether the entity should be updated/rendered.
        self.active = True

    def update(self, delta_time: float):
        """
        Called once every frame.

        Child classes can override this.
        """
        pass
    
    def render(self, surface: pygame.Surface):
        """
        Draw the entity.

        Child classes can override this.
        """
        pass                        