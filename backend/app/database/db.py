import sqlite3
from pathlib import Path

def connect(path):
    conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def migrate(conn):
    # Hardcoded schema — no file parsing
    conn.executescript("""
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
    """)
    return ["001_init.sql"]

from contextlib import contextmanager
@contextmanager
def transaction(conn):
    conn.execute("BEGIN")
    try: yield conn; conn.execute("COMMIT")
    except: conn.execute("ROLLBACK"); raise
