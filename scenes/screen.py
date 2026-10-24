"""Generate, filter, screen and select the test scenes.

Usage: python scenes/screen.py  (reads results/evaluation.json for the
plausible settings and the winning selection rule)

Stages, as in the spec:
1. Generate random scenes with 3 to 9 balls and keep the valid ones.
2. Noiseless pre-check: one run per model at noise 0 to find scenes where the
   models could disagree at all (a cheap way to skip hopeless candidates).
3. Screen: 100 replays per plausible setting.
4. Confirm the finalists with 1,000 replays per plausible setting.
5. Select by the rules (40-point disagreement, 12-point agreement).
"""
import json
import os
import sys
import zlib
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE  # noqa: E402
from scenes.generate import random_scene, valid  # noqa: E402
from sim.models import Real, budget, how, whether  # noqa: E402

OUT = os.path.join(HERE, "scenes", "work")
KINDS = ("clear", "hit", "k12", "k23")


def settings():
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    rule = ev["group"]["budget"]["best_setting"]["rule"]
    full = sorted({s["theta"] for s in ev["plausible_settings"]["full"]})
    bud = sorted({s["theta"] for s in ev["plausible_settings"]["budget"]})
    return rule, full, bud


def predict(real, rule, full_thetas, budget_thetas, n, seed):
    """Every model's p at every plausible setting: dict name -> array over thetas."""
    out = {"full": np.array([whether(real, t, n, seed) for t in full_thetas]),
           "how": np.array([how(real)])}
    for k in (1, 2, 3):
        b = budget(real, k, rule)
        out[f"k{k}"] = np.array([whether(real, t, n, seed, budget_balls=b) for t in budget_thetas])
    return out


def gaps(p):
    """The numbers the selection rules look at, in points (100 x p)."""
    bud = np.concatenate([p["k1"], p["k2"], p["k3"]]) * 100
    full = p["full"] * 100
    how_ = p["how"][0] * 100
    g = {}
    # smallest disagreement over every pair of plausible settings, with one direction
    lo, hi = bud.min() - full.max(), bud.max() - full.min()
    g["clear"] = max(-hi, lo, 0) if (hi < 0 or lo > 0) else 0.0
    lo, hi = bud.min() - how_, bud.max() - how_
    g["hit"] = max(-hi, lo, 0) if (hi < 0 or lo > 0) else 0.0
    d12 = (p["k1"] - p["k2"]) * 100
    d23 = (p["k2"] - p["k3"]) * 100
    g["d12_min"] = float(np.abs(d12).min()) if np.all(np.sign(d12) == np.sign(d12[0])) else 0.0
    g["d23_min"] = float(np.abs(d23).min()) if np.all(np.sign(d23) == np.sign(d23[0])) else 0.0
    g["d12_max"], g["d23_max"] = float(np.abs(d12).max()), float(np.abs(d23).max())
    return g


def kind_of(g, big=40, small=12):
    kinds = []
    if g["clear"] >= big:
        kinds.append("clear")
    if g["hit"] >= big:
        kinds.append("hit")
    if g["d12_min"] >= big and g["d23_max"] <= small:
        kinds.append("k12")
    if g["d23_min"] >= big and g["d12_max"] <= small:
        kinds.append("k23")
    return kinds


def stage1(i):
    """Generate scene i; return it with its noiseless predictions if it is valid."""
    rng = np.random.default_rng((2027, i))
    scene = random_scene(rng, int(rng.integers(3, 10)))
    if scene is None or valid(scene) is None:
        return None
    rule, full_t, bud_t = CFG
    real = Real(scene)
    p0 = predict(real, rule, [0.0], [0.0], 1, 0)
    return {"id": i, "scene": scene, "p0": {k: v.tolist() for k, v in p0.items()},
            "a_hits_b": real.first_hit is not None and real.first_hit[0] == "B"}


def promising(c):
    """Noiseless pre-check, loose on purpose: noise can move p, so keep any
    scene where the noiseless answers differ at all in the needed way."""
    p = {k: np.array(v) for k, v in c["p0"].items()}
    k1, k2, k3, full, h = p["k1"][0], p["k2"][0], p["k3"][0], p["full"][0], p["how"][0]
    return (min(abs(k1 - full), abs(k2 - full), abs(k3 - full)) > 0.5
            or min(abs(k1 - h), abs(k2 - h), abs(k3 - h)) > 0.5
            or abs(k1 - k2) > 0.5 or abs(k2 - k3) > 0.5)


def score(args):
    c, n = args
    rule, full_t, bud_t = CFG
    real = Real(c["scene"])
    p = predict(real, rule, full_t, bud_t, n, zlib.crc32(str(c["id"]).encode()))
    g = gaps(p)
    return {**c, f"p{n}": {k: v.tolist() for k, v in p.items()}, f"g{n}": g, f"kinds{n}": kind_of(g)}


CFG = None


def init(cfg):
    global CFG
    CFG = cfg


def main(n_scenes=20000, need=5):
    cfg = settings()
    print("rule", cfg[0], "plausible theta: full", cfg[1], "budget", cfg[2], flush=True)
    os.makedirs(OUT, exist_ok=True)
    with Pool(initializer=init, initargs=(cfg,)) as pool:
        cands = [c for c in pool.imap_unordered(stage1, range(n_scenes), chunksize=20) if c]
        print("valid", len(cands), flush=True)
        keep = [c for c in cands if promising(c)]
        print("promising", len(keep), flush=True)
        screened = pool.map(score, [(c, 100) for c in keep], chunksize=2)
        counts = {k: sum(k in c["kinds100"] for c in screened) for k in KINDS}
        print("screen pass counts", counts, flush=True)
        # finalists: screen passes, plus near misses (within 10 points of a line)
        fin = [c for c in screened if c["kinds100"] or
               kind_of(c["g100"], big=30, small=22)]
        confirmed = pool.map(score, [(c, 1000) for c in fin], chunksize=1)
    counts = {k: sum(k in c["kinds1000"] for c in confirmed) for k in KINDS}
    print("confirmed counts", counts, flush=True)
    json.dump({"settings": cfg, "n_generated": n_scenes, "n_valid": len(cands),
               "n_promising": len(keep), "confirmed": confirmed},
              open(os.path.join(OUT, "candidates.json"), "w"))


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
