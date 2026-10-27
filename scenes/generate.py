"""Random candidate scenes and the validity filter.

Start positions and speeds follow the ranges in the original 20 videos:
- A enters from the right (x 1032 to 1150, y 62 to 688) moving left, velocity
  x -1.4 to -0.9, y -0.6 to 0.4 (scene units; times 120 for pixels per second).
- About half of the other balls move. Moving balls enter from the right like A
  (velocity x -1.5 to -0.8, y -0.6 to 0.6). Still balls sit in the middle band
  of the table (x 125 to 900, y 150 to 600; the originals use x 125 to 741,
  y 276 to 475, and we widen this so more layouts are possible).
"""
import numpy as np

from sim.physics import GATE_Y, RADIUS, WIDTH, on_table, simulate

NAMES = "ABCDEFGHIJKLMNOP"
GATE_MARGIN = 10  # pixels of clearance past the ball's edge at the gate
MIN_GAP_STEPS = 10  # 0.2 seconds
NEAR = 150  # pixels: "same area" for the collision spacing rule
LENGTH = (7, 13)  # seconds, as in the originals


def random_scene(rng, n_balls):
    balls = []
    taken = []

    def free(p):
        return all(np.hypot(p[0] - q[0], p[1] - q[1]) > 2 * RADIUS + 10 for q in taken)

    for i in range(n_balls):
        name = NAMES[i]
        for _ in range(200):
            if name == "A":
                pos = [rng.uniform(1032, 1150), rng.uniform(62, 688)]
                vel = [rng.uniform(-1.4, -0.9), rng.uniform(-0.6, 0.4)]
            elif rng.random() < 0.5:
                pos = [rng.uniform(1032, 1150), rng.uniform(62, 688)]
                vel = [rng.uniform(-1.5, -0.8), rng.uniform(-0.6, 0.6)]
            else:
                pos = [rng.uniform(125, 900), rng.uniform(150, 600)]
                vel = [0.0, 0.0]
            if free(pos):
                break
        else:
            return None
        taken.append(pos)
        balls.append({"name": name, "position": [round(x, 2) for x in pos],
                      "velocity": [round(x, 2) for x in vel]})
    return balls


def valid(scene):
    """The validity filter. Returns the real run if the scene passes, else None."""
    run = simulate(scene, record=True)
    if not run.went_in:
        return None
    length = (run.exit_step + 30) / 50
    if not LENGTH[0] <= length <= LENGTH[1]:
        return None
    # B passes the gate with room to spare: its center at the gate line is
    # far enough inside the opening
    b = run.paths["B"]
    i = np.argmax(b[:, 0] < 25)
    if not (GATE_Y[0] + RADIUS + GATE_MARGIN <= b[i, 1] <= GATE_Y[1] - RADIUS - GATE_MARGIN):
        return None
    # every collision happens on the table
    for step, n1, n2, p1, p2 in run.contacts:
        if not (on_table(p1) and on_table(p2)):
            return None
    # A comes onto the table
    if run.paths["A"][:, 0].min() > WIDTH - RADIUS:
        return None
    # no two collisions too close in time and place
    c = run.contacts
    for j in range(len(c)):
        for k in range(j + 1, len(c)):
            if c[k][0] - c[j][0] >= MIN_GAP_STEPS:
                break
            mid_j = np.add(c[j][3], c[j][4]) / 2
            mid_k = np.add(c[k][3], c[k][4]) / 2
            if np.hypot(*(mid_j - mid_k)) < NEAR:
                return None
    return run
