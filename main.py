import pygame

from swyft import (
    SwyftEngine,
    PhysicsBody,
    StaticBody
)


class Player(PhysicsBody):

    def __init__(self, x, y):
        super().__init__(x, y)

        self.speed = 300
        self.jump_force = -500
        self.drag = 1000

    def update(self, delta_time):

        # Move left/right
        if pygame.key.get_pressed()[pygame.K_a]:
            self.velocity.x = -self.speed

        elif pygame.key.get_pressed()[pygame.K_d]:
            self.velocity.x = self.speed

        else:
            self.velocity.x = 0

        # Jump
        if (
            pygame.key.get_pressed()[pygame.K_SPACE]
            and self.is_on_ground
        ):
            self.velocity.y = self.jump_force

        # Let PhysicsBody handle gravity and movement
        super().update(delta_time)

    def render(self, surface):
        pygame.draw.rect(
            surface,
            (50, 150, 255),
            self.rect
        )


# Create engine
game = SwyftEngine(
    "Swyft Platformer",
    800,
    600
)

# Player
player = Player(100, 400)

# Platforms
ground = StaticBody(
    0, 500,
    800, 100
)

platform = StaticBody(
    300, 400,
    200, 30
)

# Add everything
game.scene.add_entity(player)
game.scene.add_entity(ground)
game.scene.add_entity(platform)

# Run
game.run()