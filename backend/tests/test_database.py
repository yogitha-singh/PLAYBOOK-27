import sqlite3, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import db


class Migrations(unittest.TestCase):
    def setUp(self): self.path = Path(tempfile.mkdtemp()) / "sub" / "t.sqlite3"

    def test_fresh_migration_is_idempotent_and_persistent(self):
        c = db.connect(self.path)
        self.assertEqual(db.migrate(c), ["001_init.sql"]); self.assertEqual(db.migrate(c), [])
        names = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"shortlist", "audit_log", "schema_migrations"} <= names)
        c.execute("INSERT INTO shortlist(player_id, role) VALUES (1,'bat')"); c.close()
        c2 = db.connect(self.path); self.assertEqual(db.migrate(c2), [])
        self.assertEqual(c2.execute("SELECT COUNT(*) c FROM shortlist").fetchone()["c"], 1)

    def test_constraints(self):
        c = db.connect(self.path); db.migrate(c)
        with self.assertRaises(sqlite3.IntegrityError): c.execute("INSERT INTO shortlist(player_id, role) VALUES (1,'umpire')")
        c.execute("INSERT INTO shortlist(player_id, role) VALUES (1,'bat')"); c.execute("INSERT INTO shortlist(player_id, role) VALUES (1,'bowl')")   # same player, other role OK
        with self.assertRaises(sqlite3.IntegrityError): c.execute("INSERT INTO shortlist(player_id, role) VALUES (1,'bat')")

    def test_transaction_rolls_back(self):
        c = db.connect(self.path); db.migrate(c)
        with self.assertRaises(RuntimeError):
            with db.transaction(c):
                c.execute("INSERT INTO shortlist(player_id, role) VALUES (9,'bat')"); raise RuntimeError("boom")
        self.assertEqual(c.execute("SELECT COUNT(*) c FROM shortlist").fetchone()["c"], 0)


if __name__ == "__main__":
    unittest.main()
