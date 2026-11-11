"""Opt-in human approval subscription to one already open thread."""
import json
import time
import uuid

from .local_socket import LocalSocket, RpcError, TransportError


class ApprovalConnection(LocalSocket):
    def __init__(self, path):
        self.events = []
        super().__init__(path)

    def call(self, method, params):
        if method == 'initialize':
            params['capabilities']['requiredHumanApproval'] = True
        identity = 'approval-' + uuid.uuid4().hex
        self._send(json.dumps({'id': identity, 'method': method, 'params': params}).encode())
        deadline = time.monotonic() + self.timeout
        while True:
            value = self._receive(deadline)
            if not isinstance(value, dict):
                continue
            if value.get('id') == identity and 'method' not in value:
                if 'error' in value:
                    raise RpcError(value['error'].get('code'))
                if 'result' not in value:
                    raise TransportError('审批连接缺少回执')
                return value['result']
            # Never retain streamed model output, reasoning or command output.
            method = value.get('method', '')
            if method.endswith('/requestApproval') or method == 'serverRequest/resolved':
                if len(self.events) >= 64:
                    raise TransportError('待审批事件过多，请在电脑端处理')
                self.events.append(value)

    def subscribe(self, session):
        session.inspect(self)  # Refuse to load another or closed session.
        result = self.call('thread/resume', {'threadId': session.thread_id, 'excludeTurns': True})
        if result.get('thread', {}).get('id') != session.thread_id:
            raise TransportError('审批订阅会话不一致')

    def respond(self, identity, decision):
        if decision not in ('accept', 'decline', 'cancel'):
            raise ValueError('Only explicit one-time human decisions are supported')
        self._send(json.dumps({'id': identity, 'result': {'decision': decision}}).encode())
