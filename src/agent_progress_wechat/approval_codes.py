"""Renew only phone presentation codes for known-live, never-submitted requests."""
import time
import uuid


def prepare(db):
    columns = {r[1] for r in db.execute('PRAGMA table_info(remote_approvals)')}
    if 'server_live' not in columns:
        db.execute('ALTER TABLE remote_approvals ADD COLUMN server_live INTEGER NOT NULL DEFAULT 0')
    db.execute('CREATE TABLE IF NOT EXISTS retired_approval_codes(code TEXT PRIMARY KEY, retired_at REAL)')


def renew_expired(store):
    rows = store.db.execute("SELECT * FROM remote_approvals WHERE state='expired' AND server_live=1").fetchall()
    now = time.time()
    for row in rows:
        code = 'A' + uuid.uuid4().hex[:10].upper()
        store.db.execute('INSERT OR IGNORE INTO retired_approval_codes VALUES (?,?)', (row['code'], now))
        store.db.execute("UPDATE outbox SET superseded=1,text='' WHERE delivered=0 AND (id=? OR id LIKE ?)",
                         ('approval:' + row['code'], 'approval:' + row['code'] + ':part:%'))
        store.db.execute("UPDATE remote_approvals SET code=?,state='pending',created=?,expires=?,decision='',response='' WHERE code=? AND server_live=1",
                         (code, now, now + 600, row['code']))
