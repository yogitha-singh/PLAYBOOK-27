import sqlite3
conn = sqlite3.connect('data/app.sqlite3')
conn.executescript('''
CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')));
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
INSERT OR IGNORE INTO schema_migrations(name) VALUES ('001_init.sql');
''')
conn.commit()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print('Tables:', tables)
conn.close()
