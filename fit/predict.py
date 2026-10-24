"""Compute every model's p for every video and setting, and save them.

Output: results/predictions.csv with columns
    video, model, k, rule, theta, p
model 1 (full CSM), 2 (crowding noise; theta here is the per-video effective
noise theta0 + theta1 x (balls - 2)), 3 (how only), 4 (budget).
Replay i of a video uses the same random draws in every model and setting.
"""
import os
import sys
import zlib
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, balls, scenes  # noqa: E402
from sim.models import RULES, Real, budget, how, whether, whether_crowded  # noqa: E402

REPLAYS = 1000
THETAS = np.round(np.arange(0, 5.01, 0.1), 1)  # model 1 and 4 grid, as in the paper
THETA1S = np.round(np.arange(0, 2.01, 0.1), 1)  # model 2 slope grid
KS = (1, 2, 3)
SCENES = scenes()


def seed(video):
    return zlib.crc32(video.encode())


def crowd_thetas(video):
    """Every effective theta model 2 can reach in this video on the grid."""
    n = balls(video) - 2
    return sorted({round(t0 + t1 * n, 1) for t0 in THETAS for t1 in THETA1S})


def jobs():
    out = []
    for v, scene in SCENES.items():
        real = Real(scene)
        out.append((v, 3, 0, "", 0.0))
        for t in THETAS:
            out.append((v, 1, 0, "", t))
        sets = {}
        for k in KS:
            for rule in RULES:
                sets.setdefault(budget(real, k, rule), []).append((k, rule))
        for bset, labels in sets.items():
            for t in THETAS:
                out.append((v, 4, bset, labels, t))
        for t in crowd_thetas(v):
            out.append((v, 2, 0, "", t))
    return out


_real = {}


def run(job):
    v, model, bset, labels, t = job
    if v not in _real:
        _real[v] = Real(SCENES[v])
    real = _real[v]
    if model == 1:
        return [(v, 1, 0, "", t, whether(real, t, REPLAYS, seed(v)))]
    if model == 2:
        return [(v, 2, 0, "", t, whether_crowded(real, t, REPLAYS, seed(v)))]
    if model == 3:
        return [(v, 3, 0, "", 0.0, how(real))]
    p = whether(real, t, REPLAYS, seed(v), budget_balls=bset)
    return [(v, 4, k, rule, t, p) for k, rule in labels]


def main():
    todo = jobs()
    # long jobs first so the pool stays busy
    todo.sort(key=lambda j: (-balls(j[0]), j[1] != 2))
    print(len(todo), "jobs", flush=True)
    rows = []
    with Pool() as pool:
        for i, r in enumerate(pool.imap_unordered(run, todo, chunksize=4)):
            rows.extend(r)
            if i % 500 == 0:
                print(i, flush=True)
    df = pd.DataFrame(rows, columns=["video", "model", "k", "rule", "theta", "p"])
    df = df.sort_values(["model", "video", "k", "rule", "theta"])
    out = os.path.join(HERE, "results", "predictions.csv")
    df.to_csv(out, index=False)
    print("wrote", out, len(df))


if __name__ == "__main__":
    main()
