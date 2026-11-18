# MODEL_CARD — PLAYBOOK 27 context models (v1.0.0)
Purpose: player-agnostic expectations of ball outcomes and match leverage. They are NOT predictors of individual deliveries and NOT player-quality models.
Algorithm: scikit-learn HistGradientBoosting (monotone per-innings for WP). Split: train ≤2024-12-31, valid to 2025-07-31, test after; hyper-parameters (4-point grid) and model family
chosen on VALID only; TEST reported once from a train+valid refit; deployed/cross-fitted models use match-grouped 5-fold out-of-fold predictions.

| Task | Test metrics (actual) | Baseline |
|---|---|---|
| x_runs (bat runs/ball) | MAE 1.314, RMSE 1.733, R² 0.035 | R² 0 |
| x_out (striker dismissed) | ROC-AUC 0.597, PR-AUC 0.084 (base 0.056), log-loss 0.211, Brier 0.052, ECE 0.002 | AUC 0.5 |
| x_charged (runs conceded/ball) | MAE 1.282, RMSE 1.709, R² 0.033 | R² 0 |
| x_bwk (bowler wicket) | ROC-AUC 0.590, PR-AUC 0.074 (base 0.052), log-loss 0.201, ECE 0.003 | AUC 0.5 |
| wp (batting-side win prob.) | ROC-AUC 0.829, log-loss 0.496, Brier 0.168, ECE 0.028 (CV OOF log-loss 0.529) | log-loss 0.693 |
| lev (|ΔWP| next ball) | RMSE 0.0221, R² 0.281 | R² −0.003 |

Reading: ball-level outcomes are mostly noise (R² ≈ 3%, AUC ≈ 0.6) — adequate as context baselines, not for prediction. WP is useful but trained on only ~800 correlated matches (WP is
slightly miscalibrated: ECE 0.028). Class imbalance: balanced weighting destroyed calibration, so unweighted calibrated probabilities are used; evaluation uses PR-AUC, log-loss, Brier and ECE.
Explainability: permutation importance (`model_metrics.json`) and ablation-based local attribution in `ml/models.py`; association only. Full numbers incl. calibration tables: `data/processed/model_metrics.json`.

Deployed artefacts: `models/{x_runs,x_out,x_charged,x_bwk,wp,lev}_hgb.joblib` (scikit-learn 1.9.1, loaded only from the local trusted directory). Scenario simulator inputs outside the model (team strength, venue par, striker handedness) are set to neutral defaults and listed in every response.
WP calibration by situation (cross-fitted, deliveries): overall 0.485 predicted / 0.485 observed; last two overs 0.310 / 0.322; ≤9 balls with 9–16 needed 0.370 / 0.403. Reproducibility: a complete retrain from raw data reproduced identical test metrics and rankings.
