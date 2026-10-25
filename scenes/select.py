"""Choose the final test scenes from the confirmed candidates, check simple
cues, and run model recovery.

Usage: python scenes/select.py [big small cue]   (defaults 40 12 .3)

Selection is by fixed rules, so no scene is picked by hand:
- A scene qualifies for a kind if it passes that kind's rule at 1,000 replays
  over every plausible setting (see scenes/screen.py).
- Which-model kinds need 8 scenes each, which-setting kinds 4 each. Within a
  kind, scenes are taken in order of their margin (largest first), cycling
  over ball-count bins (3 to 4, 5 to 7, 8 to 9) so they spread across crowding.
  A scene is used at most once.
- Simple-cue check: across the chosen scenes, none of the cues may correlate
  with the budget model's predicted gap to any rival above |r| = cue. If one
  does, the scene that contributes most to that correlation is swapped for the
  next qualifying scene of its kind, and the check repeats.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, balls, ratings, scenes  # noqa: E402
from fit.evaluate import full_fit, grids, scale_fit  # noqa: E402
from scenes.recovery import recover, residual_pool  # noqa: E402
from scenes.screen import KINDS, NEED, crowd_thetas, gaps, kind_of, margin  # noqa: E402
from sim.models import Real  # noqa: E402

WORK = os.path.join(HERE, "scenes", "work")
ANCHORS = ["2ball_h_only_1", "3ball_w_only_1", "9ball_w_only_1", "12ball_both_1"]
BINS = [(3, 4), (5, 7), (8, 9)]


def qualifying(cands, big, small):
    out = {k: [] for k in KINDS}
    for c in cands:
        g = gaps({k: np.array(v) for k, v in c["p1000"].items()})
        for k in kind_of(g, big, small):
            out[k].append((margin(g, k), c))
    for k in out:
        out[k].sort(key=lambda t: -t[0])
    return out


def pick(qual, used=()):
    chosen, used = {}, set(used)
    for kind, need in NEED.items():
        bins = [[c for m, c in qual[kind] if lo <= len(c["scene"]) <= hi] for lo, hi in BINS]
        got = []
        while len(got) < need and any(bins):
            for b in bins:
                while b and b[0]["id"] in used:
                    b.pop(0)
                if b and len(got) < need:
                    c = b.pop(0)
                    got.append(c)
                    used.add(c["id"])
        chosen[kind] = got
    return chosen


def cues(c):
    real = Real(c["scene"])
    a, b = real.paths["A"], real.paths["B"]
    n = min(len(a), len(b))
    ab = np.hypot(*(a[:n] - b[:n]).T).min()
    near = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min() < 60 + 60
    return {"closest_A_B": ab, "collisions": len(real.run.contacts),
            "balls": len(c["scene"]), "A_near_B_path": float(near)}


def model_gaps(c):
    p = c["p1000"]
    bud = np.mean(p["k1"] + p["k2"] + p["k3"])
    return {"vs_full": bud - np.mean(p["full"]), "vs_how": bud - p["how"][0],
            "vs_crowd": bud - np.mean(p["crowd"])}


def cue_table(chosen):
    rows = []
    for kind, cs in chosen.items():
        for c in cs:
            rows.append({"id": c["id"], "kind": kind, **cues(c), **model_gaps(c)})
    return pd.DataFrame(rows)


def worst_cue(df):
    worst = (0, None, None)
    for cue in ("closest_A_B", "collisions", "balls", "A_near_B_path"):
        for gap in ("vs_full", "vs_how", "vs_crowd"):
            if df[cue].std() == 0:
                continue
            r = np.corrcoef(df[cue], df[gap])[0, 1]
            if abs(r) > abs(worst[0]):
                worst = (r, cue, gap)
    return worst


def cue_check(qual, line, max_swaps=60):
    chosen = pick(qual)
    swaps, dropped = 0, set()
    while True:
        df = cue_table(chosen)
        r, cue, gap = worst_cue(df)
        if abs(r) < line or swaps >= max_swaps:
            return chosen, df, (r, cue, gap), swaps
        # the scene contributing most to this correlation
        z = (df[cue] - df[cue].mean()) * (df[gap] - df[gap].mean()) * np.sign(r)
        bad = df.loc[z.idxmax()]
        dropped.add(int(bad.id))
        used = {c["id"] for cs in chosen.values() for c in cs} | dropped
        kind = bad.kind
        rest = [c for c in chosen[kind] if c["id"] != bad.id]
        repl = [c for m, c in qual[kind] if c["id"] not in used]
        if not repl:
            return chosen, df, (r, cue, gap), swaps
        chosen[kind] = rest + [repl[0]]
        swaps += 1


# ---------- model recovery on the chosen scenes plus the anchors

def recovery_grids(chosen, cfg, pred, G_orig, videos):
    """Each model's p over its plausible settings, on new scenes then anchors."""
    new = [c for cs in chosen.values() for c in cs]
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    ps = ev["plausible_settings"]
    full_t = cfg["confirm"]["full"]
    bud_t = cfg["confirm"]["budget"]
    idx = [videos.index(v) for v in ANCHORS]

    def orig(name, keep):
        s, P = G_orig[name]
        rows = [i for i, st in enumerate(s) if keep(st)]
        return [s[i] for i in rows], P[np.ix_(rows, idx)]

    s_f, P_f = orig("full", lambda st: st["theta"] in full_t)
    full = (s_f, np.hstack([np.array([[c["p1000"]["full"][full_t.index(st["theta"])] for c in new]
                                      for st in s_f]), P_f]))
    s_b, P_b = orig("budget", lambda st: st["rule"] == cfg["rule"] and st["theta"] in bud_t)
    bud = (s_b, np.hstack([np.array([[c["p1000"][f"k{st['k']}"][bud_t.index(st["theta"])] for c in new]
                                     for st in s_b]), P_b]))
    how = (G_orig["how"][0], np.hstack([np.array([[c["p1000"]["how"][0] for c in new]]),
                                         G_orig["how"][1][:, idx]]))
    pairs = [(s["theta0"], s["theta1"]) for s in ps["crowding"]]
    s_c, P_c = orig("crowding", lambda st: (st["theta0"], st["theta1"]) in pairs)
    rows = []
    for st in s_c:
        row = []
        for c in new:
            grid = crowd_thetas(cfg, len(c["scene"]), cfg["confirm"]["crowd_step"])
            eff = st["theta0"] + st["theta1"] * (len(c["scene"]) - 2)
            row.append(np.interp(eff, grid, c["p1000"]["crowd"]))
        rows.append(row)
    crowd = (s_c, np.hstack([np.array(rows), P_c]))
    return {"full": full, "how": how, "budget": bud, "crowding": crowd}


def generators(models, G_orig, y, rule):
    """Each model at its best fit to the existing data, with its fitted scale.
    The budget model contributes one generator per k."""
    out = []
    for name in ("full", "how", "crowding"):
        s, a, b, _ = full_fit(G_orig[name], y)
        st = G_orig[name][0][s]
        row = models[name][0].index(st) if st in models[name][0] else 0
        out.append((name, name, None, a + b * models[name][1][row]))
    for k in (1, 2, 3):
        s_all, P_all = G_orig["budget"]
        keep = [i for i, st in enumerate(s_all) if st["k"] == k and st["rule"] == rule]
        a, b, sse = scale_fit(P_all[keep], y, np.ones(len(y)))
        i = int(np.argmin(sse))
        st = s_all[keep[i]]
        row = models["budget"][0].index(st)
        out.append((f"budget_k{k}", "budget", k, a[i] + b[i] * models["budget"][1][row]))
    return out


def main(big=40, small=12, line=0.3, write=True):
    data = json.load(open(os.path.join(WORK, "candidates.json")))
    cfg = data["settings"]
    qual = qualifying(data["confirmed"], big, small)
    counts = {k: len(v) for k, v in qual.items()}
    print("qualifying at", big, small, counts, flush=True)
    chosen, df, worst, swaps = cue_check(qual, line)
    print("chosen", {k: len(v) for k, v in chosen.items()}, "worst cue r", worst, "swaps", swaps, flush=True)

    pred = pd.read_csv(os.path.join(HERE, "results", "predictions.csv"), keep_default_na=False)
    W = ratings("whether")
    videos = sorted(W.video.unique(), key=lambda v: (balls(v), v))
    wide = W.pivot_table(index="person", columns="video", values="rating")[videos]
    y = wide.mean().to_numpy()
    G = grids(pred, videos)
    models = recovery_grids(chosen, cfg, pred, G, videos)
    rec = recover(models, generators(models, G, y, cfg["rule"]), residual_pool(wide))
    print("recovery", rec, flush=True)
    passed = all(v["model_share"] >= 0.9 and (v["k_share"] is None or v["k_share"] >= 0.8)
                 for v in rec.values())
    result = {"big": big, "small": small, "cue_line": line, "qualifying": counts,
              "chosen": {k: [c["id"] for c in v] for k, v in chosen.items()},
              "worst_cue": [float(worst[0]), worst[1], worst[2]], "swaps": swaps,
              "recovery": rec, "recovery_passed": passed}
    if write:
        out = os.path.join(HERE, "results", f"selection_{big}_{small}_{line}.json")
        json.dump(result, open(out, "w"), indent=1)
        df.to_csv(os.path.join(HERE, "results", f"cues_{big}_{small}_{line}.csv"), index=False)
    return result, chosen


if __name__ == "__main__":
    args = [float(a) for a in sys.argv[1:]]
    main(*args)
