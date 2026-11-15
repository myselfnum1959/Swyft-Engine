import pytest

from swyft import Body, PhysicsWorld, Scene, StaticEntity, PhysicsEntity, Trigger, Vec2


def world_with_floor(floor_y=500):
    world = PhysicsWorld()
    floor = world.add_body(Body(-1000, floor_y, 3000, 100, static=True))
    return world, floor


def simulate(world, seconds, dt):
    for _ in range(round(seconds / dt)):
        world.step(dt)


def test_body_falls_and_lands_on_floor():
    world, floor = world_with_floor()
    body = world.add_body(Body(100, 0, 40, 40))
    simulate(world, 2.0, 1 / 60)
    assert body.on_ground
    assert body.aabb.bottom == floor.aabb.top  # resting exactly on top
    assert body.velocity.y == 0


def test_on_ground_stays_true_while_resting():
    world, _ = world_with_floor()
    body = world.add_body(Body(100, 460, 40, 40))  # bottom edge exactly on the floor
    for _ in range(30):
        world.step(1 / 60)
        assert body.on_ground


def test_gravity_is_independent_of_mass():
    # The v0.1 engine applied gravity as a *force*, so heavy bodies fell slower.
    world = PhysicsWorld()
    light = world.add_body(Body(0, 0, 10, 10, mass=1))
    heavy = world.add_body(Body(100, 0, 10, 10, mass=50))
    simulate(world, 0.5, 1 / 60)
    assert light.aabb.y == pytest.approx(heavy.aabb.y)


def test_forces_do_depend_on_mass():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    light = world.add_body(Body(0, 0, 10, 10, mass=1))
    heavy = world.add_body(Body(100, 0, 10, 10, mass=10))
    for body in (light, heavy):
        body.apply_force(Vec2(100, 0))
    world.step(0.1)
    assert light.velocity.x == pytest.approx(10 * heavy.velocity.x)


def test_impulse_changes_velocity_by_over_mass():
    body = Body(0, 0, 10, 10, mass=2)
    body.apply_impulse(Vec2(0, -100))
    assert body.velocity == Vec2(0, -50)


def test_fall_distance_is_frame_rate_independent():
    def fall(dt):
        world = PhysicsWorld()
        body = world.add_body(Body(0, 0, 10, 10, terminal_velocity=None))
        simulate(world, 1.0, dt)
        return body.aabb.y

    assert fall(1 / 60) == pytest.approx(fall(1 / 240), rel=0.02)


def test_drag_is_frame_rate_independent():
    def final_speed(dt):
        world = PhysicsWorld(gravity=Vec2(0, 0))
        body = world.add_body(Body(0, 0, 10, 10, drag=2.0))
        body.velocity = Vec2(100, 0)
        simulate(world, 1.0, dt)
        return body.velocity.x

    assert final_speed(1 / 30) == pytest.approx(final_speed(1 / 240), rel=1e-6)


def test_wall_stops_horizontal_motion_with_flags_and_callback():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    wall = world.add_body(Body(200, 0, 20, 100, static=True))
    body = world.add_body(Body(0, 10, 40, 40))
    body.velocity = Vec2(300, 0)
    hits = []
    body.on_collide = lambda me, other, normal: hits.append((other, normal))
    simulate(world, 1.0, 1 / 60)
    assert body.aabb.right == wall.aabb.left
    assert body.on_wall_right
    assert body.velocity.x == 0
    assert hits and hits[0] == (wall, Vec2(-1, 0))


def test_ceiling_hit_zeroes_upward_velocity():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    ceiling = world.add_body(Body(0, 0, 300, 20, static=True))
    body = world.add_body(Body(50, 100, 40, 40))
    body.velocity = Vec2(0, -400)
    simulate(world, 1.0, 1 / 60)
    assert body.on_ceiling and body.aabb.top == ceiling.aabb.bottom


def test_fast_body_does_not_tunnel_through_thin_wall():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    world.add_body(Body(500, 0, 4, 200, static=True))  # 4px thick
    body = world.add_body(Body(0, 50, 20, 20))
    body.velocity = Vec2(20000, 0)  # 333 px per 1/60 s tick
    world.step(1 / 60)
    assert body.aabb.right <= 500


def test_sliding_along_a_wall_does_not_snag_on_flat_ground():
    # Corner-snagging is the classic bug of "push out along the smallest overlap".
    world = PhysicsWorld()
    for x in range(0, 1000, 100):  # ground built from many tiles with seams
        world.add_body(Body(x, 500, 100, 100, static=True))
    body = world.add_body(Body(0, 460, 40, 40))
    for _ in range(120):
        body.velocity = Vec2(200, body.velocity.y)
        world.step(1 / 60)
    assert body.aabb.x > 300  # kept moving across every seam
    assert body.on_ground


def test_collision_layers_and_masks():
    world = PhysicsWorld()
    ghost_floor = world.add_body(Body(0, 100, 500, 50, static=True, layer=2))
    body = world.add_body(Body(10, 0, 20, 20, mask=0b01))  # ignores layer 2
    simulate(world, 1.0, 1 / 60)
    assert body.aabb.y > ghost_floor.aabb.bottom  # fell straight through


def test_terminal_velocity_caps_fall_speed():
    world = PhysicsWorld()
    body = world.add_body(Body(0, 0, 10, 10, terminal_velocity=500))
    simulate(world, 5.0, 1 / 60)
    assert body.velocity.y == 500


def test_trigger_enter_and_exit_fire_once_each():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    events = []
    zone = Trigger(100, 0, 50, 50, tag="door", on_enter=lambda b: events.append("in"), on_exit=lambda b: events.append("out"))
    world.add_trigger(zone)
    body = world.add_body(Body(0, 10, 20, 20))
    body.velocity = Vec2(100, 0)
    simulate(world, 3.0, 1 / 60)
    assert events == ["in", "out"]
    assert zone.occupants == []


def test_trigger_does_not_block_movement_and_ignores_static():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    seen = []
    world.add_trigger(Trigger(0, 0, 500, 500, on_enter=seen.append))
    world.add_body(Body(300, 300, 20, 20, static=True))
    mover = world.add_body(Body(10, 10, 20, 20))
    mover.velocity = Vec2(50, 0)
    world.step(0.1)
    assert seen == [mover]  # only the dynamic body
    assert mover.aabb.x > 10


def test_query_finds_overlapping_bodies():
    world = PhysicsWorld(gravity=Vec2(0, 0))
    a = world.add_body(Body(0, 0, 10, 10))
    world.add_body(Body(500, 500, 10, 10))
    from swyft import AABB

    assert world.query(AABB(5, 5, 10, 10)) == [a]


def test_invalid_mass_rejected():
    with pytest.raises(ValueError):
        Body(0, 0, 1, 1, mass=0)


# ---- scene + entity integration (still no pygame needed) --------------------
def test_scene_steps_physics_and_syncs_entity_position():
    scene = Scene()
    scene.add(StaticEntity(0, 500, 800, 100))
    box = scene.add(PhysicsEntity(100, 400, 40, 40))
    for _ in range(120):
        scene.update(1 / 60)
    assert box.is_on_ground
    assert box.position == Vec2(100, 460)


def test_scene_defers_add_and_remove_made_during_update():
    scene = Scene()
    log = []

    class Spawner(PhysicsEntity):
        def update(self, dt):
            if not log:
                log.append("spawned")
                scene.add(PhysicsEntity(0, 0))
                self.destroy()

    spawner = scene.add(Spawner(0, 0))
    scene.update(1 / 60)  # must not crash while mutating the entity list
    assert spawner not in scene.entities
    assert len(scene.entities) == 1
    assert len(scene.world.bodies) == 1  # removed body left the physics world too


def test_find_by_tag_and_name():
    scene = Scene()
    e = scene.add(StaticEntity(0, 0, 10, 10))
    e.tags.add("wall")
    e.name = "north_wall"
    assert scene.find("north_wall") is e
    assert scene.find_by_tag("wall") == [e]


def test_wall_contact_flag_persists_while_resting_against_wall():
    # Regression: flags used to be true only on the step the body *moved into* the wall.
    world = PhysicsWorld(gravity=Vec2(0, 0))
    world.add_body(Body(200, 0, 20, 100, static=True))
    body = world.add_body(Body(0, 10, 40, 40))
    body.velocity = Vec2(300, 0)
    simulate(world, 1.0, 1 / 60)  # 160px gap at 300px/s: arrives after ~0.53s
    for _ in range(10):  # now at rest against the wall
        world.step(1 / 60)
        assert body.on_wall_right and not body.on_wall_left


def test_floor_seams_are_not_reported_as_walls():
    world = PhysicsWorld()
    for x in range(0, 400, 100):
        world.add_body(Body(x, 500, 100, 100, static=True))
    body = world.add_body(Body(95, 460, 40, 40))  # straddles a seam
    for _ in range(5):
        world.step(1 / 60)
    assert body.on_ground
    assert not body.on_wall_left and not body.on_wall_right


def test_leaving_the_ground_clears_on_ground():
    world, _ = world_with_floor()
    body = world.add_body(Body(100, 460, 40, 40))
    world.step(1 / 60)
    assert body.on_ground
    body.velocity = Vec2(0, -600)  # jump
    world.step(1 / 60)
    assert not body.on_ground
