# Counterfactual simulation on a budget

A candidate account of why people's judgments of whether ball A made a difference to ball B drift away from the counterfactual simulation model (CSM) in crowded scenes, building on Lu, Bechlivanidis & Gerstenberg (CogSci 2026). The idea: when people imagine the scene without A, they re-simulate only a few balls.

## Where to look

| If you want | Look at |
| --- | --- |
| The question, the model, the results and the proposed study, explained | [`writeup/writeup.pdf`](writeup/writeup.pdf) (two pages) |
| The 36 proposed test videos | `scenes/final/videos/` |
| A plan a lab could adopt for running them | `scenes/final/PLAN.md` |
| Every model's predictions for each test scene | `scenes/final/predictions.csv` (every setting) and `scenes/final/summary.csv` (each model at its best fit) |
| Results on the original 20 videos, including some the write-up leaves out (fits to each participant, a model of the cause ratings) | `results/evaluation.json` |
| Scene selection at other settings | the other files in `results/` |
| How our simulator was built and checked | [Our simulator](#our-simulator), below |
| The code | [Repository layout](#repository-layout) and [Reproducing](#reproducing), below |

## Our simulator

The original repository has no licence file, so we did not copy or import its code. `FACTSHEET.md` lists the physical settings and model rules we took from the paper and code (table and gate size, ball size, speed scale, time step, elasticity, where and how noise is applied), with the source of each. `sim/` was written from that list.

Checks against the original:

- Without noise, our counterfactual outcome and our answer to the CSM's how test (would nudging A slightly change B's path?) match the original in all 20 videos.
- At the paper's noise level, θ = 1.9 degrees (1,000 replays per video, 20 random seeds), our CSM correlates with people's mean whether ratings at r = .670 (range .664 to .679; `results/reproduction.csv`). The original code, run locally the same way, gives .674 (range .667 to .682; its predictions are in `results/original_code_seeds.csv`, the code itself is not included). Per video the two agree within 1 point. The paper reports .684 (and .694 in the text), which is above the original code's own seed range.

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
python scenes/screen.py 500000          # generate, filter, screen, confirm; about 10 hours on 8 cores
python scenes/select.py 40 12 0.3       # choose scenes, cue check, model recovery (uses the included scenes/work/candidates.json)
python scenes/finalize.py results/selection_40_12_0.3.json
```

## Credit

Scenes and ratings, including the four anchor scenes copied into `scenes/final/test_scenes.json`: Lu, Bechlivanidis & Gerstenberg (2026), "Causal judgments in complex situations", CogSci 2026; materials at github.com/cicl-stanford/complex_causation_cogsci2026. The capacity limit motivating the budget: Balaban & Ullman (2025), "The capacity limits of moving objects in the imagination", Nature Communications.

Our code is under the MIT licence (`LICENSE`). The original study's scenes and ratings belong to its authors and are not covered by it.
