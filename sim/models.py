"""The whether and how checks, and the models built on them.

Every whether model returns p, the share of replays in which B misses once A
is gone. Noise draws use common random numbers: replay i of a scene always
uses the same standard normal draws, scaled by theta, so p changes smoothly
with theta and differences between settings are not sampling noise.
"""
import json
from functools import lru_cache

import numpy as np

from .physics import STEP_LIMIT, on_table, simulate

CAUSE, TARGET = "A", "B"
HOW_SHIFT = 1e-3  # pixels; small enough that A hits the same balls at the same steps


def load_scenes(path):
    with open(path) as f:
        return {t["trial"]: t["balls"] for t in json.load(f)}


class Real:
    """The real video: full paths, the contact log and what the rules can see."""

    def __init__(self, scene):
        self.scene = scene
        run = simulate(scene, record=True, full_length=True)
        self.run = run
        self.paths = run.paths
        self.vels = run.vels
        self.went_in = run.went_in
        self.names = [b["name"] for b in scene]
        contacts = run.contacts
        # the ball A hit first, counting only contacts where that ball is on the table
        self.first_hit = None
        for step, n1, n2, p1, p2 in contacts:
            if CAUSE in (n1, n2):
                other, pos = (n2, p2) if n1 == CAUSE else (n1, p1)
                if on_table(pos):
                    self.first_hit = (other, step)
                    break
        self.a_targets = _unique(n2 if n1 == CAUSE else n1
                                 for s, n1, n2, _, _ in contacts if CAUSE in (n1, n2))
        b_contacts = [(s, n2 if n1 == TARGET else n1)
                      for s, n1, n2, _, _ in contacts if TARGET in (n1, n2)]
        self.b_contacts = _unique(n for s, n in reversed(b_contacts))
        self.near_b = self._near_b_path()

    def _near_b_path(self):
        # B's path while on the table, against every point of each other ball's path
        b = self.paths[TARGET][: (self.run.exit_step or STEP_LIMIT) + 1]
        b = b[(b[:, 0] >= 0)]
        dist = {}
        for name, path in self.paths.items():
            if name in (CAUSE, TARGET):
                continue
            p = path[(path[:, 0] >= 0) & (path[:, 0] <= 1000)]
            if len(p) == 0:
                continue  # never on the table, so never visible
            d = np.sqrt(((p[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min()
            dist[name] = d
        return sorted(dist, key=dist.get)


def _unique(seq):
    out = []
    for x in seq:
        if x not in out and x not in (CAUSE, TARGET):
            out.append(x)
    return out


RULES = ("a_targets", "b_contacts", "near_b")


def budget(real, k, rule):
    """B first, then up to k - 1 balls in the rule's order (fewer if it runs out)."""
    return (TARGET,) + tuple(getattr(real, rule)[: k - 1])


def _normals(seed, n, slots):
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, slots, STEP_LIMIT + 1))


def whether(real, theta, n, seed, budget_balls=None):
    """Models 1 and 4. Noise goes on the ball A hit first, from that hit on.

    budget_balls None: full simulation (model 1). Otherwise only those balls are
    simulated and the rest replay the real paths (model 4); the noise then
    applies only if the ball A hit first is in the budget.
    """
    replay = None
    if budget_balls is not None:
        replay = {m: (real.paths[m], real.vels[m]) for m in real.names
                  if m not in budget_balls and m != CAUSE}
    hit = real.first_hit
    noisy = hit is not None and theta > 0 and (budget_balls is None or hit[0] in budget_balls)
    if not noisy:
        n = 1
    z = _normals(seed, n, 1) if noisy else None
    missed = 0
    for i in range(n):
        noise = {hit[0]: (hit[1], theta * z[i, 0])} if noisy else None
        run = simulate(real.scene, leave_out=(CAUSE,), noise=noise, replay=replay)
        missed += real.went_in and not run.went_in
    return missed / n


def whether_crowded(real, theta, n, seed):
    """Model 2's simulation: noise on every ball whose path changes once A is gone,
    from the step its path first differs from the real video."""
    others = [m for m in real.names if m != CAUSE]
    if theta == 0:
        n = 1
    z = _normals(seed, n, len(others))
    ref = {m: real.paths[m] for m in others}
    missed = 0
    for i in range(n):
        noise = {m: (None, theta * z[i, j]) for j, m in enumerate(others)} if theta > 0 else None
        run = simulate(real.scene, leave_out=(CAUSE,), noise=noise, noise_ref=ref)
        missed += real.went_in and not run.went_in
    return missed / n


def how(real, shift=HOW_SHIFT):
    """Model 3. Nudge A's start position; A is a how cause if B ends differently."""
    run = simulate(real.scene, shift=(CAUSE, shift, shift))
    base = real.run
    return float(run.exit_step != base.exit_step or run.b_end != base.b_end)
