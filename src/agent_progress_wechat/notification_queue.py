"""Bound pending ordinary updates without claiming superseded notices were delivered."""
from .delivery_policy import paused

ORDINARY = ("progress", "final", "receipt", "legacy_update")


def prepare_queue(db):
    columns = {row[1] for row in db.execute("PRAGMA table_info(outbox)")}
    if "category" not in columns:
        db.execute("ALTER TABLE outbox ADD COLUMN category TEXT NOT NULL DEFAULT 'protected'")
    if "superseded" not in columns:
        db.execute("ALTER TABLE outbox ADD COLUMN superseded INTEGER NOT NULL DEFAULT 0")
    if 'revision' not in columns:
        db.execute('ALTER TABLE outbox ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
    # Repeat classification safely if an earlier process exited between DDL and DML.
    for pattern, category in (("note:%", "legacy_update"), ("card:%", "progress"),
                              ("delivered:%", "receipt")):
        db.execute("UPDATE outbox SET category=? WHERE category='protected' AND id LIKE ?",
                   (category, pattern))
    for category in ORDINARY:
        db.execute("""UPDATE outbox SET superseded=1,text='' WHERE delivered=0 AND superseded=0
                      AND category=? AND rowid != COALESCE((SELECT max(rowid) FROM outbox
                      WHERE delivered=0 AND superseded=0 AND category=?), -1)""", (category, category))


def enqueue_notice(db, identity, text, category=None):
    # Check identity first: replaying an older feed must not supersede the newest result.
    if db.execute("SELECT 1 FROM outbox WHERE id=?", (identity,)).fetchone():
        return
    if paused(db):
        db.execute("INSERT INTO outbox(id,text,category,superseded) VALUES (?,'',?,1)",
                   (identity, category or 'protected'))
        return
    if category is None:
        category = ("legacy_update" if identity.startswith("note:") else
                    "progress" if identity.startswith("card:") else
                    "receipt" if identity.startswith("delivered:") else "protected")
    if category in ORDINARY:
        categories = (category, "legacy_update") if category in ("progress", "final") else (category,)
        for value in categories:
            db.execute("UPDATE outbox SET superseded=1,text='' WHERE delivered=0 "
                       "AND superseded=0 AND category=?", (value,))
    db.execute("INSERT INTO outbox(id,text,category) VALUES (?,?,?)", (identity, text, category))
