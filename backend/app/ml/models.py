"""Model suite for PLAYBOOK 27 (all models are PLAYER-AGNOSTIC context models).

Tasks
  x_runs    batter runs off the bat per ball faced               (regression)
  x_out     probability the striker is dismissed on the ball      (classification)
  x_charged runs charged to the bowler per delivery bowled        (regression)
  x_bwk     probability of a bowler-credited wicket               (classification)
  wp        probability the BATTING side wins (pre-delivery)      (classification)
  lev       expected |change in win probability| of next delivery (regression)  -> Leverage Index

Validation design
  1. Chronological split by match date (train <= TRAIN_END < valid <= VALID_END < test) for model selection
     and honest forward-looking metrics.  Hyper-parameters are chosen on VALID only; TEST is touched once.
  2. Match-grouped K-fold cross-fitting produces out-of-fold expectations for every delivery so no delivery
     is ever scored by a model that saw its own match.
"""
from __future__ import annotations

import json
import logging
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (average_precision_score, brier_score_loss, f1_score, log_loss, mean_absolute_error,
                             mean_squared_error, precision_score, r2_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..analytics import config
from ..analytics.features import assert_no_leakage

log = logging.getLogger("playbook.ml")
MODEL_VERSION = "1.0.0"

GRIDS = {
    "reg": [dict(learning_rate=0.05, max_iter=150, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0),
            dict(learning_rate=0.05, max_iter=250, max_leaf_nodes=15, min_samples_leaf=400, l2_regularization=5.0),
            dict(learning_rate=0.03, max_iter=300, max_leaf_nodes=31, min_samples_leaf=400, l2_regularization=10.0),
            dict(learning_rate=0.05, max_iter=120, max_leaf_nodes=7, min_samples_leaf=300, l2_regularization=1.0)],
}
GRIDS["clf"] = GRIDS["reg"]
# win-probability: only ~800 matches, so use strongly regularised trees (the labels are match-level, deliveries within a match are correlated)
GRIDS["wp"] = [dict(learning_rate=0.05, max_iter=100, max_leaf_nodes=7, min_samples_leaf=800, l2_regularization=10.0),
               dict(learning_rate=0.05, max_iter=200, max_leaf_nodes=7, min_samples_leaf=1500, l2_regularization=20.0),
               dict(learning_rate=0.03, max_iter=200, max_leaf_nodes=15, min_samples_leaf=1000, l2_regularization=20.0),
               dict(learning_rate=0.05, max_iter=150, max_leaf_nodes=5, min_samples_leaf=2000, l2_regularization=30.0)]
# Family overrides (documented in MODEL_CARD): a model is forced only when validation shows no meaningful difference AND the
# alternative is structurally unsuitable for how the output is used.
FORCED_FAMILY = {"wp": ("hist_gradient_boosting",
                        "WP derivatives drive the Leverage Index; a linear logit cannot represent the runs-required x balls-remaining "
                        "interaction (it made early-chase balls look high-leverage). Validation log-loss difference is negligible.")}


class InningsWP(ClassifierMixin, BaseEstimator):
    """Win-probability estimator: one monotonically-constrained gradient-boosting model per innings.
    Constraints encode cricket logic (more wickets/balls/runs in hand can never LOWER the batting side's win
    probability; more runs required can never raise it) which removes spurious ball-to-ball wobble."""
    F1 = {"balls_rem": 1, "wkts_rem": 1, "score_before": 1, "elo_diff": 1, "venue_avg_first": 0, "is_ipl": 0, "is_t20i": 0}
    F2 = {"balls_rem": 1, "wkts_rem": 1, "target_runs_req": -1, "rrr": -1, "elo_diff": 1, "venue_avg_first": 0, "is_ipl": 0, "is_t20i": 0}

    def __init__(self, params=None, seed=config.SEED, kw=None):
        self.params, self.seed, self.kw = params, seed, (kw or {})

    def _mk(self, cst):
        return HistGradientBoostingClassifier(random_state=self.seed, monotonic_cst=cst, **self.params, **self.kw)

    def fit(self, X, y):
        y = np.asarray(y)
        self.classes_ = np.array([0, 1])
        i1 = (X["innings"] == 1).values
        self.m1 = self._mk(self.F1).fit(X.loc[i1, list(self.F1)], y[i1])
        self.m2 = self._mk(self.F2).fit(X.loc[~i1, list(self.F2)], y[~i1])
        return self

    def predict_proba(self, X):
        p = np.zeros(len(X))
        i1 = (X["innings"] == 1).values
        if i1.any():
            p[i1] = self.m1.predict_proba(X.loc[i1, list(self.F1)])[:, 1]
        if (~i1).any():
            p[~i1] = self.m2.predict_proba(X.loc[~i1, list(self.F2)])[:, 1]
        return np.column_stack([1 - p, p])


def build(name, kind, params, seed=config.SEED, **kw):
    if name == "wp":
        return InningsWP(params, seed=seed, kw=kw)
    return _hgb(kind, params, seed=seed, **kw)


def _hgb(kind, params, seed=config.SEED, **kw):
    cls = HistGradientBoostingRegressor if kind == "reg" else HistGradientBoostingClassifier
    return cls(random_state=seed, **params, **kw)


def calibration_table(y, p, bins=10) -> list[dict]:
    p = np.asarray(p)
    q = pd.Series(0, index=range(len(p))) if np.unique(p).size < 2 else pd.qcut(pd.Series(p), bins, duplicates="drop")
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p), "bin": q})
    g = d.groupby("bin", observed=True).agg(mean_pred=("p", "mean"), obs_rate=("y", "mean"), n=("y", "size"))
    return g.reset_index(drop=True).round(5).to_dict("records")


def ece(y, p, bins=10) -> float:
    t = calibration_table(y, p, bins)
    n = sum(r["n"] for r in t)
    return float(sum(r["n"] * abs(r["mean_pred"] - r["obs_rate"]) for r in t) / n)


def reg_metrics(y, p) -> dict:
    return {"MAE": float(mean_absolute_error(y, p)), "RMSE": float(np.sqrt(mean_squared_error(y, p))), "R2": float(r2_score(y, p))}


def clf_metrics(y, p, thr=None) -> dict:
    y = np.asarray(y)
    thr = thr if thr is not None else float(np.quantile(p, 1 - y.mean()))   # flag top-prevalence share
    yhat = (p >= thr).astype(int)
    return {"ROC_AUC": float(roc_auc_score(y, p)), "PR_AUC": float(average_precision_score(y, p)),
            "LogLoss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))), "Brier": float(brier_score_loss(y, p)),
            "Precision@prev": float(precision_score(y, yhat, zero_division=0)),
            "Recall@prev": float(recall_score(y, yhat, zero_division=0)),
            "F1@prev": float(f1_score(y, yhat, zero_division=0)), "ECE": ece(y, p),
            "base_rate": float(y.mean()), "n": int(len(y))}


def baseline_pred(kind, y_tr, n):
    return np.full(n, float(np.mean(y_tr)))


def linear_model(kind):
    if kind == "reg":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=500))


def _predict(m, X, kind):
    return m.predict(X) if kind == "reg" else m.predict_proba(X)[:, 1]


def split_masks(dates: pd.Series):
    d = pd.to_datetime(dates)
    tr = d <= config.TRAIN_END
    va = (d > config.TRAIN_END) & (d <= config.VALID_END)
    te = d > config.VALID_END
    return tr.values, va.values, te.values


def evaluate_task(name, kind, X, y, dates, groups, metric_key):
    """Compare baseline / linear / HGB (tuned on VALID), report TEST once, class-imbalance comparison for clf."""
    assert_no_leakage(list(X.columns))
    tr, va, te = split_masks(dates)
    t0 = time.time()
    res = {"task": name, "kind": kind, "n_train": int(tr.sum()), "n_valid": int(va.sum()), "n_test": int(te.sum()),
           "features": list(X.columns), "candidates": {}}
    lower_better = metric_key in ("MAE", "RMSE", "LogLoss", "Brier")
    # tune HGB on validation
    best, best_s = None, None
    for i, prm in enumerate(GRIDS.get(name, GRIDS[kind])):
        m = build(name, kind, prm).fit(X[tr], y[tr])
        pv = _predict(m, X[va], kind)
        s = (reg_metrics(y[va], pv) if kind == "reg" else clf_metrics(y[va], pv))[metric_key]
        res["candidates"][f"hgb_{i}"] = {"params": prm, f"valid_{metric_key}": s}
        if best is None or (s < best_s if lower_better else s > best_s):
            best, best_s = prm, s
    res["selected_params"] = best
    # family selection on VALIDATION only (linear fit on train vs best tuned HGB); TEST is never used to choose
    lin_v = linear_model(kind).fit(X[tr], y[tr])
    plv = _predict(lin_v, X[va], kind)
    lin_s = (reg_metrics(y[va], plv) if kind == "reg" else clf_metrics(y[va], plv))[metric_key]
    res["valid_selection"] = {"linear": lin_s, "hist_gradient_boosting": best_s, "metric": metric_key}
    hgb_wins = (best_s <= lin_s) if lower_better else (best_s >= lin_s)
    res["selected_model"] = "hist_gradient_boosting" if hgb_wins else "linear"
    if name in FORCED_FAMILY and FORCED_FAMILY[name][0] != res["selected_model"]:
        res["selection_override"] = {"validation_choice": res["selected_model"], "forced": FORCED_FAMILY[name][0], "reason": FORCED_FAMILY[name][1]}
        res["selected_model"] = FORCED_FAMILY[name][0]
    trva = tr | va
    # final comparison on TEST (models refit on train+valid)
    comp = {}
    pb = baseline_pred(kind, y[trva], te.sum())
    lin = linear_model(kind).fit(X[trva], y[trva])
    hg = build(name, kind, best).fit(X[trva], y[trva])
    for nm, pr in (("baseline_mean", pb), ("linear", _predict(lin, X[te], kind)), ("hist_gradient_boosting", _predict(hg, X[te], kind))):
        if kind == "clf" and nm == "baseline_mean":
            pr = np.clip(pr, 1e-6, 1 - 1e-6)
        comp[nm] = reg_metrics(y[te], pr) if kind == "reg" else clf_metrics(y[te], pr)
    res["test_metrics"] = comp
    if kind == "clf":
        ph = _predict(hg, X[te], kind)
        res["test_calibration"] = calibration_table(y[te], ph)
        # class imbalance: balanced class weights vs. unweighted -> probabilities get distorted
        wt = build(name, "clf", best, class_weight="balanced").fit(X[trva], y[trva])
        res["class_imbalance_comparison"] = {"unweighted": comp["hist_gradient_boosting"],
                                             "class_weight_balanced": clf_metrics(y[te], _predict(wt, X[te], kind))}
    res["fit_seconds"] = round(time.time() - t0, 1)
    return res, hg


def make_model(kind, family, params, seed=config.SEED, name=None):
    return linear_model(kind) if family == "linear" else build(name, kind, params, seed=seed)


def crossfit(kind, params, X, y, groups, n_splits=config.CV_FOLDS, family="hist_gradient_boosting", name=None):
    """Out-of-fold predictions: each delivery is predicted by a model that never saw its match."""
    oof = np.zeros(len(X))
    for f, (a, bb) in enumerate(GroupKFold(n_splits).split(X, y, groups)):
        m = make_model(kind, family, params, seed=config.SEED + f, name=name).fit(X.iloc[a], y[a])
        oof[bb] = _predict(m, X.iloc[bb], kind)
    return oof


def global_importance(model, X, y, kind, n=15000, repeats=3):
    rs = np.random.RandomState(config.SEED)
    idx = rs.choice(len(X), min(n, len(X)), replace=False)
    scoring = "neg_mean_squared_error" if kind == "reg" else "neg_log_loss"
    r = permutation_importance(model, X.iloc[idx], np.asarray(y)[idx], scoring=scoring, n_repeats=repeats, random_state=config.SEED)
    out = pd.DataFrame({"feature": X.columns, "importance": r.importances_mean, "std": r.importances_std})
    return out.sort_values("importance", ascending=False).round(6).to_dict("records")


def local_explanation(model, X_row: pd.DataFrame, background: pd.DataFrame, kind) -> list[dict]:
    """Single-prediction attribution by ablation: replace each feature with its background median and record the
    change in prediction. This is a transparent *predictive association* measure (NOT SHAP, NOT causal)."""
    base = _predict(model, X_row, kind)[0]
    out = []
    for c in X_row.columns:
        z = X_row.copy()
        z[c] = background[c].median()
        out.append({"feature": c, "value": float(X_row[c].iloc[0]), "effect": float(base - _predict(model, z, kind)[0])})
    return sorted(out, key=lambda r: -abs(r["effect"]))


def save(obj, name):
    config.MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, config.MODEL_DIR / f"{name}.joblib")
