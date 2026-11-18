"""Independent validation of the ranking methodology.

1. bootstrap          resample MATCHES (not balls) -> uncertainty in score and rank, P(top-10), P(top-20)
2. split_half         random halves of matches -> is each component a stable property of the player? (Spearman-Brown)
3. temporal_validity  rank on early matches, test on later matches -> does it predict future pressure value, and does it
                      add anything beyond a conventional, non-pressure measure of quality?
4. sensitivity_grid   vary pressure definition, wicket cost, component weights and eligibility -> how often each player
                      stays in the top 10 / top 20
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import pressure, reliability as R, value
from .config import PressureConfig, SEED

WEIGHT_SETS = {
    "equal": {"level": 1, "delta": 1, "consistency": 1},
    "level_only": {"level": 1, "delta": 0, "consistency": 0},
    "level_heavy": {"level": 2, "delta": 1, "consistency": 1},
    "delta_heavy": {"level": 1, "delta": 2, "consistency": 1},
    "consistency_heavy": {"level": 1, "delta": 1, "consistency": 2},
}


def bootstrap(P: R.Panel, elig: np.ndarray, weights: dict, B: int = 300, seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    M = P.Np.shape[1]
    scores, ranks = np.full((B, len(elig)), np.nan), np.full((B, len(elig)), np.nan)
    fixed = R.components(P)["fit"]          # EB hyper-parameters held at full-data values (prior is not re-estimated per replicate)
    for b in range(B):
        w = rng.multinomial(M, np.full(M, 1.0 / M)).astype(float)
        c = R.components(P, w, fixed=fixed)
        sc, _ = R.composite(c, elig, weights)
        scores[b], ranks[b] = sc, R.rank_desc(sc, elig)
    return {"score_lo": np.nanpercentile(scores, 5, axis=0), "score_hi": np.nanpercentile(scores, 95, axis=0),
            "rank_lo": np.nanpercentile(ranks, 5, axis=0), "rank_hi": np.nanpercentile(ranks, 95, axis=0),
            "p_top10": np.nanmean(ranks <= 10, axis=0), "p_top20": np.nanmean(ranks <= 20, axis=0)}


def _rho(a, b):
    if np.nanstd(a) < 1e-12 or np.nanstd(b) < 1e-12:
        return np.nan
    return spearmanr(a, b).statistic


def split_half(P: R.Panel, weights: dict, min_half_balls: int, reps: int = 60, seed: int = SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    M = P.Np.shape[1]
    out = {k: [] for k in ("level_raw", "delta_raw", "cons_raw", "level", "delta", "cons", "composite")}
    for _ in range(reps):
        m = rng.random(M) < 0.5
        a, b = R.components(P, m.astype(float)), R.components(P, (~m).astype(float))
        ok = (a["n_p"] >= min_half_balls) & (b["n_p"] >= min_half_balls) & (a["n_b"] >= min_half_balls) & (b["n_b"] >= min_half_balls)
        if ok.sum() < 20:
            continue
        for k in ("level_raw", "delta_raw", "cons_raw", "level", "delta", "cons"):
            out[k].append(_rho(a[k][ok], b[k][ok]))
        sa, _ = R.composite(a, ok, weights); sb, _ = R.composite(b, ok, weights)
        out["composite"].append(_rho(sa[ok], sb[ok]))
    rows = []
    for k, v in out.items():
        r = float(np.nanmean(v)) if v else np.nan
        rows.append({"measure": k, "half_half_spearman": r, "spearman_brown_full": 2 * r / (1 + r) if r == r else np.nan, "reps": len(v)})
    return pd.DataFrame(rows).round(3)


def temporal_validity(P: R.Panel, match_dates: pd.Series, cutoff: str, weights: dict, min_early: int, min_late: int) -> dict:
    d = pd.to_datetime(match_dates.reindex(P.matches).values)
    early = (d <= pd.Timestamp(cutoff)).astype(float)
    ce, cl = R.components(P, early), R.components(P, 1 - early)
    elig_e = R.eligibility(ce, min_early, 3)
    sc_e, z = R.composite(ce, elig_e, weights)
    A, Bp = P.A, P.B
    conv_early = ((A.SVp + A.SVb) @ early + P.V * (Bp.SVp + Bp.SVb) @ early) / np.maximum(ce["n_p"] + ce["n_b"], 1)   # overall (all-ball) value above expectation
    ok = elig_e & (cl["n_p"] >= min_late)
    if ok.sum() < 15 or np.nanstd(sc_e[ok]) < 1e-12:
        return {"cutoff": cutoff, "n_players": int(ok.sum()), "note": "early-period shrinkage found no detectable between-player variance (tau=0); no prediction possible"}
    y = cl["mean_p"][ok] * 100
    preds = {"PRI composite (early)": sc_e[ok], "pressure LEVEL shrunk (early)": ce["level"][ok], "pressure DELTA shrunk (early)": ce["delta"][ok],
             "pressure CONSISTENCY shrunk (early)": ce["cons"][ok], "conventional all-ball value (early)": conv_early[ok],
             "pressure level raw (early)": ce["mean_p"][ok]}
    corr = {k: float(_rho(v, y)) for k, v in preds.items()}
    # incremental value: late pressure value ~ conventional + pressure-specific (standardised OLS, weighted by late balls)
    Xc = np.column_stack([np.ones(ok.sum()), (conv_early[ok] - conv_early[ok].mean()) / conv_early[ok].std()])
    Xp = np.column_stack([Xc, (sc_e[ok] - sc_e[ok].mean()) / sc_e[ok].std()])
    wts = cl["n_p"][ok]
    def r2(X):
        W = np.sqrt(wts)[:, None]
        beta, *_ = np.linalg.lstsq(X * W, y * W[:, 0], rcond=None)
        res = y - X @ beta
        return float(1 - (wts * res ** 2).sum() / (wts * (y - np.average(y, weights=wts)) ** 2).sum())
    top = np.argsort(-sc_e[ok])[:10]
    return {"cutoff": cutoff, "n_players": int(ok.sum()), "spearman_with_late_pressure_value": corr,
            "weighted_R2_conventional_only": r2(Xc), "weighted_R2_conventional_plus_PRI": r2(Xp),
            "late_pressure_value_per100_early_top10_mean": float(np.average(y[top], weights=wts[top])),
            "late_pressure_value_per100_all_eligible_mean": float(np.average(y, weights=wts))}


def make_flag(s: pd.DataFrame, variant: str) -> pd.Series:
    if variant == "B_closeness_rule":
        return pressure.definition_b(s)
    cfgs = {"primary": PressureConfig(), "pooled_quantiles": PressureConfig("pooled", by_innings=False), "stricter_top15": PressureConfig("stricter", (0.60, 0.85, 0.97)),
            "broader_top30": PressureConfig("broader", (0.40, 0.70, 0.90)),
            "critical_only": PressureConfig("critical", (0.50, 0.80, 0.95), ("Critical",))}
    return pressure.assign(s, cfgs[variant])[0].is_pressure


def sensitivity_grid(s: pd.DataFrame, V: float, min_balls: dict, min_matches: int, variants=None, v_mults=(0.5, 1.0, 2.0),
                     weight_sets=None, min_scales=(0.75, 1.0, 1.5)) -> dict:
    variants = variants or ["primary", "pooled_quantiles", "stricter_top15", "broader_top30", "critical_only", "B_closeness_rule"]
    weight_sets = weight_sets or WEIGHT_SETS
    recs = {"bat": [], "bowl": []}
    sv = value.add_values(s)
    streams = {"bat": ("r_bat_run", "r_bat_out"), "bowl": ("r_bowl_run", "r_bowl_wk")}
    pids = {"bat": "striker_id", "bowl": "bowler_id"}
    for var in variants:
        flag = make_flag(s, var)
        panels = {role: R.build_role_panel(sv, pids[role], streams[role], flag, V) for role in streams}
        for vm, (role, P) in itertools.product(v_mults, panels.items()):
            P.V = V * vm
            c = R.components(P)
            for ms, (wn, w) in itertools.product(min_scales, weight_sets.items()):
                el = R.eligibility(c, int(min_balls[role] * ms * (0.5 if var == "critical_only" else 1)), min_matches if var != "critical_only" else max(3, min_matches // 2))
                if el.sum() < 20:
                    continue
                sc, _ = R.composite(c, el, w)
                rk = R.rank_desc(sc, el)
                for i in np.where(rk <= 20)[0]:
                    recs[role].append((int(P.players[i]), var, vm, ms, wn, int(rk[i])))
                recs[role].append((-1, var, vm, ms, wn, 0))   # marker so config count is known
    out = {}
    for role, r in recs.items():
        df = pd.DataFrame(r, columns=["player_id", "variant", "v_mult", "min_scale", "weights", "rank"])
        n_cfg = int((df.player_id == -1).sum())
        df = df[df.player_id != -1]
        g = df.groupby("player_id").agg(n_top20=("rank", "size"), n_top10=("rank", lambda x: int((x <= 10).sum())), mean_rank_when_top20=("rank", "mean"), best=("rank", "min"), worst=("rank", "max"))
        g["share_top10"] = g.n_top10 / n_cfg
        g["share_top20"] = g.n_top20 / n_cfg
        out[role] = (g.sort_values(["share_top10", "share_top20"], ascending=False), n_cfg, df)
    return out
