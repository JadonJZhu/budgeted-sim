# Counterfactual simulation on a budget

In Lu, Bechlivanidis & Gerstenberg (CogSci 2026), people's answers to "would B have gone through the gate if A had not been there?" drift away from the Counterfactual Simulation Model (CSM) as scenes get crowded, and end up close to their answers about whether A touched B at all. This repository tests one explanation: when people imagine the scene without A, they re-simulate only a few balls (B first) and let every other ball move along the path it really took.

On the 20 videos of that study, a budget of two balls fits people's whether ratings better than the full CSM, a CSM whose noise grows with crowding, or the contact check alone. The advantage is not decisive with 20 videos, so we also designed new scenes in which the models make clearly different predictions, for a lab to run.

## Result on the existing data

Each model maps its prediction p (the share of imagined replays in which B misses) to the rating scale with a fitted line, and is scored on each video after being fit to the other 19. Error is root mean squared error in rating points (0 to 100).

| Model | What it imagines without A | Held-out error | r |
| --- | --- | --- | --- |
| Budget (ours) | B and one other ball are re-simulated; every other ball replays its real path | 18.2 | .80 |
| Crowding noise | Full re-simulation, with noise that grows with the number of balls | 22.5 | .67 |
| How only | No simulation: B "would have missed" only if A touched B through a chain of contacts | 24.3 | .59 |
| Full CSM | Full re-simulation, with noise on the ball A hit first (the published model) | 25.1 | .55 |

- **Best budget:** 2 balls, filled with B and then the first ball A hit in the real video. This choice won in all 20 cross-validation folds over budgets of 1 and 3 and over "every ball" (which is the full CSM).
- **Not decisive:** resampling the 50 participants 1,000 times, the budget model beats the full CSM in 96% of resamples (gap −5.4 points, 95% interval −10.8 to +0.6), crowding noise in 81% (−2.7, interval −7.4 to +2.8) and how only in 87% (−4.2, interval −11.4 to +2.6). We set a 95% interval excluding zero as the bar before fitting, and the result does not clear it.
- **Crowding:** the budget model's error does not grow with the number of balls (slope −0.8 points per ball, interval −2.2 to +0.6).
- **Individuals:** fitting each participant separately, the budget model fits 34% best, how only 28%, crowding noise 28% and the full CSM 10%. Their best budgets: 1 ball for 13 people, 2 for 25, 3 for 12.
- **Cause ratings:** the authors' proposed next step weights the whether and how answers by people's certainty. That model predicts the cause ratings better with the budget model's whether answers (held-out error 16.7) than with the CSM's (18.3).

Full numbers are in `results/evaluation.json`.

## How the budget model works

Remove A. Re-simulate B and up to k − 1 other balls, chosen by a rule that uses only what the real video shows (we tested three: balls A touched, balls that touched B, and balls that came closest to B's path). Every other ball is reset to its recorded position and velocity at each time step. It therefore follows its real path exactly and is never pushed off it, but it still pushes any re-simulated ball it meets, with the force of a real ball. As in the CSM, direction noise goes on the ball A hit first, if that ball is in the budget.

With k = 1, B's imagined path can differ from its real path only if A touched B through some chain of contacts, so the whether answer becomes the how answer. With every ball in the budget, the model is the full CSM. In the 9-ball video below, A clears two balls (E and F) out of B's way. A full simulation without A sends E and F into B, and B misses. A budget of B and E leaves F on the path A really sent it, and B still goes in, which is what people said.

![The 9-ball video](writeup/figures/nine_ball.png)

## Our simulator

The original repository has no licence file, so we did not copy or import its code. `FACTSHEET.md` lists the physical settings and model rules we took from the paper and code (table and gate size, ball size, speed scale, time step, elasticity, where and how noise is applied), with the source of each. `sim/` was written from that list.

Checks against the original:

- The noise-free counterfactual outcome and the how answer match the original in all 20 videos.
- At θ = 1.9 (1,000 replays per video, 20 random seeds) our CSM correlates with people's mean whether ratings at r = .670 (range .664 to .679). The original code run the same way gives .674 (range .667 to .682). Per video the two agree within 1 point. The paper reports .684 (and .694 in the text), which is above the original code's own seed range.

## Repository layout

| Folder | Contents |
| --- | --- |
| `FACTSHEET.md` | The settings our simulator is built from, with sources |
| `sim/` | Physics (`physics.py`) and the models (`models.py`) |
| `fit/` | Prediction grid (`predict.py`), fitting and evaluation (`evaluate.py`), reproduction check (`reproduce.py`) |
| `scenes/` | Scene generator, validity filter, screening and selection, model recovery, rendering |
| `analysis/` | Figures |
| `results/` | Predictions, fits and bootstrap results |
| `writeup/` | The two-page write-up and its figures |

## Reproducing

Python 3.12 with the packages in `requirements.txt` (pymunk must be 6.x). Get the original materials and point `ORIGINAL` at them:

```
git clone https://github.com/cicl-stanford/complex_causation_cogsci2026
export ORIGINAL=$PWD/complex_causation_cogsci2026
pip install -r requirements.txt
python fit/reproduce.py      # about 3 minutes on 8 cores
python fit/predict.py        # every model and setting; a few hours on 8 cores
python fit/evaluate.py
python analysis/figures.py
```

## Credit

Scenes and ratings: Lu, Bechlivanidis & Gerstenberg (2026), "Causal judgments in complex situations", CogSci 2026; materials at github.com/cicl-stanford/complex_causation_cogsci2026. The capacity limit motivating the budget: Balaban & Ullman (2025), "The capacity limits of moving objects in the imagination", Nature Communications.
