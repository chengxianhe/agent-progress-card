"""Durable one-time approvals; disconnected or ambiguous submissions never replay."""
import json
import time
import uuid
import hashlib

from .approval_prompt import METHOD, parse_reply, request_key, numbered_reply, label_reply
from .approval_requests import describe, request_event, typed_answer, visible
from .approval_forms import form_reply
from .approval_reply_status import blocked_reply
from .selection_text import literal_selection


class ApprovalState:
    def __init__(self, store, thread_id):
        self.store, self.thread_id = store, thread_id
        self.file_changes = {}
        with store.lock, store.db:
            store.db.execute('''CREATE TABLE IF NOT EXISTS remote_approvals (
                code TEXT PRIMARY KEY, connection TEXT, request_key TEXT, state TEXT,
                preview TEXT, created REAL, expires REAL, decision TEXT DEFAULT '', choices TEXT DEFAULT '[]',
                UNIQUE(connection, request_key))''')
            columns = {r[1] for r in store.db.execute('PRAGMA table_info(remote_approvals)')}
            if 'choices' not in columns:
                store.db.execute("ALTER TABLE remote_approvals ADD COLUMN choices TEXT DEFAULT '[]'")
            for name, default in [('method', METHOD), ('response', ''), ('form', '{}')]:
                if name not in columns:
                    store.db.execute(f"ALTER TABLE remote_approvals ADD COLUMN {name} TEXT DEFAULT '{default}'")
            from .approval_codes import prepare
            prepare(store.db)
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
            if connection is None:
                self.store.db.execute('UPDATE remote_approvals SET server_live=0')
            else:
                self.store.db.execute('UPDATE remote_approvals SET server_live=0 WHERE connection=?', (connection,))

    def _finish(self, row, state, note, keep_live=False):
        self.store.db.execute('UPDATE remote_approvals SET state=?,server_live=? WHERE code=?',
                              (state, int(keep_live and row['server_live']), row['code']))
        self.store.db.execute("UPDATE outbox SET superseded=1,text='' WHERE delivered=0 AND (id=? OR id LIKE ?)",
                              ('approval:' + row['code'], 'approval:' + row['code'] + ':part:%'))
        self.store.enqueue('approval-result:' + row['code'], '审批 ' + row['code'] + '：' + note)

    def event(self, event, connection):
        if not isinstance(event, dict) or not isinstance(event.get('params'), dict):
            return
        params = event['params']
        from .request_catalog import bound_params
        params = bound_params(event.get('method'), params)
        if params.get('threadId') != self.thread_id:
            return
        method = event.get('method', '')
        if method in ('item/started', 'item/completed'):
            item = params.get('item') or {}
            if isinstance(item, dict) and item.get('type') == 'fileChange' and isinstance(item.get('id'), str):
                key = (params.get('turnId'), item['id'])
                self.file_changes.pop(key, None)
                if method == 'item/started' and isinstance(item.get('changes'), list):
                    try:
                        visible(item['changes'])
                    except (ValueError, TypeError):
                        return
                    if len(self.file_changes) >= 20:
                        self.file_changes.pop(next(iter(self.file_changes)))
                    self.file_changes[key] = item['changes']
            return
        if event.get('method') == 'serverRequest/resolved':
            try:
                key = request_key(params.get('requestId'))
            except ValueError:
                return
            with self.store.lock, self.store.db:
                row = self.store.db.execute('SELECT * FROM remote_approvals WHERE connection=? AND request_key=?',
                                            (connection, key)).fetchone()
                if row and row['server_live'] and row['state'] in ('pending', 'queued', 'sending', 'native', 'expired'):
                    # Resolved also covers desktop decisions/cancellation; never claim our decision won a race.
                    self._finish(row, 'resolved', 'Codex 已关闭此请求，编号失效。可能由手机或电脑处理；执行结果请查看任务进度。')
            return
        if not request_event(event) or 'id' not in event:
            return
        try:
            key = request_key(event['id'])
        except ValueError:
            return
        problem = ''
        try:
            preview, choices, form = describe(method, params, self.file_changes.get((params.get('turnId'), params.get('itemId'))))
            preview = visible(preview)
            if len(choices) > 8:
                raise ValueError('可展示的编号选项超过 8 项')
        except (ValueError, TypeError, KeyError) as error:
            preview, choices, form = '', [], {}
            from agent_progress_card.sanitize import clean_text
            problem = clean_text(str(error), 300) if isinstance(error, ValueError) else '请求字段不完整或格式不受支持'
            form = {'native_reason': problem}

        with self.store.lock, self.store.db:
            if self.store.db.execute('SELECT 1 FROM remote_approvals WHERE connection=? AND request_key=?', (connection, key)).fetchone():
                return
            count = self.store.db.execute("SELECT count(*) FROM remote_approvals WHERE server_live=1 AND state IN ('pending','queued','sending','expired','native')").fetchone()[0]
            if count >= 20:
                digest = hashlib.sha256((connection + key).encode()).hexdigest()[:16]
                self.store.enqueue('notice:approval-limit:' + digest,
                                   '系统待处理请求已达 20 项；新请求未在微信接管，没有提交决定。请先处理现有请求。')
                return
            now, code = time.time(), 'A' + uuid.uuid4().hex[:10].upper()
            self.store.db.execute('INSERT INTO remote_approvals(code,connection,request_key,state,preview,created,expires,choices,method,form) VALUES (?,?,?,?,?,?,?,?,?,?)',
                                  (code, connection, key, 'pending' if preview else 'native', preview or '', now, now + 600, json.dumps(choices, ensure_ascii=False), method, json.dumps(form, ensure_ascii=False)))
            self.store.db.execute('UPDATE remote_approvals SET server_live=1 WHERE code=?', (code,))
            options = '\n'.join(f"{i}. {item['label']}" for i, item in enumerate(choices, 1))
            chunks = [preview[i:i + 2200] for i in range(0, len(preview), 2200)]
            details = preview
            if len(chunks) > 1:
                for i, chunk in enumerate(chunks, 1):
                    self.store.enqueue(f'approval:{code}:part:{i}', f'授权详情 {code}（{i}/{len(chunks)}）\n' + chunk)
                details = f'完整内容见上方 {len(chunks)} 条详情；全部送达后才能选择。'
            footer = f'回复示例：1 {code}（选第1项）；其他项替换开头数字。' if choices else ''
            if form:
                footer += f'\n文字或多题填写：填写 {code} {{"字段或问题ID":"答案"}}'
            notice = (f'系统请求 {code} · 10 分钟内有效\n{details}\n\n{options}\n{footer}') if preview else (
                f'检测到未适配请求 {code}\n类型：{method}\n原因：{problem}\n没有提交任何决定；此通知不能回复数字授权。')
            self.store.enqueue('approval:' + code, notice)

    def expire(self):
        with self.store.lock, self.store.db:
            rows = self.store.db.execute("SELECT * FROM remote_approvals WHERE state IN ('pending','queued','sending') AND expires<?", (time.time(),)).fetchall()
            for row in rows:
                self._finish(row, 'uncertain' if row['state'] == 'sending' else 'expired',
                             '手机编号已过期；发送“审批”查询仍在等待的请求，旧回复不会重发。',
                             keep_live=row['state'] != 'sending')

    def handle(self, message):
        self.expire()
        from .approval_notice import query
        if query(self, message):
            return
        parsed = parse_reply(message['text'])
        numbered = numbered_reply(message['text'])
        labeled = label_reply(message['text'])
        literal = None if parsed else literal_selection(message['text'])
        try:
            filled = form_reply(message['text'])
        except ValueError as error:
            self.store.mark(message['id'], 'local', reply=str(error))
            return
        with self.store.lock, self.store.db:
            if parsed is None and numbered is None and filled is None and labeled is None and literal is None:
                reply = '请回复“数字 A编号”，例如“1 A0123456789”（以通知实际编号为准）；没有提交决定，也不会作为新任务。'
            else:
                if filled:
                    code, _ = filled
                    decision = None
                elif numbered or labeled or literal:
                    index, code = numbered or labeled or literal
                    if code is None:
                        candidates = self.store.db.execute("SELECT code FROM remote_approvals WHERE state='pending'").fetchall()
                        code = candidates[0]['code'] if len(candidates) == 1 else ''
                    decision = None
                else:
                    code, decision = parsed
                row = self.store.db.execute('SELECT * FROM remote_approvals WHERE code=?', (code,)).fetchone()
                sent = self.store.db.execute('SELECT delivered FROM outbox WHERE id=?', ('approval:' + code,)).fetchone()
                missing_parts = self.store.db.execute("SELECT 1 FROM outbox WHERE id LIKE ? AND delivered=0 LIMIT 1", ('approval:' + code + ':part:%',)).fetchone()
                retired = self.store.db.execute('SELECT 1 FROM retired_approval_codes WHERE code=?', (code,)).fetchone() if row is None else None
                problem = ('这个手机编号已过期；发送“审批”取得新编号，没有提交决定。' if retired else blocked_reply(row, message, sent, missing_parts,
                                        bool((numbered or labeled) and (numbered or labeled)[1] is None))
                           )
                if problem:
                    reply = problem
                else:
                    choices = json.loads(row['choices'])
                    response = None
                    error = ''
                    if filled:
                        try:
                            visible(filled[1])
                            response = typed_answer(json.loads(row['form']), filled[1])
                        except (ValueError, KeyError, TypeError) as problem:
                            error = str(problem)
                    elif literal and not numbered:
                        exact = [item for item in choices if item['label'].strip().casefold() == literal[0].casefold()]
                        item = exact[0] if len(exact) == 1 else {}
                        if not item and labeled:
                            for candidate in choices:
                                payload = candidate.get('response') or {}
                                matches = candidate.get('decision') == labeled[0] or payload.get('decision') == labeled[0]
                                matches = matches or (payload.get('action') == labeled[0] and not payload.get('content'))
                                if row['method'] == 'item/tool/requestUserInput':
                                    matches = candidate['label'].strip().lower() in (('allow', 'accept', '允许') if labeled[0] == 'accept' else ('cancel', '取消'))
                                if matches:
                                    exact.append(candidate)
                            item = exact[0] if len(exact) == 1 else {}
                        decision, response = item.get('decision'), item.get('response')
                    elif labeled:
                        candidates = []
                        for item in choices:
                            payload = item.get('response') or {}
                            matches = item.get('decision') == labeled[0]
                            matches = matches or (payload.get('action') == labeled[0] and not payload.get('content'))
                            if row['method'] == 'item/tool/requestUserInput':
                                matches = item['label'].strip().lower() in (('allow', 'accept', '允许') if labeled[0] == 'accept' else ('cancel', '取消'))
                            if matches:
                                candidates.append(item)
                        item = candidates[0] if len(candidates) == 1 else {}
                        decision, response = item.get('decision'), item.get('response')
                    elif numbered:
                        item = choices[index - 1] if 1 <= index <= len(choices) else {}
                        decision, response = item.get('decision'), item.get('response')
                    elif row['method'] != METHOD:
                        error = '这类请求请按通知回复选项号，不能套用命令审批的批准/拒绝格式。'
                    elif decision == 'decline' and choices and not any(c.get('decision') == 'decline' for c in choices):
                        decision = None
                    valid_command = row['method'] == METHOD and decision in ('accept', 'decline', 'cancel')
                    if error or (not valid_command and response is None):
                        reply = error or '该选项尚未启用或编号无效；执行本次可选择单次允许。没有提交决定。'
                    else:
                        self.store.db.execute("UPDATE remote_approvals SET state='queued',decision=?,response=? WHERE code=?",
                                              (decision or '', json.dumps(response), code))
                        reply = '已收到你对 ' + code + ' 的选择，等待提交到 Codex。'

            self.store.mark(message['id'], 'local', reply=reply)

    def has_recent_prompt(self, pending_only=False):
        self.expire()
        with self.store.lock:
            if pending_only:
                return bool(self.store.db.execute("SELECT 1 FROM remote_approvals WHERE state IN ('pending','queued','sending') LIMIT 1").fetchone())
            return bool(self.store.db.execute("SELECT 1 FROM remote_approvals WHERE state!='native' AND created>=? LIMIT 1", (time.time() - 600,)).fetchone())

    def claim(self, connection):
        with self.store.lock, self.store.db:
            row = self.store.db.execute("SELECT * FROM remote_approvals WHERE state='queued' AND server_live=1 AND connection=? AND expires>=? ORDER BY created LIMIT 1",
                                       (connection, time.time())).fetchone()
            if not row:
                return None
            self.store.db.execute("UPDATE remote_approvals SET state='sending' WHERE code=?", (row['code'],))
            if row['method'] == METHOD:
                return json.loads(row['request_key']), row['decision']
            return json.loads(row['request_key']), json.loads(row['response']), row['method']
