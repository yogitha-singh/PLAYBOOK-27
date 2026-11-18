"""Per-delivery value above context expectation (the common currency for batting and bowling).

batter  v = (bat_runs - xRuns)  -  V * (dismissed - xOut)   (= run stream + V x avoidance stream)        [runs above expected, wicket cost V]
bowler  v = (xCharged - runs_charged) + V * (wicket - xWicket)   [runs saved above expected + wickets]

xRuns/xOut/xCharged/xWicket are PLAYER-AGNOSTIC, cross-fitted context expectations, so v measures performance
relative to an average player in the SAME match situation (not relative to an easy/typical situation).
V (runs-equivalent cost of a wicket) is estimated from the win-probability model: the ratio of the WP effect
of a wicket to the WP effect of one run (OLS on delivery-level dWP, innings-specific, then averaged).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def estimate_wicket_cost(s: pd.DataFrame) -> dict:
    out = {}
    for inn in (1, 2):
        d = s[(s.innings == inn) & s.dwp.notna()]
        X = np.column_stack([np.ones(len(d)), d.total_runs.values, d.team_wicket.astype(float).values, d.legal.astype(float).values])
        beta, *_ = np.linalg.lstsq(X, d.dwp.values, rcond=None)
        out[f"innings{inn}"] = {"wp_per_run": float(beta[1]), "wp_per_wicket": float(beta[2]), "V_runs_per_wicket": float(-beta[2] / beta[1])}
    out["V"] = float(np.mean([out["innings1"]["V_runs_per_wicket"], out["innings2"]["V_runs_per_wicket"]]))
    return out


def add_values(s: pd.DataFrame, V: float | None = None) -> pd.DataFrame:
    """Adds two per-delivery residual STREAMS per role (positive = better for the player) and, if V is given, the combined value.
    Streams are shrunk separately (see reliability.py) because the dismissal/wicket stream is far noisier than the runs stream."""
    s = s.copy()
    s["r_bat_run"] = s.bat_runs - s.exp_runs
    s["r_bat_out"] = -(s.batter_out.astype(float) - s.exp_out)          # dismissal AVOIDANCE
    s.loc[~s.faced, ["r_bat_run", "r_bat_out"]] = np.nan
    s["r_bowl_run"] = s.exp_charged - s.bowler_runs                      # runs SAVED
    s["r_bowl_wk"] = s.bowler_wkt.astype(float) - s.exp_bwk              # wickets ABOVE expected
    s.loc[s.is_penalty, ["r_bowl_run", "r_bowl_wk"]] = np.nan
    if V is not None:
        s["v_bat"] = s.r_bat_run + V * s.r_bat_out
        s["v_bowl"] = s.r_bowl_run + V * s.r_bowl_wk
    return s
