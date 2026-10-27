"""Choose the final test scenes from the confirmed candidates, check simple
cues, and run model recovery.

Usage: python scenes/select.py [big small cue [scale]]  (defaults 40 12 .3 1; scale
multiplies the scenes needed per kind)

Selection is by fixed rules, so no scene is picked by hand:
- Scenes where A or B passes within 6 pixels of another ball without touching
  it are excluded, since a viewer could not tell whether they touched.
- A scene qualifies for a kind if it passes that kind's rule at 1,000 replays
  over every plausible setting (see scenes/screen.py).
- Which-model kinds need 8 scenes each, which-setting kinds 4 each. Within a
  kind, scenes are taken in order of their margin (largest first), cycling
  over ball-count bins (3 to 4, 5 to 7, 8 to 9) so they spread across crowding.
  A scene is used at most once.
- Simple-cue check: across the chosen scenes, none of the cues may correlate
  with the budget model's predicted gap to any rival (or between budget sizes)
  above |r| = cue. If one does, the scene that contributes most is swapped for
  the next qualifying scene of its kind and direction, and the check repeats.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, balls, ratings  # noqa: E402
from fit.evaluate import full_fit, grids, scale_fit  # noqa: E402
from scenes.recovery import recover, recover_mixed  # noqa: E402
from scenes.screen import KINDS, NEED, crowd_thetas, direction, gaps, kind_of, margin, slots  # noqa: E402
from sim.models import Real  # noqa: E402
from sim.physics import RADIUS, WIDTH, simulate  # noqa: E402

WORK = os.path.join(HERE, "scenes", "work")
ANCHORS = ["2ball_h_only_1", "3ball_w_only_1", "9ball_w_only_1", "12ball_both_1"]
BINS = [(3, 4), (5, 7), (8, 9)]


NEAR_MISS = 6  # pixels between edges


def unclear_contact(scene):
    """True if A or B passes within NEAR_MISS pixels of another ball without
    touching it, so a viewer could not tell whether they touched."""
    run = simulate(scene, record=True, full_length=True)
    end = run.exit_step + 30
    touched = {frozenset((a, b)) for _, a, b, _, _ in run.contacts}
    for a in ("A", "B"):
        for b, pb in run.paths.items():
            if b == a or frozenset((a, b)) in touched:
                continue
            pa, pb = run.paths[a][:end], pb[:end]
            on = (pa[:, 0] > 0) & (pa[:, 0] < WIDTH) & (pb[:, 0] > 0) & (pb[:, 0] < WIDTH)
            if on.any() and np.hypot(*(pa[on] - pb[on]).T).min() < 2 * RADIUS + NEAR_MISS:
                return True
    return False


def qualifying(cands, big, small):
    out = {k: [] for k in KINDS}
    cands = [c for c in cands if not unclear_contact(c["scene"])]
    for c in cands:
        g = gaps({k: np.array(v) for k, v in c["p1000"].items()})
        for k in kind_of(g, big, small):
            out[k].append((margin(g, k), c))
    for k in out:
        out[k].sort(key=lambda t: -t[0])
    return out


def pick(qual, need, used=()):
    chosen, used = {}, set(used)
    for kind in need:
        got = []
        for d, n in slots(kind, need):
            pool = [c for m, c in qual[kind] if direction(c["p1000"], kind) == d]
            bins = [[c for c in pool if lo <= len(c["scene"]) <= hi] for lo, hi in BINS]
            part = []
            while len(part) < n and any(bins):
                for b in bins:
                    while b and b[0]["id"] in used:
                        b.pop(0)
                    if b and len(part) < n:
                        c = b.pop(0)
                        part.append(c)
                        used.add(c["id"])
            got += part
        chosen[kind] = got
    return chosen


def cues(c):
    real = Real(c["scene"])
    a, b = real.paths["A"], real.paths["B"]
    n = min(len(a), len(b))
    ab = np.hypot(*(a[:n] - b[:n]).T).min()
    # A's path passes within 120 pixels (two ball widths, center to center) of B's path
    near = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min() < 4 * RADIUS
    return {"closest_A_B": ab, "collisions": len(real.run.contacts),
            "balls": len(c["scene"]), "A_near_B_path": float(near)}


def model_gaps(c):
    p = c["p1000"]
    bud = np.mean(p["k1"] + p["k2"] + p["k3"])
    return {"vs_full": bud - np.mean(p["full"]), "vs_how": bud - p["how"][0],
            "vs_crowd": bud - np.mean(p["crowd"]),
            "k1_k2": np.mean(p["k1"]) - np.mean(p["k2"]),
            "k2_k3": np.mean(p["k2"]) - np.mean(p["k3"])}


CUES = ("closest_A_B", "collisions", "balls", "A_near_B_path")
GAPS = ("vs_full", "vs_how", "vs_crowd", "k1_k2", "k2_k3")


def cue_table(chosen):
    rows = []
    for kind, cs in chosen.items():
        for c in cs:
            rows.append({"id": c["id"], "kind": kind, **cues(c), **model_gaps(c)})
    return pd.DataFrame(rows)


def z(x):
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else x * 0


def worst_cue(df):
    """The largest correlation, across the whole set, between a crude cue and
    the budget model's gap to any rival (or between budget sizes)."""
    worst = (0.0, None, None)
    for cue in CUES:
        for gap in GAPS:
            if df[cue].std() == 0 or df[gap].std() == 0:
                continue
            r = float(np.corrcoef(df[cue], df[gap])[0, 1])
            if abs(r) > abs(worst[0]):
                worst = (r, cue, gap)
    return worst


def all_cue_r(df):
    return {f"{c}~{g}": round(float(np.corrcoef(df[c], df[g])[0, 1]), 2)
            for c in CUES for g in GAPS if df[c].std() > 0 and df[g].std() > 0}


def cue_check(qual, line, need, max_swaps=300):
    """Swap scenes (same kind and direction, next in line) until no cue passes
    the line, or no swap helps."""
    chosen = pick(qual, need)
    swaps, dropped = 0, set()
    while True:
        df = cue_table(chosen)
        r, cue, gap = worst_cue(df)
        if abs(r) < line or swaps >= max_swaps:
            return chosen, df, (r, cue, gap), swaps
        contrib = (z(df[cue]) * z(df[gap]) * np.sign(r)).sort_values(ascending=False)
        used = {c["id"] for cs in chosen.values() for c in cs} | dropped
        for i in contrib.index:
            if contrib[i] <= 0:
                return chosen, df, (r, cue, gap), swaps
            bad = df.loc[i]
            kind = bad.kind
            d = direction(next(c for c in chosen[kind] if c["id"] == bad.id)["p1000"], kind)
            repl = [c for m, c in qual[kind] if c["id"] not in used
                    and direction(c["p1000"], kind) == d]
            if repl:
                dropped.add(int(bad.id))
                chosen[kind] = [c for c in chosen[kind] if c["id"] != bad.id] + [repl[0]]
                swaps += 1
                break
        else:
            return chosen, df, (r, cue, gap), swaps


# ---------- model recovery on the chosen scenes plus the anchors

def recovery_grids(chosen, cfg, ps, G_orig, videos):
    """Each model's p over its plausible settings (ps, from evaluation.json),
    on new scenes then anchors."""
    new = [c for cs in chosen.values() for c in cs]
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
    """Each model at its best setting on the existing data. The budget model
    contributes one generator per k. Returns (label, model, k, p on the test
    set, p on the 20 original videos)."""
    def row_of(name, st):
        if st not in models[name][0]:
            raise ValueError(f"{name} setting {st} is not in the test-set grid")
        return models[name][0].index(st)

    out = []
    for name in ("full", "how", "crowding"):
        s, *_ = full_fit(G_orig[name], y)
        st = G_orig[name][0][s]
        out.append((name, name, None, models[name][1][row_of(name, st)], G_orig[name][1][s]))
    s_all, P_all = G_orig["budget"]
    for k in (1, 2, 3):
        keep = [i for i, st in enumerate(s_all) if st["k"] == k and st["rule"] == rule]
        _, _, sse = scale_fit(P_all[keep], y, np.ones(len(y)))
        i = keep[int(np.argmin(sse))]
        out.append((f"budget_k{k}", "budget", k, models["budget"][1][row_of("budget", s_all[i])], P_all[i]))
    return out


def main(big=40, small=12, line=0.3, write=True, scale=1.0):
    need = {k: max(2 if k in ("k12", "k23") else 1, int(round(v * scale))) for k, v in NEED.items()}
    data = json.load(open(os.environ.get("CANDIDATES", os.path.join(WORK, "candidates.json"))))
    cfg = data["settings"]
    qual = qualifying(data["confirmed"], big, small)
    counts = {k: len(v) for k, v in qual.items()}
    print("qualifying at", big, small, counts, flush=True)
    chosen, df, worst, swaps = cue_check(qual, line, need)
    print("chosen", {k: len(v) for k, v in chosen.items()}, "worst cue r", worst, "swaps", swaps, flush=True)

    pred = pd.read_csv(os.path.join(HERE, "results", "predictions.csv"), keep_default_na=False)
    W = ratings("whether")
    videos = sorted(W.video.unique(), key=lambda v: (balls(v), v))
    wide = W.pivot_table(index="person", columns="video", values="rating")[videos]
    y = wide.mean().to_numpy()
    G = grids(pred, videos)
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    models = recovery_grids(chosen, cfg, ev["plausible_settings"], G, videos)
    gens = generators(models, G, y, cfg["rule"])
    rec = recover(models, gens, wide.to_numpy())
    print("recovery", rec, flush=True)
    # a population mixing budget sizes in the proportions of the per-person fits
    k_counts = {int(k): v for k, v in ev["per_person"]["k_counts_all"].items()}
    parts = [(k_counts.get(k, 0), p_new, p_orig) for _, model, k, p_new, p_orig in gens if model == "budget"]
    mixed = recover_mixed(models, parts, wide.to_numpy())
    print("mixed-k population", k_counts, mixed, flush=True)
    passed = all(v["model_share"] >= 0.9 and (v["k_share"] is None or v["k_share"] >= 0.8)
                 for v in rec.values())
    result = {"scale": scale, "need": need, "big": big, "small": small, "cue_line": line, "qualifying": counts,
              "chosen": {k: [c["id"] for c in v] for k, v in chosen.items()},
              "worst_cue": [float(worst[0]), worst[1], worst[2]], "swaps": swaps,
              "cue_r": all_cue_r(df),
              "recovery": rec, "recovery_passed": passed,
              "mixed_k_population": {"k_shares": k_counts, **mixed}}
    if write:
        tag = f"{big:g}_{small:g}_{line:g}" + ("" if scale == 1 else f"_x{scale:g}")
        out = os.path.join(HERE, "results", f"selection_{tag}.json")
        json.dump(result, open(out, "w"), indent=1)
        df.to_csv(os.path.join(HERE, "results", f"cues_{tag}.csv"), index=False)
    return result, chosen


if __name__ == "__main__":
    args = [float(a) for a in sys.argv[1:]]
    main(*args[:3], scale=args[3] if len(args) > 3 else 1.0)
