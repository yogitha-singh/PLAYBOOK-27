import pandas as pd
from ..core.security import ApiError

ROLE_FILE = {"bat": "rankings_batters.csv", "bowl": "rankings_bowlers.csv"}

def _csv(repo, role):
    try:
        df = repo.csv(ROLE_FILE[role])
        return df if not df.empty else None
    except Exception:
        return None

def overview(repo):
    bat = _csv(repo, "bat")
    bowl = _csv(repo, "bowl")
    if bat is None or bowl is None:
        raise ApiError(503, "data_missing", "rankings CSVs not found")
    manifest = {}
    try:
        manifest = repo.json("dataset_manifest.json")
    except Exception:
        pass
    top_bat = bat[bat["rank"] == 1].iloc[0].to_dict() if len(bat[bat["rank"] == 1]) else None
    top_bowl = bowl[bowl["rank"] == 1].iloc[0].to_dict() if len(bowl[bowl["rank"] == 1]) else None
    return {
        "matches_analysed": manifest.get("in_scope", {}).get("matches", 0),
        "deliveries_analysed": manifest.get("in_scope", {}).get("deliveries", 0),
        "pressure_deliveries": manifest.get("in_scope", {}).get("pressure_deliveries", 0),
        "eligible_batters": int(bat["eligible"].sum()) if "eligible" in bat else 0,
        "eligible_bowlers": int(bowl["eligible"].sum()) if "eligible" in bowl else 0,
        "players_analysed": int(len(set(bat["player_id"]) | set(bowl["player_id"]))),
        "top_batter": top_bat,
        "top_bowler": top_bowl,
        "dataset_coverage": {
            "tiers": manifest.get("in_scope", {}).get("in_scope_by_tier", {}),
            "date_range": manifest.get("date_range", []),
            "run_utc": manifest.get("run_utc", ""),
            "raw_row_counts": {k: v.get("rows", 0) for k, v in manifest.get("raw_files", {}).items()},
        },
        "model_status": {"model_version": "1.0.0", "pipeline_version": "1.0.0"},
        "recent_activity": [],
        "min_pressure_deliveries": {"bat": 128, "bowl": 126},
    }

def query(repo, role, *, status="ranked", sort_by="rank", order="asc", page=1, page_size=25, tier=None, q=None, **kw):
    d = _csv(repo, role)
    if d is None:
        raise ApiError(503, "data_missing", ROLE_FILE[role] + " not found")
    if status == "ranked" and "eligible" in d:
        d = d[d["eligible"] == True]
    if tier:
        d = d[d["tier"].astype(str).str.startswith(tier.upper())]
    if q:
        d = d[d["player"].str.contains(q, case=False, na=False)]
    if sort_by in d.columns:
        d = d.sort_values(sort_by, ascending=(order == "asc"))
    total = len(d)
    items = d.iloc[(page-1)*page_size:page*page_size].to_dict("records")
    return {"items": items, "total": total, "page": page, "page_size": page_size}

def player_detail(repo, role, player_id):
    d = _csv(repo, role)
    if d is None:
        raise ApiError(503, "data_missing", ROLE_FILE[role] + " not found")
    r = d[d["player_id"] == player_id]
    if len(r) == 0:
        raise ApiError(404, "player_not_found", str(player_id))
    return r.iloc[0].to_dict()

def compare(repo, role, ids):
    d = _csv(repo, role)
    if d is None:
        return {"players": [], "note": ""}
    return {"players": d[d["player_id"].isin(ids)].to_dict("records"),
            "note": "PRI differences within shown intervals are not meaningful."}

def recommendations(repo, role, *, exclude=set(), like=None, role_inferred=None, limit=8):
    d = _csv(repo, role)
    if d is None:
        return {"items": [], "basis": "no data"}
    pool = d[d["eligible"] == True] if "eligible" in d else d
    pool = pool[~pool["player_id"].isin(exclude)]
    return {"items": pool.head(limit).to_dict("records"), "basis": "highest-tier not shortlisted"}

def risk_flags(rec):
    return []
