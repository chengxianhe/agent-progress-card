"""First-run binding of one user-selected record, with state/history rollback."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time
import uuid

from .activity import timestamp
from .history import read_history, update_history
from .store import ProgressStore, checked_text, default_directory, TERMINAL
from .watcher import MAX_LINE, validate_source


class SetupError(ValueError):
    pass


def inspect(path):
    source = Path(path).resolve(strict=True)
    if not source.is_file():
        raise SetupError('请选择会话记录文件。')
    with source.open('rb') as stream:
        first = stream.readline(MAX_LINE + 1)
        if len(first) > MAX_LINE:
            raise SetupError('会话记录头部过大。')
        meta = json.loads(first)
        payload = meta.get('payload') if isinstance(meta, dict) else None
        thread = payload.get('id') if isinstance(payload, dict) else None
        if not isinstance(meta, dict) or meta.get('type') != 'session_meta' or not isinstance(thread, str):
            raise SetupError('所选文件不是受支持的 Codex 会话记录。')
        uuid.UUID(thread)
        since = 0
        start = max(stream.tell(), os.fstat(stream.fileno()).st_size - 16 * 1024 * 1024)
        partial = start > stream.tell()
        stream.seek(start)
        remaining = os.fstat(stream.fileno()).st_size - start
        while remaining > 0:
            line = stream.readline(min(MAX_LINE + 1, remaining))
            remaining -= len(line)
            if not line:
                break
            if partial or len(line) > MAX_LINE or not line.endswith(b'\n'):
                partial = not line.endswith(b'\n')
                continue
            try:
                record = json.loads(line)
                payload = record.get('payload', {})
                if record.get('type') == 'event_msg' and payload.get('type') == 'task_started':
                    since = timestamp(record.get('timestamp'))
            except (ValueError, TypeError, AttributeError):
                continue
    if since <= 0:
        raise SetupError('请在这个 Codex 对话发送一条新消息，再重新选择记录。')
    return {'path': str(source), 'thread_id': thread, 'since': since}


def atomic_bytes(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix='.setup-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def connect(directory, source, expected_thread, title, replace=False):
    binding = inspect(source)
    if binding['thread_id'] != expected_thread:
        raise SetupError('记录身份已变化，请重新选择并确认。')
    title = checked_text(title, '任务名称', 80)
    store = ProgressStore(Path(directory))
    with store._locked():
        current = store.read()
        read_history(store.directory)
        if current and current['status'] not in TERMINAL and not replace:
            raise SetupError('已有未结束的看板任务；请明确确认切换，旧任务不会被取消。')
        checkpoint = {}
        for name, limit in [('activity-source.json', 16384), ('state.json', 65536), ('history.json', 4194304)]:
            file = store.directory / name
            if file.exists():
                with file.open('rb') as stream:
                    raw = stream.read(limit + 1)
                if len(raw) > limit:
                    raise SetupError('已有本机记录过大，未修改。')
                checkpoint[name] = raw
            else:
                checkpoint[name] = None
        now = time.time()
        event = {'id': str(uuid.uuid4()), 'time': now, 'action': '已连接会话，等待新的工作说明',
                 'detail': '', 'status': 'running'}
        state = {'version': 1, 'task_id': str(uuid.uuid4()), 'title': title, 'status': 'running',
                 'action': event['action'], 'detail': '', 'started_at': now, 'updated_at': now, 'events': [event]}
        try:
            if current:
                update_history(store.directory, current)
            validate_source(Path(binding['path']), expected_thread)
            atomic_bytes(store.directory / 'activity-source.json', json.dumps(binding).encode())
            store._save(state)
            # An already-polled old feed cannot bind the new task to the previous thread.
            update_history(store.directory, state, {'thread_id': expected_thread, 'error': '', 'calls': [], 'notes': []})
        except BaseException:
            for name, raw in checkpoint.items():
                file = store.directory / name
                if raw is None:
                    file.unlink(missing_ok=True)
                else:
                    atomic_bytes(file, raw)
            raise
        return {'thread_id': expected_thread, 'task_id': state['task_id']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['inspect', 'connect'])
    parser.add_argument('--transcript', type=Path, required=True)
    parser.add_argument('--thread-id')
    parser.add_argument('--title', default='我的 Codex 任务')
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    try:
        value = inspect(args.transcript) if args.action == 'inspect' else connect(
            default_directory(), args.transcript, args.thread_id, args.title, args.replace)
        result = {'ok': True, 'value': value}
    except SetupError as error:
        result = {'ok': False, 'message': str(error)}
    except (OSError, ValueError, TypeError, KeyError):
        result = {'ok': False, 'message': '无法连接所选记录，请确认它属于目标会话、已开始过任务且本机记录可写。'}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
