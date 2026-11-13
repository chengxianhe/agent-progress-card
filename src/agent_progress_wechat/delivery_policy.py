"""One offline policy for every notification; requests are state, not a replay queue."""
import time


def value(db, key, default=''):
    row = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def put(db, key, data):
    db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(data)))


def paused(db):
    return (not value(db, 'context') or value(db, 'send_requires_context') == '1'
            or float(value(db, 'send_paused_until', '0')) > time.time())


def discard_pending(db):
    # Keep identity tombstones for dedup; never label discarded messages as delivered.
    db.execute("UPDATE outbox SET superseded=1,text='' WHERE delivered=0")


def pause(db):
    put(db, 'send_requires_context', '1')
    put(db, 'recovery_needed', '1')
    discard_pending(db)


def resume(db):
    if paused(db):
        discard_pending(db)
        moment = time.time()
        put(db, 'push_since', moment)
        put(db, 'recovery_summary', moment)
    put(db, 'send_requires_context', '0')
    put(db, 'send_paused_until', '0')


def migrate(db):
    if value(db, 'delivery_policy_version') == 'all-messages-v1':
        if paused(db):
            discard_pending(db)
        return
    if db.execute('SELECT 1 FROM outbox WHERE delivered=0 AND superseded=0 LIMIT 1').fetchone():
        pause(db)
    put(db, 'delivery_policy_version', 'all-messages-v1')


def recovery_summary(store, state, feed):
    stamp = store.get('recovery_summary')
    if not stamp:
        return False
    from .relay_mirror import overview
    count = 0
    if store.db.execute("SELECT 1 FROM sqlite_master WHERE name='remote_approvals'").fetchone():
        count = store.db.execute("SELECT count(*) FROM remote_approvals WHERE state='pending' AND expires>=?",
                                 (time.time(),)).fetchone()[0]
    text = '微信连接已恢复；断线期间的所有历史通知不补发。\n' + overview(state, feed)
    if count:
        text += f'\n当前有 {count} 项有效系统请求，发送“审批”按需查看。'
    uncertain = store.db.execute("SELECT count(*) FROM inbox WHERE status='uncertain'").fetchone()[0]
    if uncertain:
        text += f'\n有 {uncertain} 条历史投递回执不确定，不会自动重发。'
    if feed.get('choice'):
        text += '\n当前有待选问题，发送“选项”查看。'
    store.enqueue('recovery:' + stamp, text, 'recovery')
    put(store.db, 'recovery_summary', '')
    put(store.db, 'recovery_needed', '')
    return True
