def add(conn, repo, player_id, role, note=""):
    conn.execute("INSERT OR IGNORE INTO shortlist(player_id, role, note) VALUES (?,?,?)", (player_id, role, note))
    return {"player_id": player_id, "role": role, "note": note}

def remove(conn, player_id, role):
    return conn.execute("DELETE FROM shortlist WHERE player_id=? AND role=?", (player_id, role)).rowcount > 0

def update_note(conn, player_id, role, note):
    conn.execute("UPDATE shortlist SET note=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE player_id=? AND role=?", (note, player_id, role))
    return {"player_id": player_id, "role": role, "note": note}

def list_shortlist(conn, repo):
    rows = [dict(r) for r in conn.execute("SELECT player_id, role, note, added_at FROM shortlist ORDER BY added_at DESC")]
    return {"count": len(rows), "items": rows, "balance": {"batters": {}, "bowlers": {}, "gaps": [], "note": "Roles inferred"}}
