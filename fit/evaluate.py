"""Fit and compare the models on people's whether ratings (and cause ratings).

Reads results/predictions.csv (from fit/predict.py) and writes
results/evaluation.json plus a few CSV tables. Every comparison uses
leave-one-video-out error: settings, the selection rule and the linear scale
are chosen on 19 videos and scored on the 20th.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fit.data import HERE, balls, ratings  # noqa: E402
from fit.predict import THETA1S, THETAS  # noqa: E402

RESULTS = os.path.join(HERE, "results")
BOOT = 1000
rng = np.random.default_rng(2026)


# ---------- prediction grids: model -> (settings list, matrix settings x videos)

def grids(pred, videos):
    out = {}
    for m, label in ((1, "full"), (3, "how")):
        g = pred[pred.model == m].pivot_table(index="theta", columns="video", values="p")[videos]
        out[label] = ([{"theta": t} for t in g.index], g.to_numpy())
    g = pred[pred.model == 4].pivot_table(index=["k", "rule", "theta"], columns="video", values="p")[videos]
    out["budget"] = ([{"k": k, "rule": r, "theta": t} for k, r, t in g.index], g.to_numpy())
    c = pred[pred.model == 2].set_index(["video", "theta"]).p
    settings, rows = [], []
    for t0 in THETAS:
        for t1 in THETA1S:
            settings.append({"theta0": t0, "theta1": t1})
            rows.append([c[(v, round(t0 + t1 * (balls(v) - 2), 1))] for v in videos])
    out["crowding"] = (settings, np.array(rows))
    return out


def subset(grid, keep):
    settings, P = grid
    idx = [i for i, s in enumerate(settings) if keep(s)]
    return [settings[i] for i in idx], P[idx]


# ---------- the shared linear scale, rating = a + b * p with b >= 0

def scale_fit(P, y, w):
    """Weighted least squares of y on each row of P (w = 0/1 training mask).
    Returns a, b, sse arrays over rows."""
    n = w.sum()
    my = (w * y).sum() / n
    mp = (P * w).sum(1) / n
    dp = (P - mp[:, None]) * w
    vp = (dp ** 2).sum(1)
    b = np.where(vp > 0, (dp * (y - my)).sum(1) / np.where(vp > 0, vp, 1), 0)
    b = np.maximum(b, 0)
    a = my - b * mp
    sse = (((a[:, None] + b[:, None] * P - y) ** 2) * w).sum(1)
    return a, b, sse


def loo(grid, y):
    """Leave-one-video-out predictions; returns preds and the setting index per fold."""
    settings, P = grid
    nv = len(y)
    preds, chosen = np.zeros(nv), np.zeros(nv, int)
    for i in range(nv):
        w = np.ones(nv)
        w[i] = 0
        a, b, sse = scale_fit(P, y, w)
        s = int(np.argmin(sse))
        preds[i], chosen[i] = a[s] + b[s] * P[s, i], s
    return preds, chosen


def full_fit(grid, y):
    settings, P = grid
    a, b, sse = scale_fit(P, y, np.ones(len(y)))
    s = int(np.argmin(sse))
    return s, a[s], b[s], np.sqrt(sse[s] / len(y))


def rmse(p, y):
    return float(np.sqrt(np.mean((p - y) ** 2)))


def slope_ci(x, e):
    res = stats.linregress(x, e)
    t = stats.t.ppf(0.975, len(x) - 2)
    return res.slope, res.slope - t * res.stderr, res.slope + t * res.stderr


# ---------- analyses

def main():
    pred = pd.read_csv(os.path.join(RESULTS, "predictions.csv"), keep_default_na=False)
    pred["rule"] = pred.rule.astype(str)
    W = ratings("whether")
    videos = sorted(W.video.unique(), key=lambda v: (balls(v), v))
    nballs = np.array([balls(v) for v in videos])
    wide = W.pivot_table(index="person", columns="video", values="rating")[videos]
    y = wide.mean().to_numpy()
    G = grids(pred, videos)
    rules = sorted({s["rule"] for s in G["budget"][0]})
    report = {"videos": videos}

    # 1. group fit, leave one video out
    group, per_video = {}, {"video": videos, "balls": nballs, "people": y}
    for name, grid in G.items():
        p, chosen = loo(grid, y)
        s, a, b, fit_rmse = full_fit(grid, y)
        err = np.abs(p - y)
        slope, lo, hi = slope_ci(nballs, err)
        by_count = {int(n): float(err[nballs == n].mean()) for n in np.unique(nballs)}
        group[name] = {
            "loo_rmse": rmse(p, y), "loo_r": float(np.corrcoef(p, y)[0, 1]),
            "best_setting": grid[0][s], "scale": [float(a), float(b)], "fit_rmse": float(fit_rmse),
            "settings_chosen_in_folds": pd.Series([json.dumps(grid[0][c]) for c in chosen]).value_counts().to_dict(),
            "error_by_balls": by_count,
            "error_slope_per_ball": [float(slope), float(lo), float(hi)],
        }
        per_video[name] = p
    # budget sub-analyses: each rule alone, and each k alone
    for rule in rules:
        p, _ = loo(subset(G["budget"], lambda s: s["rule"] == rule), y)
        group["budget"][f"loo_rmse_rule_{rule}"] = rmse(p, y)
    for k in (1, 2, 3):
        p, _ = loo(subset(G["budget"], lambda s: s["k"] == k), y)
        group["budget"][f"loo_rmse_k{k}"] = rmse(p, y)
    report["group"] = group
    pd.DataFrame(per_video).to_csv(os.path.join(RESULTS, "loo_predictions.csv"), index=False)

    # 'budget is real': let the fit choose k among 1, 2, 3 and 'every ball' (model 1)
    combo = (G["budget"][0] + [{"k": "all", **s} for s in G["full"][0]],
             np.vstack([G["budget"][1], G["full"][1]]))
    s, *_ = full_fit(combo, y)
    _, chosen = loo(combo, y)
    report["budget_is_real"] = {
        "best_k_full_data": combo[0][s]["k"],
        "k_chosen_in_folds": pd.Series([str(combo[0][c]["k"]) for c in chosen]).value_counts().to_dict(),
    }

    # 2. bootstrap over participants: RMSE gap, budget minus each rival
    names = list(G)
    boot = {n: np.zeros(BOOT) for n in names}
    persons = wide.to_numpy()
    for i in range(BOOT):
        yb = np.nanmean(persons[rng.integers(0, len(persons), len(persons))], axis=0)
        for n in names:
            p, _ = loo(G[n], yb)
            boot[n][i] = rmse(p, yb)
    gaps = {}
    for n in names:
        if n != "budget":
            d = boot["budget"] - boot[n]
            gaps[n] = {"mean": float(d.mean()), "ci95": [float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))]}
    report["bootstrap_gap_budget_minus"] = gaps
    pd.DataFrame(boot).to_csv(os.path.join(RESULTS, "bootstrap_rmse.csv"), index=False)

    # plausible noise levels per model: settings whose full-data error is inside
    # the 95% bootstrap interval of the best fit's error
    plausible = {}
    for n in ("full", "budget", "crowding"):
        settings, P = G[n]
        _, _, sse = scale_fit(P, y, np.ones(len(y)))
        fit = np.sqrt(sse / len(y))
        hi = np.percentile(boot_fit(G[n], persons), 97.5)
        plausible[n] = [settings[i] for i in np.where(fit <= hi)[0]]
    report["plausible_settings"] = plausible

    # 3. per-person fits (rule fixed at the group winner)
    rule = group["budget"]["best_setting"]["rule"]
    person_grids = {"full": G["full"], "crowding": G["crowding"], "how": G["how"],
                    "budget": subset(G["budget"], lambda s: s["rule"] == rule)}
    rows = []
    for pid, r in wide.iterrows():
        yp = r.to_numpy()
        ok = ~np.isnan(yp)
        row = {"person": pid}
        for n, grid in person_grids.items():
            g = (grid[0], grid[1][:, ok])
            p, _ = loo(g, yp[ok])
            row[n] = rmse(p, yp[ok])
        s, *_ = full_fit((person_grids["budget"][0], person_grids["budget"][1][:, ok]), yp[ok])
        row["k"] = person_grids["budget"][0][s]["k"]
        rows.append(row)
    pp = pd.DataFrame(rows)
    pp["best"] = pp[list(person_grids)].idxmin(axis=1)
    pp.to_csv(os.path.join(RESULTS, "per_person.csv"), index=False)
    report["per_person"] = {
        "rule": rule,
        "share_best": pp.best.value_counts(normalize=True).round(3).to_dict(),
        "k_counts_all": pp.k.value_counts().to_dict(),
        "k_counts_budget_best": pp[pp.best == "budget"].k.value_counts().to_dict(),
    }

    # 4. cause ratings
    C = ratings("causal").pivot_table(index="person", columns="video", values="rating")[videos]
    H = ratings("how").pivot_table(index="person", columns="video", values="rating")[videos]
    yc = C.mean().to_numpy()
    cert_w = ((W.assign(c=(W.rating - 50).abs() * 2 / 100)
               .pivot_table(index="person", columns="video", values="c")[videos]).mean().to_numpy())
    cert_h = ((H - 50).abs() * 2 / 100).mean().to_numpy()
    how_p = G["how"][1][0]

    def best_row(name):
        s, *_ = full_fit(G[name], y)
        return G[name][1][s]

    w_full, w_budget = best_row("full"), best_row("budget")
    designs = {
        "people_whether_how": np.column_stack([y / 100, H.mean().to_numpy() / 100]),
        "full_whether_how": np.column_stack([w_full, how_p]),
        "budget_whether_how": np.column_stack([w_budget, how_p]),
        "weighted_mix_full": np.column_stack([cert_w * w_full, cert_h * how_p]),
        "weighted_mix_budget": np.column_stack([cert_w * w_budget, cert_h * how_p]),
        "how_only": how_p[:, None],
    }
    cause = {}
    for n, X in designs.items():
        cause[n] = regression_loo(X, yc)
    report["cause"] = cause

    with open(os.path.join(RESULTS, "evaluation.json"), "w") as f:
        json.dump(report, f, indent=1, default=float)
    print_summary(report)


def boot_fit(grid, persons):
    """Bootstrap distribution of the best full-data fit error."""
    settings, P = grid
    out = np.zeros(BOOT)
    r = np.random.default_rng(7)
    for i in range(BOOT):
        yb = np.nanmean(persons[r.integers(0, len(persons), len(persons))], axis=0)
        _, _, sse = scale_fit(P, yb, np.ones(len(yb)))
        out[i] = np.sqrt(sse.min() / len(yb))
    return out


def regression_loo(X, y):
    X1 = np.column_stack([np.ones(len(y)), X])
    preds = np.zeros(len(y))
    for i in range(len(y)):
        m = np.arange(len(y)) != i
        beta, *_ = np.linalg.lstsq(X1[m], y[m], rcond=None)
        preds[i] = X1[i] @ beta
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    fitted = X1 @ beta
    return {"loo_rmse": rmse(preds, y), "loo_r": float(np.corrcoef(preds, y)[0, 1]),
            "fit_r": float(np.corrcoef(fitted, y)[0, 1]), "coef": beta.tolist()}


def print_summary(rep):
    print("Leave-one-video-out on whether ratings")
    for n, g in rep["group"].items():
        print(f"  {n:9s} RMSE {g['loo_rmse']:5.1f}  r {g['loo_r']:.2f}  best {g['best_setting']}  "
              f"slope {g['error_slope_per_ball'][0]:.2f} [{g['error_slope_per_ball'][1]:.2f}, {g['error_slope_per_ball'][2]:.2f}]")
        print(f"            error by balls {({k: round(v, 1) for k, v in g['error_by_balls'].items()})}")
    print("  budget sub-fits:", {k: round(v, 1) for k, v in rep["group"]["budget"].items() if k.startswith("loo_rmse_")})
    print("Budget is real:", rep["budget_is_real"])
    print("Bootstrap gap (budget minus rival):", rep["bootstrap_gap_budget_minus"])
    print("Per person:", rep["per_person"])
    print("Cause ratings:", {k: (round(v["loo_rmse"], 1), round(v["loo_r"], 2)) for k, v in rep["cause"].items()})


if __name__ == "__main__":
    main()
