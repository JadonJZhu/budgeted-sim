"""Reproduction checkpoint: the full CSM (model 1) at theta = 1.9 on all 20
videos, 1,000 replays each, repeated with 20 seeds. Reports r and RMSE against
people's mean flipped whether ratings, scored as in the paper (100 x p, no
rescaling)."""
import os
import sys
import zlib
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, ratings, scenes  # noqa: E402
from sim.models import Real, whether  # noqa: E402

THETA, REPLAYS, SEEDS = 1.9, 1000, 20
SCENES = scenes()


def job(args):
    video, seed = args
    return video, seed, whether(Real(SCENES[video]), THETA, REPLAYS, seed=(seed, zlib.crc32(video.encode())))


def main():
    jobs = [(v, s) for v in SCENES for s in range(SEEDS)]
    with Pool() as pool:
        rows = pool.map(job, jobs)
    df = pd.DataFrame(rows, columns=["video", "seed", "p"])
    out = os.path.join(HERE, "results", "reproduction.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)

    people = ratings("whether").groupby("video").rating.mean()
    stats = []
    for seed, g in df.groupby("seed"):
        g = g.set_index("video").p * 100
        h = people[g.index]
        stats.append((np.corrcoef(g, h)[0, 1], np.sqrt(((g - h) ** 2).mean())))
    r, rmse = np.array(stats).T
    print(f"r over {SEEDS} seeds: mean {r.mean():.3f}, sd {r.std(ddof=1):.3f}, "
          f"range {r.min():.3f} to {r.max():.3f}")
    print(f"RMSE: mean {rmse.mean():.2f}, range {rmse.min():.2f} to {rmse.max():.2f}")
    print("Paper: r = .694 (text) / .684 (Figure 5), RMSE = 28.11")
    nine = df[df.video == "9ball_w_only_1"].p
    print(f"9ball_w_only_1: p from {nine.min():.3f} to {nine.max():.3f}")


if __name__ == "__main__":
    main()
