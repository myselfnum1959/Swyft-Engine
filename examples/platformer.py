"""Physics demo (the original v0.1 demo, rewritten): ``python -m examples.platformer``

A/D or arrows move, Space/W/Up jumps. The camera follows the player; walking into the
pink zone fires a trigger. F3 shows physics bodies.
"""

from swyft import AABB, Engine, PhysicsEntity, Scene, StaticEntity, Trigger, Vec2


class Player(PhysicsEntity):
    SPEED = 300
    JUMP_SPEED = 620

    def update(self, dt: float) -> None:
        inp = self.engine.input
        # Set horizontal velocity directly (snappy platformer feel); gravity owns vertical.
        self.velocity = Vec2(inp.axis("left", "right") * self.SPEED, self.velocity.y)
        if inp.pressed("jump") and self.is_on_ground:  # pressed = once per tap, not while held
            self.velocity = Vec2(self.velocity.x, -self.JUMP_SPEED)


class PlatformerScene(Scene):
    LEVEL = AABB(0, 0, 2000, 540)

    def on_enter(self) -> None:
        self.player = self.add(Player(100, 380, 40, 40))
        self.add(StaticEntity(0, 460, 2000, 80))
        for x, y, w in [(300, 360, 160), (560, 280, 160), (850, 360, 200), (1300, 300, 240)]:
            self.add(StaticEntity(x, y, w, 24))
        self.add(StaticEntity(-20, 0, 20, 540))
        self.add(StaticEntity(2000, 0, 20, 540))

        self.world.add_trigger(
            Trigger(1500, 380, 120, 80, tag="zone",
                    on_enter=lambda b: print("entered the zone"),
                    on_exit=lambda b: print("left the zone"))
        )
        self.camera.bounds = self.LEVEL
        self.camera.follow(self.player.center)

    def update(self, dt: float) -> None:
        super().update(dt)
        self.camera.follow(self.player.center)

    def render(self, surface) -> None:
        import pygame

        zone = self.world.triggers[0]
        pygame.draw.rect(surface, (120, 40, 100), self.camera.apply_rect(zone.aabb))
        super().render(surface)


if __name__ == "__main__":
    engine = Engine("Swyft Platformer", 960, 540)
    engine.push_scene(PlatformerScene())
    engine.run()
