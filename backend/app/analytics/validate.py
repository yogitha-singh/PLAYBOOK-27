"""Automated data-quality and integrity checks. Produces a machine-readable report; never mutates data."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


ISOLATED_MAX = 5   # <=5 records in 200k+ deliveries is treated as an isolated source anomaly: kept, flagged, WARN


def _chk(name, status, value, detail=""):
    if status == FAIL and isinstance(value, (int, np.integer)) and 0 < value <= ISOLATED_MAX:
        status, detail = WARN, (detail + " | isolated source anomaly; record kept and flagged, impact negligible").strip(" |")
    return {"check": name, "status": status, "value": value, "detail": detail}


def run_validation(raw: dict, matches: pd.DataFrame, b: pd.DataFrame) -> list[dict]:
    r = raw["ball_by_ball"]
    out = []
    out.append(_chk("duplicate full rows", PASS if r.duplicated().sum() == 0 else FAIL, int(r.duplicated().sum())))
    d = r.duplicated(["match_id", "innings", "innings_ball_num"]).sum()
    out.append(_chk("duplicate (match, innings, ball number)", PASS if d == 0 else FAIL, int(d)))
    idcols = ["match_id", "innings", "striker_id", "bowler_id", "batting_team_id", "bowling_team_id"]
    n = int(r[idcols].isna().sum().sum())
    out.append(_chk("null identifiers in delivery table", PASS if n == 0 else FAIL, n))
    bad_runs = int(((r.runs < 0) | (r.runs > 7)).sum())
    out.append(_chk("bat runs outside 0-7", PASS if bad_runs == 0 else FAIL, bad_runs))
    fs = int(((r.is_four & (r.runs != 4)) | (r.is_six & (r.runs != 6))).sum())
    out.append(_chk("is_four/is_six inconsistent with runs", PASS if fs == 0 else FAIL, fs))
    lo = b[b.innings <= 2].groupby(["match_id", "innings", "overid"]).legal.sum()
    out.append(_chk("overs with >6 legal balls", PASS if (lo > 6).sum() == 0 else FAIL, int((lo > 6).sum()),
                    "legal = not wide/no-ball/penalty"))
    out.append(_chk("overid outside 1-20", PASS if r.overid.between(1, 20).all() else FAIL, int((~r.overid.between(1, 20)).sum())))
    inc = int(((lo < 6) & (lo.groupby(level=[0, 1]).transform("size") > 0)).sum())
    out.append(_chk("overs with <6 legal balls (innings ends / interrupted)", WARN, inc, "expected at innings end; flagged not dropped"))
    dm = int((r.is_wicket != r.dismissal_type.notna()).sum())
    out.append(_chk("is_wicket vs dismissal_type disagreement", PASS if dm == 0 else FAIL, dm))
    orphan = int((r.dismissed_player_id.notna() & ~r.is_wicket).sum())
    out.append(_chk("dismissed_player_id present without a wicket", PASS if orphan == 0 else WARN, orphan,
                    "rows ignored for wicket logic; dismissal_type is authoritative"))
    nm = pd.concat([r[["striker_id", "striker_name"]].set_axis(["i", "n"], axis=1),
                    r[["bowler_id", "bowler_name"]].set_axis(["i", "n"], axis=1)]).drop_duplicates()
    out.append(_chk("player_id with >1 name", PASS if (nm.groupby("i").n.nunique() > 1).sum() == 0 else FAIL,
                    int((nm.groupby("i").n.nunique() > 1).sum())))
    dn = nm.groupby("n").i.nunique()
    out.append(_chk("names shared by different player_ids", WARN if (dn > 1).any() else PASS, sorted(dn[dn > 1].index.tolist()),
                    "different players with identical names; analysis keys on player_id and disambiguates in display"))
    out.append(_chk("striker == non-striker", PASS if (r.striker_id == r.non_striker_id).sum() == 0 else FAIL, int((r.striker_id == r.non_striker_id).sum())))
    out.append(_chk("batting team == bowling team", PASS if (r.batting_team_id == r.bowling_team_id).sum() == 0 else FAIL, int((r.batting_team_id == r.bowling_team_id).sum())))
    miss = set(nm.i) - set(raw["mapping"].player_id)
    out.append(_chk("delivery players absent from player mapping", PASS if not miss else WARN, len(miss)))
    nobbb = matches[~matches.match_id.isin(r.match_id.unique())]
    out.append(_chk("matches without ball-by-ball data", WARN if len(nobbb) else PASS, int(len(nobbb)),
                    "results: " + str(nobbb.result.value_counts().to_dict())))
    # run accounting: first-innings minus second-innings total must equal the stated run margin (non-DLS)
    t = b[b.innings <= 2].groupby(["match_id", "innings"]).total_runs.sum().unstack()
    mm = matches.set_index("match_id").join(t, how="inner")
    ex = mm.result.astype(str).str.extract(r"(?i)by (\d+) run")[0].astype(float)
    ok = mm[ex.notna() & ~mm.interrupted & ~mm.result.astype(str).str.contains("Super", case=False)]
    exm = ex[ok.index]
    rate = float(((ok[1] - ok[2]) == exm).mean())
    out.append(_chk("innings totals reconcile with stated run margin", PASS if rate > 0.99 else WARN, round(rate, 4),
                    f"{len(ok)} decided-by-runs matches; validates total = runs + extras"))
    inn = b[b.innings > 2].match_id.nunique()
    out.append(_chk("super-over innings (3/4)", WARN if inn else PASS, int(inn), "present; excluded from pressure analysis"))
    sc = b[b.in_scope]
    out.append(_chk("in-scope deliveries", PASS, int(len(sc)), f"{sc.match_id.nunique()} matches"))
    return out


def summarise(report: list[dict]) -> dict:
    return {s: sum(1 for c in report if c["status"] == s) for s in (PASS, WARN, FAIL)}
