# A study that separates the budget model from its rivals

This is a plan in the form of a pre-registration that a lab could adopt or change. Every prediction it refers to is in `predictions.csv` (every model at every setting the existing data allow) and `summary.csv` (each model at its best fit to the existing data, on the rating scale).

## Hypotheses

1. People's whether ratings follow the budget model (re-simulate B and a few other balls; replay the rest) better than the full CSM, a CSM whose noise grows with the number of balls, or the contact check alone.
2. The group's budget holds two balls, as the existing data suggest (best k = 2 at group level; per person, 13 people at k = 1, 25 at k = 2 and 12 at k = 3). On held-out error the existing data cannot tell k = 1 from k = 2, so this is the weaker hypothesis.

## Design

Same task as Experiment 1 of Lu, Bechlivanidis & Gerstenberg (2026): "Would ball B have gone through the gate if ball A had not been there?", one slider from 0 to 100, each video played twice. 36 videos in random order, about 27 minutes at the original pace.

| Kind | Scenes | Built so that |
| --- | --- | --- |
| Clear the way (`clear_*`) | 8 | The budget model and the full CSM differ by at least 40 points of predicted probability at every plausible setting |
| Hit but no difference (`hit_*`) | 8 | The budget model and the contact check differ by at least 40 points |
| Budget vs. crowding noise (`crowd_*`) | 8 | The budget model and crowding noise differ by at least 40 points |
| Budget 1 vs. 2 (`k12_*`) | 4 | Budgets of 1 and 2 differ by at least 40 points and budgets of 2 and 3 agree within 12; two scenes in each direction |
| Budget 2 vs. 3 (`k23_*`) | 4 | The mirror of the above |
| Anchors | 4 | Original videos `2ball_h_only_1`, `3ball_w_only_1`, `9ball_w_only_1`, `12ball_both_1`, to tie the new study to the old one |

"Plausible setting" means a budget of 1 to 3 balls and any noise level on the paper's grid (0 to 5 degrees) whose fit to the existing whether ratings is inside the 95% bootstrap interval of the best fit's error. For the budget model, the noise range of its best budget (2 balls) is used for all three sizes. The full CSM's plausible range runs to the grid's edge at 5 degrees. At the fitted rating scales, 40 points of probability is about 23 rating points; the which-model scenes separate the models by 41 to 47 rating points on average. All scenes come from a fixed generate, filter and select procedure (`scenes/`), with no scene picked by hand. Scenes in which A or B passes within 6 pixels of another ball without touching it were excluded.

Participants: 50, as in the original experiments. Exclusions as in the original study's pre-registration.

## Analysis

1. Flip the ratings (100 − rating) so that high means "B would have missed without A".
2. Fit each model to the 36 mean ratings with a shared linear scale (rating = a + b × p, b ≥ 0), over its plausible settings only, and score it by leave-one-scene-out error.
3. Primary test: the budget model's error minus each rival's error, with a 95% interval from 1,000 resamples of participants.
4. The budget size is the k of the best-fitting budget model. The same fit per participant gives each person's k.

## Pass and fail lines

- **Support for the budget model:** its leave-one-scene-out error is lower than every rival's, and the 95% interval of each gap excludes zero.
- **Against it:** any rival's error is lower, with an interval that excludes zero.
- Anything else is inconclusive and is reported as such.

## Expected power

We simulated 200 studies of 50 participants from each model. Each fake person copies one real participant's slider scale and noise, fit to that participant's 20 original ratings under the generating model. The generating model won all 200 studies, and the generating budget size was recovered in all 200, for every model and every k from 1 to 3. A population mixing budgets in the proportions of the per-person fits was identified as a budget population in all 200, with k = 2 in 199. The same held for sets half and a quarter this size; the set is this large because of the simple-cue check. These studies assume each person follows one model exactly, so they show that the scenes can separate the models, not that real ratings will be this clean.

## Known weak spots

- **Simple cues.** Across the 36 scenes, none of four crude cues (A's closest approach to B, number of collisions, number of balls, whether A passes within one ball width of B's path) correlates with any model's disagreement with the budget model above |r| = .3 (largest .26, after 78 rule-based swaps). A stricter line of .2 could not be met (best .28).
- **One-sided which-model scenes.** In all 24 which-model scenes the budget model says A did not matter, so a general lean toward that answer would favour it there. The which-setting scenes and two anchors include scenes where it says A mattered (predicted rating 83), which a lean of that kind cannot fit.
- **Extreme predictions.** The best-fitting budget model has almost no noise, so its predictions are close to 0 or 1 in these scenes. The test is about which answers people give, not how confident they are.
- **The scenes were checked by eye from still frames only.** Each video should be watched before the study runs.
