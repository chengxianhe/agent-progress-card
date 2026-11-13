"""Complete ordinary forms share the same bounded, revisioned notification delivery."""
from .relay_mirror import choice_text


def publish(store, choice, refresh=False):
    from .delivery_policy import paused
    if paused(store.db):
        return
    text = choice_text(choice)
    key = 'choice:' + choice['id']
    chunks = [text[i:i + 2200] for i in range(0, len(text), 2200)]
    notices = [(key, text)] if len(chunks) == 1 else [
        (key + ':part:' + str(i), f'看板问题详情（{i}/{len(chunks)}）\n' + chunk)
        for i, chunk in enumerate(chunks, 1)
    ] + [(key, '当前问题的完整详情已分段发送；全部收到后按上方 C 编号回复，或发送“选项”重新获取。')]
    if refresh:
        store.db.execute("UPDATE outbox SET superseded=1,text='' WHERE delivered=0 AND (id=? OR id LIKE ?)",
                         (key, key + ':part:%'))
    for identity, content in notices:
        old = store.db.execute('SELECT revision FROM outbox WHERE id=?', (identity,)).fetchone()
        if refresh and old:
            store.db.execute("UPDATE outbox SET text=?,delivered=0,superseded=0,due=0,revision=revision+1 WHERE id=?",
                             (content, identity))
        else:
            store.enqueue(identity, content)


def incomplete(store, choice):
    return bool(store.db.execute("SELECT 1 FROM outbox WHERE id LIKE ? AND delivered=0 LIMIT 1",
                                 ('choice:' + choice['id'] + ':part:%',)).fetchone())
