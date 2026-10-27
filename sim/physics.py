"""Billiard table physics, written from FACTSHEET.md.

One function, `simulate`, runs a scene once. Counterfactual changes are passed
in as arguments: balls to leave out, balls that get direction noise, and balls
that replay a recorded path instead of being simulated.
"""
import math

import numpy as np
import pymunk

WIDTH, HEIGHT = 1000, 750
RADIUS = 30
SPEED_SCALE = 120
DT = 1 / 50
STEP_LIMIT = 700
EXIT_X = -RADIUS  # B has gone in once its center passes this line

# (x_min, x_max, y_min, y_max) of each wall box; the gap at y 258.34 to 491.67 is the gate
WALLS = [
    (0, 1000, 725, 750),
    (0, 1000, -2.5, 22.5),
    (0, 25, 627.094, 725.012),
    (0, 25, 491.6745, 589.5935),
    (0, 25, 160.4185, 258.3375),
    (0, 25, 24.9995, 122.9185),
]
GATE_Y = (258.3375, 491.6745)

BALL, WALL = 1, 2  # pymunk collision types


def on_table(p):
    return 0 <= p[0] <= WIDTH and 0 <= p[1] <= HEIGHT


class Run:
    """What one simulation produced."""

    def __init__(self, names):
        self.names = names
        self.contacts = []  # (step, name1, name2, pos1, pos2), in order
        self.went_in = False
        self.exit_step = None
        self.b_end = None  # B's position when the run decided the outcome
        self.paths = None  # name -> (steps, 2) array, if recorded
        self.vels = None


def _space():
    space = pymunk.Space()
    for x0, x1, y0, y1 in WALLS:
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = ((x0 + x1) / 2, (y0 + y1) / 2)
        box = pymunk.Poly.create_box(body, size=(x1 - x0, y1 - y0))
        box.elasticity = 1
        box.friction = 0
        box.collision_type = WALL
        space.add(body, box)
    return space


def _ball(space, pos, vel):
    body = pymunk.Body(1, pymunk.moment_for_circle(1, 0, RADIUS))
    body.position = tuple(pos)
    body.velocity = tuple(vel)
    shape = pymunk.Circle(body, RADIUS)
    shape.elasticity = 1
    shape.friction = 0
    shape.collision_type = BALL
    space.add(body, shape)
    return body


def simulate(scene, *, leave_out=(), noise=None, replay=None, record=False,
             full_length=False, shift=None, target="B", noise_ref=None, tol=1e-6):
    """Run a scene once.

    scene: list of dicts with name, position and velocity (velocity as in the
        scene file, before the speed scale).
    leave_out: names of balls that are not in the scene at all.
    noise: dict name -> (start_step, angles), where angles[t] is the rotation in
        degrees applied to that ball's velocity at step t; applied only when
        t > start_step. A ball can also be listed with start_step None, in which
        case noise starts at the step after its position first differs from
        noise_ref[name] (a recorded path) by more than tol.
    replay: dict name -> (positions, velocities), each a (steps, 2) recording.
        Those balls are reset to the recording at the start of every step, so
        they follow it exactly and are never pushed off it. Within a step they
        are ordinary balls of mass 1, so a simulated ball that meets one is
        pushed exactly as it would be by that ball moving on that path. (A
        fixed-path body of infinite mass would instead bounce it like a moving
        wall, which changes B's path even when nothing about B changed.)
    record: keep every ball's path and velocity.
    full_length: keep running to the step limit after B goes in.
    shift: (name, dx, dy) moves one ball's start position.
    """
    space = _space()
    names, bodies = [], []
    replay = replay or {}
    for ball in scene:
        name = ball["name"]
        if name in leave_out:
            continue
        pos = list(ball["position"])
        if shift is not None and shift[0] == name:
            pos = [pos[0] + shift[1], pos[1] + shift[2]]
        vel = [v * SPEED_SCALE for v in ball["velocity"]]
        body = _ball(space, pos, vel)
        body.ball_name = name
        names.append(name)
        bodies.append(body)

    run = Run(names)
    step = 0

    def log_contact(arbiter, space_, data):
        b1, b2 = arbiter.shapes[0].body, arbiter.shapes[1].body
        run.contacts.append((step, b1.ball_name, b2.ball_name,
                             tuple(b1.position), tuple(b2.position)))
        return True

    space.add_collision_handler(BALL, BALL).begin = log_contact

    by_name = dict(zip(names, bodies))
    tb = by_name[target]
    noisy = []
    for name, (start, angles) in (noise or {}).items():
        if name in by_name:
            ref = None if start is not None else np.asarray(noise_ref[name])
            noisy.append([by_name[name], start, np.radians(angles), ref])
    replays = [(by_name[n], np.asarray(p), np.asarray(v))
               for n, (p, v) in replay.items() if n in by_name]
    if record:
        paths = np.zeros((STEP_LIMIT + 1, len(bodies), 2))
        vels = np.zeros((STEP_LIMIT + 1, len(bodies), 2))

    # The original also counts B as in if it has left at step 701; we stop at
    # 700. The noise-free outcomes of all 20 videos are the same either way.
    while step <= STEP_LIMIT:
        for entry in noisy:
            body, start, rad, ref = entry
            if start is None:
                t = min(step, len(ref) - 1)
                d = body.position - tuple(ref[t])
                if d.x * d.x + d.y * d.y > tol * tol:
                    entry[1] = step
                continue
            if step > start:
                a = rad[step]
                c, s = math.cos(a), math.sin(a)
                vx, vy = body.velocity
                body.velocity = (vx * c - vy * s, vx * s + vy * c)
        for body, path, vel in replays:
            t = min(step, len(path) - 1)
            body.position = tuple(path[t])
            body.velocity = tuple(vel[t])
        if record:
            for i, body in enumerate(bodies):
                paths[step, i] = body.position
                vels[step, i] = body.velocity
        if not run.went_in and tb.position.x < EXIT_X:
            run.went_in = True
            run.exit_step = step
            run.b_end = tuple(tb.position)
            if not full_length:
                break
        space.step(DT)
        step += 1

    if run.b_end is None:
        run.b_end = tuple(tb.position)
    if record:
        run.paths = {n: paths[:step, i] for i, n in enumerate(names)}
        run.vels = {n: vels[:step, i] for i, n in enumerate(names)}
    return run
