CREATE TABLE IF NOT EXISTS shortlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('bat','bowl')),
  note TEXT NOT NULL DEFAULT '',
  added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE (player_id, role)
);
CREATE INDEX IF NOT EXISTS idx_shortlist_role ON shortlist(role);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  action TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT ''
);
