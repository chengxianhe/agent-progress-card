"""Opt-in human approval subscription to one already open thread."""
import json
import time
import uuid

from .local_socket import LocalSocket, RpcError, TransportError
from .approval_requests import METHOD, FILE, INPUT, MCP, PERMISSIONS, retained_event


class ApprovalConnection(LocalSocket):
    def __init__(self, path):
        self.events = []
        super().__init__(path)

    def call(self, method, params):
        if method == 'initialize':
            params['capabilities']['requiredHumanApproval'] = True
            params['capabilities']['mcpServerOpenaiFormElicitation'] = True
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
            if retained_event(value):
                if len(self.events) >= 64:
                    raise TransportError('待审批事件过多，请在电脑端处理')
                self.events.append(value)

    def subscribe(self, session):
        session.inspect(self)  # Refuse to load another or closed session.
        result = self.call('thread/resume', {'threadId': session.thread_id, 'excludeTurns': True})
        if result.get('thread', {}).get('id') != session.thread_id:
            raise TransportError('审批订阅会话不一致')

    def respond(self, identity, decision, method=METHOD):
        if method == METHOD:
            if decision not in ('accept', 'decline', 'cancel'):
                raise ValueError('Only explicit one-time human decisions are supported')
            result = {'decision': decision}
        else:
            result = decision
            if not isinstance(result, dict):
                raise ValueError('Typed response must be an object')
            valid = False
            if method == FILE:
                valid = set(result) == {'decision'} and result['decision'] in ('accept', 'decline', 'cancel')
            elif method == MCP:
                valid = (set(result) == {'action', 'content', '_meta'} and result['_meta'] is None
                         and result['action'] in ('accept', 'decline', 'cancel')
                         and (isinstance(result['content'], dict) if result['action'] == 'accept' else result['content'] is None))
            elif method == INPUT:
                valid = set(result) == {'answers'} and isinstance(result['answers'], dict) and all(
                    isinstance(k, str) and isinstance(v, dict) and set(v) == {'answers'} and
                    isinstance(v['answers'], list) and len(v['answers']) == 1 and isinstance(v['answers'][0], str)
                    for k, v in result['answers'].items())
            elif method == PERMISSIONS:
                valid = (set(result) == {'permissions', 'scope'} and result['scope'] == 'turn'
                         and isinstance(result['permissions'], dict) and not set(result['permissions']) - {'network', 'fileSystem'})
            elif method in ('execCommandApproval', 'applyPatchApproval'):
                rejected = result.get('decision')
                valid = set(result) == {'decision'} and (
                    rejected in ('approved', 'abort') or
                    (isinstance(rejected, dict) and set(rejected) == {'denied'}
                     and isinstance(rejected['denied'], dict) and set(rejected['denied']) == {'rejection'}
                     and isinstance(rejected['denied']['rejection'], str)))
            if not valid:
                raise ValueError('Invalid typed response; no permission overrides')
        self._send(json.dumps({'id': identity, 'result': result}).encode())
