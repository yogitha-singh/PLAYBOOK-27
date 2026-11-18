"""Pressure framework.

PRIMARY DEFINITION (leverage-based, model-driven, pre-delivery only)
  Pressure = how much the NEXT delivery can move the match.  The Leverage Index of a delivery is the model-expected
  absolute change in the batting side's win probability (lev_hat), divided by the average over all deliveries
  (LI = 1.0 is an average ball).  It is built from pre-delivery state only (balls left, wickets in hand, score,
  required rate, run-rate gap, venue par, team strength) so it automatically captures: a high required rate, few
  wickets in hand, few balls left, a close chase, a collapse, and a tight first innings - at ANY stage of the innings.
  Categories are quantiles of LI computed WITHIN each innings (setting vs chasing have structurally different leverage
  scales, and pooled quantiles would make "pressure" a proxy for "chasing"): Low (<P50), Moderate (P50-P80),
  High (P80-P95), Critical (>=P95).
  "Pressure" for player evaluation = High + Critical (the top 20% of deliveries).

ALTERNATIVE DEFINITION B (rule-based closeness, used only for sensitivity analysis)
  Contest alive (batting-side WP in [0.25, 0.75]) AND the last 8 overs of the innings (balls_rem <= 48).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PressureConfig

CATS = ["Low", "Moderate", "High", "Critical"]


def thresholds(s: pd.DataFrame, cfg: PressureConfig) -> dict:
    return {f"q{int(q * 100)}": float(s.LI.quantile(q)) for q in cfg.cuts}


def assign(s: pd.DataFrame, cfg: PressureConfig | None = None) -> tuple[pd.DataFrame, dict]:
    cfg = cfg or PressureConfig()
    s = s.copy()
    groups = [(1, s.innings == 1), (2, s.innings == 2)] if cfg.by_innings else [("all", pd.Series(True, index=s.index))]
    idx = np.zeros(len(s), int)
    th_out = {}
    for key, m in groups:
        th = [s.loc[m, "LI"].quantile(q) for q in cfg.cuts]
        idx[m.values] = np.digitize(s.loc[m, "LI"], th)
        th_out[f"innings_{key}" if cfg.by_innings else "all"] = dict(zip([f"P{int(q*100)}" for q in cfg.cuts], map(float, th)))
    s["pressure_cat"] = pd.Categorical(np.array(CATS)[idx], categories=CATS, ordered=True)
    s["is_pressure"] = s.pressure_cat.isin(cfg.pressure_levels)
    return s, {"cuts": cfg.cuts, "by_innings": cfg.by_innings, "LI_thresholds": th_out, "pressure_levels": list(cfg.pressure_levels)}


def definition_b(s: pd.DataFrame) -> pd.Series:
    return (s.wp_pre.between(0.25, 0.75) & (s.balls_rem <= 48))


def validity_table(s: pd.DataFrame) -> pd.DataFrame:
    """Evidence that categories separate ordinary from pressure situations (all measured on outcomes NOT used to define them)."""
    f = s[s.faced]
    rows = []
    for c in CATS:
        a, fa = s[s.pressure_cat == c], f[f.pressure_cat == c]
        ch = a[a.innings == 2]
        rows.append({
            "category": c, "deliveries": len(a), "share_pct": 100 * len(a) / len(s),
            "mean_LI": a.LI.mean(), "mean_abs_dWP": a.dwp.abs().mean(),
            "pct_powerplay": 100 * (a.phase == "Powerplay").mean(), "pct_middle": 100 * (a.phase == "Middle").mean(),
            "pct_death": 100 * (a.phase == "Death").mean(), "pct_chase": 100 * (a.innings == 2).mean(),
            "mean_wkts_rem": a.wkts_rem.mean(), "mean_balls_rem": a.balls_rem.mean(),
            "chase_mean_rrr": ch.rrr.mean() if len(ch) else np.nan,
            "mean_bat_wp": a.wp_pre.mean(), "pct_close_bat_wp_35_65": 100 * a.wp_pre.between(0.35, 0.65).mean(),
            "runs_per_ball": fa.bat_runs.mean(), "dot_pct": 100 * (fa.bat_runs == 0).mean(),
            "boundary_pct": 100 * (fa.is_four | fa.is_six).mean(), "dismissal_pct": 100 * fa.batter_out.mean(),
        })
    return pd.DataFrame(rows).round(3)


def phase_by_category(s: pd.DataFrame) -> pd.DataFrame:
    t = pd.crosstab(s.phase, s.pressure_cat, normalize="columns").mul(100).round(1)
    return t.reindex(["Powerplay", "Middle", "Death"])


def pressure_rate_by_over(s: pd.DataFrame) -> pd.DataFrame:
    g = s.groupby(["innings", "over_idx"]).agg(pressure_share=("is_pressure", "mean"), mean_LI=("LI", "mean")).reset_index()
    g["over"] = g.over_idx + 1
    return g.drop(columns="over_idx").round(4)
