# Model governance v1.1

A challenger can enter the production ensemble only if all conditions hold:

1. No future leakage under code review.
2. Walk-forward evaluation uses only earlier draws to predict each later draw.
3. Hyperparameters are selected without touching the final holdout.
4. Performance is compared to Uniform, Empirical Bayes and regularized Logistic baselines under the same protocol.
5. Improvement is stable across multiple windows, not driven by one short period or one lucky high-hit draw.
6. Statistical uncertainty is reported; large hypothesis/model sweeps require multiple-comparison control.
7. Model contribution is capped initially and promoted gradually.
8. Any sustained regression reduces ensemble weight; previous versions remain available for rollback.
9. Directional folklore (hot/cold, overdue/rebound, repeat/avoid-repeat, trend/reversion) may enter only as learnable features, never as mandatory weights or hard filters.
10. If no learning model reliably beats Uniform out of sample, production falls back to Uniform rather than forcing an AI advantage.

Primary scoring: Brier and LogLoss on per-number inclusion probabilities.
Secondary diagnostics: Top-K recall, mean matched numbers, calibration, rolling stability.
Jackpot/ROI is recorded but never used alone to select a model because it is too sparse/noisy.

## Promotion states

`candidate -> shadow -> low_weight -> production -> promoted`

Failure path:

`candidate/shadow -> rejected` or `production -> reduced -> retired`

Every transition must be written to the evolution log with the evidence window and model version.


## 当前1.5实现

实际门槛和状态以 `ACCEPTANCE_V1_5.md` 及 `backtest.py` 为准。深度模型仍在候选池，未自动上线；holdout不用于调参或增加融合权重。通过验证时最多5%小权重，缺证据回退Uniform。
