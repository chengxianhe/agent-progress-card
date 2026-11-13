"""Rebuild one current request on explicit query, never replay offline notification rows."""
import json
import re
import time


def publish(store, row, refresh=False):
    from .delivery_policy import paused
    if paused(store.db):
        return  # A queued query must not bypass a concurrently paused sender.
    code, preview = row['code'], row['preview']
    choices, form = json.loads(row['choices']), json.loads(row['form'])
    chunks = [preview[i:i + 2200] for i in range(0, len(preview), 2200)]
    notices = []
    if len(chunks) > 1:
        notices += [(f'approval:{code}:part:{i}', f'授权详情 {code}（{i}/{len(chunks)}）\n' + chunk)
                    for i, chunk in enumerate(chunks, 1)]
    options = '\n'.join(f"{i}. {item['label']}" for i, item in enumerate(choices, 1))
    details = f'完整内容见上方 {len(chunks)} 条详情；全部送达后才能选择。' if len(chunks) > 1 else preview
    footer = f'回复示例：1 {code}（选第1项）；其他项替换开头数字。' if choices else ''
    if form and form.get('type'):
        footer += f'\n文字或多题填写：填写 {code} {{"字段或问题ID":"答案"}}'
    remaining = max(0, int(row['expires'] - time.time()))
    text = (f'系统请求 {code} · 剩余约{remaining}秒\n{details}\n\n{options}\n{footer}') if preview else (
        f"需原客户端处理 {code}\n类型：{row['method']}\n原因：{form.get('native_reason', '当前结构未适配')}\n没有提交任何决定。")
    notices.append(('approval:' + code, text))
    if refresh:
        store.db.execute("UPDATE outbox SET superseded=1,text='' WHERE id=? OR id LIKE ?",
                         ('approval:' + code, 'approval:' + code + ':part:%'))
    for identity, text in notices:
        if refresh:
            old = store.db.execute('SELECT revision FROM outbox WHERE id=?', (identity,)).fetchone()
            if old:
                store.db.execute("UPDATE outbox SET text=?,delivered=0,superseded=0,due=0,revision=revision+1 WHERE id=?",
                                 (text, identity))
                continue
        store.enqueue(identity, text)


def query(state, message):
    text = message['text'].strip()
    if text not in ('审批', '/approvals') and not re.fullmatch(r'(?:审批|/approvals)\s+(?:A[0-9a-f]{10}|[1-9][0-9]{0,2})', text, re.I):
        return False
    store = state.store
    suffix = text.split(maxsplit=1)[1].upper() if ' ' in text else ''
    with store.lock, store.db:
        from .approval_codes import renew_expired
        renew_expired(store)
        rows = store.db.execute("SELECT * FROM remote_approvals WHERE server_live=1 AND state IN ('pending','native') ORDER BY created").fetchall()
        if suffix.startswith('A'):
            row = next((r for r in rows if r['code'] == suffix), None)
            if row:
                publish(store, row, refresh=True)
                store.mark(message['id'], 'local')
            else:
                store.mark(message['id'], 'local', reply='该编号不再有效；没有提交决定。发送“审批”查询当前状态。')
        elif len(rows) == 1:
            publish(store, rows[0], refresh=True)
            store.mark(message['id'], 'local')
        else:
            page = int(suffix) if suffix else 1
            selected = rows[(page - 1) * 5:page * 5]
            reply = '当前没有有效系统请求。' if not rows else f'当前 {len(rows)} 项请求，第{page}页：\n'
            reply += '\n'.join(r['code'] + ' · ' + r['method'] + ('（需原客户端）' if r['state'] == 'native' else '') for r in selected)
            if rows:
                reply += '\n发送“审批 A编号”查看一项完整详情；“审批 2”查看第2页。'
            store.mark(message['id'], 'local', reply=reply)
    return True
