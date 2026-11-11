"""Login-agent supervisor: preserve explicit binding, credentials and manual stops."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid

from agent_progress_card.store import default_directory
from .files import read_json, save_json


def relay_target(card):
    source = read_json(card / 'wechat-source.json')
    binding = read_json(card / 'activity-source.json')
    if source.get('version') != 1:
        raise ValueError('Unsupported binding')
    directory = Path(source['directory'])
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise ValueError('Invalid state directory')
    thread = binding['thread_id']
    uuid.UUID(thread)
    state = read_json(directory / 'connection.json')
    if state.get('mode') != 'current_session' or state.get('thread_id') != thread:
        return directory, None, 'binding_changed'
    if (directory / 'stop-request').exists() or (directory / 'reconnect-request').exists():
        return directory, None, 'manually_stopped'
    credentials = directory / 'credentials.json'
    if not credentials.is_file() or credentials.is_symlink():
        return directory, None, 'login_required'
    if state.get('status') == 'expired' and credentials.stat().st_mtime <= (directory / 'connection.json').stat().st_mtime:
        return directory, None, 'login_expired'
    # Existing service owns its lock. Do not spawn a second poller or steal its cursor.
    with (directory / 'service.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return directory, None, 'already_running'
        fcntl.flock(lock, fcntl.LOCK_UN)
    return directory, thread, 'ready'


def supervise(card, stop, launch=subprocess.Popen):
    while not stop.is_set():
        child = None
        try:
            directory, thread, status = relay_target(card)
            save_json(card / 'resident.json', {'status': status, 'enabled': True})
            if thread:
                environment = os.environ.copy()
                environment['PYTHONDONTWRITEBYTECODE'] = '1'
                child = launch([sys.executable, '-B', '-m', 'agent_progress_wechat.relay',
                                '--state-dir', str(directory), '--thread-id', thread, '--card-dir', str(card)],
                               env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                save_json(card / 'resident.json', {'status': 'running', 'enabled': True})
                while child.poll() is None and not stop.wait(1):
                    pass
        except (OSError, ValueError, KeyError, TypeError):
            save_json(card / 'resident.json', {'status': 'waiting_for_binding', 'enabled': True})
        finally:
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        stop.wait(15)


def main():
    parser = argparse.ArgumentParser(description='保持本人微信桥接运行；尊重手动停止及原会话绑定')
    parser.add_argument('--card-dir', type=Path, default=default_directory())
    args = parser.parse_args()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    supervise(args.card_dir, stop)


if __name__ == '__main__':
    main()
