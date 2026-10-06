import sys
import pygame

from .entity import Entity


# ============================================================
# PHYSICS
# ============================================================

class PhysicsBody(Entity):
    """
    An Entity that uses simple 2D physics.

    PhysicsBody supports:
        - Velocity
        - Acceleration
        - Gravity
        - Forces
        - Collision detection
        - Collision response
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: int = 40,
        height: int = 40,
        mass: float = 1.0
    ):
        super().__init__("PhysicsBody")

        # Position
        self.position = pygame.Vector2(x, y)

        # Movement
        self.velocity = pygame.Vector2(0, 0)
        self.acceleration = pygame.Vector2(0, 0)

        # Physics settings
        self.mass = mass
        self.gravity = pygame.Vector2(0, 1000)

        # Small amount of air resistance
        self.drag = 0.98

        # Collision rectangle
        self.rect = pygame.Rect(
            x,
            y,
            width,
            height
        )

        # Is the object standing on something?
        self.is_on_ground = False

    # --------------------------------------------------------
    # FORCES
    # --------------------------------------------------------

    def apply_force(self, force: pygame.Vector2):
        """
        Apply a force to the body.

        Newton's second law:

            F = ma

        Therefore:

            a = F / m
        """

        self.acceleration += force / self.mass

    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    def update(self, delta_time: float):
        """
        Update the physics body.

        delta_time is the amount of time that passed
        since the previous frame.
        """

        # Apply gravity
        self.apply_force(self.gravity)

        # Acceleration changes velocity
        self.velocity += self.acceleration * delta_time

        # Apply drag
        self.velocity *= self.drag

        # Velocity changes position
        self.position += self.velocity * delta_time

        # Forces only last for one frame
        self.acceleration = pygame.Vector2(0, 0)

        # We assume we're not touching the ground
        # until a collision proves otherwise.
        self.is_on_ground = False

        # Keep the collision rectangle synchronized
        # with the object's position.
        self.update_rect()

    # --------------------------------------------------------
    # COLLISION
    # --------------------------------------------------------

    def update_rect(self):
        """Move the collision rectangle to the object's position."""

        self.rect.topleft = (
            round(self.position.x),
            round(self.position.y)
        )

    def handle_collision(self, other):
        """
        Resolve a collision with another object.

        The smaller overlap tells us which direction
        the collision most likely happened from.
        """

        if not self.rect.colliderect(other.rect):
            return

        # Find the area where the two rectangles overlap.
        overlap = self.rect.clip(other.rect)

        # ----------------------------------------------------
        # HORIZONTAL COLLISION
        # ----------------------------------------------------

        if overlap.width < overlap.height:

            if self.rect.centerx < other.rect.centerx:
                # We hit the other object from the left.
                self.position.x -= overlap.width

            else:
                # We hit the other object from the right.
                self.position.x += overlap.width

            # Stop horizontal movement.
            self.velocity.x = 0

        # ----------------------------------------------------
        # VERTICAL COLLISION
        # ----------------------------------------------------

        else:

            if self.rect.centery < other.rect.centery:
                # We landed on top of the other object.
                self.position.y -= overlap.height

                self.is_on_ground = True

            else:
                # We hit the bottom of the other object.
                self.position.y += overlap.height

            # Stop vertical movement.
            self.velocity.y = 0

        # Update the rectangle after moving the object.
        self.update_rect()


# ============================================================
# STATIC BODY
# ============================================================

class StaticBody(Entity):
    """
    An object that does not move.

    Useful for:
        - Floors
        - Walls
        - Platforms
        - Obstacles
    """

    def __init__(
        self,
        x: float,
        y: float,
        width: int,
        height: int
    ):
        super().__init__("StaticBody")

        self.position = pygame.Vector2(x, y)

        self.rect = pygame.Rect(
            x,
            y,
            width,
            height
        )

        # Temporary color until Swyft gets
        # a proper rendering/material system.
        self.color = (80, 120, 220)

    def render(self, surface):
        """Draw the static body."""

        pygame.draw.rect(
            surface,
            self.color,
            self.rect
        )


# ============================================================
# INPUT
# ============================================================

class InputManager:
    """
    Handles keyboard input.
    """

    def __init__(self):
        self.keys = None

    def update(self):
        """Update the keyboard state."""

        self.keys = pygame.key.get_pressed()

    def is_key_pressed(self, key) -> bool:
        """
        Return True if the specified key is being held.
        """

        if self.keys is None:
            return False

        return self.keys[key]


# ============================================================
# SCENE
# ============================================================

class SceneManager:
    """
    Keeps track of all objects currently in the game.
    """

    def __init__(self):
        self.entities = []

    # --------------------------------------------------------
    # ENTITY MANAGEMENT
    # --------------------------------------------------------

    def add_entity(self, entity: Entity):
        """Add an entity to the scene."""

        self.entities.append(entity)

    def remove_entity(self, entity: Entity):
        """Remove an entity from the scene."""

        if entity in self.entities:
            self.entities.remove(entity)

    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    def update(self, delta_time: float):
        """
        Update every active entity, then check collisions.
        """

        # Update entities
        for entity in self.entities:

            if entity.active:
                entity.update(delta_time)

        # Check collisions
        self.handle_collisions()

    # --------------------------------------------------------
    # COLLISIONS
    # --------------------------------------------------------

    def handle_collisions(self):
        """
        Check every entity against every other entity.

        If one of them is a PhysicsBody,
        let that PhysicsBody handle the collision.
        """

        for i, first in enumerate(self.entities):

            for second in self.entities[i + 1:]:

                # Both objects need collision rectangles.
                if not hasattr(first, "rect"):
                    continue

                if not hasattr(second, "rect"):
                    continue

                # Don't do anything if they aren't touching.
                if not first.rect.colliderect(second.rect):
                    continue

                # PhysicsBody handles the collision.
                if isinstance(first, PhysicsBody):

                    first.handle_collision(second)

                elif isinstance(second, PhysicsBody):

                    second.handle_collision(first)

    # --------------------------------------------------------
    # RENDER
    # --------------------------------------------------------

    def render(self, surface: pygame.Surface):
        """Render every active entity."""

        for entity in self.entities:

            if entity.active:
                entity.render(surface)


# ============================================================
# SWYFT ENGINE
# ============================================================

class SwyftEngine:
    """
    Main class used to create and run a Swyft Engine game.

    Example:

        game = SwyftEngine("My Game", 800, 600)

        game.run()
    """

    def __init__(
        self,
        title: str = "Swyft Engine Game",
        width: int = 800,
        height: int = 600
    ):

        # ----------------------------------------------------
        # START PYGAME
        # ----------------------------------------------------

        pygame.init()

        # ----------------------------------------------------
        # WINDOW
        # ----------------------------------------------------

        self.width = width
        self.height = height

        self.screen = pygame.display.set_mode(
            (width, height),
            pygame.RESIZABLE | pygame.SCALED
        )

        pygame.display.set_caption(title)

        # ----------------------------------------------------
        # GAME CLOCK
        # ----------------------------------------------------

        self.clock = pygame.time.Clock()

        self.fps = 60

        # ----------------------------------------------------
        # ENGINE SYSTEMS
        # ----------------------------------------------------

        self.input = InputManager()

        self.scene = SceneManager()

        # ----------------------------------------------------
        # ENGINE STATE
        # ----------------------------------------------------

        self.running = False

    # ========================================================
    # GAME LOOP
    # ========================================================

    def run(self):
        """
        Start the Swyft Engine game loop.
        """

        self.running = True

        while self.running:

            # ------------------------------------------------
            # DELTA TIME
            # ------------------------------------------------

            # Convert milliseconds into seconds.
            delta_time = self.clock.tick(self.fps) / 1000.0

            # ------------------------------------------------
            # EVENTS
            # ------------------------------------------------

            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    self.running = False

            # ------------------------------------------------
            # INPUT
            # ------------------------------------------------

            self.input.update()

            # ------------------------------------------------
            # UPDATE
            # ------------------------------------------------

            self.scene.update(delta_time)

            # ------------------------------------------------
            # RENDER
            # ------------------------------------------------

            self.screen.fill((30, 30, 35))

            self.scene.render(self.screen)

            pygame.display.flip()

        # ----------------------------------------------------
        # SHUTDOWN
        # ----------------------------------------------------

        pygame.quit()
        sys.exit()