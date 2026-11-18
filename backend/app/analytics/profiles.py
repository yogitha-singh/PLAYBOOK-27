"""Conventional statistics, pressure-vs-baseline splits, inferred roles and display names.
Cricket rules: balls faced excludes wides; bowler balls = legal deliveries; bowler runs exclude byes/leg-byes;
bowler wickets exclude run-outs/retired/obstructing; batting average = runs / dismissals (undefined if never out)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def display_names(raw: dict) -> pd.Series:
    b = raw["ball_by_ball"]
    nm = pd.concat([b[["striker_id", "striker_name"]].set_axis(["id", "name"], axis=1),
                    b[["bowler_id", "bowler_name"]].set_axis(["id", "name"], axis=1)]).drop_duplicates()
    dup = nm.groupby("name").id.transform("nunique") > 1
    nm["display"] = np.where(dup, nm.name + " (#" + nm.id.astype(str) + ")", nm.name)
    return nm.set_index("id").display


def latest_teams(b: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    tn = teams.drop_duplicates("team_id", keep="last").set_index("team_id").team_name
    rows = pd.concat([b[["match_date", "striker_id", "batting_team_id", "tier"]].set_axis(["d", "pid", "tid", "tier"], axis=1),
                      b[["match_date", "bowler_id", "bowling_team_id", "tier"]].set_axis(["d", "pid", "tid", "tier"], axis=1)])
    rows = rows.sort_values("d").drop_duplicates(["pid", "tier"], keep="last")
    rows["team"] = rows.tid.map(tn)
    w = rows.pivot(index="pid", columns="tier", values="team")
    w.columns = [f"latest_team_{c.lower()}" for c in w.columns]
    return w


def batter_role(s: pd.DataFrame) -> pd.Series:
    pos = s[s.faced].groupby("striker_id").striker_order.median()
    lab = pd.cut(pos, [0, 2, 3, 5, 7, 11], labels=["Opener", "Number 3", "Middle order", "Finisher / lower-middle", "Lower order"])
    return lab.astype(str).rename("role_inferred")


def bowler_role(s: pd.DataFrame) -> pd.DataFrame:
    d = s[s.legal]
    g = d.groupby("bowler_id")
    share = pd.crosstab(d.bowler_id, d.phase, normalize="index")
    pace = g.is_pace.mean()
    out = pd.DataFrame({"pace_share": pace, "pp_share": share.get("Powerplay"), "mid_share": share.get("Middle"), "death_share": share.get("Death")})
    kind = np.where(out.pace_share >= 0.5, "Pace", "Spin")
    use = np.select([out.death_share >= 0.30, out.pp_share >= 0.35], ["death", "powerplay"], "middle")
    out["role_inferred"] = [f"{k} - {u} overs" for k, u in zip(kind, use)]
    return out


def batting_table(s: pd.DataFrame, flag_col: str = "is_pressure") -> pd.DataFrame:
    f = s[s.faced].copy()
    f["dot"] = f.bat_runs == 0
    f["bdry"] = f.is_four | f.is_six

    def agg(d, p=""):
        g = d.groupby("striker_id").agg(**{f"{p}balls": ("faced", "size"), f"{p}runs": ("bat_runs", "sum"), f"{p}dismissals": ("batter_out", "sum"),
                                           f"{p}fours": ("is_four", "sum"), f"{p}sixes": ("is_six", "sum"), f"{p}dots": ("dot", "sum"),
                                           f"{p}exp_runs": ("exp_runs", "sum"), f"{p}exp_out": ("exp_out", "sum")})
        return g
    t = agg(f)
    t["innings"] = f.groupby("striker_id").apply(lambda d: d.groupby(["match_id", "innings"]).ngroups, include_groups=False)
    t["matches"] = f.groupby("striker_id").match_id.nunique()
    t["average"] = t.runs / t.dismissals.replace(0, np.nan)
    t["strike_rate"] = 100 * t.runs / t.balls
    t["boundary_pct"] = 100 * (t.fours + t.sixes) / t.balls
    t["dot_pct"] = 100 * t.dots / t.balls
    p = agg(f[f[flag_col]], "p_")
    n = agg(f[~f[flag_col]], "b_")
    t = t.join(p).join(n).fillna({c: 0 for c in list(p.columns) + list(n.columns)})
    t["p_strike_rate"] = 100 * t.p_runs / t.p_balls.replace(0, np.nan)
    t["b_strike_rate"] = 100 * t.b_runs / t.b_balls.replace(0, np.nan)
    t["p_dismissal_rate_pct"] = 100 * t.p_dismissals / t.p_balls.replace(0, np.nan)
    t["b_dismissal_rate_pct"] = 100 * t.b_dismissals / t.b_balls.replace(0, np.nan)
    t["p_dot_pct"] = 100 * t.p_dots / t.p_balls.replace(0, np.nan)
    t["p_runs_above_exp"] = t.p_runs - t.p_exp_runs
    t["p_dismissals_below_exp"] = t.p_exp_out - t.p_dismissals
    for ph in ("Powerplay", "Middle", "Death"):
        d = f[f.phase == ph].groupby("striker_id").agg(b=("faced", "size"), r=("bat_runs", "sum"))
        t[f"sr_{ph.lower()}"] = (100 * d.r / d.b.where(d.b >= 30)).reindex(t.index)
        t[f"balls_{ph.lower()}"] = d.b.reindex(t.index).fillna(0)
    for lab, inn in (("setting", 1), ("chasing", 2)):
        d = f[f.innings == inn].groupby("striker_id").agg(b=("faced", "size"), r=("bat_runs", "sum"))
        t[f"sr_{lab}"] = (100 * d.r / d.b.where(d.b >= 30)).reindex(t.index)
    return t


def bowling_table(s: pd.DataFrame, flag_col: str = "is_pressure") -> pd.DataFrame:
    d0 = s[~s.is_penalty].copy()
    d0["dot"] = d0.legal & (d0.bowler_runs == 0)
    d0["bdry"] = d0.legal & (d0.is_four | d0.is_six)

    def agg(d, p=""):
        return d.groupby("bowler_id").agg(**{f"{p}legal_balls": ("legal", "sum"), f"{p}runs": ("bowler_runs", "sum"), f"{p}wickets": ("bowler_wkt", "sum"),
                                              f"{p}dots": ("dot", "sum"), f"{p}boundaries": ("bdry", "sum"), f"{p}exp_runs": ("exp_charged", "sum"), f"{p}exp_wkts": ("exp_bwk", "sum")})
    t = agg(d0)
    t["matches"] = d0.groupby("bowler_id").match_id.nunique()
    t["economy"] = 6 * t.runs / t.legal_balls
    t["average"] = t.runs / t.wickets.replace(0, np.nan)
    t["strike_rate"] = t.legal_balls / t.wickets.replace(0, np.nan)
    t["dot_pct"] = 100 * t.dots / t.legal_balls
    t["boundary_pct"] = 100 * t.boundaries / t.legal_balls
    t["wickets_per_match"] = t.wickets / t.matches
    p, n = agg(d0[d0[flag_col]], "p_"), agg(d0[~d0[flag_col]], "b_")
    t = t.join(p).join(n).fillna({c: 0 for c in list(p.columns) + list(n.columns)})
    t["p_economy"] = 6 * t.p_runs / t.p_legal_balls.replace(0, np.nan)
    t["b_economy"] = 6 * t.b_runs / t.b_legal_balls.replace(0, np.nan)
    t["p_wicket_rate_per_over"] = 6 * t.p_wickets / t.p_legal_balls.replace(0, np.nan)
    t["b_wicket_rate_per_over"] = 6 * t.b_wickets / t.b_legal_balls.replace(0, np.nan)
    t["p_dot_pct"] = 100 * t.p_dots / t.p_legal_balls.replace(0, np.nan)
    t["p_runs_saved_vs_exp"] = t.p_exp_runs - t.p_runs
    t["p_wkts_above_exp"] = t.p_wickets - t.p_exp_wkts
    for ph in ("Powerplay", "Middle", "Death"):
        d = d0[(d0.phase == ph) & d0.legal].groupby("bowler_id").agg(b=("legal", "size"), r=("bowler_runs", "sum"))
        t[f"econ_{ph.lower()}"] = (6 * d.r / d.b.where(d.b >= 30)).reindex(t.index)
        t[f"balls_{ph.lower()}"] = d.b.reindex(t.index).fillna(0)
    for lab, inn in (("defending", 1), ("chasing_opp", 2)):
        d = d0[(d0.innings == inn) & d0.legal].groupby("bowler_id").agg(b=("legal", "size"), r=("bowler_runs", "sum"))
        t[f"econ_{lab}"] = (6 * d.r / d.b.where(d.b >= 30)).reindex(t.index)
    return t
