"""Cricket-rule-aware cleaning. Nothing is silently dropped: rows are FLAGGED and every
exclusion is counted in the cleaning log (data/processed/cleaning_log.json)."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from . import config

BOWLER_CREDITED = {"caught", "bowled", "lbw", "stump", "hit wicket"}   # run-out / retired / obstructing are not credited to the bowler


def _tier(row) -> str:
    if row.match_format == "T20I":
        return "T20I"
    return "IPL" if "IPL" in str(row.comp_name) else "EMERGING"


def build_matches(raw: dict) -> pd.DataFrame:
    m = raw["matches"].merge(raw["competitions"], on="comp_id", how="left", validate="m:1")
    m["tier"] = m.apply(_tier, axis=1)
    m["match_date"] = pd.to_datetime(m["match_date"])
    m["interrupted"] = (m[["first_inn_revised_overs", "second_inn_revised_overs", "revised_target"]].notna().any(axis=1)
                        | m["result"].astype(str).str.contains(r"d/?l|dls", case=False, regex=True))
    return m.sort_values(["match_date", "match_id"]).reset_index(drop=True)


def clean_deliveries(raw: dict, matches: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    log: dict = {}
    b = raw["ball_by_ball"].copy()
    b = b.sort_values(["match_id", "innings", "innings_ball_num"]).reset_index(drop=True)
    log["rows_in"] = int(len(b))

    et = b["extras_type"].fillna("none").str.lower().str.strip()
    b["extras_type"] = et
    b["is_wide"] = et.eq("wide")
    b["is_noball"] = et.isin(["overstep", "other"])      # 'other' behaves exactly like a no-ball in this feed
    b["is_penalty"] = et.eq("penalty")                   # 5 penalty runs: not a delivery
    b["legal"] = ~(b.is_wide | b.is_noball | b.is_penalty)   # counts toward the 6 balls of an over
    b["faced"] = ~(b.is_wide | b.is_penalty)                 # batter faces no-balls, not wides
    b["bat_runs"] = b["runs"].where(~b.is_penalty, 0)
    b["total_runs"] = b["runs"] + b["extras1_runs"] + b["extras_2_runs"]
    # Runs charged to the bowler: bat runs + wides + no-ball penalties; NOT byes/leg-byes/penalty.
    b["bowler_runs"] = np.where(b.is_wide | b.is_noball, b["runs"] + b["extras1_runs"], b["runs"])
    b.loc[b.is_penalty, "bowler_runs"] = 0

    dt = b["dismissal_type"].fillna("").str.lower().str.replace("obstracting", "obstructing", regex=False)
    b["dismissal_type"] = dt.replace("", np.nan)
    wk = dt.ne("")
    log["wicket_flag_vs_dismissal_type_disagreements"] = int((b.is_wicket != wk).sum())
    b["is_wicket"] = wk                                   # dismissal_type is the authoritative wicket indicator
    b["team_wicket"] = wk                                 # a wicket falls for the batting side (incl. retired-out)
    real = wk & ~dt.eq("retire out")
    b["batter_out"] = real & (b.dismissed_player_id == b.striker_id)
    b["bowler_wkt"] = dt.isin(BOWLER_CREDITED)

    b = b.merge(matches[["match_id", "match_date", "tier", "venue_id", "interrupted", "first_inn_revised_overs",
                         "win_team_id", "result"]], on="match_id", how="left", validate="m:1")
    b["is_ipl"] = (b.tier == "IPL").astype(int)
    b["is_t20i"] = (b.tier == "T20I").astype(int)
    b["is_left"] = b.batting_type.eq("LHB").astype(int)
    b["is_pace"] = b.pace_or_spin.eq("Pace").astype(int)
    b["batting_order"] = b["batting_order"].clip(upper=11)
    log["rows_out"] = int(len(b))
    return b, log


def flag_analysis_scope(b: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Decide which innings/matches enter the pressure analysis. Reasons are recorded, never silent."""
    log: dict = {}
    g = b[b.innings <= 2].groupby(["match_id", "innings"]).agg(
        legal=("legal", "sum"), wk=("team_wicket", "sum"), tot=("total_runs", "sum"),
        team=("batting_team_id", "first"), rev=("first_inn_revised_overs", "first"))
    inn1, inn2 = g.xs(1, level=1), g.xs(2, level=1)
    ms = inn1.join(inn2, lsuffix="1", rsuffix="2", how="left")
    ms["has_both"] = ms.legal2.notna()
    ms["inn1_complete"] = (ms.legal1 >= 120) | (ms.wk1 >= 10)
    chased = ms.tot2 > ms.tot1
    ms["inn2_complete"] = ms.has_both & ((ms.legal2 >= 120) | (ms.wk2 >= 10) | chased)
    ms = ms.join(b.groupby("match_id")[["interrupted", "tier"]].first())
    ms["in_scope"] = ms.has_both & ms.inn1_complete & ms.inn2_complete & ~ms.interrupted
    log["matches_with_ball_data"] = int(len(ms))
    log["excluded_single_innings"] = int((~ms.has_both).sum())
    log["excluded_interrupted_dls_or_revised_overs"] = int((ms.has_both & ms.interrupted).sum())
    log["excluded_truncated_innings"] = int((ms.has_both & ~ms.interrupted & ~(ms.inn1_complete & ms.inn2_complete)).sum())
    log["matches_in_scope"] = int(ms.in_scope.sum())
    log["in_scope_by_tier"] = ms[ms.in_scope].tier.value_counts().to_dict()
    # outcome label derived from the SCOREBOARD (state-determined); cross-checked with matches.win_team_id
    ms["first_wins"] = np.where(ms.tot1 > ms.tot2, 1.0, np.where(ms.tot1 < ms.tot2, 0.0, np.nan))
    b = b.merge(ms[["in_scope", "tot1", "first_wins", "team1"]].rename(columns={"tot1": "inn1_total", "team1": "first_bat_team"}),
                left_on="match_id", right_index=True, how="left")
    b["in_scope"] = b["in_scope"].fillna(False) & (b.innings <= 2)
    return b, log
