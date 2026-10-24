# Fact sheet: the physical settings and model rules of Lu et al. (2026)

Our simulator in `sim/` is written from this list, not from the original code. The original repository (github.com/cicl-stanford/complex_causation_cogsci2026, commit 7546369) has no licence file, so we use its scene files and ratings as credited data and reimplement the model ourselves. Each fact below names where it comes from. "Paper" is Lu, Bechlivanidis & Gerstenberg, "Causal judgments in complex situations", CogSci 2026. "Code" is a file in that repository; we read it only to take these facts down.

Coordinates use the physics engine's convention: the origin is the bottom left corner and y grows upward.

## World

| Setting | Value | Source |
| --- | --- | --- |
| Physics engine | pymunk 6.x (2D rigid bodies; version 7 removed an API the original code uses) | Code: `code/python/model.py` imports |
| Table | 1000 wide by 750 high (pixels) | Code: `World.__init__` |
| Gravity, damping | none (engine defaults: zero gravity, no damping) | Code: the space is created without changing either |
| Time step | 1/50 second, so 50 steps per second of video | Code: `World.__init__` |
| Step limit | the run ends once the step counter passes 700 (14 seconds) | Code: `World.end_clip` |
| Top wall | a box spanning x 0 to 1000, y 725 to 750 | Code: `World.__init__` |
| Bottom wall | a box spanning x 0 to 1000, y −2.5 to 22.5 (drawn on screen as 0 to 25) | Code: `World.__init__` |
| Left wall | a 25 pixel thick wall at x 0 to 25, made of four boxes, with one opening between y 258.34 and 491.67: the gate | Code: `World.__init__` |
| Gate drawing | a red rectangle at x 0 to 25, y 258 to 492 | Code: `World.animation_step` |
| Right side | open: no wall | Code: `World.__init__` |
| Wall material | elasticity 1, friction 0 | Code: `World.add_wall` |

## Balls

| Setting | Value | Source |
| --- | --- | --- |
| Size | diameter 60 (radius 30) | Code: `World.__init__` |
| Mass | 1, with the moment of a solid disc | Code: `World.add_ball` |
| Material | elasticity 1, friction 0 | Code: `World.add_ball` |
| Starting velocity | the scene file's velocity times a speed scale of 120 (pixels per second). It is given as an impulse to a mass of 1, which is the same as setting that velocity | Code: `World.add_ball` |
| Names | A is the candidate cause, B the target; other balls are gray, named C onward | Scene file; Paper, Methods |
| Colors | A is green and labeled, B is labeled, the rest are gray | Paper, Methods; Code: sprite file names |

## Scenes

- 20 scenes in `code/python/trialinfo/multi_ball_trials_combined.json`, 4 at each of 2, 3, 6, 9 and 12 balls. Each lists, per ball, a name, a start position and a start velocity. (Code; Paper, Methods.)
- A always starts just off the right edge (x 1037.5) moving left. (Scene file.)
- Video names carry the scene's type: `both` (A is a whether cause and a how cause), `w_only`, `h_only` or `neither`. (Scene file; Paper, Methods.)

## Outcome

- B goes in when its center passes x < −30, that is, when it has fully left the table through the gate. The outcome is recorded at the first step this happens. (Code: `World.end_clip`.)
- After B leaves, the run continues 30 more steps and then stops. If the step counter passes 700 and B has not left, B missed. (Code: `World.end_clip`.)
- In every real video B goes in. (Paper, Methods; checked in our run.)

## Event log

- Every ball to ball contact is logged when it begins, with the step number and both balls' positions. (Code: `World.collisions`, a "begin" collision callback.)
- The step number logged is the counter before the physics step in which the contact begins. (Code: `World.simulate` increments the counter after each physics step.)

## Whether test (the counterfactual simulation)

- Remove A from the scene before the first step. (Paper, Modeling; Code: `whether_test` removes A at step 0.)
- Find, in the real run, the first contact between A and another ball whose position is on the table (0 ≤ x ≤ 1000, 0 ≤ y ≤ 750). That ball is "the ball A hit first", and that contact's step is the noise start. (Paper, Modeling; Code: `whether_test`.)
- Noise: at every step strictly after the noise start, rotate that one ball's velocity by an angle drawn from a Gaussian with mean 0 and standard deviation θ, in degrees. The speed is unchanged. No other ball gets noise. If A hits no ball on the table, there is no noise. (Paper, Modeling; Code: `apply_noise`.)
- Within a step, the order is: apply any counterfactual change, record positions, check for the end, then advance the physics by one step. (Code: `World.simulate`.)
- Each video's whether score is the mean, over replays, of (real outcome − counterfactual outcome), which for these videos is the share of replays in which B misses. 1,000 replays per video. (Paper, Modeling; Code: `whether_test`, `fit_model.py`.)
- θ is fit on a grid from 0 to 5 in steps of 0.1 by least squares between 100 × score and the mean flipped whether rating, with no other scaling. Best fit: θ = 1.9. (Paper, Modeling; Code: `fit_model.py`.)
- Reported fit at θ = 1.9: r = .694 and RMSE = 28.11 in the text; Figure 5 prints r = 0.684 with the same RMSE. The repository's `fitting_results.csv` gives r = .684, so .694 in the text looks like a typo. We treat .69 as the target, within our run to run spread. (Paper, Results and Figure 5; Code: `fitting_results.csv`.)

## How test

- Shift A's start position once, before the first step, by a very small Gaussian amount in x and y, and replay without noise. A is a how cause if B's final position differs from the real run's. The result is yes or no. (Paper, Modeling; Code: `how_test`, `perturb`.)
- The original code does not fix the size of the shift in the files we used. Ours is in `sim/` and is stated there. The original per video how results are in `data/complexity_measures.csv` (`how_result_A`), which we use only to check ours.

## Ratings data

- Three groups of about 50 people, one per question, each rating all 20 videos on a 0 to 100 slider. Files: `data/{whether,how,causal}_judgment/output/Output_*.csv`, columns `randomID`, `video_id`, `continuous_response`. (Paper, Methods; Code: data files.)
- The whether question was "Would ball B have gone through the gate if ball A had not been there?" The paper flips it (100 − rating) so that high means A mattered. We do the same. (Paper, Methods and Results.)
