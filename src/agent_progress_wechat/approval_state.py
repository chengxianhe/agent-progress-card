"""Durable one-time approvals; disconnected or ambiguous submissions never replay."""
import json
import time
import uuid

from .approval_prompt import METHOD, display, parse_reply, request_key, ordered_choices, numbered_reply, rejection_reason


class ApprovalState:
    def __init__(self, store, thread_id):
        self.store, self.thread_id = store, thread_id
        with store.lock, store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS remote_approvals (
                code TEXT PRIMARY KEY, connection TEXT, request_key TEXT, state TEXT,
                preview TEXT, created REAL, expires REAL, decision TEXT DEFAULT '', choices TEXT DEFAULT '[]',
                UNIQUE(connection, request_key))''')
            columns = {r[1] for r in store.db.execute('PRAGMA table_info(remote_approvals)')}
            if 'choices' not in columns:
                store.db.execute("ALTER TABLE remote_approvals ADD COLUMN choices TEXT DEFAULT '[]'")
        self.invalidate()

    def invalidate(self, connection=None):
        with self.store.lock, self.store.db:
            rows = self.store.db.execute("SELECT * FROM remote_approvals WHERE state IN ('pending','queued','sending')").fetchall()
            for row in rows:
                if connection is not None and row['connection'] != connection:
                    continue
                state = 'uncertain' if row['state'] == 'sending' else 'expired'
                self._finish(row, state, '连接已断开；旧编号失效，请查看新的审批通知或在电脑端处理。' if state == 'expired'
                             else '提交回执未确认，不能确定结果；不会重发，请在电脑端核对。')

    def _finish(self, row, state, note):
        self.store.db.execute('UPDATE remote_approvals SET state=? WHERE code=?', (state, row['code']))
        self.store.db.execute('UPDATE outbox SET delivered=1 WHERE id=?', ('approval:' + row['code'],))
        self.store.enqueue('approval-result:' + row['code'], '审批 ' + row['code'] + '：' + note)

    def event(self, event, connection):
        if not isinstance(event, dict) or not isinstance(event.get('params'), dict):
            return
        params = event['params']
        if params.get('threadId') != self.thread_id:
            return
        if event.get('method') == 'serverRequest/resolved':
            try:
                key = request_key(params.get('requestId'))
            except ValueError:
                return
            with self.store.lock, self.store.db:
                row = self.store.db.execute('SELECT * FROM remote_approvals WHERE connection=? AND request_key=?',
                                            (connection, key)).fetchone()
                if row and row['state'] in ('pending', 'queued', 'sending'):
                    # Resolved also covers desktop decisions/cancellation; never claim our decision won a race.
                    self._finish(row, 'resolved', 'Codex 已关闭此请求，编号失效。可能由手机或电脑处理；执行结果请查看任务进度。')
            return
        if event.get('method') != METHOD or 'id' not in event:
            return
        try:
            key = request_key(event['id'])
        except ValueError:
            return
        preview = display(params)
        with self.store.lock, self.store.db:
            if self.store.db.execute('SELECT 1 FROM remote_approvals WHERE connection=? AND request_key=?', (connection, key)).fetchone():
                return
            count = self.store.db.execute("SELECT count(*) FROM remote_approvals WHERE state IN ('pending','queued','sending')").fetchone()[0]
            if count >= 20:
                return
            now, code = time.time(), 'A' + uuid.uuid4().hex[:10].upper()
            choices = ordered_choices(params)
            self.store.db.execute('INSERT INTO remote_approvals(code,connection,request_key,state,preview,created,expires,choices) VALUES (?,?,?,?,?,?,?,?)',
                                  (code, connection, key, 'pending' if preview else 'native', preview or '', now, now + 600, json.dumps(choices, ensure_ascii=False)))
            options = '\n'.join(f"{i}. {item['label']}" for i, item in enumerate(choices, 1))
            notice = (f'待授权 {code} · 10 分钟有效\n{preview}\n\n{options}\n'
                      f'回复「选项号 {code}」；仅一项待选时可只回数字。') if preview else (
                      f'需电脑确认：{rejection_reason(params)}。\n本通知不能回复数字授权。')
            self.store.enqueue('approval:' + code, notice)

    def expire(self):
        with self.store.lock, self.store.db:
            rows = self.store.db.execute("SELECT * FROM remote_approvals WHERE state IN ('pending','queued','sending') AND expires<?", (time.time(),)).fetchall()
            for row in rows:
                self._finish(row, 'uncertain' if row['state'] == 'sending' else 'expired', '编号已过期；请在电脑端核对，旧回复不会重发。')

    def handle(self, message):
        self.expire()
        parsed = parse_reply(message['text'])
        numbered = numbered_reply(message['text'])
        with self.store.lock, self.store.db:
            if message['text'] in ('审批', '/approvals'):
                rows = self.store.db.execute("SELECT code FROM remote_approvals WHERE state='pending' ORDER BY created").fetchall()
                reply = '待审批编号：' + '、'.join(r['code'] for r in rows) if rows else '当前没有可在微信处理的审批；电脑弹窗可能需要原客户端确认。'
                for row in rows:
                    self.store.db.execute('UPDATE outbox SET delivered=0,due=0 WHERE id=?', ('approval:' + row['code'],))
            elif parsed is None and numbered is None:
                reply = '请按通知回复「选项号 A编号」或「批准 A编号」；不会把这条消息当作新任务。'
            else:
                if numbered:
                    index, code = numbered
                    if code is None:
                        candidates = self.store.db.execute("SELECT code FROM remote_approvals WHERE state='pending'").fetchall()
                        code = candidates[0]['code'] if len(candidates) == 1 else ''
                    decision = None
                else:
                    code, decision = parsed
                row = self.store.db.execute('SELECT * FROM remote_approvals WHERE code=?', (code,)).fetchone()
                sent = self.store.db.execute('SELECT delivered FROM outbox WHERE id=?', ('approval:' + code,)).fetchone()
                if (not row or row['state'] != 'pending' or message.get('created', 0) < row['created']
                        or (numbered and numbered[1] is None and (not sent or not sent[0]))):
                    reply = '这个审批编号不可用、已经处理或已过期；没有再次提交。请发送“审批”查看。'
                else:
                    choices = json.loads(row['choices'])
                    if numbered:
                        item = choices[index - 1] if 1 <= index <= len(choices) else {}
                        decision = item.get('decision')
                    elif decision == 'decline' and choices and not any(c['decision'] == 'decline' for c in choices):
                        # Do not silently turn a rejection into a whole-turn cancellation.
                        decision = None
                    if decision not in ('accept', 'decline', 'cancel'):
                        reply = '该选项需在电脑端处理或编号无效。请按通知中完整编号重新选择；没有提交决定。'
                    else:
                        self.store.db.execute("UPDATE remote_approvals SET state='queued',decision=? WHERE code=?", (decision, code))
                        reply = '已收到你对 ' + code + ' 的单次决定，等待提交到 Codex。'

            self.store.mark(message['id'], 'local', reply=reply)

    def has_recent_prompt(self):
        self.expire()
        with self.store.lock:
            return bool(self.store.db.execute("SELECT 1 FROM remote_approvals WHERE state!='native' AND created>=? LIMIT 1", (time.time() - 600,)).fetchone())

    def claim(self, connection):
        with self.store.lock, self.store.db:
            row = self.store.db.execute("SELECT * FROM remote_approvals WHERE state='queued' AND connection=? AND expires>=? ORDER BY created LIMIT 1",
                                       (connection, time.time())).fetchone()
            if not row:
                return None
            self.store.db.execute("UPDATE remote_approvals SET state='sending' WHERE code=?", (row['code'],))
            return json.loads(row['request_key']), row['decision']
