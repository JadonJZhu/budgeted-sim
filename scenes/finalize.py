"""Write the chosen test scenes and every model's predictions for them.

Usage: python scenes/finalize.py results/selection_40_12_0.3.json

Outputs, in scenes/final/:
- test_scenes.json: the new scenes in the original study's format
  ([{"trial": name, "balls": [...]}]); anchors keep their original names
- predictions.csv: every model's p at every plausible setting, per scene
- summary.csv: per scene, each model's predicted rating at its best fit to
  the existing data (rating = a + b x p)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, scenes  # noqa: E402
from scenes.screen import crowd_thetas  # noqa: E402

FINAL = os.path.join(HERE, "scenes", "final")
ANCHORS = ["2ball_h_only_1", "3ball_w_only_1", "9ball_w_only_1", "12ball_both_1"]
ORDER = ["clear", "hit", "crowd", "k12", "k23"]


def main(selection):
    sel = json.load(open(selection))
    data = json.load(open(os.path.join(HERE, "scenes", "work", "candidates.json")))
    cfg = data["settings"]
    by_id = {c["id"]: c for c in data["confirmed"]}
    ev = json.load(open(os.path.join(HERE, "results", "evaluation.json")))
    pred = pd.read_csv(os.path.join(HERE, "results", "predictions.csv"), keep_default_na=False)
    os.makedirs(FINAL, exist_ok=True)

    trials, rows, names = [], [], {}
    for kind in ORDER:
        for i, cid in enumerate(sel["chosen"][kind], 1):
            name = f"{kind}_{i:02d}"
            names[cid] = name
            c = by_id[cid]
            trials.append({"trial": name, "kind": kind, "source_id": cid, "balls": c["scene"]})
            p = c["p1000"]
            for t, v in zip(cfg["confirm"]["full"], p["full"]):
                rows.append((name, kind, "full", "", t, "", v))
            rows.append((name, kind, "how", "", "", "", p["how"][0]))
            for k in (1, 2, 3):
                for t, v in zip(cfg["confirm"]["budget"], p[f"k{k}"]):
                    rows.append((name, kind, "budget", k, t, cfg["rule"], v))
            for t, v in zip(crowd_thetas(cfg, len(c["scene"]), cfg["confirm"]["crowd_step"]), p["crowd"]):
                rows.append((name, kind, "crowding_effective_theta", "", t, "", v))
    orig = scenes()
    for a in ANCHORS:
        trials.append({"trial": a, "kind": "anchor", "balls": orig[a]})
        sub = pred[pred.video == a]
        for _, r in sub.iterrows():
            model = {1: "full", 2: "crowding_effective_theta", 3: "how", 4: "budget"}[r.model]
            if model == "budget" and r.rule != cfg["rule"]:
                continue
            rows.append((a, "anchor", model, r.k if model == "budget" else "",
                         r.theta if model != "how" else "", r.rule if model == "budget" else "", r.p))
    json.dump(trials, open(os.path.join(FINAL, "test_scenes.json"), "w"), indent=1)
    df = pd.DataFrame(rows, columns=["scene", "kind", "model", "k", "theta", "rule", "p"])
    df.to_csv(os.path.join(FINAL, "predictions.csv"), index=False)

    # predicted ratings at each model's best fit to the existing data
    best = ev["group"]
    summ = []
    for t in trials:
        s = df[df.scene == t["trial"]]
        out = {"scene": t["trial"], "kind": t["kind"], "balls": len(t["balls"])}
        for model, key in (("full", "full"), ("how", "how"), ("budget", "budget"), ("crowding", "crowding")):
            st = best[key]["best_setting"]
            a, b = best[key]["scale"]
            if model == "full":
                v = s[(s.model == "full") & np.isclose(s.theta.astype(float), st["theta"])].p
            elif model == "how":
                v = s[s.model == "how"].p
            elif model == "budget":
                v = s[(s.model == "budget") & (s.k.astype(str) == str(st["k"]))
                      & np.isclose(s.theta.astype(float), st["theta"])].p
            else:
                eff = st["theta0"] + st["theta1"] * (len(t["balls"]) - 2)
                c = s[s.model == "crowding_effective_theta"]
                v = [np.interp(eff, c.theta.astype(float), c.p)]
            out[f"{model}_rating"] = round(float(a + b * float(list(v)[0])), 1)
            if model == "budget":
                for k in (1, 2, 3):
                    vk = s[(s.model == "budget") & (s.k.astype(str) == str(k))
                           & np.isclose(s.theta.astype(float), st["theta"])].p
                    out[f"budget_k{k}_rating"] = round(float(a + b * float(list(vk)[0])), 1)
        summ.append(out)
    pd.DataFrame(summ).to_csv(os.path.join(FINAL, "summary.csv"), index=False)
    print(pd.DataFrame(summ).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
