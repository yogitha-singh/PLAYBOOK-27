"""Pressure Scenario Simulator.

Response sections (never merged):
  model_estimates          MODEL-GENERATED: win probability, leverage, pressure category, context expectations (from the deployed models)
  historical_observations  HISTORICAL: how often batting sides won from comparable states in the data (aggregated counts, observations are correlated)
  player_evidence          HISTORICAL: players' recorded outcomes in the same innings / phase / pressure category (small cells suppressed)
  local_explanation        optional ablation-based attribution of the model estimates (predictive association, not causal)
"""
from __future__ import annotations

import threading

import joblib
import numpy as np
import pandas as pd

from ..analytics.features import CONTEXT_FEATURES, WP_FEATURES
from ..core.security import ApiError
from ..ml import models as M

TASKS = ("wp", "lev", "x_runs", "x_out")
PRESETS = [
    {"id": "chase_45_24", "label": "45 needed from 24 balls, 4 wickets left", "innings": 2, "runs_required": 45, "balls_remaining": 24, "wickets_remaining": 4},
    {"id": "chase_12_6", "label": "12 needed from the final over, 6 wickets left", "innings": 2, "runs_required": 12, "balls_remaining": 6, "wickets_remaining": 6},
    {"id": "defend_30_18", "label": "Defending: opposition need 30 from the last 3 overs (7 wickets left)", "innings": 2, "runs_required": 30, "balls_remaining": 18, "wickets_remaining": 7, "note": "bowling-side view of a chase state"},
    {"id": "collapse_new_batter", "label": "New batter after a collapse: 62/5 after 9 overs batting first", "innings": 1, "score": 62, "balls_remaining": 66, "wickets_remaining": 5, "striker_order": 6, "striker_balls_faced": 0},
]


class ModelStore:
    """Loads the pipeline's joblib artefacts once. Artefacts are loaded only from the local, trusted model directory."""

    def __init__(self, model_dir):
        self.dir, self._m, self._lock = model_dir, {}, threading.Lock()

    def available(self) -> bool:
        return all((self.dir / f"{t}_hgb.joblib").exists() for t in TASKS)

    def get(self, task):
        with self._lock:
            if task not in self._m:
                path = self.dir / f"{task}_hgb.joblib"
                if not path.exists():
                    raise ApiError(503, "models_unavailable", "trained model artefacts not found; run scripts/run_pipeline.py")
                self._m[task] = joblib.load(path)
            return self._m[task]


def _num(name, raw, lo, hi, default=None, integer=True):
    if raw is None or raw == "":
        if default is None:
            raise ApiError(400, "missing_parameter", f"{name} is required")
        return default
    try:
        v = float(raw)
    except ValueError:
        raise ApiError(400, "bad_parameter", f"{name} must be a number")
    if not lo <= v <= hi or (integer and v != int(v)):
        raise ApiError(400, "bad_parameter", f"{name} must be {'an integer ' if integer else ''}between {lo} and {hi}")
    return int(v) if integer else v


def parse(args) -> dict:
    inn = _num("innings", args.get("innings"), 1, 2)
    p = {"innings": inn, "balls_remaining": _num("balls_remaining", args.get("balls_remaining"), 1, 120),
         "wickets_remaining": _num("wickets_remaining", args.get("wickets_remaining"), 1, 10),
         "tier": (args.get("tier") or "ipl").lower(), "striker_order": _num("striker_order", args.get("striker_order"), 1, 11, 5),
         "striker_balls_faced": _num("striker_balls_faced", args.get("striker_balls_faced"), 0, 120, 0),
         "explain": str(args.get("explain", "")).lower() in ("1", "true", "yes")}
    if p["tier"] not in ("ipl", "t20i"):
        raise ApiError(400, "bad_parameter", "tier must be ipl or t20i")
    if inn == 2:
        p["runs_required"] = _num("runs_required", args.get("runs_required"), 1, 300)
        p["first_innings_total"] = _num("first_innings_total", args.get("first_innings_total"), 1, 300, None) if args.get("first_innings_total") else None
    else:
        p["score"] = _num("score", args.get("score"), 0, 300)
    return p


def build_state(p: dict, med: dict) -> pd.DataFrame:
    br = p["balls_remaining"]
    legal_before = 120 - br
    r = {c: med[c] for c in CONTEXT_FEATURES}
    r.update(innings=p["innings"], balls_rem=br, wkts_rem=p["wickets_remaining"], over_idx=min(legal_before // 6, 19), ball_in_over=legal_before % 6,
             is_ipl=int(p["tier"] == "ipl"), is_t20i=int(p["tier"] == "t20i"), striker_order=p["striker_order"], striker_balls_before=p["striker_balls_faced"],
             striker_runs_before=0, bat_elo=1500.0, bowl_elo=1500.0, elo_diff=0.0)
    if p["innings"] == 2:
        req = p["runs_required"]
        total = p.get("first_innings_total") or max(int(round(med["venue_avg_first"])), req)
        score_before = max(total + 1 - req, 0)
        r.update(score_before=score_before, target_runs_req=req, rrr=min(req / br * 6, 36.0))
        r["crr"] = min(score_before / legal_before * 6, 36.0) if legal_before else 0.0
        r["rrr_minus_crr"] = r["rrr"] - r["crr"]
        p["_first_innings_total_used"] = total
    else:
        r.update(score_before=p["score"], target_runs_req=0.0, rrr=0.0, rrr_minus_crr=0.0)
        r["crr"] = min(p["score"] / legal_before * 6, 36.0) if legal_before else 0.0
    return pd.DataFrame([r])


def _category(li: float, th: dict) -> str:
    return ["Low", "Moderate", "High", "Critical"][int(np.digitize(li, [th["P50"], th["P80"], th["P95"]]))]


def _pool(df: pd.DataFrame, cols: list[str], target: dict, radius: int, steps: dict, min_obs: int):
    for r in range(radius + 1):
        m = pd.Series(True, index=df.index)
        for c in cols:
            m &= (df[c] - target[c]).abs() <= steps[c] * r
        sub = df[m]
        if sub.match_visits.sum() >= min_obs:
            return sub, r
    return df[m], radius


def historical_state(repo, p: dict) -> dict:
    from ..analytics.scenario import BIN_BALLS, BIN_RUNS_CHASE, BIN_SCORE
    if p["innings"] == 2:
        df, cols, key = repo.csv("scenario_chase_states.csv"), ["req_bin", "balls_bin", "wkts_rem"], "sum_req"
        tgt = {"req_bin": p["runs_required"] // BIN_RUNS_CHASE * BIN_RUNS_CHASE, "balls_bin": p["balls_remaining"] // BIN_BALLS * BIN_BALLS, "wkts_rem": p["wickets_remaining"]}
        steps = {"req_bin": BIN_RUNS_CHASE, "balls_bin": BIN_BALLS, "wkts_rem": 1}
        what, lab = "batting (chasing) side won the match", "runs_required"
    else:
        df, cols, key = repo.csv("scenario_setting_states.csv"), ["score_bin", "balls_bin", "wkts_rem"], "sum_score"
        tgt = {"score_bin": p["score"] // BIN_SCORE * BIN_SCORE, "balls_bin": p["balls_remaining"] // BIN_BALLS * BIN_BALLS, "wkts_rem": p["wickets_remaining"]}
        steps = {"score_bin": BIN_SCORE, "balls_bin": BIN_BALLS, "wkts_rem": 1}
        what, lab = "side batting first won the match", "score"
    sub, r = _pool(df, cols, tgt, 3, steps, 40)         # radius capped at 3 bins: wider pools stop being "comparable"
    visits, wins, dl = int(sub.match_visits.sum()), float(sub.wins.sum()), float(sub.deliveries.sum())
    if visits < 40:
        return {"outcome": what, "available": False, "reason": f"only {visits} comparable historical match-states within the allowed search radius; too few to report a frequency"}
    ph, z = wins / visits, 1.96
    den = 1 + z * z / visits
    half = z * np.sqrt(ph * (1 - ph) / visits + z * z / (4 * visits ** 2)) / den
    ctr = (ph + z * z / (2 * visits)) / den
    avg = {lab: round(float(sub[key].sum()) / dl, 1), "balls_remaining": round(float(sub.sum_balls.sum()) / dl, 1),
           "wickets_remaining": round(float((sub.wkts_rem * sub.deliveries).sum()) / dl, 2)}
    warn = []
    if abs(avg["balls_remaining"] - p["balls_remaining"]) > 1.5:
        warn.append(f"pooled states average {avg['balls_remaining']} balls remaining vs {p['balls_remaining']} requested (pooling is one-sided near the end of an innings)")
    if abs(avg[lab] - p["runs_required" if p["innings"] == 2 else "score"]) > (3 if p["innings"] == 2 else 6):
        warn.append(f"pooled {lab} averages {avg[lab]} vs requested")
    if abs(avg["wickets_remaining"] - p["wickets_remaining"]) > 0.75:
        warn.append(f"pooled wickets remaining average {avg['wickets_remaining']} vs {p['wickets_remaining']} requested")
    return {"outcome": what, "available": True, "comparability_warnings": warn, "historical_win_rate": round(wins / visits, 4), "wilson_95_interval": [round(max(ctr - half, 0), 4), round(min(ctr + half, 1), 4)],
            "match_state_observations": visits, "deliveries": int(dl), "search_radius_bins": r, "average_pooled_state": avg,
            "pooled_ranges": {c: [int(sub[c].min()), int(sub[c].max())] for c in cols},
            "caveat": "Pooled observations are neighbouring states, not exact matches; compare average_pooled_state with your inputs. One match contributes to many states, so observations are NOT independent (interval is optimistic)"}


def player_evidence(repo, p: dict, category: str, limit: int = 8) -> dict:
    phase = "Powerplay" if p["balls_remaining"] > 84 else "Middle" if p["balls_remaining"] > 30 else "Death"
    base = repo.csv("scenario_league_bins.csv")
    b = base[(base.innings == p["innings"]) & (base.phase == phase) & (base.pressure_cat == category)]
    out = {"situation": {"innings": p["innings"], "phase": phase, "pressure_category": category},
           "league_baseline_batting": b.drop(columns=["innings", "phase", "pressure_cat"]).to_dict("records")[:1],
           "note": "Recorded outcomes in situations classified the same way (innings x phase x pressure category); NOT a prediction for this exact state"}
    if category not in ("High", "Critical"):
        out["batters"] = out["bowlers"] = []
        out["message"] = "This state is classified below the pressure threshold; player pressure evidence covers High/Critical situations only"
        return out
    for role, f, key in (("bat", "scenario_player_bins_batters.csv", "batters"), ("bowl", "scenario_player_bins_bowlers.csv", "bowlers")):
        d = repo.csv(f)
        d = d[(d.innings == p["innings"]) & (d.phase == phase) & (d.pressure_cat == category)]
        r = repo.rankings(role).set_index("player_id")
        d = d.assign(player=d.player_id.map(r.player), ranked=d.player_id.map(r.eligible).fillna(False).astype(bool)).sort_values("value_per100", ascending=False).head(limit)
        keep = [c for c in ("player_id", "player", "ranked", "deliveries", "runs", "strike_rate", "dismissals", "wickets", "economy", "dot_pct", "value_per100") if c in d]
        out[key] = d[keep].astype(object).where(d[keep].notna(), None).to_dict("records")
    out["message"] = "Sorted by value above expectation per 100 deliveries in this cell; cells are small (>=15 deliveries), so treat as descriptive evidence, not a ranking"
    return out


def simulate(repo, store: ModelStore, args) -> dict:
    p = parse(args)
    med = repo.json("feature_medians.json")
    th = repo.json("pressure_thresholds.json")["LI_thresholds"][f"innings_{p['innings']}"]
    X = build_state(p, med)
    wp_m, lev_m, xr_m, xo_m = (store.get(t) for t in TASKS)
    wp = float(wp_m["model"].predict_proba(X[WP_FEATURES])[:, 1][0])
    X2 = X.assign(wp_pre=wp)
    lev = float(lev_m["model"].predict(X2[lev_m["features"]])[0])
    li = lev / med["_lev_hat_mean"]
    cat = _category(li, th)
    est = {"batting_side_win_probability": round(wp, 4), "leverage_index": round(li, 3), "pressure_category": cat,
           "category_thresholds_LI_innings": {k: round(v, 3) for k, v in th.items()},
           "expected_runs_next_ball_for_average_batter": round(float(xr_m["model"].predict(X[xr_m["features"]])[0]), 3),
           "dismissal_probability_next_ball_average_batter": round(float(xo_m["model"].predict_proba(X[xo_m["features"]])[:, 1][0]), 4)}
    out = {"inputs": {k: v for k, v in p.items() if not k.startswith("_") and k != "explain"},
           "assumptions": ["team strength equal (Elo diff 0)", "venue par = dataset median", "striker defaults: right-handed, facing pace, 0 runs so far unless set"] +
                          ([f"first-innings total assumed {p['_first_innings_total_used']} (affects only the leverage model's score input)"] if p["innings"] == 2 else []),
           "model_estimates": {"type": "MODEL-GENERATED ESTIMATE (not a match prediction)", "model_version": wp_m["version"], **est},
           "historical_observations": {"type": "HISTORICAL OBSERVATION (aggregated counts)", **historical_state(repo, p)},
           "player_evidence": {"type": "HISTORICAL OBSERVATION (aggregated player outcomes)", **player_evidence(repo, p, cat)}}
    if p["explain"]:
        bg = pd.DataFrame([{**{c: med[c] for c in CONTEXT_FEATURES}, "wp_pre": med["wp_pre"]}])
        ex = {}
        for t, m, Xs, kind in (("wp", wp_m, X[WP_FEATURES], "clf"), ("lev", lev_m, X2[lev_m["features"]], "reg"), ("x_runs", xr_m, X[xr_m["features"]], "reg"), ("x_out", xo_m, X[xo_m["features"]], "clf")):
            rows = M.local_explanation(m["model"], Xs.reset_index(drop=True), bg[Xs.columns], kind)
            ex[t] = [r for r in rows if r["feature"] not in ("innings", "is_ipl", "is_t20i") and abs(r["effect"]) > 1e-9][:6]
        out["local_explanation"] = {"type": "MODEL EXPLANATION (ablation vs typical-state background; predictive association, not causal, not SHAP)", "effects": ex,
                                    "reading": "effect = prediction minus prediction with that one feature replaced by its dataset median"}
    return out


def explain_player(rec: dict, params: dict, role: str) -> dict:
    """Decomposes a player's PRI into its components using the stored, already-computed quantities."""
    w = 1 / 3
    comp = []
    for key, label, tau_key in (("z_level", "Level (value above expectation under pressure)", "level"), ("z_delta", "Delta (pressure vs own baseline)", "delta"), ("z_consistency", "Consistency (appearances above expectation)", "cons")):
        tau = params[role]["tau"][tau_key]
        comp.append({"component": label, "z": round(rec[key], 3), "pri_points": round(10 * w * rec[key], 2), "estimated_true_sd_tau": round(tau, 4),
                     "weight_note": "zero weight: no detectable between-player variation (tau=0)" if tau < 1e-9 else "contributes"})
    return {"PRI": rec["PRI"], "formula": "PRI = 50 + 10 x mean(z_level, z_delta, z_consistency)", "components": comp, "check_sum": round(50 + sum(c["pri_points"] for c in comp), 2),
            "shrinkage": {"weight_on_own_data": round(rec["shrink_weight_on_own_data"], 3), "raw_level_per100": round(rec["level_raw100"], 2), "shrunk_level_per100": round(rec["level100"], 2), "level_sd_per100": round(rec["level_sd100"], 2),
                          "reading": "shrunk = prior mean + weight x (raw - prior mean); a low weight means the estimate is mostly the league prior"},
            "uncertainty": {"PRI_90_interval": [rec["PRI_lo"], rec["PRI_hi"]], "rank_range": [rec["rank_lo"], rec["rank_hi"]], "p_top10": rec["p_top10"], "sensitivity_grid_share_top10": rec["share_top10"]},
            "caution": "Association with model-based expectations, not a causal explanation of why the player performs"}
