"""Pre-delivery match-state features. Every feature is computed from information available BEFORE the
delivery is bowled (cumulative sums are shifted by one ball). Outcome columns are never used as inputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

CONTEXT_FEATURES = [
    "innings", "balls_rem", "wkts_rem", "score_before", "crr", "target_runs_req", "rrr", "rrr_minus_crr",
    "over_idx", "ball_in_over", "bat_elo", "bowl_elo", "elo_diff", "venue_avg_first", "is_ipl", "is_t20i",
    "striker_order", "striker_balls_before", "striker_runs_before", "is_left", "is_pace",
]
# crr / rrr_minus_crr are deliberately EXCLUDED from the win-probability model: after 1-3 balls they swing wildly
# (one boundary on ball 1 => crr = 24) and made leverage artificially high at the start of innings.
WP_FEATURES = ["innings", "balls_rem", "wkts_rem", "score_before", "target_runs_req", "rrr",
               "elo_diff", "venue_avg_first", "is_ipl", "is_t20i"]


def compute_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Chronological pre-match Elo for every team (only past matches are used)."""
    rating: dict[int, float] = {}
    rows = []
    for r in matches.sort_values(["match_date", "match_id"]).itertuples():
        h, a = int(r.home_team_id), int(r.away_team_id)
        rh, ra = rating.get(h, config.ELO_START), rating.get(a, config.ELO_START)
        rows.append((r.match_id, h, rh, a, ra))
        if pd.notna(r.win_team_id) and int(r.win_team_id) in (h, a):
            eh = 1 / (1 + 10 ** ((ra - rh) / 400))
            sh = 1.0 if int(r.win_team_id) == h else 0.0
            rating[h] = rh + config.ELO_K * (sh - eh)
            rating[a] = ra + config.ELO_K * ((1 - sh) - (1 - eh))
    return pd.DataFrame(rows, columns=["match_id", "home_id", "home_elo", "away_id", "away_elo"])


def venue_prior(matches: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
    """Shrunk average first-innings total at the venue using strictly EARLIER matches only."""
    fi = (b[(b.innings == 1) & b.in_scope].groupby("match_id").agg(tot=("total_runs", "sum")).join(
        matches.set_index("match_id")[["match_date", "venue_id"]]).sort_values("match_date", kind="stable"))
    out, vsum, vcnt, gsum, gcnt = {}, {}, {}, 0.0, 0
    k = config.VENUE_PRIOR_STRENGTH
    for mid, row in fi.iterrows():
        gmean = gsum / gcnt if gcnt else 150.0
        s, c = vsum.get(row.venue_id, 0.0), vcnt.get(row.venue_id, 0)
        out[mid] = (s + k * gmean) / (c + k)
        vsum[row.venue_id], vcnt[row.venue_id] = s + row.tot, c + 1
        gsum, gcnt = gsum + row.tot, gcnt + 1
    return pd.Series(out, name="venue_avg_first")


def add_state_features(b: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    b = b.copy()
    key = ["match_id", "innings"]
    grp = b.groupby(key, sort=False)
    b["score_before"] = grp["total_runs"].cumsum() - b["total_runs"]
    b["wkts_before"] = grp["team_wicket"].cumsum() - b["team_wicket"].astype(int)
    b["legal_before"] = grp["legal"].cumsum() - b["legal"].astype(int)
    b["wkts_rem"] = config.WICKETS - b["wkts_before"]
    b["balls_rem"] = (config.STANDARD_BALLS - b["legal_before"]).clip(lower=0)
    b["over_idx"] = (b["legal_before"] // 6).clip(upper=19)
    b["ball_in_over"] = b["legal_before"] % 6
    b["crr"] = np.where(b.legal_before > 0, b.score_before / b.legal_before.clip(lower=1) * 6, 0.0)
    b["phase"] = pd.cut(b.over_idx, [-1, 5, 14, 19], labels=["Powerplay", "Middle", "Death"]).astype(str)
    tgt = (b["inn1_total"] + 1).where(b.innings == 2)
    b["target"] = tgt
    b["target_runs_req"] = (tgt - b.score_before).where(b.innings == 2, 0.0)
    rrr = np.where((b.innings == 2) & (b.balls_rem > 0), b.target_runs_req / b.balls_rem.clip(lower=1) * 6, 0.0)
    b["rrr"] = np.clip(rrr, 0, 36.0)                      # cap: >36 rpo (6 per ball) is "unwinnable" for any state
    b["crr"] = b["crr"].clip(upper=36.0)
    b["rrr_minus_crr"] = np.where(b.innings == 2, b.rrr - b.crr, 0.0)
    # striker's own innings so far (before this ball)
    sk = b.groupby(["match_id", "innings", "striker_id"], sort=False)
    b["striker_balls_before"] = sk["faced"].cumsum() - b["faced"].astype(int)
    b["striker_runs_before"] = sk["bat_runs"].cumsum() - b["bat_runs"]
    b["striker_order"] = b["batting_order"]
    # Elo (bat/bowl perspective) and venue prior
    elo = compute_elo(matches)
    b = b.merge(elo, on="match_id", how="left")
    is_home = b.batting_team_id == b.home_id
    b["bat_elo"] = np.where(is_home, b.home_elo, b.away_elo)
    b["bowl_elo"] = np.where(is_home, b.away_elo, b.home_elo)
    b["elo_diff"] = b.bat_elo - b.bowl_elo
    vp = venue_prior(matches, b)
    b = b.merge(vp, left_on="match_id", right_index=True, how="left")
    b["venue_avg_first"] = b["venue_avg_first"].fillna(150.0)
    # after-ball state (used ONLY to build training targets such as win-probability swings)
    b["score_after"] = b.score_before + b.total_runs
    b["wkts_after"] = b.wkts_before + b.team_wicket.astype(int)
    b["legal_after"] = b.legal_before + b.legal.astype(int)
    return b.drop(columns=["home_id", "home_elo", "away_id", "away_elo"])


def assert_no_leakage(feature_names: list[str]) -> None:
    bad = [c for c in feature_names if c in config.LEAKY_COLUMNS]
    if bad:
        raise AssertionError(f"Leaky columns used as features: {bad}")
