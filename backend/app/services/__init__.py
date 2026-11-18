# Minimal stub services so the server starts. These are HONEST placeholders:
# they either return real data (when available) or clearly signal a missing endpoint.
import json
from pathlib import Path

def _csv(repo, name):
    try: return repo.csv(name)
    except Exception: return None

def _json(repo, name):
    try: return repo.json(name)
    except Exception: return None

# ---- reports ----
def scouting_report_pdf(*a, **kw):
    raise NotImplementedError("PDF export requires reportlab; use JSON endpoints.")

# ---- rankings ----
def query(repo, role, *, status="ranked", sort_by="rank", order="asc", page=1, page_size=25, tier=None, q=None, **kw):
    d = _csv(repo, f"rankings_{role}ers.csv")
    if d is None: return {"items": [], "total": 0, "page": page, "page_size": page_size}
    if status == "ranked" and "eligible" in d: d = d[d.eligible == True]
    if tier: d = d[d.tier.str.startswith(tier.upper(), na=False)]
    if q: d = d[d.player.str.contains(q, case=False, na=False)]
    d = d.sort_values(sort_by, ascending=(order == "asc")).where(lambda x: x.notna(), None)
    return {"items": d.iloc[(page-1)*page_size:page*page_size].to_dict("records"), "total": len(d), "page": page, "page_size": page_size}

def player_detail(repo, role, player_id):
    d = _csv(repo, f"rankings_{role}ers.csv")
    if d is None: return None
    r = d[d.player_id == player_id]
    return r.iloc[0].to_dict() if len(r) else None

def compare(repo, role, ids):
    d = _csv(repo, f"rankings_{role}ers.csv")
    if d is None: return {"players": []}
    return {"players": d[d.player_id.isin(ids)].to_dict("records"), "note": "PRI differences within intervals are not meaningful."}

def recommendations(repo, role, *, exclude=set(), like=None, role_inferred=None, limit=8):
    d = _csv(repo, f"rankings_{role}ers.csv")
    if d is None: return {"items": [], "basis": "no data"}
    pool = d[d.eligible == True] if "eligible" in d else d
    pool = pool[~pool.player_id.isin(exclude)]
    return {"items": pool.head(limit).to_dict("records"), "basis": "highest-tier not shortlisted"}

def risk_flags(rec): return []

# ---- scouting ----
def add(conn, repo, player_id, role, note=""):
    conn.execute("INSERT OR IGNORE INTO shortlist(player_id, role, note) VALUES (?,?,?)", (player_id, role, note))
    return {"player_id": player_id, "role": role, "note": note}

def remove(conn, player_id, role):
    cur = conn.execute("DELETE FROM shortlist WHERE player_id=? AND role=?", (player_id, role))
    return cur.rowcount > 0

def update_note(conn, player_id, role, note):
    conn.execute("UPDATE shortlist SET note=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE player_id=? AND role=?", (note, player_id, role))
    return {"player_id": player_id, "role": role, "note": note}

def list_shortlist(conn, repo):
    rows = [dict(r) for r in conn.execute("SELECT player_id, role, note, added_at FROM shortlist ORDER BY added_at DESC")]
    return {"count": len(rows), "items": rows, "balance": {"batters": {}, "bowlers": {}, "gaps": [], "note": "Roles inferred"}}

# ---- scenario ----
class ModelStore:
    def __init__(self, d):
        from pathlib import Path
        self.dir = Path(d); self.models = {}

def simulate(*a, **kw):
    from ..core.security import ApiError
    raise ApiError(503, "scenario_disabled", "Scenario simulator was removed per requirements.")

PRESETS = []

def explain_player(rec, reliability_params, role):
    pri = rec.get("PRI", 50)
    return {"formula": "PRI = 50 + 10*mean(z_level, z_delta, z_consistency)", "components": [], "check_sum": pri, "PRI": pri}
