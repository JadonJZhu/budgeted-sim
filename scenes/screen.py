"""Generate, filter, screen and select the test scenes.

Usage: python scenes/screen.py [n_scenes]  (500000 for the included results;
reads results/evaluation.json for the plausible settings and the winning
selection rule)

Stages:
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
from sim.models import Real, budget, how, whether, whether_crowded  # noqa: E402

OUT = os.path.join(HERE, "scenes", "work")
KINDS = ("clear", "hit", "crowd", "k12", "k23")


def thin(values, step=None):
    """Grid points every `step`, always keeping both ends of the range.
    step None: the two ends and the middle."""
    lo, hi = min(values), max(values)
    if step is None:
        return sorted({float(lo), float(round((lo + hi) / 2, 1)), float(hi)})
    pts = set(np.round(np.arange(lo, hi + 1e-9, step), 1)) | {lo, hi}
    return sorted(float(x) for x in pts)


def settings():
    """Plausible settings from the fit to the existing data.

    The budget model's noise range is that of its winning k and rule, used for
    every k from 1 to 3 (all three sizes count as plausible). Screening
    uses the ends and middle of each range; confirmation uses steps of 0.2 for
    the CSM and budget, and 0.5 for crowding noise's per-scene effective noise
    (p changes smoothly with noise because the random draws are shared)."""
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    ps = ev["plausible_settings"]
    best = ev["group"]["budget"]["best_setting"]
    rule = best["rule"]
    full = [s["theta"] for s in ps["full"]]
    bud = [s["theta"] for s in ps["budget"] if s["rule"] == rule and s["k"] == best["k"]]
    crowd = [(s["theta0"], s["theta1"]) for s in ps["crowding"]]
    return {"rule": rule,
            "screen": {"full": thin(full), "budget": thin(bud), "crowd_step": None},
            "confirm": {"full": thin(full, 0.2), "budget": thin(bud, 0.2), "crowd_step": 0.5},
            "crowd_pairs": crowd}


def crowd_thetas(cfg, n_balls, step):
    eff = [t0 + t1 * (n_balls - 2) for t0, t1 in cfg["crowd_pairs"]]
    return thin([round(e, 1) for e in eff], step)


def predict(real, cfg, stage, n, seed):
    """Every model's p at every plausible setting: dict name -> array over settings."""
    st = cfg[stage]
    out = {"full": np.array([whether(real, t, n, seed) for t in st["full"]]),
           "how": np.array([how(real)]),
           "crowd": np.array([whether_crowded(real, t, n, seed)
                              for t in crowd_thetas(cfg, len(real.names), st["crowd_step"])])}
    for k in (1, 2, 3):
        b = budget(real, k, cfg["rule"])
        out[f"k{k}"] = np.array([whether(real, t, n, seed, budget_balls=b) for t in st["budget"]])
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
    crowd = p["crowd"] * 100
    lo, hi = bud.min() - crowd.max(), bud.max() - crowd.min()
    g["crowd"] = max(-hi, lo, 0) if (hi < 0 or lo > 0) else 0.0
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
    if g["crowd"] >= big:
        kinds.append("crowd")
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
    real = Real(scene)
    zero = {"zero": {"full": [0.0], "budget": [0.0], "crowd_step": None}, "rule": CFG["rule"],
            "crowd_pairs": [(0.0, 0.0)]}
    p0 = predict(real, zero, "zero", 1, 0)
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
    real = Real(c["scene"])
    p = predict(real, CFG, "screen" if n == 100 else "confirm", n, zlib.crc32(str(c["id"]).encode()))
    g = gaps(p)
    return {**c, f"p{n}": {k: v.tolist() for k, v in p.items()}, f"g{n}": g, f"kinds{n}": kind_of(g)}


CFG = None


def init(cfg):
    global CFG
    CFG = cfg


NEED = {"clear": 8, "hit": 8, "crowd": 8, "k12": 4, "k23": 4}
FINALISTS = 5  # confirm this many times the scenes each kind needs


def direction(p, kind):
    """Which-setting scenes come in both directions, so that every budget size
    predicts 'A mattered' in some scenes and 'A did not matter' in others.
    Without this, a budget of 1 predicts the same answer for every scene and
    cannot be recovered."""
    if kind == "k12":
        return "up" if np.mean(p["k1"]) > np.mean(p["k2"]) else "down"
    if kind == "k23":
        return "up" if np.mean(p["k2"]) > np.mean(p["k3"]) else "down"
    return None


def slots(kind, need=NEED):
    """(direction, scenes needed) for a kind."""
    if kind in ("k12", "k23"):
        return [("up", need[kind] // 2), ("down", need[kind] - need[kind] // 2)]
    return [(None, need[kind])]


def margin(g, kind):
    """How far a scene clears its kind's rule, in points."""
    return {"clear": g["clear"], "hit": g["hit"], "crowd": g["crowd"],
            "k12": g["d12_min"] - g["d23_max"], "k23": g["d23_min"] - g["d12_max"]}[kind]


def run_stage(pool, items, n, path):
    """Score items with n replays, appending each result to a JSON-lines file
    so an interrupted run resumes where it stopped."""
    done = {}
    if os.path.exists(path):
        for line in open(path):
            c = json.loads(line)
            done[c["id"]] = c
    todo = [(c, n) for c in items if c["id"] not in done]
    print(f"{n} replays: {len(done)} done, {len(todo)} to go", flush=True)
    with open(path, "a") as f:
        for i, c in enumerate(pool.imap_unordered(score, todo, chunksize=1)):
            f.write(json.dumps(c) + "\n")
            f.flush()
            done[c["id"]] = c
            if i % 100 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    return [done[c["id"]] for c in items]


def main(n_scenes=500000):
    cfg = settings()
    print("settings", {k: v for k, v in cfg.items() if k != "crowd_pairs"}, flush=True)
    os.makedirs(OUT, exist_ok=True)
    prom_path = os.path.join(OUT, "promising.json")
    with Pool(initializer=init, initargs=(cfg,)) as pool:
        saved = json.load(open(prom_path)) if os.path.exists(prom_path) else None
        if saved is not None and saved["n_generated"] == n_scenes:
            n_valid, keep = saved["n_valid"], saved["promising"]
        else:
            cands = [c for c in pool.imap_unordered(stage1, range(n_scenes), chunksize=500) if c]
            keep = sorted((c for c in cands if promising(c)), key=lambda c: c["id"])
            n_valid = len(cands)
            json.dump({"n_generated": n_scenes, "n_valid": n_valid, "promising": keep},
                      open(prom_path, "w"))
        print("valid", n_valid, "promising", len(keep), flush=True)
        screened = run_stage(pool, keep, 100, os.path.join(OUT, "screened.jsonl"))
        screen_counts = {k: sum(k in c["kinds100"] for c in screened) for k in KINDS}
        print("screen pass counts", screen_counts, flush=True)
        # finalists: each kind's strongest screen passes, FINALISTS x what it needs
        fin = {}
        for kind in KINDS:
            for d, need in slots(kind):
                passing = [c for c in screened if kind in c["kinds100"]
                           and direction(c["p100"], kind) == d]
                passing.sort(key=lambda c: -margin(c["g100"], kind))
                for c in passing[: FINALISTS * need]:
                    fin[c["id"]] = c
        fin = sorted(fin.values(), key=lambda c: c["id"])
        print("finalists", len(fin), flush=True)
        confirmed = run_stage(pool, fin, 1000, os.path.join(OUT, "confirmed.jsonl"))
    confirmed_counts = {k: sum(k in c["kinds1000"] for c in confirmed) for k in KINDS}
    print("confirmed counts", confirmed_counts, flush=True)
    json.dump({"settings": cfg, "n_generated": n_scenes, "n_valid": n_valid, "n_promising": len(keep),
               "screen_counts": screen_counts, "confirmed_counts": confirmed_counts, "confirmed": confirmed},
              open(os.path.join(OUT, "candidates.json"), "w"))


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:]))
