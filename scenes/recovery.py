"""Model recovery for a set of test scenes.

For each generating model (its group best fit; for the budget model, each k
with that k's best noise level), simulate fake studies of 50 people. A fake
person's rating of a scene is the model's predicted rating plus a residual
drawn from the real whether data (one person's rating minus that video's
mean), clipped to 0 to 100. Each fake study is then analysed exactly like the
real data: every model is fit with the shared linear scale and scored by
leave-one-scene-out error over its plausible settings. The study counts as
recovered when the generating model has the lowest error, and the k as
recovered when the budget model's chosen k equals the generating k.
"""
import numpy as np

from fit.evaluate import loo, rmse


def residual_pool(wide):
    """Every (person, video) residual from the real whether ratings."""
    r = wide - wide.mean()
    return r.to_numpy()[~np.isnan(r.to_numpy())]


def fake_means(mean_rating, residuals, people, rng):
    e = rng.choice(residuals, size=(people, len(mean_rating)))
    return np.clip(mean_rating[None, :] + e, 0, 100).mean(0)


def recover(models, generators, residuals, studies=200, people=50, seed=11):
    """models: name -> (settings, P) over the test scenes (plausible settings).
    generators: list of (label, model name, k or None, predicted ratings array).
    Returns a dict label -> {model_share, k_share}."""
    rng = np.random.default_rng(seed)
    out = {}
    for label, gen_model, gen_k, mean_rating in generators:
        wins, k_hits = 0, 0
        for _ in range(studies):
            y = fake_means(mean_rating, residuals, people, rng)
            scores, k_chosen = {}, None
            for name, grid in models.items():
                p, chosen = loo(grid, y)
                scores[name] = rmse(p, y)
                if name == "budget":
                    # k chosen on all scenes (the study's estimate of k)
                    from fit.evaluate import full_fit
                    s, *_ = full_fit(grid, y)
                    k_chosen = grid[0][s]["k"]
            wins += min(scores, key=scores.get) == gen_model
            if gen_k is not None:
                k_hits += k_chosen == gen_k
        out[label] = {"model_share": wins / studies,
                      "k_share": (k_hits / studies) if gen_k is not None else None}
    return out
