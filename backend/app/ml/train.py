"""Train, evaluate, cross-fit and persist every context model. Returns the delivery table enriched with
out-of-fold expectations: exp_runs, exp_out, exp_charged, exp_bwk, wp_pre, wp_post, dwp, lev_hat, LI."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..analytics import config
from ..analytics.features import CONTEXT_FEATURES, WP_FEATURES
from . import models as M

log = logging.getLogger("playbook.train")
LEV_FEATURES = WP_FEATURES + ["over_idx", "wp_pre"]


def _task(name, kind, metric, X, y, dates, groups, results, full_models):
    log.info("task %-10s n=%d", name, len(X))
    res, _ = M.evaluate_task(name, kind, X, y, dates, groups, metric)
    params = res["selected_params"]
    fam = res["selected_model"]
    oof = M.crossfit(kind, params, X, y, groups, family=fam, name=name)
    final = M.make_model(kind, fam, params, name=name).fit(X, y)             # deployed model: all in-scope data
    res["cv_oof_metrics"] = M.reg_metrics(y, oof) if kind == "reg" else M.clf_metrics(y, oof)
    res["global_importance"] = M.global_importance(final, X, y, kind)
    res["deployed_family"] = fam
    results[name] = res
    full_models[name] = final
    import json, os
    ck = os.environ.get("PLAYBOOK_CKPT")
    if ck:
        json.dump(results, open(ck, "w"), default=str)
    M.save({"model": final, "features": list(X.columns), "version": M.MODEL_VERSION}, f"{name}_hgb")
    return oof, final


def add_win_prob_and_leverage(s: pd.DataFrame, results: dict, full: dict) -> None:
    """Adds wp_pre, wp_post, dwp, lev_hat, LI in place (cross-fitted)."""
    # ---- win probability (batting-side perspective); ties (no scoreboard winner) are unlabeled
    lab = s.first_wins.notna().values
    y_wp = np.where(s.innings == 1, s.first_wins, 1 - s.first_wins)
    Xp = s[WP_FEATURES]
    oof, final = _task("wp", "clf", "LogLoss", Xp[lab].reset_index(drop=True), y_wp[lab].astype(int), s.loc[lab, "match_date"].reset_index(drop=True),
                       s.loc[lab, "match_id"].values, results, full)
    s["wp_pre"] = np.nan; s.loc[lab, "wp_pre"] = oof
    s.loc[~lab, "wp_pre"] = final.predict_proba(Xp[~lab])[:, 1]
    # ---- win-probability after each delivery (batting-side perspective)
    g = s.groupby(["match_id", "innings"], sort=False)
    nxt = g["wp_pre"].shift(-1)
    last = nxt.isna()
    first2 = s[s.innings == 2].groupby("match_id")["wp_pre"].first()
    post = nxt.copy()
    m1 = last & (s.innings == 1)
    post[m1] = 1 - s.loc[m1, "match_id"].map(first2)
    m2 = last & (s.innings == 2)
    post[m2] = (1 - s.loc[m2, "first_wins"]).fillna(0.5)
    s["wp_post"] = post
    s["dwp"] = s.wp_post - s.wp_pre
    s.loc[m1, "dwp"] = np.nan        # innings-1 -> innings-2 hand-over compares two different models: not a real swing
    # ---- leverage index: pre-delivery expectation of |dWP|
    ok = s.dwp.notna().values
    Xl = s.loc[ok, LEV_FEATURES].reset_index(drop=True)
    oof, _ = _task("lev", "reg", "RMSE", Xl, s.loc[ok, "dwp"].abs().values, s.loc[ok, "match_date"].reset_index(drop=True), s.loc[ok, "match_id"].values, results, full)
    s["lev_hat"] = np.nan; s.loc[ok, "lev_hat"] = oof
    s["lev_hat"] = s.lev_hat.fillna(s.lev_hat.median())
    s["LI"] = s.lev_hat / s.lev_hat.mean()
    s.drop(columns=["exp_out_tmp"], errors="ignore")


def train_all(b: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    keep = [c for c in b.columns if c not in ("delivery_ist_time", "stroke", "delivery_style", "over_or_around", "on_or_off", "bowl_speed", "result")]
    s = b.loc[b.in_scope, keep].copy().reset_index(drop=True)
    results, full = {}, {}
    # ---- batter models: balls faced
    bm = s.faced.values
    Xb = s.loc[bm, CONTEXT_FEATURES].reset_index(drop=True); gb = s.loc[bm, "match_id"].values; db = s.loc[bm, "match_date"].reset_index(drop=True)
    oof, _ = _task("x_runs", "reg", "RMSE", Xb, s.loc[bm, "bat_runs"].values.astype(float), db, gb, results, full)
    s["exp_runs"] = np.nan; s.loc[bm, "exp_runs"] = oof
    oof, _ = _task("x_out", "clf", "LogLoss", Xb, s.loc[bm, "batter_out"].values.astype(int), db, gb, results, full)
    s["exp_out"] = np.nan; s.loc[bm, "exp_out"] = oof
    # ---- bowler models: every delivery bowled
    wm = ~s.is_penalty.values
    Xw = s.loc[wm, CONTEXT_FEATURES].reset_index(drop=True); gw = s.loc[wm, "match_id"].values; dw = s.loc[wm, "match_date"].reset_index(drop=True)
    oof, _ = _task("x_charged", "reg", "RMSE", Xw, s.loc[wm, "bowler_runs"].values.astype(float), dw, gw, results, full)
    s["exp_charged"] = np.nan; s.loc[wm, "exp_charged"] = oof
    oof, _ = _task("x_bwk", "clf", "LogLoss", Xw, s.loc[wm, "bowler_wkt"].values.astype(int), dw, gw, results, full)
    s["exp_bwk"] = np.nan; s.loc[wm, "exp_bwk"] = oof
    add_win_prob_and_leverage(s, results, full)
    meta = {"model_version": M.MODEL_VERSION, "split": {"train_end": config.TRAIN_END, "valid_end": config.VALID_END, "cv_folds": config.CV_FOLDS},
            "tasks": results}
    return s, meta
