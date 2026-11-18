from app.database import db
c = db.connect('data/app.sqlite3')
res = db.migrate(c)
print('Migrated:', res)
tables = [r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=?', ('table',))]
print('Tables:', tables)
