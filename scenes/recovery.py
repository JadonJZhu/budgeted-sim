"""Model recovery for a set of test scenes.

For each generating model (its best setting on the existing data; for the
budget model, each k at that k's best noise level), simulate fake studies of
50 people. Each fake person copies one real participant's own scale and noise:
we fit that participant's 20 whether ratings with rating = a + b x p (b >= 0)
under the generating model, and the fake person's rating of a test scene is
a + b x p + Gaussian noise with that participant's residual spread, clipped
to 0 to 100. So fake people differ in how they use the slider and in how
noisy they are, as real people do, while all following the generating model.

Each fake study is analysed like the real data: every model is fit with the
shared linear scale over its plausible settings and scored by
leave-one-scene-out error. A study recovers the model when the generating
model has the lowest error, and recovers k when the budget model's best k on
all scenes equals the generating k.
"""
import numpy as np

from fit.evaluate import full_fit, loo, rmse


def person_params(persons, p_orig):
    """Per real participant: (a, b, residual sd) under predictions p_orig."""
    out = []
    for r in persons:
        ok = ~np.isnan(r)
        x, y = p_orig[ok], r[ok]
        vx = x.var()
        b = max(((x - x.mean()) * (y - y.mean())).mean() / vx, 0) if vx > 0 else 0.0
        a = y.mean() - b * x.mean()
        out.append((a, b, np.std(y - a - b * x)))
    return np.array(out)


def fake_means(p_new, params, people, rng):
    pick = params[rng.integers(0, len(params), people)]
    a, b, sd = pick[:, :1], pick[:, 1:2], pick[:, 2:]
    r = a + b * p_new[None, :] + rng.standard_normal((people, len(p_new))) * sd
    return np.clip(r, 0, 100).mean(0)


def fake_means_mixed(parts, people, rng):
    """parts: list of (share, p_new, params). Each fake person follows one part."""
    shares = np.array([sh for sh, _, _ in parts])
    which = rng.choice(len(parts), size=people, p=shares / shares.sum())
    rows = []
    for j, (_, p_new, params) in enumerate(parts):
        n = int((which == j).sum())
        if n:
            pick = params[rng.integers(0, len(params), n)]
            r = pick[:, :1] + pick[:, 1:2] * p_new[None, :] + rng.standard_normal((n, len(p_new))) * pick[:, 2:]
            rows.append(np.clip(r, 0, 100))
    return np.vstack(rows).mean(0)


def recover_mixed(models, parts, persons, studies=200, people=50, seed=12):
    """A population that mixes budget sizes. parts: (share, p on test scenes,
    p on the original videos) per k. Returns how often the budget model wins
    and how often each k is chosen."""
    rng = np.random.default_rng(seed)
    parts = [(sh, p_new, person_params(persons, p_orig)) for sh, p_new, p_orig in parts]
    wins, ks = 0, {}
    for _ in range(studies):
        y = fake_means_mixed(parts, people, rng)
        scores = {name: rmse(loo(grid, y)[0], y) for name, grid in models.items()}
        wins += min(scores, key=scores.get) == "budget"
        s, *_ = full_fit(models["budget"], y)
        k = int(models["budget"][0][s]["k"])
        ks[k] = ks.get(k, 0) + 1
    return {"model_share": wins / studies, "k_counts": ks}


def recover(models, generators, persons, studies=200, people=50, seed=11):
    """models: name -> (settings, P) over the test scenes (plausible settings).
    generators: (label, model name, k or None, p on test scenes, p on the 20
    original videos). persons: real whether ratings, people x videos.
    Returns label -> {model_share, k_share}."""
    rng = np.random.default_rng(seed)
    out = {}
    for label, gen_model, gen_k, p_new, p_orig in generators:
        params = person_params(persons, p_orig)
        wins, k_hits = 0, 0
        for _ in range(studies):
            y = fake_means(p_new, params, people, rng)
            scores = {name: rmse(loo(grid, y)[0], y) for name, grid in models.items()}
            wins += min(scores, key=scores.get) == gen_model
            if gen_k is not None:
                s, *_ = full_fit(models["budget"], y)
                k_hits += models["budget"][0][s]["k"] == gen_k
        out[label] = {"model_share": wins / studies,
                      "k_share": (k_hits / studies) if gen_k is not None else None}
    return out
