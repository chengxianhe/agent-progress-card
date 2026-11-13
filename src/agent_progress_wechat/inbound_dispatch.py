"""Reserve local control handling independently of a blocked ordinary session send."""
from .approval_prompt import is_approval_text


def local_control(text):
    from .remote_health import COMMANDS
    if text.lower().startswith('填写 c'):
        return False
    return (text in COMMANDS or text in ('进度', '/status', '结果', '/result', '帮助', '/help', '选项', '/choice')
            or is_approval_text(text))


def take(store, fast):
    with store.lock, store.db:
        rows = store.db.execute("SELECT * FROM inbox WHERE status='queued' ORDER BY rowid").fetchall()
        eligible = [r for r in rows if local_control(r['text']) == fast]
        from .control_messages import is_control
        row = next((r for r in eligible if is_control(r['text'])), eligible[0] if eligible else None)
        if row is not None:
            store.db.execute("UPDATE inbox SET status='dispatching' WHERE id=? AND status='queued'", (row['id'],))
        return dict(row) if row else None


def release(store, message):
    if message:
        with store.lock, store.db:
            store.db.execute("UPDATE inbox SET status='queued' WHERE id=? AND status='dispatching'", (message['id'],))
