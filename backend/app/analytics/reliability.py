"""Pressure Reliability Index (PRI).

Three components per player, each measured on PRESSURE deliveries, each expressed relative to an average player
in the same situation and each empirically-Bayes shrunk so small samples cannot top the table:

  LEVEL        mean value above expectation per pressure ball (x100)  - absolute contribution when it matters
  DELTA        pressure value minus the player's OWN non-pressure value - rising (or falling) relative to usual level
  CONSISTENCY  share of pressure appearances (>= KM pressure balls in a match) with total value >= 0

Empirical Bayes (normal-normal, DerSimonian-Laird heteroskedastic estimator):
  observed mean x_i ~ N(theta_i, se_i^2),  theta_i ~ N(mu, tau^2)
  posterior mean = mu + B_i (x_i - mu),  B_i = tau^2/(tau^2 + se_i^2),  posterior var = B_i se_i^2
Composite: weighted mean of the three z-scores (z computed on the eligible pool).  Higher = better, always.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

KM = 6  # a "pressure appearance" needs at least one over-equivalent of pressure balls in the match


def eb_shrink(x, se2, fit_mask=None, iters=100, fixed=None):
    x, se2 = np.asarray(x, float), np.asarray(se2, float)
    if fixed is not None:           # hyper-parameters (mu, tau2) supplied: used by the bootstrap to avoid prior re-estimation bias
        mu, tau2 = fixed
        B = tau2 / (tau2 + se2) if tau2 > 0 else np.zeros_like(se2)
        return {"mu": float(mu), "tau2": float(tau2), "B": B, "post": mu + B * (x - mu), "post_sd": np.sqrt(B * se2)}
    m = np.ones(len(x), bool) if fit_mask is None else np.asarray(fit_mask, bool)
    xs, ss = x[m], se2[m]
    mu, tau2 = xs.mean(), xs.var()
    for _ in range(iters):
        w = 1.0 / (ss + tau2)
        mu = (w * xs).sum() / w.sum()
        w0 = 1.0 / ss
        mu0 = (w0 * xs).sum() / w0.sum()
        Q = (w0 * (xs - mu0) ** 2).sum()
        k = len(xs)
        tau2_new = max(0.0, (Q - (k - 1)) / (w0.sum() - (w0 ** 2).sum() / w0.sum()))
        if abs(tau2_new - tau2) < 1e-12:
            break
        tau2 = tau2_new
    B = tau2 / (tau2 + se2) if tau2 > 0 else np.zeros_like(se2)
    post = mu + B * (x - mu)
    return {"mu": float(mu), "tau2": float(tau2), "B": B, "post": post, "post_sd": np.sqrt(B * se2)}


@dataclass
class Panel:
    """Player x match arrays for one role/pressure definition (enables fast bootstrap by match)."""
    players: np.ndarray
    matches: np.ndarray
    Np: np.ndarray; SVp: np.ndarray; Nb: np.ndarray; SVb: np.ndarray
    App: np.ndarray; Hit: np.ndarray
    var_p: float; var_b: float; p0: float


def build_panel(s: pd.DataFrame, pid: str, vcol: str, flag: pd.Series) -> Panel:
    d = pd.DataFrame({"pid": s[pid].values, "mid": s.match_id.values, "p": np.asarray(flag), "v": s[vcol].values}).dropna(subset=["v"])
    d["v2"] = d.v ** 2
    g = d.groupby(["pid", "mid", "p"]).agg(n=("v", "size"), sv=("v", "sum"), sv2=("v2", "sum")).reset_index()
    players, matches = np.sort(g.pid.unique()), np.sort(g.mid.unique())
    pi, mi = np.searchsorted(players, g.pid.values), np.searchsorted(matches, g.mid.values)
    shape = (len(players), len(matches))
    N = {f: np.zeros(shape) for f in (True, False)}
    SV = {f: np.zeros(shape) for f in (True, False)}
    for f in (True, False):
        r = g[g.p == f]
        ri, rj = np.searchsorted(players, r.pid.values), np.searchsorted(matches, r.mid.values)
        N[f][ri, rj], SV[f][ri, rj] = r.n.values, r.sv.values

    def pooled_var(f):
        r = g[g.p == f]
        n, s1, s2 = r.n.sum(), r.sv.sum(), r.sv2.sum()
        return float((s2 - s1 ** 2 / n) / (n - 1))
    app = (N[True] >= KM).astype(float)
    hit = app * (SV[True] >= 0)
    p0 = hit.sum() / max(app.sum(), 1)
    return Panel(players, matches, N[True], SV[True], N[False], SV[False], app, hit, pooled_var(True), pooled_var(False), float(p0))


def _stream(P: Panel, w: np.ndarray | None = None, fit_min_balls: int = 12, fixed: dict | None = None) -> dict:
    w = np.ones(P.Np.shape[1]) if w is None else w
    n_p, sv_p, n_b, sv_b = P.Np @ w, P.SVp @ w, P.Nb @ w, P.SVb @ w
    app, hit = P.App @ w, P.Hit @ w
    with np.errstate(divide="ignore", invalid="ignore"):
        mp, mb = sv_p / n_p, sv_b / n_b
        cons = hit / app
    ok = (n_p > 0) & (n_b > 0)
    level_raw = np.where(ok, mp, 0.0); se_l = np.where(n_p > 0, P.var_p / np.maximum(n_p, 1), 1e6)
    delta_raw = np.where(ok, mp - mb, 0.0); se_d = np.where(ok, P.var_p / np.maximum(n_p, 1) + P.var_b / np.maximum(n_b, 1), 1e6)
    cons_raw = np.where(app > 0, cons, P.p0); se_c = np.where(app > 0, P.p0 * (1 - P.p0) / np.maximum(app, 1), 1e6)
    fit = (n_p >= fit_min_balls) & (n_b >= fit_min_balls) & (app >= 2)
    fx = fixed or {}
    L, D, C = (eb_shrink(level_raw, se_l, fit, fixed=fx.get("level")), eb_shrink(delta_raw, se_d, fit, fixed=fx.get("delta")),
               eb_shrink(cons_raw, se_c, fit, fixed=fx.get("cons")))
    return {"n_p": n_p, "n_b": n_b, "app": app, "mean_p": mp, "mean_b": mb, "level_raw": level_raw, "delta_raw": delta_raw, "cons_raw": cons_raw,
            "level": L["post"], "delta": D["post"], "cons": C["post"], "level_sd": L["post_sd"], "delta_sd": D["post_sd"], "cons_sd": C["post_sd"],
            "eb": {"level": {k: v for k, v in L.items() if k in ("mu", "tau2")}, "delta": {k: v for k, v in D.items() if k in ("mu", "tau2")},
                   "cons": {k: v for k, v in C.items() if k in ("mu", "tau2")}},
            "fit": {"level": (L["mu"], L["tau2"]), "delta": (D["mu"], D["tau2"]), "cons": (C["mu"], C["tau2"])},
            "B_level": L["B"], "mu": {"level": L["mu"], "delta": D["mu"], "cons": C["mu"]},
            "tau": {"level": np.sqrt(L["tau2"]), "delta": np.sqrt(D["tau2"]), "cons": np.sqrt(C["tau2"])}}


@dataclass
class RolePanel:
    """Two residual streams (runs, wickets/dismissals) over the same balls, combined in runs with wicket cost V AFTER separate shrinkage."""
    A: Panel
    B: Panel
    V: float

    @property
    def players(self): return self.A.players
    @property
    def matches(self): return self.A.matches
    @property
    def Np(self): return self.A.Np


def build_role_panel(s: pd.DataFrame, pid: str, cols: tuple, flag, V: float) -> RolePanel:
    return RolePanel(build_panel(s, pid, cols[0], flag), build_panel(s, pid, cols[1], flag), V)


def components(P, w: np.ndarray | None = None, fit_min_balls: int = 12, fixed: dict | None = None) -> dict:
    if isinstance(P, Panel):
        return _stream(P, w, fit_min_balls, fixed)
    fixed = fixed or {}
    a, b = _stream(P.A, w, fit_min_balls, fixed.get("A")), _stream(P.B, w, fit_min_balls, fixed.get("B"))
    out = dict(a)
    out["fit"] = {"A": a["fit"], "B": b["fit"]}
    V = P.V
    for k in ("level", "delta", "level_raw", "delta_raw", "mean_p", "mean_b"):
        out[k] = a[k] + V * b[k]
    out["level_sd"] = np.sqrt(a["level_sd"] ** 2 + (V * b["level_sd"]) ** 2)
    out["delta_sd"] = np.sqrt(a["delta_sd"] ** 2 + (V * b["delta_sd"]) ** 2)
    out["eb"] = {"runs_level": a["eb"]["level"], "runs_delta": a["eb"]["delta"], "runs_consistency": a["eb"]["cons"],
                 "wicket_level": b["eb"]["level"], "wicket_delta": b["eb"]["delta"]}
    out["stream_runs"] = {k: a[k] for k in ("level", "delta", "level_raw")}
    out["stream_wkt"] = {k: b[k] for k in ("level", "delta", "level_raw")}
    out["B_level_runs"], out["B_level_wkt"] = a["B_level"], b["B_level"]
    ea, eb = a["eb"], b["eb"]
    out["mu"] = {"level": ea["level"]["mu"] + V * eb["level"]["mu"], "delta": ea["delta"]["mu"] + V * eb["delta"]["mu"], "cons": ea["cons"]["mu"]}
    out["tau"] = {"level": np.sqrt(ea["level"]["tau2"] + V ** 2 * eb["level"]["tau2"]), "delta": np.sqrt(ea["delta"]["tau2"] + V ** 2 * eb["delta"]["tau2"]),
                  "cons": np.sqrt(ea["cons"]["tau2"])}
    return out


def eligibility(c: dict, min_balls: int, min_matches: int) -> np.ndarray:
    return (c["n_p"] >= min_balls) & (c["app"] >= min_matches) & (c["n_b"] >= min_balls)


def composite(c: dict, elig: np.ndarray, weights: dict) -> tuple[np.ndarray, dict]:
    """Each shrunk component is expressed in units of its estimated TRUE-score SD (tau): z = (posterior - mu) / tau.
    A component whose between-player variance is indistinguishable from noise (tau ~ 0) therefore contributes nothing,
    instead of having its noise inflated by pool-standardisation. `weights` are then relative importance multipliers."""
    z = {}
    for k in ("level", "delta", "cons"):
        tau = c["tau"][k]
        z[k] = (c[k] - c["mu"][k]) / tau if tau > 1e-9 else np.zeros_like(c[k])
    wsum = sum(weights.values())
    return (weights["level"] * z["level"] + weights["delta"] * z["delta"] + weights["consistency"] * z["cons"]) / wsum, z


def derive_min_sample(c: dict, var_ball: float, target_B: float = 0.20) -> int:
    """Smallest pressure-ball count at which >= target_B of the player's posterior LEVEL comes from his own data
    (B = n/(n+k), k = ball-variance / tau^2), i.e. n = k*B/(1-B)."""
    tau2 = c["tau"]["level"] ** 2
    return int(np.ceil((var_ball / tau2) * target_B / (1 - target_B))) if tau2 > 0 else 10 ** 9


def rank_desc(score: np.ndarray, elig: np.ndarray) -> np.ndarray:
    r = np.full(len(score), np.nan)
    idx = np.where(elig)[0]
    order = idx[np.argsort(-score[idx], kind="stable")]
    r[order] = np.arange(1, len(order) + 1)
    return r
