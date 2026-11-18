"""Player evaluation engine: ties pressure labels, shrinkage, uncertainty, stability and profiles into ranking tables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import profiles, reliability as R, stability as S, value
from .config import SEED

MIN_APPEARANCES = 6
ROLE_COLS = {"bat": ("striker_id", ("r_bat_run", "r_bat_out")), "bowl": ("bowler_id", ("r_bowl_run", "r_bowl_wk"))}
W_PRIMARY = S.WEIGHT_SETS["equal"]


def _note_bat(r) -> tuple[str, str, str]:
    st, wk, sit = [], [], []
    if r.level_raw100 > 0: st.append(f"scores {r.level_raw100:+.1f} runs/100 pressure balls vs an average batter in the same situations (shrunk estimate {r.level100:+.1f})")
    if pd.notna(r.p_strike_rate) and pd.notna(r.b_strike_rate):
        (st if r.p_strike_rate >= r.b_strike_rate else wk).append(f"pressure strike rate {r.p_strike_rate:.0f} vs {r.b_strike_rate:.0f} otherwise")
    (st if r.p_dismissals_below_exp >= 0 else wk).append(f"{abs(r.p_dismissals_below_exp):.1f} dismissals {'fewer' if r.p_dismissals_below_exp >= 0 else 'more'} than expected under pressure")
    for k, lab in (("sr_powerplay", "powerplay"), ("sr_middle", "middle overs"), ("sr_death", "death overs"), ("sr_chasing", "chases"), ("sr_setting", "setting totals")):
        if pd.notna(r.get(k)): sit.append((r[k], lab))
    best = ", ".join(l for _, l in sorted(sit, reverse=True)[:2]) or "n/a (thin phase samples)"
    return "; ".join(st) or "no clear pressure strength", "; ".join(wk) or "no clear pressure weakness in the data", f"highest strike rates in: {best}"


def _note_bowl(r) -> tuple[str, str, str]:
    st, wk, sit = [], [], []
    if r.level_raw100 > 0: st.append(f"saves/gains {r.level_raw100:+.1f} runs-equivalent per 100 pressure balls vs an average bowler in the same situations (shrunk {r.level100:+.1f})")
    if pd.notna(r.p_economy) and pd.notna(r.b_economy):
        (st if r.p_economy <= r.b_economy else wk).append(f"pressure economy {r.p_economy:.2f} vs {r.b_economy:.2f} otherwise")
    (st if r.p_wkts_above_exp >= 0 else wk).append(f"{abs(r.p_wkts_above_exp):.1f} wickets {'more' if r.p_wkts_above_exp >= 0 else 'fewer'} than expected under pressure")
    for k, lab in (("econ_powerplay", "powerplay"), ("econ_middle", "middle overs"), ("econ_death", "death overs"), ("econ_defending", "defending"), ("econ_chasing_opp", "bowling in chases")):
        if pd.notna(r.get(k)): sit.append((-r[k], lab))
    best = ", ".join(l for _, l in sorted(sit, reverse=True)[:2]) or "n/a (thin phase samples)"
    return "; ".join(st) or "no clear pressure strength", "; ".join(wk) or "no clear pressure weakness in the data", f"lowest economy in: {best}"


def evaluate_role(s: pd.DataFrame, role: str, V: float, names: pd.Series, teams: pd.DataFrame, roles: pd.DataFrame | pd.Series,
                  grid: dict, n_boot: int = 300) -> tuple[pd.DataFrame, dict]:
    pid, cols = ROLE_COLS[role]
    P = R.build_role_panel(s, pid, cols, s.is_pressure, V)
    c = R.components(P)
    nmin = R.derive_min_sample(c, P.A.var_p)
    el = R.eligibility(c, nmin, MIN_APPEARANCES)
    sc, z = R.composite(c, el, W_PRIMARY)
    rk = R.rank_desc(sc, el)
    bt = S.bootstrap(P, el, W_PRIMARY, B=n_boot)
    d = pd.DataFrame({"player_id": P.players, "pressure_deliveries": c["n_p"].astype(int), "baseline_balls": c["n_b"].astype(int),
                      "pressure_appearances": c["app"].astype(int),
                      "level100": c["level"] * 100, "level_sd100": c["level_sd"] * 100, "level_raw100": c["level_raw"] * 100,
                      "delta100": c["delta"] * 100, "delta_raw100": c["delta_raw"] * 100,
                      "consistency_pct": c["cons"] * 100, "consistency_raw_pct": c["cons_raw"] * 100,
                      "shrink_weight_on_own_data": c["B_level"],
                      "z_level": z["level"], "z_delta": z["delta"], "z_consistency": z["cons"],
                      "composite_z": sc, "PRI": 50 + 10 * sc, "rank": rk,
                      "PRI_lo": 50 + 10 * bt["score_lo"], "PRI_hi": 50 + 10 * bt["score_hi"],
                      "rank_lo": bt["rank_lo"], "rank_hi": bt["rank_hi"], "p_top10": bt["p_top10"], "p_top20": bt["p_top20"]})
    d["eligible"] = el
    d["status"] = np.where(el, "Ranked", np.where(d.pressure_deliveries >= 0.5 * nmin, "Low-confidence (below minimum pressure sample)", "Insufficient sample"))
    d["sample_confidence"] = np.where(d.pressure_deliveries >= 2.0 * nmin, "High", np.where(el, "Moderate", "Low"))
    g = grid[role][0]
    d = d.merge(g[["share_top10", "share_top20", "best", "worst"]].rename(columns={"best": "grid_best_rank", "worst": "grid_worst_rank"}), left_on="player_id", right_index=True, how="left")
    d[["share_top10", "share_top20"]] = d[["share_top10", "share_top20"]].fillna(0.0)
    # reliability tier (grouping instead of over-reading small score gaps)
    d["tier"] = np.select([(d["rank"] <= 20) & (d.p_top10 >= 0.30) & (d.share_top10 >= 0.30),
                           (d["rank"] <= 20) & ((d.p_top20 >= 0.30) | (d.share_top20 >= 0.30)), d.eligible],
                          ["A - robust contender", "B - plausible, assumption-sensitive", "C - ranked pool"], "Unranked")
    prof = profiles.batting_table(s) if role == "bat" else profiles.bowling_table(s)
    d = d.merge(prof, left_on="player_id", right_index=True, how="left")
    # Unit clarity: pressure_deliveries is the statistical unit (batters: balls faced; bowlers: ALL deliveries bowled incl. wides/no-balls).
    # pressure_legal_balls is the cricket "balls" count (batters: same as faced; bowlers: legal deliveries only).
    d["pressure_legal_balls"] = d["p_balls"] if role == "bat" else d["p_legal_balls"]
    for col in ("rank_lo", "rank_hi"):
        d[col] = d[col].round()
    d.insert(1, "player", d.player_id.map(names))
    rl = roles["role_inferred"] if isinstance(roles, pd.DataFrame) else roles
    d["role_inferred"] = d.player_id.map(rl)
    d = d.merge(teams, left_on="player_id", right_index=True, how="left")
    notes = d.apply(_note_bat if role == "bat" else _note_bowl, axis=1, result_type="expand") if len(d) else None
    d[["strengths", "risks", "situations"]] = notes
    d = d.sort_values(["eligible", "rank"], ascending=[False, True]).reset_index(drop=True)
    meta = {"role": role, "min_pressure_deliveries": int(nmin), "min_appearances": MIN_APPEARANCES, "n_eligible": int(el.sum()), "V_runs_per_wicket": V,
            "tau": {k: float(v) for k, v in c["tau"].items()}, "eb": {k: {a: float(b) for a, b in v.items()} for k, v in c["eb"].items()},
            "ball_variance_runs_stream": float(P.A.var_p), "baseline_ball_variance_runs_stream": float(P.A.var_b), "n_players_with_pressure_deliveries": int((c["n_p"] > 0).sum())}
    return d, meta
