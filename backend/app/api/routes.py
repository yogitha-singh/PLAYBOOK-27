"""PLAYBOOK 27 REST API (v1). Only derived, player-level aggregates are served - never delivery-level records."""
from __future__ import annotations

import time

from flask import Blueprint, Response, current_app, jsonify, request

from ..core.security import ApiError, require_key
from ..repositories.analytics_repo import to_records
from ..services import reports, rankings as rk, scenario as scn, scouting as sc

bp = Blueprint("api", __name__, url_prefix="/api/v1")
STARTED = time.time()


def repo(): return current_app.config["REPO"]
def conn(): return current_app.config["DB"]
def need_data():
    if not repo().available():
        raise ApiError(503, "analytics_unavailable", "analytical outputs not found; run scripts/run_pipeline.py")


def int_arg(name, default, lo=1, hi=10 ** 9):
    raw = request.args.get(name)
    if raw is None: return default
    try: v = int(raw)
    except ValueError: raise ApiError(400, "bad_parameter", f"{name} must be an integer")
    if not lo <= v <= hi: raise ApiError(400, "bad_parameter", f"{name} must be between {lo} and {hi}")
    return v


def body():
    j = request.get_json(silent=True)
    if not isinstance(j, dict): raise ApiError(400, "bad_body", "JSON object body required")
    return j


# ---------- health ----------
@bp.get("/health")
def health():
    return jsonify(status="ok", uptime_s=round(time.time() - STARTED, 1))


@bp.get("/health/ready")
def ready():
    checks = {}
    try: conn().execute("SELECT 1").fetchone(); checks["database"] = "ok"
    except Exception: checks["database"] = "error"
    checks["analytics_outputs"] = "ok" if repo().available() else "missing"
    ok = all(v == "ok" for v in checks.values())
    return jsonify(status="ready" if ok else "degraded", checks=checks), (200 if ok else 503)


# ---------- overview ----------
@bp.get("/overview")
def overview():
    need_data()
    r = repo()
    man, params, mm = r.json("dataset_manifest.json"), r.json("reliability_parameters.json"), r.json("model_metrics.json")
    bat, bowl = r.rankings("bat"), r.rankings("bowl")
    top = lambda d: to_records(d[d.eligible].sort_values("rank").head(1)[["player_id", "player", "PRI", "PRI_lo", "PRI_hi", "tier"]])[0]
    tasks = mm["tasks"]
    recent = [dict(x) for x in conn().execute("SELECT ts, action, detail FROM audit_log ORDER BY id DESC LIMIT 5")]
    return jsonify(
        players_analysed=int(len(set(bat.player_id) | set(bowl.player_id))), matches_analysed=man["in_scope"]["matches"], deliveries_analysed=man["in_scope"]["deliveries"],
        pressure_deliveries=man["in_scope"]["pressure_deliveries"], eligible_batters=params["bat"]["n_eligible"], eligible_bowlers=params["bowl"]["n_eligible"],
        min_pressure_deliveries={"bat": params["bat"]["min_pressure_deliveries"], "bowl": params["bowl"]["min_pressure_deliveries"]},
        top_batter=top(bat), top_bowler=top(bowl),
        model_status={"model_version": mm["model_version"], "pipeline_version": man["pipeline_version"], "tasks": {t: {"selected": v["selected_model"], "n_test": v["n_test"]} for t, v in tasks.items()}},
        dataset_coverage={"date_range": man["date_range"], "run_utc": man["run_utc"], "tiers": r.json("cleaning_log.json")["in_scope_by_tier"], "raw_row_counts": {k: v["rows"] for k, v in man["raw_files"].items()}},
        recent_activity=recent)


# ---------- players & rankings ----------
def _rank_endpoint(role):
    need_data()
    a = request.args
    return jsonify(rk.query(repo(), role, status=a.get("status", "ranked"), tier=a.get("tier"), role_inferred=a.get("role_inferred"), q=a.get("q"),
                            sort_by=a.get("sort_by", "rank"), order=a.get("order", "asc"), page=int_arg("page", 1), page_size=int_arg("page_size", 25, 1, 10 ** 6),
                            max_page=current_app.config["SETTINGS"].max_page_size))


@bp.get("/batters/rankings")
def batter_rankings(): return _rank_endpoint("bat")


@bp.get("/bowlers/rankings")
def bowler_rankings(): return _rank_endpoint("bowl")


@bp.get("/players")
def players():
    need_data()
    q, out = (request.args.get("q") or "").strip(), []
    for role in ("bat", "bowl"):
        d = repo().rankings(role)
        if q: d = d[d.player.str.contains(q, case=False, na=False, regex=False)]
        part = d[["player_id", "player", "role_inferred", "status", "tier", "rank", "pressure_deliveries"]].assign(role=role)
        out.append(part)
    import pandas as pd
    df = pd.concat(out).sort_values(["player", "role"])
    page, size = int_arg("page", 1), min(int_arg("page_size", 50, 1, 10 ** 6), current_app.config["SETTINGS"].max_page_size)
    return jsonify(total=len(df), page=page, page_size=size, items=to_records(df.iloc[(page - 1) * size: page * size]))


@bp.get("/players/compare")
def compare():
    need_data()
    try: ids = [int(x) for x in (request.args.get("ids") or "").split(",") if x]
    except ValueError: raise ApiError(400, "bad_ids", "ids must be comma-separated integers")
    return jsonify(rk.compare(repo(), request.args.get("role", "bat"), ids))


@bp.get("/players/<int:player_id>")
def player(player_id):
    need_data()
    roles = [r for r in ("bat", "bowl") if request.args.get("role", r) == r]
    found = {}
    for r in roles:
        try: found[r] = rk.player_detail(repo(), r, player_id)
        except ApiError as e:
            if e.status != 404: raise
    if not found: raise ApiError(404, "player_not_found", f"player {player_id} not found")
    for rec in found.values(): rec["risk_flags"] = rk.risk_flags(rec)
    return jsonify(player_id=player_id, profiles=found)


@bp.get("/players/<int:player_id>/explain")
def player_explain(player_id):
    need_data()
    role = rk.role_of(request.args.get("role", "bat"))
    rec = rk.player_detail(repo(), role, player_id)
    if rec["status"] != "Ranked":
        raise ApiError(409, "not_ranked", "decomposition is only provided for ranked players")
    return jsonify(player_id=player_id, role=role, player=rec["player"], **scn.explain_player(rec, repo().json("reliability_parameters.json"), role))


# ---------- scenario simulator ----------
@bp.get("/scenario/presets")
def scenario_presets(): return jsonify(presets=scn.PRESETS)


@bp.get("/scenario/simulate")
def scenario_simulate():
    need_data()
    if not repo().dir.joinpath("scenario_chase_states.csv").exists():
        raise ApiError(503, "scenario_unavailable", "scenario evidence tables missing; rerun scripts/run_pipeline.py")
    return jsonify(scn.simulate(request.args, repo(), current_app.config["MODELS"]))


# ---------- pressure & model insight ----------
@bp.get("/pressure/overview")
def pressure_overview():
    need_data()
    r = repo()
    return jsonify(definition="Pressure = top 20% of pre-delivery Leverage Index within each innings (High + Critical)", thresholds=r.json("pressure_thresholds.json"),
                   wicket_cost=r.json("wicket_cost.json"), categories=to_records(r.csv("pressure_validity.csv")),
                   caveat="first-innings pressure concentrates late / in collapses; leverage is model-estimated")


@bp.get("/pressure/distribution")
def pressure_distribution():
    need_data()
    r = repo()
    phase = r.csv("pressure_phase_mix.csv")
    return jsonify(by_over=to_records(r.csv("pressure_by_over.csv")), phase_mix_pct=to_records(phase))


@bp.get("/models/metrics")
def model_metrics():
    need_data()
    mm = repo().json("model_metrics.json")
    tasks = {}
    for t, v in mm["tasks"].items():
        tasks[t] = {k: v[k] for k in ("kind", "n_train", "n_valid", "n_test", "selected_model", "selected_params", "valid_selection", "test_metrics", "cv_oof_metrics", "features") if k in v}
        for k in ("test_calibration", "class_imbalance_comparison", "selection_override"):
            if k in v: tasks[t][k] = v[k]
    return jsonify(model_version=mm["model_version"], split=mm["split"], tasks=tasks,
                   caveat="ball-level models are modest context baselines (R2 ~0.03, AUC ~0.6); win-probability trained on ~800 correlated matches")


@bp.get("/models/feature-importance")
def feature_importance():
    need_data()
    mm = repo().json("model_metrics.json")["tasks"]
    task = request.args.get("task", "wp")
    if task not in mm: raise ApiError(400, "bad_task", f"task must be one of {sorted(mm)}")
    return jsonify(task=task, method="permutation importance on a 15k-delivery sample (predictive association, not causal)", items=mm[task]["global_importance"])


@bp.get("/methodology/validation")
def validation():
    need_data()
    r = repo()
    return jsonify(reliability_parameters=r.json("reliability_parameters.json"), split_half={"batters": to_records(r.csv("split_half_batters.csv")), "bowlers": to_records(r.csv("split_half_bowlers.csv"))},
                   temporal={"batters": r.json("temporal_validity_batters.json"), "bowlers": r.json("temporal_validity_bowlers.json")}, data_validation=r.json("validation_report.json"),
                   cleaning=r.json("cleaning_log.json"))


# ---------- scouting ----------
@bp.get("/scouting/recommendations")
def recommendations():
    need_data()
    role = request.args.get("role", "bat")
    like = int_arg("like", None) if request.args.get("like") else None
    ex = {r["player_id"] for r in conn().execute("SELECT player_id FROM shortlist WHERE role=?", (role,))}
    return jsonify(rk.recommendations(repo(), role, exclude=ex, like=like, role_inferred=request.args.get("role_inferred"), limit=int_arg("limit", 8, 1, 30)))


@bp.get("/scouting/shortlist")
def shortlist(): need_data(); return jsonify(sc.listing(conn(), repo()))


@bp.post("/scouting/shortlist")
@require_key
def shortlist_add():
    need_data(); b = body()
    out = sc.add(conn(), repo(), b.get("player_id"), b.get("role"), str(b.get("note", "")))
    return jsonify(out), 201


@bp.patch("/scouting/shortlist/<int:player_id>")
@require_key
def shortlist_note(player_id):
    b = body()
    return jsonify(sc.update_note(conn(), player_id, request.args.get("role", ""), str(b.get("note", ""))))


@bp.delete("/scouting/shortlist/<int:player_id>")
@require_key
def shortlist_remove(player_id):
    sc.remove(conn(), player_id, request.args.get("role", ""))
    return "", 204


# ---------- exports ----------
@bp.get("/exports/rankings/<role>.csv")
def export_rankings(role):
    need_data()
    return Response(reports.ranking_csv(repo(), role, request.args.get("status", "ranked")), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=playbook27_{role}_rankings.csv"})


@bp.get("/exports/shortlist.csv")
def export_shortlist():
    need_data()
    import pandas as pd
    items = sc.listing(conn(), repo())["items"]
    cols = ["role", "rank", "player", "role_inferred", "tier", "PRI", "PRI_lo", "PRI_hi", "p_top10", "sample_confidence", "note"]
    df = pd.DataFrame(items, columns=cols) if items else pd.DataFrame(columns=cols)
    return Response(df.to_csv(index=False), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=playbook27_shortlist.csv"})


@bp.get("/scouting/report/<role>/<int:player_id>.pdf")
def scouting_report(role, player_id):
    need_data()
    rec = rk.player_detail(repo(), role, player_id)
    row = conn().execute("SELECT note FROM shortlist WHERE player_id=? AND role=?", (player_id, role)).fetchone()
    return Response(reports.scouting_card_pdf(rec, row["note"] if row else ""), mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=playbook27_{role}_{player_id}.pdf"})


# ---------- admin ----------
@bp.get("/admin/status")
@require_key
def admin_status():
    need_data()
    r = repo()
    return jsonify(manifest=r.json("dataset_manifest.json"), validation_summary=r.json("validation_report.json")["summary"], model_version=r.json("model_metrics.json")["model_version"],
                   migrations=[x["name"] for x in conn().execute("SELECT name FROM schema_migrations")], audit_entries=conn().execute("SELECT COUNT(*) c FROM audit_log").fetchone()["c"])
